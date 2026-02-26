/**
 * Smart Home IoT - Main Application
 * Wires MQTT client, dashboard, and controls together.
 */
document.addEventListener("DOMContentLoaded", () => {
    const mqttClient = new SmartHomeMQTT(CONFIG);
    const dashboard  = new Dashboard();
    const controls   = new Controls(mqttClient);

    /* -------- connection status -------- */

    mqttClient.on("onConnect", () => {
        const el = document.getElementById("mqtt-status");
        el.textContent = "Connected";
        el.className   = "badge bg-success";
    });

    mqttClient.on("onDisconnect", () => {
        const el = document.getElementById("mqtt-status");
        el.textContent = "Disconnected";
        el.className   = "badge bg-danger";
    });

    /* -------- data handlers -------- */

    mqttClient.on("onSensorData", (item) => dashboard.updateSensor(item));
    mqttClient.on("onAlarmState",  (data) => dashboard.updateAlarmState(data));
    mqttClient.on("onPersonCount", (data) => dashboard.updatePersonCount(data));

    /* -------- Grafana iframes (loaded on accordion open) -------- */

    const grafanaBase = `http://${CONFIG.grafana.host}:${CONFIG.grafana.port}`;
    const iframes = {
        "chart-temp":      { id: "iframe-temperature", uid: "smart-home-temperature", slug: "temperature" },
        "chart-security":  { id: "iframe-security",    uid: "smart-home-security",    slug: "security" },
        "chart-actuators": { id: "iframe-actuators",   uid: "smart-home-actuators",   slug: "actuators" },
    };

    // Lazy-load Grafana iframes when accordion sections open
    document.querySelectorAll(".accordion-collapse").forEach((section) => {
        section.addEventListener("shown.bs.collapse", () => {
            const info = iframes[section.id];
            if (!info) return;
            const iframe = document.getElementById(info.id);
            if (iframe && iframe.src === "about:blank") {
                iframe.src = `${grafanaBase}/d/${info.uid}/${info.slug}?orgId=1&theme=dark&kiosk`;
            }
        });
    });

    // Load the first iframe immediately (temperature is open by default)
    const firstInfo = iframes["chart-temp"];
    if (firstInfo) {
        const iframe = document.getElementById(firstInfo.id);
        if (iframe) {
            iframe.src = `${grafanaBase}/d/${firstInfo.uid}/${firstInfo.slug}?orgId=1&theme=dark&kiosk`;
        }
    }

    /* -------- periodic refresh -------- */

    setInterval(() => dashboard.refreshTimestamps(), 5000);

    /* -------- connect -------- */

    mqttClient.connect();
    console.log("[APP] Smart Home IoT frontend initialized");
});
