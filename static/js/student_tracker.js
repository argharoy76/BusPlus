/**
 * Khulna University Bus Tracker (BusPlus)
 * Student Live Tracking, Stop ETA & Proximity Alert Controller
 *
 * Features:
 * - BusPlus Side Menu Drawer (Home position selection, alert lead time, repeat frequency)
 * - Front Drop-Down Quick Selector Bar (Bus & Main Stop selection)
 * - Real-time animated Google Maps engine integration
 * - Customizable multi-tone audio alerts and push notifications
 */

/** Bus icon used in the list (front view of a bus, drawn with the current text colour). */
const BUS_ICON_SVG = '<svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="3" width="14" height="14.5" rx="3"/><path d="M5 10.5h14"/><path d="M9.5 6.5h5"/><circle cx="8.5" cy="14" r="1" class="ico-fill"/><circle cx="15.5" cy="14" r="1" class="ico-fill"/><path d="M7.5 17.5v2.5M16.5 17.5v2.5"/></svg>';

/**
 * Google-Maps-style bottom sheet with three resting heights:
 *   peek (just the header), half (about half the screen) and full.
 * Drag the handle/header, flick it, tap the handle, or scroll the list to move it.
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
        this.suppressClick = false;
        this.lastWheel = 0;

        this.measure();
        this.setVisible(this.snaps.peek, false);

        this.bindPointerDrag();
        this.bindContentTouch();
        this.bindWheel();

        this.grabber?.addEventListener("click", () => {
            if (this.suppressClick || BottomSheet.isSidePanel()) return;
            this.snapTo(this.snap === "peek" ? "half" : this.snap === "half" ? "full" : "peek");
        });

        // Swallow the click that follows a drag so it doesn't press a tab/button by accident
        this.dragArea?.addEventListener("click", (e) => {
            if (this.suppressClick) {
                e.stopPropagation();
                e.preventDefault();
                this.suppressClick = false;
            }
        }, true);

        window.addEventListener("resize", () => {
            this.measure();
            this.setVisible(this.snaps[this.snap], false);
        });
    }

    /** On wide screens (computers) the sheet is a fixed panel at the side instead of a bottom sheet. */
    static isSidePanel() {
        return window.matchMedia("(min-width: 900px)").matches;
    }

    measure() {
        const H = this.sheet.offsetHeight || window.innerHeight * 0.9;
        const peek = Math.min(H, (this.dragArea?.offsetHeight || 140) + 6);

        // Tallest the sheet needs to be to show everything in it (no big empty area under a short list)
        let needed = H;
        if (!this.forceFull && this.content) {
            const last = this.content.lastElementChild;
            const contentEnd = last ? last.offsetTop + last.offsetHeight : this.content.offsetTop;
            needed = Math.round(contentEnd + 20);
        }
        const full = Math.max(peek, Math.min(H, needed));
        const half = Math.min(full, Math.max(peek + 120, Math.round(window.innerHeight * 0.5)));
        this.height = H;
        this.snaps = { peek, half, full };
    }

    /** Lets the sheet open to the full screen height (e.g. while the route drop-down is open). */
    setForceFull(on) {
        this.forceFull = on;
        if (on) this.snapTo("full");
        else this.refresh();
    }

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

    startDrag(y) {
        this.measure();
        this.drag = { startY: y, startVisible: this.visiblePx, lastY: y, lastT: performance.now(), v: 0, moved: false };
    }

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

    endDrag() {
        const d = this.drag;
        this.drag = null;
        if (!d) return false;
        if (d.moved) {
            this.suppressClick = true;
            setTimeout(() => { this.suppressClick = false; }, 50);
            this.settle(d.v);
        } else {
            this.setVisible(this.visiblePx, true);
        }
        return d.moved;
    }

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
            if (BottomSheet.isSidePanel()) return;        // computer layout: fixed side panel
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
     * and pushing up while the sheet isn't full raises it — like Google Maps.
     */
    bindContentTouch() {
        const c = this.content;
        if (!c) return;
        let startY = 0;
        let mode = null; // null | "sheet" | "scroll"
        c.addEventListener("touchstart", (e) => {
            if (BottomSheet.isSidePanel()) { mode = "scroll"; return; }
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
            if (BottomSheet.isSidePanel()) return;        // let the list scroll normally
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

class StudentTracker {
    constructor() {
        this.audience = window.APP_DATA?.audience === "teacher" ? "teacher" : "student";
        this.allRoutes = window.APP_DATA?.routes || [];
        this.buses = window.APP_DATA?.buses || [];

        // Restore or default route and stop
        this.selectedRouteId = window.APP_DATA?.preferred_route_id || "KU-R01";
        this.selectedStopName = window.APP_DATA?.preferred_stop || "Malabotha More";

        // Restore or default Home Position
        this.homePosition = localStorage.getItem("busplus_home_stop") || "Malabotha More";
        this.homeLat = parseFloat(localStorage.getItem("busplus_home_lat")) || 22.7725;
        this.homeLng = parseFloat(localStorage.getItem("busplus_home_lng")) || 89.5855;
        this.homeAddress = localStorage.getItem("busplus_home_address") || "";

        // Restore or default Notification Settings
        const savedLeadMin = parseInt(localStorage.getItem("busplus_alert_lead_minutes"), 10);
        this.alertThresholdMinutes = !isNaN(savedLeadMin) ? savedLeadMin : parseInt(window.APP_DATA?.alert_lead_minutes || 5, 10);

        this.alertFrequency = localStorage.getItem("busplus_alert_frequency") || "1";
        this.alertTriggerCount = 0;
        this.lastAlertTimestamp = 0;

        this.isAudioAlertEnabled = true;
        this.studentLocation = null;
        this.pollInterval = null;

        // Web Audio Synthesizer Context
        this.audioCtx = null;

        // UI references
        this.routeSelect = document.getElementById("select-route");
        this.stopSelect = document.getElementById("select-stop");
        this.frontBusSelect = document.getElementById("front-select-bus");
        this.frontStopSelect = document.getElementById("front-select-stop");

        this.sideHomeSelect = document.getElementById("side-home-select");
        this.sideHomeLabel = document.getElementById("side-current-home-label");
        this.sideFreqSelect = document.getElementById("side-frequency-select");
        this.sideSoundCheckbox = document.getElementById("side-sound-checkbox");
        this.customMinutesInput = document.getElementById("side-custom-minutes-input");
        this.sideNotifLabel = document.getElementById("side-current-notif-label");
        this.homeAddressInput = document.getElementById("side-home-address-input");
        this.homeSuggestionsBox = document.getElementById("side-home-suggestions");
        this.minutesHint = document.getElementById("side-minutes-hint");

        // Places offered as Home address suggestions (every stop on every KU route)
        this.homePlaces = this.buildHomePlaces();
        this.homeSuggestions = [];
        this.activeSuggestionIdx = -1;
        this.pendingHomePlace = null;
        this.minutesApplyTimer = null;

        // Bottom sheet selection: nothing selected = all routes & buses on the map
        this.routeFilter = null;   // route_id or null
        this.busFilter = null;     // bus_id or null
        this.latestBuses = this.buses;
        this.latestAlert = null;
        this.sheet = null;
        this.lastSheetSignature = "";

        this.sheetEl = document.getElementById("bus-sheet");
        this.sheetContent = document.getElementById("bus-sheet-content");
        this.sheetTitle = document.getElementById("bus-sheet-title");
        this.sheetSubtitle = document.getElementById("bus-sheet-subtitle");
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
        this.soundToggle = document.getElementById("toggle-audio-alerts");
        this.btnTestSound = document.getElementById("btn-test-sound");
        this.alertBannerCard = document.getElementById("proximity-alert-banner");
        this.etaNumber = document.getElementById("eta-minutes-val");
        this.etaDistance = document.getElementById("eta-dist-val");
        this.etaClock = document.getElementById("eta-clock-val");
        this.etaSpeed = document.getElementById("eta-speed-val");
        this.alertStatusPill = document.getElementById("alert-status-pill");
        this.targetStopLabel = document.getElementById("target-stop-label");
        this.busNameLabel = document.getElementById("target-bus-label");
    }

    async init() {
        // 1. Initialize Google Map
        await window.googleMapsHelper.initMap("student-map", {
            center: { lat: 22.8010, lng: 89.5345 },
            zoom: 13
        });

        // 2. Initialize Front Drop-Downs & Side Menu Home/Stops
        this.populateStopsDropdown(this.selectedRouteId);
        this.populateFrontStopsDropdown(this.selectedRouteId);
        this.populateSideHomeDropdown();
        this.renderTimelineStops(this.selectedRouteId);

        // 3. Sync UI with saved preferences
        this.syncPreferencesUi();

        // 4. Render saved Home Position marker on map
        if (this.homeLat && this.homeLng) {
            window.googleMapsHelper.updateHomeLocationMarker(this.homeLat, this.homeLng, this.getHomeDisplayName());
        }

        // 4b. Route lines + bottom sheet (start with every route and live bus showing)
        await this.loadRoutesFromBackend();
        window.googleMapsHelper.onBusMarkerClick = (busId) => this.selectBus(busId);
        window.googleMapsHelper.drawRoutes(this.allRoutes);
        this.setupBottomSheet();
        this.renderSheet(true);
        this.applyMapFilter({ fit: true });

        // 5. Attach event listeners
        if (this.routeSelect) {
            this.routeSelect.value = this.selectedRouteId;
            this.routeSelect.addEventListener("change", (e) => this.handleRouteChange(e.target.value));
        }

        if (this.stopSelect) {
            this.stopSelect.value = this.selectedStopName;
            this.stopSelect.addEventListener("change", (e) => this.handleStopChange(e.target.value));
        }

        if (this.btnLocateMe) {
            this.btnLocateMe.addEventListener("click", () => this.locateStudentGps());
        }

        this.attachHomeAddressAutocomplete();
        this.attachMinutesInput();

        if (this.soundToggle) {
            this.soundToggle.addEventListener("change", (e) => {
                this.isAudioAlertEnabled = e.target.checked;
                if (this.sideSoundCheckbox) this.sideSoundCheckbox.checked = e.target.checked;
            });
        }

        if (this.btnTestSound) {
            this.btnTestSound.addEventListener("click", () => {
                this.playProximityAlertChime();
                this.showToastNotification("🔊 Sound Test", "Alert chime sound verified successfully!", "toast-info");
            });
        }

        // Request browser notification permission early
        if ("Notification" in window && Notification.permission === "default") {
            Notification.requestPermission();
        }

        // 6. Initial fetch and start real-time telemetry polling
        this.fetchLiveTrackingData();
        this.startLiveStream();
        this.pollInterval = setInterval(() => this.fetchLiveTrackingData(), 3000);
    }

    /**
     * Synchronizes UI controls (chips, dropdowns, inputs) with stored settings.
     */
    syncPreferencesUi() {
        // Sync Home & Notification summary lines in the main menu
        this.updateMenuSummaries();

        // Sync Home edit page
        if (this.homeAddressInput) {
            this.homeAddressInput.value = this.homeAddress;
        }
        this.pendingHomePlace = null;
        this.hideHomeSuggestions();

        // Sync Alert Frequency Select
        if (this.sideFreqSelect) {
            this.sideFreqSelect.value = this.alertFrequency;
        }

        // Sync Sound Checkbox
        if (this.sideSoundCheckbox) {
            this.sideSoundCheckbox.checked = this.isAudioAlertEnabled;
        }

        // Sync Time Chips
        document.querySelectorAll(".side-time-chip").forEach(chip => {
            const min = parseInt(chip.getAttribute("data-min"), 10);
            if (min === this.alertThresholdMinutes) {
                chip.classList.add("active");
            } else {
                chip.classList.remove("active");
            }
        });

        if (this.customMinutesInput) {
            this.customMinutesInput.value = this.alertThresholdMinutes;
        }
        this.updateMinutesHint(this.alertThresholdMinutes);

        // Sync Front Bus Select to match current route
        if (this.frontBusSelect) {
            const busForRoute = this.buses.find(b => b.assigned_route_id === this.selectedRouteId);
            if (busForRoute) {
                this.frontBusSelect.value = busForRoute.bus_id;
            }
        }
    }

    /**
     * Name shown for Home: the typed address if the student entered one, otherwise the stop / GPS label.
     */
    getHomeDisplayName() {
        return this.homeAddress || this.homePosition;
    }

    /**
     * Refreshes the small summary lines under "Home" and "Notification" in the main menu.
     */
    updateMenuSummaries() {
        if (this.sideHomeLabel) {
            this.sideHomeLabel.textContent = this.getHomeDisplayName();
        }
        if (this.sideNotifLabel) {
            const repeat = this.alertFrequency === "continuous"
                ? "continuous"
                : `${this.alertFrequency} time${this.alertFrequency === "1" ? "" : "s"}`;
            this.sideNotifLabel.textContent = `${this.alertThresholdMinutes} min before · ${repeat}`;
        }
    }

    /**
     * Builds the list of known places (unique stops across all routes) for Home address suggestions.
     */
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
     * Returns the best matching places for what the student has typed so far.
     * Names starting with the text come first, then names containing a word that starts with it,
     * then any other name or landmark containing it.
     */
    findHomePlaces(query) {
        const q = (query || "").trim().toLowerCase();
        if (!q) return [];
        const scored = [];
        this.homePlaces.forEach(place => {
            const name = place.name.toLowerCase();
            const hint = place.hint.toLowerCase();
            let score = -1;
            if (name.startsWith(q)) score = 0;
            else if (name.split(/[\s\-/]+/).some(w => w.startsWith(q))) score = 1;
            else if (name.includes(q)) score = 2;
            else if (hint.includes(q)) score = 3;
            if (score >= 0) scored.push({ place, score });
        });
        scored.sort((a, b) => a.score - b.score || a.place.name.localeCompare(b.place.name));
        return scored.slice(0, 6).map(s => s.place);
    }

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
            const open = this.homeSuggestions.length > 0;
            if (e.key === "ArrowDown" && open) {
                e.preventDefault();
                this.setActiveSuggestion((this.activeSuggestionIdx + 1) % this.homeSuggestions.length);
            } else if (e.key === "ArrowUp" && open) {
                e.preventDefault();
                const n = this.homeSuggestions.length;
                this.setActiveSuggestion((this.activeSuggestionIdx - 1 + n) % n);
            } else if (e.key === "Enter") {
                e.preventDefault();
                if (open && this.activeSuggestionIdx >= 0) {
                    this.pickHomeSuggestion(this.homeSuggestions[this.activeSuggestionIdx]);
                } else if (typeof saveHomeAddress === "function") {
                    saveHomeAddress();
                }
            } else if (e.key === "Escape" && open) {
                e.preventDefault();
                e.stopPropagation(); // close the list, not the whole menu
                this.hideHomeSuggestions();
            }
        });

        // Close the list when tapping elsewhere in the menu
        document.addEventListener("pointerdown", (e) => {
            if (!e.target.closest(".side-address-wrap")) this.hideHomeSuggestions();
        });
    }

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
        this.homeSuggestions.forEach((place, idx) => {
            const row = document.createElement("div");
            row.className = "side-suggestion-row";
            row.setAttribute("role", "option");
            row.id = `side-home-suggestion-${idx}`;

            const icon = document.createElement("span");
            icon.className = "side-suggestion-icon";
            icon.textContent = "📍";

            const text = document.createElement("span");
            text.className = "side-suggestion-text";

            const nameEl = document.createElement("span");
            nameEl.className = "side-suggestion-name";
            this.appendHighlighted(nameEl, place.name, q);

            const subEl = document.createElement("span");
            subEl.className = "side-suggestion-sub";
            subEl.textContent = place.hint || place.routes.join(", ");

            text.appendChild(nameEl);
            text.appendChild(subEl);
            row.appendChild(icon);
            row.appendChild(text);

            // pointerdown (not click) so the pick happens before the input loses focus
            row.addEventListener("pointerdown", (e) => {
                e.preventDefault();
                this.pickHomeSuggestion(place);
            });
            box.appendChild(row);
        });

        box.classList.add("open");
        if (this.homeAddressInput) this.homeAddressInput.setAttribute("aria-expanded", "true");
    }

    /** Writes text into el, wrapping the part that matches the typed text in <mark>. */
    appendHighlighted(el, text, query) {
        const i = query ? text.toLowerCase().indexOf(query.toLowerCase()) : -1;
        if (i < 0) {
            el.textContent = text;
            return;
        }
        el.appendChild(document.createTextNode(text.slice(0, i)));
        const mark = document.createElement("mark");
        mark.textContent = text.slice(i, i + query.length);
        el.appendChild(mark);
        el.appendChild(document.createTextNode(text.slice(i + query.length)));
    }

    setActiveSuggestion(idx) {
        this.activeSuggestionIdx = idx;
        const rows = this.homeSuggestionsBox ? this.homeSuggestionsBox.children : [];
        Array.from(rows).forEach((row, i) => row.classList.toggle("active", i === idx));
        if (this.homeAddressInput) {
            this.homeAddressInput.setAttribute("aria-activedescendant", idx >= 0 ? `side-home-suggestion-${idx}` : "");
        }
    }

    pickHomeSuggestion(place) {
        if (!place || !this.homeAddressInput) return;
        this.homeAddressInput.value = place.name;
        this.pendingHomePlace = place;
        this.hideHomeSuggestions();
        this.homeAddressInput.focus();
    }

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

    /**
     * Notification minutes box: the student just types a number; it is applied automatically.
     */
    attachMinutesInput() {
        const input = this.customMinutesInput;
        if (!input) return;

        const readValue = () => {
            const raw = input.value.trim();
            if (!/^\d+$/.test(raw)) return null;
            const val = parseInt(raw, 10);
            return val >= 1 && val <= 120 ? val : null;
        };

        const apply = () => {
            clearTimeout(this.minutesApplyTimer);
            const val = readValue();
            if (val !== null && val !== this.alertThresholdMinutes) {
                this.setAlertLeadMinutes(val, { silent: true });
            }
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

    /** Shows, in plain words, what the typed minutes mean (or why the value isn't valid). */
    updateMinutesHint(minutes, isEmpty = false) {
        const hint = this.minutesHint;
        if (!hint) return;
        if (isEmpty) {
            hint.className = "side-minutes-hint";
            hint.textContent = "Type how many minutes before arrival you want the alert.";
        } else if (minutes === null || minutes === undefined) {
            hint.className = "side-minutes-hint is-error";
            hint.textContent = "Enter a whole number from 1 to 120.";
        } else {
            hint.className = "side-minutes-hint is-ok";
            const unit = minutes === 1 ? "minute" : "minutes";
            hint.textContent = `✓ You'll be notified ${minutes} ${unit} before the bus reaches ${this.getAlertStopName()}.`;
        }
    }

    /**
     * Saves the student's home address. If it matches a suggested place, the Home pin moves there;
     * otherwise the text is kept as the Home label and the pin stays where it was.
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
            localStorage.setItem("busplus_home_stop", this.homePosition);
            localStorage.setItem("busplus_home_lat", this.homeLat);
            localStorage.setItem("busplus_home_lng", this.homeLng);
        }

        if (this.homeAddress) {
            localStorage.setItem("busplus_home_address", this.homeAddress);
        } else {
            localStorage.removeItem("busplus_home_address");
        }
        this.updateMenuSummaries();
        this.updateMinutesHint(this.alertThresholdMinutes);
        this.alertTriggerCount = 0;
        this.latestAlert = null;
        this.fetchLiveTrackingData();
        window.googleMapsHelper.updateHomeLocationMarker(this.homeLat, this.homeLng, this.getHomeDisplayName());
        this.showToastNotification("🏡 Home Saved", `Home set to ${this.getHomeDisplayName()}`, "toast-success");
    }

    /**
     * Populates the Front Quick Dropdown for Main Stops.
     */
    populateFrontStopsDropdown(routeId) {
        if (!this.frontStopSelect) return;
        this.frontStopSelect.innerHTML = "";

        const route = this.allRoutes.find(r => r.route_id === routeId);
        if (!route || !route.stops) return;

        let hasSelected = false;
        route.stops.forEach(stop => {
            const opt = document.createElement("option");
            opt.value = stop.stop_name;
            opt.textContent = `${stop.sequence_order}. ${stop.stop_name} (${stop.scheduled_morning_time})`;
            if (stop.stop_name.toLowerCase().includes(this.selectedStopName.toLowerCase()) ||
                this.selectedStopName.toLowerCase().includes(stop.stop_name.toLowerCase())) {
                opt.selected = true;
                hasSelected = true;
            }
            this.frontStopSelect.appendChild(opt);
        });

        if (!hasSelected && route.stops.length > 0) {
            this.frontStopSelect.options[0].selected = true;
            this.selectedStopName = route.stops[0].stop_name;
        }
    }

    /**
     * Populates Side Menu Home Position Stop Dropdown with all stops across all routes.
     */
    populateSideHomeDropdown() {
        if (!this.sideHomeSelect) return;
        this.sideHomeSelect.innerHTML = "";

        const seenStops = new Set();
        this.allRoutes.forEach(route => {
            if (!route.stops) return;
            route.stops.forEach(stop => {
                if (!seenStops.has(stop.stop_name)) {
                    seenStops.add(stop.stop_name);
                    const opt = document.createElement("option");
                    opt.value = stop.stop_name;
                    opt.textContent = `${stop.stop_name} (${route.route_code})`;
                    if (stop.stop_name.toLowerCase().includes(this.homePosition.toLowerCase())) {
                        opt.selected = true;
                    }
                    this.sideHomeSelect.appendChild(opt);
                }
            });
        });
    }

    populateStopsDropdown(routeId) {
        if (!this.stopSelect) return;
        this.stopSelect.innerHTML = "";
        const route = this.allRoutes.find(r => r.route_id === routeId);
        if (!route || !route.stops) return;

        route.stops.forEach(stop => {
            const opt = document.createElement("option");
            opt.value = stop.stop_name;
            opt.textContent = `${stop.sequence_order}. ${stop.stop_name} (${stop.scheduled_morning_time})`;
            if (stop.stop_name.toLowerCase().includes(this.selectedStopName.toLowerCase())) {
                opt.selected = true;
            }
            this.stopSelect.appendChild(opt);
        });
    }

    renderTimelineStops(routeId) {
        const container = document.getElementById("timeline-stops-list");
        if (!container) return;
        container.innerHTML = "";

        const route = this.allRoutes.find(r => r.route_id === routeId);
        if (!route || !route.stops) return;

        route.stops.forEach(stop => {
            const isTarget = stop.stop_name.toLowerCase().includes(this.selectedStopName.toLowerCase());
            const item = document.createElement("div");
            item.className = `stop-timeline-item ${isTarget ? 'active-target' : ''}`;
            item.innerHTML = `
                <div class="stop-dot"></div>
                <div style="flex:1;">
                    <div style="font-size:0.825rem; font-weight:600; color:var(--text-primary);">${stop.sequence_order}. ${stop.stop_name}</div>
                    <div style="font-size:0.75rem; color:var(--text-muted);">${stop.scheduled_morning_time} · ${stop.landmark_hint || "KU Stop"}</div>
                </div>
            `;
            item.addEventListener("click", () => {
                this.handleStopChange(stop.stop_name);
                if (this.stopSelect) this.stopSelect.value = stop.stop_name;
                if (this.frontStopSelect) this.frontStopSelect.value = stop.stop_name;
                window.googleMapsHelper.panTo(stop.latitude, stop.longitude, 15);
            });
            container.appendChild(item);
        });
    }

    /**
     * Handlers for Front Drop-Down Quick Selection Bar
     */
    handleFrontBusChange(busId) {
        const bus = this.buses.find(b => b.bus_id === busId);
        if (!bus) return;

        const routeId = bus.assigned_route_id || "KU-R01";
        this.handleRouteChange(routeId);
        this.showToastNotification("🚌 Bus Selected", `${bus.bus_name || bus.bus_number} selected.`, "toast-info");
    }

    handleFrontStopChange(stopName) {
        this.handleStopChange(stopName);
        if (this.stopSelect) this.stopSelect.value = stopName;

        // Pan to selected stop
        const route = this.allRoutes.find(r => r.route_id === this.selectedRouteId);
        if (route && route.stops) {
            const stop = route.stops.find(s => s.stop_name.toLowerCase().includes(stopName.toLowerCase()));
            if (stop) {
                window.googleMapsHelper.panTo(stop.latitude, stop.longitude, 15);
            }
        }
    }

    handleRouteChange(routeId) {
        this.selectedRouteId = routeId;
        this.populateStopsDropdown(routeId);
        this.populateFrontStopsDropdown(routeId);

        if (this.stopSelect && this.stopSelect.options.length > 0) {
            this.selectedStopName = this.stopSelect.options[0].value;
        }

        // Sync Front Bus Select
        if (this.frontBusSelect) {
            const busForRoute = this.buses.find(b => b.assigned_route_id === routeId);
            if (busForRoute) {
                this.frontBusSelect.value = busForRoute.bus_id;
            }
        }

        // Sync Route Chips
        document.querySelectorAll(".phone-chip-btn").forEach(btn => {
            if (btn.getAttribute("data-route-id") === routeId) {
                btn.classList.add("active");
            } else {
                btn.classList.remove("active");
            }
        });

        this.renderTimelineStops(routeId);
        this.alertTriggerCount = 0;
        this.fetchLiveTrackingData();
    }

    handleStopChange(stopName) {
        this.selectedStopName = stopName;
        if (this.frontStopSelect && this.frontStopSelect.value !== stopName) {
            this.frontStopSelect.value = stopName;
        }
        if (this.stopSelect && this.stopSelect.value !== stopName) {
            this.stopSelect.value = stopName;
        }
        this.renderTimelineStops(this.selectedRouteId);
        this.updateMinutesHint(this.alertThresholdMinutes);
        this.alertTriggerCount = 0;
        this.fetchLiveTrackingData();
    }

    /**
     * Home Position Management
     */
    setHomePositionFromStop(stopName) {
        let matchedStop = null;
        for (const route of this.allRoutes) {
            if (route.stops) {
                matchedStop = route.stops.find(s => s.stop_name.toLowerCase().includes(stopName.toLowerCase()));
                if (matchedStop) break;
            }
        }

        if (matchedStop) {
            this.homePosition = matchedStop.stop_name;
            this.homeLat = matchedStop.latitude;
            this.homeLng = matchedStop.longitude;

            localStorage.setItem("busplus_home_stop", this.homePosition);
            localStorage.setItem("busplus_home_lat", this.homeLat);
            localStorage.setItem("busplus_home_lng", this.homeLng);

            this.updateMenuSummaries();

            window.googleMapsHelper.updateHomeLocationMarker(this.homeLat, this.homeLng, this.getHomeDisplayName());
            this.showToastNotification("🏡 Home Position Set", `Home stop set to ${this.homePosition}`, "toast-success");
        }
    }

    setHomeFromGps() {
        if (!navigator.geolocation) {
            alert("Geolocation is not supported by your browser.");
            return;
        }

        this.showToastNotification("📍 Locating", "Fetching your live GPS coordinates for Home...", "toast-info");

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                this.homeLat = lat;
                this.homeLng = lng;
                this.homePosition = `GPS Home (${lat.toFixed(4)}, ${lng.toFixed(4)})`;

                localStorage.setItem("busplus_home_stop", this.homePosition);
                localStorage.setItem("busplus_home_lat", this.homeLat);
                localStorage.setItem("busplus_home_lng", this.homeLng);

                this.updateMenuSummaries();

                window.googleMapsHelper.updateHomeLocationMarker(this.homeLat, this.homeLng, this.homeAddress || "My Home (GPS)");
                this.showToastNotification("🏡 Home Saved", "Your live GPS position has been set as Home.", "toast-success");
            },
            (err) => {
                console.warn("Geolocation failed:", err);
                alert("Could not access your location. Please check browser GPS permissions.");
            },
            { enableHighAccuracy: true, timeout: 8000 }
        );
    }

    viewHomeOnMap() {
        if (!this.homeLat || !this.homeLng) {
            alert("Please set your home position first.");
            return;
        }
        window.googleMapsHelper.panTo(this.homeLat, this.homeLng, 16);
        window.googleMapsHelper.updateHomeLocationMarker(this.homeLat, this.homeLng, this.getHomeDisplayName());
        this.showToastNotification("🏡 Home Focused", `Map centered on ${this.getHomeDisplayName()}`, "toast-info");
    }

    /**
     * Notification Lead Time & Repeat Frequency Settings
     */
    setAlertLeadMinutes(minutes, { silent = false } = {}) {
        this.alertThresholdMinutes = parseInt(minutes, 10);
        localStorage.setItem("busplus_alert_lead_minutes", this.alertThresholdMinutes);

        document.querySelectorAll(".side-time-chip").forEach(chip => {
            const m = parseInt(chip.getAttribute("data-min"), 10);
            if (m === this.alertThresholdMinutes) {
                chip.classList.add("active");
            } else {
                chip.classList.remove("active");
            }
        });

        // Don't overwrite the box while the student is still typing in it
        if (this.customMinutesInput && document.activeElement !== this.customMinutesInput) {
            this.customMinutesInput.value = this.alertThresholdMinutes;
        }
        this.updateMinutesHint(this.alertThresholdMinutes);

        this.updateMenuSummaries();
        this.alertTriggerCount = 0;
        this.fetchLiveTrackingData();
        if (!silent) {
            this.showToastNotification("⏱ Alert Time Updated", `Notification alert set to ${this.alertThresholdMinutes} minutes before arrival.`, "toast-info");
        }
    }

    setAlertFrequency(freqVal) {
        this.alertFrequency = freqVal;
        localStorage.setItem("busplus_alert_frequency", freqVal);
        this.alertTriggerCount = 0;
        this.updateMenuSummaries();

        const labels = {
            "1": "1 Time",
            "2": "2 Times",
            "3": "3 Times",
            "continuous": "Continuous (Every minute)"
        };

        this.showToastNotification("🔔 Alert Frequency", `Notification will repeat: ${labels[freqVal] || freqVal}`, "toast-info");
    }

    /**
     * Obtains student's live GPS coordinates via HTML5 Geolocation API.
     */
    locateStudentGps() {
        if (!navigator.geolocation) {
            alert("Geolocation is not supported by your browser.");
            return;
        }

        this.btnLocateMe.innerHTML = "<span>📍</span> Locating...";
        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                this.studentLocation = { lat, lng };
                window.googleMapsHelper.updateStudentLocationMarker(lat, lng, pos.coords.accuracy);
                this.btnLocateMe.innerHTML = "<span>📍</span> GPS Active";
                this.btnLocateMe.classList.add("active");
                this.btnLocateMe.classList.add("btn-primary");
                this.showToastNotification("📍 GPS Located", "Your current location has been marked on the map.", "toast-success");
                this.fetchLiveTrackingData();
            },
            (err) => {
                console.warn("Geolocation failed:", err);
                this.btnLocateMe.innerHTML = "<span>📍</span> Locate Me";
                alert("Could not access your location. Please check browser GPS permissions.");
            },
            { enableHighAccuracy: true, timeout: 8000 }
        );
    }

    /**
     * Polls the server for bus telemetry and evaluates proximity alerts.
     */
    /**
     * Live bus feed: the server pushes every change straight away (no waiting for the next poll).
     * If it drops, the browser reconnects by itself and the 3-second poll fills in meanwhile.
     */
    startLiveStream() {
        if (!window.EventSource) return;
        const es = new EventSource(`/api/buses/stream?audience=${this.audience}`);
        es.onopen = () => { this.streamLive = true; };
        es.onerror = () => { this.streamLive = false; };
        es.onmessage = (e) => {
            try {
                const data = JSON.parse(e.data);
                if (!Array.isArray(data.buses)) return;
                this.streamLive = true;
                this.latestBuses = data.buses;
                this.refreshMapBuses();
                this.renderSheet();
                // Arrival time to Home: refresh at most every 1.5 s
                const now = Date.now();
                if (now - (this.lastArrivalCheck || 0) > 1500) {
                    this.lastArrivalCheck = now;
                    this.checkArrival();
                }
            } catch (err) { /* ignore a bad message */ }
        };
        this.liveStream = es;
    }

    async fetchLiveTrackingData() {
        try {
            // 1. Buses (only this rider's): from the live stream if it's connected, otherwise fetch them
            if (!this.streamLive) {
                const busResp = await fetch(`/api/buses?audience=${this.audience}`);
                const busData = await busResp.json();
                if (busData.success && busData.buses) {
                    this.latestBuses = busData.buses;
                    this.refreshMapBuses();
                    this.renderSheet();
                }
            }
            await this.checkArrival();
        } catch (err) {
            console.error("Error updating live tracking telemetry:", err);
        }
    }

    async checkArrival() {
        try {
            // Arrival check for the student's Home stop
            const target = this.getAlertTarget();
            if (!target.routeId) {
                this.updateHomeStrip(null, target);
                return;
            }
            let notifUrl = `/api/notification/check?route_id=${encodeURIComponent(target.routeId)}` +
                `&stop_name=${encodeURIComponent(target.stopName)}` +
                `&alert_threshold_minutes=${this.alertThresholdMinutes}` +
                `&audience=${this.audience}`;
            if (target.busId) notifUrl += `&bus_id=${encodeURIComponent(target.busId)}`;

            const notifResp = await fetch(notifUrl);
            const notifData = await notifResp.json();

            if (notifData.success && !notifData.alert) {
                this.latestAlert = null;
                this.updateHomeStrip(null, target);   // no bus of yours on this route
            }
            if (notifData.success && notifData.alert) {
                // Start the alert count again only when a different bus is being watched
                if (notifData.alert.bus_id !== this.lastAlertBusId) {
                    this.lastAlertBusId = notifData.alert.bus_id;
                    this.alertTriggerCount = 0;
                }
                this.latestAlert = notifData.alert;
                this.updateHomeStrip(notifData.alert, target);
                this.updateAlertUi(notifData.alert);
                if (this.busFilter) this.renderSheet(true); // refresh "To your Home" in bus details
            }
        } catch (err) {
            console.error("Error updating live tracking telemetry:", err);
        }
    }

    // =====================================================================
    // Home stop alerts
    // =====================================================================

    /** The stop alerts are about: the Home stop the student picked (defaults to Malabotha More). */
    getAlertStopName() {
        return this.homePosition || "Malabotha More";
    }

    /**
     * Works out which route / bus to watch for the Home stop:
     *  - a selected bus → that bus (only if its route passes the Home stop)
     *  - otherwise a selected route that passes the Home stop, or the first route that does;
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
            return { routeId: null, busId: bus?.bus_id, stopName, reason: "bus-not-on-route", bus };
        }

        if (this.routeFilter && passes(routeById(this.routeFilter))) {
            return { routeId: this.routeFilter, busId: null, stopName };
        }

        const first = this.allRoutes.find(passes);
        return { routeId: first ? first.route_id : null, busId: null, stopName, reason: first ? null : "no-route" };
    }

    /** Updates the 🏡 line in the bottom sheet with the arrival time at the Home stop. */
    updateHomeStrip(alertInfo, target) {
        if (!this.homeStripText || !this.homeStripEta) return;
        const stop = target?.stopName || this.getAlertStopName();
        this.homeStrip?.classList.remove("is-alert");

        // Only shown while a live bus is heading to the Home stop; no explanation text otherwise
        const hasEta = alertInfo && alertInfo.is_active &&
            alertInfo.eta_minutes !== null && alertInfo.eta_minutes !== undefined;
        if (this.homeStrip && this.homeStrip.hidden !== !hasEta) {
            this.homeStrip.hidden = !hasEta;
            this.sheet?.refresh(); // header height changed
        }
        if (!hasEta) return;

        const eta = alertInfo.eta_minutes;
        this.homeStripText.textContent = stop;
        this.homeStripEta.textContent = alertInfo.urgency_level === "ARRIVED" ? "Here" : (eta < 1 ? "< 1 min" : `${Math.round(eta)} min`);
        if (alertInfo.is_alert_triggered && eta <= this.alertThresholdMinutes) {
            this.homeStrip?.classList.add("is-alert");
        }
    }

    // =====================================================================
    // Bottom sheet: Select route / Select bus
    // =====================================================================

    /** Refreshes the route list from the backend (/api/routes); keeps the page's copy if that fails. */
    async loadRoutesFromBackend() {
        try {
            const resp = await fetch("/api/routes");
            const data = await resp.json();
            if (data.success && Array.isArray(data.routes) && data.routes.length) {
                this.allRoutes = data.routes;
                this.homePlaces = this.buildHomePlaces();   // include stops of routes added by the admin
            }
        } catch (err) {
            console.warn("Could not refresh routes from the server; using the page's copy.", err);
        }
    }

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

    // ---------------------------------------------------------------------
    // Select route: type-ahead search with a drop-down
    // ---------------------------------------------------------------------

    /** Routes whose name contains the typed letters (anywhere in the name). Empty text = all routes. */
    findRoutes(query) {
        const q = (query || "").trim().toLowerCase();
        const scored = [];
        this.allRoutes.forEach(route => {
            const name = (route.route_name || "").toLowerCase();
            let score = -1;
            if (!q) score = 0;
            else if (name.startsWith(q)) score = 0;
            else if (name.split(/[\s\-/]+/).some(w => w.startsWith(q))) score = 1;
            else if (name.includes(q)) score = 2;
            if (score >= 0) scored.push({ route, score });
        });
        scored.sort((a, b) => a.score - b.score);
        return scored;
    }

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
                const pick = this.routeOptions[this.activeRouteOptionIdx >= 0 ? this.activeRouteOptionIdx : 0];
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

    renderRouteOptions(query) {
        const box = this.routeSearchDropdown;
        if (!box) return;
        const esc = (v) => this.escapeHtml(v);
        const q = (query || "").trim();
        this.routeOptions = this.findRoutes(q);
        this.activeRouteOptionIdx = -1;

        if (!this.routeOptions.length) {
            box.innerHTML = `<div class="route-option-empty">No route found</div>`;
        } else {
            box.innerHTML = this.routeOptions.map(({ route }, idx) => `
                <div class="route-option" role="option" id="route-option-${idx}" data-route-id="${esc(route.route_id)}">
                    <span class="route-option-swatch" style="--route-color:${esc(route.color_hex)}"></span>
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
        if (i < 0) return this.escapeHtml(t);
        return this.escapeHtml(t.slice(0, i)) +
            `<mark>${this.escapeHtml(t.slice(i, i + query.length))}</mark>` +
            this.escapeHtml(t.slice(i + query.length));
    }

    setActiveRouteOption(idx) {
        this.activeRouteOptionIdx = idx;
        const opts = this.routeSearchDropdown?.querySelectorAll(".route-option") || [];
        opts.forEach((o, i) => o.classList.toggle("active", i === idx));
        opts[idx]?.scrollIntoView({ block: "nearest" });
        this.routeSearchInput?.setAttribute("aria-activedescendant", idx >= 0 ? `route-option-${idx}` : "");
    }

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

    pickRoute(routeId) {
        this.closeRouteDropdown();
        this.routeFilter = routeId;
        this.busFilter = null;
        if (this.sheet) this.sheet.forceFull = false;
        this.routeSearchInput?.blur();
        if (this.sheet) this.sheet.snapTo("half");
        this.afterSelectionChange();
    }

    /** Shows the chosen route's name (and colour) in the search box, or empties it. */
    syncRouteSearchBox() {
        const route = this.allRoutes.find(r => r.route_id === this.routeFilter);
        if (this.routeSearchInput && document.activeElement !== this.routeSearchInput) {
            this.routeSearchInput.value = route ? route.route_name : "";
        }
        if (this.routeSearchWrap) {
            this.routeSearchWrap.classList.toggle("has-route", !!route);
            this.routeSearchWrap.style.setProperty("--route-color", route ? route.color_hex : "#0866ff");
            if (this.routeSearchWrap.hidden !== !!this.busFilter) {
                this.routeSearchWrap.hidden = !!this.busFilter; // bus details view: just the bus
                this.sheet?.refresh();
            }
        }
        if (this.routeSearchSwatch) this.routeSearchSwatch.hidden = !route;
        if (this.routeSearchClear) this.routeSearchClear.hidden = !route;
    }

    // ---------------------------------------------------------------------
    // Selection
    // ---------------------------------------------------------------------

    selectBus(busId) {
        const bus = this.latestBuses.find(b => b.bus_id === busId);
        if (!bus) return;
        this.busFilter = busId;   // the route choice (if any) is kept for "back"
        this.afterSelectionChange();
    }

    sheetGoBack() {
        this.busFilter = null;    // back to the list you came from
        this.afterSelectionChange();
    }

    afterSelectionChange() {
        this.latestAlert = null;
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

    /** Route ids whose lines should be visible (null = all). */
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
        const selected = this.getVisibleRouteIds();          // null = every route
        const live = new Set(this.latestBuses.filter(b => b.is_active).map(b => b.assigned_route_id));
        return [...live].filter(id => !selected || selected.includes(id));
    }

    refreshMapBuses() {
        const helper = window.googleMapsHelper;
        const visible = this.getVisibleLiveBuses();
        const shown = this.getShownRouteIds().sort().join(",");
        if (shown !== this.lastShownRoutes) {               // only touch the lines when that changes
            this.lastShownRoutes = shown;
            helper.showRoutes(shown ? shown.split(",") : []);
        }
        helper.updateTrails(visible);      // red line where each bus has driven
        helper.updateActiveBuses(visible);
    }

    isDesktop() {
        return window.matchMedia("(min-width: 900px)").matches;
    }

    applyMapFilter({ fit = false } = {}) {
        const helper = window.googleMapsHelper;
        const routeIds = this.getVisibleRouteIds();
        this.lastShownRoutes = null;          // redraw the route lines for the new selection
        this.refreshMapBuses();
        if (!fit) return;

        // Keep what we zoom to clear of the panel: below it on phones, beside it on computers
        const desktop = this.isDesktop();
        const bottomPx = desktop ? 24 : (this.sheet ? Math.min(this.sheet.visiblePx, this.sheet.snaps.half) : 150);
        const leftPx = desktop ? 420 : 24;
        const bus = this.busFilter ? this.latestBuses.find(b => b.bus_id === this.busFilter) : null;
        if (bus && bus.is_active) {
            helper.fitToPoints([[bus.current_latitude, bus.current_longitude]], bottomPx, leftPx);
        } else {
            helper.fitToPoints(helper.getRoutePoints(routeIds), bottomPx, leftPx);
        }
    }

    /**
     * Draws the sheet list for the current selection. Skips the redraw when nothing visible changed
     * (the list is refreshed every poll), unless force is true.
     */
    renderSheet(force = false) {
        if (!this.sheetContent) return;

        const signature = JSON.stringify([
            this.routeFilter, this.busFilter,
            this.latestBuses.map(b => [b.bus_id, b.is_active, Math.round(b.speed_kmh || 0), b.next_stop_name])
        ]);
        if (!force && signature === this.lastSheetSignature) return;
        this.lastSheetSignature = signature;

        const routeById = (id) => this.allRoutes.find(r => r.route_id === id);
        // Live buses first, then offline ones
        const ordered = (list) => [...list].sort((a, b) => (b.is_active ? 1 : 0) - (a.is_active ? 1 : 0));

        if (this.sheetBack) this.sheetBack.hidden = !this.busFilter;
        this.syncRouteSearchBox();

        // No explanation lines under the heading
        this.sheetSubtitle.textContent = "";

        if (this.busFilter) {
            const bus = this.latestBuses.find(b => b.bus_id === this.busFilter);
            const route = bus ? routeById(bus.assigned_route_id) : null;
            this.sheetTitle.textContent = bus ? (bus.bus_name || bus.bus_number) : "Bus";
            this.sheetContent.innerHTML = bus ? this.busDetailHtml(bus, route) : "";
            this.sheetCount && (this.sheetCount.textContent = "");
            this.sheet?.refresh();
            return;
        }

        const list = this.routeFilter
            ? this.latestBuses.filter(b => b.assigned_route_id === this.routeFilter)
            : this.latestBuses;

        this.sheetTitle.textContent = this.routeFilter ? "Buses" : "All buses";
        this.sheetCount && (this.sheetCount.textContent = String(list.length));
        this.sheetContent.innerHTML = ordered(list).map(b => this.busRowHtml(b)).join("");
        this.sheet?.refresh();
    }

    /** One bus in the list: colour icon (grey = offline, green dot = live) and its name. */
    busRowHtml(bus) {
        const esc = (v) => this.escapeHtml(v);
        const live = !!bus.is_active;
        return `
            <button type="button" class="sheet-row" data-bus-id="${esc(bus.bus_id)}" aria-label="${esc(bus.bus_name || bus.bus_number)}, ${live ? "live" : "offline"}">
                <span class="sheet-bus-dot ${live ? "is-live" : "is-offline"}" style="--bus-color:${esc(bus.color_hex || "#0866FF")}">${BUS_ICON_SVG}</span>
                <span class="sheet-row-text">
                    <span class="sheet-row-title">${esc(bus.bus_name || bus.bus_number)}</span>
                </span>
                <span class="sheet-row-chevron">›</span>
            </button>`;
    }

    /** Bus details: just the facts, no explanation text. */
    busDetailHtml(bus, route) {
        const esc = (v) => this.escapeHtml(v);
        const live = !!bus.is_active;
        return `
            <div class="sheet-bus-detail">
                <div class="sheet-detail-grid">
                    <div class="sheet-detail-cell">
                        <div class="sheet-detail-label">Speed</div>
                        <div class="sheet-detail-value">${live ? `${Math.round(bus.speed_kmh || 0)} km/h` : "--"}</div>
                    </div>
                    <div class="sheet-detail-cell">
                        <div class="sheet-detail-label">Next stop</div>
                        <div class="sheet-detail-value">${live ? esc(bus.next_stop_name || "--") : "--"}</div>
                    </div>
                    <div class="sheet-detail-cell">
                        <div class="sheet-detail-label">Route</div>
                        <div class="sheet-detail-value">${esc(route ? route.route_name : bus.assigned_route_id)}</div>
                    </div>
                    <div class="sheet-detail-cell">
                        <div class="sheet-detail-label">Driver</div>
                        <div class="sheet-detail-value">${esc(bus.driver_name || "--")}</div>
                    </div>
                </div>
            </div>`;
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
     * Updates the UI cards and triggers alerts according to student's repeat count and lead time.
     */
    updateAlertUi(alertInfo) {
        const frontEtaBadge = document.getElementById("front-eta-badge");

        if (!alertInfo.is_active || alertInfo.eta_minutes === null || alertInfo.eta_minutes === undefined) {
            if (this.etaNumber) this.etaNumber.textContent = "--";
            if (this.etaDistance) this.etaDistance.textContent = "--";
            if (this.etaClock) this.etaClock.textContent = "--";
            if (this.etaSpeed) this.etaSpeed.textContent = "--";
            if (frontEtaBadge) frontEtaBadge.classList.remove("eta-alert-pulsing");
            if (this.targetStopLabel) this.targetStopLabel.textContent = alertInfo.target_stop_name || this.selectedStopName;
            if (this.busNameLabel) this.busNameLabel.textContent = `${alertInfo.bus_name || alertInfo.bus_number} (Awaiting GPS)`;
            if (this.alertStatusPill) {
                this.alertStatusPill.className = "alert-pill pill-info";
                this.alertStatusPill.innerHTML = `⏱ Awaiting GPS`;
            }
            if (this.alertBannerCard) {
                this.alertBannerCard.classList.remove("proximity-alert-active");
            }
            return;
        }

        const etaMinutes = alertInfo.eta_minutes;
        const distanceKm = alertInfo.distance_km;
        const arrivalClock = alertInfo.estimated_arrival_clock_time;
        const busName = alertInfo.bus_name || alertInfo.bus_number;

        if (this.etaNumber) this.etaNumber.textContent = etaMinutes < 1 ? "< 1" : etaMinutes.toFixed(1);
        if (this.etaDistance) this.etaDistance.textContent = `${distanceKm} km`;
        if (this.etaClock) this.etaClock.textContent = arrivalClock;
        if (this.etaSpeed) this.etaSpeed.textContent = `${Math.round(alertInfo.bus_speed_kmh || 0)} km/h`;
        if (this.targetStopLabel) this.targetStopLabel.textContent = alertInfo.target_stop_name;
        if (this.busNameLabel) this.busNameLabel.textContent = busName;

        // Proximity Warning Evaluation
        if (alertInfo.is_alert_triggered && etaMinutes <= this.alertThresholdMinutes) {
            if (frontEtaBadge) frontEtaBadge.classList.add("eta-alert-pulsing");
            if (this.alertBannerCard) {
                this.alertBannerCard.classList.add("proximity-alert-active");
            }
            if (this.alertStatusPill) {
                this.alertStatusPill.className = "alert-pill pill-warning";
                this.alertStatusPill.innerHTML = `🔔 ${Math.round(etaMinutes)} MIN ALERT`;
            }

            // Evaluate Alert Repeat Frequency
            const maxRepeats = this.alertFrequency === "continuous" ? Infinity : parseInt(this.alertFrequency || "1", 10);
            const now = Date.now();
            const minIntervalMs = 40000; // 40 seconds minimum between chime repeats
            const canTrigger = (this.alertTriggerCount < maxRepeats) &&
                               (this.alertTriggerCount === 0 || (now - this.lastAlertTimestamp) > minIntervalMs);

            if (canTrigger) {
                this.alertTriggerCount++;
                this.lastAlertTimestamp = now;

                if (this.isAudioAlertEnabled) {
                    this.playProximityAlertChime();
                }

                const repeatTag = this.alertTriggerCount > 1 ? ` (Alert #${this.alertTriggerCount})` : "";
                this.showToastNotification(
                    alertInfo.alert_title + repeatTag,
                    alertInfo.alert_message,
                    "toast-warning"
                );
                this.triggerBrowserNotification(alertInfo.alert_title + repeatTag, alertInfo.alert_message);
            }
        } else {
            // Normal transit info state
            if (frontEtaBadge) frontEtaBadge.classList.remove("eta-alert-pulsing");
            if (this.alertBannerCard) {
                this.alertBannerCard.classList.remove("proximity-alert-active");
            }
            if (this.alertStatusPill) {
                this.alertStatusPill.className = "alert-pill pill-info";
                this.alertStatusPill.innerHTML = `⏱ En Route`;
            }
        }
    }

    /**
     * Web Audio API Synthesizer: Generates a melodious two-tone chime bell.
     */
    playProximityAlertChime() {
        try {
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            if (!AudioContext) return;

            if (!this.audioCtx) {
                this.audioCtx = new AudioContext();
            }

            if (this.audioCtx.state === "suspended") {
                this.audioCtx.resume();
            }

            const now = this.audioCtx.currentTime;

            // Tone 1: 587.33 Hz (D5)
            const osc1 = this.audioCtx.createOscillator();
            const gain1 = this.audioCtx.createGain();
            osc1.type = "sine";
            osc1.frequency.setValueAtTime(587.33, now);
            gain1.gain.setValueAtTime(0.18, now);
            gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
            osc1.connect(gain1);
            gain1.connect(this.audioCtx.destination);
            osc1.start(now);
            osc1.stop(now + 0.5);

            // Tone 2: 880 Hz (A5) for bright arrival chime
            const osc2 = this.audioCtx.createOscillator();
            const gain2 = this.audioCtx.createGain();
            osc2.type = "sine";
            osc2.frequency.setValueAtTime(880.0, now + 0.18);
            gain2.gain.setValueAtTime(0.20, now + 0.18);
            gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.85);
            osc2.connect(gain2);
            gain2.connect(this.audioCtx.destination);
            osc2.start(now + 0.18);
            osc2.stop(now + 0.85);
        } catch (e) {
            console.warn("Web Audio alert chime error:", e);
        }
    }

    triggerBrowserNotification(title, body) {
        if ("Notification" in window && Notification.permission === "granted") {
            try {
                new Notification(title, {
                    body: body,
                    icon: "/static/favicon.ico"
                });
            } catch (e) {
                // Ignore if in restricted context
            }
        }
    }

    showToastNotification(title, message, typeClass = "toast-warning") {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast ${typeClass}`;
        toast.innerHTML = `
            <div style="font-size:1.25rem;">🚌</div>
            <div style="flex:1; font-weight:700; font-size:0.9rem; color:var(--text-primary); align-self:center;">${this.escapeHtml(title)}</div>
        `;
        container.appendChild(toast);

        setTimeout(() => {
            toast.style.opacity = "0";
            toast.style.transform = "translateX(100%)";
            toast.style.transition = "all 0.3s ease";
            setTimeout(() => toast.remove(), 300);
        }, 5500);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    const tracker = new StudentTracker();
    window.studentTrackerInstance = tracker;
    tracker.init();
});
