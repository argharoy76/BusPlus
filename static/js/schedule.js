/*
 * "Bus schedule" pop-up (templates/_schedule_popup.html) for students, teachers and drivers.
 *
 * Shows TODAY's buses of the chosen route: in the Morning tab the time each bus reaches
 * the campus, in the Afternoon tab the time it leaves the campus. The admin sets the
 * timetable day by day in the backend (Schedules tab); data comes from GET /api/schedules.
 *
 * Use: BusSchedule.open({ routeId: "KU-R01", audience: "student" })
 */
const BusSchedule = (() => {
    const text = window.SCHEDULE_TEXT || {};
    const el = {
        overlay: document.getElementById("sched-overlay"),
        close: document.getElementById("sched-close"),
        dayName: document.getElementById("sched-day-name"),
        route: document.getElementById("sched-route"),
        swatch: document.getElementById("sched-route-swatch"),
        tabs: document.querySelectorAll(".sched-tab"),
        timeLabel: document.getElementById("sched-time-label"),
        count: document.getElementById("sched-count"),
        list: document.getElementById("sched-list")
    };
    let routes = [];
    let part = "morning";

    /** "13:30" -> ["01:30", "PM"] */
    function clock(hhmm) {
        const [h, m] = hhmm.split(":").map(Number);
        return [`${String(h % 12 || 12).padStart(2, "0")}:${String(m).padStart(2, "0")}`, h < 12 ? "AM" : "PM"];
    }

    function make(tag, className, content) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (content !== undefined) node.textContent = content;   // text only, never HTML
        return node;
    }

    /** Draws today's trips of the chosen route for the chosen part of the day. */
    function render() {
        el.tabs.forEach(tab => {
            const on = tab.dataset.part === part;
            tab.classList.toggle("active", on);
            tab.setAttribute("aria-selected", on ? "true" : "false");
        });
        const route = routes.find(r => r.route_id === el.route.value);
        el.swatch.style.background = route?.color_hex || "#cbd5e1";
        el.timeLabel.textContent = part === "morning" ? text.morningTime : text.afternoonTime;
        const trips = route ? route[part] : [];
        el.count.textContent = trips.length ? String(trips.length) : "";

        if (!trips.length) {
            const empty = make("li", "sched-empty");
            empty.append(make("span", "sched-empty-icon", "—"), make("span", "", text.noBus));
            el.list.replaceChildren(empty);
            return;
        }
        el.list.replaceChildren(...trips.map(trip => {
            const [time, ampm] = clock(trip.time);
            const row = make("li", "sched-row");
            const when = make("div", "sched-when");
            when.append(make("span", "sched-time", time), make("span", "sched-ampm", ampm));
            const bus = make("div", "sched-bus");
            const dot = make("span", "sched-bus-dot");
            dot.style.background = trip.color_hex;
            bus.append(dot, make("span", "sched-bus-name", trip.bus_name || "—"));
            row.append(when, bus);
            return row;
        }));
    }

    /** Opens on a route (or the first one), on Morning before noon and Afternoon after. */
    async function open({ routeId = null, audience = null } = {}) {
        part = new Date().getHours() < 12 ? "morning" : "afternoon";
        el.overlay.hidden = false;
        el.list.replaceChildren(make("li", "sched-empty", "…"));
        try {
            const url = "/api/schedules" + (audience ? `?audience=${encodeURIComponent(audience)}` : "");
            const data = await (await fetch(url)).json();
            routes = data.routes || [];
            el.dayName.textContent = data.day_name || "";
        } catch (e) {
            el.list.replaceChildren(make("li", "sched-empty", "Could not load. Check your internet."));
            return;
        }
        el.route.replaceChildren(...routes.map(r => {
            const option = make("option", "", r.route_name);
            option.value = r.route_id;
            return option;
        }));
        if (routeId && routes.some(r => r.route_id === routeId)) el.route.value = routeId;
        render();
    }

    function close() { el.overlay.hidden = true; }

    el.close.addEventListener("click", close);
    el.overlay.addEventListener("click", (e) => { if (e.target === el.overlay) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !el.overlay.hidden) close(); });
    el.route.addEventListener("change", render);
    el.tabs.forEach(tab => tab.addEventListener("click", () => { part = tab.dataset.part; render(); }));

    return { open, close };
})();
window.BusSchedule = BusSchedule;
