# 🚌 BusPlus - Khulna University Smart Bus Tracker

> A modern, real-time university bus tracking web application tailored for **Khulna University (KU)** students, faculty, and drivers. Built with Python (Flask) and Google Maps, designed with a clean, aesthetic whitish interface.

---

## ✨ Features

### 1. 🤍 Aesthetic Whitish Launching Page
- Clean, minimalist white design system with subtle shadows, crisp typography, and university branding.
- Two distinct portal choices:
  - **Driver Portal**: For bus drivers to log in and broadcast real-time GPS coordinates.
  - **Student / Passenger Portal**: For students to track live buses, view route stops, and receive 5-minute arrival notifications.
- Interactive showcase of official Khulna University bus routes and scheduled morning timings.

### 2. 👨‍✈️ Driver Portal & Live GPS Broadcaster
- **Live GPS Broadcasting**: Leverages HTML5 `navigator.geolocation.watchPosition` to broadcast real-time latitude, longitude, speed (km/h), and heading direction.
- **Route Movement Simulator**: Integrated simulator that smoothly advances the bus along official route waypoints for testing indoors or on desktop.
- **Driver Telemetry Console**: Live speed gauge, compass heading, next stop prediction, and stop completion checklist.
- **Manual Stop Jumper**: Allows drivers to jump coordinates directly to any designated stop.

### 3. 🎓 Student & Passenger Live Tracker
- **Google Maps Integration**: Live bus positions with custom directional markers, color-coded route polylines, and clickable stop milestones.
- **"Turn on GPS / Locate Me"**: Marks the student's live location on the map with a blue radar pin and calculates real-time distance to the approaching bus.
- **Pre-Configured Khulna University Routes**:
  - **Route 1 (Malabotha - Rupsha - KU Line)**: *Malabotha Bazar (08:35 AM)* ➔ *Rupsha Bridge* ➔ *Labanchara* ➔ *Rupsha Mor* ➔ *Royal Mor* ➔ *Moylapota* ➔ *Sonadanga* ➔ *Gollamari* ➔ *Zero Point* ➔ *Khulna University Main Gate (09:30 AM)*.
  - **Route 2 (Phultala - Daulatpur - Shibbari - KU Line)**: *Phultala (08:15 AM)* ➔ *Shiromoni* ➔ *Daulatpur* ➔ *Khalishpur* ➔ *Boyra* ➔ *Shibbari* ➔ *Gollamari* ➔ *Khulna University*.
  - **Route 3 (Dumuria - Zero Point - KU Line)**: *Dumuria (08:40 AM)* ➔ *Gutudia* ➔ *Zero Point* ➔ *Khulna University*.
- **🔔 5-Minute Proximity Arrival Notification**:
  - Automatically calculates ETA to the student's boarding stop (e.g., Malabotha Bazar).
  - When the bus is **5 minutes away** (or user-customized threshold), the system triggers:
    1. **Animated Golden Warning Card**: Displays countdown minutes and exact arrival clock time.
    2. **Synthesized Audio Chime**: Melodic two-tone alert chime built with Web Audio API (no external MP3 asset dependency).
    3. **Native Desktop Notification**: Prompts browser push alert banner.
    4. **In-Page Toast Banner**: Real-time pop-up notification.

### 4. 🗺️ Google Maps + Zero-Downtime Fallback
- Supports Google Maps JavaScript API with custom light styling.
- Includes a **Maps Key** modal in the navigation bar to enter or update your Google Maps API key directly from the UI.
- Automatically falls back to an interactive OpenStreetMap/Leaflet vector map if no Google Maps API key is configured, guaranteeing zero broken screens.

---

## 📁 Project Architecture

The codebase follows a clean, modular Model-Service-Controller (MSC) architectural pattern with meaningful naming:

