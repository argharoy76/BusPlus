/**
 * Khulna University Bus Tracker (BusPlus)
 * Real Google Maps Engine & Modern Vector Navigation System
 *
 * Configured just like Uber / special transit apps:
 * - ALL streets, roads, lanes, bridges, highways, and street names are 100% visible and authentic.
 * - Only commercial business clutter (cafes, shops, stores, restaurants, hotels) is removed.
 * - Transit milestones (PTI More, Malabotha More, Gollamari More, KU Campus) are clearly marked.
 */

class GoogleMapsHelper {
    constructor() {
        this.apiKey = window.APP_CONFIG?.googleMapsApiKey || "";
        this.map = null;
        this.mapType = "google_tiles"; // "google_sdk" or "google_tiles"
        this.defaultCenter = {
            lat: window.APP_CONFIG?.universityLocation?.latitude || 22.8010,
            lng: window.APP_CONFIG?.universityLocation?.longitude || 89.5345
        };
        this.defaultZoom = 14;

        // Leaflet Google Maps Tile Layer References
        this.leafletMap = null;
        this.googleRoadmapLayer = null;
        this.googleSatelliteLayer = null;
        this.googleTrafficLayer = null;
        this.currentLayerMode = "roadmap";

        // Marker & Polyline Registries
        this.markers = {};
        this.polylines = {};
        this.trails = {};          // bus_id -> red line of where the bus has driven this trip
        this.stopMarkers = {};
        this.studentAccuracyCircle = null;
        this.activeTargetStopName = "Malabotha More";

        // Optional callback: called with a bus_id when a bus marker is tapped.
        // When set, tapping a bus selects it instead of opening a popup.
        this.onBusMarkerClick = null;

        // Transit/Ride-sharing style filter: Removes commercial clutter (cafes, restaurants, shops, stores, hotels, hospitals)
        // while preserving 100% of ALL streets, roads, alleys, highways, bridges, street names, and university/city landmarks.
        this.cleanApistyle = encodeURIComponent(
            "s.t:33|p.v:off," + // cafes, restaurants, shops, stores, hotels
            "s.t:35|p.v:off," + // hospitals, medical colleges, clinics, pharmacies
            "s.e:l.i|p.v:off"   // all POI establishment icons
        );
    }

    /**
     * Map style for Native Google Maps SDK when API key is provided:
     * Removes hospitals, cafes, restaurants, and shops while keeping all roads, streets, and spot names intact.
     */
    getCleanGoogleSdkStyle() {
        return [
            { "featureType": "poi.business", "stylers": [{ "visibility": "off" }] },
            { "featureType": "poi.medical", "stylers": [{ "visibility": "off" }] },
            { "featureType": "road", "elementType": "all", "stylers": [{ "visibility": "on" }] },
            { "featureType": "road", "elementType": "labels", "stylers": [{ "visibility": "on" }] }
        ];
    }

    /**
     * Initializes the modern Google Map inside containerId.
     */
    async initMap(containerId, options = {}) {
        const container = document.getElementById(containerId);
        if (!container) return null;

        const center = options.center || this.defaultCenter;
        const zoom = options.zoom || this.defaultZoom;

        // If official Google Maps JS API key is provided and SDK loaded, use native Google Maps SDK
        if (this.apiKey && window.google && window.google.maps) {
            try {
                this.map = new google.maps.Map(container, {
                    center: center,
                    zoom: zoom,
                    styles: this.getCleanGoogleSdkStyle(),
                    mapTypeId: "roadmap",
                    mapTypeControl: true,
                    mapTypeControlOptions: {
                        style: google.maps.MapTypeControlStyle.HORIZONTAL_BAR,
                        position: google.maps.ControlPosition.TOP_RIGHT
                    },
                    streetViewControl: false,
                    fullscreenControl: false,
                    zoomControl: true,
                    zoomControlOptions: {
                        position: google.maps.ControlPosition.RIGHT_BOTTOM
                    }
                });
                this.infoWindow = new google.maps.InfoWindow();
                this.mapType = "google_sdk";
                console.log(" Real Google Maps SDK initialized (all streets intact, shops/cafes hidden).");
                return this.map;
            } catch (err) {
                console.warn("Failed to load Google Maps SDK, using Google Maps Tile Engine:", err);
            }
        }

        // Initialize Google Maps Tile Engine via Leaflet
        return this.initGoogleTileMap(container, center, zoom);
    }

