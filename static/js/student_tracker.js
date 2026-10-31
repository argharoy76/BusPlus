/*
 * BusPlus rider map (students and teachers; APP_DATA.audience says which).
 *
 * - Full-screen map with every live bus of this rider's audience.
 * - Bottom sheet (phones) / side panel (computers): pick a route, see its buses, tap a bus for details.
 * - Menu: Home stop (type-ahead from all route stops) and arrival-alert settings.
 * - Arrival alerts: chime + pop-up + browser notification when a bus nears the Home stop.
 *
 * Needs google_maps_helper.js (window.googleMapsHelper and escapeHtml) loaded first.
 * Settings are kept in this browser's localStorage.
 * Words: content/words/rider_map.py (the RT look-up below).
 */

/** Words of this page from content/words/rider_map.py. */
const RT = words("rider_map");

/** Bus icon used in the list (front view of a bus, drawn with the current text colour). */
const BUS_ICON_SVG = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="14.5" rx="3"/><path d="M5 10.5h14"/><path d="M9.5 6.5h5"/><circle cx="8.5" cy="14" r="1" class="ico-fill"/><circle cx="15.5" cy="14" r="1" class="ico-fill"/><path d="M7.5 17.5v2.5M16.5 17.5v2.5"/></svg>';
/** Small line icons used inside lists and pop-up messages (static markup, no user data). */
const PIN_ICON_SVG = '<svg class="bp-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-7-6.1-7-11a7 7 0 0 1 14 0c0 4.9-7 11-7 11z"/><circle cx="12" cy="10" r="2.5"/></svg>';
const BELL_ICON_SVG = '<svg class="bp-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 8.5a6 6 0 0 1 12 0c0 6.5 2.5 8.5 2.5 8.5h-17S6 15 6 8.5z"/><path d="M10.2 20.5a2 2 0 0 0 3.6 0"/></svg>';

/** Screens this wide show the sheet as a fixed side panel (must match the @media rule in student.css). */
const isWideScreen = () => window.matchMedia("(min-width: 900px)").matches;

/** localStorage that never throws (private mode / blocked storage just means nothing is remembered). */
const settings = {
    get(key) { try { return localStorage.getItem(key); } catch (e) { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* not saved */ } },
    remove(key) { try { localStorage.removeItem(key); } catch (e) { /* not saved */ } }
};

/**
 * Google-Maps-style bottom sheet with three resting heights:
 *   peek (just the header), half (about half the screen) and full.
 * Drag the handle/header, flick it, tap the handle, or scroll the list to move it.
 * On wide screens it stays put as a side panel and all of this is switched off.
 */
class BottomSheet {
    constructor({ sheet, dragArea, grabber, content, app }) {
        this.sheet = sheet;
        this.dragArea = dragArea;
        this.grabber = grabber;
        this.content = content;
        this.app = app;
        this.snap = "peek";
        this.visiblePx = 150;
        this.drag = null;
        this.forceFull = false;
        this.suppressClick = false;
        this.lastWheel = 0;

        this.measure();
        this.setVisible(this.snaps.peek, false);

        this.bindPointerDrag();
        this.bindContentTouch();
        this.bindWheel();

        this.grabber?.addEventListener("click", () => {
            if (this.suppressClick || isWideScreen()) return;
            this.snapTo(this.snap === "peek" ? "half" : this.snap === "half" ? "full" : "peek");
        });

        // Swallow the click that follows a drag so it doesn't press a button by accident
        this.dragArea?.addEventListener("click", (e) => {
            if (this.suppressClick) {
                e.stopPropagation();
                e.preventDefault();
                this.suppressClick = false;
            }
        }, true);

        // Re-measure when the screen changes size (rotation, the browser's bars showing / hiding)
        const onResize = () => {
            this.measure();
            this.setVisible(this.snaps[this.snap], false);
        };
        window.addEventListener("resize", onResize);
        window.visualViewport?.addEventListener("resize", onResize);
    }

    /** Works out the three resting heights (px of sheet visible) for the current screen and content. */
    measure() {
        const H = this.sheet.offsetHeight || window.innerHeight * 0.9;
        const peek = Math.min(H, (this.dragArea?.offsetHeight || 140) + 6);

        // Tallest the sheet needs to be to show everything in it (no big empty area under a short list)
        let needed = H;
        if (!this.forceFull && this.content) {
            const last = this.content.lastElementChild;
            const contentEnd = last ? last.offsetTop + last.offsetHeight : this.content.offsetTop;
            const bottomRoom = parseFloat(getComputedStyle(this.content).paddingBottom) || 24;   // includes the phone's safe area
            needed = Math.round(contentEnd + bottomRoom + 4);
        }
        const full = Math.max(peek, Math.min(H, needed));
        const half = Math.min(full, Math.max(peek + 120, Math.round(window.innerHeight * 0.5)));
        this.height = H;
        this.snaps = { peek, half, full };
    }

    /** Lets the sheet open to the full screen height (while the route drop-down is open). */
    setForceFull(on) {
        this.forceFull = on;
        if (on) this.snapTo("full");
        else this.refresh();
    }

    /** Moves the sheet so px of it is visible; also tells the page (Locate Me button rides on top). */
    setVisible(px, animate = true) {
        const v = Math.max(this.snaps.peek, Math.min(this.snaps.full, px));
        this.visiblePx = v;
        this.sheet.classList.toggle("dragging", !animate);
        this.sheet.style.setProperty("--sheet-translate", `${this.height - v}px`);
        if (this.app) {
            this.app.style.setProperty("--sheet-offset", `${Math.min(v, this.snaps.half)}px`);
            this.app.classList.toggle("sheet-full", v > this.snaps.half + 40);
            this.app.classList.toggle("sheet-dragging", !animate);
        }
    }

    /** Re-measures (e.g. after the header grew or shrank) and stays at the current resting height. */
    refresh() {
        if (this.drag) return;
        this.measure();
        this.setVisible(this.snaps[this.snap], true);
    }

    /** Moves the sheet to a resting height: "peek", "half" or "full". */
    snapTo(name) {
        this.measure();
        this.snap = name;
        this.setVisible(this.snaps[name], true);
        this.sheet.setAttribute("data-snap", name);
    }

