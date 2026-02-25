"""Button (BTN) component - momentary press button"""

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False

from components.base import BaseComponent


class Button(BaseComponent):
    """
    Momentary push button (active-low, internal pull-up).

    Fires on_press callback each time the button is pressed.

    In simulation : inject_press() simulates a single press.
    In real HW    : GPIO edge-detection (FALLING edge = button pressed).
    """

    DEBOUNCE_MS = 200  # milliseconds between recognised presses

    def __init__(self, code, settings, publisher=None, on_press=None):
        super().__init__(code, settings, publisher)
        self.pin      = settings.get('pin', 16)
        self.on_press = on_press
        self._monitoring = False

        if not self.simulate and GPIO_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # ========== SIMULATION ==========

    def inject_press(self):
        """Simulation: fire a single button press."""
        self._publish_sensor(True, extra={'action': 'press'})
        print(f"[{self.code}] Button pressed (SIM)")
        if self.on_press:
            self.on_press()

    # ========== REAL HW MONITORING ==========

    def start_monitoring(self):
        if self.simulate or self._monitoring:
            return
        if not GPIO_AVAILABLE:
            print(f"[{self.code}] GPIO not available – skipping HW monitoring")
            return
        GPIO.add_event_detect(
            self.pin,
            GPIO.FALLING,
            callback=self._gpio_callback,
            bouncetime=self.DEBOUNCE_MS,
        )
        self._monitoring = True
        print(f"[{self.code}] Button monitoring on GPIO {self.pin}")

    def _gpio_callback(self, channel):
        self._publish_sensor(True, extra={'action': 'press'})
        print(f"[{self.code}] Button pressed")
        if self.on_press:
            self.on_press()

    # ========== LIFECYCLE ==========

    def stop(self):
        self._monitoring = False

    def cleanup(self):
        self.stop()
        if not self.simulate and GPIO_AVAILABLE:
            try:
                GPIO.remove_event_detect(self.pin)
                GPIO.cleanup(self.pin)
            except Exception:
                pass
