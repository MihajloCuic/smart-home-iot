"""PI2 Simulator - kitchen sensors simulation"""

import random
import threading
import time

from simulators.base_simulator import BaseSimulator
from components.gyroscope import Gyroscope


class PI2Simulator(BaseSimulator):
    """
    Simulator for PI2 (Kitchen) components.

    Simulates automatically:
      - DUS2  : ultrasonic distance sensor
      - DPIR2 : PIR motion sensor
      - GSG   : gyroscope movement

    Not simulated here (done via CLI commands in the controller):
      - DS2   : door sensor
      - BTN   : kitchen button
    """

    def start(self):
        self.running = True
        self._maybe_start("DUS2", self._simulate_ultrasonic)
        self._maybe_start("DPIR2", self._simulate_motion)
        self._maybe_start_gyro("GSG")

    def _maybe_start_gyro(self, code):
        comp = self.components.get(code)
        if comp is not None and isinstance(comp, Gyroscope) and comp.simulate and comp.auto_simulate:
            t = threading.Thread(target=self._simulate_gyro, args=(code,), daemon=True)
            t.start()
            self.threads.append(t)

    def _simulate_gyro(self, code):
        comp = self.components[code]
        while self.running:
            if random.random() < 0.05:
                comp.trigger_movement()
            time.sleep(10)
