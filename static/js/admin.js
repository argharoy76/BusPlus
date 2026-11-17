/* Backend admin panel (/backend): GPS devices, routes (map editor), buses, schedules, live map. */

// Words of this page: content/words/backend.py (AT(original) gives the text shown)
const AT = words("backend");

// Data the page was rendered with (routes, buses, final destination)
const ADMIN_DATA = JSON.parse(document.getElementById("admin-data").textContent);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------- Shared helpers ----------
/** Shows one tab (Live map, GPS devices, Routes, Buses, ...) and remembers it for the next reload. */
function switchTab(tabName) {
    const tab = document.getElementById(`tab-${tabName}`);
    const nav = document.getElementById(`nav-${tabName}`);
    if (!tab || !nav) return;
    document.querySelectorAll(".tab-section").forEach(s => s.classList.remove("active"));
    document.querySelectorAll(".admin-nav-item").forEach(n => n.classList.remove("active"));
    tab.classList.add("active");
    nav.classList.add("active");
    if (tabName === "live") startLiveMap();
    if (tabName === "devices") refreshDevices();
    try { sessionStorage.setItem("busplus_admin_tab", tabName); } catch (e) { /* storage blocked */ }
}
try {
    const savedTab = sessionStorage.getItem("busplus_admin_tab");
    if (savedTab) switchTab(savedTab);
} catch (e) {}

/** Opens a pop-up form by its id. */
function openModal(id) { document.getElementById(id).classList.add("active"); }
/** Closes a pop-up form (and any open place suggestions). */
function closeModal(id) {
    document.getElementById(id).classList.remove("active");
    if (typeof closeSuggest === "function") closeSuggest();
}
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.querySelectorAll(".modal-overlay.active").forEach(m => m.classList.remove("active"));
});

/** Shows a red message inside a form (empty message hides it). */
function showFormError(id, message) {
    const box = document.getElementById(id);
    box.textContent = message || "";
    box.style.display = message ? "block" : "none";
}

let toastTimer = null;
/** Short message at the bottom of the screen (red when isError). */
function toast(message, isError = false) {
    const t = document.getElementById("admin-toast");
    t.textContent = message;
    t.classList.toggle("error", !!isError);
    t.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove("show"), 2600);
}

/** Sends JSON to the server and returns its reply; a server error becomes a readable message. */
async function api(method, url, body) {
    const resp = await fetch(url, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined
    });
    if (resp.status === 401) {
        window.location.href = "/backend/login";
        throw new Error("signed out");
    }
    const data = await resp.json().catch(() => ({}));
    return { ok: resp.ok && data.success !== false, data };
}

// ---------- GPS devices (ESP32 + NEO-6M tracker boxes) ----------
// The tab has three parts: "Add a device" (manually / automatically), the counts, and the
// connected devices. Everything is refreshed from /api/admin/devices every few seconds.
let gpsDevices = ADMIN_DATA.devices || [];
let waitingBoxes = [];
let nextFreeBus = null;
let serverOffset = (ADMIN_DATA.server_now || Date.now() / 1000) - Date.now() / 1000;   // server clock - this clock
const DEVICE_REFRESH_MS = 5000;
const busById = Object.fromEntries(ADMIN_DATA.buses.map(b => [b.bus_id, b]));

/** What the Status column says for each device status (models/device.py). */
function deviceStatusText(status) {
    return {
        online: AT("Sending GPS"),
        no_fix: AT("Searching for satellites"),
        offline: AT("Offline"),
        never: AT("Never connected")
    }[status] || status;
}

/** "now", "12 s ago", "3 min ago", "2 h ago" for a server timestamp (seconds). */
function agoText(ts) {
    if (!ts) return "—";
    const age = Math.max(0, Math.round(Date.now() / 1000 + serverOffset - ts));
    if (age < 5) return AT("now");
    if (age < 120) return AT("{seconds} s ago", { seconds: age });
    if (age < 7200) return AT("{minutes} min ago", { minutes: Math.round(age / 60) });
    return AT("{hours} h ago", { hours: Math.round(age / 3600) });
}

/** <option>s of every bus for a "Fitted to bus" list; buses that already have a device say so. */
function deviceBusOptions(selected, exceptDeviceId = null) {
    const taken = Object.fromEntries(gpsDevices.filter(d => d.bus_id && d.device_id !== exceptDeviceId).map(d => [d.bus_id, d]));
    return `<option value="">${esc(AT("Not fitted to a bus"))}</option>` + ADMIN_DATA.buses.map(b => {
        const other = taken[b.bus_id];
        const label = other ? AT("{bus} (has {device})", { bus: b.bus_number, device: other.name }) : `${b.bus_number} · ${b.bus_name}`;
        return `<option value="${esc(b.bus_id)}" ${b.bus_id === selected ? "selected" : ""} ${other ? "disabled" : ""}>${esc(label)}</option>`;
    }).join("");
}

