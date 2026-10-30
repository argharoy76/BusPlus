/* Backend admin panel (/backend): drivers, routes (map editor), buses. */

// Data the page was rendered with (routes, buses, final destination)
const ADMIN_DATA = JSON.parse(document.getElementById("admin-data").textContent);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- Shared helpers ----------
function switchTab(tabName) {
    const tab = document.getElementById(`tab-${tabName}`);
    const nav = document.getElementById(`nav-${tabName}`);
    if (!tab || !nav) return;
    document.querySelectorAll(".tab-section").forEach(s => s.classList.remove("active"));
    document.querySelectorAll(".admin-nav-item").forEach(n => n.classList.remove("active"));
    tab.classList.add("active");
    nav.classList.add("active");
    try { sessionStorage.setItem("busplus_admin_tab", tabName); } catch (e) { /* storage blocked */ }
}
try {
    const savedTab = sessionStorage.getItem("busplus_admin_tab");
    if (savedTab) switchTab(savedTab);
} catch (e) {}

function openModal(id) { document.getElementById(id).classList.add("active"); }
function closeModal(id) {
    document.getElementById(id).classList.remove("active");
    if (typeof closeSuggest === "function") closeSuggest();
}
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".modal-overlay.active").forEach(m => m.classList.remove("active"));
});

function showFormError(id, message) {
    const box = document.getElementById(id);
    box.textContent = message || "";
    box.style.display = message ? "block" : "none";
}

let toastTimer = null;
function toast(message, isError = false) {
    const t = document.getElementById("admin-toast");
    t.textContent = message;
    t.classList.toggle("error", !!isError);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

async function api(method, url, body) {
    const resp = await fetch(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined
    });
    if (resp.status === 401) {
        window.location.href = "/backend/login";
        throw new Error("Signed out");
    }
    const data = await resp.json().catch(() => ({}));
    return { ok: resp.ok && data.success !== false, data };
}

// ---------- Drivers ----------
const driverBusSelect = document.getElementById("driver-bus");
function updateDriverRouteNote() {
    const opt = driverBusSelect.selectedOptions[0];
    const route = opt ? ADMIN_DATA.routes.find(r => r.route_id === opt.dataset.routeId) : null;
    document.getElementById("driver-route-note").textContent = route ? `Route today: ${route.route_name}` : "";
}
driverBusSelect.addEventListener("change", updateDriverRouteNote);

function openDriverModal(driver) {
    showFormError("driver-form-error", "");
    const editing = !!driver;
    document.getElementById("driver-modal-title").textContent = editing ? `Edit ${driver.full_name}` : "Add Driver";
    document.getElementById("driver-submit-btn").textContent = editing ? "Save" : "Add Driver";
    document.getElementById("driver-id").value = editing ? driver.driver_id : "";
    document.getElementById("driver-name").value = editing ? driver.full_name : "";
    document.getElementById("driver-phone").value = editing ? (driver.phone || "") : "";
    // PINs are stored hashed, so they can't be shown. Leave the box empty to keep the current PIN.
    const pinInput = document.getElementById("driver-pin");
    pinInput.value = "";
    pinInput.required = !editing;
    pinInput.placeholder = editing ? "New PIN (optional)" : "4–8 digits";
    document.getElementById("driver-pin-note").textContent = editing ? "Leave empty to keep the current PIN." : "";
    if (editing && driver.assigned_bus_id) driverBusSelect.value = driver.assigned_bus_id;
    updateDriverRouteNote();
    openModal("modal-driver");
    setTimeout(() => document.getElementById("driver-name").focus(), 50);
}

document.getElementById("form-driver").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("driver-id").value;
    const payload = {
        full_name: document.getElementById("driver-name").value.trim(),
        phone: document.getElementById("driver-phone").value.trim(),
        pin: document.getElementById("driver-pin").value.trim(),
        assigned_bus_id: driverBusSelect.value
    };
    const { ok, data } = await api(id ? "PUT" : "POST", id ? `/api/admin/drivers/${encodeURIComponent(id)}` : "/api/admin/drivers", payload);
    if (ok) location.reload();
    else showFormError("driver-form-error", data.message || "Could not save the driver.");
});

async function unlockDriver(driverId, name) {
    if (!confirm(`Sign ${name} out of their device so they can log in again?`)) return;
    const { ok, data } = await api("POST", `/api/admin/drivers/${encodeURIComponent(driverId)}/unlock`);
    if (ok) location.reload(); else toast(data.message || "Could not unlock.", true);
}

