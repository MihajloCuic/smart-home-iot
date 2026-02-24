"""Kitchen Button component (momentary switch) - BTN"""

import time
import threading

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class KitchenButton(BaseComponent):
    """
    Kitchen Button (momentary switch) - BTN
    Publishes press events and optionally calls on_press for controller logic.
    """

    def __init__(self, code, settings, publisher=None, on_press=None):
        super().__init__(code, settings, publisher)
        self.pin = settings.get('pin', 6)
        self.on_press = on_press

        self.running = False
        self.thread = None
        self._last_state = False
        self._pressed = False

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    def read(self):
        if self.simulate:
            return self._pressed
        if RPI_AVAILABLE:
            return GPIO.input(self.pin) == GPIO.LOW
        return False

    def press(self):
        """Simulate a button press"""
        if not self.simulate:
            return
        self._pressed = True
        self._handle_press()
        self._pressed = False

    def start_monitoring(self):
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        while self.running:
            current = self.read()
            if current and not self._last_state:
                self._handle_press()
            self._last_state = current
            time.sleep(0.05)

    def _handle_press(self):
        print(f"\n[{self.code}] Button pressed")
        self._publish_sensor(True)
        if self.on_press:
            self.on_press()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)
