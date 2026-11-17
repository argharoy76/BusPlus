// BusPlus GPS tracker - your settings.
// Copy this file to "secrets.h" in the same folder and fill it in.
// secrets.h is ignored by Git: your Wi-Fi password and device key never go to GitHub.
//
// The SERVER_URL and DEVICE_KEY come from the BusPlus backend:
//   GPS devices > Add a device > Manually or Quick add (or "New key") -> the "Device settings"
//   pop-up shows both, and a ready-made secrets.h you can copy with "Copy all".
// Or leave DEVICE_KEY empty ("") and the box asks to join by itself: approve it in the backend under
//   GPS devices > Add a device > Automatically (check that the pairing code matches the serial monitor).

#define WIFI_SSID      "your-wifi-name"          // the bus's hotspot / 4G router
#define WIFI_PASSWORD  "your-wifi-password"

// Live server:        "https://bus.yourdomain.com/api/device/location"
// Your own computer:  "http://192.168.0.10:5000/api/device/location"   (your PC's IP, see README.md)
#define SERVER_URL     "https://bus.yourdomain.com/api/device/location"

#define DEVICE_KEY     ""          // "" = ask to join by itself, or paste the 24-letter key here

// HTTPS is checked against the root certificates built into the ESP32. Optional:
// #define SERVER_ROOT_CA "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n"   // trust only this root
// #define INSECURE_TLS                                                                     // testing only: no check
