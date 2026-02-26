/**
 * Smart Home IoT - Dashboard
 * Updates real-time sensor cards and system overview from MQTT data.
 */
class Dashboard {
    constructor() {
        this.lastUpdate = { PI1: null, PI2: null, PI3: null };
    }

    /* -------- main dispatcher -------- */

    updateSensor(item) {
        const sensor = item.sensor;
        const device = item.device;
        const value  = item.value;

        if (device) {
            this.lastUpdate[device] = new Date();
            this._setText(`${device.toLowerCase()}-last-update`, this._timeAgo(new Date()));
            this._updatePiStatus(device, true);
        }

        switch (sensor) {
            case "DHT1": case "DHT2": case "DHT3":
                this._updateDHT(sensor, value);
                break;
            case "DPIR1": case "DPIR2": case "DPIR3":
                this._updateMotion(sensor, value);
                break;
            case "DS1": case "DS2":
                this._updateDoor(sensor, value);
                break;
            case "DUS1": case "DUS2":
                this._updateDistance(sensor, value);
                break;
            case "DL":
                this._updateOnOff("dl-state", value);
                break;
            case "DB":
                this._updateOnOff("db-state", value);
                break;
            case "BRGB":
                this._updateRGB(value);
                break;
            case "GSG":
                this._updateGyroscope(item);
                break;
            case "4SD":
                this._updateTimer(item);
                break;
        }
    }

    /* -------- system overview -------- */

    updateAlarmState(data) {
        const state = typeof data === "string" ? data : (data.state || data);
        const el   = document.getElementById("alarm-state");
        const card = document.getElementById("alarm-card");
        if (!el) return;

        el.textContent = state;
        el.className   = "badge fs-6";
        card.className = "card h-100";

        const map = {
            DISARMED: ["bg-success",              "alarm-disarmed"],
            ARMING:   ["bg-warning text-dark",    "alarm-arming"],
            ARMED:    ["bg-primary",              "alarm-armed"],
            GRACE:    ["bg-warning text-dark",    "alarm-grace"],
            ALARMING: ["bg-danger",               "alarm-alarming"],
        };
        const [badge, border] = map[state] || ["bg-secondary", ""];
        badge.split(" ").forEach((c) => el.classList.add(c));
        if (border) card.classList.add(border);
    }

    updatePersonCount(data) {
        let count;
        if (typeof data === "number") {
            count = data;
        } else if (typeof data === "object" && data !== null && data.count != null) {
            count = data.count;
        } else {
            count = parseInt(data, 10);
        }
        this._setText("person-count", isNaN(count) ? "?" : count);
    }

    /* -------- sensor-specific updaters -------- */

    _updateDHT(sensor, value) {
        const p = sensor.toLowerCase();
        if (typeof value === "object" && value !== null) {
            if (value.temperature != null)
                this._setText(`${p}-temp`, Number(value.temperature).toFixed(1));
            if (value.humidity != null)
                this._setText(`${p}-hum`, Number(value.humidity).toFixed(1));
        }
    }

    _updateMotion(sensor, value) {
        const id       = sensor.toLowerCase();
        const detected = value === 1 || value === true;
        const stateEl  = document.getElementById(`${id}-state`);
        const cardEl   = document.getElementById(`card-${id}`);
        if (stateEl) {
            stateEl.textContent = detected ? "MOTION" : "CLEAR";
            stateEl.className   = `badge mt-1 ${detected ? "bg-danger" : "bg-secondary"}`;
        }
        if (cardEl) cardEl.classList.toggle("sensor-active", detected);
    }

    _updateDoor(sensor, value) {
        const id     = sensor.toLowerCase();
        const isOpen = value === 1 || value === true;
        const el     = document.getElementById(`${id}-state`);
        if (el) {
            el.textContent = isOpen ? "OPEN" : "CLOSED";
            el.className   = `badge mt-1 ${isOpen ? "bg-danger" : "bg-success"}`;
        }
        // swap icon
        const card = document.getElementById(`card-${id}`);
        if (card) {
            const icon = card.querySelector("i");
            if (icon) icon.className = `bi ${isOpen ? "bi-door-open" : "bi-door-closed"} fs-3`;
        }
    }

    _updateDistance(sensor, value) {
        const el = document.getElementById(`${sensor.toLowerCase()}-value`);
        if (el && typeof value === "number") el.textContent = value.toFixed(1);
    }

    _updateOnOff(elementId, value) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const isOn = value === 1 || value === true;
        el.textContent = isOn ? "ON" : "OFF";
        el.className   = `badge mt-1 ${isOn ? "bg-success" : "bg-secondary"}`;
    }

    _updateRGB(value) {
        const preview = document.getElementById("rgb-preview");
        if (!preview || typeof value !== "object") return;
        const r = Math.round((value.r || 0) * 255);
        const g = Math.round((value.g || 0) * 255);
        const b = Math.round((value.b || 0) * 255);
        preview.style.backgroundColor = `rgb(${r},${g},${b})`;
    }

    _updateGyroscope(item) {
        const el = document.getElementById("gsg-value");
        if (!el) return;
        // Accel fields are at the top level of the batch item (ax, ay, az)
        if (item.ax != null) {
            el.textContent =
                `x:${Number(item.ax).toFixed(2)}  y:${Number(item.ay).toFixed(2)}  z:${Number(item.az).toFixed(2)}`;
        }
    }

    _updateTimer(item) {
        const el = document.getElementById("timer-display");
        if (!el) return;
        const action = item.action;
        if (action === "show_time") {
            el.textContent = item.display || "00:00";
            el.classList.remove("timer-blink");
        } else if (action === "blink_start") {
            el.textContent = "00:00";
            el.classList.add("timer-blink");
        } else if (action === "blink_stop") {
            el.textContent = "00:00";
            el.classList.remove("timer-blink");
        }
    }

    /* -------- PI status -------- */

    _updatePiStatus(device, online) {
        const statusEl = document.getElementById(`${device.toLowerCase()}-status`);
        if (statusEl) {
            statusEl.textContent = online ? "Online" : "Offline";
            statusEl.className = `badge mt-1 ${online ? "bg-success" : "bg-secondary"}`;
        }
    }

    /* -------- helpers -------- */

    _setText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    }

    _timeAgo(date) {
        if (!date) return "No data";
        const s = Math.floor((Date.now() - date.getTime()) / 1000);
        if (s < 5)  return "Just now";
        if (s < 60) return `${s}s ago`;
        return `${Math.floor(s / 60)}m ago`;
    }

    /** Call from setInterval to keep "last update" labels fresh. */
    refreshTimestamps() {
        ["PI1", "PI2", "PI3"].forEach((pi) => {
            if (this.lastUpdate[pi]) {
                const secAgo = Math.floor(
                    (Date.now() - this.lastUpdate[pi].getTime()) / 1000
                );
                this._setText(
                    `${pi.toLowerCase()}-last-update`,
                    this._timeAgo(this.lastUpdate[pi])
                );
                this._updatePiStatus(pi, secAgo < 30);
            }
        });
    }
}
