# Security in BusPlus

## What is protected, and how

| Risk | Protection |
|---|---|
| Stolen passwords or PINs | Driver PINs are stored only as salted hashes (Werkzeug scrypt). The admin can set a new PIN but can never see an old one. |
| Password and PIN guessing | Logins are rate-limited per IP address by Flask-Limiter. Admin: 5 per minute and 30 per hour. Driver: 10 per minute. |
| Other websites acting as a signed-in user (CSRF) | Every POST, PUT and DELETE needs the page's CSRF token (Flask-WTF). `static/js/common.js` adds it to every request automatically. |
| Someone else moving a bus | Location updates are accepted only from the signed-in driver's phone. They always go to that driver's own bus, whatever the request says. |
| One driver account used on two phones | One phone at a time. The admin can unlock an account in the backend. |
| Injected scripts (XSS) | Jinja escapes pages automatically. JavaScript escapes server text or uses `textContent`. A Content-Security-Policy lets the browser load code only from BusPlus itself; the only outside images are Google map tiles. |
| Cookie theft | The session cookie is `HttpOnly`, `SameSite=Lax`, signed with `SECRET_KEY`, and `Secure` (HTTPS-only) in production. |
| Unencrypted traffic | In production, http:// is redirected to https:// and HSTS is turned on. Let's Encrypt provides HTTPS through nginx. |
| Clickjacking and content sniffing | `X-Frame-Options`, `frame-ancestors 'none'` and `X-Content-Type-Options: nosniff` are set by Flask-Talisman. |
| Leaking private data | The public bus feed contains no phone numbers or PINs. The backend is admin-only; drivers can't open it. |
| Weak production setup | In production the app refuses to start without a strong `SECRET_KEY` and admin password. Debug mode is always off in production. |
| Server compromise | The app runs as its own `busplus` user under systemd hardening and can write only to `instance/`. The firewall allows only SSH and web traffic. The GitHub deploy key can run nothing but `deploy/update.sh`. |
| Losing data | The database is backed up every night, and the last 14 days are kept. |

## Secrets: never put these on GitHub

- `.env`: holds `SECRET_KEY` and the admin password.
- `instance/`: holds the database, plus the secret key and password files created on your computer.
- `backups/`

All three are listed in `.gitignore`. Before your first push, check with `git status` that none of them appear.

If a secret was ever pushed by mistake:

1. Change it: make a new `SECRET_KEY` and admin password in `/opt/busplus/.env` on the server.
2. Restart the app: `sudo systemctl restart busplus`.
3. Remove the secret from the Git history.

## Notes

- Students and teachers sign in with just a name and an ID, with no password. They can only *view* bus positions, which are public information, so nothing sensitive is behind that sign-in.
- The admin password lives in `.env` on the server. Use a long one, and change it there (then restart) if it ever leaks.
- To report a problem, contact the BusPlus maintainers privately rather than opening a public issue.
