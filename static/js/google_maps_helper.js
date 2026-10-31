/*
 * BusPlus map helper, used by the rider map (student/teacher) and the driver map.
 *
 * Draws a Leaflet map with Google Maps tiles, plus everything BusPlus puts on it:
 * route lines, live bus markers (they glide between GPS fixes), the red trail each
 * bus has driven, the rider's GPS position and the Home dot.
 * Page scripts use the single shared instance: window.googleMapsHelper.
 * Words: content/words/map.py (the MT look-up below). Layers, credit, trail colour: content/ folder via APP_CONFIG.
 */

/** Words shown on every map, from content/words/map.py. */
const MT = words("map");

/** Makes text safe to put inside HTML (names, messages, anything from the server). */
function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/** Bus icon (front view of a bus) drawn with the current text colour. */
const BUS_SVG_PATHS = '<rect x="5" y="3" width="14" height="14.5" rx="3"/><path d="M5 10.5h14"/><path d="M9.5 6.5h5"/><path d="M7.5 17.5v2.5M16.5 17.5v2.5"/>';

/** Google tile URL. lyrs: m = map, y = satellite with labels, "m,traffic" = map with live traffic. */
const googleTileUrl = (lyrs, extra = "") => `https://mt{s}.google.com/vt/lyrs=${lyrs}${extra}&x={x}&y={y}&z={z}`;

/** Map style for the plain map: hides shops, cafes, hotels, hospitals and POI icons, keeps every road and street name. */
const CLEAN_MAP_STYLE = encodeURIComponent(
    "s.t:33|p.v:off," +   // shops, cafes, restaurants, hotels
    "s.t:35|p.v:off," +   // hospitals, clinics, pharmacies
    "s.e:l.i|p.v:off"     // all POI icons
);

const M_PER_DEG = 111320;                  // metres per degree of latitude
const EXTRAPOLATE_MAX_S = 2.0;             // keep a moving bus going this long after its last GPS fix
const CORRECT_PER_S = 1.2;                 // how fast a position error is worked off (share per second)
const STALE_S = 30;                        // no GPS for this long: the bus is shown greyed out

/**
 * A route's road line that we can measure along (same maths as services/route_geometry.py),
 * so a bus between two GPS fixes moves ALONG the road, around corners, not straight across.
 */
class RoadLine {
    constructor(points) {                  // [[lat, lng], ...]
        this.pts = points;
        this.cum = [0];
        for (let i = 1; i < points.length; i++) {
            this.cum.push(this.cum[i - 1] + metresBetween(points[i - 1], points[i]));
        }
        this.length = this.cum[this.cum.length - 1];
    }

    /** {lat, lng, bearing} at `m` metres from the start of the route. */
    pointAt(m) {
        const p = Math.max(0, Math.min(this.length, m));
        let lo = 0, hi = this.cum.length - 1;
        while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (this.cum[mid] <= p) lo = mid; else hi = mid; }
        const a = this.pts[lo], b = this.pts[hi] || a;
        const seg = this.cum[hi] - this.cum[lo];
        const t = seg > 0 ? (p - this.cum[lo]) / seg : 0;
        return { lat: a[0] + (b[0] - a[0]) * t, lng: a[1] + (b[1] - a[1]) * t, bearing: bearingBetween(a, b) };
    }
}

function metresBetween(a, b) {
    const kx = Math.cos((a[0] + b[0]) / 2 * Math.PI / 180);
    return Math.hypot((b[0] - a[0]) * M_PER_DEG, (b[1] - a[1]) * M_PER_DEG * kx);
}

function bearingBetween(a, b) {
    const kx = Math.cos((a[0] + b[0]) / 2 * Math.PI / 180);
    return (Math.atan2((b[1] - a[1]) * kx, b[0] - a[0]) * 180 / Math.PI + 360) % 360;
}

/** Shortest turn from angle a to angle b, in degrees (-180..180). */
const turnBetween = (a, b) => ((b - a + 540) % 360) - 180;

/**
 * The live bus feed for a map page. One EventSource connection: the server first sends every
 * bus ("snapshot"), then only what moved ("delta": new position + new trail points). This class
 * keeps the complete bus objects and calls onUpdate(buses) after every message.
 * If the live connection is down (or silent for too long) it falls back to asking every few seconds.
 */