async function deleteDriver(driverId, name) {
    if (!confirm(`Delete driver ${name}?`)) return;
    const { ok, data } = await api("DELETE", `/api/admin/drivers/${encodeURIComponent(driverId)}`);
    if (ok) location.reload(); else toast(data.message || "Could not delete.", true);
}

// ---------- Routes (map editor) ----------
// The admin clicks points along the roads; the line between them follows the roads (OSRM).
let routeMap = null;
let routeLayer = null;
let editPoints = [];          // [{lat, lng, name}] - name only kept for built-in routes' places
let roadPath = null;          // [[lat, lng], ...] following the roads, or null if not available
let roadIsFresh = false;      // true when roadPath was just worked out from the road map
let roadRequest = 0;
let roadTimer = null;

function routeColor() { return document.getElementById("route-color").value; }
function destLatLng() { return [ADMIN_DATA.destination.latitude, ADMIN_DATA.destination.longitude]; }

function ensureRouteMap() {
    if (routeMap) return;
    routeMap = L.map("route-map", { zoomControl: true, attributionControl: false, doubleClickZoom: false })
        .setView(destLatLng(), 13);
    L.tileLayer("https://mt{s}.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", { subdomains: ["0", "1", "2", "3"], maxZoom: 20 }).addTo(routeMap);
    routeLayer = L.layerGroup().addTo(routeMap);
    routeMap.on("click", (e) => {
        editPoints.push({ lat: +e.latlng.lat.toFixed(6), lng: +e.latlng.lng.toFixed(6), name: "" });
        routeChanged();
    });
}

function routeChanged() {
    drawRoute();
    clearTimeout(roadTimer);
    roadTimer = setTimeout(fetchRoadPath, 250);
}

// Ask the road map for the driving route through the points and on to Hadi Chattar
async function fetchRoadPath() {
    const id = ++roadRequest;
    if (!editPoints.length) { roadPath = null; drawRoute(); return; }
    const coords = editPoints.map(p => [p.lat, p.lng]).concat([destLatLng()]);
    setRouteInfo("Finding the roads…");
    try {
        // Our server asks the road map (no browser cross-site issues)
        const { ok, data } = await api("POST", "/api/admin/road-path", { points: coords });
        if (id !== roadRequest) return;               // a newer change is on its way
        if (!ok || !data.path?.length) throw new Error(data.message || "no route");
        roadPath = data.path;
        roadIsFresh = true;
        drawRoute();
    } catch (err) {
        if (id !== roadRequest) return;
        roadPath = null;
        drawRoute(true);
    }
}

function lengthKm(pts) {
    let km = 0;
    for (let i = 1; i < pts.length; i++) {
        const [a, b] = pts[i - 1], [c, d] = pts[i];
        const r = Math.PI / 180, x = (d - b) * r * Math.cos((a + c) / 2 * r), y = (c - a) * r;
        km += Math.sqrt(x * x + y * y) * 6371;
    }
    return km;
}

function setRouteInfo(text, warn = false) {
    const el = document.getElementById("route-info");
    el.textContent = text;
    el.classList.toggle("warn", warn);
}

function drawRoute(roadFailed = false) {
    if (!routeMap) return;
    routeLayer.clearLayers();
    const color = routeColor();
    const straight = editPoints.map(p => [p.lat, p.lng]).concat([destLatLng()]);
    const line = roadPath || straight;
    if (editPoints.length) {
        L.polyline(line, { color: "#ffffff", weight: 8, opacity: 0.9 }).addTo(routeLayer);
        L.polyline(line, { color, weight: 4, opacity: 0.95, dashArray: roadPath ? null : "6 8" }).addTo(routeLayer);
    }
    editPoints.forEach((p, i) => {
        const m = L.marker([p.lat, p.lng], {
            draggable: true,
            icon: L.divIcon({ className: "route-stop-marker", html: `<div style="background:${esc(color)}">${i + 1}</div>`, iconSize: [24, 24], iconAnchor: [12, 12] })
        }).addTo(routeLayer);
        m.bindTooltip(i === 0 ? "Start · drag to move, double-click to remove" : "Drag to move, double-click to remove");
        m.on("dragend", () => {
            const ll = m.getLatLng();
            p.lat = +ll.lat.toFixed(6);
            p.lng = +ll.lng.toFixed(6);
            routeChanged();
        });
        m.on("dblclick", (e) => {
            L.DomEvent.stop(e);
            editPoints.splice(i, 1);
            routeChanged();
        });
    });
    L.marker(destLatLng(), {
        interactive: false,
        icon: L.divIcon({ className: "route-dest-marker", html: `<div>🏁 ${esc(ADMIN_DATA.destination.stop_name)}</div>`, iconSize: [110, 22], iconAnchor: [12, 22] })
    }).addTo(routeLayer);

    if (!editPoints.length) setRouteInfo("Click the map where the route starts.");
    else if (roadFailed) setRouteInfo("Couldn't reach the road map, so the line is drawn straight. It will still save.", true);
    else if (roadPath) setRouteInfo(roadIsFresh ? `${lengthKm(roadPath).toFixed(1)} km along the roads` : `${lengthKm(roadPath).toFixed(1)} km`);
}

