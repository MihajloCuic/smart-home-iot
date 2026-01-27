import json
import time
import os
import sys

try:
    from influxdb_client import InfluxDBClient, Point, WriteOptions
    INFLUX_AVAILABLE = True
except ImportError:
    INFLUX_AVAILABLE = False

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from settings import load_settings


def _normalize_value(value):
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return None


def main():
    settings = load_settings()
    mqtt_cfg = settings.get("mqtt", {})
    influx_cfg = settings.get("influx", {})

    if not MQTT_AVAILABLE:
        print("[SERVER] paho-mqtt not installed.")
        return
    if not INFLUX_AVAILABLE:
        print("[SERVER] influxdb-client not installed.")
        return

    host = mqtt_cfg.get("host", "localhost")
    port = int(mqtt_cfg.get("port", 1883))
    username = mqtt_cfg.get("username")
    password = mqtt_cfg.get("password")
    topic = mqtt_cfg.get("topic", "iot/sensors")

    url = influx_cfg.get("url", "http://localhost:8086")
    token = influx_cfg.get("token", "")
    org = influx_cfg.get("org", "smart-home")
    bucket = influx_cfg.get("bucket", "iot")

    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=WriteOptions(batch_size=500, flush_interval=1000))

    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("[SERVER] MQTT connected")
            client.subscribe(topic)
        else:
            print(f"[SERVER] MQTT connection failed: {rc}")

    def on_message(client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        items = data.get("items") if isinstance(data, dict) else None
        if items is None:
            items = [data]

        points = []
        for item in items:
            if not isinstance(item, dict):
                continue
            device = item.get("device") or data.get("device")
            sensor = item.get("sensor")
            source = item.get("source", "sensor")
            simulated = str(item.get("simulated", False)).lower()
            ts = item.get("ts")

            point = Point("iot")\
                .tag("device", device or "unknown")\
                .tag("sensor", sensor or "unknown")\
                .tag("source", source)\
                .tag("simulated", simulated)

            value = _normalize_value(item.get("value"))
            if value is not None:
                point.field("value", value)
            elif "value" in item:
                point.field("value_str", str(item.get("value")))

            if "alert" in item:
                point.field("alert", 1 if item.get("alert") else 0)

            if ts:
                point.time(int(ts * 1_000_000_000))

            points.append(point)

        if points:
            write_api.write(bucket=bucket, org=org, record=points)

    mqtt_client = mqtt.Client()
    if username:
        mqtt_client.username_pw_set(username, password)

    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    mqtt_client.connect(host, port, 60)
    print("[SERVER] Listening for MQTT data...")
    try:
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.disconnect()
        write_api.flush()
        client.close()


if __name__ == "__main__":
    main()
