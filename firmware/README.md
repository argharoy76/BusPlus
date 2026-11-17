# BusPlus GPS box (ESP32 + NEO-6M)

Each bus carries one small box. It reads the bus's position from a NEO-6M GPS module and sends it
to BusPlus every 2 seconds over Wi-Fi. BusPlus then moves that bus on every student, teacher and
staff map. Nobody on the bus has to do anything: power on = bus online.

```
NEO-6M GPS  --serial-->  ESP32  --Wi-Fi (bus hotspot / 4G router)-->  BusPlus server  -->  live maps
```

## 1. Parts (per bus)

| Part | Notes |
|---|---|
| ESP32 dev board (ESP32-WROOM-32, "ESP32 DevKit V1") | any common ESP32 board works |
| NEO-6M GPS module with its ceramic antenna (GY-NEO6MV2) | put the antenna where it sees the sky (under the windscreen) |
| Internet in the bus | a 4G pocket router or an old phone as a hotspot |
| 12 V → 5 V USB car adapter + USB cable | powers the ESP32 from the bus |
| 4 jumper wires, a small box | |

## 2. Wiring

| NEO-6M pin | ESP32 pin |
|---|---|
| VCC | 3V3 (or VIN/5V: most GY-NEO6MV2 boards have their own regulator) |
| GND | GND |
| TX  | GPIO 16 (RX2) |
| RX  | GPIO 17 (TX2), optional |

## 3. Add the device in BusPlus

Open the backend (`/backend`) → **GPS devices**. The **Add a device** box at the top has two ways:

**Manually**: type a name (e.g. "Tracker in Bus #01"), choose its bus, click **Add device**.
**Automatically → Quick add**: one click; the name is made for you and the device is fitted to the first bus
without one.

Both show the **Device settings** pop-up with the **Server URL**, the **Device key** and a ready-made `secrets.h`.
Click **Copy all**. The key is shown **only this once** (BusPlus stores only a hash of it).
Lost it? **New key** makes another one and the old one stops working.

**Automatically → Boxes asking to join** (no key to copy at all):

1. Leave `DEVICE_KEY` empty (`""`) in `secrets.h` and upload the sketch.
2. Switch the box on. It asks the server to join every 5 seconds and prints a **pairing code** on the serial
   monitor, e.g. `[pair] waiting for approval in the backend - chip 24A160C8F3B4, pairing code 483920`.
3. The backend lists the box under **Automatically** (the menu shows how many are waiting). Check that the
   pairing code is the same, give it a name and a bus (or leave them for automatic ones), click **Approve**.
4. Within a few seconds the box receives its key, saves it in its flash memory and starts sending GPS.
   It keeps the key after power cuts. **Reject** ignores the box for an hour.

If the saved key stops working (you made a new key or deleted the device), the box forgets it and asks to join again.

## The connected devices list

Under the counts, every device shows its status (**Sending GPS**, **Searching for satellites**, **Offline**,
**Never connected**), satellites, signal and last report.

- **Remove from map**: the bus disappears from every map (admin, students, teachers, staff). The box stays
  connected and keeps reporting, so you can still see its status. **Show on map** brings it back with its next position.
- **View live**: opens the Live map on that bus.
- **Edit**, **New key**, **Delete** as before.

## 4. Upload the firmware

