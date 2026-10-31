/*
 * BusPlus driver page: full-screen map, GPS on automatically, one bus icon with a menu.
 *   - "Your bus": only this driver's bus (and its route + trail)
 *   - "All buses": every route and every live bus (with their trails)
 *   - Today's duty: which bus to drive on which route (set daily by the admin)
 *   - Online / Offline switch: start or stop sharing the bus's location
 *
 * Needs google_maps_helper.js (window.googleMapsHelper) loaded first.
 * Words: content/words/driver_map.py (the DT look-up below).
 */

/** Words of this page from content/words/driver_map.py. */
const DT = words("driver_map");

/** The driver page: map, GPS sending, menu, duty notification and session handling. */
class DriverApp {
    constructor() {
        const data = window.DRIVER_DATA || {};
        this.driver = data.driver || {};
        this.bus = data.bus || {};
        this.routes = data.routes || [];
        this.allBuses = [];

        this.view = this.readSetting("busplus_driver_view", "mine"); // "mine" | "all"
        this.online = this.readSetting("busplus_driver_online", "1") === "1";   // driver's Online/Offline switch
        this.pendingFix = null;      // newest GPS fix waiting while the previous one is still being sent
        this.pendingTimer = null;
        this.streamLive = false;
        this.follow = true;          // keep the own bus in view until the driver pans the map
        this.watchId = null;
        this.lastSent = { t: 0, lat: null, lng: null };
        this.sending = false;
        this.wakeLock = null;
        this.pollTimer = null;
        this.dutyTimer = null;
        this.duty = null;
        this.firstFit = true;
        this.lastShownRoutes = null;

        this.el = {
            icon: document.getElementById("drv-icon"),
            menu: document.getElementById("drv-menu"),
            backdrop: document.getElementById("drv-backdrop"),
            gpsDot: document.getElementById("drv-gps-dot"),
            unseenDot: document.getElementById("drv-unseen-dot"),
            gpsState: document.getElementById("drv-gps-state"),
            gpsRetry: document.getElementById("drv-gps-retry"),
            onlineSwitch: document.getElementById("drv-online-switch"),
            onlineTitle: document.getElementById("drv-online-title"),
            banner: document.getElementById("drv-banner"),
            logout: document.getElementById("drv-logout"),
            duty: document.getElementById("drv-duty"),
            dutyBadge: document.getElementById("drv-duty-badge"),
            dutyChanged: document.getElementById("drv-duty-changed"),
            dutyDate: document.getElementById("drv-duty-date"),
            dutyBus: document.getElementById("drv-duty-bus"),
            dutyBusDot: document.getElementById("drv-duty-bus-dot"),
            dutyPlate: document.getElementById("drv-duty-plate"),
            dutyRoute: document.getElementById("drv-duty-route"),
            dutyRouteSwatch: document.getElementById("drv-duty-route-swatch"),
            dutyStops: document.getElementById("drv-duty-stops"),
        };
    }

    /** localStorage that never throws (private mode just means nothing is remembered). */
    readSetting(key, fallback) {
        try { return localStorage.getItem(key) || fallback; } catch (e) { return fallback; }
    }

    /** Saves a setting on this phone (ignored if storage is blocked). */
    writeSetting(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
    }

    /** Starts the page: map, menu, live feed, GPS and the duty card. */
    init() {
        const helper = window.googleMapsHelper;
        // Driver map: nothing but the map and the bus icon (no layer buttons, no corner label)
        helper.initMap("driver-map", {
            center: {
                lat: this.bus.current_latitude || 22.8021,
                lng: this.bus.current_longitude || 89.5340
            },
            zoom: (window.APP_CONFIG?.zoom || 13) + 1,   // a little closer than the rider map
            layerSwitcher: false,
            attribution: false
        });

        helper.drawRoutes(this.routes);

        // Panning by hand stops "follow my bus" until "Your bus" is chosen again
        helper.leafletMap?.on("dragstart", () => { this.follow = false; });

        this.bindMenu();
        this.applyView(this.view, { fit: true });

        this.renderOnline();
        if (this.online) this.startGps();
        else this.goOffline({ quiet: true });
        this.loadDuty();
        this.refreshBuses();
        this.startLiveStream();
        // Fallback only: while the live stream is connected, updates arrive instantly
        this.pollTimer = setInterval(() => { if (!this.streamLive) this.refreshBuses(); }, window.APP_CONFIG?.refreshMs || 3000);
        this.dutyTimer = setInterval(() => this.loadDuty(), 60000);

        document.addEventListener("visibilitychange", () => {
            if (document.visibilityState === "visible") this.requestWakeLock();
        });
    }