    /**
     * Initializes authentic Google Maps tile layers:
     * - All streets, roads, and street names fully visible.
     * - Commercial cafes and shops removed.
     */
    initGoogleTileMap(container, center, zoom) {
        if (!window.L) {
            console.error("Leaflet core is not yet loaded.");
            return null;
        }

        if (this.leafletMap) {
            this.leafletMap.remove();
            this.leafletMap = null;
        }

        // Create Leaflet map with smooth zooming
        this.leafletMap = L.map(container, {
            center: [center.lat, center.lng],
            zoom: zoom,
            zoomControl: false,
            attributionControl: false
        });

        // 1. Google Maps Roadmap Layer (Standard Google Maps LOD strategy: minor streets hidden when zoomed out, street names appear as you zoom in)
        this.googleRoadmapLayer = L.tileLayer(
            `https://mt{s}.google.com/vt/lyrs=m&apistyle=${this.cleanApistyle}&x={x}&y={y}&z={z}`,
            {
                subdomains: ["0", "1", "2", "3"],
                maxZoom: 20,
                attribution: "© Google Maps"
            }
        );

        // 2. Google Maps Satellite + Street Hybrid Layer
        this.googleSatelliteLayer = L.tileLayer(
            "https://mt{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            {
                subdomains: ["0", "1", "2", "3"],
                maxZoom: 20,
                attribution: "© Google Maps Satellite"
            }
        );

        // 3. Google Maps Live Traffic Overlay Layer
        this.googleTrafficLayer = L.tileLayer(
            "https://mt{s}.google.com/vt/lyrs=m,traffic&x={x}&y={y}&z={z}",
            {
                subdomains: ["0", "1", "2", "3"],
                maxZoom: 20,
                attribution: "© Google Maps Traffic"
            }
        );

        // Default to Google Roadmap
        this.googleRoadmapLayer.addTo(this.leafletMap);
        this.mapType = "google_tiles";

        // Level-of-Detail (LOD) listener: Sync container class with zoom level just like Google Maps
        const updateZoomState = () => {
            if (!this.leafletMap) return;
            const z = this.leafletMap.getZoom();
            if (z >= 15) {
                container.classList.add("gmap-zoomed-in");
            } else {
                container.classList.remove("gmap-zoomed-in");
            }
        };
        this.leafletMap.on("zoomend", updateZoomState);
        updateZoomState();

        // Add Google Attribution Badge in bottom right
        const attribBadge = L.control({ position: "bottomright" });
        attribBadge.onAdd = function() {
            const div = L.DomUtil.create("div", "gmap-attrib-pill");
            div.style.cssText = "background:rgba(255,255,255,0.9); backdrop-filter:blur(4px); padding:2px 8px; border-radius:4px; font-size:10px; font-weight:700; color:#334155; margin:4px; box-shadow:0 1px 4px rgba(0,0,0,0.12);";
            div.innerHTML = "Google Maps · Khulna Transit";
            return div;
        };
        attribBadge.addTo(this.leafletMap);

        // Add Modern Floating Google Map Layer Switcher
        this.injectModernLayerSwitcher(container);

