import json
import time
import queue
import multiprocessing

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


def _publisher_process(config, device_info, q):
    if not MQTT_AVAILABLE:
        print("[MQTT] paho-mqtt not installed. Publisher stopped.")
        return

    host = config.get("host", "localhost")
    port = int(config.get("port", 1883))
    username = config.get("username")
    password = config.get("password")
    topic = config.get("topic", "iot/sensors")
    qos = int(config.get("qos", 1))
    batch_interval = float(config.get("batch_interval", 2.0))
    max_batch = int(config.get("max_batch", 50))

    client = mqtt.Client()
    if username:
        client.username_pw_set(username, password)

    try:
        client.connect(host, port, 60)
    except Exception as exc:
        print(f"[MQTT] Connection failed: {exc}")
        return

    client.loop_start()

    batch = []
    last_flush = time.monotonic()

    def flush():
        nonlocal batch, last_flush
        if not batch:
            return
        payload = json.dumps({
            "device": device_info.get("id"),
            "batch": True,
            "items": batch,
        })
        client.publish(topic, payload, qos=qos)
        batch = []
        last_flush = time.monotonic()

    try:
        while True:
            try:
                item = q.get(timeout=0.2)
            except queue.Empty:
                item = None

            if item is None:
                if time.monotonic() - last_flush >= batch_interval:
                    flush()
                continue

            if item == "__STOP__":
                flush()
                break

            batch.append(item)
            if len(batch) >= max_batch:
                flush()
            elif time.monotonic() - last_flush >= batch_interval:
                flush()
    finally:
        try:
            client.loop_stop()
            client.disconnect()
        except Exception:
            pass


class MQTTBatchPublisher:
    def __init__(self, config, device_info):
        self.config = config or {}
        self.device_info = device_info or {}
        self.enabled = bool(self.config.get("enabled", True))
        self._queue = multiprocessing.Queue(maxsize=1000)
        self._process = None

    def start(self):
        if not self.enabled:
            return
        self._process = multiprocessing.Process(
            target=_publisher_process,
            args=(self.config, self.device_info, self._queue),
            daemon=True
        )
        self._process.start()

    def enqueue(self, item):
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(item)
        except Exception:
            pass

    def stop(self):
        if self._process and self._process.is_alive():
            try:
                self._queue.put_nowait("__STOP__")
            except Exception:
                pass
            self._process.join(timeout=2)
