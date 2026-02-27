/**
 * Smart Home IoT - Configuration
 * Adjust host/port if running on a different machine.
 */
const CONFIG = {
    mqtt: {
        host: window.location.hostname || "localhost",
        port: 9001,
    },
    grafana: {
        host: window.location.hostname || "localhost",
        port: 3000,
    },
    // PI1 camera (mjpg_streamer). Change host to PI1's IP when on real hardware.
    camera: {
        host: window.location.hostname || "localhost",
        port: 8081,
    },
    topics: {
        sensors:     "iot/sensors",
        alarmState:  "iot/alarm/state",
        personCount: "iot/home/person_count",
        webCommand:  "iot/web/command",
    },
};
