"""PI3 Controller - Bedroom sensors and actuators"""

import threading
import time

from mqtt_publisher import MQTTBatchPublisher

from components import (
    DoorSensor,
    DoorLight,
    Buzzer,
    MotionSensor,
    MembraneSwitch,
    DHTSensor,
    LCDDisplay,
    IRReceiver,
    RGBLight,
)
from controllers.alarm_state_machine import AlarmStateMachine
from simulators import PI3Simulator


class PI3Controller:
    """
    Controller for PI3 (Bedroom).

    Responsibilities:
    - Creates the MQTT publisher and injects it into every component
    - Wires up inter-component automation via hooks
    - Handles user CLI commands
    - Starts / stops monitoring and the simulator

    Rules implemented:
    - Rule 1:  Motion detected -> light on for 10 seconds (resets on new motion)
    - Rule 3:  Door open >5s while DISARMED -> trigger alarm
    - Rule 4:  PIN keypad arms/disarms the security system
    - Rule 5:  Motion detected with person_count==0 -> trigger alarm
    - Rule 7:  LCD cycles DHT1 / DHT2 readings every 3 seconds
    - Rule 9:  IR remote control codes set RGB light color
    """

    MOTION_LIGHT_TIMEOUT  = 10   # Rule 1: seconds light stays on after motion
    DOOR_OPEN_ALARM_DELAY = 5    # Rule 3: seconds before alarm if door stays open
    LCD_CYCLE_INTERVAL    = 3    # Rule 7: seconds between DHT display cycles

    # Rule 9: IR code string -> action mapping
    IR_CODE_TOGGLE = 'TOGGLE'
    IR_CODE_RED    = 'RED'
    IR_CODE_GREEN  = 'GREEN'
    IR_CODE_BLUE   = 'BLUE'

    def __init__(self, settings, mqtt_cfg=None, get_person_count=None, set_person_count=None):
        self.settings = settings
        self.device_info = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", {})
        alarm_cfg = settings.get("alarm", {})

        self.components = {}
        self.running = False
        self.simulator = None

        # get_person_count is a callable returning the current occupant count
        self.get_person_count = get_person_count or (lambda: 0)
        self.set_person_count = set_person_count

        # Publisher shared with all components
        self.publisher = MQTTBatchPublisher(mqtt_cfg or {}, self.device_info)

        # Rule 1 state
        self._motion_timer = None
        self._motion_lock  = threading.Lock()

        # Rule 3 state
        self._door_open_timer = None
        self._door_timer_lock = threading.Lock()

        # Rule 7 state
        self._lcd_thread    = None
        self._lcd_dht_index = 0   # toggles between DHT1 and DHT2

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
        """Initialize all PI3 components and inject publisher + hooks"""
        s = self.sensors_settings

        print("=" * 50)
        print("Initializing PI3 Components...")
        print("=" * 50)

        if "DS2" in s:
            self.components["DS2"] = DoorSensor(
                'DS2', s["DS2"],
                publisher=self.publisher,
                on_change=self._on_door_change,
            )
            self._log_init("DS2")

        if "DL1" in s:
            self.components["DL1"] = DoorLight(
                'DL1', s["DL1"],
                publisher=self.publisher,
            )
            self._log_init("DL1")

        if "DB" in s:
            self.components["DB"] = Buzzer(
                'DB', s["DB"],
                publisher=self.publisher,
            )
            self._log_init("DB")

        if "DPIR3" in s:
            self.components["DPIR3"] = MotionSensor(
                'DPIR3', s["DPIR3"],
                publisher=self.publisher,
                on_motion=self._on_motion,      # Rule 1 + Rule 5
            )
            self._log_init("DPIR3")

        if "DMS" in s:
            self.components["DMS"] = MembraneSwitch(
                'DMS', s["DMS"],
                publisher=self.publisher,
                on_key=self._on_key,            # Rule 4
            )
            self._log_init("DMS")

        if "DHT1" in s:
            self.components["DHT1"] = DHTSensor('DHT1', s["DHT1"], publisher=self.publisher)
            self._log_init("DHT1")

        if "DHT2" in s:
            self.components["DHT2"] = DHTSensor('DHT2', s["DHT2"], publisher=self.publisher)
            self._log_init("DHT2")

        if "LCD" in s:
            self.components["LCD"] = LCDDisplay('LCD', s["LCD"], publisher=self.publisher)
            self._log_init("LCD")

        if "IR" in s:
            self.components["IR"] = IRReceiver(
                'IR', s["IR"],
                publisher=self.publisher,
                on_code=self._on_ir_code,       # Rule 9
            )
            self._log_init("IR")

        if "BRGB" in s:
            self.components["BRGB"] = RGBLight('BRGB', s["BRGB"], publisher=self.publisher)
            self._log_init("BRGB")

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
          - Basic: light follows door
          - Rule 3: start 5s timer if door opens while DISARMED
          - Rule 4: notify alarm state machine (ARMED -> GRACE on open)
        """
        # Basic: light follows door
        dl = self.components.get("DL1")
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
        """Rule 3: fires 5s after door opened; alarm if DISARMED and door still open"""
        ds = self.components.get("DS2")
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
        dl = self.components.get("DL1")
        if dl:
            dl.turn_on(reason="motion detected")
        self._reset_motion_timer()

        # Rule 5: no one home -> alarm
        if self.get_person_count() == 0:
            state = self.alarm.get_state()
            if state != AlarmStateMachine.ALARMING:
                print("[RULE5] Motion with no occupants -> triggering alarm")
                self.alarm.trigger_alarm()

    def _reset_motion_timer(self):
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
        dl = self.components.get("DL1")
        if dl:
            dl.turn_off(reason="motion timeout")

    def _on_key(self, key):
        """Rule 4: forward all key presses to the alarm state machine"""
        self.alarm.handle_key(key)

    def _on_ir_code(self, code):
        """
        Rule 9: IR remote control sets RGB light color.
        TOGGLE -> toggle on/off (restores last color if turning on)
        RED    -> set red
        GREEN  -> set green
        BLUE   -> set blue
        """
        rgb = self.components.get("BRGB")
        if rgb is None:
            return

        if code == self.IR_CODE_TOGGLE:
            if rgb.is_on():
                rgb.turn_off()
            else:
                # Restore last known color; defaults to white if never set
                rgb.set_color(*rgb.get_last_color())
        elif code == self.IR_CODE_RED:
            rgb.set_red()
        elif code == self.IR_CODE_GREEN:
            rgb.set_green()
        elif code == self.IR_CODE_BLUE:
            rgb.set_blue()
        else:
            print(f"[IR] Unknown code: '{code}' - no action")

    # ========== RULE 7: LCD DHT CYCLING ==========

    def _lcd_cycle_loop(self):
        """
        Rule 7: Background thread.
        Every LCD_CYCLE_INTERVAL seconds alternates showing DHT1 and DHT2
        readings on the LCD.
        """
        dht_keys = ['DHT1', 'DHT2']
        while self.running:
            key = dht_keys[self._lcd_dht_index % 2]
            dht = self.components.get(key)
            lcd = self.components.get("LCD")

            if dht and lcd:
                temp, humidity = dht.read()
                line1 = f"{key}: {temp:.1f}C {humidity:.0f}%"
                lcd.show(line1)

            self._lcd_dht_index += 1
            time.sleep(self.LCD_CYCLE_INTERVAL)

    # ========== LIFECYCLE ==========

    def start(self):
        """Start publisher, sensor monitoring, and simulator"""
        self.running = True
        self.publisher.start()

        # Start monitoring sensors
        for code in ["DS2", "DPIR3", "DMS"]:
            if code in self.components:
                self.components[code].start_monitoring()

        if "IR" in self.components:
            self.components["IR"].start_monitoring()

        # Rule 7: start LCD cycle thread if LCD and at least one DHT present
        if "LCD" in self.components and ("DHT1" in self.components or "DHT2" in self.components):
            self._lcd_thread = threading.Thread(
                target=self._lcd_cycle_loop,
                daemon=True
            )
            self._lcd_thread.start()

        self.simulator = PI3Simulator(self.components)
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

        if "DS2" in self.components:
            status["DS2"] = "OPEN" if self.components["DS2"].read() else "CLOSED"
        if "DL1" in self.components:
            status["DL1"] = "ON" if self.components["DL1"].is_on() else "OFF"
        if "DB" in self.components:
            s = "ON" if self.components["DB"].is_on() else "OFF"
            if self.components["DB"].is_alarming():
                s += " (ALARM)"
            status["DB"] = s
        if "DPIR3" in self.components:
            status["DPIR3"] = "DETECTED" if self.components["DPIR3"].read() else "CLEAR"
        if "DMS" in self.components:
            status["DMS"] = self.components["DMS"].last_key or "-"
        if "DHT1" in self.components:
            t, h = self.components["DHT1"].read()
            status["DHT1"] = f"{t:.1f}C {h:.0f}%"
        if "DHT2" in self.components:
            t, h = self.components["DHT2"].read()
            status["DHT2"] = f"{t:.1f}C {h:.0f}%"
        if "BRGB" in self.components:
            r, g, b = self.components["BRGB"].get_color()
            status["BRGB"] = f"R={r} G={g} B={b}"
        if "IR" in self.components:
            status["IR"] = "monitoring"

        status["ALARM"]   = self.alarm.get_state()
        status["PERSONS"] = self.get_person_count()

        return status

    def show_status(self):
        """Print status table to console"""
        print("\n" + "=" * 40)
        print("PI3 STATUS")
        print("=" * 40)
        status = self.get_status()
        if "DS2"   in status: print(f"  [DS2]   Door:      {status['DS2']}")
        if "DL1"   in status: print(f"  [DL1]   Light:     {status['DL1']}")
        if "DB"    in status: print(f"  [DB]    Buzzer:    {status['DB']}")
        if "DPIR3" in status: print(f"  [DPIR3] Motion:    {status['DPIR3']}")
        if "DMS"   in status: print(f"  [DMS]   Last key:  {status['DMS']}")
        if "DHT1"  in status: print(f"  [DHT1]  Temp/Hum:  {status['DHT1']}")
        if "DHT2"  in status: print(f"  [DHT2]  Temp/Hum:  {status['DHT2']}")
        if "BRGB"  in status: print(f"  [BRGB]  RGB:       {status['BRGB']}")
        if "IR"    in status: print(f"  [IR]    Receiver:  {status['IR']}")
        print(f"  [ALARM] State:     {status['ALARM']}")
        print(f"  [HOME]  Persons:   {status['PERSONS']}")
        print("=" * 40)

    # ========== COMMANDS ==========

    def handle_command(self, cmd):
        """
        Handle a CLI command.
        Returns True on success, None if command is unknown.
        """

        if cmd == 's':
            self.show_status()

        # --- Actuators ---
        elif cmd == '1':
            self.components["DL1"].toggle()
        elif cmd == '2':
            self.components["DL1"].turn_on()
        elif cmd == '3':
            self.components["DL1"].turn_off()
        elif cmd == '4':
            self.components["DB"].beep(0.5)
        elif cmd == '5':
            self.components["DB"].start_alarm()
        elif cmd == '6':
            self.components["DB"].stop_alarm()

        # --- RGB direct commands ---
        elif cmd == 'r':
            self.components["BRGB"].set_red()
        elif cmd == 'g':
            self.components["BRGB"].set_green()
        elif cmd == 'bu':
            self.components["BRGB"].set_blue()
        elif cmd == 'x':
            self.components["BRGB"].turn_off()

        # --- Simulation overrides ---
        elif cmd == '7':
            self.components["DS2"].set_state(True)
            print("[SIM] Door -> OPEN")
        elif cmd == '8':
            self.components["DS2"].set_state(False)
            print("[SIM] Door -> CLOSED")
        elif cmd == '9':
            self.components["DPIR3"].set_motion(True)
            print("[SIM] Motion ON")
            time.sleep(1)
            self.components["DPIR3"].set_motion(False)
        elif cmd == '0':
            key = input("Key (0-9, A-D, *, #): ").strip()
            if key:
                self.components["DMS"].set_key(key)
                print(f"[SIM] Injected key '{key}'")
        elif cmd == 'i':
            code = input("IR code (TOGGLE/RED/GREEN/BLUE): ").strip().upper()
            if code:
                self.components["IR"].inject_code(code)
                print(f"[SIM] IR code '{code}' injected")

        else:
            return None  # Unknown command

        return True