/** Counts, the connected devices table, the boxes asking to join and the quick-add hint. */
function renderDevices() {
    const rows = document.getElementById("device-rows");
    if (!rows) return;
    const setText = (id, value) => { const el = document.getElementById(id); if (el) el.textContent = value; };
    const fitted = new Set(gpsDevices.map(d => d.bus_id).filter(Boolean));
    setText("stat-devices", gpsDevices.length);
    setText("stat-devices-online", gpsDevices.filter(d => d.status === "online").length);
    setText("stat-devices-hidden", gpsDevices.filter(d => !d.show_on_map).length);
    setText("stat-devices-waiting", waitingBoxes.length);
    setText("stat-buses-bare", ADMIN_DATA.buses.filter(b => !fitted.has(b.bus_id)).length);
    for (const id of ["nav-waiting-count", "waiting-count-badge"]) {
        const badge = document.getElementById(id);
        if (badge) { badge.textContent = waitingBoxes.length; badge.hidden = !waitingBoxes.length; }
    }

    if (!gpsDevices.length) {
        rows.innerHTML = `<tr><td colspan="6" class="empty-row">${esc(AT("No GPS devices yet."))}</td></tr>`;
    } else {
        rows.innerHTML = gpsDevices.map(d => {
            const bus = busById[d.bus_id];
            const gps = d.satellites == null ? "—"
                : AT("{count} satellites", { count: d.satellites }) + (d.hdop != null ? " · " + AT("HDOP {hdop}", { hdop: d.hdop }) : "");
            const power = [d.rssi_dbm != null ? `${d.rssi_dbm} dBm` : "", d.battery_v != null ? `${d.battery_v} V` : ""].filter(Boolean).join(" · ") || "—";
            const details = [d.device_id, AT("key …{hint}", { hint: d.key_hint }),
                d.chip_id ? AT("chip {chip}", { chip: d.chip_id }) : "",
                d.firmware ? AT("firmware {version}", { version: d.firmware }) : ""].filter(Boolean).join(" · ");
            const canView = d.show_on_map && bus && d.status === "online";
            return `<tr class="${d.show_on_map ? "" : "row-muted"}">
                <td class="col-device">
                    <div class="cell-title">${esc(d.name)}</div>
                    <div class="cell-sub">${esc(details)}</div>
                </td>
                <td>${bus ? `<span class="bus-tag" style="--bus-color:${esc(bus.color_hex)}">${esc(bus.bus_number)}</span>`
                          : `<span class="muted">${esc(AT("Not fitted to a bus"))}</span>`}</td>
                <td>
                    <span class="status-pill status-${esc(d.status)}">${esc(deviceStatusText(d.status))}</span>
                    <div class="cell-sub">${esc(AT("Last report {ago}", { ago: agoText(d.last_seen_ts) }))}</div>
                </td>
                <td class="nowrap">
                    <div>${esc(gps)}</div>
                    <div class="cell-sub">${esc(power)}</div>
                </td>
                <td>
                    <div class="map-cell">
                        <span class="status-pill ${d.show_on_map ? "status-on-map" : "status-off-map"}">${esc(d.show_on_map ? AT("On the map") : AT("Off the map"))}</span>
                        <button class="btn btn-secondary btn-sm" data-device-action="map" data-device-id="${esc(d.device_id)}" ${bus ? "" : "disabled"}>${esc(d.show_on_map ? AT("Remove from map") : AT("Show on map"))}</button>
                    </div>
                </td>
                <td class="col-actions">
                    <div class="row-actions">
                        ${canView ? `<button class="btn btn-secondary btn-sm" data-device-action="view" data-device-id="${esc(d.device_id)}">${esc(AT("View live"))}</button>` : ""}
                        <button class="btn btn-secondary btn-sm" data-device-action="edit" data-device-id="${esc(d.device_id)}">${esc(AT("Edit"))}</button>
                        <button class="btn btn-secondary btn-sm" data-device-action="key" data-device-id="${esc(d.device_id)}" title="${esc(AT("Make a new key (the old one stops working)"))}">${esc(AT("New key"))}</button>
                        <button class="btn btn-secondary btn-sm btn-danger-text" data-device-action="delete" data-device-id="${esc(d.device_id)}">${esc(AT("Delete"))}</button>
                    </div>
                </td>
            </tr>`;
        }).join("");
    }
    renderWaitingBoxes();
}

/**
 * The boxes asking to join. Rows are kept (not redrawn) while they stay in the list,
 * so a name the admin is typing isn't wiped by the refresh every few seconds.
 */
