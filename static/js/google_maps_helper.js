/*
 * BusPlus map helper, used by the rider map (student/teacher) and the driver map.
 *
 * Draws a Leaflet map with Google Maps tiles, plus everything BusPlus puts on it:
 * route lines, live bus markers (they glide between GPS fixes), the red trail each
 * bus has driven, the rider's GPS position and the Home dot.
 * Page scripts use the single shared instance: window.googleMapsHelper.
 */

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

class GoogleMapsHelper {
    constructor() {
        const ku = window.APP_CONFIG?.universityLocation || {};
        this.defaultCenter = { lat: ku.latitude || 22.8010, lng: ku.longitude || 89.5345 };
        this.defaultZoom = 14;

        this.leafletMap = null;
        this.layers = {};          // "roadmap" | "satellite" | "traffic" -> tile layer
        this.busMarkers = {};      // bus_id -> marker
        this.polylines = {};       // route_id -> { glowLine, mainLine, points }
        this.trails = {};          // bus_id -> red line of where the bus has driven this trip
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

        const tiles = (url) => L.tileLayer(url, { subdomains: ["0", "1", "2", "3"], maxZoom: 20 });
        this.layers = {
            roadmap: tiles(googleTileUrl("m", `&apistyle=${CLEAN_MAP_STYLE}`)),
            satellite: tiles(googleTileUrl("y")),
            traffic: tiles(googleTileUrl("m,traffic"))
        };
        this.layers.roadmap.addTo(this.leafletMap);

        if (attribution) {
            const badge = L.control({ position: "bottomright" });
            badge.onAdd = () => {
                const div = L.DomUtil.create("div", "gmap-attrib-pill");
                div.textContent = "Google Maps · Khulna Transit";
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
        const buttons = [
            ["roadmap", "Map", '<path d="M3 6.5l6-2.5 6 2.5 6-2.5v13.5l-6 2.5-6-2.5-6 2.5z"/><path d="M9 4v13.5M15 6.5V20"/>'],
            ["satellite", "Satellite", '<path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12.5l9 5 9-5"/><path d="M3 16.5l9 5 9-5"/>'],
            ["traffic", "Traffic", '<rect x="7.5" y="2.5" width="9" height="19" rx="3"/><circle cx="12" cy="7" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="17" r="1.6" fill="currentColor"/>']
        ];

        const switcher = document.createElement("div");
        switcher.className = "gmap-layer-selector";
        switcher.innerHTML = buttons.map(([layer, label, paths], i) =>
            `<button type="button" class="gmap-layer-btn${i === 0 ? " active" : ""}" data-layer="${layer}" title="${label}" aria-label="${label}">${icon(paths)}</button>`
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
        (this.layers[mode] || this.layers.roadmap).addTo(this.leafletMap);
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

    removeBusMarker(id) {
        this.busMarkers[id]?.remove();
        delete this.busMarkers[id];
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
            this.glideMarker(marker, latLng);
            const el = marker.getElement();
            if (el) {
                el.querySelector(".gmap-bus-container")?.style.setProperty("--bus-color", color);
                const headingEl = el.querySelector(".gmap-bus-heading");
                if (headingEl) headingEl.style.transform = `rotate(${heading}deg)`;   // only the arrow turns
                const speedTag = el.querySelector(".gmap-bus-speed-tag");
                if (speedTag) speedTag.textContent = `${speed} km/h`;
            }
            // Keep an open popup (driver map) in step with the live data
            if (marker.getPopup()) marker.setPopupContent(this.busPopupHtml(bus, speed, heading));
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
                    <div class="gmap-bus-speed-tag">${speed} km/h</div>
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
    }

    /**
     * Moves a marker smoothly to a new position (about one second), so live buses
     * glide along instead of jumping between GPS fixes. Big jumps snap straight there.
     */
    glideMarker(marker, to, ms = 900) {
        const cur = marker.getLatLng();
        const from = [cur.lat, cur.lng];
        if (marker._glide) cancelAnimationFrame(marker._glide);

        const dLat = to[0] - from[0], dLng = to[1] - from[1];
        const far = Math.abs(dLat) > 0.02 || Math.abs(dLng) > 0.02;          // > ~2 km: just jump
        if (far || (dLat === 0 && dLng === 0) || document.hidden) { marker.setLatLng(to); return; }

        const start = performance.now();
        const step = (now) => {
            const t = Math.min(1, (now - start) / ms);
            const e = t * (2 - t);                                              // ease-out
            marker.setLatLng([from[0] + dLat * e, from[1] + dLng * e]);
            marker._glide = t < 1 ? requestAnimationFrame(step) : null;
        };
        marker._glide = requestAnimationFrame(step);
    }

    /** Popup shown when a bus is tapped on the driver map. */
    busPopupHtml(bus, speed, heading) {
        return `
            <div class="gmap-card-popup">
                <div class="gmap-card-popup-header">
                    <h4 class="gmap-card-title">${escapeHtml(bus.bus_number)}</h4>
                    <span class="gmap-badge-live">● LIVE GPS</span>
                </div>
                <p class="gmap-card-sub">${escapeHtml(bus.bus_name)}</p>
                <p class="gmap-card-metric">Route: <b>${escapeHtml(bus.route_name || bus.assigned_route_id)}</b></p>
                <p class="gmap-card-metric">Speed: <b>${speed} km/h</b> (Heading ${Math.round(heading)}°)</p>
                <p class="gmap-card-metric">Approaching: <b>${escapeHtml(bus.next_stop_name || "En route to KU")}</b></p>
            </div>`;
    }

    /**
     * Draws a red trail behind each given bus (bus.trail = [[lat, lng], ...]) and removes the rest.
     * Each bus has its own trail, so buses that drove the same road each leave a line.
     */
    updateTrails(buses = []) {
        if (!this.leafletMap) return;
        const keep = new Set();
        buses.forEach(bus => {
            const pts = (bus.trail || []).slice();
            if (bus.is_active && bus.current_latitude && bus.current_longitude) {
                pts.push([bus.current_latitude, bus.current_longitude]);   // reach right up to the bus
            }
            if (pts.length < 2) return;
            keep.add(bus.bus_id);

            if (this.trails[bus.bus_id]) {
                this.trails[bus.bus_id].setLatLngs(pts);
            } else {
                this.trails[bus.bus_id] = L.polyline(pts, {
                    color: "#DC2626", weight: 5, opacity: 0.9, lineJoin: "round", lineCap: "round", interactive: false
                }).addTo(this.leafletMap);
            }
            this.trails[bus.bus_id].bringToFront();   // always above the route lines
        });

        Object.keys(this.trails).forEach(id => {
            if (keep.has(id)) return;
            this.trails[id].remove();
            delete this.trails[id];
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
                    <div class="gmap-student-beacon" title="Your GPS Location">
                        <div class="gmap-student-beacon-wave"></div>
                        <div class="gmap-student-beacon-dot"></div>
                    </div>`,
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
            this.studentMarker = L.marker(latLng, { icon, zIndexOffset: 2000 }).addTo(this.leafletMap);
            this.studentMarker.bindPopup(`
                <div class="gmap-card-popup">
                    <h4 class="gmap-card-title">📍 Your Live Location</h4>
                    <p class="gmap-card-metric">GPS Accuracy: ±${Math.round(accuracy)}m</p>
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

        const lineStyle = { lineJoin: "round", lineCap: "round", interactive: false };
        routes.forEach(route => {
            const points = (route.polyline_waypoints || []).map(p => [p.lat, p.lng]);
            if (points.length < 2) return;
            const glowLine = L.polyline(points, { ...lineStyle, color: "#ffffff", weight: 9, opacity: 0.95 }).addTo(this.leafletMap);
            const mainLine = L.polyline(points, { ...lineStyle, color: route.color_hex || "#2563EB", weight: 5, opacity: 0.9 }).addTo(this.leafletMap);
            this.polylines[route.route_id] = { glowLine, mainLine, points };
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