    // ------------------------------------------------------------------
    // Menu
    // ------------------------------------------------------------------
    /** Wires up the logo button, menu buttons, online switch and log out. */
    bindMenu() {
        this.el.icon.addEventListener("click", () => this.toggleMenu());
        this.el.backdrop.addEventListener("click", () => this.closeMenu());
        // "Bus schedule": the timetable pop-up, opened on this driver's route (all buses shown)
        document.getElementById("drv-schedule-btn")?.addEventListener("click", () => {
            this.closeMenu();
            window.BusSchedule?.open({ routeId: this.bus.assigned_route_id });
        });
        document.addEventListener("keydown", (e) => { if (e.key === "Escape") this.closeMenu(); });

        document.querySelectorAll(".drv-view-btn").forEach(btn => {
            btn.addEventListener("click", () => {
                this.applyView(btn.dataset.view, { fit: true });
                this.closeMenu();
            });
        });

        this.el.gpsRetry.addEventListener("click", () => this.startGps());
        this.el.onlineSwitch.addEventListener("click", () => this.setOnline(!this.online));
        this.el.logout.addEventListener("click", () => this.logout());
    }

    /** Opens or closes the menu under the logo. */
    toggleMenu() {
        if (this.el.menu.classList.contains("open")) this.closeMenu();
        else this.openMenu();
    }

    /** Opens the menu (and marks a new duty as seen). */
    openMenu() {
        this.el.menu.classList.add("open");
        this.el.menu.setAttribute("aria-hidden", "false");
        this.el.backdrop.classList.add("open");
        this.el.icon.classList.add("menu-open");
        this.el.icon.setAttribute("aria-expanded", "true");
        this.markDutySeen();
    }

    /** Closes the menu. */
    closeMenu() {
        this.el.menu.classList.remove("open");
        this.el.menu.setAttribute("aria-hidden", "true");
        this.el.backdrop.classList.remove("open");
        this.el.icon.classList.remove("menu-open");
        this.el.icon.setAttribute("aria-expanded", "false");
    }

    // ------------------------------------------------------------------
    // Your bus / All buses
    // ------------------------------------------------------------------
    /** Switches between "Your bus" and "All buses" and redraws the map. */
    applyView(view, { fit = false } = {}) {
        this.view = view === "all" ? "all" : "mine";
        this.writeSetting("busplus_driver_view", this.view);
        if (this.view === "mine") this.follow = true;

        document.querySelectorAll(".drv-view-btn").forEach(btn => {
            const on = btn.dataset.view === this.view;
            btn.classList.toggle("active", on);
            btn.setAttribute("aria-checked", on ? "true" : "false");
        });

        const helper = window.googleMapsHelper;
        this.lastShownRoutes = null;
        this.drawBuses();

        if (!fit) return;
        if (this.view === "mine") {
            if (this.bus.is_active && this.bus.current_latitude) {
                helper.fitToPoints([[this.bus.current_latitude, this.bus.current_longitude]], 40);
            } else {
                helper.fitToPoints(helper.getRoutePoints(this.bus.assigned_route_id ? [this.bus.assigned_route_id] : null), 40);
            }
        } else {
            helper.fitToPoints(helper.getRoutePoints(null), 40);
        }
    }

    /** Route lines: only for routes with a bus online (your own route while you are online). */
    shownRouteIds() {
        const mine = this.bus.assigned_route_id;
        if (this.view === "mine") return this.online && mine ? [mine] : [];
        const live = new Set(this.allBuses.filter(b => b.is_active).map(b => b.assigned_route_id));
        if (this.online && mine) live.add(mine);
        return [...live];
    }

    /** Puts the buses for the current view, their trails and route lines on the map. */
    drawBuses() {
        const helper = window.googleMapsHelper;
        const myId = this.bus.bus_id;
        let list = this.allBuses.filter(b => b.is_active);
        if (this.view === "mine") list = list.filter(b => b.bus_id === myId);

        const shown = this.shownRouteIds().sort().join(",");
        if (shown !== this.lastShownRoutes) {
            this.lastShownRoutes = shown;
            helper.showRoutes(shown ? shown.split(",") : []);
        }

        helper.updateTrails(list);
        helper.updateActiveBuses(list);

        // Make the driver's own bus stand out
        helper.busMarkers[myId]?.getElement()?.querySelector(".gmap-bus-container")?.classList.add("is-mine");
    }