function renderWaitingBoxes() {
    const body = document.getElementById("waiting-rows");
    if (!body) return;
    const emptyRow = body.querySelector(".waiting-empty");
    if (!waitingBoxes.length) {
        if (!emptyRow) body.innerHTML = `<tr class="waiting-empty"><td colspan="6" class="empty-row">${esc(AT("No box is waiting."))}</td></tr>`;
        return;
    }
    emptyRow?.remove();
    const wanted = new Set(waitingBoxes.map(w => w.chip_id));
    body.querySelectorAll("tr[data-chip]").forEach(tr => { if (!wanted.has(tr.dataset.chip)) tr.remove(); });
    for (const box of waitingBoxes) {
        let tr = body.querySelector(`tr[data-chip="${CSS.escape(box.chip_id)}"]`);
        if (!tr) {
            tr = document.createElement("tr");
            tr.dataset.chip = box.chip_id;
            const suggestedBus = box.known_device_id ? (gpsDevices.find(d => d.device_id === box.known_device_id)?.bus_id || "") : (nextFreeBus || "");
            tr.innerHTML = `
                <td>
                    <div class="cell-title mono">${esc(box.chip_id)}</div>
                    <div class="cell-sub waiting-sub"></div>
                </td>
                <td><span class="pair-code">${esc(box.code)}</span></td>
                <td class="nowrap waiting-asked"></td>
                <td><input type="text" class="custom-input input-sm waiting-name" maxlength="60" placeholder="${esc(AT("Made for you if empty"))}" value="${esc(box.known_device_name || "")}"></td>
                <td><select class="custom-select input-sm waiting-bus">${deviceBusOptions(suggestedBus, box.known_device_id)}</select></td>
                <td style="text-align:right;">
                    <div class="row-actions">
                        <button class="btn btn-primary btn-sm" data-waiting-action="approve">${esc(AT("Approve"))}</button>
                        <button class="btn btn-secondary btn-sm btn-danger-text" data-waiting-action="reject">${esc(AT("Reject"))}</button>
                    </div>
                </td>`;
            body.appendChild(tr);
        }
        const sub = [box.ip, box.firmware ? AT("firmware {version}", { version: box.firmware }) : "",
            box.known_device_name ? AT("joined before as {name}", { name: box.known_device_name }) : ""].filter(Boolean).join(" · ");
        tr.querySelector(".waiting-sub").textContent = sub;
        tr.querySelector(".waiting-asked").textContent = agoText(box.first_seen);
    }
}

document.getElementById("device-rows")?.addEventListener("click", (e) => {
    const button = e.target.closest("[data-device-action]");
    if (!button) return;
    const device = gpsDevices.find(d => d.device_id === button.dataset.deviceId);
    if (!device) return;
    const action = button.dataset.deviceAction;
    if (action === "edit") openDeviceModal(device);
    else if (action === "key") renewDeviceKey(device);
    else if (action === "delete") deleteDevice(device);
    else if (action === "map") setDeviceOnMap(device, !device.show_on_map, button);
    else if (action === "view") viewDeviceLive(device);
});

document.getElementById("waiting-rows")?.addEventListener("click", async (e) => {
    const button = e.target.closest("[data-waiting-action]");
    const tr = button?.closest("tr[data-chip]");
    if (!tr) return;
    const chip = tr.dataset.chip;
    const url = `/api/admin/devices/waiting/${encodeURIComponent(chip)}/${button.dataset.waitingAction}`;
    if (button.dataset.waitingAction === "reject") {
        if (!confirm(AT("Reject box {chip}? It is ignored for an hour.", { chip }))) return;
        button.disabled = true;
        const { ok, data } = await api("POST", url);
        toast(data.message || (ok ? "" : AT("Something went wrong.")), !ok);
    } else {
        button.disabled = true;
        const { ok, data } = await api("POST", url, {
            name: tr.querySelector(".waiting-name").value.trim(),
            bus_id: tr.querySelector(".waiting-bus").value
        });
        toast(data.message || (ok ? "" : AT("Something went wrong.")), !ok);
        if (ok) document.getElementById("waiting-rows").innerHTML = "";   // rebuild: the free buses changed
    }
    button.disabled = false;
    refreshDevices(true);
});

/** Asks the server for the devices' latest reports and waiting boxes (only while their tab is open). */
async function refreshDevices(force = false) {
    if (!force && !document.getElementById("tab-devices")?.classList.contains("active")) return;
    try {
        const { ok, data } = await api("GET", "/api/admin/devices");
        if (ok) {
            gpsDevices = data.devices || [];
            waitingBoxes = data.waiting || [];
            nextFreeBus = data.next_free_bus || null;
            if (data.now) serverOffset = data.now - Date.now() / 1000;
        }
    } catch (e) { /* offline for a moment: keep the last list */ }
    renderDevices();
}
renderDevices();
refreshDevices(true);
setInterval(refreshDevices, DEVICE_REFRESH_MS);

// "Manually" / "Automatically"
document.querySelectorAll("[data-add-mode]").forEach(btn => btn.addEventListener("click", () => {
    document.querySelectorAll("[data-add-mode]").forEach(b => {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-selected", String(b === btn));
    });
    document.getElementById("add-mode-manual").hidden = btn.dataset.addMode !== "manual";
    document.getElementById("add-mode-auto").hidden = btn.dataset.addMode !== "auto";
}));

