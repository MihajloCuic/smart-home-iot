"""4-Digit 7-Segment Display component - 4SD"""

from components.base import BaseComponent


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

    def show(self, text):
        self._value = str(text)
        print(f"[{self.code}] Display -> {self._value}")
        self._publish_actuator(self._value)

    def clear(self):
        self._value = ""
        print(f"[{self.code}] Display cleared")
        self._publish_actuator(self._value)

    def get_value(self):
        return self._value
