"""Membrane Switch component (4x4 Keypad) - DMS"""

import time
import threading

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class MembraneSwitch(BaseComponent):
    """
    Door Membrane Switch (4x4 Keypad) - DMS
    Scans a 4x4 matrix keypad for key presses.
    Publishes its own events and optionally calls on_key for controller logic.
    """

    KEYS = [
        ['1', '2', '3', 'A'],
        ['4', '5', '6', 'B'],
        ['7', '8', '9', 'C'],
        ['*', '0', '#', 'D']
    ]

    def __init__(self, code, settings, publisher=None, on_key=None):
        super().__init__(code, settings, publisher)
        self.row_pins = settings.get('row_pins', [6, 13, 19, 26])
        self.col_pins = settings.get('col_pins', [12, 16, 20, 21])
        self.on_key = on_key  # Optional external hook for controller logic

        self.running = False
        self.thread = None
        self.last_key = None
        self._simulated_key = None

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            for pin in self.row_pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
            for pin in self.col_pins:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def read_key(self):
        """Read currently pressed key (returns None if none pressed)"""
        if self.simulate:
            key = self._simulated_key
            self._simulated_key = None
            return key
        elif RPI_AVAILABLE:
            for i, row_pin in enumerate(self.row_pins):
                GPIO.output(row_pin, GPIO.HIGH)
                for j, col_pin in enumerate(self.col_pins):
                    if GPIO.input(col_pin) == GPIO.HIGH:
                        GPIO.output(row_pin, GPIO.LOW)
                        return self.KEYS[i][j]
                GPIO.output(row_pin, GPIO.LOW)
        return None

    def set_key(self, key):
        """
        Inject a simulated key press.
        Calls the handler immediately (does NOT go through the polling loop)
        so that rapid multi-key sequences (e.g. '1234#') are processed in order
        without any key being overwritten before the monitor thread reads it.
        """
        self._on_key_detected(key)

    def start_monitoring(self):
        """Start background monitoring thread"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()

    def _monitor_loop(self):
        """Poll for key presses and fire internal handler on each press"""
        while self.running:
            key = self.read_key()
            if key:
                self._on_key_detected(key)
                time.sleep(0.3)  # debounce
            time.sleep(0.05)

    def _on_key_detected(self, key):
        """
        Internal handler: called whenever a key is pressed.
        Prints, publishes, then calls the optional external hook.
        """
        self.last_key = key
        print(f"\n[{self.code}] Key pressed: '{key}'")
        self._publish_sensor(key)

        if self.on_key:
            self.on_key(key)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            for pin in self.row_pins + self.col_pins:
                GPIO.cleanup(pin)