/** The manual form starts on the first bus without a device. */
function resetAddDeviceForm() {
    const fitted = new Set(gpsDevices.map(d => d.bus_id));
    const free = ADMIN_DATA.buses.find(b => !fitted.has(b.bus_id));
    document.getElementById("add-device-name").value = "";
    document.getElementById("add-device-bus").value = free ? free.bus_id : "";
    showFormError("add-device-error", "");
}
resetAddDeviceForm();

document.getElementById("form-add-device").addEventListener("submit", async (e) => {
    e.preventDefault();
    const name = document.getElementById("add-device-name").value.trim();
    if (!name) {
        showFormError("add-device-error", AT("Give the device a name."));
        return;
    }
    const { ok, data } = await api("POST", "/api/admin/devices", { name, bus_id: document.getElementById("add-device-bus").value });
    if (!ok) {
        showFormError("add-device-error", data.message || AT("Could not save the device."));
        return;
    }
    resetAddDeviceForm();
    showDeviceSettings(data.device, data.settings);
    refreshDevices(true);
});

document.getElementById("quick-add-btn").addEventListener("click", async (e) => {
    e.currentTarget.disabled = true;
    const { ok, data } = await api("POST", "/api/admin/devices/quick");
    e.currentTarget.disabled = false;
    if (!ok) { toast(data.message || AT("Could not save the device."), true); return; }
    showDeviceSettings(data.device, data.settings);
    refreshDevices(true);
});

/** Puts a device's bus on every map, or takes it off (the box stays connected). */
async function setDeviceOnMap(device, show, button) {
    if (!show && !confirm(AT("Remove {name} from the map? Its bus disappears from every map until you show it again.", { name: device.name }))) return;
    button.disabled = true;
    const { ok, data } = await api("PUT", `/api/admin/devices/${encodeURIComponent(device.device_id)}/map`, { show });
    toast(data.message || (ok ? "" : AT("Something went wrong.")), !ok);
    refreshDevices(true);
}

/** Opens the Live map on this device's bus. */
function viewDeviceLive(device) {
    switchTab("live");
    const helper = window.googleMapsHelper;
    let tries = 0;
    const focus = () => {
        const bus = window.adminLive?.buses.get(device.bus_id);
        if (bus && bus.is_active) helper.fitToPoints([[bus.current_latitude, bus.current_longitude]], 24);
        else if (++tries < 20) setTimeout(focus, 250);
    };
    focus();
}

/** Opens the Edit device form. */
function openDeviceModal(device) {
    showFormError("device-form-error", "");
    document.getElementById("device-modal-title").textContent = AT("Edit {name}", { name: device.name });
    document.getElementById("device-id").value = device.device_id;
    document.getElementById("device-name").value = device.name;
    document.getElementById("device-bus").value = device.bus_id || "";
    openModal("modal-device");
    setTimeout(() => document.getElementById("device-name").focus(), 50);
}

document.getElementById("form-device").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("device-id").value;
    const payload = {
        name: document.getElementById("device-name").value.trim(),
        bus_id: document.getElementById("device-bus").value
    };
    const { ok, data } = await api("PUT", `/api/admin/devices/${encodeURIComponent(id)}`, payload);
    if (!ok) {
        showFormError("device-form-error", data.message || AT("Could not save the device."));
        return;
    }
    closeModal("modal-device");
    location.reload();
});

/** Makes a new key for a device (after asking) and shows it. */
async function renewDeviceKey(device) {
    if (!confirm(AT("Make a new key for {name}? The old key stops working at once, so the device must be updated.", { name: device.name }))) return;
    const { ok, data } = await api("POST", `/api/admin/devices/${encodeURIComponent(device.device_id)}/key`);
    if (ok) showDeviceSettings(data.device, data.settings);
    else toast(data.message || AT("Something went wrong."), true);
}

/** Deletes a device after asking to confirm. */
async function deleteDevice(device) {
    if (!confirm(AT("Delete {name}? Its key stops working and its bus goes offline.", { name: device.name }))) return;
    const { ok, data } = await api("DELETE", `/api/admin/devices/${encodeURIComponent(device.device_id)}`);
    if (ok) location.reload(); else toast(data.message || AT("Could not delete the device."), true);
}

