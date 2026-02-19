"""Simple simulated gyroscope (GSG) component.

Detects movement when injected via simulate_movement() and calls on_movement callback.
"""
import time

from components.base import BaseComponent


class Gyroscope(BaseComponent):
    def __init__(self, code, cfg, publisher=None, on_movement=None):
        super().__init__(code, cfg, publisher)
        self.on_movement = on_movement
        self._last_movement = None

    def simulate_movement(self):
        self._last_movement = time.time()
        if self.on_movement:
            try:
                self.on_movement()
            except Exception:
                pass
        try:
            self._publish_actuator({'event': 'movement'})
        except Exception:
            pass

    def get_state(self):
        return {'last_movement': self._last_movement}
