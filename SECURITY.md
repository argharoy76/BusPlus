# Security in BusPlus

## What is protected, and how

| Risk | Protection |
|---|---|
| Stolen GPS device keys | Each GPS box has its own random 24-letter key (about 119 bits). Only a SHA-256 hash is stored, so the key is shown to the admin once and can never be read back from the database or the backend. The admin can make a new key (the old one stops at once) or delete the device. |
| Password and key guessing | Admin logins are rate-limited per IP address by Flask-Limiter: 5 per minute and 30 per hour. GPS reports are limited to 120 per minute per device key. A key is far too long to guess. |
| Other websites acting as a signed-in user (CSRF) | Every POST, PUT and DELETE needs the page's CSRF token (Flask-WTF). `static/js/common.js` adds it to every request automatically. |
| Someone else moving a bus | Positions are accepted only with a valid device key (`X-Device-Key` header). They always move the bus that device is fitted to in the backend, whatever the report says. Broken numbers (NaN, Infinity, out-of-range values, the NEO-6M's 0,0 before its first fix) are dropped, so one bad report can't break the maps. |
| Key sent in the clear | On the live server the GPS boxes use HTTPS and check the server's certificate against the root certificates built into the ESP32, so nobody on the bus Wi-Fi can pose as the server. The same protects the key a box receives when it joins by itself. `SERVER_ROOT_CA` in `secrets.h` trusts only one root; `INSECURE_TLS` turns the check off (testing only). |
| Boxes joining by themselves | A box that asks to join only gets a key after the admin approves it in the backend, after checking that its 6-digit pairing code matches the box's serial monitor. The key is handed out once, only to the same box (its secret token). At most 20 boxes can wait, and rejected boxes are ignored for an hour. |
| Injected scripts (XSS) | Jinja escapes pages automatically. JavaScript escapes server text or uses `textContent`. A Content-Security-Policy lets the browser load code only from BusPlus itself; the only outside images are Google map tiles. |
| A forgotten backend sign-in | The admin is signed out 12 hours after signing in (`ADMIN_SESSION_HOURS`), even if the browser stays open or a rider signs in in the same browser. Signing out needs the page's CSRF token, so other sites can't sign the admin out. |
| Cookie theft | The session cookie is `HttpOnly`, `SameSite=Lax`, signed with `SECRET_KEY`, and `Secure` (HTTPS-only) in production. |
| Unencrypted traffic | In production, http:// is redirected to https:// and HSTS is turned on. Let's Encrypt provides HTTPS through nginx. |
| Clickjacking and content sniffing | `X-Frame-Options`, `frame-ancestors 'none'` and `X-Content-Type-Options: nosniff` are set by Flask-Talisman. |
| Leaking private data | The public bus feed contains no device keys or personal data. The backend is admin-only; a device key opens nothing but the GPS report endpoint. |
| Weak production setup | In production the app refuses to start without a strong `SECRET_KEY` and admin password. Debug mode is always off in production. |
| Server compromise | The app runs as its own `busplus` user under systemd hardening and can write only to `instance/`. The firewall allows only SSH and web traffic. The GitHub deploy key can run nothing but `deploy/update.sh`. |
| Losing data | The database is backed up every night, and the last 14 days are kept. |

## Secrets: never put these on GitHub

- `.env`: holds `SECRET_KEY` and the admin password.
- `firmware/busplus_tracker/secrets.h`: holds your Wi-Fi password and a device key.
- `instance/`: holds the database, plus the secret key and password files created on your computer.
- `backups/`

All of them are listed in `.gitignore`. Before your first push, check with `git status` that none of them appear.

If a secret was ever pushed by mistake:

1. Change it: make a new `SECRET_KEY` and admin password in `/opt/busplus/.env` on the server.
2. Restart the app: `sudo systemctl restart busplus`.
3. Remove the secret from the Git history.

## Notes

- Students, teachers and staff sign in with just a name and an ID, with no password. They can only *view* bus positions, which are public information, so nothing sensitive is behind that sign-in. IDs may only use letters, digits and - _ / ., names can't contain links or code, and the name from a rider's first sign-in is kept, so someone typing another person's ID can't rename them in the Users tab.
- The admin password lives in `.env` on the server. Use a long one, and change it there (then restart) if it ever leaks.
- To report a problem, contact the BusPlus maintainers privately rather than opening a public issue.
