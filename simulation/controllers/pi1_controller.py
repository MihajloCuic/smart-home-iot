"""PI1 Controller - Entrance door sensors and actuators"""

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
from simulators import SensorSimulator


class PI1Controller:
    """
    Controller for PI1 (Entrance).

    Responsibilities:
    - Creates the MQTT publisher and injects it into every component
    - Wires up inter-component automation via on_change / on_motion hooks
    - Handles user CLI commands
    - Starts / stops monitoring and the simulator

    What this class does NOT do anymore:
    - Publish MQTT messages (each component does its own publishing)
    - Print sensor/actuator state (each component prints its own messages)
    """

    def __init__(self, settings):
        self.settings = settings
        self.device_info = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", {})
        self.components = {}
        self.running = False
        self.simulator = None

        # Publisher is created here and shared with all components
        self.publisher = MQTTBatchPublisher(settings.get("mqtt", {}), self.device_info)
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
                s["DS1"],
                publisher=self.publisher,
                on_change=self._on_door_change,   # controller-level hook
            )
            self._log_init("DS1")

        if "DL" in s:
            self.components["DL"] = DoorLight(s["DL"], publisher=self.publisher)
            self._log_init("DL")

        if "DUS1" in s:
            self.components["DUS1"] = UltrasonicSensor(s["DUS1"], publisher=self.publisher)
            self._log_init("DUS1")

        if "DB" in s:
            self.components["DB"] = Buzzer(s["DB"], publisher=self.publisher)
            self._log_init("DB")

        if "DPIR1" in s:
            self.components["DPIR1"] = MotionSensor(s["DPIR1"], publisher=self.publisher)
            self._log_init("DPIR1")

        if "DMS" in s:
            self.components["DMS"] = MembraneSwitch(s["DMS"], publisher=self.publisher)
            self._log_init("DMS")

        print("=" * 50)

    def _log_init(self, code):
        s = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    # ========== CONTROLLER-LEVEL HOOKS ==========
    # These are called AFTER the component has already printed and published.
    # They contain only cross-component automation logic.

    def _on_door_change(self, is_open):
        """Auto-control the light based on door state"""
        dl = self.components.get("DL")
        if dl:
            if is_open:
                dl.turn_on(reason="door opened")
            else:
                dl.turn_off(reason="door closed")

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

        self.simulator = SensorSimulator(self.components)
        self.simulator.start_all()

    def stop(self):
        """Stop all monitoring threads and publisher"""
        self.running = False
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

        return status

    def show_status(self):
        """Print status table to console"""
        print("\n" + "=" * 40)
        print("PI1 STATUS")
        print("=" * 40)
        status = self.get_status()
        if "DS1" in status:
            print(f"  [DS1]   Door:      {status['DS1']}")
        if "DL" in status:
            print(f"  [DL]    Light:     {status['DL']}")
        if "DUS1" in status:
            print(f"  [DUS1]  Distance:  {status['DUS1']}")
        if "DB" in status:
            print(f"  [DB]    Buzzer:    {status['DB']}")
        if "DPIR1" in status:
            print(f"  [DPIR1] Motion:    {status['DPIR1']}")
        if "DMS" in status:
            print(f"  [DMS]   Last key:  {status['DMS']}")
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
            print("[SIM] Door → OPEN")
        elif cmd == '8':
            self.components["DS1"].set_state(False)
            print("[SIM] Door → CLOSED")
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