document.getElementById("route-color").addEventListener("input", () => drawRoute());
document.getElementById("route-undo").addEventListener("click", () => { editPoints.pop(); routeChanged(); });
document.getElementById("route-clear").addEventListener("click", () => {
    if (editPoints.length && !confirm("Remove all points of this route?")) return;
    editPoints = [];
    routeChanged();
});
document.getElementById("route-name").addEventListener("input", () => showFormError("route-form-error", ""));

// ---------- Place-name suggestions ----------
// Every stop the app knows (all routes), except the final destination
function knownPlaces() {
    const seen = new Map();
    const dest = ADMIN_DATA.destination.stop_name.toLowerCase();
    ADMIN_DATA.routes.forEach(r => (r.stops || []).forEach(st => {
        const key = st.stop_name.toLowerCase();
        if (key !== dest && !seen.has(key)) seen.set(key, { name: st.stop_name, lat: st.latitude, lng: st.longitude });
    }));
    return Array.from(seen.values());
}

function matchPlaces(query) {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return knownPlaces()
        .map(p => {
            const n = p.name.toLowerCase();
            const score = n.startsWith(q) ? 0 : n.split(/[\s\-/]+/).some(w => w.startsWith(q)) ? 1 : n.includes(q) ? 2 : -1;
            return { p, score };
        })
        .filter(x => x.score >= 0)
        .sort((a, b) => a.score - b.score || a.p.name.localeCompare(b.p.name))
        .slice(0, 8)
        .map(x => x.p);
}

const suggestBox = document.createElement("div");
suggestBox.className = "place-suggest";
suggestBox.setAttribute("role", "listbox");
document.body.appendChild(suggestBox);
let suggestFor = null;      // { input, onPick, items, active }

function closeSuggest() {
    suggestBox.classList.remove("open");
    suggestBox.innerHTML = "";
    suggestFor = null;
}

function showSuggest(input, onPick) {
    const items = matchPlaces(input.value);
    if (!items.length) { closeSuggest(); return; }
    const q = input.value.trim();
    suggestBox.innerHTML = items.map((p, i) => {
        const n = p.name, at = n.toLowerCase().indexOf(q.toLowerCase());
        const label = at < 0 ? esc(n) : esc(n.slice(0, at)) + "<mark>" + esc(n.slice(at, at + q.length)) + "</mark>" + esc(n.slice(at + q.length));
        return `<div class="place-option" role="option" data-i="${i}"><span class="place-pin">📍</span><span>${label}</span></div>`;
    }).join("");
    const r = input.getBoundingClientRect();
    suggestBox.style.left = `${r.left}px`;
    suggestBox.style.top = `${r.bottom + 4}px`;
    suggestBox.style.width = `${Math.max(r.width, 240)}px`;
    suggestBox.classList.add("open");
    suggestFor = { input, onPick, items, active: -1 };
    suggestBox.querySelectorAll(".place-option").forEach(opt => {
        opt.addEventListener("pointerdown", (e) => {
            e.preventDefault();             // keep focus in the input
            pickSuggest(+opt.dataset.i);
        });
    });
}

function pickSuggest(i) {
    if (!suggestFor) return;
    const { onPick, items } = suggestFor;
    const place = items[i];
    closeSuggest();
    if (place) onPick(place);
}