```text
BusPlus/
├── app.py                         # Application factory & entrypoint
├── config.py                      # Application settings, university coordinates & constants
├── requirements.txt               # Python package dependencies
├── models/                        # Domain entities & data structures
│   ├── __init__.py
│   ├── bus.py                     # Bus model, telemetry, and default KU fleet
│   ├── route.py                   # BusRoute, BusStop, waypoints & KU predefined routes
│   └── user.py                    # DriverUser, StudentUser, and demo credentials
├── services/                      # Business logic & algorithms
│   ├── __init__.py
│   ├── eta_service.py             # Haversine distance, bearing & ETA calculations
│   ├── tracking_service.py        # Thread-safe telemetry store & route simulation engine
│   └── notification_service.py    # 5-minute proximity alerts & notification payloads
├── controllers/                   # HTTP & API endpoints
│   ├── __init__.py
│   ├── auth_controller.py         # Driver & student login/session handlers
│   ├── bus_controller.py          # Bus telemetry & driver GPS broadcast endpoints
│   ├── route_controller.py        # Route query & ETA evaluation endpoints
│   └── view_controller.py         # Frontend HTML page renderers
├── static/                        # Static UI assets
│   ├── css/
│   │   ├── common.css             # Whitish theme variables, badges, buttons & modals
│   │   ├── landing.css            # Launching page layout and portal selection cards
│   │   ├── driver.css             # Driver dashboard & telemetry console styles
│   │   └── student.css            # Student map, 5-min alert card & floating filters
│   └── js/
│       ├── google_maps_helper.js  # Google Maps SDK loader, custom markers & fallback map
│       ├── driver_tracker.js      # Driver HTML5 GPS streaming & simulation controller
│       └── student_tracker.js     # Student live map, stop ETA & 5-minute audio chime
├── templates/                     # Jinja2 HTML templates
│   ├── base.html                  # Whitish base shell with header, key modal & toast
│   ├── landing.html               # Main launching page (Driver vs Student options)
│   ├── driver_login.html          # Driver authentication & bus assignment
│   ├── driver_dashboard.html      # Driver GPS broadcaster & telemetry view
│   ├── student_login.html         # Student stop preference & access configuration
│   └── student_dashboard.html     # Live Google Map tracking & 5-minute arrival alerts
└── tests/
    └── test_busplus.py            # Unit and integration test suite
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10+ (Tested and verified on Python 3.15).

### 2. Installation
Clone or navigate to the directory:
```bash
cd d:\myProjects\BusPlus
```

Install dependencies:
```bash
python -m pip install -r requirements.txt
```

### 3. Run the Application
```bash
python app.py
```

The application will start on:
```text
🌐 http://localhost:5000
```

### 4. Running the Automated Tests
```bash
python -m unittest tests/test_busplus.py
```

---

## 🔐 Backend (admin only)

Open `http://localhost:5000/backend`. Only the admin can sign in here; drivers and students can't.

- **Username:** `admin` (change with the `BUSPLUS_ADMIN_USERNAME` environment variable)
- **Password:** set `BUSPLUS_ADMIN_PASSWORD`, or leave it unset and BusPlus creates one the first time it runs,
  saves it in `instance/admin_password.txt` and prints it in the console when the app starts.

Sections:
- **Drivers** – name, phone, login PIN (4–8 digits) and the driver's bus. The driver's route is the bus's route.
- **Routes** – add, edit or remove routes. Click the map to place stops, drag pins to move them. Every route ends at **Hadi Chattar** (set in `config.py` → `FINAL_DESTINATION`).
- **Buses** – add, edit or remove buses and pick each bus's **route for today** right in the table. The bus's driver gets a "Changed today" notification. **Test drive** moves a bus along its route for testing.
- **Students** – who has used the student app.

## 👨‍✈️ Driver app

1. Driver opens `/driver/login`, picks their name, their route and enters their PIN (as set by the admin).
2. GPS turns on by itself and the bus appears live for students, leaving a red trail along the road it has driven.
3. The screen shows only the map and the bus icon. Tapping the icon shows the driver ID, **Today's duty** (bus + route), and two views: **Your bus** and **All buses**.
4. **Log out** ends the trip (the bus goes offline) and frees the account.

> Phones only share GPS with sites opened over **HTTPS** (or `localhost` on the same computer). To test on a phone over Wi-Fi, serve BusPlus over HTTPS.

> BusPlus keeps everything in memory: routes, buses and drivers added in the backend are reset when the app restarts.

---

## 🎯 Verification & Demo Workflow

### Scenario: Malabotha Student & Driver Live Tracking
1. **Open Launching Page**:
   - Go to `http://localhost:5000`.
   - Observe the clean, whitish aesthetic launching page with the two prominent portals (**Driver Portal** and **Student Portal**).
2. **Open Driver Console**:
   - Click **Driver Portal** (or visit `/driver/login`).
   - Click **⚡ Quick Login as Driver 1 (Malabotha Line)**.
   - On the Driver Console, click **▶ Start Route Simulation** (or **Turn ON GPS & Broadcast** if on a mobile device).
   - The bus begins driving along the real Khulna road from Malabotha Bazar past Rupsha Bridge towards Khulna University!
3. **Open Student Live Tracker**:
   - In a new browser window or tab, open `http://localhost:5000/student/dashboard`.
   - Note the **Target Stop: Malabotha Bazar**.
   - Watch the bus moving in real-time along Route 1.
   - Click **📍 Turn on GPS / Locate Me** to view your location pin relative to the bus.
   - Notice the ETA countdown: As the bus enters the 5-minute proximity window, the banner turns into a golden pulsing alert:
     > 🔔 **5-MIN PROXIMITY ALERT**: KU Bus #01 Approaching Malabotha Bazar (~4.5 min away)!
   - Click **🔊 Test Chime** to hear the arrival bell synthesized by the Web Audio API!

---

## 🔌 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Whitish launching page |
| `GET` | `/driver/dashboard` | Driver GPS broadcast console |
| `GET` | `/student/dashboard` | Student live Google Maps tracker |
| `GET` | `/api/buses` | Get real-time status of all KU buses |
| `GET` | `/api/buses/<bus_id>` | Get specific bus telemetry |
| `POST` | `/api/driver/location` | Post GPS coordinates from driver device |
| `POST` | `/api/driver/simulate/toggle` | Toggle route drive simulation |
| `GET` | `/api/routes` | Get all pre-configured KU bus routes & stops |
| `GET` | `/api/notification/check` | Check 5-minute arrival alert for a stop |
| `POST` | `/api/config/maps-key` | Dynamically update Google Maps API key |
