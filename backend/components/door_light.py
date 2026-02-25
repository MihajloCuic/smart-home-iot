"""Door Light component (LED diode) - DL"""

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class DoorLight(BaseComponent):
    """
    Door Light (LED diode) - DL
    Controls an LED. Publishes its own state changes on every turn_on / turn_off.
    """

    def __init__(self, code, settings, publisher=None):
        super().__init__(code, settings, publisher)
        self.pin = settings.get('pin', 27)
        self.state = False

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT)
            GPIO.output(self.pin, GPIO.LOW)

    def turn_on(self, reason=None):
        self.state = True
        if not self.simulate and RPI_AVAILABLE:
            GPIO.output(self.pin, GPIO.HIGH)
        msg = f"[{self.code}] Light ON"
        if reason:
            msg += f" ({reason})"
        print(msg)
        self._publish_actuator(True)

    def turn_off(self, reason=None):
        self.state = False
        if not self.simulate and RPI_AVAILABLE:
            GPIO.output(self.pin, GPIO.LOW)
        msg = f"[{self.code}] Light OFF"
        if reason:
            msg += f" ({reason})"
        print(msg)
        self._publish_actuator(False)

    def toggle(self):
        if self.state:
            self.turn_off()
        else:
            self.turn_on()

    def is_on(self):
        return self.state

    def cleanup(self):
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)
