"""PI2 Controller - Kitchen (ALARM + timer + 4SD)

Implements:
- Rule 2a: basic entry/exit hooks (logs)
- Rule 6: gyroscope movement -> alarm
- Rule 8: kitchen timer shown on 4SD, BTN adds seconds / stops blinking
"""
import threading
import time

from mqtt_publisher import MQTTBatchPublisher

from components import (
    DoorSensor,
    UltrasonicSensor,
    MotionSensor,
    Buzzer,
    FourDigitDisplay,
    Button,
    DHTSensor,
    Gyroscope,
)
from controllers.alarm_state_machine import AlarmStateMachine
from simulators import SensorSimulator


class PI2Controller:
    TIMER_TICK = 1

    def __init__(self, settings, mqtt_cfg=None, get_person_count=None):
        self.settings = settings
        self.device_info = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", {})
        alarm_cfg = settings.get("alarm", {})

        self.components = {}
        self.running = False
        self.simulator = None

        self.get_person_count = get_person_count or (lambda: 0)
        self.publisher = MQTTBatchPublisher(mqtt_cfg or {}, self.device_info)

        # Alarm state machine
        self.alarm = AlarmStateMachine(
            correct_pin=alarm_cfg.get("pin", "1234"),
            arm_delay=alarm_cfg.get("arm_delay", 5),
            grace_period=alarm_cfg.get("grace_period", 30),
            on_alarm_start=self._start_alarm,
            on_alarm_stop=self._stop_alarm,
        )

        # Timer state (Rule 8)
        self._timer_seconds = 0
        self._timer_lock = threading.Lock()
        self._timer_thread = None
        self._timer_running = False
        self._blink_on_expiry = False

        self._init_components()

    def _init_components(self):
        s = self.sensors_settings
        print("=" * 50)
        print("Initializing PI2 Components...")
        print("=" * 50)

        if "DS2" in s:
            self.components["DS2"] = DoorSensor('DS2', s["DS2"], publisher=self.publisher, on_change=self._on_door_change)
            self._log_init('DS2')

        if "DUS2" in s:
            self.components["DUS2"] = UltrasonicSensor(s["DUS2"], publisher=self.publisher)
            self._log_init('DUS2')

        if "DPIR2" in s:
            self.components["DPIR2"] = MotionSensor('DPIR2', s['DPIR2'], publisher=self.publisher, on_motion=self._on_motion)
            self._log_init('DPIR2')

        if "DB" in s:
            self.components['DB'] = Buzzer('DB', s['DB'], publisher=self.publisher)
            self._log_init('DB')

        if "4SD" in s:
            self.components['4SD'] = FourDigitDisplay('4SD', s['4SD'], publisher=self.publisher)
            self._log_init('4SD')

        if "BTN" in s:
            self.components['BTN'] = Button('BTN', s['BTN'], publisher=self.publisher, on_press=self._on_btn_press)
            self._log_init('BTN')

        if "DHT3" in s:
            self.components['DHT3'] = DHTSensor('DHT3', s['DHT3'], publisher=self.publisher)
            self._log_init('DHT3')

        if "GSG" in s:
            self.components['GSG'] = Gyroscope('GSG', s['GSG'], publisher=self.publisher, on_movement=self._on_gyro_movement)
            self._log_init('GSG')

        print("=" * 50)

    def _log_init(self, code):
        s = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    # Alarm callbacks
    def _start_alarm(self):
        db = self.components.get('DB')
        if db:
            db.start_alarm()

    def _stop_alarm(self):
        db = self.components.get('DB')
        if db:
            db.stop_alarm()

    # Hooks
    def _on_door_change(self, is_open):
        # Basic behavior: log and light follow (if present)
        print(f"[PI2] Door changed -> {'OPEN' if is_open else 'CLOSED'}")
        # Rule 4: notify alarm state machine as well
        if is_open:
            self.alarm.door_opened()
        else:
            self.alarm.door_closed()

    def _on_motion(self):
        print("[PI2] Motion detected (DPIR2)")
        # Example Rule 2a logic placeholder - can be extended
        # If no persons at home, trigger alarm (Rule 5 semantics still apply)
        if self.get_person_count() == 0:
            if self.alarm.get_state() != AlarmStateMachine.ALARMING:
                print("[RULE5] Motion with no occupants -> triggering alarm")
                self.alarm.trigger_alarm()

    def _on_gyro_movement(self):
        print("[RULE6] Gyro detected movement -> triggering alarm")
        if self.alarm.get_state() != AlarmStateMachine.ALARMING:
            self.alarm.trigger_alarm()

    # BTN behavior (Rule 8)
    def _on_btn_press(self):
        # Default BTN action: add configured seconds or stop blinking when expired
        cfg = self.sensors_settings.get('BTN', {})
        add_n = cfg.get('add_seconds', 30)
        with self._timer_lock:
            if self._timer_seconds <= 0 and self._blink_on_expiry:
                # stop blinking
                disp = self.components.get('4SD')
                if disp:
                    disp.stop_blink()
                self._blink_on_expiry = False
                print("[PI2] BTN pressed: stopped blinking")
            else:
                self._timer_seconds = max(0, self._timer_seconds + int(add_n))
                disp = self.components.get('4SD')
                if disp:
                    disp.show_time(self._timer_seconds)
                print(f"[PI2] BTN pressed: added {add_n} seconds -> {self._timer_seconds}s")

    # Timer management (Rule 8)
    def _timer_loop(self):
        while self._timer_running:
            time.sleep(self.TIMER_TICK)
            with self._timer_lock:
                if self._timer_seconds > 0:
                    self._timer_seconds -= 1
                    disp = self.components.get('4SD')
                    if disp:
                        disp.show_time(self._timer_seconds)
                    if self._timer_seconds == 0:
                        # timer expired
                        print('[RULE8] Timer expired -> blink 4SD and set to 00:00')
                        self._blink_on_expiry = True
                        if disp:
                            disp.show_time(0)
                            disp.blink()
                        # Optionally trigger alarm (not strictly demanded)
                        # self.alarm.trigger_alarm()

    # Lifecycle
    def start(self):
        self.running = True
        self.publisher.start()

        # Start monitoring basic sensors
        for code in ["DS2", "DUS2", "DPIR2", "GSG"]:
            if code in self.components:
                # Ultrasonic requires interval param
                if code == 'DUS2':
                    self.components[code].start_monitoring(interval=2.0)
                else:
                    self.components[code].start_monitoring()

        # start simulator
        self.simulator = SensorSimulator(self.components)
        self.simulator.start_all()

        # Timer background thread (not running until timer set)
        self._timer_running = True
        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

    def stop(self):
        self.running = False
        self._timer_running = False
        if self.simulator:
            self.simulator.stop()
        self.publisher.stop()

        for comp in self.components.values():
            if hasattr(comp, 'stop'):
                comp.stop()

    def cleanup(self):
        self.stop()
        for comp in self.components.values():
            comp.cleanup()

    # Status and commands
    def get_status(self):
        status = {}
        if 'DS2' in self.components:
            status['DS2'] = 'OPEN' if self.components['DS2'].read() else 'CLOSED'
        if 'DUS2' in self.components:
            dist = self.components['DUS2'].measure_distance()
            status['DUS2'] = f"{dist:.1f} cm"
        if 'DPIR2' in self.components:
            status['DPIR2'] = 'DETECTED' if self.components['DPIR2'].read() else 'CLEAR'
        if 'DB' in self.components:
            s = 'ON' if self.components['DB'].is_on() else 'OFF'
            if self.components['DB'].is_alarming():
                s += ' (ALARM)'
            status['DB'] = s
        if '4SD' in self.components:
            status['4SD'] = self.components['4SD'].get_state()
        if 'BTN' in self.components:
            status['BTN'] = self.components['BTN'].get_state()
        if 'DHT3' in self.components:
            t, h = self.components['DHT3'].read()
            status['DHT3'] = f"{t:.1f}C {h:.0f}%"
        if 'GSG' in self.components:
            status['GSG'] = self.components['GSG'].get_state()

        status['ALARM'] = self.alarm.get_state()
        status['PERSONS'] = self.get_person_count()
        return status

    def show_status(self):
        print('\n' + '=' * 40)
        print('PI2 STATUS')
        print('=' * 40)
        s = self.get_status()
        if 'DS2' in s: print(f"  [DS2]  Door:    {s['DS2']}")
        if 'DUS2' in s: print(f"  [DUS2] Dist:    {s['DUS2']}")
        if 'DPIR2' in s: print(f"  [DPIR2] Motion:  {s['DPIR2']}")
        if '4SD' in s: print(f"  [4SD]  Display: {s['4SD']}")
        if 'BTN' in s: print(f"  [BTN]  {s['BTN']}")
        if 'GSG' in s: print(f"  [GSG]  {s['GSG']}")
        print(f"  [ALARM] State:  {s['ALARM']}")
        print(f"  [HOME]  Persons:{s['PERSONS']}")
        print('=' * 40)

    def handle_command(self, cmd):
        if cmd == 's':
            self.show_status()
        elif cmd == '1':
            # Toggle a display demo: show 00:10
            dsp = self.components.get('4SD')
            if dsp:
                dsp.show_time(10)
        elif cmd == '2':
            # Start a sample 60s timer
            with self._timer_lock:
                self._timer_seconds = 60
                disp = self.components.get('4SD')
                if disp:
                    disp.show_time(self._timer_seconds)
        elif cmd == '3':
            # Stop alarm
            self.alarm.stop_alarm()
        elif cmd == '4':
            # Start alarm
            self.alarm.trigger_alarm()
        elif cmd == '7':
            if 'DS2' in self.components:
                self.components['DS2'].set_state(True); print('[SIM] Door -> OPEN')
        elif cmd == '8':
            if 'DS2' in self.components:
                self.components['DS2'].set_state(False); print('[SIM] Door -> CLOSED')
        elif cmd == '9':
            if 'DPIR2' in self.components:
                self.components['DPIR2'].set_motion(True); print('[SIM] Motion ON'); time.sleep(1); self.components['DPIR2'].set_motion(False)
        elif cmd == '0':
            # simulate button press
            if 'BTN' in self.components:
                self.components['BTN'].press(); print('[SIM] BTN pressed')
        else:
            return None

        return True
