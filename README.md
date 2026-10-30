# BusPlus · Khulna University live bus tracker

BusPlus shows where every Khulna University bus is, live on a map.

- **Drivers** sign in on their phone and go online. The phone's GPS moves their bus on everyone's map about once a second.
- **Students** and **teachers** open the live map. Each group sees only its own buses. They can save their home and get a notice before the bus arrives.
- The **admin** manages drivers, routes and buses in the backend at `/backend`, including which route each bus drives today. Every route ends at **Hadi Chattar**.

It works on phones and on PC: phones get a bottom sheet you drag, PCs get a side panel.

---

## Run it on your computer

You need Python 3.11 or newer.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py
```

- App: <http://localhost:5000>
- Backend: <http://localhost:5000/backend>
  - username `admin`
  - the password is created on the first start and saved in `instance/admin_password.txt`
- On your computer the first start also creates four demo drivers, all with PIN `1234`.
  - Example: driver **Md. Rafiqul Islam** with route **Malabotha - Rupsha - KU Line**.

Optional: copy `.env.example` to `.env` to choose your own settings.

### Tests and code checks

```bash
pytest          # 30 automated tests
ruff check .    # code style and common mistakes
```

GitHub runs both on every push.

---

## Put it online (GitHub → Hostinger VPS)

See **[DEPLOYMENT.md](DEPLOYMENT.md)**. The short version:

1. Push this folder to a GitHub repository.
2. Run `deploy/setup_server.sh` once on your Hostinger **VPS**. It sets up:
   - HTTPS, nginx and the firewall
   - the database and its nightly backups
   - the key that lets GitHub deploy
3. Add three secrets to GitHub.
4. From then on, every `git push` to `main` is tested and then goes live by itself.

> Hostinger's shared Web/Cloud hosting can't run Python apps like this one. Only a VPS can.

---

## How the code is organised

```text
app.py                  create_app(): settings, security, database, URLs
wsgi.py                 entry point for gunicorn (production)
config.py               all settings (read from .env)
extensions.py           Flask extensions: database, CSRF, rate limits, security headers
gunicorn.conf.py        production server settings (1 process, gevent)

controllers/            URLs, one file per area
  view_controller.py      the pages
  auth_controller.py      sign-in / sign-out (admin, drivers, students, teachers)
  bus_controller.py       live buses, the live stream, and the driver phone API
  route_controller.py     routes and "your bus is coming" checks
  admin_controller.py     the backend: drivers, buses, routes, road snapping
  helpers.py              shared helpers (JSON replies, driver check)

services/               the app's logic
  tracking_service.py     routes, buses, live GPS, trails, test drives, live updates
  user_service.py         driver accounts, PIN sign-in, one-phone lock, duty notices
  notification_service.py arrival alerts
  geo.py                  distances, directions, ETA
  road_router.py          snaps a drawn route to real roads (OpenStreetMap / OSRM)
  store.py                saving to / loading from the database

models/                 data
  records.py              database tables
  route.py, bus.py, user.py   objects used while the app runs
  seed_data.py, route_paths.py  built-in KU routes and buses for a new database

templates/              HTML pages (Jinja)
static/                 CSS, JavaScript, images
  vendor/                 Leaflet map library and Inter font, served locally
deploy/                 server setup, update, backup, nginx and systemd files
tests/                  automated tests (pytest)
```

### Where data lives

- **Saved in the database** (`instance/busplus.db`, SQLite):
  - routes
  - buses
  - drivers (PINs are stored only as hashes)
  - which students and teachers have signed in
- **Kept in memory only**: live GPS positions, speeds and trails. These come back as soon as drivers send their next position.
- Because of the in-memory data, the app runs as **one** server process. gevent lets that one process serve hundreds of open maps.

### Libraries used

| Library | Used for |
|---|---|
| Flask | Web framework |
| Flask-SQLAlchemy and SQLAlchemy | Database |
| Flask-WTF | CSRF protection |
| Flask-Limiter | Login rate limits |
| Flask-Talisman | Security headers, HTTPS and HSTS |
| Werkzeug | PIN hashing |
| python-dotenv | Loading `.env` settings |
| requests | Calls to the road router |
| gunicorn and gevent | Production server |
| Leaflet | Maps in the browser |
| pytest and ruff | Tests and code checks |

Security details are in [SECURITY.md](SECURITY.md).
