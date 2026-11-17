/*
 * BusPlus GPS tracker - ESP32 + NEO-6M
 * =====================================
 * Reads the bus's position from a NEO-6M GPS module and sends it to the BusPlus
 * server every few seconds over Wi-Fi (a phone hotspot or a 4G pocket router in the bus).
 *
 *   NEO-6M  ->  ESP32
 *   VCC     ->  3V3   (or 5V/VIN if your GPS board has its own regulator, most do)
 *   GND     ->  GND
 *   TX      ->  GPIO 16  (ESP32 RX2)
 *   RX      ->  GPIO 17  (ESP32 TX2)   - optional, only needed to change GPS settings
 *
 * Before uploading:
 *   1. Arduino IDE > Boards Manager: install "esp32" by Espressif Systems.
 *   2. Library Manager: install "TinyGPSPlus" by Mikal Hart.
 *   3. Copy secrets.example.h to secrets.h (same folder) and fill in your Wi-Fi and the Server URL.
 *      DEVICE_KEY: paste a key from the backend (GPS devices > Add a device > Manually / Quick add),
 *      OR leave it empty ("") and the box asks to join by itself (see "Joining by itself" below).
 *   4. Tools > Board: "ESP32 Dev Module". Pick the port, click Upload.
 *   5. Tools > Serial Monitor at 115200 baud shows what the tracker is doing.
 *
 * What it sends (POST <SERVER_URL>, header "X-Device-Key: <DEVICE_KEY>"):
 *   {"fix":true,"lat":22.802090,"lng":89.533980,"speed_kmh":31.5,"course":182.0,
 *    "sats":8,"hdop":1.10,"age_ms":420,"time":"2026-11-17T08:15:01Z",
 *    "rssi":-67,"fw":"1.0.0","uptime_s":3600}
 * While the GPS is still searching for satellites it sends {"fix":false,...} now and then,
 * so the backend shows the box as connected ("Searching for satellites").
 *
 * The server answers {"ok":true,"bus_id":"KU-BUS-01","send_every_s":2}. The tracker
 * follows send_every_s, so the interval can be changed in content/rules.py without re-flashing.
 *
 * Joining by itself (DEVICE_KEY empty):
 *   The box POSTs {"chip_id","token","fw"} to <server>/api/device/pair every 5 seconds and prints a
 *   6-digit pairing code on the serial monitor. The backend shows the same code under
 *   GPS devices > Add a device > Automatically. After the admin approves it, the box receives its key
 *   and saves it in flash memory (it survives power cuts and re-uploads of the same sketch).
 *   If the server later refuses the saved key (new key made, or device deleted), the box forgets it
 *   and asks to join again.
 *
 * Full guide: firmware/README.md
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <TinyGPSPlus.h>
#include <Preferences.h>

#include "secrets.h"   // WIFI_SSID, WIFI_PASSWORD, SERVER_URL, DEVICE_KEY  (see secrets.example.h)
#ifndef DEVICE_KEY
#define DEVICE_KEY ""    // no key: ask to join by itself
#endif

// ---------------------------------------------------------------------------
// Settings you may change
// ---------------------------------------------------------------------------
#define FIRMWARE_VERSION   "1.2.0"
#define GPS_RX_PIN         16        // ESP32 pin that receives from the GPS's TX
#define GPS_TX_PIN         17        // ESP32 pin that sends to the GPS's RX
#define GPS_BAUD           9600      // NEO-6M factory setting
#define LED_PIN            2         // on-board LED of most ESP32 dev boards (-1 = no LED)

#define DEFAULT_SEND_MS    2000      // until the server says otherwise
#define MIN_SEND_MS        1000
#define MAX_SEND_MS        60000
#define NO_FIX_SEND_MS     10000     // heartbeat while the GPS has no position
#define MAX_FIX_AGE_MS     5000      // a position older than this counts as "no fix"
#define HTTP_TIMEOUT_MS    8000
#define WIFI_RETRY_MS      10000
#define PAIR_RETRY_MS      5000      // while waiting for the admin's approval (the server may say otherwise)
#define PAIR_REJECTED_MS   60000     // after the admin said no

// HTTPS: the server's certificate is checked against the root certificates built into the
// ESP32 (the same ones browsers trust, e.g. Let's Encrypt), so nobody on the bus Wi-Fi can pose
// as the server and read the device key. Two optional settings, in secrets.h:
//   #define SERVER_ROOT_CA "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"
//        trust only this one root certificate (stricter)
//   #define INSECURE_TLS
//        don't check the certificate at all (only for testing; anyone on the network could read the key)
// The connection is kept open between reports, so the slow HTTPS handshake happens only once.

// ---------------------------------------------------------------------------
TinyGPSPlus gps;
HardwareSerial gpsSerial(2);

Preferences prefs;                 // flash memory: the key received by joining, and this box's pairing token

String deviceKey;                  // the key in use ("" = not joined yet: ask to join)
bool keyFromFlash = false;         // true: received by joining (forgotten if the server refuses it)
String chipId;                     // this ESP32's chip ID (from its factory MAC address)
String pairToken;                  // random secret made once; proves the key request comes from this box
String pairCode;                   // 6-digit code from the server, shown on the serial monitor
unsigned long pairEveryMs = PAIR_RETRY_MS;
unsigned long lastPairMs = 0;

unsigned long sendEveryMs = DEFAULT_SEND_MS;
unsigned long lastSendMs = 0;
unsigned long lastWifiTryMs = 0;
unsigned long lastStatusMs = 0;
uint32_t okCount = 0, failCount = 0;

// ---------------------------------------------------------------------------
// LED: slow blink = no Wi-Fi, fast blink = no GPS fix, short flash = position sent
// ---------------------------------------------------------------------------
void setLed(bool on) {
  if (LED_PIN >= 0) digitalWrite(LED_PIN, on ? HIGH : LOW);
}

void updateLed(bool wifiOk, bool fixOk) {
  if (LED_PIN < 0) return;
  // slow = no Wi-Fi, medium = waiting to be approved, fast = no GPS fix
  unsigned long period = !wifiOk ? 1000 : (deviceKey.length() == 0 ? 500 : (!fixOk ? 250 : 0));
  if (period == 0) return;                                  // all good: only flashes when sending
  setLed((millis() / period) % 2 == 0);
}

// ---------------------------------------------------------------------------
// Wi-Fi
// ---------------------------------------------------------------------------
void startWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWifiTryMs = millis();
  Serial.printf("[wifi] connecting to \"%s\" ...\n", WIFI_SSID);
}

bool wifiReady() {
  if (WiFi.status() == WL_CONNECTED) return true;
  if (millis() - lastWifiTryMs > WIFI_RETRY_MS) {           // still not connected: try again
    WiFi.disconnect();
    startWifi();
  }
  return false;
}

// ---------------------------------------------------------------------------
// GPS: feed every byte from the NEO-6M into TinyGPSPlus (call this as often as possible)
// ---------------------------------------------------------------------------
void readGps() {
  while (gpsSerial.available() > 0) {
    gps.encode(gpsSerial.read());
  }
}

bool haveFix() {
  return gps.location.isValid() && gps.location.age() < MAX_FIX_AGE_MS &&
         !(gps.location.lat() == 0.0 && gps.location.lng() == 0.0);
}

// ---------------------------------------------------------------------------
// Report -> JSON (built by hand: no extra library needed)
// ---------------------------------------------------------------------------
String buildReport(bool fix) {
  char buf[400];
  int n = snprintf(buf, sizeof(buf), "{\"fix\":%s", fix ? "true" : "false");

  if (fix) {
    n += snprintf(buf + n, sizeof(buf) - n, ",\"lat\":%.6f,\"lng\":%.6f,\"age_ms\":%lu",
                  gps.location.lat(), gps.location.lng(), (unsigned long)gps.location.age());
    if (gps.speed.isValid())  n += snprintf(buf + n, sizeof(buf) - n, ",\"speed_kmh\":%.1f", gps.speed.kmph());
    if (gps.course.isValid()) n += snprintf(buf + n, sizeof(buf) - n, ",\"course\":%.1f", gps.course.deg());
    if (gps.date.isValid() && gps.time.isValid() && gps.date.year() >= 2024) {
      n += snprintf(buf + n, sizeof(buf) - n, ",\"time\":\"%04d-%02d-%02dT%02d:%02d:%02dZ\"",
                    gps.date.year(), gps.date.month(), gps.date.day(),
                    gps.time.hour(), gps.time.minute(), gps.time.second());
    }
  }
  if (gps.satellites.isValid()) n += snprintf(buf + n, sizeof(buf) - n, ",\"sats\":%lu",
                                              (unsigned long)gps.satellites.value());
  if (gps.hdop.isValid())       n += snprintf(buf + n, sizeof(buf) - n, ",\"hdop\":%.2f", gps.hdop.hdop());
  n += snprintf(buf + n, sizeof(buf) - n, ",\"rssi\":%d,\"fw\":\"%s\",\"uptime_s\":%lu}",
                (int)WiFi.RSSI(), FIRMWARE_VERSION, millis() / 1000UL);
  return String(buf);
}

// Reads "send_every_s":N from the server's answer (no JSON library needed for one number).
void followServerInterval(const String& body) {
  int at = body.indexOf("\"send_every_s\":");
  if (at < 0) return;
  float seconds = body.substring(at + 15).toFloat();
  if (seconds <= 0) return;
  unsigned long ms = (unsigned long)(seconds * 1000);
  sendEveryMs = constrain(ms, (unsigned long)MIN_SEND_MS, (unsigned long)MAX_SEND_MS);
}

// ---------------------------------------------------------------------------
// HTTP: POST a JSON body. Returns the HTTP status (or a negative error code); the reply goes to `answer`.
// ---------------------------------------------------------------------------
HTTPClient http;                   // kept between reports: the connection stays open (setReuse)
WiFiClient plainClient;
WiFiClientSecure secureClient;

void setupHttp() {
#if defined(INSECURE_TLS)
  secureClient.setInsecure();
  Serial.println("[http] WARNING: INSECURE_TLS - the server certificate is not checked");
#elif defined(SERVER_ROOT_CA)
  secureClient.setCACert(SERVER_ROOT_CA);
#else
  secureClient.useBuiltinCACertBundle();     // trusted root certificates built into the ESP32
#endif
  secureClient.setHandshakeTimeout(15);      // seconds; mobile data can be slow
  http.setReuse(true);
}

int postJson(const String& url, const String& body, const String& key, String& answer) {
  bool started = url.startsWith("https://") ? http.begin(secureClient, url) : http.begin(plainClient, url);
  if (!started) {
    Serial.println("[http] bad SERVER_URL in secrets.h");
    answer = "";
    return -100;
  }

  http.setTimeout(HTTP_TIMEOUT_MS);
  http.addHeader("Content-Type", "application/json");
  if (key.length()) http.addHeader("X-Device-Key", key);
  setLed(true);
  int status = http.POST(body);
  setLed(false);
  answer = status > 0 ? http.getString() : http.errorToString(status);
  http.end();                                 // keeps the connection open for the next report (setReuse)
  if (status < 0) {                           // network error: start the next report on a fresh connection
    secureClient.stop();
    plainClient.stop();
  }
  return status;
}

// The value of "name":"..." in a small JSON reply ("" if it isn't there). No JSON library needed.
String jsonText(const String& body, const char* name) {
  String pattern = String("\"") + name + "\":";
  int at = body.indexOf(pattern);
  if (at < 0) return "";
  at += pattern.length();
  while (at < (int)body.length() && body[at] == ' ') at++;      // the server may pretty-print ("key": "...")
  if (at >= (int)body.length() || body[at] != '"') return "";
  int end = body.indexOf('"', ++at);
  return end < 0 ? "" : body.substring(at, end);
}

// ---------------------------------------------------------------------------
// Send one position report. Returns the HTTP status (or a negative error code).
// ---------------------------------------------------------------------------
int sendReport(bool fix) {
  String answer;
  int status = postJson(SERVER_URL, buildReport(fix), deviceKey, answer);
  if (status == 200) {
    okCount++;
    followServerInterval(answer);
  } else {
    failCount++;
    // 401 = wrong DEVICE_KEY, 409 = device not fitted to a bus in the backend, 429 = sending too often
    Serial.printf("[http] %d %s\n", status, answer.c_str());
    if (status == 401 && keyFromFlash) {        // the key it joined with was replaced or deleted: join again
      Serial.println("[pair] the server no longer accepts the saved key: asking to join again");
      prefs.remove("key");
      deviceKey = "";
      keyFromFlash = false;
      lastPairMs = 0;
    }
  }
  return status;
}

// ---------------------------------------------------------------------------
// Joining by itself: ask the server for a key until the admin approves this box
// ---------------------------------------------------------------------------
String pairUrl() {
  String url = SERVER_URL;
  int at = url.lastIndexOf("/location");
  return (at >= 0 ? url.substring(0, at) : url) + "/pair";
}

void askToJoin() {
  String body = String("{\"chip_id\":\"") + chipId + "\",\"token\":\"" + pairToken +
                "\",\"fw\":\"" FIRMWARE_VERSION "\"}";
  String answer;
  int status = postJson(pairUrl(), body, "", answer);
  String state = jsonText(answer, "status");
  if (status == 200 && state == "approved") {
    String key = jsonText(answer, "key");
    if (key.length() >= 16) {
      prefs.putString("key", key);
      deviceKey = key;
      keyFromFlash = true;
      followServerInterval(answer);
      Serial.printf("[pair] approved as %s - key saved, sending GPS now\n", jsonText(answer, "device_id").c_str());
      return;
    }
  }
  if (status == 200 && state == "waiting") {
    pairCode = jsonText(answer, "code");
    pairEveryMs = PAIR_RETRY_MS;
    Serial.printf("[pair] waiting for approval in the backend - chip %s, pairing code %s\n",
                  chipId.c_str(), pairCode.c_str());
  } else if (status == 403) {
    pairEveryMs = PAIR_REJECTED_MS;
    Serial.println("[pair] the admin rejected this box - asking again in a minute");
  } else {
    pairEveryMs = PAIR_RETRY_MS;
    Serial.printf("[pair] %d %s\n", status, answer.c_str());
  }
}

// This box's chip ID, its pairing token (made once) and the key it joined with (if any).
void loadIdentity() {
  uint64_t mac = ESP.getEfuseMac();
  char id[13];
  snprintf(id, sizeof(id), "%04X%08X", (uint16_t)(mac >> 32), (uint32_t)mac);
  chipId = id;

  prefs.begin("busplus", false);
  pairToken = prefs.getString("token", "");
  if (pairToken.length() < 16) {
    char token[33];
    for (int i = 0; i < 4; i++) snprintf(token + i * 8, 9, "%08lx", (unsigned long)esp_random());
    pairToken = token;
    prefs.putString("token", pairToken);
  }

  String fromSecrets = DEVICE_KEY;
  if (fromSecrets.length() >= 16 && fromSecrets.indexOf("paste") < 0) {
    deviceKey = fromSecrets;                    // a key typed into secrets.h always wins
  } else {
    deviceKey = prefs.getString("key", "");
    keyFromFlash = deviceKey.length() > 0;
  }
  Serial.printf("Chip ID %s - %s\n", chipId.c_str(),
                deviceKey.length() ? (keyFromFlash ? "key from joining" : "key from secrets.h") : "no key yet: asking to join");
}

// ---------------------------------------------------------------------------
// Serial monitor: a status line every 5 seconds
// ---------------------------------------------------------------------------
void printStatus() {
  if (millis() - lastStatusMs < 5000) return;
  lastStatusMs = millis();
  Serial.printf("[status] wifi=%s rssi=%d | gps chars=%lu sats=%lu hdop=%.1f fix=%s",
                WiFi.status() == WL_CONNECTED ? "ok" : "no", (int)WiFi.RSSI(),
                (unsigned long)gps.charsProcessed(),
                gps.satellites.isValid() ? (unsigned long)gps.satellites.value() : 0UL,
                gps.hdop.isValid() ? gps.hdop.hdop() : 99.9, haveFix() ? "yes" : "no");
  if (haveFix()) Serial.printf(" pos=%.6f,%.6f %.1fkm/h", gps.location.lat(), gps.location.lng(), gps.speed.kmph());
  if (deviceKey.length() == 0) Serial.printf(" | waiting to join, code %s", pairCode.length() ? pairCode.c_str() : "-");
  Serial.printf(" | sent ok=%lu failed=%lu every=%lums\n", (unsigned long)okCount, (unsigned long)failCount, sendEveryMs);
  if (millis() > 10000 && gps.charsProcessed() < 10) {
    Serial.println("[gps] no data from the GPS: check the wiring (GPS TX -> ESP32 GPIO 16) and power");
  }
}

// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\nBusPlus GPS tracker %s\n", FIRMWARE_VERSION);
  if (LED_PIN >= 0) pinMode(LED_PIN, OUTPUT);
  gpsSerial.setRxBufferSize(2048);          // keeps ~2 s of GPS data while a report is being sent
  gpsSerial.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
  loadIdentity();
  setupHttp();
  startWifi();
}

void loop() {
  readGps();
  bool wifiOk = wifiReady();
  bool fix = haveFix();
  updateLed(wifiOk, fix);
  printStatus();

  if (deviceKey.length() == 0) {                // not joined yet: ask the server for a key
    if (wifiOk && (lastPairMs == 0 || millis() - lastPairMs >= pairEveryMs)) {
      lastPairMs = millis();
      askToJoin();
    }
    delay(5);
    return;
  }

  unsigned long wait = fix ? sendEveryMs : NO_FIX_SEND_MS;
  if (wifiOk && millis() - lastSendMs >= wait) {
    lastSendMs = millis();
    sendReport(fix);
  }
  delay(5);
}
