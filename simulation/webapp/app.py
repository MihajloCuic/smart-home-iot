"""Simple web app for PI2 alarm + timer control."""

import json
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, request

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

BASE_DIR = Path(__file__).resolve().parent
SETTINGS_PATH = BASE_DIR.parent / "settings.json"

app = Flask(__name__, static_folder="static", template_folder="templates")

state_lock = threading.Lock()
status_state = {
    "alarm": "DISARMED",
    "persons": 0,
    "timer_remaining": 0,
    "timer_running": False,
    "timer_blinking": False,
    "timer_increment": 10,
    "display": "",
    "updated": None,
}

mqtt_client = None
mqtt_topic = "iot/sensors"
cmd_topic = "iot/commands"
pi_id = "PI2"


def load_settings():
    if not SETTINGS_PATH.exists():
        return {}
    return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))


def _update_status(update):
    with state_lock:
        status_state.update(update)
        status_state["updated"] = time.time()


def _parse_payload(payload):
    try:
        data = json.loads(payload)
    except Exception:
        return []

    if isinstance(data, dict) and data.get("batch") and "items" in data:
        return data["items"]
    if isinstance(data, dict):
        return [data]
    return []


def start_mqtt():
    global mqtt_client, mqtt_topic, cmd_topic, pi_id

    if not MQTT_AVAILABLE:
        return

    settings = load_settings()
    mqtt_cfg = settings.get("mqtt", {})
    pi_cfg = settings.get("PI2", {})
    cmd_cfg = pi_cfg.get("mqtt_commands", {})

    mqtt_topic = mqtt_cfg.get("topic", "iot/sensors")
    cmd_topic = cmd_cfg.get("topic", "iot/commands")
    pi_id = pi_cfg.get("device", {}).get("id", "PI2")

    host = mqtt_cfg.get("host", "localhost")
    port = int(mqtt_cfg.get("port", 1883))
    username = mqtt_cfg.get("username")
    password = mqtt_cfg.get("password")

    def on_connect(client, userdata, flags, rc):
        client.subscribe(mqtt_topic)

    def on_message(client, userdata, msg):
        items = _parse_payload(msg.payload.decode("utf-8"))
        for item in items:
            if item.get("device") != pi_id:
                continue
            if item.get("source") == "controller" and item.get("sensor") == "STATUS":
                value = item.get("value", {})
                _update_status(value)
            if item.get("sensor") == "4SD":
                _update_status({"display": item.get("value", "")})

    mqtt_client = mqtt.Client()
    if username:
        mqtt_client.username_pw_set(username, password)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message
    mqtt_client.connect(host, port, 60)
    mqtt_client.loop_start()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    with state_lock:
        return jsonify(status_state)


@app.route("/api/alarm/deactivate", methods=["POST"])
def api_alarm_deactivate():
    publish_command("alarm_off", {})
    return jsonify({"ok": True})


@app.route("/api/timer/set", methods=["POST"])
def api_timer_set():
    payload = request.get_json(silent=True) or {}
    seconds = int(payload.get("seconds", 0))
    publish_command("timer_set", {"seconds": seconds})
    return jsonify({"ok": True})


@app.route("/api/timer/increment", methods=["POST"])
def api_timer_increment():
    payload = request.get_json(silent=True) or {}
    seconds = int(payload.get("seconds", 1))
    publish_command("timer_increment_set", {"seconds": seconds})
    return jsonify({"ok": True})


@app.route("/api/timer/stop", methods=["POST"])
def api_timer_stop():
    publish_command("timer_stop", {})
    return jsonify({"ok": True})


@app.route("/api/timer/add", methods=["POST"])
def api_timer_add():
    payload = request.get_json(silent=True) or {}
    seconds = int(payload.get("seconds", 0))
    publish_command("timer_add", {"seconds": seconds})
    return jsonify({"ok": True})


def publish_command(command, extra):
    if mqtt_client is None:
        return
    payload = {
        "device": pi_id,
        "command": command,
    }
    payload.update(extra)
    mqtt_client.publish(cmd_topic, json.dumps(payload))


if __name__ == "__main__":
    start_mqtt()
    app.run(host="0.0.0.0", port=5000, debug=True)
