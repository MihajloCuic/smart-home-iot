"""Motion Sensor component (PIR) - DPIR1"""

import time
import threading

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class MotionSensor(BaseComponent):
    """
    Door Motion Sensor (PIR) - DPIR1
    Detects motion via passive infrared.
    Publishes its own events and optionally calls on_motion for controller logic.
    """

    def __init__(self, code, settings, publisher=None, on_motion=None):
        super().__init__(code, settings, publisher)
        self.pin = settings.get('pin', 5)
        self.on_motion = on_motion  # Optional external hook for controller logic

        self.running = False
        self.thread = None
        self.motion_detected = False
        self._last_state = False

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN)

    def read(self):
        """Read current motion state"""
        if self.simulate:
            return self.motion_detected
        elif RPI_AVAILABLE:
            return GPIO.input(self.pin) == GPIO.HIGH
        return False

    def set_motion(self, detected):
        """Set motion state (simulation only)"""
        self.motion_detected = detected

    def start_monitoring(self):
        """Start background monitoring thread"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        """Fire internal handler only on rising edge (no motion -> motion)"""
        while self.running:
            current = self.read()
            if current and not self._last_state:
                self._on_motion_detected()
            self._last_state = current
            time.sleep(0.1)

    def _on_motion_detected(self):
        """
        Internal handler: called on rising edge of motion detection.
        Prints, publishes, then calls the optional external hook.
        """
        print(f"\n[{self.code}] Motion detected!")
        self._publish_sensor(True)

        if self.on_motion:
            self.on_motion()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)
