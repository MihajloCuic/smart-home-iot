/**
 * Smart Home IoT - MQTT WebSocket Client
 * Connects to Mosquitto via WebSocket and dispatches sensor data, alarm state,
 * and person count updates to registered callbacks.
 */
class SmartHomeMQTT {
    constructor(config) {
        this.config = config;
        this.client = null;
        this.connected = false;
        this._callbacks = {
            onConnect:     [],
            onDisconnect:  [],
            onSensorData:  [],
            onAlarmState:  [],
            onPersonCount: [],
        };
    }

    /* -------- connection -------- */

    connect() {
        const url = `ws://${this.config.mqtt.host}:${this.config.mqtt.port}`;
        console.log("[MQTT] Connecting to", url);

        this.client = mqtt.connect(url, {
            keepalive: 30,
            reconnectPeriod: 3000,
            clean: true,
        });

        this.client.on("connect", () => {
            console.log("[MQTT] Connected");
            this.connected = true;
            this.client.subscribe(this.config.topics.sensors);
            this.client.subscribe(this.config.topics.alarmState);
            this.client.subscribe(this.config.topics.personCount);
            this._fire("onConnect");
        });

        this.client.on("close", () => {
            console.log("[MQTT] Disconnected");
            this.connected = false;
            this._fire("onDisconnect");
        });

        this.client.on("error", (err) => {
            console.error("[MQTT] Error:", err);
        });

        this.client.on("message", (topic, payload) => {
            try {
                const data = JSON.parse(payload.toString());
                this._handleMessage(topic, data);
            } catch (e) {
                console.warn("[MQTT] Parse error:", e);
            }
        });
    }

    /* -------- incoming -------- */

    _handleMessage(topic, data) {
        const t = this.config.topics;

        if (topic === t.sensors) {
            // Batch format: { device, batch, items: [...] }
            const items  = data.items || [data];
            const device = data.device;
            items.forEach((item) => {
                item.device = item.device || device;
                this._fire("onSensorData", item);
            });
        } else if (topic === t.alarmState) {
            this._fire("onAlarmState", data);
        } else if (topic === t.personCount) {
            this._fire("onPersonCount", data);
        }
    }

    /* -------- outgoing -------- */

    publishCommand(target, command, params) {
        if (!this.client || !this.connected) {
            console.warn("[MQTT] Not connected, cannot send command");
            return;
        }
        const payload = JSON.stringify({ target, command, params: params || {} });
        this.client.publish(this.config.topics.webCommand, payload);
        console.log(`[MQTT] Command -> ${target}: ${command}`, params);
    }

    /* -------- event helpers -------- */

    on(event, callback) {
        if (this._callbacks[event]) {
            this._callbacks[event].push(callback);
        }
    }

    _fire(event, data) {
        (this._callbacks[event] || []).forEach((cb) => cb(data));
    }
}