1. Install the [Arduino IDE](https://www.arduino.cc/en/software).
2. **Boards Manager**: install **esp32** by Espressif Systems.
3. **Library Manager**: install **TinyGPSPlus** by Mikal Hart.
4. Open `firmware/busplus_tracker/busplus_tracker.ino`.
5. Make `secrets.h` next to it: paste what you copied in step 3, or copy `secrets.example.h` to
   `secrets.h` and fill it in. Put in your Wi-Fi name and password. Leave `DEVICE_KEY` as `""` to let
   the box ask to join by itself. (`secrets.h` is ignored by Git.)
6. **Tools → Board → ESP32 Dev Module**, pick the port, click **Upload**.
   (If the upload hangs on "Connecting...", hold the board's **BOOT** button until it starts.)
7. **Tools → Serial Monitor**, 115200 baud. Every 5 seconds you see a status line:
   ```
   [status] wifi=ok rssi=-61 | gps chars=48211 sats=8 hdop=1.1 fix=yes pos=22.802090,89.533980 31.2km/h | sent ok=120 failed=0 every=2000ms
   ```

The first GPS fix outdoors takes **30 seconds to a few minutes** (cold start). Indoors the NEO-6M usually finds nothing.
While it searches, the backend shows the device as **Searching for satellites**. As soon as it has a fix it shows
**Sending GPS** and the bus appears on the maps.

**On-board LED**: slow blink = no Wi-Fi, medium blink = waiting to be approved, fast blink = no GPS fix,
short flash = a position was sent.

## 4b. On the live server

Use your site's HTTPS address in `secrets.h`, for example `"https://busplus.online/api/device/location"`.
The box checks the site's certificate against the root certificates built into the ESP32 (the same ones
browsers trust, such as Let's Encrypt), so nobody on the bus Wi-Fi can pose as the server or read the key.
It keeps the connection open between reports, so the slow HTTPS handshake happens only once.
Optional, in `secrets.h`: `SERVER_ROOT_CA` trusts only one root certificate; `INSECURE_TLS` turns the check off
(for testing only).

## 5. Testing on your own computer

The ESP32 can't reach `localhost`. Start BusPlus so other devices on your Wi-Fi can connect:

```
set HOST=0.0.0.0        (Windows Command Prompt)
python app.py
```

Find your computer's IP address with `ipconfig` (e.g. `192.168.0.10`) and use
`http://192.168.0.10:5000/api/device/location` as `SERVER_URL`. The backend's Device settings pop-up
already suggests this address when you open it on `localhost`. Allow Python through the Windows firewall
when asked. The ESP32 and the computer must be on the same Wi-Fi.

**No hardware yet?** `tools/simulate_gps_box.py` pretends to be a box and drives the bus along its route:

```
python tools/simulate_gps_box.py <device key>
python tools/simulate_gps_box.py              (no key: asks to join; approve it in the backend)
```

## 6. What the box sends (for anyone writing their own firmware)

`POST /api/device/location` with header `X-Device-Key: <key>` (or `Authorization: Bearer <key>`) and JSON:

```json
{"fix": true, "lat": 22.80209, "lng": 89.53398, "speed_kmh": 31.5, "course": 182.0,
 "sats": 8, "hdop": 1.1, "age_ms": 420, "time": "2026-11-17T08:15:01Z",
 "rssi": -67, "battery_v": 12.4, "fw": "1.0.0", "uptime_s": 3600}
```

Only `lat` and `lng` are required. `{"fix": false, ...}` is a heartbeat while the GPS has no position.

| Answer | Meaning |
|---|---|
| `200 {"ok": true, "bus_id": "KU-BUS-01", "send_every_s": 2, "on_map": true}` | moved the bus; send again after `send_every_s` (`on_map: false` = the admin took the bus off the map) |
| `400` | report not usable (e.g. no latitude/longitude, or 0,0) |
| `401` | wrong or old device key: make a new key in the backend and update `secrets.h` |
| `409` | the device is not fitted to a bus: choose its bus in the backend |
| `429` | sending too often (more than 120 reports a minute) |

Joining by itself: `POST /api/device/pair` with `{"chip_id": "24A160C8F3B4", "token": "<16-64 letters/digits, made once>", "fw": "1.2.0"}`
and no key. Answers: `200 {"status": "waiting", "code": "483920", "retry_s": 5}`, then after approval
`200 {"status": "approved", "key": "...", "device_id": "GPS-03", "send_every_s": 2}` (once), or `403 {"status": "rejected"}`.

The interval, the offline timeout and the rate limit are set in `content/rules.py`
(`DEVICE_SEND_EVERY_SECONDS`, `DEVICE_OFFLINE_SECONDS`, `AUTO_OFFLINE_MINUTES`, `DEVICE_LIMIT`).

## 7. Troubleshooting

| Serial monitor says | Fix |
|---|---|
| `no data from the GPS` | check GPS TX → GPIO 16, and power/GND |
| `sats=0 fix=no` for minutes | take it outside or under the windscreen; first fix can take a few minutes |
| `wifi=no` | check `WIFI_SSID` / `WIFI_PASSWORD`; the ESP32 only uses 2.4 GHz Wi-Fi |
| `[http] 401` | wrong `DEVICE_KEY` (or a new key was made): copy the new one |
| `[http] 409` | backend → GPS devices → Edit → choose the bus |
| `[http] -1` | server not reachable: check `SERVER_URL`; on your PC use its IP and `HOST=0.0.0.0` |

## Later: a SIM card instead of Wi-Fi

If the bus has no Wi-Fi, a SIM800L / SIM7600 (4G) module can carry the same HTTP request over
mobile data. The server side stays the same: it only needs the JSON above and the key.