/** The settings for the device's firmware: server URL, its key and a ready secrets.h. Shown once. */
function showDeviceSettings(device, settings) {
    const url = settings.lan_url || settings.server_url;
    document.getElementById("device-key-title").textContent = AT("Device settings · {name}", { name: device.name });
    document.getElementById("device-url").textContent = url;
    document.getElementById("device-key").textContent = settings.key;
    const lanNote = document.getElementById("device-lan-note");
    lanNote.hidden = !settings.lan_url;
    lanNote.textContent = settings.lan_url
        ? AT("This computer calls itself \"localhost\", which the ESP32 can't reach, so its network address is used instead. Start BusPlus with HOST=0.0.0.0 so the ESP32 can connect (see firmware/README.md).")
        : "";
    document.getElementById("device-secrets").textContent = [
        `// BusPlus GPS box: ${device.name} (${device.device_id})`,
        `#define WIFI_SSID      "your-wifi-name"`,
        `#define WIFI_PASSWORD  "your-wifi-password"`,
        `#define SERVER_URL     "${url}"`,
        `#define DEVICE_KEY     "${settings.key}"`
    ].join("\n");
    if (settings.key) toast(AT("Device saved. Copy its key now."));
    openModal("modal-device-key");
}

/** Copies the text of an element (URL, key, secrets.h) to the clipboard. */
async function copyText(elementId) {
    const text = document.getElementById(elementId).textContent;
    try {
        await navigator.clipboard.writeText(text);
        toast(AT("Copied"));
    } catch (e) {
        toast(text);
    }
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

/** The colour chosen in the route form. */
function routeColor() { return document.getElementById("route-color").value; }
/** Position of the final stop that every route ends at. */
function destLatLng() { return [ADMIN_DATA.destination.latitude, ADMIN_DATA.destination.longitude]; }

/** Creates the route editor's map the first time it is needed. */
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

/** The admin moved or added a point: fetch a new road line shortly after. */
function routeChanged() {
    drawRoute();
    clearTimeout(roadTimer);
    roadTimer = setTimeout(fetchRoadPath, 250);
}

// Ask the road map for the driving route through the points and on to Hadi Chattar
/** Asks the server (OSRM road router) for the road line through the points. */
async function fetchRoadPath() {
    const id = ++roadRequest;
    if (!editPoints.length) { roadPath = null; drawRoute(); return; }
    const coords = editPoints.map(p => [p.lat, p.lng]).concat([destLatLng()]);
    setRouteInfo(AT("Finding the roads…"));
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

/** Length of a line of points in km. */
function lengthKm(pts) {
    let km = 0;
    for (let i = 1; i < pts.length; i++) {
        const [a, b] = pts[i - 1], [c, d] = pts[i];
        const r = Math.PI / 180, x = (d - b) * r * Math.cos((a + c) / 2 * r), y = (c - a) * r;
        km += Math.sqrt(x * x + y * y) * 6371;
    }
    return km;
}

/** Status line under the route editor map (length, or a warning). */
function setRouteInfo(text, warn = false) {
    const el = document.getElementById("route-info");
    el.textContent = text;
    el.classList.toggle("warn", warn);
}

/** Draws the route's points and its road line (or straight lines if the road router failed). */
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
        m.bindTooltip(i === 0 ? AT("Start · drag to move, double-click to remove") : AT("Drag to move, double-click to remove"));
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
        icon: L.divIcon({ className: "route-dest-marker", html: `<div>${esc(ADMIN_DATA.destination.stop_name)}</div>`, iconSize: [110, 22], iconAnchor: [12, 22] })
    }).addTo(routeLayer);

    if (!editPoints.length) setRouteInfo(AT("Click the map where the route starts."));
    else if (roadFailed) setRouteInfo(AT("Couldn't reach the road map, so the line is drawn straight. It will still save."), true);
    else if (roadPath) setRouteInfo(roadIsFresh
        ? AT("{km} km along the roads", { km: lengthKm(roadPath).toFixed(1) })
        : AT("{km} km", { km: lengthKm(roadPath).toFixed(1) }));
}

document.getElementById("route-color").addEventListener("input", () => drawRoute());
document.getElementById("route-undo").addEventListener("click", () => { editPoints.pop(); routeChanged(); });
document.getElementById("route-clear").addEventListener("click", () => {
    if (editPoints.length && !confirm(AT("Remove all points of this route?"))) return;
    editPoints = [];
    routeChanged();
});
document.getElementById("route-name").addEventListener("input", () => showFormError("route-form-error", ""));

// ---------- Place-name suggestions ----------
// Every stop the app knows (all routes), except the final destination
/** Every named stop of every route (for the place suggestions). */
function knownPlaces() {
    const seen = new Map();
    const dest = ADMIN_DATA.destination.stop_name.toLowerCase();
    ADMIN_DATA.routes.forEach(r => (r.stops || []).forEach(st => {
        const key = st.stop_name.toLowerCase();
        if (key !== dest && !seen.has(key)) seen.set(key, { name: st.stop_name, lat: st.latitude, lng: st.longitude });
    }));
    return Array.from(seen.values());
}

/** Known places matching the typed text, best first. */
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

/** Hides the place suggestion list. */
function closeSuggest() {
    suggestBox.classList.remove("open");
    suggestBox.innerHTML = "";
    suggestFor = null;
}

