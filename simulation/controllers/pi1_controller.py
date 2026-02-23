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
from simulators import PI1Simulator


class PI1Controller:
    """
    Controller for PI1 (Entrance).

    Responsibilities:
    - Creates the MQTT publisher and injects it into every component
    - Wires up inter-component automation via hooks
    - Handles user CLI commands
    - Starts / stops monitoring and the simulator

    Rules implemented:
    - Rule 1: Motion detected -> light on for 10 seconds (resets on new motion)
    - Rule 3: Door open >5s while DISARMED -> trigger alarm
    - Rule 4: PIN keypad arms/disarms the security system
    - Rule 5: Motion detected with person_count==0 -> trigger alarm
    """

    MOTION_LIGHT_TIMEOUT  = 10   # Rule 1: seconds light stays on after motion
    DOOR_OPEN_ALARM_DELAY = 5    # Rule 3: seconds before alarm if door stays open

    def __init__(self, settings, mqtt_cfg=None, get_person_count=None):
        self.settings = settings
        self.device_info = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", {})
        alarm_cfg = settings.get("alarm", {})

        self.components = {}
        self.running = False
        self.simulator = None

        # get_person_count is a callable returning the current occupant count
        # Defaults to always-zero (alarm fires on any motion) if not provided
        self.get_person_count = get_person_count or (lambda: 0)

        # Publisher shared with all components
        self.publisher = MQTTBatchPublisher(mqtt_cfg or {}, self.device_info)

        # Rule 1 state: timer turns light off after MOTION_LIGHT_TIMEOUT seconds
        self._motion_timer = None
        self._motion_lock  = threading.Lock()

        # Rule 3 state: timer triggers alarm if door stays open too long
        self._door_open_timer = None
        self._door_timer_lock = threading.Lock()

        # Rule 4: alarm state machine (also handles Rule 3 and Rule 5 alarms)
        self.alarm = AlarmStateMachine(
            correct_pin=alarm_cfg.get("pin", "1234"),
            arm_delay=alarm_cfg.get("arm_delay", 5),
            grace_period=alarm_cfg.get("grace_period", 30),
            on_alarm_start=self._start_alarm,
            on_alarm_stop=self._stop_alarm,
        )

        self._init_components()

    # ========== INIT ==========

    def _init_components(self):
        """Initialize all PI1 components and inject publisher + hooks"""
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
                on_motion=self._on_motion,      # Rule 1 + Rule 5
            )
            self._log_init("DPIR1")

        if "DMS" in s:
            self.components["DMS"] = MembraneSwitch(
                'DMS', s["DMS"],
                publisher=self.publisher,
                on_key=self._on_key,            # Rule 4
            )
            self._log_init("DMS")

        print("=" * 50)

    def _log_init(self, code):
        s = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    # ========== ALARM CALLBACKS ==========

    def _start_alarm(self):
        """Called by AlarmStateMachine when alarm begins"""
        db = self.components.get("DB")
        if db:
            db.start_alarm()

    def _stop_alarm(self):
        """Called by AlarmStateMachine when alarm is stopped"""
        db = self.components.get("DB")
        if db:
            db.stop_alarm()

    # ========== CONTROLLER-LEVEL HOOKS ==========

    def _on_door_change(self, is_open):
        """
        Door state change hook.
        Implements:
          - Basic: light follows door (existing behavior)
          - Rule 3: start 5s timer if door opens while DISARMED
          - Rule 4: notify alarm state machine (ARMED -> GRACE on open)
        """
        # Basic: light follows door
        dl = self.components.get("DL")
        if dl:
            if is_open:
                dl.turn_on(reason="door opened")
            else:
                dl.turn_off(reason="door closed")

        # Rule 4: notify alarm state machine
        if is_open:
            self.alarm.door_opened()
        else:
            self.alarm.door_closed()

        # Rule 3: start/cancel the 5s door-open timer
        if is_open:
            self._start_door_open_timer()
        else:
            self._cancel_door_open_timer()

    def _start_door_open_timer(self):
        """Rule 3: start 5s countdown; fires if door still open"""
        with self._door_timer_lock:
            self._cancel_door_open_timer_locked()
            self._door_open_timer = threading.Timer(
                self.DOOR_OPEN_ALARM_DELAY,
                self._door_open_timeout
            )
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
        """
        Rule 3: fires DOOR_OPEN_ALARM_DELAY seconds after door opened.
        Triggers alarm only if door is still open AND system is DISARMED.
        (If ARMED, the GRACE period already handles this via door_opened().)
        """
        ds = self.components.get("DS1")
        if ds and ds.read():
            state = self.alarm.get_state()
            if state == AlarmStateMachine.DISARMED:
                print("[RULE3] Door open >5s while DISARMED -> triggering alarm")
                self.alarm.trigger_alarm()

    def _on_motion(self):
        """
        Motion sensor hook.
        Implements:
          - Rule 1: turn light on, reset 10s off-timer
          - Rule 5: if person_count == 0 -> trigger alarm
        """
        # Rule 1: turn light on + reset 10s timer
        dl = self.components.get("DL")
        if dl:
            dl.turn_on(reason="motion detected")
        self._reset_motion_timer()

        # Rule 5: no one home -> alarm
        if self.get_person_count() == 0:
            state = self.alarm.get_state()
            if state != AlarmStateMachine.ALARMING:
                print("[RULE5] Motion detected with no occupants -> triggering alarm")
                self.alarm.trigger_alarm()

    def _reset_motion_timer(self):
        """Rule 1: cancel existing off-timer and start a new 10s countdown"""
        with self._motion_lock:
            if self._motion_timer is not None:
                self._motion_timer.cancel()
            self._motion_timer = threading.Timer(
                self.MOTION_LIGHT_TIMEOUT,
                self._motion_timeout
            )
            self._motion_timer.daemon = True
            self._motion_timer.start()

    def _motion_timeout(self):
        """Rule 1: 10s with no new motion - turn light off"""
        dl = self.components.get("DL")
        if dl:
            dl.turn_off(reason="motion timeout")

    def _on_key(self, key):
        """Rule 4: forward all key presses to the alarm state machine"""
        self.alarm.handle_key(key)

    # ========== LIFECYCLE ==========

    def start(self):
        """Start publisher, sensor monitoring, and simulator"""
        self.running = True
        self.publisher.start()

        for code in ["DS1", "DUS1", "DPIR1", "DMS"]:
            if code in self.components:
                if code == "DUS1":
                    self.components[code].start_monitoring(interval=2.0)
                else:
                    self.components[code].start_monitoring()

        self.simulator = PI1Simulator(self.components)
        self.simulator.start()

    def stop(self):
        """Stop all monitoring threads and publisher"""
        self.running = False

        # Cancel any pending timers
        with self._motion_lock:
            if self._motion_timer:
                self._motion_timer.cancel()
                self._motion_timer = None
        with self._door_timer_lock:
            if self._door_open_timer:
                self._door_open_timer.cancel()
                self._door_open_timer = None

        if self.simulator:
            self.simulator.stop()
        self.publisher.stop()
        for comp in self.components.values():
            if hasattr(comp, 'stop'):
                comp.stop()

    def cleanup(self):
        """Stop everything and release GPIO resources"""
        self.stop()
        for comp in self.components.values():
            comp.cleanup()

    # ========== STATUS ==========

    def get_status(self):
        """Return a dict with human-readable status for each component"""
        status = {}

        if "DS1" in self.components:
            status["DS1"] = "OPEN" if self.components["DS1"].read() else "CLOSED"
        if "DL" in self.components:
            status["DL"] = "ON" if self.components["DL"].is_on() else "OFF"
        if "DUS1" in self.components:
            dist = self.components["DUS1"].measure_distance()
            status["DUS1"] = f"{dist:.1f} cm"
        if "DB" in self.components:
            state = "ON" if self.components["DB"].is_on() else "OFF"
            if self.components["DB"].is_alarming():
                state += " (ALARM)"
            status["DB"] = state
        if "DPIR1" in self.components:
            status["DPIR1"] = "DETECTED" if self.components["DPIR1"].read() else "CLEAR"
        if "DMS" in self.components:
            status["DMS"] = self.components["DMS"].last_key or "-"

        status["ALARM"]   = self.alarm.get_state()
        status["PERSONS"] = self.get_person_count()

        return status

    def show_status(self):
        """Print status table to console"""
        print("\n" + "=" * 40)
        print("PI1 STATUS")
        print("=" * 40)
        status = self.get_status()
        if "DS1"   in status: print(f"  [DS1]   Door:      {status['DS1']}")
        if "DL"    in status: print(f"  [DL]    Light:     {status['DL']}")
        if "DUS1"  in status: print(f"  [DUS1]  Distance:  {status['DUS1']}")
        if "DB"    in status: print(f"  [DB]    Buzzer:    {status['DB']}")
        if "DPIR1" in status: print(f"  [DPIR1] Motion:    {status['DPIR1']}")
        if "DMS"   in status: print(f"  [DMS]   Last key:  {status['DMS']}")
        print(f"  [ALARM] State:     {status['ALARM']}")
        print(f"  [HOME]  Persons:   {status['PERSONS']}")
        print("=" * 40)

    # ========== COMMANDS ==========

    def handle_command(self, cmd):
        """
        Handle a CLI command.
        Returns True on success, None if command is unknown.
        Components handle their own printing and publishing.
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

        # --- Simulation overrides ---
        elif cmd == '7':
            self.components["DS1"].set_state(True)
            print("[SIM] Door -> OPEN")
        elif cmd == '8':
            self.components["DS1"].set_state(False)
            print("[SIM] Door -> CLOSED")
        elif cmd == '9':
            self.components["DPIR1"].set_motion(True)
            print("[SIM] Motion ON")
            time.sleep(1)
            self.components["DPIR1"].set_motion(False)
        elif cmd == '0':
            key = input("Key (0-9, A-D, *, #): ").strip()
            if key:
                self.components["DMS"].set_key(key)
                print(f"[SIM] Injected key '{key}'")

        else:
            return None  # Unknown command

        return True
