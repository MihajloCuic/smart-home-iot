"""Base component class for all IoT components"""

import time


class BaseComponent:
    """
    Base class for all IoT components.
    Handles publish logic so each component owns its own data publishing.
    """

    def __init__(self, code, settings, publisher=None):
        self.code = code
        self.settings = settings
        self.simulate = settings.get('simulate', True)
        self.publish_enabled = settings.get('publish', True)
        self._publisher = publisher

    def set_publisher(self, publisher):
        """Set or replace the MQTT publisher"""
        self._publisher = publisher

    def _publish(self, value, source='sensor', extra=None):
        """Internal publish — builds payload and enqueues it"""
        if not self.publish_enabled or self._publisher is None:
            return
        device_id = self._publisher.device_info.get('id', 'UNKNOWN')
        payload = {
            'device': device_id,
            'source': source,
            'sensor': self.code,
            'value': value,
            'simulated': self.simulate,
            'ts': time.time()
        }
        if extra:
            payload.update(extra)
        self._publisher.enqueue(payload)

    def _publish_sensor(self, value, extra=None):
        """Publish a sensor reading"""
        self._publish(value, 'sensor', extra)

    def _publish_actuator(self, value, extra=None):
        """Publish an actuator state change"""
        self._publish(value, 'actuator', extra)

    def cleanup(self):
        """Override in subclasses to release GPIO resources"""
        pass
