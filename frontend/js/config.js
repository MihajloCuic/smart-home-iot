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
    topics: {
        sensors:     "iot/sensors",
        alarmState:  "iot/alarm/state",
        personCount: "iot/home/person_count",
        webCommand:  "iot/web/command",
    },
};