function attachPlaceSuggest(input, onPick) {
    input.addEventListener("input", () => showSuggest(input, onPick));
    input.addEventListener("focus", () => { if (input.value.trim()) showSuggest(input, onPick); });
    input.addEventListener("blur", () => setTimeout(() => { if (suggestFor?.input === input) closeSuggest(); }, 120));
    input.addEventListener("keydown", (e) => {
        if (!suggestFor || suggestFor.input !== input) return;
        const n = suggestFor.items.length;
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
            e.preventDefault();
            suggestFor.active = (suggestFor.active + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
            suggestBox.querySelectorAll(".place-option").forEach((o, i) => o.classList.toggle("active", i === suggestFor.active));
        } else if (e.key === "Enter") {
            e.preventDefault();
            pickSuggest(suggestFor.active >= 0 ? suggestFor.active : 0);
        } else if (e.key === "Escape") {
            e.stopPropagation();
            closeSuggest();
        }
    });
}

// The list scrolls with the modal; close it rather than leave it floating in the wrong spot
document.addEventListener("scroll", (e) => { if (e.target !== suggestBox) closeSuggest(); }, true);

// Route name: pick a place -> "<place> - Hadi Chattar", and start the route there if it has no stops yet
attachPlaceSuggest(document.getElementById("route-name"), (place) => {
    document.getElementById("route-name").value = `${place.name} - ${ADMIN_DATA.destination.stop_name}`;
    showFormError("route-form-error", "");
    if (!editPoints.length) {
        editPoints.push({ lat: place.lat, lng: place.lng, name: "" });
        routeChanged();
        routeMap?.fitBounds([[place.lat, place.lng], destLatLng()], { padding: [30, 30] });
    }
});

function openRouteModal(routeId) {
    showFormError("route-form-error", "");
    const route = routeId ? ADMIN_DATA.routes.find(r => r.route_id === routeId) : null;
    document.getElementById("route-modal-title").textContent = route ? `Edit ${route.route_name}` : "Add Route";
    document.getElementById("route-submit-btn").textContent = route ? "Save" : "Add Route";
    document.getElementById("route-id").value = route ? route.route_id : "";
    document.getElementById("route-name").value = route ? route.route_name : "";
    document.getElementById("route-color").value = route ? route.color_hex.toLowerCase() : "#2563eb";
    editPoints = route ? (route.via_points || []).map(p => ({ lat: p.lat, lng: p.lng, name: p.name || "" })) : [];
    // Keep the saved road line until something is changed
    roadPath = route && route.polyline_waypoints?.length > 1 ? route.polyline_waypoints.map(w => [w.lat, w.lng]) : null;
    roadIsFresh = false;
    openModal("modal-route");
    setTimeout(() => {
        ensureRouteMap();
        routeMap.invalidateSize();
        drawRoute();
        const pts = (roadPath || editPoints.map(p => [p.lat, p.lng])).concat([destLatLng()]);
        if (pts.length > 1) routeMap.fitBounds(pts, { padding: [30, 30] });
        else routeMap.setView(destLatLng(), 13);
        document.getElementById("route-name").focus();
    }, 60);
}

document.getElementById("form-route").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("route-id").value;
    const name = document.getElementById("route-name").value.trim();
    if (!name) { showFormError("route-form-error", "Give the route a name."); return; }
    if (!editPoints.length) { showFormError("route-form-error", "Click the map to draw the route."); return; }
    const payload = {
        route_name: name,
        color_hex: routeColor(),
        points: editPoints.map(p => ({ lat: p.lat, lng: p.lng, name: p.name || "" })),
        path: roadPath
    };
    const { ok, data } = await api(id ? "PUT" : "POST", id ? `/api/admin/routes/${encodeURIComponent(id)}` : "/api/admin/routes", payload);
    if (ok) location.reload();
    else showFormError("route-form-error", data.message || "Could not save the route.");
});

async function deleteRoute(routeId, name) {
    if (!confirm(`Remove route "${name}"?`)) return;
    const { ok, data } = await api("DELETE", `/api/admin/routes/${encodeURIComponent(routeId)}`);
    if (ok) location.reload(); else toast(data.message || "Could not remove the route.", true);
}

// ---------- Buses ----------
async function changeBusRoute(select) {
    const busId = select.dataset.busId;
    const previous = select.dataset.current;
    const { ok, data } = await api("PUT", `/api/admin/buses/${encodeURIComponent(busId)}`, { assigned_route_id: select.value });
    if (ok) {
        select.dataset.current = select.value;
        toast(`${data.bus.bus_number} → ${select.selectedOptions[0].textContent}. Its driver has been notified.`);
    } else {
        select.value = previous;
        toast(data.message || "Could not change the route.", true);
    }
}