/** Shows place suggestions under a text box. */
function showSuggest(input, onPick) {
    const items = matchPlaces(input.value);
    if (!items.length) { closeSuggest(); return; }
    const q = input.value.trim();
    suggestBox.innerHTML = items.map((p, i) => {
        const n = p.name, at = n.toLowerCase().indexOf(q.toLowerCase());
        const label = at < 0 ? esc(n) : esc(n.slice(0, at)) + "<mark>" + esc(n.slice(at, at + q.length)) + "</mark>" + esc(n.slice(at + q.length));
        return `<div class="place-option" role="option" data-i="${i}"><span>${label}</span></div>`;
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

/** Uses the chosen suggestion. */
function pickSuggest(i) {
    if (!suggestFor) return;
    const { onPick, items } = suggestFor;
    const place = items[i];
    closeSuggest();
    if (place) onPick(place);
}

/** Adds type-ahead place suggestions to a text box. */
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

/** Opens the Add / Edit route form with its map editor. */
function openRouteModal(routeId) {
    showFormError("route-form-error", "");
    const route = routeId ? ADMIN_DATA.routes.find(r => r.route_id === routeId) : null;
    document.getElementById("route-modal-title").textContent = route ? AT("Edit {name}", { name: route.route_name }) : AT("Add route");
    document.getElementById("route-submit-btn").textContent = route ? AT("Save") : AT("Add route");
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
    if (!name) { showFormError("route-form-error", AT("Give the route a name.")); return; }
    if (!editPoints.length) { showFormError("route-form-error", AT("Click the map to draw the route.")); return; }
    const payload = {
        route_name: name,
        color_hex: routeColor(),
        points: editPoints.map(p => ({ lat: p.lat, lng: p.lng, name: p.name || "" })),
        path: roadPath
    };
    const { ok, data } = await api(id ? "PUT" : "POST", id ? `/api/admin/routes/${encodeURIComponent(id)}` : "/api/admin/routes", payload);
    if (ok) location.reload();
    else showFormError("route-form-error", data.message || AT("Could not save the route."));
});

/** Deletes a route after asking to confirm. */
async function deleteRoute(routeId, name) {
    if (!confirm(AT("Remove the route {name}?", { name }))) return;
    const { ok, data } = await api("DELETE", `/api/admin/routes/${encodeURIComponent(routeId)}`);
    if (ok) location.reload(); else toast(data.message || AT("Could not remove the route."), true);
}

// ---------- Buses ----------
/** Bus table: sends a bus on another route today. */
async function changeBusRoute(select) {
    const busId = select.dataset.busId;
    const previous = select.dataset.current;
    const { ok, data } = await api("PUT", `/api/admin/buses/${encodeURIComponent(busId)}`, { assigned_route_id: select.value });
    if (ok) {
        select.dataset.current = select.value;
        toast(AT("{bus} now drives {route}.", { bus: data.bus.bus_number, route: select.selectedOptions[0].textContent }));
    } else {
        select.value = previous;
        toast(data.message || AT("Could not change the route."), true);
    }
}

/** Bus table: changes who a bus is for (students, teachers, ...). */
async function changeBusAudience(select) {
    const previous = select.dataset.current;
    const { ok, data } = await api("PUT", `/api/admin/buses/${encodeURIComponent(select.dataset.busId)}`, { audience: select.value });
    if (ok) {
        select.dataset.current = select.value;
        const rider = ADMIN_DATA.rider_types[select.value];
        select.style.setProperty("--aud-color", rider.color);
        toast(AT("{bus} is now a bus for {group}.", { bus: data.bus.bus_number, group: rider.plural.toLowerCase() }));
    } else {
        select.value = previous;
        toast(data.message || AT("Could not change it."), true);
    }
}

/** Starts or stops a test drive of a bus along its route. */
async function simulateBus(busId, isLive) {
    const { ok, data } = await api("POST", `/api/admin/buses/${encodeURIComponent(busId)}/simulate`, { action: isLive ? "stop" : "start" });
    if (ok) location.reload(); else toast(data.message || AT("Could not start the test drive."), true);
}

const busColorInput = document.getElementById("bus-color");
const busSwatches = document.querySelectorAll("#bus-color-swatches .color-swatch-btn");
/** Picks a colour in the bus form. */
function selectBusColor(color) {
    busColorInput.value = color.toLowerCase();
    busSwatches.forEach(b => b.classList.toggle("selected", b.dataset.color.toLowerCase() === color.toLowerCase()));
}
busSwatches.forEach(b => b.addEventListener("click", () => selectBusColor(b.dataset.color)));
busColorInput.addEventListener("input", () => selectBusColor(busColorInput.value));

/** Opens the Add / Edit bus form (filled in when a bus is given). */
function openBusModal(bus) {
    showFormError("bus-form-error", "");
    const editing = !!bus;
    document.getElementById("bus-modal-title").textContent = editing ? AT("Edit {name}", { name: bus.bus_number }) : AT("Add bus");
    document.getElementById("bus-submit-btn").textContent = editing ? AT("Save") : AT("Add bus");
    document.getElementById("bus-id").value = editing ? bus.bus_id : "";
    document.getElementById("bus-number").value = editing ? bus.bus_number : "";
    document.getElementById("bus-name").value = editing ? bus.bus_name : "";
    document.getElementById("bus-plate").value = editing ? (bus.license_plate || "") : "";
    document.getElementById("bus-capacity").value = editing ? bus.capacity : ADMIN_DATA.default_bus_seats;
    if (editing) document.getElementById("bus-route-id").value = bus.assigned_route_id;
    const firstType = ADMIN_DATA.default_rider_type;
    const aud = editing && ADMIN_DATA.rider_types[bus.audience] ? bus.audience : firstType;
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
        audience: document.querySelector('input[name="bus-audience"]:checked')?.value,
        color_hex: busColorInput.value
    };
    const { ok, data } = await api(id ? "PUT" : "POST", id ? `/api/admin/buses/${encodeURIComponent(id)}` : "/api/admin/buses", payload);
    if (ok) location.reload();
    else showFormError("bus-form-error", data.message || AT("Could not save the bus."));
});

