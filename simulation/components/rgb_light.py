"""RGB LED Light component - BRGB"""

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class RGBLight(BaseComponent):
    """
    RGB LED Light with three independent GPIO pins.

    Simulation: prints current color state to console.
    Real HW: drives each channel with GPIO.output().

    Color is represented as (r, g, b) where each value is 0 or 1.
    The last non-off color is remembered for toggle restore (Rule 9).
    """

    COLOR_NAMES = {
        (1, 0, 0): "RED",
        (0, 1, 0): "GREEN",
        (0, 0, 1): "BLUE",
        (1, 1, 0): "YELLOW",
        (1, 0, 1): "MAGENTA",
        (0, 1, 1): "CYAN",
        (1, 1, 1): "WHITE",
        (0, 0, 0): "OFF",
    }

    def __init__(self, code, settings, publisher=None):
        super().__init__(code, settings, publisher)
        self.pin_r = settings.get('pin_r', 13)
        self.pin_g = settings.get('pin_g', 19)
        self.pin_b = settings.get('pin_b', 26)

        self._r = 0
        self._g = 0
        self._b = 0
        self._last_color = (1, 1, 1)  # last non-off color; defaults to white

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            for pin in (self.pin_r, self.pin_g, self.pin_b):
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)

    def set_color(self, r, g, b):
        """
        Set RGB color. r, g, b are each 0 or 1 (or truthy/falsy).
        Saves non-off state as last_color for toggle restore.
        """
        self._r = int(bool(r))
        self._g = int(bool(g))
        self._b = int(bool(b))

        if not self.simulate and RPI_AVAILABLE:
            GPIO.output(self.pin_r, GPIO.HIGH if self._r else GPIO.LOW)
            GPIO.output(self.pin_g, GPIO.HIGH if self._g else GPIO.LOW)
            GPIO.output(self.pin_b, GPIO.HIGH if self._b else GPIO.LOW)

        if (self._r, self._g, self._b) != (0, 0, 0):
            self._last_color = (self._r, self._g, self._b)

        color_name = self.COLOR_NAMES.get((self._r, self._g, self._b), "CUSTOM")
        print(f"[{self.code}] RGB -> R={self._r} G={self._g} B={self._b}  ({color_name})")

        self._publish_actuator({'r': self._r, 'g': self._g, 'b': self._b})

    def turn_off(self):
        """Turn off all channels"""
        self.set_color(0, 0, 0)

    def set_red(self):
        self.set_color(1, 0, 0)

    def set_green(self):
        self.set_color(0, 1, 0)

    def set_blue(self):
        self.set_color(0, 0, 1)

    def is_on(self):
        """Return True if any channel is active"""
        return (self._r, self._g, self._b) != (0, 0, 0)

    def get_color(self):
        """Return current (r, g, b) tuple"""
        return (self._r, self._g, self._b)

    def get_last_color(self):
        """Return the last non-off color (used by toggle in Rule 9)"""
        return self._last_color

    def cleanup(self):
        self.turn_off()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin_r)
            GPIO.cleanup(self.pin_g)
            GPIO.cleanup(self.pin_b)
