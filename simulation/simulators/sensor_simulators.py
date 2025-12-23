import random
import threading
import time


class SensorSimulator:
    """Simulator for generating random sensor data"""
    
    def __init__(self, components):
        self.components = components
        self.running = False
        self.threads = []
    
    def start_all(self):
        """Start simulators for components in simulation mode"""
        self.running = True
        
        if 'DUS1' in self.components and self.components['DUS1'].simulate:
            t = threading.Thread(target=self._simulate_ultrasonic, daemon=True)
            t.start()
            self.threads.append(t)
        
        if 'DPIR1' in self.components and self.components['DPIR1'].simulate:
            t = threading.Thread(target=self._simulate_motion, daemon=True)
            t.start()
            self.threads.append(t)
    
    def _simulate_ultrasonic(self):
        """Simulate distance changes"""
        while self.running:
            if random.random() < 0.1:  # 10% chance someone approaches
                self.components['DUS1'].set_distance(random.uniform(10, 25))
                time.sleep(random.uniform(2, 4))
                self.components['DUS1'].set_distance(random.uniform(80, 150))
            else:
                self.components['DUS1'].set_distance(random.uniform(80, 200))
            time.sleep(5)
    
    def _simulate_motion(self):
        """Simulate motion detection"""
        while self.running:
            if random.random() < 0.15:  # 15% chance of motion
                self.components['DPIR1'].set_motion(True)
                time.sleep(random.uniform(1, 3))
                self.components['DPIR1'].set_motion(False)
            time.sleep(8)
    
    def stop(self):
        self.running = False
        for t in self.threads:
            t.join(timeout=1)