class BusFeed {
    constructor({ audience = null, onUpdate = () => {}, pollMs = 3000 } = {}) {
        this.query = audience ? `?audience=${encodeURIComponent(audience)}` : "";
        this.onUpdate = onUpdate;
        this.pollMs = pollMs;
        this.buses = new Map();
        this.trailMax = 1500;
        this.live = false;
        this.lastMessageAt = 0;
    }

    /** Opens the live connection and starts the fallback timer. */
    start() {
        this.poll();
        this.connect();
        setInterval(() => {
            // The server sends at least a ping every 15 s: silence means a dead connection
            if (this.live && Date.now() - this.lastMessageAt > 40000) this.connect();
            if (!this.live) this.poll();
        }, this.pollMs);
        return this;
    }

    connect() {
        if (!window.EventSource) return;
        this.source?.close();
        this.source = new EventSource(`/api/buses/stream${this.query}`);
        this.source.onopen = () => { this.live = true; this.lastMessageAt = Date.now(); };
        this.source.onerror = () => { this.live = false; };
        this.source.onmessage = (e) => {
            this.live = true;
            this.lastMessageAt = Date.now();
            try { this.apply(JSON.parse(e.data)); } catch (err) { /* ignore a bad message */ }
        };
    }

    async poll() {
        try {
            const data = await (await fetch(`/api/buses${this.query}`)).json();
            if (data.success) this.apply({ type: "snapshot", now: data.now, buses: data.buses || [] });
        } catch (e) { /* offline for a moment */ }
    }

    /** Merges one message from the server into the bus list. */
    apply(data) {
        if (data.now) window.googleMapsHelper?.noteServerTime(data.now);
        if (data.trail_max) this.trailMax = data.trail_max;
        if (data.type === "ping") return;                       // keep-alive (every 15 s)
        if (data.type === "delta") {
            (data.buses || []).forEach(change => {
                const bus = this.buses.get(change.bus_id);
                if (!bus) return;                               // unknown bus: the next snapshot brings it
                const added = change.trail_add || [];
                delete change.trail_add;
                Object.assign(bus, change);
                if (added.length) {
                    bus.trail = (bus.trail || []).concat(added);
                    if (bus.trail.length > this.trailMax) bus.trail = bus.trail.slice(-this.trailMax);
                }
            });
        } else {
            this.buses = new Map((data.buses || []).map(b => [b.bus_id, b]));
        }
        this.onUpdate([...this.buses.values()], data.type);
    }

    /** Adds what the page learnt another way (the driver's own location reply) to a known bus. */
    merge(change) {
        const bus = this.buses.get(change?.bus_id);
        if (!bus) return;
        const { trail, ...rest } = change;
        Object.assign(bus, rest);
    }
}

/** Everything drawn on a map; one shared instance: window.googleMapsHelper. */
class GoogleMapsHelper {
    constructor() {
        const ku = window.APP_CONFIG?.universityLocation || {};
        this.defaultCenter = { lat: ku.latitude || 22.8010, lng: ku.longitude || 89.5345 };
        this.defaultZoom = window.APP_CONFIG?.zoom || 13;   // content/map_settings.py: MAP_START_ZOOM

        this.leafletMap = null;
        this.layers = {};          // "roadmap" | "satellite" | "traffic" -> tile layer
        this.busMarkers = {};      // bus_id -> marker
        this.polylines = {};       // route_id -> { glowLine, mainLine, points }
        this.trails = {};          // bus_id -> red line of where the bus has driven this trip
        this.trailTips = {};       // bus_id -> short red line from the last trail point to the moving marker
        this.trailDrawn = {};      // bus_id -> { first, count } of the trail points already drawn
        this.tracks = {};          // bus_id -> recent GPS samples and where the marker is drawn now
        this.roadLines = {};       // route_id -> RoadLine (for moving buses along the road)
        this.clockOffset = null;   // server clock minus this browser's clock (seconds)
        this.animating = false;
        this.onFrame = null;       // optional: called (bus_id, [lat, lng]) every frame (driver map: follow)
        this.studentMarker = null;
        this.studentAccuracyCircle = null;
        this.homeMarker = null;

        // Optional: called with a bus_id when a bus marker is tapped.
        // When set (rider map), tapping a bus selects it instead of opening a popup.
        this.onBusMarkerClick = null;
    }