    /** Live bus feed pushed by the server (the 3-second poll only runs while it is down). */
    startLiveStream() {
        if (!window.EventSource) return;
        const es = new EventSource("/api/buses/stream");
        es.onopen = () => { this.streamLive = true; };
        es.onerror = () => { this.streamLive = false; };
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (Array.isArray(data.buses)) { this.streamLive = true; this.handleBuses(data.buses); }
            } catch (err) { /* ignore a bad message */ }
        };
    }

    /** Fetches the bus list once (used while the live feed is down). */
    async refreshBuses() {
        try {
            const resp = await fetch("/api/buses");
            const data = await resp.json();
            if (data.success) this.handleBuses(data.buses || []);
        } catch (err) {
            // network blip: try again on the next tick
        }
    }

    /** New bus list from the stream or the poll: redraw, and re-fit if the admin moved this bus to another route. */
    handleBuses(buses) {
        try {
            this.allBuses = buses;
            const mine = this.allBuses.find(b => b.bus_id === this.bus.bus_id);
            if (mine) {
                const routeChanged = mine.assigned_route_id !== this.bus.assigned_route_id;
                this.bus = mine;
                if (routeChanged) {
                    this.applyView(this.view, { fit: this.view === "mine" });
                    this.loadDuty();
                    return;
                }
            }
            this.drawBuses();
            if (this.view === "mine" && this.follow && this.bus.is_active && this.bus.current_latitude && this.firstFit) {
                window.googleMapsHelper.fitToPoints([[this.bus.current_latitude, this.bus.current_longitude]], 40);
                this.firstFit = false;
            }
        } catch (err) {
            // keep the last good picture
        }
    }

    // ------------------------------------------------------------------
    // GPS (turns on by itself)
    // ------------------------------------------------------------------
    /** Updates the GPS dot on the logo and the GPS line in the menu. */
    setGpsState(state, text) {
        this.el.gpsDot.className = `drv-gps-dot ${state}`;
        this.el.gpsState.className = `drv-gps-state ${state}`;
        this.el.gpsState.textContent = text;
        this.el.gpsRetry.hidden = state !== "off";
    }

    /** Shows (or hides, with empty text) the red message at the bottom. */
    showBanner(text) {
        this.el.banner.textContent = text;
        this.el.banner.hidden = !text;
    }

    /** Turns the trip on and starts watching the phone's GPS. */
    async startGps() {
        if (!this.online) return;
        if (!window.isSecureContext) {
            this.setGpsState("off", DT("GPS needs HTTPS"));
            this.showBanner(DT("GPS can't start: phones only share location with sites opened over HTTPS (or on this computer as localhost)."));
            return;
        }
        if (!navigator.geolocation) {
            this.setGpsState("off", DT("No GPS on this device"));
            this.showBanner(DT("This device or browser can't share its location."));
            return;
        }

        this.setGpsState("", DT("Starting GPS…"));
        this.showBanner("");

        const started = await this.post("/api/driver/trip/start", {});
        if (!started) return;

        if (this.watchId !== null) navigator.geolocation.clearWatch(this.watchId);
        this.watchId = navigator.geolocation.watchPosition(
            (pos) => this.onPosition(pos),
            (err) => this.onGpsError(err),
            { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 }   // always a fresh fix
        );
        this.requestWakeLock();
    }

    /** New GPS fix from the phone: sends it to the server, at most about once a second. */
    onPosition(pos) {
        if (!this.online) return;
        const { latitude, longitude, speed, heading } = pos.coords;
        this.setGpsState("on", DT("GPS on · sharing location"));
        this.showBanner("");

        const fix = {
            latitude,
            longitude,
            // Many phones don't report speed: send null and the server works it out from the movement
            speed_kmh: typeof speed === "number" && !Number.isNaN(speed) ? speed * 3.6 : null,
            // Only send a heading the phone actually knows; otherwise the server works it out
            heading_deg: typeof heading === "number" && !Number.isNaN(heading) ? heading : null
        };

        // Send a fix at most every GPS_SEND_EVERY_SECONDS, sooner after GPS_SEND_AFTER_METERS
        // (both in content/rules.py). If one is still on its way, keep only the newest and send it right after.
        if (this.sending) { this.pendingFix = fix; return; }
        const everyMs = window.APP_CONFIG?.gpsSendEveryMs || 1000;
        const afterMeters = window.APP_CONFIG?.gpsSendAfterMeters || 8;
        const now = Date.now();
        const moved = this.lastSent.lat === null ? Infinity
            : Math.hypot(latitude - this.lastSent.lat, (longitude - this.lastSent.lng) * Math.cos(latitude * Math.PI / 180)) * 111000;
        if (now - this.lastSent.t < everyMs && moved < afterMeters) {
            this.pendingFix = fix;
            clearTimeout(this.pendingTimer);
            this.pendingTimer = setTimeout(() => this.flushPending(), everyMs - (now - this.lastSent.t));
            return;
        }
        this.sendFix(fix);
    }

    /** Sends one GPS position to the server. */
    sendFix(fix) {
        this.lastSent = { t: Date.now(), lat: fix.latitude, lng: fix.longitude };
        this.sending = true;
        this.pendingFix = null;
        this.post("/api/driver/location", fix).then(data => {
            if (data && data.bus) {
                this.bus = { ...this.bus, ...data.bus };
                const idx = this.allBuses.findIndex(b => b.bus_id === data.bus.bus_id);
                if (idx >= 0) this.allBuses[idx] = { ...this.allBuses[idx], ...data.bus };
                else this.allBuses.push(data.bus);
                this.drawBuses();
                this.followMyBus();
            }
            this.flushPending();
        });
    }

    /** Sends the newest waiting GPS position once the last one is done. */
    flushPending() {
        if (this.pendingFix && !this.sending && this.online) this.sendFix(this.pendingFix);
    }

    /** Keeps the map centred on this driver's bus while following. */
    followMyBus() {
        if (this.view === "mine" && this.follow && this.bus.is_active && this.bus.current_latitude) {
            window.googleMapsHelper.leafletMap?.panTo([this.bus.current_latitude, this.bus.current_longitude], { animate: true, duration: 0.8 });
        }
    }

    // ------------------------------------------------------------------
    // Online / Offline
    // ------------------------------------------------------------------
    /** Shows the Online / Offline switch and title. */
    renderOnline() {
        const on = this.online;
        this.el.onlineSwitch.classList.toggle("on", on);
        this.el.onlineSwitch.setAttribute("aria-checked", on ? "true" : "false");
        this.el.onlineSwitch.setAttribute("aria-label", on ? DT("Online. Tap to go offline") : DT("Offline. Tap to go online"));
        this.el.onlineTitle.textContent = on ? DT("You are online") : DT("You are offline");
        this.el.onlineTitle.classList.toggle("off", !on);
    }

    /** The driver flipped the switch: start or stop sharing location. */
    setOnline(on) {
        this.online = !!on;
        this.writeSetting("busplus_driver_online", this.online ? "1" : "0");
        this.renderOnline();
        if (this.online) this.startGps();
        else this.goOffline();
        this.lastShownRoutes = null;
        this.drawBuses();
    }

    /** Stops sharing location; the bus disappears from students' maps. */
    async goOffline({ quiet = false } = {}) {
        if (this.watchId !== null) navigator.geolocation.clearWatch(this.watchId);
        this.watchId = null;
        this.pendingFix = null;
        clearTimeout(this.pendingTimer);
        this.showBanner("");
        this.setGpsState("off-duty", DT("Not sharing location"));
        // Let a location update that's already on its way land first, so it can't switch the bus back on
        for (let i = 0; i < 30 && this.sending; i++) await new Promise(r => setTimeout(r, 100));
        if (!quiet || this.bus.is_active) await this.post("/api/driver/trip/stop", {});
        try { await this.wakeLock?.release(); } catch (e) {}
    }

    /** Explains why GPS stopped (blocked, no signal, unavailable). */
    onGpsError(err) {
        if (err.code === 1) {
            this.setGpsState("off", DT("Location blocked"));
            this.showBanner(DT("Location is blocked for this site. Allow location in your browser settings, then open the menu and tap Try again."));
            if (this.watchId !== null) navigator.geolocation.clearWatch(this.watchId);
            this.watchId = null;
        } else if (err.code === 3) {
            this.setGpsState("", DT("Waiting for GPS signal…"));
        } else {
            this.setGpsState("off", DT("GPS unavailable"));
            this.showBanner(DT("Can't get a GPS position right now. Move to an open area, then open the menu and tap Try again."));
        }
    }

    /** Keeps the screen awake while driving (where the browser allows it). */
    async requestWakeLock() {
        // Keeps the screen (and GPS) awake while driving, where the browser supports it
        try {
            if ("wakeLock" in navigator && document.visibilityState === "visible" && !this.wakeLock) {
                this.wakeLock = await navigator.wakeLock.request("screen");
                this.wakeLock.addEventListener("release", () => { this.wakeLock = null; });
            }
        } catch (e) { /* not allowed right now */ }
    }

    // ------------------------------------------------------------------
    // Today's duty (notification)
    // ------------------------------------------------------------------
    /** Fetches today's duty (bus, route, start time) from the server. */
    async loadDuty() {
        try {
            const resp = await fetch("/api/driver/assignment");
            if (resp.status === 401) return this.sessionLost();
            const data = await resp.json();
            if (!data.success) return;
            this.duty = data.assignment;
            this.renderDuty();
        } catch (e) { /* try again later */ }
    }

    /** Fills the duty card in the menu. */
    renderDuty() {
        const d = this.duty;
        if (!d) return;
        this.el.dutyDate.textContent = d.date_label || "";

        // Bus: its name big, then "Bus no. … · Plate …"
        this.el.dutyBus.textContent = d.bus_number ? (d.bus_name || d.bus_number) : DT("No bus assigned yet");
        const busFacts = [];
        if (d.bus_number) busFacts.push(/bus/i.test(d.bus_number) ? d.bus_number : DT("Bus no. {number}", { number: d.bus_number }));
        if (d.license_plate) busFacts.push(DT("Plate {plate}", { plate: d.license_plate }));
        this.el.dutyPlate.textContent = d.bus_number ? busFacts.join(" · ") : DT("Ask the admin to assign you a bus.");
        this.el.dutyBusDot.style.setProperty("--duty-color", d.bus_color || "#94a3b8");

        // Route: its name big, then where it goes
        this.el.dutyRoute.textContent = d.route_name || DT("No route assigned yet");
        this.el.dutyRouteSwatch.style.setProperty("--duty-color", d.route_color || "#94a3b8");
        if (!d.route_name) {
            this.el.dutyStops.textContent = "";
        } else if (d.from_stop) {
            this.el.dutyStops.textContent = d.from_time
                ? DT("From {from} at {time} to {to}", { from: d.from_stop, time: d.from_time, to: d.to_stop })
                : DT("From {from} to {to}", { from: d.from_stop, to: d.to_stop });
        } else {
            this.el.dutyStops.textContent = DT("Ends at {stop}", { stop: d.to_stop });
        }

        const changed = !!d.changed_today;
        this.el.dutyBadge.hidden = !changed;
        if (this.el.dutyChanged) this.el.dutyChanged.hidden = !changed;
        this.el.duty.classList.toggle("is-new", !!d.unseen);
        this.el.unseenDot.hidden = !d.unseen;
        if (d.unseen && this.el.menu.classList.contains("open")) this.markDutySeen();
    }

    /** Tells the server the driver has seen a changed duty. */
    async markDutySeen() {
        if (!this.duty || !this.duty.unseen) return;
        this.el.unseenDot.hidden = true;
        await this.post("/api/driver/assignment/seen", {});
        this.duty.unseen = false;
    }

    // ------------------------------------------------------------------
    // Session
    // ------------------------------------------------------------------
    /** POST JSON; a lost session (401/409) sends the driver back to the login page. Returns the reply or null. */
    async post(url, body) {
        try {
            const resp = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body || {})
            });
            if (resp.status === 401 || resp.status === 409) {
                this.sessionLost();
                return null;
            }
            const data = await resp.json().catch(() => ({}));
            if (resp.status === 404 && data.message) {
                this.setGpsState("off", DT("No bus assigned"));
                this.showBanner(data.message);
                return null;
            }
            return data;
        } catch (e) {
            return null;   // offline for a moment; the next GPS fix will retry
        } finally {
            if (url === "/api/driver/location") this.sending = false;
        }
    }

    /** Another phone took over or the sign-in ended: back to the login page. */
    sessionLost() {
        if (this.watchId !== null) navigator.geolocation.clearWatch(this.watchId);
        window.location.href = "/driver/login";
    }

    /** Stops GPS, signs out and goes to the start page. */
    async logout() {
        if (this.watchId !== null) navigator.geolocation.clearWatch(this.watchId);
        this.watchId = null;
        clearInterval(this.pollTimer);
        clearInterval(this.dutyTimer);
        try { await this.wakeLock?.release(); } catch (e) {}
        try {
            await fetch("/api/auth/logout", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: "{}"
            });
        } catch (e) {}
        window.location.href = "/";
    }
}

document.addEventListener("DOMContentLoaded", () => {
    window.driverApp = new DriverApp();
    window.driverApp.init();
});