/** Deletes a bus after asking to confirm. */
async function deleteBus(busId, busNumber) {
    if (!confirm(AT("Delete {bus}? Nobody will see it on the map any more.", { bus: busNumber }))) return;
    const { ok, data } = await api("DELETE", `/api/admin/buses/${encodeURIComponent(busId)}`);
    if (ok) location.reload(); else toast(data.message || AT("Could not delete the bus."), true);
}

// Show saved UTC times (Users tab) in the admin's local time.
document.querySelectorAll("time.local-time").forEach(el => {
    const when = new Date(el.getAttribute("datetime"));
    if (!isNaN(when)) el.textContent = when.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
});

// ---------- Schedules (one weekly timetable per route) ----------
// The modal edits a copy of the route's week (scheduleWeek) one day at a time; Save sends the whole week.
let scheduleRouteId = null;
let scheduleWeek = null;
let scheduleDay = null;

/** <option>s for the bus picker: buses on this route first, then the other buses. */
function busOptions(routeId, selected) {
    const group = (label, buses) => buses.length
        ? `<optgroup label="${esc(label)}">${buses.map(b =>
            `<option value="${esc(b.bus_id)}" ${b.bus_id === selected ? "selected" : ""}>${esc(b.bus_name)} · ${esc(b.bus_number)}</option>`).join("")}</optgroup>`
        : "";
    const onRoute = ADMIN_DATA.buses.filter(b => b.assigned_route_id === routeId);
    const others = ADMIN_DATA.buses.filter(b => b.assigned_route_id !== routeId);
    return `<option value="">${esc(AT("— Choose bus —"))}</option>${group(AT("On this route"), onRoute)}${group(AT("Other buses"), others)}`;
}

/** Reads the rows on screen back into scheduleWeek for the day being edited. */
function storeScheduleDay() {
    if (!scheduleDay) return;
    ["morning", "afternoon"].forEach(part => {
        scheduleWeek[scheduleDay][part] = Array.from(document.querySelectorAll(`#trips-${part} .trip-row`))
            .map(row => ({ bus_id: row.querySelector(".trip-bus").value, time: row.querySelector(".trip-time").value }))
            .filter(t => t.bus_id || t.time);
    });
}

/** Adds one trip row (bus + time) to the morning or afternoon list in the schedule form. */
function addTripRow(part, trip = { bus_id: "", time: "" }) {
    const row = document.createElement("div");
    row.className = "trip-row";
    row.innerHTML = `
        <select class="custom-select trip-bus" aria-label="${esc(AT("Bus"))}">${busOptions(scheduleRouteId, trip.bus_id)}</select>
        <input type="time" class="custom-input trip-time" aria-label="${esc(AT("Time"))}">
        <button type="button" class="trip-remove">${esc(AT("Remove"))}</button>`;
    row.querySelector(".trip-time").value = trip.time;
    row.querySelector(".trip-remove").addEventListener("click", () => { row.remove(); storeScheduleDay(); updateDayCounts(); });
    row.querySelectorAll("select, input").forEach(field => field.addEventListener("change", () => { storeScheduleDay(); updateDayCounts(); }));
    document.getElementById(`trips-${part}`).appendChild(row);
}

/** Small number on each day tab = how many buses that day (empty = no bus). */
function updateDayCounts() {
    document.querySelectorAll("#schedule-day-tabs .day-tab").forEach(tab => {
        const d = scheduleWeek[tab.dataset.day];
        const n = d.morning.length + d.afternoon.length;
        tab.querySelector(".day-tab-count").textContent = n === 1 ? AT("1 bus") : n ? AT("{count} buses", { count: n }) : AT("Off");
        tab.classList.toggle("is-off", !n);
    });
}