    /**
     * Creates the map inside containerId.
     * options: center {lat, lng}, zoom, layerSwitcher (Map / Satellite / Traffic buttons),
     * attribution (small "Google Maps" label in the corner).
     */
    initMap(containerId, { center = this.defaultCenter, zoom = this.defaultZoom, layerSwitcher = true, attribution = true } = {}) {
        const container = document.getElementById(containerId);
        if (!container || !window.L) return null;

        this.leafletMap = L.map(container, {
            center: [center.lat, center.lng],
            zoom,
            zoomControl: false,
            attributionControl: false
        });

        // Map layers come from content/map_settings.py (MAP_LAYERS); these are the defaults.
        const layerList = window.APP_CONFIG?.layers?.length ? window.APP_CONFIG.layers : [
            { key: "roadmap", label: "Map", url: googleTileUrl("m"), clean: true },
            { key: "satellite", label: "Satellite", url: googleTileUrl("y") },
            { key: "traffic", label: "Traffic", url: googleTileUrl("m,traffic") }
        ];
        const tiles = (layer) => L.tileLayer(layer.clean ? `${layer.url}&apistyle=${CLEAN_MAP_STYLE}` : layer.url,
            { subdomains: ["0", "1", "2", "3"], maxZoom: 20 });
        this.layerList = layerList;
        this.layers = Object.fromEntries(layerList.map(layer => [layer.key, tiles(layer)]));
        this.defaultLayer = layerList[0].key;
        this.layers[this.defaultLayer].addTo(this.leafletMap);

        if (attribution) {
            const badge = L.control({ position: "bottomright" });
            badge.onAdd = () => {
                const div = L.DomUtil.create("div", "gmap-attrib-pill");
                div.textContent = window.APP_CONFIG?.credit || "";
                return div;
            };
            badge.addTo(this.leafletMap);
        }

        if (layerSwitcher) this.addLayerSwitcher(container);
        return this.leafletMap;
    }

