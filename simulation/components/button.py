"""Simple button component (single push button)

Provides simulate() to inject presses and an on_press callback.
"""
import threading
import time

from components.base import BaseComponent


class Button(BaseComponent):
    def __init__(self, code, cfg, publisher=None, on_press=None):
        super().__init__(code, cfg, publisher)
        self.on_press = on_press
        self._last_pressed = None

    def press(self):
        """Simulate a button press; call callback and publish."""
        self._last_pressed = time.time()
        if self.on_press:
            try:
                self.on_press()
            except Exception:
                pass
        try:
            self._publish_actuator({'event': 'pressed'})
        except Exception:
            pass

    def get_state(self):
        return {'last_pressed': self._last_pressed}
