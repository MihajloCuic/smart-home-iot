"""Base simulator - shared simulation logic for PI1 and PI3"""

import random
import threading
import time

SIMULATED_IR_CODES = ['TOGGLE', 'RED', 'GREEN', 'BLUE']


class BaseSimulator:
    """
    Base class with shared simulation methods.
    Subclasses define which components to simulate by overriding start().
    """

    def __init__(self, components):
        self.components = components
        self.running = False
        self.threads = []

    def _maybe_start(self, code, target):
        """Start a simulation thread for a component if it exists and simulate=True."""
        comp = self.components.get(code)
        if comp is not None and comp.simulate:
            t = threading.Thread(target=target, args=(code,), daemon=True)
            t.start()
            self.threads.append(t)

    # ========== SIMULATION METHODS ==========

    def _simulate_motion(self, code):
        """15% chance of motion every 8 seconds."""
        comp = self.components[code]
        while self.running:
            if random.random() < 0.15:
                comp.set_motion(True)
                time.sleep(random.uniform(1, 3))
                comp.set_motion(False)
            time.sleep(8)

    def _simulate_dht(self, code):
        """Slow temperature/humidity drift every 10 seconds."""
        comp = self.components[code]
        temp = random.uniform(18.0, 28.0)
        humidity = random.uniform(40.0, 70.0)
        while self.running:
            temp += random.uniform(-0.5, 0.5)
            humidity += random.uniform(-1.0, 1.0)
            temp = max(18.0, min(28.0, temp))
            humidity = max(40.0, min(70.0, humidity))
            comp.set_values(temp, humidity)
            time.sleep(10)

    def _simulate_ultrasonic(self, code):
        """10% chance someone approaches (distance drops) every 5 seconds."""
        comp = self.components[code]
        while self.running:
            if random.random() < 0.1:
                comp.set_distance(random.uniform(10, 25))
                time.sleep(random.uniform(2, 4))
                comp.set_distance(random.uniform(80, 150))
            else:
                comp.set_distance(random.uniform(80, 200))
            time.sleep(5)

    def _simulate_ir(self, code):
        """5% chance of random IR code every 15 seconds."""
        comp = self.components[code]
        while self.running:
            if random.random() < 0.05:
                comp.inject_code(random.choice(SIMULATED_IR_CODES))
            time.sleep(15)

    # ========== LIFECYCLE ==========

    def start(self):
        raise NotImplementedError("Subclasses must implement start()")

    def stop(self):
        self.running = False
        for t in self.threads:
            t.join(timeout=1)