    /** Adds the floating Map / Satellite / Traffic buttons. */
    addLayerSwitcher(container) {
        const icon = (paths) => `<svg class="gmap-layer-ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths}</svg>`;
        const ICONS = {
            roadmap: '<path d="M3 6.5l6-2.5 6 2.5 6-2.5v13.5l-6 2.5-6-2.5-6 2.5z"/><path d="M9 4v13.5M15 6.5V20"/>',
            satellite: '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12.5l9 5 9-5"/><path d="M3 16.5l9 5 9-5"/>',
            traffic: '<rect x="7.5" y="2.5" width="9" height="19" rx="3"/><circle cx="12" cy="7" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="17" r="1.6" fill="currentColor"/>'
        };
        const buttons = this.layerList.map(layer => [layer.key, layer.label, ICONS[layer.key] || ICONS.roadmap]);

        const switcher = document.createElement("div");
        switcher.className = "gmap-layer-selector";
        switcher.innerHTML = buttons.map(([layer, label, paths], i) =>
            `<button type="button" class="gmap-layer-btn${i === 0 ? " active" : ""}" data-layer="${escapeHtml(layer)}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${icon(paths)}</button>`
        ).join("");

        switcher.querySelectorAll(".gmap-layer-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                this.switchLayer(btn.dataset.layer);
                switcher.querySelectorAll(".gmap-layer-btn").forEach(b => b.classList.toggle("active", b === btn));
            });
        });
        container.appendChild(switcher);
    }

    /** Shows one tile layer ("roadmap", "satellite" or "traffic") and hides the others. */
    switchLayer(mode) {
        if (!this.leafletMap) return;
        Object.values(this.layers).forEach(layer => layer.remove());
        (this.layers[mode] || this.layers[this.defaultLayer]).addTo(this.leafletMap);
    }

    // ------------------------------------------------------------------
    // Buses
    // ------------------------------------------------------------------

    /** Shows exactly these buses (live ones only): adds/moves their markers, removes all others. */
    updateActiveBuses(activeBuses = []) {
        const keep = new Set(activeBuses.map(b => b.bus_id));
        Object.keys(this.busMarkers).forEach(id => {
            if (!keep.has(id)) this.removeBusMarker(id);
        });
        activeBuses.forEach(bus => this.updateBusMarker(bus));
    }

    /** Takes one bus marker off the map. */
    removeBusMarker(id) {
        this.busMarkers[id]?.remove();
        delete this.busMarkers[id];
        delete this.tracks[id];
    }

    /**
     * Adds or moves one bus marker: a circle in the bus's colour with a bus icon,
     * a heading arrow that turns with the bus, and a speed tag underneath.
     * A bus that is not live is taken off the map.
     */
    updateBusMarker(bus) {
        if (!bus || !this.leafletMap) return;
        const id = bus.bus_id;
        if (!bus.is_active) {
            this.removeBusMarker(id);
            return;
        }

        const latLng = [bus.current_latitude, bus.current_longitude];
        const heading = bus.heading_deg || 0;
        const speed = Math.round(bus.speed_kmh || 0);
        const color = bus.color_hex || "#0866FF";
        const marker = this.busMarkers[id];

        if (marker) {
            this.track(bus);
            const el = marker.getElement();
            if (el) {
                const box = el.querySelector(".gmap-bus-container");
                box?.style.setProperty("--bus-color", color);
                box?.classList.toggle("is-stale", this.isStale(bus));
                const speedTag = el.querySelector(".gmap-bus-speed-tag");
                const label = MT("{speed} km/h", { speed });
                if (speedTag && speedTag.textContent !== label) speedTag.textContent = label;
            }
            // Keep an open popup (driver map) in step with the live data
            if (marker.getPopup()?.isOpen()) marker.setPopupContent(this.busPopupHtml(bus, speed, heading));
            return;
        }

        const icon = L.divIcon({
            className: "gmap-bus-marker-wrap",
            html: `
                <div class="gmap-bus-container" style="--bus-color: ${escapeHtml(color)};" title="${escapeHtml(bus.bus_name || bus.bus_number)}">
                    <div class="gmap-bus-pulse-ring"></div>
                    <div class="gmap-bus-body">
                        <div class="gmap-bus-heading" style="transform: rotate(${heading}deg);">
                            <div class="gmap-bus-heading-arrow"></div>
                        </div>
                        <svg class="gmap-bus-svg" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${BUS_SVG_PATHS}</svg>
                    </div>
                    <div class="gmap-bus-speed-tag">${escapeHtml(MT("{speed} km/h", { speed }))}</div>
                </div>`,
            iconSize: [44, 44],
            iconAnchor: [22, 22]
        });

        const newMarker = L.marker(latLng, { icon, zIndexOffset: 1000 }).addTo(this.leafletMap);
        if (this.onBusMarkerClick) {
            newMarker.on("click", () => this.onBusMarkerClick(id));   // rider map: select the bus
        } else {
            newMarker.bindPopup(this.busPopupHtml(bus, speed, heading));
        }
        this.busMarkers[id] = newMarker;
        this.track(bus);
    }

    // ------------------------------------------------------------------
    // Smooth live movement
    // ------------------------------------------------------------------
    //
    // Every GPS sample carries the time it was measured (sample_t, server clock), the bus's
    // speed and how far along its route it is (progress_m). Each screen frame we work out
    // where the bus is NOW: its last sample, moved on along the road at its speed for the
    // time since (at most EXTRAPOLATE_MAX_S). The marker eases towards that point, so it
    // moves continuously at the real pace, follows curves, and corrects gently when the
    // next GPS fix arrives - instead of jumping or stopping and starting every second.

    /** Learns the server's clock from a live message ("now"), to compare with sample times. */
    noteServerTime(serverNow) {
        const offset = serverNow - Date.now() / 1000;          // the smallest network delay wins
        this.clockOffset = this.clockOffset === null ? offset : Math.max(offset, this.clockOffset - 0.05);
    }

    serverNow() {
        return Date.now() / 1000 + (this.clockOffset || 0);
    }

    isStale(bus) {
        return !!bus.last_update_ts && this.clockOffset !== null && this.serverNow() - bus.last_update_ts > STALE_S;
    }

    /** Adds a bus's latest live state as a sample for the animation. */
    track(bus) {
        const id = bus.bus_id;
        const sample = {
            t: bus.sample_t || this.serverNow(),
            lat: bus.current_latitude,
            lng: bus.current_longitude,
            p: typeof bus.progress_m === "number" ? bus.progress_m : null,
            route: bus.assigned_route_id,
            speed: this.isStale(bus) ? 0 : (bus.speed_kmh || 0) / 3.6,      // m/s
            heading: bus.heading_deg || 0
        };
        let tr = this.tracks[id];
        if (!tr) {
            tr = this.tracks[id] = { samples: [], lat: sample.lat, lng: sample.lng, heading: sample.heading };
        }
        const last = tr.samples[tr.samples.length - 1];
        if (last && sample.t <= last.t) {
            if (sample.t === last.t) Object.assign(last, sample);   // same fix again (e.g. stale flag changed)
        } else {
            tr.samples.push(sample);
            if (tr.samples.length > 3) tr.samples.shift();
        }
        this.startAnimation();
    }

    /** Where the bus should be right now: its last sample, carried on along the road at its speed. */
    targetOf(tr, now) {
        const a = tr.samples[tr.samples.length - 1];
        const b = tr.samples[tr.samples.length - 2];
        const dt = Math.max(0, Math.min(EXTRAPOLATE_MAX_S, now - a.t));
        if (a.speed < 0.5 || dt === 0) return { lat: a.lat, lng: a.lng, heading: a.heading };

        const road = a.p !== null ? this.roadLines[a.route] : null;
        if (road) {
            let dir = 1;
            if (b && b.p !== null && b.route === a.route && a.p !== b.p) dir = Math.sign(a.p - b.p);
            else if (Math.abs(turnBetween(road.pointAt(a.p).bearing, a.heading)) > 90) dir = -1;
            const at = road.pointAt(a.p + dir * a.speed * dt);
            return { lat: at.lat, lng: at.lng, heading: dir > 0 ? at.bearing : (at.bearing + 180) % 360 };
        }
        const d = a.speed * dt, h = a.heading * Math.PI / 180;
        return {
            lat: a.lat + d * Math.cos(h) / M_PER_DEG,
            lng: a.lng + d * Math.sin(h) / (M_PER_DEG * Math.cos(a.lat * Math.PI / 180)),
            heading: a.heading
        };
    }

    startAnimation() {
        if (this.animating) return;
        this.animating = true;
        let previous = performance.now();
        const frame = (nowMs) => {
            const ids = Object.keys(this.tracks);
            if (!ids.length || !this.leafletMap) { this.animating = false; return; }
            const dt = Math.min(0.5, (nowMs - previous) / 1000);
            previous = nowMs;
            const now = this.serverNow();
            ids.forEach(id => this.drawFrame(id, now, dt));
            requestAnimationFrame(frame);
        };
        requestAnimationFrame(frame);
    }

    /**
     * Moves one marker for this frame. The marker travels WITH the bus (the change of the
     * predicted position since the last frame) and works off any difference to the prediction
     * a little each second - so a new GPS fix bends the path gently instead of making the bus
     * jump, stop or race to catch up.
     */
    drawFrame(id, now, dt) {
        const tr = this.tracks[id], marker = this.busMarkers[id];
        if (!tr || !marker || !tr.samples.length) return;
        const target = this.targetOf(tr, now);
        const before = this.targetOf(tr, now - dt);
        const far = metresBetween([tr.lat, tr.lng], [target.lat, target.lng]) > 400;
        const share = far || document.hidden ? 1 : Math.min(1, CORRECT_PER_S * dt);   // big jumps: go straight there
        const moveLat = (target.lat - before.lat) * (1 - share) + (target.lat - tr.lat) * share;
        const moveLng = (target.lng - before.lng) * (1 - share) + (target.lng - tr.lng) * share;
        const turn = turnBetween(tr.heading, target.heading) * Math.min(1, 6 * dt);
        if (Math.abs(moveLat) < 1e-8 && Math.abs(moveLng) < 1e-8 && Math.abs(turn) < 0.05) return;   // at rest

        tr.lat += moveLat;
        tr.lng += moveLng;
        tr.heading = (tr.heading + turn + 360) % 360;
        const pos = [tr.lat, tr.lng];
        marker.setLatLng(pos);
        const arrow = tr.arrow || (tr.arrow = marker.getElement()?.querySelector(".gmap-bus-heading"));
        if (arrow) arrow.style.transform = `rotate(${tr.heading.toFixed(1)}deg)`;   // only the arrow turns
        const tip = this.trailTips[id];
        if (tip) {
            const tail = tip.getLatLngs()[0];
            tip.setLatLngs([tail, pos]);
        }
        if (this.onFrame) this.onFrame(id, pos);
    }

    /** Popup shown when a bus is tapped on the driver map. */
    busPopupHtml(bus, speed, heading) {
        return `
            <div class="gmap-card-popup">
                <div class="gmap-card-popup-header">
                    <h4 class="gmap-card-title">${escapeHtml(bus.bus_number)}</h4>
                    <span class="gmap-badge-live">${escapeHtml(MT("Live"))}</span>
                </div>
                <p class="gmap-card-sub">${escapeHtml(bus.bus_name)}</p>
                <p class="gmap-card-metric">${escapeHtml(MT("Route"))}: <b>${escapeHtml(bus.route_name || bus.assigned_route_id)}</b></p>
                <p class="gmap-card-metric">${escapeHtml(MT("Speed"))}: <b>${escapeHtml(MT("{speed} km/h", { speed }))}</b></p>
                <p class="gmap-card-metric">${escapeHtml(MT("Next stop"))}: <b>${escapeHtml(bus.next_stop_name || MT("On the way"))}</b></p>
            </div>`;
    }

    /**
     * Draws a red trail behind each given bus (bus.trail = [[lat, lng], ...]) and removes the rest.
     * Each bus has its own trail, so buses that drove the same road each leave a line.
     */
    updateTrails(buses = []) {
        if (!this.leafletMap) return;
        const keep = new Set();
        const style = {
            color: window.APP_CONFIG?.trailColor || "#DC2626", weight: 5, opacity: 0.9,
            lineJoin: "round", lineCap: "round", interactive: false
        };
        buses.forEach(bus => {
            const pts = bus.trail || [];
            if (!bus.is_active || !pts.length) return;
            const id = bus.bus_id;
            keep.add(id);

            // Draw only the new points; redraw everything if the trail was restarted or trimmed
            const drawn = this.trailDrawn[id];
            const line = this.trails[id];
            const sameTrail = drawn && line && pts[0] === drawn.first && pts.length >= drawn.count;
            if (!line) {
                this.trails[id] = L.polyline(pts, style).addTo(this.leafletMap);
            } else if (sameTrail) {
                for (let i = drawn.count; i < pts.length; i++) line.addLatLng(pts[i]);
            } else {
                line.setLatLngs(pts);
            }
            this.trailDrawn[id] = { first: pts[0], count: pts.length };

            // The tip joins the last trail point to the moving marker (moved every frame)
            const tr = this.tracks[id];
            const at = tr ? [tr.lat, tr.lng] : [bus.current_latitude, bus.current_longitude];
            const tip = this.trailTips[id];
            if (tip) tip.setLatLngs([pts[pts.length - 1], at]);
            else this.trailTips[id] = L.polyline([pts[pts.length - 1], at], style).addTo(this.leafletMap);
            this.trails[id].bringToFront();   // always above the route lines
            this.trailTips[id].bringToFront();
        });

        Object.keys(this.trails).forEach(id => {
            if (keep.has(id)) return;
            this.trails[id].remove();
            this.trailTips[id]?.remove();
            delete this.trails[id];
            delete this.trailTips[id];
            delete this.trailDrawn[id];
        });
    }

    // ------------------------------------------------------------------
    // Rider position and Home
    // ------------------------------------------------------------------

    /** Shows the rider's GPS position (blue pulsing dot + accuracy circle) and flies there. */
    updateStudentLocationMarker(lat, lng, accuracy = 20) {
        if (!lat || !lng || !this.leafletMap) return;
        const latLng = [lat, lng];
        const radius = Math.max(accuracy, 15);

        if (this.studentMarker) {
            this.studentMarker.setLatLng(latLng);
            this.studentAccuracyCircle.setLatLng(latLng).setRadius(radius);
        } else {
            this.studentAccuracyCircle = L.circle(latLng, {
                radius, color: "#0284c7", fillColor: "#0284c7", fillOpacity: 0.15, weight: 1.5
            }).addTo(this.leafletMap);

            const icon = L.divIcon({
                className: "gmap-student-icon-wrap",
                html: `
                    <div class="gmap-student-beacon" title="${escapeHtml(MT("Your location"))}">
                        <div class="gmap-student-beacon-wave"></div>
                        <div class="gmap-student-beacon-dot"></div>
                    </div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
            this.studentMarker = L.marker(latLng, { icon, zIndexOffset: 2000 }).addTo(this.leafletMap);
            this.studentMarker.bindPopup(`
                <div class="gmap-card-popup">
                    <h4 class="gmap-card-title">${escapeHtml(MT("Your location"))}</h4>
                    <p class="gmap-card-metric">${escapeHtml(MT("Accurate to about {meters} m", { meters: Math.round(accuracy) }))}</p>
                </div>`);
        }
        this.leafletMap.flyTo(latLng, 15, { duration: 1.2 });
    }

    /**
     * Shows Home as a small dot (no label, no popup) and flies there.
     * It sits below bus markers so a bus waiting at your stop can still be tapped.
     */
    updateHomeLocationMarker(lat, lng) {
        if (!lat || !lng || !this.leafletMap) return;
        const latLng = [lat, lng];
        if (this.homeMarker) {
            this.homeMarker.setLatLng(latLng);
        } else {
            const icon = L.divIcon({
                className: "gmap-home-dot-wrap",
                html: '<div class="gmap-home-dot"></div>',
                iconSize: [14, 14],
                iconAnchor: [7, 7]
            });
            this.homeMarker = L.marker(latLng, { icon, zIndexOffset: 500, interactive: false, keyboard: false }).addTo(this.leafletMap);
        }
        this.leafletMap.flyTo(latLng, 15, { duration: 1.0 });
    }

    // ------------------------------------------------------------------
    // Routes and zooming
    // ------------------------------------------------------------------

    /**
     * Draws every route as a coloured line (white casing underneath so it stands out on the map).
     * Lines are created once; showRoutes() chooses which ones are visible.
     */
    drawRoutes(routes = []) {
        if (!this.leafletMap) return;
        Object.values(this.polylines).forEach(p => { p.glowLine.remove(); p.mainLine.remove(); });
        this.polylines = {};
        this.roadLines = {};

        const lineStyle = { lineJoin: "round", lineCap: "round", interactive: false };
        routes.forEach(route => {
            const points = (route.polyline_waypoints || []).map(p => [p.lat, p.lng]);
            if (points.length < 2) return;
            const glowLine = L.polyline(points, { ...lineStyle, color: "#ffffff", weight: 9, opacity: 0.95 }).addTo(this.leafletMap);
            const mainLine = L.polyline(points, { ...lineStyle, color: route.color_hex || "#2563EB", weight: 5, opacity: 0.9 }).addTo(this.leafletMap);
            this.polylines[route.route_id] = { glowLine, mainLine, points };
            this.roadLines[route.route_id] = new RoadLine(points);
        });
    }

    /** Shows only the given route lines (array of route_ids), or every route when routeIds is null. */
    showRoutes(routeIds = null) {
        if (!this.leafletMap) return;
        const visible = routeIds ? new Set(routeIds) : null;
        Object.entries(this.polylines).forEach(([routeId, p]) => {
            const show = !visible || visible.has(routeId);
            [p.glowLine, p.mainLine].forEach(line => {
                if (show && !this.leafletMap.hasLayer(line)) line.addTo(this.leafletMap);
                if (!show && this.leafletMap.hasLayer(line)) line.remove();
            });
        });
    }

    /**
     * Zooms the map to fit the given points ([[lat, lng], ...]), keeping clear of the
     * top bar, the bottom sheet (bottomPadding px) and a side panel (leftPadding px).
     * Works for one point too: it is centred in the area left visible.
     */
    fitToPoints(points = [], bottomPadding = 120, leftPadding = 24) {
        if (!points.length || !this.leafletMap) return;
        this.leafletMap.flyToBounds(L.latLngBounds(points), {
            paddingTopLeft: [leftPadding, 80],
            paddingBottomRight: [24, bottomPadding + 16],
            duration: 0.8,
            maxZoom: points.length === 1 ? 15 : 16
        });
    }

    /** All points of the given routes (all routes when routeIds is null), for fitToPoints(). */
    getRoutePoints(routeIds = null) {
        const pts = [];
        Object.entries(this.polylines).forEach(([routeId, p]) => {
            if (!routeIds || routeIds.includes(routeId)) pts.push(...p.points);
        });
        return pts;
    }
}

window.googleMapsHelper = new GoogleMapsHelper();
window.BusFeed = BusFeed;
