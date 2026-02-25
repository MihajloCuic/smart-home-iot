"""Door Sensor component (Button) - DS1"""

import time
import threading

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class DoorSensor(BaseComponent):
    """
    Door Sensor (Button) - DS1
    Monitors door open/close state changes.
    Publishes its own events and optionally calls an external hook (on_change)
    for controller-level automation (e.g. turning the light on when door opens).
    """

    def __init__(self, code, settings, publisher=None, on_change=None):
        super().__init__(code, settings, publisher)
        self.pin = settings.get('pin', 17)
        self.on_change = on_change  # Optional external hook for controller logic

        self.running = False
        self.thread = None
        self.state = False       # False = closed, True = open
        self._last_state = False

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def read(self):
        """Read current door state"""
        if self.simulate:
            return self.state
        elif RPI_AVAILABLE:
            return GPIO.input(self.pin) == GPIO.HIGH
        return False

    def set_state(self, state):
        """Set door state (simulation only)"""
        self.state = state

    def start_monitoring(self):
        """Start background monitoring thread"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        """Poll for state changes and fire internal handler on change"""
        while self.running:
            current = self.read()
            if current != self._last_state:
                self._on_state_change(current)
                self._last_state = current
            time.sleep(0.1)

    def _on_state_change(self, is_open):
        """
        Internal handler: called whenever door state changes.
        Prints, publishes, then calls the optional external hook.
        """
        status = "OPENED" if is_open else "CLOSED"
        print(f"\n[{self.code}] Door {status}")
        self._publish_sensor(is_open)

        if self.on_change:
            self.on_change(is_open)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)
