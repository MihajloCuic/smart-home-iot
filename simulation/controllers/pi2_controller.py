"""PI2 Controller - Kitchen sensors and actuators (Alarm + Timer)"""

import threading
import time

from mqtt_publisher import MQTTBatchPublisher

from components import (
    DoorSensor,
    UltrasonicSensor,
    MotionSensor,
    KitchenButton,
    DHTSensor,
    SevenSegmentDisplay,
    Gyroscope,
    Buzzer,
)
from controllers.alarm_state_machine import AlarmStateMachine
from simulators import PI2Simulator

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


class PI2Controller:
    """
    Controller for PI2 (Kitchen).

    Rules implemented:
    - Rule 2a: DPIR2 + DUS2 entry/exit detection (updates person count)
    - Rule 6:  GSG movement -> ALARM
    - Rule 8:  Kitchen timer with 4SD display and BTN increment
    """

    ENTRY_EXIT_WINDOW = 3.0  # seconds to correlate DUS2 and DPIR2
    TIMER_TICK_SECONDS = 1.0
    TIMER_BLINK_INTERVAL = 0.5

    def __init__(self, settings, mqtt_cfg=None, get_person_count=None, set_person_count=None):
        self.settings = settings
        self.device_info = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", {})
        alarm_cfg = settings.get("alarm", {})
        timer_cfg = settings.get("timer", {})
        mqtt_cmd_cfg = settings.get("mqtt_commands", {})

        self.components = {}
        self.running = False
        self.simulator = None

        self.get_person_count = get_person_count or (lambda: 0)
        self.set_person_count = set_person_count

        self.publisher = MQTTBatchPublisher(mqtt_cfg or {}, self.device_info)

        self._entry_exit_lock = threading.Lock()
        self._last_motion_ts = None
        self._last_dus_alert_ts = None

        self._timer_lock = threading.Lock()
        self._timer_thread = None
        self._blink_thread = None
        self._blink_active = False

        self.timer_increment_seconds = int(timer_cfg.get("increment_seconds", 10))
        self.timer_remaining = int(timer_cfg.get("initial_seconds", 0))
        self.timer_running = self.timer_remaining > 0

        self._mqtt_cmd_enabled = mqtt_cmd_cfg.get("enabled", True)
        self._mqtt_cmd_topic = mqtt_cmd_cfg.get("topic", "iot/commands")
        self._mqtt_cmd_client = None

        self.alarm = AlarmStateMachine(
            correct_pin=alarm_cfg.get("pin", "1234"),
            arm_delay=alarm_cfg.get("arm_delay", 5),
            grace_period=alarm_cfg.get("grace_period", 30),
            on_alarm_start=self._start_alarm,
            on_alarm_stop=self._stop_alarm,
        )

        self._init_components()

    # ========== INIT ==============

    def _init_components(self):
        s = self.sensors_settings

        print("=" * 50)
        print("Initializing PI2 Components...")
        print("=" * 50)

        if "DS2" in s:
            self.components["DS2"] = DoorSensor(
                'DS2', s["DS2"],
                publisher=self.publisher,
            )
            self._log_init("DS2")

        if "DUS2" in s:
            self.components["DUS2"] = UltrasonicSensor(
                'DUS2', s["DUS2"],
                publisher=self.publisher,
                on_alert=self._on_dus_alert,
            )
            self._log_init("DUS2")

        if "DPIR2" in s:
            self.components["DPIR2"] = MotionSensor(
                'DPIR2', s["DPIR2"],
                publisher=self.publisher,
                on_motion=self._on_motion,
            )
            self._log_init("DPIR2")

        if "BTN" in s:
            self.components["BTN"] = KitchenButton(
                'BTN', s["BTN"],
                publisher=self.publisher,
                on_press=self._on_button_press,
            )
            self._log_init("BTN")

        if "DHT3" in s:
            self.components["DHT3"] = DHTSensor('DHT3', s["DHT3"], publisher=self.publisher)
            self._log_init("DHT3")

        if "4SD" in s:
            self.components["4SD"] = SevenSegmentDisplay('4SD', s["4SD"], publisher=self.publisher)
            self._log_init("4SD")

        if "GSG" in s:
            self.components["GSG"] = Gyroscope(
                'GSG', s["GSG"],
                publisher=self.publisher,
                on_movement=self._on_gyro_movement,
            )
            self._log_init("GSG")

        if "DB" in s:
            self.components["DB"] = Buzzer('DB', s["DB"], publisher=self.publisher)
            self._log_init("DB")

        print("=" * 50)

    def _log_init(self, code):
        s = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    # ========== ALARM CALLBACKS ==========

    def _start_alarm(self):
        db = self.components.get("DB")
        if db:
            db.start_alarm()
        self._publish_status()

    def _stop_alarm(self):
        db = self.components.get("DB")
        if db:
            db.stop_alarm()
        self._publish_status()

    # ========== RULE 2a: ENTRY/EXIT ==========

    def _on_motion(self):
        now = time.monotonic()
        with self._entry_exit_lock:
            if self._last_dus_alert_ts and (now - self._last_dus_alert_ts) <= self.ENTRY_EXIT_WINDOW:
                self._register_entry()
                self._last_dus_alert_ts = None
            else:
                self._last_motion_ts = now

    def _on_dus_alert(self, distance, is_alert):
        if not is_alert:
            return
        now = time.monotonic()
        with self._entry_exit_lock:
            if self._last_motion_ts and (now - self._last_motion_ts) <= self.ENTRY_EXIT_WINDOW:
                self._register_exit()
                self._last_motion_ts = None
            else:
                self._last_dus_alert_ts = now

    def _register_entry(self):
        self._update_person_count(1, reason="ENTRY")

    def _register_exit(self):
        self._update_person_count(-1, reason="EXIT")

    def _update_person_count(self, delta, reason):
        current = self.get_person_count()
        new_count = max(0, current + delta)
        if self.set_person_count:
            self.set_person_count(new_count)
        print(f"[RULE2a] {reason}: persons now {new_count}")
        self._publish_status()

    # ========== RULE 6: GYRO -> ALARM ==========

    def _on_gyro_movement(self):
        if self.alarm.get_state() != AlarmStateMachine.ALARMING:
            print("[RULE6] Gyro movement -> ALARM")
            self.alarm.trigger_alarm()

    # ========== RULE 8: TIMER ==========

    def _on_button_press(self):
        with self._timer_lock:
            if self._blink_active:
                self._blink_active = False
                self.timer_remaining = 0
                self.timer_running = False
                self._show_time_locked(0)
                self._publish_status()
                return

            self.timer_remaining += self.timer_increment_seconds
            self.timer_running = True
            self._show_time_locked(self.timer_remaining)
            self._publish_status()

    def _show_time_locked(self, seconds):
        display = self.components.get("4SD")
        if display:
            display.show(self._format_time(seconds))

    def _format_time(self, seconds):
        minutes = max(0, int(seconds)) // 60
        secs = max(0, int(seconds)) % 60
        return f"{minutes:02d}:{secs:02d}"

    def _timer_loop(self):
        while self.running:
            time.sleep(self.TIMER_TICK_SECONDS)
            with self._timer_lock:
                if not self.timer_running or self._blink_active:
                    continue
                if self.timer_remaining > 0:
                    self.timer_remaining -= 1
                    self._show_time_locked(self.timer_remaining)
                    if self.timer_remaining == 0:
                        self.timer_running = False
                        self._start_blinking_locked()
                self._publish_status()

    def _start_blinking_locked(self):
        if self._blink_active:
            return
        self._blink_active = True
        if self._blink_thread and self._blink_thread.is_alive():
            return
        self._blink_thread = threading.Thread(target=self._blink_loop, daemon=True)
        self._blink_thread.start()

    def _blink_loop(self):
        display = self.components.get("4SD")
        show = True
        while self.running:
            with self._timer_lock:
                if not self._blink_active:
                    break
            if display:
                if show:
                    display.show("00:00")
                else:
                    display.clear()
            show = not show
            time.sleep(self.TIMER_BLINK_INTERVAL)

    def set_timer(self, seconds):
        with self._timer_lock:
            self.timer_remaining = max(0, int(seconds))
            self.timer_running = self.timer_remaining > 0
            self._blink_active = False
            self._show_time_locked(self.timer_remaining)
            self._publish_status()

    def set_timer_increment(self, seconds):
        with self._timer_lock:
            self.timer_increment_seconds = max(1, int(seconds))
            self._publish_status()

    def stop_timer_blink(self):
        """Stop blinking and reset timer to 00:00."""
        with self._timer_lock:
            self._blink_active = False
            self.timer_remaining = 0
            self.timer_running = False
            self._show_time_locked(0)
            self._publish_status()

    # ========== MQTT COMMANDS (WEB APP) ==========

    def _start_mqtt_commands(self, mqtt_cfg):
        if not MQTT_AVAILABLE or not self._mqtt_cmd_enabled:
            return

        host = mqtt_cfg.get("host", "localhost")
        port = int(mqtt_cfg.get("port", 1883))
        username = mqtt_cfg.get("username")
        password = mqtt_cfg.get("password")

        def on_connect(client, userdata, flags, rc):
            client.subscribe(self._mqtt_cmd_topic)

        def on_message(client, userdata, msg):
            try:
                import json
                payload = json.loads(msg.payload.decode("utf-8"))
            except Exception:
                return
            if payload.get("device") != self.device_info.get("id"):
                return

            command = payload.get("command")
            if command == "alarm_off":
                self.alarm.force_disarm()
                self._publish_status()
            elif command == "timer_set":
                self.set_timer(payload.get("seconds", 0))
            elif command == "timer_increment_set":
                self.set_timer_increment(payload.get("seconds", self.timer_increment_seconds))
            elif command == "timer_stop":
                self.stop_timer_blink()

        self._mqtt_cmd_client = mqtt.Client()
        if username:
            self._mqtt_cmd_client.username_pw_set(username, password)
        self._mqtt_cmd_client.on_connect = on_connect
        self._mqtt_cmd_client.on_message = on_message
        self._mqtt_cmd_client.connect(host, port, 60)
        self._mqtt_cmd_client.loop_start()

    # ========== STATUS ==========

    def _publish_status(self):
        payload = {
            "device": self.device_info.get("id", "PI2"),
            "source": "controller",
            "sensor": "STATUS",
            "value": {
                "alarm": self.alarm.get_state(),
                "persons": self.get_person_count(),
                "timer_remaining": self.timer_remaining,
                "timer_running": self.timer_running,
                "timer_blinking": self._blink_active,
                "timer_increment": self.timer_increment_seconds,
            },
            "ts": time.time(),
        }
        self.publisher.enqueue(payload)

    def publish_status(self):
        """Public wrapper for status publishing (used by main loop)."""
        self._publish_status()

    # ========== LIFECYCLE ==========

    def start(self):
        self.running = True
        self.publisher.start()

        for code in ["DS2", "DUS2", "DPIR2", "BTN"]:
            if code in self.components:
                if code == "DUS2":
                    self.components[code].start_monitoring(interval=2.0)
                else:
                    self.components[code].start_monitoring()

        if "4SD" in self.components:
            with self._timer_lock:
                self._show_time_locked(self.timer_remaining)

        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

        self._start_mqtt_commands(self.publisher.config)

        self.simulator = PI2Simulator(self.components)
        self.simulator.start()

        self._publish_status()

    def stop(self):
        self.running = False
        if self.simulator:
            self.simulator.stop()
        self.publisher.stop()

        if self._mqtt_cmd_client:
            self._mqtt_cmd_client.loop_stop()
            self._mqtt_cmd_client.disconnect()

        for comp in self.components.values():
            if hasattr(comp, 'stop'):
                comp.stop()

    def cleanup(self):
        self.stop()
        for comp in self.components.values():
            comp.cleanup()

    # ========== STATUS (CLI) ==========

    def get_status(self):
        status = {}

        if "DS2" in self.components:
            status["DS2"] = "OPEN" if self.components["DS2"].read() else "CLOSED"
        if "DUS2" in self.components:
            dist = self.components["DUS2"].measure_distance()
            status["DUS2"] = f"{dist:.1f} cm"
        if "DPIR2" in self.components:
            status["DPIR2"] = "DETECTED" if self.components["DPIR2"].read() else "CLEAR"
        if "BTN" in self.components:
            status["BTN"] = "ready"
        if "DHT3" in self.components:
            t, h = self.components["DHT3"].read()
            status["DHT3"] = f"{t:.1f}C {h:.0f}%"
        if "4SD" in self.components:
            status["4SD"] = self.components["4SD"].get_value()
        if "GSG" in self.components:
            status["GSG"] = "monitoring"
        if "DB" in self.components:
            state = "ON" if self.components["DB"].is_on() else "OFF"
            if self.components["DB"].is_alarming():
                state += " (ALARM)"
            status["DB"] = state

        status["ALARM"] = self.alarm.get_state()
        status["PERSONS"] = self.get_person_count()
        status["TIMER_REMAINING"] = self.timer_remaining
        status["TIMER_INCREMENT"] = self.timer_increment_seconds

        return status

    def show_status(self):
        print("\n" + "=" * 40)
        print("PI2 STATUS")
        print("=" * 40)
        status = self.get_status()
        if "DS2" in status: print(f"  [DS2]   Door:      {status['DS2']}")
        if "DUS2" in status: print(f"  [DUS2]  Distance:  {status['DUS2']}")
        if "DPIR2" in status: print(f"  [DPIR2] Motion:    {status['DPIR2']}")
        if "BTN" in status: print(f"  [BTN]   Button:    {status['BTN']}")
        if "DHT3" in status: print(f"  [DHT3]  Temp/Hum:  {status['DHT3']}")
        if "4SD" in status: print(f"  [4SD]   Display:   {status['4SD']}")
        if "GSG" in status: print(f"  [GSG]   Gyro:      {status['GSG']}")
        if "DB" in status: print(f"  [DB]    Buzzer:    {status['DB']}")
        print(f"  [ALARM] State:     {status['ALARM']}")
        print(f"  [HOME]  Persons:   {status['PERSONS']}")
        print(f"  [TIMER] Remain:    {status['TIMER_REMAINING']}s")
        print(f"  [TIMER] Increment: {status['TIMER_INCREMENT']}s")
        print("=" * 40)

    # ========== COMMANDS ==========

    def handle_command(self, cmd):
        if cmd == 's':
            self.show_status()

        elif cmd == '5' and "DB" in self.components:
            self.components["DB"].start_alarm()
        elif cmd == '6' and "DB" in self.components:
            self.components["DB"].stop_alarm()

        elif cmd == '7' and "DS2" in self.components:
            self.components["DS2"].set_state(True)
            print("[SIM] Door -> OPEN")
        elif cmd == '8' and "DS2" in self.components:
            self.components["DS2"].set_state(False)
            print("[SIM] Door -> CLOSED")
        elif cmd == '9' and "DPIR2" in self.components:
            self.components["DPIR2"].set_motion(True)
            print("[SIM] Motion ON")
            time.sleep(1)
            self.components["DPIR2"].set_motion(False)
        elif cmd == 'u' and "DUS2" in self.components:
            try:
                dist = float(input("Distance (cm): ").strip())
            except ValueError:
                print("Invalid distance")
                return True
            self.components["DUS2"].set_distance(dist)
            print(f"[SIM] DUS2 distance -> {dist:.1f} cm")
        elif cmd == 'k' and "BTN" in self.components:
            self.components["BTN"].press()
        elif cmd == 'g' and "GSG" in self.components:
            self.components["GSG"].trigger_movement()
        elif cmd == 't':
            try:
                seconds = int(input("Timer seconds: ").strip())
            except ValueError:
                print("Invalid seconds")
                return True
            self.set_timer(seconds)
        elif cmd == 'i':
            try:
                seconds = int(input("BTN increment seconds: ").strip())
            except ValueError:
                print("Invalid seconds")
                return True
            self.set_timer_increment(seconds)
        else:
            return None

        return True
