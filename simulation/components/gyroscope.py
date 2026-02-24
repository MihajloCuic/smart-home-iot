"""Gyroscope component (MPU-6050) - GSG"""

from components.base import BaseComponent


class Gyroscope(BaseComponent):
    """
    Gyroscope / movement detector.
    In simulation, trigger_movement() can be called to fire a movement event.
    """

    def __init__(self, code, settings, publisher=None, on_movement=None):
        super().__init__(code, settings, publisher)
        self.on_movement = on_movement
        self._last_movement = False
        self.auto_simulate = settings.get('auto_simulate', False)

    def trigger_movement(self):
        """Simulate a movement event"""
        self._handle_movement(True)
        self._handle_movement(False)

    def _handle_movement(self, moving):
        if moving and not self._last_movement:
            print(f"\n[{self.code}] Movement detected")
            self._publish_sensor(True)
            if self.on_movement:
                self.on_movement()
        self._last_movement = moving