    /** Picks the resting height closest to where a drag would carry the sheet. */
    settle(velocityPxPerMs) {
        const projected = this.visiblePx + velocityPxPerMs * 180;
        let best = "peek";
        let bestDist = Infinity;
        Object.entries(this.snaps).forEach(([name, px]) => {
            const d = Math.abs(px - projected);
            if (d < bestDist) { best = name; bestDist = d; }
        });
        this.snapTo(best);
    }

    /** A drag on the sheet began. */
    startDrag(y) {
        this.measure();
        this.drag = { startY: y, startVisible: this.visiblePx, lastY: y, lastT: performance.now(), v: 0, moved: false };
    }

    /** The sheet follows the finger / mouse. */
    moveDrag(y) {
        const d = this.drag;
        if (!d) return;
        const dy = d.startY - y;               // up = positive
        if (!d.moved && Math.abs(dy) < 6) return;
        d.moved = true;
        const now = performance.now();
        const dt = Math.max(1, now - d.lastT);
        d.v = (d.lastY - y) / dt;               // up = positive
        d.lastY = y;
        d.lastT = now;
        this.setVisible(d.startVisible + dy, false);
    }

    /** Drag ended: settle at the nearest resting height. */
    endDrag() {
        const d = this.drag;
        this.drag = null;
        if (!d) return;
        if (d.moved) {
            this.suppressClick = true;
            setTimeout(() => { this.suppressClick = false; }, 50);
            this.settle(d.v);
        } else {
            this.setVisible(this.visiblePx, true);
        }
    }

    /** Mouse / pen / touch drag on the handle and header. */
    bindPointerDrag() {
        const area = this.dragArea;
        if (!area) return;
        // After pressing on the handle/header, follow the pointer anywhere on the page
        // (it quickly leaves the small handle area while dragging).
        const onMove = (e) => {
            if (!this.drag || e.pointerId !== this.pointerId) return;
            this.moveDrag(e.clientY);
        };
        const onEnd = (e) => {
            if (e.pointerId !== this.pointerId) return;
            window.removeEventListener("pointermove", onMove);
            window.removeEventListener("pointerup", onEnd);
            window.removeEventListener("pointercancel", onEnd);
            this.endDrag();
        };
        area.addEventListener("pointerdown", (e) => {
            if (isWideScreen()) return;
            if (e.pointerType === "mouse" && e.button !== 0) return;
            // Typing / picking in the route search must not drag the sheet
            if (e.target.closest("input, textarea, select, .route-search-dropdown, .route-search-clear")) return;
            if (e.pointerType === "mouse") e.preventDefault(); // no text selection while dragging
            this.pointerId = e.pointerId;
            this.startDrag(e.clientY);
            window.addEventListener("pointermove", onMove);
            window.addEventListener("pointerup", onEnd);
            window.addEventListener("pointercancel", onEnd);
        });
    }

    /**
     * Touch on the list: pulling down at the top of the list lowers the sheet,
     * and pushing up while the sheet isn't full raises it, like Google Maps.
     */
    bindContentTouch() {
        const c = this.content;
        if (!c) return;
        let startY = 0;
        let mode = null; // null | "sheet" | "scroll"
        c.addEventListener("touchstart", (e) => {
            if (isWideScreen()) { mode = "scroll"; return; }
            startY = e.touches[0].clientY;
            mode = null;
        }, { passive: true });
        c.addEventListener("touchmove", (e) => {
            const y = e.touches[0].clientY;
            const dy = y - startY; // down = positive
            if (mode === null && Math.abs(dy) > 6) {
                const pullDownAtTop = dy > 0 && c.scrollTop <= 0;
                const pushUpNotFull = dy < 0 && this.snap !== "full";
                mode = (pullDownAtTop || pushUpNotFull) ? "sheet" : "scroll";
                if (mode === "sheet") this.startDrag(startY);
            }
            if (mode === "sheet") {
                e.preventDefault();
                this.moveDrag(y);
            }
        }, { passive: false });
        const end = () => {
            if (mode === "sheet") this.endDrag();
            mode = null;
        };
        c.addEventListener("touchend", end);
        c.addEventListener("touchcancel", end);
    }

    /** Mouse wheel / trackpad: scroll down on the sheet to raise it, scroll up at the top to lower it. */
    bindWheel() {
        this.sheet.addEventListener("wheel", (e) => {
            if (isWideScreen()) return;        // side panel: the list just scrolls
            const now = Date.now();
            const atTop = !this.content || this.content.scrollTop <= 0;
            const order = ["peek", "half", "full"];
            const idx = order.indexOf(this.snap);
            let next = null;
            if (e.deltaY > 0 && this.snap !== "full") next = order[idx + 1];
            else if (e.deltaY < 0 && atTop && this.snap !== "peek") next = order[idx - 1];
            if (!next) return; // let the list scroll normally
            e.preventDefault();
            if (now - this.lastWheel < 350) return;
            this.lastWheel = now;
            this.snapTo(next);
        }, { passive: false });
    }
}

