"""LCD Display - 16x2 I2C (address 0x27)"""

from components.base import BaseComponent

try:
    from RPLCD.i2c import CharLCD
    RPLCD_AVAILABLE = True
except ImportError:
    RPLCD_AVAILABLE = False


class LCDDisplay(BaseComponent):
    """
    16x2 I2C LCD Display.

    In simulation mode: prints to console instead of writing to hardware.
    On real HW: uses RPLCD.i2c.CharLCD.

    No publish is needed because this is an output-only actuator.
    The address field in settings is a hex string (e.g. "0x27").
    """

    def __init__(self, code, settings, publisher=None):
        super().__init__(code, settings, publisher)
        self.address = int(settings.get('address', '0x27'), 16)
        self._lcd = None
        self._line1 = ""
        self._line2 = ""

        if not self.simulate and RPLCD_AVAILABLE:
            self._lcd = CharLCD(
                i2c_expander='PCF8574',
                address=self.address,
                port=1,
                cols=16,
                rows=2,
                dotsize=8
            )
            self._lcd.clear()

    def show(self, line1, line2=""):
        """
        Display two lines of text on the LCD.
        Truncates each line to 16 characters.
        """
        self._line1 = str(line1)[:16]
        self._line2 = str(line2)[:16]

        if self.simulate:
            print(f"[{self.code}] LCD | {self._line1:<16} | {self._line2:<16} |")
        elif self._lcd is not None:
            self._lcd.clear()
            self._lcd.write_string(self._line1.ljust(16))
            self._lcd.crlf()
            self._lcd.write_string(self._line2.ljust(16))

    def clear(self):
        """Clear the display"""
        self._line1 = ""
        self._line2 = ""
        if self.simulate:
            print(f"[{self.code}] LCD cleared")
        elif self._lcd is not None:
            self._lcd.clear()

    def cleanup(self):
        self.clear()
        if self._lcd is not None:
            try:
                self._lcd.close(clear=True)
            except Exception:
                pass
