"""PI1 Controller - Entrance door sensors and actuators"""

import threading
import time

from mqtt_publisher import MQTTBatchPublisher

from components import (
    DoorSensor,
    DoorLight,
    UltrasonicSensor,
    Buzzer,
    MotionSensor,
    MembraneSwitch,
)
from controllers.alarm_state_machine import AlarmStateMachine
from controllers.alarm_mqtt_sync import AlarmMQTTSync
from simulators import PI1Simulator


class PI1Controller:
    """
    Controller for PI1 (Entrance) - ALARM MASTER.

    Components   : DS1, DL, DUS1, DB, DPIR1, DMS
    Alarm role   : master  -  owns the AlarmStateMachine, DB buzzer, and DMS keypad.
                              broadcasts state changes to PI2/PI3 via MQTT.
                              receives trigger events and DS2 door events from PI2,
                              and trigger events from PI3.

    Rules implemented:
    - Rule 1  : Motion (DPIR1) -> DL on for 10 s; resets on new motion.
    - Rule 2a : DPIR1 + DUS1 < threshold -> person entering (+1 count).
    - Rule 2b : CLI command 'o' -> person exiting (-1 count).
    - Rule 3  : DS1 open > 5 s while DISARMED -> trigger alarm.
                DS2 door events forwarded from PI2 via MQTT.
    - Rule 4  : DMS PIN arms/disarms the alarm state machine.
    - Rule 5  : DPIR1 motion + person_count == 0 -> trigger alarm.
                Triggers from PI2/PI3 received via MQTT also call trigger_alarm().
    """

    MOTION_LIGHT_TIMEOUT  = 10   # Rule 1: seconds light stays on after motion
    DOOR_OPEN_ALARM_DELAY = 5    # Rule 3: seconds before alarm if door stays open

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

        # Rule 1 state
        self._motion_timer = None
        self._motion_lock  = threading.Lock()

        # Rule 3 state: timer for DS1 door-open alarm
        self._door_open_timer   = None
        self._door_timer_lock   = threading.Lock()
        self._door_alarm_active = False

        # Alarm sync: PI1 is the master
        self.alarm_sync = AlarmMQTTSync(
            mqtt_cfg                = _mqtt_cfg,
            device_id               = self.device_info.get('id', 'PI1'),
            role                    = 'master',
            on_trigger_received     = self._on_alarm_trigger_from_mqtt,
            on_door_pi2_received    = self._on_door_pi2_from_mqtt,
            on_person_delta_received= self._on_person_delta_from_mqtt,
            on_web_command          = self._on_web_command,
        )

        # Rule 4: alarm state machine (PI1-owned)
        self.alarm = AlarmStateMachine(
            correct_pin    = alarm_cfg.get("pin", "1234"),
            arm_delay      = alarm_cfg.get("arm_delay", 10),
            grace_period   = alarm_cfg.get("grace_period", 30),
            on_alarm_start = self._start_alarm,
            on_alarm_stop  = self._stop_alarm,
            on_state_change= self.alarm_sync.publish_state,  # broadcast via MQTT
        )

        self._init_components()

    # ========== INIT ==========

    def _init_components(self):
        """Initialise all PI1 components."""
        s = self.sensors_settings

        print("=" * 50)
        print("Initializing PI1 Components...")
        print("=" * 50)

        if "DS1" in s:
            self.components["DS1"] = DoorSensor(
                'DS1', s["DS1"],
                publisher=self.publisher,
                on_change=self._on_door_change,
            )
            self._log_init("DS1")

        if "DL" in s:
            self.components["DL"] = DoorLight(
                'DL', s["DL"],
                publisher=self.publisher,
            )
            self._log_init("DL")

        if "DUS1" in s:
            self.components["DUS1"] = UltrasonicSensor(
                s["DUS1"],
                publisher=self.publisher,
            )
            self._log_init("DUS1")

        if "DB" in s:
            self.components["DB"] = Buzzer(
                'DB', s["DB"],
                publisher=self.publisher,
            )
            self._log_init("DB")

        if "DPIR1" in s:
            self.components["DPIR1"] = MotionSensor(
                'DPIR1', s["DPIR1"],
                publisher=self.publisher,
                on_motion=self._on_motion,     # Rule 1 + Rule 2a + Rule 5
            )
            self._log_init("DPIR1")

        if "DMS" in s:
            self.components["DMS"] = MembraneSwitch(
                'DMS', s["DMS"],
                publisher=self.publisher,
                on_key=self._on_key,           # Rule 4
            )
            self._log_init("DMS")

        print("=" * 50)

    def _log_init(self, code):
        s    = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    # ========== ALARM CALLBACKS ==========

    def _start_alarm(self):
        """Called by AlarmStateMachine when entering ALARMING state."""
        db = self.components.get("DB")
        if db:
            db.start_alarm()

    def _stop_alarm(self):
        """Called by AlarmStateMachine when leaving ALARMING state."""
        db = self.components.get("DB")
        if db:
            db.stop_alarm()

    # ========== ALARM MQTT CALLBACKS ==========

    def _on_alarm_trigger_from_mqtt(self, source, reason):
        """
        Called when PI2 or PI3 published a trigger event.
        Forwards the request to the local AlarmStateMachine.
        """
        print(f"[ALARM] Trigger from {source}: {reason}")
        self.alarm.trigger_alarm()

    def _on_person_delta_from_mqtt(self, source, delta):
        """
        Called when PI2 published a person count delta via MQTT.
        Apply the delta locally and broadcast the new absolute count.
        """
        if self.update_person_count:
            self.update_person_count(delta)
            count = self.get_person_count()
            self.alarm_sync.publish_person_count(count)
            print(f"[HOME] Person count from {source}: {delta:+d} -> persons: {count}")

    def _publish_person_count(self):
        """Broadcast current person count to PI2/PI3 via MQTT."""
        self.alarm_sync.publish_person_count(self.get_person_count())

    def _on_door_pi2_from_mqtt(self, is_open):
        """
        Called when PI2 published a DS2 door state change.
        Forwards to the alarm state machine for Rule 4 grace-period management.
        Rule 3 (5 s timer) is handled locally on PI2; PI2 publishes a trigger
        when the timeout fires, which arrives here via _on_alarm_trigger_from_mqtt.
        """
        if is_open:
            self.alarm.door_opened()
        else:
            self.alarm.door_closed()

    # ========== WEB COMMAND HANDLER ==========

    def _on_web_command(self, command, params):
        """
        Handle commands from the web application.
        Commands: 'arm', 'disarm' - inject PIN keys into the alarm state machine.
        """
        pin = str(params.get('pin', ''))
        if command == 'arm':
            print(f"[WEB] Arm command received")
            for key in pin:
                self.alarm.handle_key(key)
            self.alarm.handle_key('#')
        elif command == 'disarm':
            print(f"[WEB] Disarm command received")
            for key in pin:
                self.alarm.handle_key(key)
            self.alarm.handle_key('#')
        else:
            print(f"[WEB] Unknown PI1 command: {command}")

    # ========== CONTROLLER HOOKS ==========

    def _on_door_change(self, is_open):
        """
        DS1 door state change.
        Rule 3: start 5 s timer.
        Rule 4: notify alarm state machine.
        """
        dl = self.components.get("DL")
        if dl:
            dl.turn_on(reason="door opened") if is_open else dl.turn_off(reason="door closed")

        if is_open:
            self.alarm.door_opened()
            self._start_door_open_timer()
        else:
            self.alarm.door_closed()
            self._cancel_door_open_timer()
            if self._door_alarm_active:
                self._stop_door_alarm()
                print("[DS1] Door closed -> alarm stopped")

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
        """Rule 3: DS1 open > 5 s while DISARMED -> activate buzzer directly."""
        ds = self.components.get("DS1")
        if ds and ds.read():
            if self.alarm.get_state() == AlarmStateMachine.DISARMED:
                print("[DS1] Door open >5s while DISARMED -> alarm")
                self._start_door_alarm()

    def _start_door_alarm(self):
        self._door_alarm_active = True
        db = self.components.get("DB")
        if db:
            db.start_alarm()

    def _stop_door_alarm(self):
        self._door_alarm_active = False
        db = self.components.get("DB")
        if db:
            db.stop_alarm()

    def _on_motion(self):
        """
        DPIR1 motion hook.
        Rule 1: turn DL on, reset 10 s timer.
        Rule 2a: update person count via DUS1.
        Rule 5: if count == 0 after Rule 2a -> trigger alarm.
        """
        dl = self.components.get("DL")
        if dl:
            dl.turn_on(reason="motion detected")
        self._reset_motion_timer()

        # Rule 2a: update count first (must precede Rule 5 check)
        self._update_person_count_from_ultrasonic()

        # Rule 5: no one home -> alarm
        if self.get_person_count() == 0:
            if self.alarm.get_state() != AlarmStateMachine.ALARMING:
                print("[DPIR1] Motion with no occupants -> triggering alarm")
                self.alarm.trigger_alarm()

    def _reset_motion_timer(self):
        with self._motion_lock:
            if self._motion_timer is not None:
                self._motion_timer.cancel()
            self._motion_timer = threading.Timer(
                self.MOTION_LIGHT_TIMEOUT, self._motion_timeout)
            self._motion_timer.daemon = True
            self._motion_timer.start()

    def _motion_timeout(self):
        """Rule 1: 10 s with no new motion -> turn DL off."""
        dl = self.components.get("DL")
        if dl:
            dl.turn_off(reason="motion timeout")

    def _update_person_count_from_ultrasonic(self):
        """
        Rule 2a: if DUS1 reads < ALERT_THRESHOLD_CM when DPIR1 fires,
        someone is approaching from outside -> entering (count + 1).
        """
        if self.update_person_count is None:
            return
        dus = self.components.get("DUS1")
        if dus is None:
            return
        dist = dus.measure_and_publish()
        if dist < 0:
            return
        if dist < UltrasonicSensor.ALERT_THRESHOLD_CM:
            self.update_person_count(+1)
            self._publish_person_count()
            print(f"[HOME] Person entering (dist={dist:.1f} cm) -> persons: {self.get_person_count()}")

    def _on_key(self, key):
        """Rule 4: forward key press to the alarm state machine."""
        self.alarm.handle_key(key)

    # ========== LIFECYCLE ==========

    def start(self):
        self.running = True
        self.publisher.start()
        self.alarm_sync.start()

        for code in ("DS1", "DPIR1", "DMS"):
            if code in self.components:
                self.components[code].start_monitoring()

        # DUS1: continuous monitoring (publishes distance every 2 s)
        if "DUS1" in self.components:
            self.components["DUS1"].start_monitoring(interval=2.0)

        self.simulator = PI1Simulator(self.components)
        self.simulator.start()

    def stop(self):
        self.running = False

        with self._motion_lock:
            if self._motion_timer:
                self._motion_timer.cancel()
                self._motion_timer = None

        with self._door_timer_lock:
            if self._door_open_timer:
                self._door_open_timer.cancel()
                self._door_open_timer = None

        if self._door_alarm_active:
            self._stop_door_alarm()

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
        if "DS1"   in self.components:
            status["DS1"]  = "OPEN" if self.components["DS1"].read() else "CLOSED"
        if "DL"    in self.components:
            status["DL"]   = "ON" if self.components["DL"].is_on() else "OFF"
        if "DUS1"  in self.components:
            dist = self.components["DUS1"].measure_distance()
            status["DUS1"] = f"{dist:.1f} cm"
        if "DB"    in self.components:
            state = "ON" if self.components["DB"].is_on() else "OFF"
            if self.components["DB"].is_alarming():
                state += " (ALARM)"
            status["DB"]   = state
        if "DPIR1" in self.components:
            status["DPIR1"] = "DETECTED" if self.components["DPIR1"].read() else "CLEAR"
        if "DMS"   in self.components:
            status["DMS"]  = self.components["DMS"].last_key or "-"
        status["ALARM"]   = self.alarm.get_state()
        status["PERSONS"] = self.get_person_count()
        return status

    def show_status(self):
        print("\n" + "=" * 40)
        print("PI1 STATUS")
        print("=" * 40)
        s = self.get_status()
        if "DS1"   in s: print(f"  [DS1]   Door:      {s['DS1']}")
        if "DL"    in s: print(f"  [DL]    Light:     {s['DL']}")
        if "DUS1"  in s: print(f"  [DUS1]  Distance:  {s['DUS1']}")
        if "DB"    in s: print(f"  [DB]    Buzzer:    {s['DB']}")
        if "DPIR1" in s: print(f"  [DPIR1] Motion:    {s['DPIR1']}")
        if "DMS"   in s: print(f"  [DMS]   Last key:  {s['DMS']}")
        print(f"  [ALARM] State:     {s['ALARM']}")
        print(f"  [HOME]  Persons:   {s['PERSONS']}")
        print("=" * 40)

    # ========== COMMANDS ==========

    def handle_command(self, cmd):
        """
        CLI commands:
          s          - status
          1/2/3      - DL toggle/on/off
          4/5/6      - DB beep/alarm/stop
          7/8        - simulate DS1 open/close
          9          - raw PIR motion (Rule 1 only)
          e          - simulate person entering (DUS1 close + DPIR1)
          o          - simulate person exiting (-1 count)
          0          - inject DMS keypad keys
        """
        if cmd == 's':
            self.show_status()

        # --- Actuators ---
        elif cmd == '1':
            self.components["DL"].toggle()
        elif cmd == '2':
            self.components["DL"].turn_on()
        elif cmd == '3':
            self.components["DL"].turn_off()
        elif cmd == '4':
            self.components["DB"].beep(0.5)
        elif cmd == '5':
            self.components["DB"].start_alarm()
        elif cmd == '6':
            self.components["DB"].stop_alarm()

        # --- Simulation ---
        elif cmd == '7':
            self.components["DS1"].set_state(True)
            print("[SIM] DS1 -> OPEN")
        elif cmd == '8':
            self.components["DS1"].set_state(False)
            print("[SIM] DS1 -> CLOSED")
        elif cmd == '9':
            self.components["DPIR1"].set_motion(True)
            print("[SIM] DPIR1 Motion ON (raw, no DUS1 change)")
            time.sleep(1)
            self.components["DPIR1"].set_motion(False)
        elif cmd == 'e':
            if "DUS1" in self.components:
                self.components["DUS1"].set_distance(15.0)
            self.components["DPIR1"].set_motion(True)
            print("[SIM] Person entering – DUS1=15 cm, DPIR1 ON")
            time.sleep(1)
            self.components["DPIR1"].set_motion(False)
            if "DUS1" in self.components:
                self.components["DUS1"].set_distance(200.0)
        elif cmd == 'o':
            if self.update_person_count:
                self.update_person_count(-1)
                self._publish_person_count()
                print(f"[SIM] Person exited -> persons: {self.get_person_count()}")
            else:
                print("[SIM] update_person_count not wired (run from main.py)")
        elif cmd == '0':
            keys = input("Keys (e.g. '1234#' to arm/disarm): ").strip()
            for k in keys:
                self.components["DMS"].set_key(k)
            if keys:
                print(f"[SIM] Injected keys: {' '.join(keys)}")

        else:
            return None

        return True