/** The rider map page: live buses, route/bus selection, Home stop and arrival alerts. */
class StudentTracker {
    constructor() {
        const data = window.APP_DATA || {};
        this.audience = data.audience;          // rider type key, e.g. "student" (content/user_types.py)
        this.allRoutes = data.routes || [];
        this.latestBuses = data.buses || [];

        // Home stop (default: DEFAULT_HOME in content/map_settings.py) and an optional typed address shown as its name
        const home = window.APP_CONFIG?.defaultHome || {};
        this.homePosition = settings.get("busplus_home_stop") || home.stop_name || "";
        this.homeLat = parseFloat(settings.get("busplus_home_lat")) || home.latitude;
        this.homeLng = parseFloat(settings.get("busplus_home_lng")) || home.longitude;
        this.homeAddress = settings.get("busplus_home_address") || "";

        // Arrival alert: how many minutes before, and how many times to repeat
        const savedLeadMin = parseInt(settings.get("busplus_alert_lead_minutes"), 10);
        this.alertThresholdMinutes = !isNaN(savedLeadMin) ? savedLeadMin : parseInt(data.alert_lead_minutes || 5, 10);
        this.alertFrequency = settings.get("busplus_alert_frequency") || "1";
        this.alertTriggerCount = 0;
        this.lastAlertTimestamp = 0;
        this.lastAlertBusId = null;
        this.audioCtx = null;

        // Menu
        this.sideFreqSelect = document.getElementById("side-frequency-select");
        this.customMinutesInput = document.getElementById("side-custom-minutes-input");
        this.minutesHint = document.getElementById("side-minutes-hint");
        this.homeAddressInput = document.getElementById("side-home-address-input");
        this.homeSuggestionsBox = document.getElementById("side-home-suggestions");

        // Home address suggestions: every stop on every route
        this.homePlaces = this.buildHomePlaces();
        this.homeSuggestions = [];
        this.activeSuggestionIdx = -1;
        this.pendingHomePlace = null;
        this.minutesApplyTimer = null;

        // Bottom sheet selection: nothing selected = all routes & buses on the map
        this.routeFilter = null;   // route_id or null
        this.busFilter = null;     // bus_id or null
        this.sheet = null;
        this.lastSheetSignature = "";
        this.lastShownRoutes = null;
        this.lastArrivalCheck = 0;

        this.sheetEl = document.getElementById("bus-sheet");
        this.sheetContent = document.getElementById("bus-sheet-content");
        this.sheetTitle = document.getElementById("bus-sheet-title");
        this.sheetCount = document.getElementById("bus-sheet-count");
        this.sheetBack = document.getElementById("bus-sheet-back");
        this.routeSearchWrap = document.getElementById("route-search");
        this.routeSearchInput = document.getElementById("route-search-input");
        this.routeSearchDropdown = document.getElementById("route-search-dropdown");
        this.routeSearchClear = document.getElementById("route-search-clear");
        this.routeSearchSwatch = document.getElementById("route-search-swatch");
        this.routeOptions = [];
        this.activeRouteOptionIdx = -1;
        this.homeStrip = document.getElementById("bus-sheet-home");
        this.homeStripText = document.getElementById("bus-sheet-home-text");
        this.homeStripEta = document.getElementById("bus-sheet-home-eta");

        this.btnLocateMe = document.getElementById("btn-locate-me");
        this.btnLocateLabel = this.btnLocateMe?.querySelector("span");
    }

    /** Starts the page: map, routes, live feed, menu, Home and alerts. */
    async init() {
        const helper = window.googleMapsHelper;
        helper.initMap("student-map");

        this.syncPreferencesUi();
        helper.updateHomeLocationMarker(this.homeLat, this.homeLng);

        // Route lines + bottom sheet (start with every route and live bus showing)
        await this.loadRoutesFromBackend();
        helper.onBusMarkerClick = (busId) => this.selectBus(busId);
        helper.drawRoutes(this.allRoutes);
        this.setupBottomSheet();
        this.renderSheet(true);
        this.applyMapFilter({ fit: true });

        this.btnLocateMe?.addEventListener("click", () => this.locateStudentGps());
        this.attachHomeAddressAutocomplete();
        this.attachMinutesInput();

        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
        }