        console.log(" Real Google Maps Engine initialized with all streets & street names intact.");
        return this.leafletMap;
    }

    /**
     * Injects a modern Google Maps floating layer switcher pill [ Map | Satellite | Traffic ].
     */
    injectModernLayerSwitcher(container) {
        const oldSwitcher = container.querySelector(".gmap-layer-selector");
        if (oldSwitcher) oldSwitcher.remove();

        const switcher = document.createElement("div");
        switcher.className = "gmap-layer-selector";
        switcher.innerHTML = `
            <button class="gmap-layer-btn active" data-layer="roadmap" title="Map" aria-label="Map">
                <svg class="gmap-layer-ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6.5l6-2.5 6 2.5 6-2.5v13.5l-6 2.5-6-2.5-6 2.5z"/><path d="M9 4v13.5M15 6.5V20"/></svg>
                <span class="gmap-layer-text">Map</span>
            </button>
            <button class="gmap-layer-btn" data-layer="satellite" title="Satellite" aria-label="Satellite">
                <svg class="gmap-layer-ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l9 5-9 5-9-5z"/><path d="M3 12.5l9 5 9-5"/><path d="M3 16.5l9 5 9-5"/></svg>
                <span class="gmap-layer-text">Satellite</span>
            </button>
            <button class="gmap-layer-btn" data-layer="traffic" title="Traffic" aria-label="Traffic">
                <svg class="gmap-layer-ico" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="7.5" y="2.5" width="9" height="19" rx="3"/><circle cx="12" cy="7" r="1.6" fill="currentColor"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/><circle cx="12" cy="17" r="1.6" fill="currentColor"/></svg>
                <span class="gmap-layer-text">Traffic</span>
            </button>
        `;

        switcher.querySelectorAll(".gmap-layer-btn").forEach(btn => {
            btn.addEventListener("click", (e) => {
                e.stopPropagation();
                const mode = btn.getAttribute("data-layer");
                this.switchGoogleMapLayer(mode);

                switcher.querySelectorAll(".gmap-layer-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
            });
        });

        container.appendChild(switcher);
    }

    /**
     * Seamlessly switches the active Google Maps layer.
     */
    switchGoogleMapLayer(mode) {
        if (!this.leafletMap) return;

        [this.googleRoadmapLayer, this.googleSatelliteLayer, this.googleTrafficLayer].forEach(layer => {
            if (layer && this.leafletMap.hasLayer(layer)) {
                this.leafletMap.removeLayer(layer);
            }
        });

        if (mode === "satellite") {
            this.googleSatelliteLayer.addTo(this.leafletMap);
        } else if (mode === "traffic") {
            this.googleTrafficLayer.addTo(this.leafletMap);
        } else {
            this.googleRoadmapLayer.addTo(this.leafletMap);
        }

        this.currentLayerMode = mode;
    }

    /**
     * Updates active broadcasting buses and completely removes inactive/idle demo buses from the map.
     * Ensures only real active buses appear when a driver tests broadcasting/simulation.
     */
    updateActiveBuses(activeBuses = []) {
        const activeIds = new Set(activeBuses.map(b => b.bus_id));

        // Remove any buses currently on map that are no longer active
        Object.keys(this.markers).forEach(id => {
            if (!["student_location", "home_location", "destination"].includes(id) && !activeIds.has(id)) {
                if (this.markers[id]) {
                    if (this.leafletMap && this.markers[id].remove) {
                        this.markers[id].remove();
                    } else if (this.markers[id].setMap) {
                        this.markers[id].setMap(null);
                    }
                    delete this.markers[id];
                }
            }
        });

        // Plot or update each active bus
        activeBuses.forEach(bus => {
            this.updateBusMarker(bus);
        });
    }

    /**
     * Updates or creates a real-time animated Google 3D bus marker.
     * Only actively broadcasting buses will be displayed on the map.
     */
    updateBusMarker(bus) {
        if (!bus) return;
        const id = bus.bus_id;

        // If bus is not actively broadcasting GPS, remove any existing marker and do not show it
        if (!bus.is_active) {
            if (this.markers[id]) {
                if (this.leafletMap && this.markers[id].remove) {
                    this.markers[id].remove();
                } else if (this.markers[id].setMap) {
                    this.markers[id].setMap(null);
                }
                delete this.markers[id];
            }
            return;
        }

        const lat = bus.current_latitude;
        const lng = bus.current_longitude;
        const heading = bus.heading_deg || 0;
        const speed = Math.round(bus.speed_kmh || 0);
        const isActive = bus.is_active;

        const color = bus.color_hex || "#0866FF";

        if (this.mapType === "google_sdk" && window.google?.maps) {
            const pos = { lat, lng };
            if (this.markers[id]) {
                this.glideMarker(this.markers[id], [lat, lng]);
            } else {
                const marker = new google.maps.Marker({
                    position: pos,
                    map: this.map,
                    title: bus.bus_name || bus.bus_number,
                    icon: {
                        path: google.maps.SymbolPath.CIRCLE,
                        scale: 11,
                        fillColor: color,
                        fillOpacity: 1,
                        strokeColor: "#ffffff",
                        strokeWeight: 3
                    },
                    zIndex: 1000
                });
                if (this.onBusMarkerClick) {
                    marker.addListener("click", () => this.onBusMarkerClick(id));
                }
                this.markers[id] = marker;
            }
            return;
        }

        if (!this.leafletMap) return;

        const latLng = [lat, lng];

        if (this.markers[id]) {
            this.glideMarker(this.markers[id], latLng);

            const containerEl = this.markers[id].getElement();
            if (containerEl) {
                const wrapEl = containerEl.querySelector(".gmap-bus-container");
                const headingEl = containerEl.querySelector(".gmap-bus-heading");
                const speedTag = containerEl.querySelector(".gmap-bus-speed-tag");
                const pulseRing = containerEl.querySelector(".gmap-bus-pulse-ring");

                if (wrapEl) {
                    wrapEl.style.setProperty("--bus-color", color);
                }
                if (headingEl) {
                    // Only the direction arrow turns; the bus icon stays upright
                    headingEl.style.transform = `rotate(${heading}deg)`;
                }
                if (speedTag) {
                    speedTag.textContent = `${speed} km/h`;
                }
                if (pulseRing) {
                    pulseRing.className = "gmap-bus-pulse-ring";
                }
            }
            // Keep the popup (driver page) in step with the live telemetry
            if (this.markers[id].getPopup && this.markers[id].getPopup()) {
                this.markers[id].setPopupContent(this.busPopupHtml(bus, speed, heading));
            }
        } else {
            const busIcon = L.divIcon({
                className: "gmap-bus-marker-wrap",
                html: `
                    <div class="gmap-bus-container" style="--bus-color: ${this.escapeHtml(color)};" title="${this.escapeHtml(bus.bus_name || bus.bus_number)}">
                        <div class="gmap-bus-pulse-ring"></div>
                        <div class="gmap-bus-body">
                            <div class="gmap-bus-heading" style="position:absolute; inset:0; pointer-events:none; transition:transform 0.4s ease; transform: rotate(${heading}deg);">
                                <div class="gmap-bus-heading-arrow"></div>
                            </div>
                            <svg class="gmap-bus-svg" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="#ffffff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="3" width="14" height="14.5" rx="3"/><path d="M5 10.5h14"/><path d="M9.5 6.5h5"/><path d="M7.5 17.5v2.5M16.5 17.5v2.5"/></svg>
                        </div>
                        <div class="gmap-bus-speed-tag">${speed} km/h</div>
                    </div>
                `,
                iconSize: [44, 44],
                iconAnchor: [22, 22]
            });

            const marker = L.marker(latLng, { icon: busIcon, zIndexOffset: 1000 }).addTo(this.leafletMap);

            if (this.onBusMarkerClick) {
                // Student map: tapping a bus selects it in the bottom sheet
                marker.on("click", () => this.onBusMarkerClick(id));
            } else {
                marker.bindPopup(this.busPopupHtml(bus, speed, heading));
            }
            this.markers[id] = marker;
        }
    }

    /**
     * Moves a marker smoothly to a new position (about one second), so live buses
     * glide along instead of jumping between GPS fixes. Big jumps snap straight there.
     */
    glideMarker(marker, to, ms = 900) {
        const isGoogle = typeof marker.getPosition === "function";
        const cur = isGoogle ? marker.getPosition() : marker.getLatLng();
        const from = isGoogle ? [cur.lat(), cur.lng()] : [cur.lat, cur.lng];
        const set = (lat, lng) => isGoogle ? marker.setPosition({ lat, lng }) : marker.setLatLng([lat, lng]);
        if (marker._glide) cancelAnimationFrame(marker._glide);

        const dLat = to[0] - from[0], dLng = to[1] - from[1];
        const far = Math.abs(dLat) > 0.02 || Math.abs(dLng) > 0.02;          // > ~2 km: just jump
        if (far || (dLat === 0 && dLng === 0) || document.hidden) { set(to[0], to[1]); return; }

        const start = performance.now();
        const step = (now) => {
            const t = Math.min(1, (now - start) / ms);
            const e = t * (2 - t);                                              // ease-out
            set(from[0] + dLat * e, from[1] + dLng * e);
            marker._glide = t < 1 ? requestAnimationFrame(step) : null;
        };
        marker._glide = requestAnimationFrame(step);
    }

    busPopupHtml(bus, speed, heading) {
        const esc = (v) => this.escapeHtml(v);
        return `
            <div class="gmap-card-popup">
                <div class="gmap-card-popup-header">
                    <h4 class="gmap-card-title">${esc(bus.bus_number)}</h4>
                    <span class="gmap-badge-live">● LIVE GPS</span>
                </div>
                <p style="margin:2px 0 6px; font-weight:700; color:#1e40af; font-size:0.875rem;">${esc(bus.bus_name)}</p>
                <p class="gmap-card-metric">Route: <b>${esc(bus.route_name || bus.assigned_route_id)}</b></p>
                <p class="gmap-card-metric">Speed: <b>${speed} km/h</b> (Heading ${Math.round(heading)}°)</p>
                <p class="gmap-card-metric">Approaching: <b>${esc(bus.next_stop_name || 'En route to KU')}</b></p>
            </div>
        `;
    }

    escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    /**
     * Updates student's live GPS blue beacon marker with pulsing radar halo and accuracy radius.
     */
    updateStudentLocationMarker(lat, lng, accuracy = 20) {
        if (!lat || !lng) return;

        if (this.mapType === "google_sdk" && window.google?.maps) {
            this.map.panTo({ lat, lng });
            return;
        }

        if (!this.leafletMap) return;

        const latLng = [lat, lng];

        if (this.markers["student_location"]) {
            this.markers["student_location"].setLatLng(latLng);
            if (this.studentAccuracyCircle) {
                this.studentAccuracyCircle.setLatLng(latLng);
                this.studentAccuracyCircle.setRadius(Math.max(accuracy, 15));
            }
        } else {
            this.studentAccuracyCircle = L.circle(latLng, {
                radius: Math.max(accuracy, 15),
                color: "#0284c7",
                fillColor: "#0284c7",
                fillOpacity: 0.15,
                weight: 1.5
            }).addTo(this.leafletMap);

            const studentIcon = L.divIcon({
                className: "gmap-student-icon-wrap",
                html: `
                    <div class="gmap-student-beacon" title="Your GPS Location">
                        <div class="gmap-student-beacon-wave"></div>
                        <div class="gmap-student-beacon-dot"></div>
                    </div>
                `,
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });

            this.markers["student_location"] = L.marker(latLng, { icon: studentIcon, zIndexOffset: 2000 }).addTo(this.leafletMap);
            this.markers["student_location"].bindPopup(`
                <div class="gmap-card-popup">
                    <h4 class="gmap-card-title">📍 Your Live Location</h4>
                    <p class="gmap-card-metric">GPS Accuracy: ±${Math.round(accuracy)}m</p>
                </div>
            `);
        }

        this.leafletMap.flyTo(latLng, 15, { duration: 1.2 });
    }

    /**
     * Marks the final destination of every route (Hadi Chattar) with a flag label.
     */
    updateDestinationMarker(lat, lng, label = "Hadi Chattar") {
        if (!lat || !lng) return;
        if (this.mapType === "google_sdk" && window.google?.maps) {
            if (!this.markers["destination"]) {
                this.markers["destination"] = new google.maps.Marker({
                    position: { lat, lng }, map: this.map, title: label, zIndex: 900,
                    label: { text: "🏁", fontSize: "16px" }
                });
            }
            return;
        }
        if (!this.leafletMap) return;
        const icon = L.divIcon({
            className: "gmap-dest-marker-wrap",
            html: `<div class="gmap-dest-badge"><span class="gmap-dest-flag">🏁</span><span class="gmap-dest-name">${this.escapeHtml(label)}</span></div>`,
            iconSize: [120, 30],
            iconAnchor: [14, 30]
        });
        if (this.markers["destination"]) {
            this.markers["destination"].setLatLng([lat, lng]).setIcon(icon);
        } else {
            this.markers["destination"] = L.marker([lat, lng], { icon, zIndexOffset: 800, interactive: false }).addTo(this.leafletMap);
        }
    }

    /**
     * Updates student's designated Home Location marker on the map.
     */
    updateHomeLocationMarker(lat, lng, label = "Home") {
        if (!lat || !lng) return;

        if (this.mapType === "google_sdk" && window.google?.maps) {
            this.map.panTo({ lat, lng });
            return;
        }

        if (!this.leafletMap) return;

        const latLng = [lat, lng];

        // Home is just a small dot: no label, no popup.
        // Below bus markers (1000) so a bus waiting at your stop can still be tapped.
        if (this.markers["home_location"]) {
            this.markers["home_location"].setLatLng(latLng);
        } else {
            const homeIcon = L.divIcon({
                className: "gmap-home-dot-wrap",
                html: `<div class="gmap-home-dot"></div>`,
                iconSize: [14, 14],
                iconAnchor: [7, 7]
            });
            this.markers["home_location"] = L.marker(latLng, { icon: homeIcon, zIndexOffset: 500, interactive: false, keyboard: false }).addTo(this.leafletMap);
        }

        this.leafletMap.flyTo(latLng, 15, { duration: 1.0 });
    }

    /**
     * Draws every route as a coloured line (white casing underneath so it stands out on the map).
     * Lines are created once; use showRoutes() to choose which ones are visible.
     */
    drawRoutes(routes = []) {
        this.clearAllRoutes();
        routes.forEach(route => {
            const pts = (route.polyline_waypoints || []).map(p => [p.lat, p.lng]);
            if (pts.length < 2) return;
            const color = route.color_hex || "#2563EB";

            if (this.mapType === "google_sdk" && window.google?.maps) {
                const path = pts.map(([lat, lng]) => ({ lat, lng }));
                const glowLine = new google.maps.Polyline({ path, map: this.map, strokeColor: "#ffffff", strokeOpacity: 0.95, strokeWeight: 9, zIndex: 1 });
                const mainLine = new google.maps.Polyline({ path, map: this.map, strokeColor: color, strokeOpacity: 0.9, strokeWeight: 5, zIndex: 2 });
                this.polylines[route.route_id] = { glowLine, mainLine, points: pts };
                return;
            }

            if (!this.leafletMap) return;
            const glowLine = L.polyline(pts, { color: "#ffffff", weight: 9, opacity: 0.95, lineJoin: "round", lineCap: "round", interactive: false }).addTo(this.leafletMap);
            const mainLine = L.polyline(pts, { color, weight: 5, opacity: 0.9, lineJoin: "round", lineCap: "round", interactive: false }).addTo(this.leafletMap);
            this.polylines[route.route_id] = { glowLine, mainLine, points: pts };
        });
    }

    /**
     * Draws a red trail behind each given bus (bus.trail = [[lat, lng], ...]) and removes the rest.
     * Each bus has its own trail, so buses that drove the same road each leave a line.
     */
    updateTrails(buses = []) {
        const keep = new Set();
        buses.forEach(bus => {
            const pts = (bus.trail || []).slice();
            if (bus.is_active && bus.current_latitude && bus.current_longitude) {
                pts.push([bus.current_latitude, bus.current_longitude]);   // reach right up to the bus
            }
            if (pts.length < 2) return;
            keep.add(bus.bus_id);

            if (this.mapType === "google_sdk" && window.google?.maps) {
                const path = pts.map(([lat, lng]) => ({ lat, lng }));
                if (this.trails[bus.bus_id]) this.trails[bus.bus_id].setPath(path);
                else this.trails[bus.bus_id] = new google.maps.Polyline({
                    path, map: this.map, strokeColor: "#DC2626", strokeOpacity: 0.9, strokeWeight: 5, zIndex: 50
                });
                return;
            }
            if (!this.leafletMap) return;
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
            const line = this.trails[id];
            if (line.setMap) line.setMap(null); else line.remove();
            delete this.trails[id];
        });
    }

    /**
     * Shows only the given route lines (array of route_ids), or every route when routeIds is null.
     */
    showRoutes(routeIds = null) {
        const visible = routeIds ? new Set(routeIds) : null;
        Object.entries(this.polylines).forEach(([routeId, p]) => {
            const show = !visible || visible.has(routeId);
            [p.glowLine, p.mainLine].forEach(line => {
                if (!line) return;
                if (line.setMap) {
                    line.setMap(show ? this.map : null);
                } else if (this.leafletMap) {
                    if (show && !this.leafletMap.hasLayer(line)) line.addTo(this.leafletMap);
                    if (!show && this.leafletMap.hasLayer(line)) line.remove();
                }
            });
        });
    }

    /**
     * Zooms the map to fit the given points ([[lat, lng], ...]), keeping clear of the
     * top bar and the bottom sheet (bottomPadding px).
     */
    fitToPoints(points = [], bottomPadding = 120, leftPadding = 24) {
        if (!points.length) return;
        if (this.mapType === "google_sdk" && window.google?.maps && this.map) {
            const bounds = new google.maps.LatLngBounds();
            points.forEach(([lat, lng]) => bounds.extend({ lat, lng }));
            this.map.fitBounds(bounds, { top: 80, left: leftPadding, right: 24, bottom: bottomPadding + 16 });
            return;
        }
        if (!this.leafletMap) return;
        // Works for one point too: it is centred in the area left visible above the sheet
        this.leafletMap.flyToBounds(L.latLngBounds(points), {
            paddingTopLeft: [leftPadding, 80],
            paddingBottomRight: [24, bottomPadding + 16],
            duration: 0.8,
            maxZoom: points.length === 1 ? 15 : 16
        });
    }

    /** Points of the given routes (all routes when routeIds is null), for fitToPoints(). */
    getRoutePoints(routeIds = null) {
        const pts = [];
        Object.entries(this.polylines).forEach(([routeId, p]) => {
            if (!routeIds || routeIds.includes(routeId)) pts.push(...p.points);
        });
        return pts;
    }

    /**
     * Kept for older callers: draws a single route.
     */
    renderRoute(route) {
        if (route) this.drawRoutes([route]);
    }

    /**
     * Clears all route polylines and stop markers if any exist.
     */
    clearAllRoutes() {
        Object.values(this.polylines).forEach(p => {
            [p && p.glowLine, p && p.mainLine].forEach(line => {
                if (!line) return;
                if (line.setMap) line.setMap(null);
                else if (line.remove) line.remove();
            });
        });
        this.polylines = {};

        Object.values(this.stopMarkers).forEach(m => {
            if (m && m.remove) m.remove();
        });
        this.stopMarkers = {};
    }

    /**
     * Sets target stop name reference.
     */
    setTargetStop(stopName) {
        this.activeTargetStopName = stopName || "";
    }

    /**
     * Smoothly pans and zooms to specific coordinate.
     */
    panTo(lat, lng, zoom = 15) {
        if (this.map && this.mapType === "google_sdk") {
            this.map.panTo({ lat, lng });
            if (zoom) this.map.setZoom(zoom);
        } else if (this.leafletMap) {
            this.leafletMap.flyTo([lat, lng], zoom, { duration: 1.0 });
        }
    }
}

// Global instance
window.googleMapsHelper = new GoogleMapsHelper();