async function changeBusAudience(select) {
    const previous = select.dataset.current;
    const { ok, data } = await api("PUT", `/api/admin/buses/${encodeURIComponent(select.dataset.busId)}`, { audience: select.value });
    if (ok) {
        select.dataset.current = select.value;
        select.className = `inline-audience-select audience-${select.value}`;
        toast(`${data.bus.bus_number} is now a ${select.value === "teacher" ? "teacher" : "student"} bus.`);
    } else {
        select.value = previous;
        toast(data.message || "Could not change it.", true);
    }
}

async function simulateBus(busId, isLive) {
    const { ok, data } = await api("POST", `/api/admin/buses/${encodeURIComponent(busId)}/simulate`, { action: isLive ? "stop" : "start" });
    if (ok) location.reload(); else toast(data.message || "Could not start the test drive.", true);
}

const busColorInput = document.getElementById("bus-color");
const busSwatches = document.querySelectorAll("#bus-color-swatches .color-swatch-btn");
function selectBusColor(color) {
    busColorInput.value = color.toLowerCase();
    busSwatches.forEach(b => b.classList.toggle("selected", b.dataset.color.toLowerCase() === color.toLowerCase()));
}
busSwatches.forEach(b => b.addEventListener("click", () => selectBusColor(b.dataset.color)));
busColorInput.addEventListener("input", () => selectBusColor(busColorInput.value));

function openBusModal(bus) {
    showFormError("bus-form-error", "");
    const editing = !!bus;
    document.getElementById("bus-modal-title").textContent = editing ? `Edit ${bus.bus_number}` : "Add Bus";
    document.getElementById("bus-submit-btn").textContent = editing ? "Save" : "Add Bus";
    document.getElementById("bus-id").value = editing ? bus.bus_id : "";
    document.getElementById("bus-number").value = editing ? bus.bus_number : "";
    document.getElementById("bus-name").value = editing ? bus.bus_name : "";
    document.getElementById("bus-plate").value = editing ? (bus.license_plate || "") : "";
    document.getElementById("bus-capacity").value = editing ? bus.capacity : 52;
    if (editing) document.getElementById("bus-route-id").value = bus.assigned_route_id;
    const aud = editing && bus.audience === "teacher" ? "teacher" : "student";
    document.querySelectorAll('input[name="bus-audience"]').forEach(r => { r.checked = r.value === aud; });
    const used = new Set(ADMIN_DATA.buses.map(b => (b.color_hex || "").toUpperCase()));
    const free = Array.from(busSwatches).map(b => b.dataset.color).find(c => !used.has(c.toUpperCase()));
    selectBusColor(editing ? bus.color_hex : (free || "#E11D48"));
    openModal("modal-bus");
    setTimeout(() => document.getElementById("bus-number").focus(), 50);
}

document.getElementById("form-bus").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("bus-id").value;
    const payload = {
        bus_number: document.getElementById("bus-number").value.trim(),
        bus_name: document.getElementById("bus-name").value.trim(),
        license_plate: document.getElementById("bus-plate").value.trim(),
        capacity: document.getElementById("bus-capacity").value,
        assigned_route_id: document.getElementById("bus-route-id").value,
        audience: document.querySelector('input[name="bus-audience"]:checked')?.value || "student",
        color_hex: busColorInput.value
    };
    const { ok, data } = await api(id ? "PUT" : "POST", id ? `/api/admin/buses/${encodeURIComponent(id)}` : "/api/admin/buses", payload);
    if (ok) location.reload();
    else showFormError("bus-form-error", data.message || "Could not save the bus.");
});

async function deleteBus(busId, busNumber) {
    if (!confirm(`Delete ${busNumber}? Students will no longer see it.`)) return;
    const { ok, data } = await api("DELETE", `/api/admin/buses/${encodeURIComponent(busId)}`);
    if (ok) location.reload(); else toast(data.message || "Could not delete the bus.", true);
}

// Show saved UTC times (Users tab) in the admin's local time.
document.querySelectorAll("time.local-time").forEach(el => {
    const when = new Date(el.getAttribute("datetime"));
    if (!isNaN(when)) el.textContent = when.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
});
