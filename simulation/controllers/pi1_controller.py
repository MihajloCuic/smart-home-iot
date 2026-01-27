"""PI1 Controller - Door sensors and actuators"""

import time

from mqtt_publisher import MQTTBatchPublisher

from components import (
    DoorSensor,
    DoorLight,
    UltrasonicSensor,
    Buzzer,
    MotionSensor,
    MembraneSwitch
)
from simulators import SensorSimulator


class PI1Controller:
    """Controller for PI1 device"""
    
    def __init__(self, settings):
        self.settings = settings
        self.device_info = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", settings)
        self.components = {}
        self.running = False
        self.simulator = None
        self.publisher = MQTTBatchPublisher(settings.get("mqtt", {}), self.device_info)
        self._dus1_last_alert = None
        self._init_components()
    
    def _init_components(self):
        """Initialize PI1 components"""
        print("=" * 50)
        print("Initializing PI1 Components...")
        print("=" * 50)
        
        if "DS1" in self.sensors_settings:
            self.components["DS1"] = DoorSensor(self.sensors_settings["DS1"], self._on_door_change)
            self._log_init("DS1")
        
        if "DL" in self.sensors_settings:
            self.components["DL"] = DoorLight(self.sensors_settings["DL"])
            self._log_init("DL")
        
        if "DUS1" in self.sensors_settings:
            self.components["DUS1"] = UltrasonicSensor(self.sensors_settings["DUS1"], self._on_distance_alert)
            self._log_init("DUS1")
        
        if "DB" in self.sensors_settings:
            self.components["DB"] = Buzzer(self.sensors_settings["DB"])
            self._log_init("DB")
        
        if "DPIR1" in self.sensors_settings:
            self.components["DPIR1"] = MotionSensor(self.sensors_settings["DPIR1"], self._on_motion)
            self._log_init("DPIR1")
        
        if "DMS" in self.sensors_settings:
            self.components["DMS"] = MembraneSwitch(self.sensors_settings["DMS"], self._on_key_press)
            self._log_init("DMS")
        
        print("=" * 50)
    
    def _log_init(self, code):
        s = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    def _publish(self, payload):
        payload.setdefault("device", self.device_info.get("id", "PI1"))
        payload.setdefault("ts", time.time())
        self.publisher.enqueue(payload)

    def _publish_sensor(self, code, value, extra=None):
        if not self.sensors_settings.get(code, {}).get("publish", True):
            return
        payload = {
            "source": "sensor",
            "sensor": code,
            "value": value,
            "simulated": self.sensors_settings.get(code, {}).get("simulate", True)
        }
        if extra:
            payload.update(extra)
        self._publish(payload)

    def _publish_actuator(self, code, value, extra=None):
        if not self.sensors_settings.get(code, {}).get("publish", True):
            return
        payload = {
            "source": "actuator",
            "sensor": code,
            "value": value,
            "simulated": self.sensors_settings.get(code, {}).get("simulate", True)
        }
        if extra:
            payload.update(extra)
        self._publish(payload)
    
    # ========== CALLBACKS ==========
    
    def _on_door_change(self, is_open):
        status = "OPENED" if is_open else "CLOSED"
        print(f"\n[EVENT] Door {status}")
        self._publish_sensor("DS1", is_open)
        if "DL" in self.components:
            if is_open:
                self.components["DL"].turn_on()
                print("[AUTO] Light ON")
                self._publish_actuator("DL", True)
            else:
                self.components["DL"].turn_off()
                print("[AUTO] Light OFF")
                self._publish_actuator("DL", False)
    
    def _on_distance_alert(self, distance, is_alert):
        self._publish_sensor("DUS1", distance, {"alert": is_alert})
        if self._dus1_last_alert is None or is_alert != self._dus1_last_alert:
            if is_alert:
                print(f"\n[ALERT] Object at {distance:.1f} cm!")
            else:
                print(f"\n[INFO] Object moved away ({distance:.1f} cm)")
        self._dus1_last_alert = is_alert
    
    def _on_motion(self, detected):
        if detected:
            print("\n[ALERT] Motion detected!")
        self._publish_sensor("DPIR1", detected)
    
    def _on_key_press(self, key):
        print(f"\n[INPUT] Key: {key}")
        self._publish_sensor("DMS", key)
    
    # ========== CONTROL ==========
    
    def start(self):
        """Start monitoring all sensors"""
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
        """Stop monitoring"""
        self.running = False
        if self.simulator:
            self.simulator.stop()
        self.publisher.stop()
        for comp in self.components.values():
            if hasattr(comp, 'stop'):
                comp.stop()
    
    def cleanup(self):
        """Cleanup all resources"""
        self.stop()
        for comp in self.components.values():
            comp.cleanup()
    
    # ========== STATUS ==========
    
    def get_status(self):
        """Return status of all components"""
        status = {}
        
        if "DS1" in self.components:
            status["DS1"] = "OPEN" if self.components["DS1"].read() else "CLOSED"
        
        if "DL" in self.components:
            status["DL"] = "ON" if self.components["DL"].is_on() else "OFF"
        
        if "DUS1" in self.components:
            dist = self.components["DUS1"].measure_distance()
            status["DUS1"] = f"{dist:.1f} cm" + (" ⚠" if dist < 30 else "")
        
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
        """Print status to console"""
        print("\n" + "=" * 40)
        print("PI1 STATUS")
        print("=" * 40)
        
        status = self.get_status()
        
        if "DS1" in status:
            print(f"  [DS1]   Door:       {status['DS1']}")
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
        """Handle user command. Returns False if should quit."""
        
        if cmd == 's':
            self.show_status()
        
        # Actuators
        elif cmd == '1':
            self.components["DL"].toggle()
            print(f"[DL] Light: {'ON' if self.components['DL'].is_on() else 'OFF'}")
            self._publish_actuator("DL", self.components["DL"].is_on())
        elif cmd == '2':
            self.components["DL"].turn_on()
            print("[DL] Light: ON")
            self._publish_actuator("DL", True)
        elif cmd == '3': 
            self.components["DL"].turn_off()
            print("[DL] Light: OFF")
            self._publish_actuator("DL", False)
        elif cmd == '4':
            print("[DB] Beeping...")
            self.components["DB"].beep(0.5)
            self._publish_actuator("DB", True, {"action": "beep"})
        elif cmd == '5':
            self.components["DB"].start_alarm()
            print("[DB] Alarm STARTED")
            self._publish_actuator("DB", True, {"action": "alarm"})
        elif cmd == '6':
            self.components["DB"].stop_alarm()
            print("[DB] Alarm STOPPED")
            self._publish_actuator("DB", False, {"action": "alarm"})
        
        # Simulation
        elif cmd == '7':
            self.components["DS1"].set_state(True)
            print("[SIM] Door OPEN")
        elif cmd == '8':
            self.components["DS1"].set_state(False)
            print("[SIM] Door CLOSED")
        elif cmd == '9':
            self.components["DPIR1"].set_motion(True)
            print("[SIM] Motion ON")
            time.sleep(1)
            self.components["DPIR1"].set_motion(False)
        elif cmd == '0':
            key = input("Key (0-9, A-D, *, #): ").strip()
            if key:
                self.components["DMS"].set_key(key)
                print(f"[SIM] Key '{key}'")
        else:
            return None  # Unknown command
        
        return True