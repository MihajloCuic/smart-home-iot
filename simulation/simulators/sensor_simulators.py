import random
import threading
import time

from components.dht_sensor import DHTSensor
from components.motion_sensor import MotionSensor
from components.ultrasonic_sensor import UltrasonicSensor
from components.ir_receiver import IRReceiver


# IR codes that the simulator randomly sends (matches Rule 9 mapping in PI3)
SIMULATED_IR_CODES = ['TOGGLE', 'RED', 'GREEN', 'BLUE']


class SensorSimulator:
    """
    Simulator for generating random sensor data for any PI controller.
    Detects component types via isinstance() checks rather than hardcoded
    component keys, so it works transparently for both PI1 and PI3.
    """

    def __init__(self, components):
        self.components = components
        self.running = False
        self.threads = []

    def start_all(self):
        """
        Start simulator threads for all components in simulation mode.
        One thread per component that needs simulation.
        """
        self.running = True

        for code, comp in self.components.items():
            t = None

            if isinstance(comp, UltrasonicSensor) and comp.simulate:
                t = threading.Thread(
                    target=self._simulate_ultrasonic,
                    args=(code,),
                    daemon=True
                )
            elif isinstance(comp, MotionSensor) and comp.simulate:
                t = threading.Thread(
                    target=self._simulate_motion_generic,
                    args=(code,),
                    daemon=True
                )
            elif isinstance(comp, DHTSensor) and comp.simulate:
                t = threading.Thread(
                    target=self._simulate_dht,
                    args=(code,),
                    daemon=True
                )
            elif isinstance(comp, IRReceiver) and comp.simulate:
                t = threading.Thread(
                    target=self._simulate_ir,
                    args=(code,),
                    daemon=True
                )

            if t is not None:
                t.start()
                self.threads.append(t)

    def _simulate_ultrasonic(self, code):
        """Simulate distance changes for any UltrasonicSensor"""
        comp = self.components[code]
        while self.running:
            if random.random() < 0.1:   # 10% chance someone approaches
                comp.set_distance(random.uniform(10, 25))
                time.sleep(random.uniform(2, 4))
                comp.set_distance(random.uniform(80, 150))
            else:
                comp.set_distance(random.uniform(80, 200))
            time.sleep(5)

    def _simulate_motion_generic(self, code):
        """Simulate motion for any MotionSensor regardless of its code"""
        comp = self.components[code]
        while self.running:
            if random.random() < 0.15:  # 15% chance of motion
                comp.set_motion(True)
                time.sleep(random.uniform(1, 3))
                comp.set_motion(False)
            time.sleep(8)

    def _simulate_dht(self, code):
        """
        Simulate slow DHT temperature and humidity drift.
        Values change by small increments to mimic real sensor behavior.
        """
        comp = self.components[code]
        temp = random.uniform(18.0, 28.0)
        humidity = random.uniform(40.0, 70.0)
        while self.running:
            temp += random.uniform(-0.5, 0.5)
            humidity += random.uniform(-1.0, 1.0)
            # Clamp to realistic bounds
            temp = max(18.0, min(28.0, temp))
            humidity = max(40.0, min(70.0, humidity))
            comp.set_values(temp, humidity)
            time.sleep(10)

    def _simulate_ir(self, code):
        """
        Occasionally send random IR codes to simulate remote control presses.
        Low probability to avoid overwhelming the console output.
        """
        comp = self.components[code]
        while self.running:
            if random.random() < 0.05:  # 5% chance every 15 seconds
                ir_code = random.choice(SIMULATED_IR_CODES)
                comp.inject_code(ir_code)
            time.sleep(15)

    def stop(self):
        self.running = False
        for t in self.threads:
            t.join(timeout=1)
