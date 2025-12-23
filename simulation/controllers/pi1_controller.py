"""PI1 Controller - Door sensors and actuators"""

import time

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
        self.components = {}
        self.running = False
        self.simulator = None
        self._init_components()
    
    def _init_components(self):
        """Initialize PI1 components"""
        print("=" * 50)
        print("Initializing PI1 Components...")
        print("=" * 50)
        
        if "DS1" in self.settings:
            self.components["DS1"] = DoorSensor(self.settings["DS1"], self._on_door_change)
            self._log_init("DS1")
        
        if "DL" in self.settings:
            self.components["DL"] = DoorLight(self.settings["DL"])
            self._log_init("DL")
        
        if "DUS1" in self.settings:
            self.components["DUS1"] = UltrasonicSensor(self.settings["DUS1"], self._on_distance_alert)
            self._log_init("DUS1")
        
        if "DB" in self.settings:
            self.components["DB"] = Buzzer(self.settings["DB"])
            self._log_init("DB")
        
        if "DPIR1" in self.settings:
            self.components["DPIR1"] = MotionSensor(self.settings["DPIR1"], self._on_motion)
            self._log_init("DPIR1")
        
        if "DMS" in self.settings:
            self.components["DMS"] = MembraneSwitch(self.settings["DMS"], self._on_key_press)
            self._log_init("DMS")
        
        print("=" * 50)
    
    def _log_init(self, code):
        s = self.settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")
    
    # ========== CALLBACKS ==========
    
    def _on_door_change(self, is_open):
        status = "OPENED" if is_open else "CLOSED"
        print(f"\n[EVENT] Door {status}")
        if "DL" in self.components:
            if is_open:
                self.components["DL"].turn_on()
                print("[AUTO] Light ON")
            else:
                self.components["DL"].turn_off()
                print("[AUTO] Light OFF")
    
    def _on_distance_alert(self, distance, is_alert):
        if is_alert:
            print(f"\n[ALERT] Object at {distance:.1f} cm!")
        else:
            print(f"\n[INFO] Object moved away ({distance:.1f} cm)")
    
    def _on_motion(self, detected):
        if detected:
            print("\n[ALERT] Motion detected!")
    
    def _on_key_press(self, key):
        print(f"\n[INPUT] Key: {key}")
    
    # ========== CONTROL ==========
    
    def start(self):
        """Start monitoring all sensors"""
        self.running = True
        
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
        elif cmd == '2':
            self.components["DL"].turn_on()
            print("[DL] Light: ON")
        elif cmd == '3': 
            self.components["DL"].turn_off()
            print("[DL] Light: OFF")
        elif cmd == '4':
            print("[DB] Beeping...")
            self.components["DB"].beep(0.5)
        elif cmd == '5':
            self.components["DB"].start_alarm()
            print("[DB] Alarm STARTED")
        elif cmd == '6':
            self.components["DB"].stop_alarm()
            print("[DB] Alarm STOPPED")
        
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