"""4-Digit 7-Segment Display component - 4SD"""

import threading
import time

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class SevenSegmentDisplay(BaseComponent):
    """
    4-digit 7-segment display.
    In simulation, just prints the text being shown.
    """

    def __init__(self, code, settings, publisher=None):
        super().__init__(code, settings, publisher)
        self.segment_pins = settings.get('segment_pins', {})
        self.digit_pins = settings.get('digit_pins', {})
        self.decimal_pin = settings.get('decimal_pin')
        self._value = ""
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            self._segments = [
                self.segment_pins.get('a'),
                self.segment_pins.get('b'),
                self.segment_pins.get('c'),
                self.segment_pins.get('d'),
                self.segment_pins.get('e'),
                self.segment_pins.get('f'),
                self.segment_pins.get('g'),
            ]
            self._digits = [
                self.digit_pins.get('d1'),
                self.digit_pins.get('d2'),
                self.digit_pins.get('d3'),
                self.digit_pins.get('d4'),
            ]
            for pin in self._segments:
                if pin is not None:
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, 0)
            if self.decimal_pin is not None:
                GPIO.setup(self.decimal_pin, GPIO.OUT)
                GPIO.output(self.decimal_pin, 0)
            for pin in self._digits:
                if pin is not None:
                    GPIO.setup(pin, GPIO.OUT)
                    GPIO.output(pin, 1)

            self._running = True
            self._thread = threading.Thread(target=self._refresh_loop, daemon=True)
            self._thread.start()

    def show(self, text):
        with self._lock:
            self._value = str(text)
        print(f"[{self.code}] Display -> {self._value}")
        self._publish_actuator(self._value)

    def clear(self):
        with self._lock:
            self._value = ""
        print(f"[{self.code}] Display cleared")
        self._publish_actuator(self._value)

    def get_value(self):
        return self._value

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            for pin in self._segments + self._digits:
                if pin is not None:
                    GPIO.cleanup(pin)
            if self.decimal_pin is not None:
                GPIO.cleanup(self.decimal_pin)

    # ========== INTERNAL DISPLAY LOGIC ==========

    _NUM_MAP = {
        ' ': (0, 0, 0, 0, 0, 0, 0),
        '0': (1, 1, 1, 1, 1, 1, 0),
        '1': (0, 1, 1, 0, 0, 0, 0),
        '2': (1, 1, 0, 1, 1, 0, 1),
        '3': (1, 1, 1, 1, 0, 0, 1),
        '4': (0, 1, 1, 0, 0, 1, 1),
        '5': (1, 0, 1, 1, 0, 1, 1),
        '6': (1, 0, 1, 1, 1, 1, 1),
        '7': (1, 1, 1, 0, 0, 0, 0),
        '8': (1, 1, 1, 1, 1, 1, 1),
        '9': (1, 1, 1, 1, 0, 1, 1),
    }

    def _normalize_value(self, value):
        value = value or ""
        dp_index = None
        if ":" in value:
            colon_index = value.index(":")
            dp_index = max(0, colon_index - 1)
            value = value.replace(":", "")
        value = value[-4:].rjust(4)
        return value, dp_index

    def _refresh_loop(self):
        if self.simulate or not RPI_AVAILABLE:
            return
        while self._running:
            with self._lock:
                text, dp_index = self._normalize_value(self._value)

            for idx in range(4):
                char = text[idx] if idx < len(text) else ' '
                segments_state = self._NUM_MAP.get(char, self._NUM_MAP[' '])

                for seg_index, pin in enumerate(self._segments):
                    if pin is not None:
                        GPIO.output(pin, segments_state[seg_index])

                if self.decimal_pin is not None:
                    GPIO.output(self.decimal_pin, 1 if dp_index == idx else 0)

                digit_pin = self._digits[idx]
                if digit_pin is not None:
                    GPIO.output(digit_pin, 0)
                time.sleep(0.001)
                if digit_pin is not None:
                    GPIO.output(digit_pin, 1)