/** Shows one day of the week in the schedule form. */
function showScheduleDay(day) {
    storeScheduleDay();
    scheduleDay = day;
    document.querySelectorAll("#schedule-day-tabs .day-tab").forEach(tab => tab.classList.toggle("active", tab.dataset.day === day));
    ["morning", "afternoon"].forEach(part => {
        document.getElementById(`trips-${part}`).replaceChildren();
        scheduleWeek[day][part].forEach(trip => addTripRow(part, trip));
    });
    updateDayCounts();
}

/** Opens a route's weekly schedule form. */
function openScheduleModal(routeId) {
    const s = ADMIN_DATA.schedules.find(x => x.route_id === routeId);
    if (!s) return;
    showFormError("schedule-form-error", "");
    scheduleRouteId = routeId;
    scheduleWeek = JSON.parse(JSON.stringify(s.days));
    scheduleDay = null;
    document.getElementById("schedule-modal-title").textContent = s.route_name;
    showScheduleDay(ADMIN_DATA.today);                          // today in Bangladesh time (from the server)
    openModal("modal-schedule");
}

document.querySelectorAll("#schedule-day-tabs .day-tab").forEach(tab =>
    tab.addEventListener("click", () => showScheduleDay(tab.dataset.day)));
document.querySelectorAll(".add-trip").forEach(btn =>
    btn.addEventListener("click", () => { addTripRow(btn.dataset.part); }));
document.getElementById("schedule-copy-all")?.addEventListener("click", () => {
    storeScheduleDay();
    const source = JSON.stringify(scheduleWeek[scheduleDay]);
    Object.keys(scheduleWeek).forEach(day => { scheduleWeek[day] = JSON.parse(source); });
    updateDayCounts();
    toast(AT("Copied to all days. Press Save to keep it."));
});

document.getElementById("form-schedule")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    storeScheduleDay();
    const { ok, data } = await api("PUT", `/api/admin/schedules/${encodeURIComponent(scheduleRouteId)}`, { days: scheduleWeek });
    if (ok) location.reload();
    else showFormError("schedule-form-error", data.message || AT("Could not save the schedule."));
});

// ---------- Live map tab ----------
/** Opens the Live map the first time its tab is shown: same smooth live buses as the riders' map. */
function startLiveMap() {
    const helper = window.googleMapsHelper;
    if (!helper || !window.BusFeed) return;
    if (window.adminLive) {
        setTimeout(() => helper.leafletMap?.invalidateSize(), 50);    // the tab was hidden: re-measure
        return;
    }
    helper.plainMarkers = true;                 // plain dots with the bus number, text layer buttons
    helper.initMap("admin-live-map");
    helper.drawRoutes(ADMIN_DATA.routes);
    helper.fitToPoints(helper.getRoutePoints(null), 24);
    helper.onBusMarkerClick = null;
    window.adminLive = new BusFeed({
        pollMs: 3000,
        onUpdate: (buses) => {
            const live = buses.filter(b => b.is_active);
            helper.updateTrails(live);
            helper.updateActiveBuses(live);
            renderLiveList(live);
        }
    }).start();
    setInterval(() => renderLiveList([...window.adminLive.buses.values()].filter(b => b.is_active)), 5000);
}

/** The table next to the live map: each online bus, its speed, next stop and how old its GPS is. */
function renderLiveList(live) {
    const rows = document.getElementById("live-bus-rows");
    if (!rows) return;
    if (!live.length) {
        rows.innerHTML = `<tr><td colspan="4" class="muted">${esc(AT("No bus is online."))}</td></tr>`;
        return;
    }
    const helper = window.googleMapsHelper;
    rows.innerHTML = live.map(bus => {
        const age = Math.max(0, Math.round(helper.serverNow() - (bus.last_update_ts || 0)));
        const ago = age < 5 ? AT("now") : age < 120 ? AT("{seconds} s ago", { seconds: age }) : AT("{minutes} min ago", { minutes: Math.round(age / 60) });
        return `<tr class="${age > 30 ? "live-stale" : ""}">
            <td><span class="live-bus" data-bus="${esc(bus.bus_id)}"><span class="bus-color-dot" style="--bus-color:${esc(bus.color_hex)}"></span>${esc(bus.bus_number)}</span></td>
            <td>${esc(AT("{speed} km/h", { speed: Math.round(bus.speed_kmh || 0) }))}</td>
            <td>${esc(bus.next_stop_name || "—")}</td>
            <td>${esc(ago)}</td></tr>`;
    }).join("");
    rows.querySelectorAll(".live-bus").forEach(el => el.addEventListener("click", () => {
        const bus = window.adminLive.buses.get(el.dataset.bus);
        if (bus) helper.fitToPoints([[bus.current_latitude, bus.current_longitude]], 24);
    }));
}
