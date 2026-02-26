/**
 * Smart Home IoT - Controls
 * Alarm arm/disarm, RGB light, and kitchen timer controls.
 * Sends commands to backend controllers via MQTT.
 */
class Controls {
    constructor(mqttClient) {
        this.mqtt = mqttClient;
        this._bindAlarm();
        this._bindRGB();
        this._bindTimer();
    }

    /* -------- Alarm (PI1) -------- */

    _bindAlarm() {
        const pinInput = document.getElementById("alarm-pin");

        document.getElementById("btn-disarm")?.addEventListener("click", () => {
            const pin = pinInput.value;
            if (!this._validatePin(pin)) return;
            this.mqtt.publishCommand("PI1", "disarm", { pin });
            pinInput.value = "";
        });

        document.getElementById("btn-arm")?.addEventListener("click", () => {
            const pin = pinInput.value;
            if (!this._validatePin(pin)) return;
            this.mqtt.publishCommand("PI1", "arm", { pin });
            pinInput.value = "";
        });

        // Allow Enter key in PIN field
        pinInput?.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                document.getElementById("btn-disarm")?.click();
            }
        });
    }

    _validatePin(pin) {
        if (!pin || pin.length !== 4 || !/^\d{4}$/.test(pin)) {
            this._showToast("Enter a 4-digit PIN", "warning");
            return false;
        }
        return true;
    }

    /* -------- RGB Light (PI3) -------- */

    _bindRGB() {
        document.querySelectorAll("[data-rgb]").forEach((btn) => {
            btn.addEventListener("click", () => {
                const [r, g, b] = btn.dataset.rgb.split(",").map(Number);
                this.mqtt.publishCommand("PI3", "rgb_set", { r, g, b });
                // Immediate preview
                const preview = document.getElementById("rgb-preview");
                if (preview) {
                    preview.style.backgroundColor =
                        `rgb(${r * 255},${g * 255},${b * 255})`;
                }
            });
        });

        document.getElementById("btn-rgb-off")?.addEventListener("click", () => {
            this.mqtt.publishCommand("PI3", "rgb_off", {});
            const preview = document.getElementById("rgb-preview");
            if (preview) preview.style.backgroundColor = "#000";
        });
    }

    /* -------- Kitchen Timer (PI2) -------- */

    _bindTimer() {
        document.getElementById("btn-timer-start")?.addEventListener("click", () => {
            const minutes = parseInt(document.getElementById("timer-minutes").value, 10) || 5;
            this.mqtt.publishCommand("PI2", "timer_start", { minutes });
            this._showToast(`Timer started: ${minutes} min`, "success");
        });

        document.getElementById("btn-timer-add")?.addEventListener("click", () => {
            this.mqtt.publishCommand("PI2", "timer_add", { seconds: 30 });
            this._showToast("Added 30 seconds", "info");
        });

        document.getElementById("btn-timer-stop")?.addEventListener("click", () => {
            this.mqtt.publishCommand("PI2", "timer_stop", {});
            this._showToast("Timer stopped", "warning");
        });
    }

    /* -------- Toast notifications -------- */

    _showToast(message, type) {
        const container = document.getElementById("toast-container");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = `toast align-items-center text-bg-${type} border-0 show`;
        toast.setAttribute("role", "alert");
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">${message}</div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto"
                        data-bs-dismiss="toast"></button>
            </div>`;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    }
}