        // Live data: the stream pushes changes; the 3-second poll covers gaps
        this.fetchLiveTrackingData();
        this.startLiveStream();
        setInterval(() => this.fetchLiveTrackingData(), window.APP_CONFIG?.refreshMs || 3000);
    }

    // =====================================================================
    // Menu: Home and Notification settings
    // =====================================================================

    /** Fills the menu's inputs and summary lines from the saved settings (called when a menu page opens). */
    syncPreferencesUi() {
        if (this.homeAddressInput) this.homeAddressInput.value = this.homeAddress;
        this.pendingHomePlace = null;
        this.hideHomeSuggestions();
        if (this.sideFreqSelect) this.sideFreqSelect.value = this.alertFrequency;
        if (this.customMinutesInput) this.customMinutesInput.value = this.alertThresholdMinutes;
        this.updateMinutesHint(this.alertThresholdMinutes);
    }

    /** Name shown for Home: the typed address if the rider entered one, otherwise the stop name. */
    getHomeDisplayName() {
        return this.homeAddress || this.homePosition;
    }

    /** Unique stops across all routes, offered as Home address suggestions. */
    buildHomePlaces() {
        const byName = new Map();
        this.allRoutes.forEach(route => {
            (route.stops || []).forEach(stop => {
                const key = stop.stop_name.toLowerCase();
                if (!byName.has(key)) {
                    byName.set(key, {
                        name: stop.stop_name,
                        hint: stop.landmark_hint || "",
                        lat: stop.latitude,
                        lng: stop.longitude,
                        routes: []
                    });
                }
                const place = byName.get(key);
                if (!place.routes.includes(route.route_code)) place.routes.push(route.route_code);
            });
        });
        return Array.from(byName.values());
    }

    /**
     * Best matching places for what the rider has typed so far.
     * Names starting with the text come first, then names containing a word that starts with it,
     * then any other name or landmark containing it.
     */
    findHomePlaces(query) {
        const q = (query || "").trim().toLowerCase();
        if (!q) return [];
        const scored = [];
        this.homePlaces.forEach(place => {
            const name = place.name.toLowerCase();
            let score = -1;
            if (name.startsWith(q)) score = 0;
            else if (name.split(/[\s\-/]+/).some(w => w.startsWith(q))) score = 1;
            else if (name.includes(q)) score = 2;
            else if (place.hint.toLowerCase().includes(q)) score = 3;
            if (score >= 0) scored.push({ place, score });
        });
        scored.sort((a, b) => a.score - b.score || a.place.name.localeCompare(b.place.name));
        return scored.slice(0, 6).map(s => s.place);
    }

    /** Type-ahead on the Home address box (arrow keys, Enter, Escape, tap a suggestion). */
    attachHomeAddressAutocomplete() {
        const input = this.homeAddressInput;
        if (!input || !this.homeSuggestionsBox) return;

        input.addEventListener("input", () => {
            this.pendingHomePlace = null;
            this.renderHomeSuggestions(input.value);
        });

        input.addEventListener("focus", () => {
            if (input.value.trim()) this.renderHomeSuggestions(input.value);
        });

        input.addEventListener("keydown", (e) => {
            const n = this.homeSuggestions.length;
            if (e.key === "ArrowDown" && n) {
                e.preventDefault();
                this.setActiveSuggestion((this.activeSuggestionIdx + 1) % n);
            } else if (e.key === "ArrowUp" && n) {
                e.preventDefault();
                this.setActiveSuggestion((this.activeSuggestionIdx - 1 + n) % n);
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (n && this.activeSuggestionIdx >= 0) {
                    this.pickHomeSuggestion(this.homeSuggestions[this.activeSuggestionIdx]);
                } else if (typeof saveHomeAddress === "function") {
                    saveHomeAddress();   // defined by the page template
                }
            } else if (e.key === "Escape" && n) {
                e.preventDefault();
                e.stopPropagation(); // close the list, not the whole menu
                this.hideHomeSuggestions();
            }
        });

        // Close the list when tapping elsewhere
        document.addEventListener("pointerdown", (e) => {
            if (!e.target.closest(".side-address-wrap")) this.hideHomeSuggestions();
        });
    }

    /** Shows matching stops under the Home address box. */
    renderHomeSuggestions(query) {
        const box = this.homeSuggestionsBox;
        if (!box) return;
        this.homeSuggestions = this.findHomePlaces(query);
        this.activeSuggestionIdx = -1;
        box.innerHTML = "";

        if (this.homeSuggestions.length === 0) {
            this.hideHomeSuggestions();
            return;
        }

        const q = query.trim();
        const span = (className) => {
            const el = document.createElement("span");
            el.className = className;
            return el;
        };
        this.homeSuggestions.forEach((place, idx) => {
            const row = document.createElement("div");
            row.className = "side-suggestion-row";
            row.setAttribute("role", "option");
            row.id = `side-home-suggestion-${idx}`;

            const icon = span("side-suggestion-icon");
            icon.innerHTML = PIN_ICON_SVG;
            const text = span("side-suggestion-text");
            const nameEl = span("side-suggestion-name");
            this.appendHighlighted(nameEl, place.name, q);
            const subEl = span("side-suggestion-sub");
            subEl.textContent = place.hint || place.routes.join(", ");
            text.append(nameEl, subEl);
            row.append(icon, text);

            // pointerdown (not click) so the pick happens before the input loses focus
            row.addEventListener("pointerdown", (e) => {
                e.preventDefault();
                this.pickHomeSuggestion(place);
            });
            box.appendChild(row);
        });

        box.classList.add("open");
        this.homeAddressInput?.setAttribute("aria-expanded", "true");
    }

    /** Writes text into el, wrapping the part that matches the typed text in <mark>. */
    appendHighlighted(el, text, query) {
        const i = query ? text.toLowerCase().indexOf(query.toLowerCase()) : -1;
        if (i < 0) {
            el.textContent = text;
            return;
        }
        const mark = document.createElement("mark");
        mark.textContent = text.slice(i, i + query.length);
        el.append(text.slice(0, i), mark, text.slice(i + query.length));
    }

    /** Highlights a Home suggestion (arrow keys). */
    setActiveSuggestion(idx) {
        this.activeSuggestionIdx = idx;
        Array.from(this.homeSuggestionsBox?.children || []).forEach((row, i) => row.classList.toggle("active", i === idx));
        this.homeAddressInput?.setAttribute("aria-activedescendant", idx >= 0 ? `side-home-suggestion-${idx}` : "");
    }

    /** Puts the chosen stop into the Home address box. */
    pickHomeSuggestion(place) {
        if (!place || !this.homeAddressInput) return;
        this.homeAddressInput.value = place.name;
        this.pendingHomePlace = place;
        this.hideHomeSuggestions();
        this.homeAddressInput.focus();
    }

    /** Hides the Home suggestions. */
    hideHomeSuggestions() {
        this.homeSuggestions = [];
        this.activeSuggestionIdx = -1;
        if (this.homeSuggestionsBox) {
            this.homeSuggestionsBox.classList.remove("open");
            this.homeSuggestionsBox.innerHTML = "";
        }
        if (this.homeAddressInput) {
            this.homeAddressInput.setAttribute("aria-expanded", "false");
            this.homeAddressInput.removeAttribute("aria-activedescendant");
        }
    }

    /** Notification minutes box: the rider just types a number; it is applied automatically. */
    attachMinutesInput() {
        const input = this.customMinutesInput;
        if (!input) return;

        const readValue = () => {
            const raw = input.value.trim();
            if (!/^\d+$/.test(raw)) return null;
            const val = parseInt(raw, 10);
            return val >= 1 && val <= this.maxAlertMinutes() ? val : null;
        };

        const apply = () => {
            clearTimeout(this.minutesApplyTimer);
            const val = readValue();
            if (val !== null && val !== this.alertThresholdMinutes) this.setAlertLeadMinutes(val);
        };

        input.addEventListener("input", () => {
            const val = readValue();
            this.updateMinutesHint(val, input.value.trim() === "");
            clearTimeout(this.minutesApplyTimer);
            if (val !== null) this.minutesApplyTimer = setTimeout(apply, 600);
        });

        input.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                e.preventDefault();
                apply();
                input.blur();
            }
        });

        input.addEventListener("blur", () => {
            apply();
            // If the box was left empty or invalid, show the saved value again
            input.value = this.alertThresholdMinutes;
            this.updateMinutesHint(this.alertThresholdMinutes);
        });
    }

    /** Largest "notify me" minutes allowed (MAX_ALERT_MINUTES in content/rules.py). */
    maxAlertMinutes() {
        return window.APP_CONFIG?.alertMinutesMax || 120;
    }

    /** Shows, in plain words, what the typed minutes mean (or why the value isn't valid). */
    updateMinutesHint(minutes, isEmpty = false) {
        const hint = this.minutesHint;
        if (!hint) return;
        if (isEmpty) {
            hint.className = "side-minutes-hint";
            hint.textContent = RT("Type how many minutes before arrival you want the alert.");
        } else if (minutes === null || minutes === undefined) {
            hint.className = "side-minutes-hint is-error";
            hint.textContent = RT("Enter a whole number from 1 to {max}.", { max: this.maxAlertMinutes() });
        } else {
            hint.className = "side-minutes-hint is-ok";
            const stop = this.getAlertStopName();
            hint.textContent = minutes === 1
                ? RT("You'll be notified 1 minute before the bus reaches {stop}.", { stop })
                : RT("You'll be notified {minutes} minutes before the bus reaches {stop}.", { minutes, stop });
        }
    }

    /**
     * Saves the Home address (called by the page's Save button). If it matches a known stop,
     * the Home dot moves there; otherwise the text is kept as Home's name and the dot stays put.
     */
    setHomeAddress(address) {
        this.homeAddress = (address || "").trim();
        this.hideHomeSuggestions();

        const typed = this.homeAddress.toLowerCase();
        let place = null;
        if (this.pendingHomePlace && this.pendingHomePlace.name.toLowerCase() === typed) {
            place = this.pendingHomePlace;
        } else if (typed) {
            place = this.homePlaces.find(p => p.name.toLowerCase() === typed) || null;
        }
        this.pendingHomePlace = null;

        if (place) {
            this.homePosition = place.name;
            this.homeLat = place.lat;
            this.homeLng = place.lng;
            settings.set("busplus_home_stop", this.homePosition);
            settings.set("busplus_home_lat", this.homeLat);
            settings.set("busplus_home_lng", this.homeLng);
        }

        if (this.homeAddress) settings.set("busplus_home_address", this.homeAddress);
        else settings.remove("busplus_home_address");

        this.updateMinutesHint(this.alertThresholdMinutes);
        this.alertTriggerCount = 0;
        this.fetchLiveTrackingData();
        window.googleMapsHelper.updateHomeLocationMarker(this.homeLat, this.homeLng);
        this.showToast(RT("Home saved"), "toast-success");
    }

    /** Saves how many minutes before arrival the alert should go off. */
    setAlertLeadMinutes(minutes) {
        this.alertThresholdMinutes = parseInt(minutes, 10);
        settings.set("busplus_alert_lead_minutes", this.alertThresholdMinutes);

        // Don't overwrite the box while the rider is still typing in it
        if (this.customMinutesInput && document.activeElement !== this.customMinutesInput) {
            this.customMinutesInput.value = this.alertThresholdMinutes;
        }
        this.updateMinutesHint(this.alertThresholdMinutes);
        this.alertTriggerCount = 0;
        this.fetchLiveTrackingData();
    }

    /** Saves how often the alert repeats ("1", "2", "3" or "continuous"); called by the page's Repeat select. */
    setAlertFrequency(freqVal) {
        this.alertFrequency = freqVal;
        settings.set("busplus_alert_frequency", freqVal);
        this.alertTriggerCount = 0;
        this.showToast(RT("Notification updated"), "toast-info");
    }

    /** "Locate Me": shows the rider's GPS position on the map. */
    locateStudentGps() {
        if (!navigator.geolocation) {
            this.showToast(RT("This browser can't share your location."), "toast-warning");
            return;
        }
        const setLabel = (text) => { if (this.btnLocateLabel) this.btnLocateLabel.textContent = text; };
        const original = this.btnLocateLabel?.dataset.label || this.btnLocateLabel?.textContent || RT("Locate me");
        if (this.btnLocateLabel) this.btnLocateLabel.dataset.label = original;

        setLabel(RT("Locating…"));
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                window.googleMapsHelper.updateStudentLocationMarker(pos.coords.latitude, pos.coords.longitude, pos.coords.accuracy);
                setLabel(RT("Location on"));
                this.btnLocateMe.classList.add("active");
                this.showToast(RT("Location found"), "toast-success");
            },
            () => {
                setLabel(original);
                this.showToast(RT("Could not get your location. Please allow location access for this site."), "toast-warning");
            },
            { enableHighAccuracy: true, timeout: 8000 }
        );
    }

    // =====================================================================
    // Live data
    // =====================================================================

    /**
     * Live bus feed: the server pushes every change straight away (no waiting for the next poll).
     * If it drops, the browser reconnects by itself and the 3-second poll fills in meanwhile.
     */
    startLiveStream() {
        this.feed = new BusFeed({
            audience: this.audience,
            pollMs: window.APP_CONFIG?.refreshMs || 3000,
            onUpdate: (buses) => {
                this.latestBuses = buses;
                this.refreshMapBuses();
                this.renderSheet();
                // Arrival time to Home: refresh at most every 1.5 s
                const now = Date.now();
                if (now - this.lastArrivalCheck > 1500) {
                    this.lastArrivalCheck = now;
                    this.checkArrival();
                }
            }
        }).start();
    }

    /** Checks the Home arrival (the bus positions themselves come from the live feed). */
    async fetchLiveTrackingData() {
        try {
            await this.checkArrival();
        } catch (err) {
            // network blip: try again on the next tick
        }
    }

    /** Asks the server how far the watched bus is from the Home stop; updates the Home line and alerts. */
    async checkArrival() {
        const target = this.getAlertTarget();
        if (!target.routeId) {
            this.updateHomeStrip(null, target);
            return;
        }
        const params = new URLSearchParams({
            route_id: target.routeId,
            stop_name: target.stopName,
            alert_threshold_minutes: this.alertThresholdMinutes,
            audience: this.audience
        });
        if (target.busId) params.set("bus_id", target.busId);

        try {
            const resp = await fetch(`/api/notification/check?${params}`);
            const data = await resp.json();
            if (!data.success) return;
            if (!data.alert) {
                this.updateHomeStrip(null, target);   // no bus of yours on this route
                return;
            }
            // Start the alert count again only when a different bus is being watched
            if (data.alert.bus_id !== this.lastAlertBusId) {
                this.lastAlertBusId = data.alert.bus_id;
                this.alertTriggerCount = 0;
            }
            this.updateHomeStrip(data.alert, target);
            this.maybeAlert(data.alert);
        } catch (err) {
            // network blip: try again on the next tick
        }
    }

    /** The stop alerts are about: the rider's Home stop. */
    getAlertStopName() {
        return this.homePosition || window.APP_CONFIG?.defaultHome?.stop_name || "";
    }

    /**
     * Which route / bus to watch for the Home stop:
     *  - a selected bus: that bus (only if its route passes the Home stop)
     *  - otherwise the selected route if it passes the Home stop, or the first route that does;
     *    the server then watches the nearest live bus on that route.
     */
    getAlertTarget() {
        const stopName = this.getAlertStopName();
        const passes = (route) => (route?.stops || []).some(st => st.stop_name.toLowerCase() === stopName.toLowerCase());
        const routeById = (id) => this.allRoutes.find(r => r.route_id === id);

        if (this.busFilter) {
            const bus = this.latestBuses.find(b => b.bus_id === this.busFilter);
            const route = bus ? routeById(bus.assigned_route_id) : null;
            if (route && passes(route)) return { routeId: route.route_id, busId: bus.bus_id, stopName };
            return { routeId: null, busId: bus?.bus_id, stopName };
        }

        if (this.routeFilter && passes(routeById(this.routeFilter))) {
            return { routeId: this.routeFilter, busId: null, stopName };
        }

        const first = this.allRoutes.find(passes);
        return { routeId: first ? first.route_id : null, busId: null, stopName };
    }

    /** Updates the Home line in the sheet: arrival time at the Home stop, shown only while a live bus is coming. */
    updateHomeStrip(alertInfo, target) {
        if (!this.homeStrip || !this.homeStripText || !this.homeStripEta) return;
        this.homeStrip.classList.remove("is-alert");

        const hasEta = alertInfo && alertInfo.is_active &&
            alertInfo.eta_minutes !== null && alertInfo.eta_minutes !== undefined;
        if (this.homeStrip.hidden !== !hasEta) {
            this.homeStrip.hidden = !hasEta;
            this.sheet?.refresh(); // header height changed
        }
        if (!hasEta) return;

        const eta = alertInfo.eta_minutes;
        this.homeStripText.textContent = target.stopName;
        this.homeStripEta.textContent = alertInfo.urgency_level === "ARRIVED" ? RT("Here")
            : eta < 1 ? RT("< 1 min") : RT("{minutes} min", { minutes: Math.round(eta) });
        if (alertInfo.is_alert_triggered && eta <= this.alertThresholdMinutes) {
            this.homeStrip.classList.add("is-alert");
        }
    }

    /**
     * Fires the arrival alert (chime, pop-up, browser notification) when the bus is within the
     * rider's minutes, as many times as the Repeat setting allows (at least 40 s apart).
     */
    maybeAlert(alertInfo) {
        const eta = alertInfo.eta_minutes;
        if (!alertInfo.is_active || eta === null || eta === undefined) return;
        if (!alertInfo.is_alert_triggered || eta > this.alertThresholdMinutes) return;

        const maxRepeats = this.alertFrequency === "continuous" ? Infinity : parseInt(this.alertFrequency || "1", 10);
        const now = Date.now();
        const canTrigger = this.alertTriggerCount < maxRepeats &&
            (this.alertTriggerCount === 0 || now - this.lastAlertTimestamp > 40000);
        if (!canTrigger) return;

        this.alertTriggerCount++;
        this.lastAlertTimestamp = now;
        this.playProximityAlertChime();

        const title = alertInfo.alert_title + (this.alertTriggerCount > 1 ? RT(" (alert {count})", { count: this.alertTriggerCount }) : "");
        this.showToast(title, "toast-warning");
        this.triggerBrowserNotification(title, alertInfo.alert_message);
    }

    // =====================================================================
    // Bottom sheet: Select route / Select bus
    // =====================================================================

    /** Refreshes the route list from /api/routes (includes routes the admin just added); keeps the page's copy if that fails. */
    async loadRoutesFromBackend() {
        try {
            const resp = await fetch("/api/routes");
            const data = await resp.json();
            if (data.success && Array.isArray(data.routes) && data.routes.length) {
                this.allRoutes = data.routes;
                this.homePlaces = this.buildHomePlaces();
            }
        } catch (err) {
            // use the routes the page came with
        }
    }

    /** Creates the bottom sheet and its click handlers. */
    setupBottomSheet() {
        if (!this.sheetEl) return;
        this.sheet = new BottomSheet({
            sheet: this.sheetEl,
            dragArea: document.getElementById("bus-sheet-drag"),
            grabber: document.getElementById("bus-sheet-grabber"),
            content: this.sheetContent,
            app: document.querySelector(".phone-map-app")
        });

        this.sheetBack?.addEventListener("click", () => this.sheetGoBack());
        this.attachRouteSearch();

        // One click handler for every bus row in the list
        this.sheetContent?.addEventListener("click", (e) => {
            const row = e.target.closest("[data-bus-id]");
            if (row) this.selectBus(row.dataset.busId);
        });
    }

    /** Routes whose name contains the typed letters, best matches first. Empty text = all routes. */
    findRoutes(query) {
        const q = (query || "").trim().toLowerCase();
        const scored = [];
        this.allRoutes.forEach(route => {
            const name = (route.route_name || "").toLowerCase();
            let score = -1;
            if (!q || name.startsWith(q)) score = 0;
            else if (name.split(/[\s\-/]+/).some(w => w.startsWith(q))) score = 1;
            else if (name.includes(q)) score = 2;
            if (score >= 0) scored.push({ route, score });
        });
        scored.sort((a, b) => a.score - b.score);
        return scored;
    }

    /** "Select route" search box: type-ahead drop-down, arrow keys, Enter, Escape and the ✕ button. */
    attachRouteSearch() {
        const input = this.routeSearchInput;
        if (!input || !this.routeSearchDropdown) return;

        input.addEventListener("focus", () => {
            // Make room for the drop-down (and the phone keyboard)
            this.sheet?.setForceFull(true);
            // If a route is chosen, select the text so typing starts a new search
            if (this.routeFilter) input.select();
            this.renderRouteOptions(this.routeFilter ? "" : input.value);
        });

        input.addEventListener("input", () => this.renderRouteOptions(input.value));

        input.addEventListener("keydown", (e) => {
            const n = this.routeOptions.length;
            if (e.key === "ArrowDown" && n) {
                e.preventDefault();
                this.setActiveRouteOption((this.activeRouteOptionIdx + 1) % n);
            } else if (e.key === "ArrowUp" && n) {
                e.preventDefault();
                this.setActiveRouteOption((this.activeRouteOptionIdx - 1 + n) % n);
            } else if (e.key === "Enter") {
                e.preventDefault();
                const pick = this.routeOptions[Math.max(this.activeRouteOptionIdx, 0)];
                if (pick) this.pickRoute(pick.route.route_id);
            } else if (e.key === "Escape") {
                e.preventDefault();
                this.closeRouteDropdown();
                input.blur();
            }
        });

        input.addEventListener("blur", () => {
            // Let a tap on an option land first
            setTimeout(() => {
                this.closeRouteDropdown();
                this.syncRouteSearchBox();
                if (this.sheet?.forceFull) {
                    this.sheet.forceFull = false;
                    this.sheet.snapTo(this.routeFilter ? "half" : "peek");
                }
            }, 120);
        });

        this.routeSearchClear?.addEventListener("click", (e) => {
            e.stopPropagation();
            this.routeFilter = null;
            this.busFilter = null;
            input.value = "";
            this.afterSelectionChange();
            input.focus();
        });
    }

    /** Shows the routes matching the typed text in the drop-down. */
    renderRouteOptions(query) {
        const box = this.routeSearchDropdown;
        if (!box) return;
        const q = (query || "").trim();
        this.routeOptions = this.findRoutes(q);
        this.activeRouteOptionIdx = -1;

        if (!this.routeOptions.length) {
            box.innerHTML = `<div class="route-option-empty">${escapeHtml(RT("No route found"))}</div>`;
        } else {
            box.innerHTML = this.routeOptions.map(({ route }, idx) => `
                <div class="route-option" role="option" id="route-option-${idx}" data-route-id="${escapeHtml(route.route_id)}">
                    <span class="route-option-swatch" style="--route-color:${escapeHtml(route.color_hex)}"></span>
                    <span class="route-option-name">${this.highlightHtml(route.route_name, q)}</span>
                </div>`).join("");
            box.querySelectorAll(".route-option").forEach(opt => {
                // pointerdown so the pick happens before the input loses focus
                opt.addEventListener("pointerdown", (e) => {
                    e.preventDefault();
                    this.pickRoute(opt.dataset.routeId);
                });
            });
        }
        box.classList.add("open");
        this.routeSearchInput?.setAttribute("aria-expanded", "true");
    }

    /** Escapes text and wraps the part matching the query in <mark>. */
    highlightHtml(text, query) {
        const t = String(text ?? "");
        const i = query ? t.toLowerCase().indexOf(query.toLowerCase()) : -1;
        if (i < 0) return escapeHtml(t);
        return escapeHtml(t.slice(0, i)) +
            `<mark>${escapeHtml(t.slice(i, i + query.length))}</mark>` +
            escapeHtml(t.slice(i + query.length));
    }

    /** Highlights a route in the drop-down (arrow keys). */
    setActiveRouteOption(idx) {
        this.activeRouteOptionIdx = idx;
        const opts = this.routeSearchDropdown?.querySelectorAll(".route-option") || [];
        opts.forEach((o, i) => o.classList.toggle("active", i === idx));
        opts[idx]?.scrollIntoView({ block: "nearest" });
        this.routeSearchInput?.setAttribute("aria-activedescendant", idx >= 0 ? `route-option-${idx}` : "");
    }

    /** Hides the route drop-down. */
    closeRouteDropdown() {
        this.routeOptions = [];
        this.activeRouteOptionIdx = -1;
        if (this.routeSearchDropdown) {
            this.routeSearchDropdown.classList.remove("open");
            this.routeSearchDropdown.innerHTML = "";
        }
        this.routeSearchInput?.setAttribute("aria-expanded", "false");
        this.routeSearchInput?.removeAttribute("aria-activedescendant");
    }

    /** Shows only the chosen route and its buses. */
    pickRoute(routeId) {
        this.closeRouteDropdown();
        this.routeFilter = routeId;
        this.busFilter = null;
        if (this.sheet) this.sheet.forceFull = false;
        this.routeSearchInput?.blur();
        this.sheet?.snapTo("half");
        this.afterSelectionChange();
    }

    /** Shows the chosen route's name (and colour) in the search box, or empties it; hides the box in bus details. */
    syncRouteSearchBox() {
        const route = this.allRoutes.find(r => r.route_id === this.routeFilter);
        if (this.routeSearchInput && document.activeElement !== this.routeSearchInput) {
            this.routeSearchInput.value = route ? route.route_name : "";
        }
        if (this.routeSearchWrap) {
            this.routeSearchWrap.classList.toggle("has-route", !!route);
            this.routeSearchWrap.style.setProperty("--route-color", route ? route.color_hex : "#0866ff");
            if (this.routeSearchWrap.hidden !== !!this.busFilter) {
                this.routeSearchWrap.hidden = !!this.busFilter;
                this.sheet?.refresh();
            }
        }
        if (this.routeSearchSwatch) this.routeSearchSwatch.hidden = !route;
        if (this.routeSearchClear) this.routeSearchClear.hidden = !route;
    }

    /** Shows one bus's details and zooms to it. */
    selectBus(busId) {
        if (!this.latestBuses.some(b => b.bus_id === busId)) return;
        this.busFilter = busId;   // the route choice (if any) is kept for "back"
        this.afterSelectionChange();
    }

    /** Back from a bus's details to the list. */
    sheetGoBack() {
        this.busFilter = null;    // back to the list you came from
        this.afterSelectionChange();
    }

    /** Redraws the sheet and map after a route or bus was chosen. */
    afterSelectionChange() {
        this.syncRouteSearchBox();
        this.renderSheet(true);
        // Raise the sheet first so the map fits the area that stays visible above it
        if (this.sheet && this.sheet.snap === "peek" && (this.routeFilter || this.busFilter)) {
            this.sheet.snapTo("half");
        }
        this.applyMapFilter({ fit: true });
        if (this.sheetContent) this.sheetContent.scrollTop = 0;
        this.fetchLiveTrackingData();
    }

    /** Route ids of the current selection (null = all). */
    getVisibleRouteIds() {
        if (this.busFilter) {
            const bus = this.latestBuses.find(b => b.bus_id === this.busFilter);
            return bus ? [bus.assigned_route_id] : null;
        }
        return this.routeFilter ? [this.routeFilter] : null;
    }

    /** Live buses that match the current selection. */
    getVisibleLiveBuses() {
        return this.latestBuses.filter(b => {
            if (!b.is_active) return false;
            if (this.busFilter) return b.bus_id === this.busFilter;
            if (this.routeFilter) return b.assigned_route_id === this.routeFilter;
            return true;
        });
    }

    /** Route lines to draw: only routes with a bus online right now (within the current selection). */
    getShownRouteIds() {
        const selected = this.getVisibleRouteIds();
        const live = new Set(this.latestBuses.filter(b => b.is_active).map(b => b.assigned_route_id));
        return [...live].filter(id => !selected || selected.includes(id));
    }

    /** Puts the selected live buses, their trails and route lines on the map. */
    refreshMapBuses() {
        const helper = window.googleMapsHelper;
        const visible = this.getVisibleLiveBuses();
        const shown = this.getShownRouteIds().sort().join(",");
        if (shown !== this.lastShownRoutes) {               // only touch the lines when that changes
            this.lastShownRoutes = shown;
            helper.showRoutes(shown ? shown.split(",") : []);
        }
        helper.updateTrails(visible);
        helper.updateActiveBuses(visible);
    }

    /** Redraws the map for the current selection; with fit, zooms to it (clear of the sheet / side panel). */
    applyMapFilter({ fit = false } = {}) {
        const helper = window.googleMapsHelper;
        this.lastShownRoutes = null;          // redraw the route lines for the new selection
        this.refreshMapBuses();
        if (!fit) return;

        const wide = isWideScreen();
        const bottomPx = wide ? 24 : (this.sheet ? Math.min(this.sheet.visiblePx, this.sheet.snaps.half) : 150);
        const leftPx = wide ? 420 : 24;
        const bus = this.busFilter ? this.latestBuses.find(b => b.bus_id === this.busFilter) : null;
        if (bus && bus.is_active) {
            helper.fitToPoints([[bus.current_latitude, bus.current_longitude]], bottomPx, leftPx);
        } else {
            helper.fitToPoints(helper.getRoutePoints(this.getVisibleRouteIds()), bottomPx, leftPx);
        }
    }

    /**
     * Draws the sheet list for the current selection. Skips the redraw when nothing visible changed
     * (the list is refreshed on every update), unless force is true.
     */
    renderSheet(force = false) {
        if (!this.sheetContent) return;

        const signature = JSON.stringify([
            this.routeFilter, this.busFilter,
            this.latestBuses.map(b => [b.bus_id, b.is_active, Math.round(b.speed_kmh || 0), b.next_stop_name])
        ]);
        if (!force && signature === this.lastSheetSignature) return;
        this.lastSheetSignature = signature;

        if (this.sheetBack) this.sheetBack.hidden = !this.busFilter;
        this.syncRouteSearchBox();

        if (this.busFilter) {
            const bus = this.latestBuses.find(b => b.bus_id === this.busFilter);
            const route = bus ? this.allRoutes.find(r => r.route_id === bus.assigned_route_id) : null;
            this.sheetTitle.textContent = bus ? (bus.bus_name || bus.bus_number) : RT("Bus");
            this.sheetContent.innerHTML = bus ? this.busDetailHtml(bus, route) : "";
            if (this.sheetCount) this.sheetCount.textContent = "";
        } else {
            const list = this.routeFilter
                ? this.latestBuses.filter(b => b.assigned_route_id === this.routeFilter)
                : this.latestBuses;
            const liveFirst = [...list].sort((a, b) => (b.is_active ? 1 : 0) - (a.is_active ? 1 : 0));
            this.sheetTitle.textContent = this.routeFilter ? RT("Buses") : RT("All buses");
            if (this.sheetCount) this.sheetCount.textContent = String(list.length);
            this.sheetContent.innerHTML = liveFirst.map(b => this.busRowHtml(b)).join("");
        }
        this.sheet?.refresh();
    }

    /** One bus in the list: icon in the bus's colour (solid + green dot = live, light = offline) and its name. */
    busRowHtml(bus) {
        const live = !!bus.is_active;
        const name = escapeHtml(bus.bus_name || bus.bus_number);
        return `
            <button type="button" class="sheet-row" data-bus-id="${escapeHtml(bus.bus_id)}" aria-label="${name}, ${escapeHtml(live ? RT("live") : RT("offline"))}">
                <span class="sheet-bus-dot ${live ? "is-live" : "is-offline"}" style="--bus-color:${escapeHtml(bus.color_hex || "#0866FF")}">${BUS_ICON_SVG}</span>
                <span class="sheet-row-text">
                    <span class="sheet-row-title">${name}</span>
                </span>
                <span class="sheet-row-chevron">›</span>
            </button>`;
    }

    /** Bus details: speed, next stop, route and driver. */
    busDetailHtml(bus, route) {
        const live = !!bus.is_active;
        const cell = (label, value) => `
                    <div class="sheet-detail-cell">
                        <div class="sheet-detail-label">${escapeHtml(label)}</div>
                        <div class="sheet-detail-value">${value}</div>
                    </div>`;
        return `
            <div class="sheet-bus-detail">
                <div class="sheet-detail-grid">
                    ${cell(RT("Speed"), live ? escapeHtml(RT("{speed} km/h", { speed: Math.round(bus.speed_kmh || 0) })) : "--")}
                    ${cell(RT("Next stop"), live ? escapeHtml(bus.next_stop_name || "--") : "--")}
                    ${cell(RT("Route"), escapeHtml(route ? route.route_name : bus.assigned_route_id))}
                    ${cell(RT("Driver"), escapeHtml(bus.driver_name || "--"))}
                </div>
            </div>`;
    }

    // =====================================================================
    // Alert output: sound, pop-up, browser notification
    // =====================================================================

    /** Two-tone chime made with the Web Audio API (no sound file needed). */
    playProximityAlertChime() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;
            if (!this.audioCtx) this.audioCtx = new AudioContext();
            if (this.audioCtx.state === "suspended") this.audioCtx.resume();

            const ctx = this.audioCtx;
            const tone = (freq, start, end, volume) => {
                const osc = ctx.createOscillator();
                const gain = ctx.createGain();
                osc.type = "sine";
                osc.frequency.setValueAtTime(freq, start);
                gain.gain.setValueAtTime(volume, start);
                gain.gain.exponentialRampToValueAtTime(0.001, end);
                osc.connect(gain);
                gain.connect(ctx.destination);
                osc.start(start);
                osc.stop(end);
            };
            const now = ctx.currentTime;
            tone(587.33, now, now + 0.5, 0.18);          // D5
            tone(880.0, now + 0.18, now + 0.85, 0.20);   // A5
        } catch (e) {
            // no sound available: the pop-up still shows
        }
    }

    /** System notification (only if the rider allowed notifications for this site). */
    triggerBrowserNotification(title, body) {
        if (!("Notification" in window) || Notification.permission !== "granted") return;
        try {
            new Notification(title, { body, icon: "/favicon.svg" });
        } catch (e) {
            // not allowed in this context
        }
    }

    /** Small pop-up under the top bar that disappears after a few seconds. type: toast-info | toast-success | toast-warning */
    showToast(title, type = "toast-warning") {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast ${type}`;
        const icon = document.createElement("div");
        icon.className = "toast-icon";
        icon.innerHTML = BELL_ICON_SVG;
        const text = document.createElement("div");
        text.className = "toast-title";
        text.textContent = title;
        toast.append(icon, text);
        container.appendChild(toast);

        setTimeout(() => {
            toast.classList.add("is-leaving");
            setTimeout(() => toast.remove(), 300);
        }, 5500);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const tracker = new StudentTracker();
    window.studentTrackerInstance = tracker;
    tracker.init();
});
