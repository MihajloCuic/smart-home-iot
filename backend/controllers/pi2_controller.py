"""PI2 Controller - Kitchen / Upstairs sensors and actuators"""

import threading
import time

from mqtt_publisher import MQTTBatchPublisher

from components import (
    DoorSensor,
    UltrasonicSensor,
    MotionSensor,
    DHTSensor,
    Button,
    FourDigitDisplay,
    GyroscopeSensor,
)
from controllers.alarm_mqtt_sync import AlarmMQTTSync
from simulators import PI2Simulator


class PI2Controller:
    """
    Controller for PI2 (Kitchen / Upstairs area).

    Components   : DS2, DUS2, DPIR2, DHT3, BTN, 4SD, GSG
    Alarm role   : slave  -  subscribes to alarm state from PI1 (master),
                             publishes DS2 door events and alarm trigger events.

    Rules implemented:
    - Rule 3  : DS2 open > 5 s while DISARMED -> publish alarm trigger to PI1.
    - Rule 4  : DS2 open/close events forwarded to PI1 via MQTT (grace period).
    - Rule 5  : DPIR2 motion + person_count == 0 -> publish alarm trigger to PI1.
    - Rule 6  : GSG significant displacement -> publish alarm trigger to PI1.
    - Rule 7  : DHT3 data published to MQTT; PI3 subscribes and shows on LCD.

    Rules wired – logic added in logic-rules phase:
    - Rule 2a : DPIR2 + DUS2 < threshold -> person entering (+1 count).
    - Rule 2b : CLI command 'o'           -> person exiting  (-1 count).
    - Rule 8  : Kitchen timer on 4SD, BTN adds seconds.
    """

    DOOR_OPEN_ALARM_DELAY = 5   # Rule 3: seconds before trigger if DS2 stays open
    DHT_READ_INTERVAL     = 10  # Rule 7: how often DHT3 is read and published (seconds)

    def __init__(self, settings, mqtt_cfg=None,
                 get_person_count=None, update_person_count=None,
                 set_person_count=None):
        self.settings         = settings
        self.device_info      = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", {})
        alarm_cfg             = settings.get("alarm", {})
        _mqtt_cfg             = mqtt_cfg or {}

        self.components = {}
        self.running    = False
        self.simulator  = None

        self.get_person_count    = get_person_count    or (lambda: 0)
        self.update_person_count = update_person_count
        self.set_person_count    = set_person_count

        # Shared MQTT publisher for sensor / actuator data
        self.publisher = MQTTBatchPublisher(_mqtt_cfg, self.device_info)

        # Rule 3 state: local 5 s timer for DS2 door-open alarm
        self._door_open_timer = None
        self._door_timer_lock = threading.Lock()
        self._door_is_open    = False

        # Rule 8: kitchen timer state
        self._timer_remaining  = 0       # seconds remaining
        self._timer_thread     = None
        self._timer_lock       = threading.Lock()
        self._timer_running    = False
        self._timer_stop_event = threading.Event()

        # Rule 7: background thread that periodically publishes DHT3 for PI3 LCD
        self._dht3_thread = None

        # Alarm sync: PI2 is a slave
        self.alarm_sync = AlarmMQTTSync(
            mqtt_cfg                  = _mqtt_cfg,
            device_id                 = self.device_info.get('id', 'PI2'),
            role                      = 'slave',
            on_state_received         = self._on_alarm_state_received,
            on_person_count_received  = self._on_person_count_received,
            on_web_command            = self._on_web_command,
        )
        self._known_alarm_state = alarm_cfg.get('initial_state', 'DISARMED')

        self._init_components()

    # ========== INIT ==========

    def _init_components(self):
        """Initialise all PI2 components."""
        s = self.sensors_settings

        print("=" * 50)
        print("Initializing PI2 Components...")
        print("=" * 50)

        if "DS2" in s:
            self.components["DS2"] = DoorSensor(
                'DS2', s["DS2"],
                publisher=self.publisher,
                on_change=self._on_door_change,
            )
            self._log_init("DS2")

        if "DUS2" in s:
            self.components["DUS2"] = UltrasonicSensor(
                s["DUS2"],
                publisher=self.publisher,
                code='DUS2',
            )
            self._log_init("DUS2")

        if "DPIR2" in s:
            self.components["DPIR2"] = MotionSensor(
                'DPIR2', s["DPIR2"],
                publisher=self.publisher,
                on_motion=self._on_motion,     # Rule 5
            )
            self._log_init("DPIR2")

        if "DHT3" in s:
            self.components["DHT3"] = DHTSensor(
                'DHT3', s["DHT3"],
                publisher=self.publisher,
            )
            self._log_init("DHT3")

        if "BTN" in s:
            self.components["BTN"] = Button(
                'BTN', s["BTN"],
                publisher=self.publisher,
                on_press=self._on_button_press,   # Rule 8b
            )
            self._log_init("BTN")

        if "4SD" in s:
            self.components["4SD"] = FourDigitDisplay(
                '4SD', s["4SD"],
                publisher=self.publisher,
            )
            self._log_init("4SD")

        if "GSG" in s:
            self.components["GSG"] = GyroscopeSensor(
                'GSG', s["GSG"],
                publisher=self.publisher,
                on_displacement=self._on_displacement,   # Rule 6
            )
            self._log_init("GSG")

        print("=" * 50)

    def _log_init(self, code):
        s    = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    # ========== ALARM SYNC CALLBACK ==========

    def _on_alarm_state_received(self, state):
        """Called by AlarmMQTTSync when PI1 broadcasts a new alarm state."""
        self._known_alarm_state = state
        print(f"[PI2] Alarm state updated -> {state}")

    def _on_person_count_received(self, count):
        """Called by AlarmMQTTSync when PI1 broadcasts absolute person count."""
        if self.set_person_count:
            self.set_person_count(count)
        print(f"[PI2] Person count updated -> {count}")

    # ========== WEB COMMAND HANDLER ==========

    def _on_web_command(self, command, params):
        """
        Handle commands from the web application.
        Commands: 'timer_start', 'timer_add', 'timer_stop'.
        """
        if command == 'timer_start':
            minutes = int(params.get('minutes', 1))
            self._start_kitchen_timer(minutes * 60)
        elif command == 'timer_add':
            seconds = int(params.get('seconds', 30))
            self._add_timer_seconds(seconds)
        elif command == 'timer_stop':
            self._stop_kitchen_timer()
        else:
            print(f"[WEB] Unknown PI2 command: {command}")

    # ========== RULE 8: KITCHEN TIMER ==========

    def _start_kitchen_timer(self, total_seconds):
        """Start or restart the kitchen countdown timer on 4SD."""
        # Stop any existing timer and wait for its thread to finish
        with self._timer_lock:
            self._timer_running = False
        self._timer_stop_event.set()
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=2)
        # Start new timer
        self._timer_stop_event.clear()
        with self._timer_lock:
            self._timer_remaining = max(1, total_seconds)
            self._timer_running = True
        display = self.components.get("4SD")
        if display:
            display.stop_blink()
            display.show_time(self._timer_remaining)
        self._timer_thread = threading.Thread(
            target=self._timer_loop, daemon=True)
        self._timer_thread.start()
        print(f"[TIMER] Started: {total_seconds}s")

    def _add_timer_seconds(self, seconds):
        """Add seconds to the running kitchen timer."""
        with self._timer_lock:
            if self._timer_running:
                self._timer_remaining += seconds
                print(f"[TIMER] Added {seconds}s -> {self._timer_remaining}s remaining")
            else:
                print("[TIMER] Not running, cannot add time")

    def _stop_kitchen_timer(self):
        """Stop the kitchen timer and clear the display."""
        with self._timer_lock:
            was_running = self._timer_running
            self._timer_running = False
        self._timer_stop_event.set()
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=2)
            self._timer_thread = None
        display = self.components.get("4SD")
        if display:
            display.stop_blink()
            display.clear()
        if was_running:
            print("[TIMER] Stopped")

    def _timer_loop(self):
        """Background thread: counts down every second, updates 4SD."""
        display = self.components.get("4SD")
        while not self._timer_stop_event.is_set():
            # Wait 1 second, but wake immediately if stop is signaled
            if self._timer_stop_event.wait(timeout=1.0):
                return
            with self._timer_lock:
                if not self._timer_running:
                    return
                self._timer_remaining -= 1
                remaining = self._timer_remaining
            if remaining <= 0:
                with self._timer_lock:
                    self._timer_running = False
                if display:
                    display.start_blink("0000")
                print("[TIMER] Time's up!")
                return
            if display:
                display.show_time(remaining)

    # ========== SENSOR HOOKS ==========

    def _on_door_change(self, is_open):
        """
        DS2 door state change.
        Rule 3: start local 5 s timer; when expired and door still open
                -> publish alarm trigger to PI1.
        Rule 4: forward open/close event to PI1 for alarm grace-period management.
        """
        print(f"[DS2] Door {'OPEN' if is_open else 'CLOSED'}")
        self._door_is_open = is_open
        self.alarm_sync.publish_door_event(is_open)   # Rule 4: grace period

        if is_open:
            self._start_door_open_timer()
        else:
            self._cancel_door_open_timer()

    def _start_door_open_timer(self):
        with self._door_timer_lock:
            self._cancel_door_open_timer_locked()
            self._door_open_timer = threading.Timer(
                self.DOOR_OPEN_ALARM_DELAY, self._door_open_timeout)
            self._door_open_timer.daemon = True
            self._door_open_timer.start()

    def _cancel_door_open_timer(self):
        with self._door_timer_lock:
            self._cancel_door_open_timer_locked()

    def _cancel_door_open_timer_locked(self):
        if self._door_open_timer is not None:
            self._door_open_timer.cancel()
            self._door_open_timer = None

    def _door_open_timeout(self):
        """Rule 3: DS2 open > 5 s while DISARMED -> publish alarm trigger to PI1."""
        if self._door_is_open and self._known_alarm_state == 'DISARMED':
            print("[DS2] Door open >5s while DISARMED -> triggering alarm")
            self.alarm_sync.publish_trigger(reason='door_open_5s_DS2')

    def _on_motion(self):
        """
        DPIR2 motion hook.
        Rule 2a: update person count via DUS2 (must precede Rule 5 check).
        Rule 5: if person_count == 0 -> publish alarm trigger to PI1.
        """
        print("[DPIR2] Motion detected")
        # --- Rule 2a: update count first ---
        self._update_person_count_from_ultrasonic()
        # --- Rule 5 ---
        if self.get_person_count() == 0 and self._known_alarm_state != 'ALARMING':
            print("[DPIR2] Motion with no occupants -> triggering alarm")
            self.alarm_sync.publish_trigger(reason='motion_no_occupants')

    def _on_button_press(self):
        """
        BTN kitchen button press.
        Rule 8b: adds 30 seconds to the running kitchen timer.
        """
        print("[BTN] Button pressed")
        self._add_timer_seconds(30)

    def _on_displacement(self, delta, accel):
        """
        GSG significant displacement.
        Rule 6: significant movement -> publish alarm trigger to PI1.
        """
        print(f"[GSG] Significant displacement detected (delta={delta:.3f} g)")
        if self._known_alarm_state != 'ALARMING':
            self.alarm_sync.publish_trigger(reason=f'gyroscope_displacement delta={delta:.3f}')

    def _dht3_loop(self):
        """
        Rule 7: periodically read DHT3 and publish to MQTT so PI3 can display it on LCD.
        Runs as a background daemon thread while the controller is active.
        Publishes silently (no console output) to avoid cluttering the PI2 terminal.
        """
        while self.running:
            dht = self.components.get("DHT3")
            if dht:
                dht.read_and_publish(silent=True)
            time.sleep(self.DHT_READ_INTERVAL)

    def _update_person_count_from_ultrasonic(self):
        """
        Rule 2a: if DUS2 reads < threshold when DPIR2 fires -> entering (+1).
        Called from _on_motion in logic-rules phase.
        """
        if self.update_person_count is None:
            return
        dus = self.components.get("DUS2")
        if dus is None:
            return
        dist = dus.measure_and_publish()
        if dist < 0:
            return
        if dist < UltrasonicSensor.ALERT_THRESHOLD_CM:
            self.update_person_count(+1)
            self.alarm_sync.publish_person_delta(+1)
            print(f"[HOME] Person entering (dist={dist:.1f} cm) -> persons: {self.get_person_count()}")

    # ========== LIFECYCLE ==========

    def start(self):
        self.running = True
        self.publisher.start()
        self.alarm_sync.start()

        if "DS2"   in self.components:
            self.components["DS2"].start_monitoring()
        if "DPIR2" in self.components:
            self.components["DPIR2"].start_monitoring()
        if "BTN"   in self.components:
            self.components["BTN"].start_monitoring()
        if "GSG"   in self.components:
            self.components["GSG"].start_monitoring()

        # DUS2: continuous monitoring (publishes distance every 2 s)
        if "DUS2" in self.components:
            self.components["DUS2"].start_monitoring(interval=2.0)

        # Rule 7: start DHT3 publish thread so PI3 LCD receives kitchen temperature
        if "DHT3" in self.components:
            self._dht3_thread = threading.Thread(
                target=self._dht3_loop,
                daemon=True,
            )
            self._dht3_thread.start()

        self.simulator = PI2Simulator(self.components)
        self.simulator.start()

    def stop(self):
        self.running = False
        self._stop_kitchen_timer()
        with self._door_timer_lock:
            self._cancel_door_open_timer_locked()
        if self.simulator:
            self.simulator.stop()
        self.alarm_sync.stop()
        self.publisher.stop()
        for comp in self.components.values():
            if hasattr(comp, 'stop'):
                comp.stop()

    def cleanup(self):
        self.stop()
        for comp in self.components.values():
            comp.cleanup()

    # ========== STATUS ==========

    def get_status(self):
        status = {}
        if "DS2"   in self.components:
            status["DS2"]  = "OPEN" if self.components["DS2"].read() else "CLOSED"
        if "DUS2"  in self.components:
            dist = self.components["DUS2"].measure_distance()
            status["DUS2"] = f"{dist:.1f} cm"
        if "DPIR2" in self.components:
            status["DPIR2"] = "DETECTED" if self.components["DPIR2"].read() else "CLEAR"
        if "BTN"   in self.components:
            status["BTN"]  = "monitoring"
        if "4SD"   in self.components:
            status["4SD"]  = self.components["4SD"].get_display_text()
        if "GSG"   in self.components:
            data = self.components["GSG"].read()
            accel = data.get('accel', {})
            status["GSG"] = (f"ax={accel.get('x', 0):.2f} "
                             f"ay={accel.get('y', 0):.2f} "
                             f"az={accel.get('z', 1):.2f}")
        status["ALARM"]   = self._known_alarm_state
        status["PERSONS"] = self.get_person_count()
        return status

    def show_status(self):
        print("\n" + "=" * 40)
        print("PI2 STATUS")
        print("=" * 40)
        s = self.get_status()
        if "DS2"   in s: print(f"  [DS2]   Door:      {s['DS2']}")
        if "DUS2"  in s: print(f"  [DUS2]  Distance:  {s['DUS2']}")
        if "DPIR2" in s: print(f"  [DPIR2] Motion:    {s['DPIR2']}")
        if "BTN"   in s: print(f"  [BTN]   Button:    {s['BTN']}")
        if "4SD"   in s: print(f"  [4SD]   Display:   {s['4SD']}")
        if "GSG"   in s: print(f"  [GSG]   Accel:     {s['GSG']}")
        print(f"  [ALARM] State:     {s['ALARM']}")
        print(f"  [HOME]  Persons:   {s['PERSONS']}")
        print("=" * 40)

    # ========== COMMANDS ==========

    def handle_command(self, cmd):
        """
        CLI commands:
          s     - status
          7 / 8 - simulate DS2 open / close
          e     - simulate person entering (DUS2 close + DPIR2)
          o     - simulate person exiting  (-1 count)
          9     - simulate motion only (DPIR2, no DUS2) -> Rule 5
          g     - simulate gyroscope significant displacement -> Rule 6
          p     - simulate button press (BTN)
          d     - DUS2 custom distance reading
        """
        if cmd == 's':
            self.show_status()

        # --- Door simulation ---
        elif cmd == '7':
            self.components["DS2"].set_state(True)
            print("[SIM] DS2 -> OPEN")
        elif cmd == '8':
            self.components["DS2"].set_state(False)
            print("[SIM] DS2 -> CLOSED")

        # --- Person counting ---
        elif cmd == 'e':
            if "DUS2" in self.components:
                self.components["DUS2"].set_distance(15.0)
            self.components["DPIR2"].set_motion(True)
            print("[SIM] Person entering – DUS2=15 cm, DPIR2 ON")
            time.sleep(1)
            self.components["DPIR2"].set_motion(False)
            if "DUS2" in self.components:
                self.components["DUS2"].set_distance(200.0)

        elif cmd == 'o':
            if self.update_person_count:
                self.update_person_count(-1)
                self.alarm_sync.publish_person_delta(-1)
                print(f"[SIM] Person exited -> persons: {self.get_person_count()}")
            else:
                print("[SIM] update_person_count not wired (run from main.py)")

        elif cmd == '9':
            # Motion only (no DUS2 close) – for testing Rule 5
            self.components["DPIR2"].set_motion(True)
            print("[SIM] DPIR2 Motion ON (room motion, no person at door)")
            time.sleep(1)
            self.components["DPIR2"].set_motion(False)

        # --- Gyroscope ---
        elif cmd == 'g':
            if "GSG" in self.components:
                self.components["GSG"].inject_significant_move()
            else:
                print("[SIM] GSG not present")

        # --- Button ---
        elif cmd == 'p':
            if "BTN" in self.components:
                self.components["BTN"].inject_press()
            else:
                print("[SIM] BTN not present")

        # --- DUS2 custom distance ---
        elif cmd == 'd':
            try:
                dist = float(input("DUS2 distance (cm): ").strip())
                if "DUS2" in self.components:
                    self.components["DUS2"].set_distance(dist)
                    print(f"[SIM] DUS2 -> {dist:.1f} cm")
            except ValueError:
                print("[SIM] Invalid distance")

        else:
            return None

        return True
