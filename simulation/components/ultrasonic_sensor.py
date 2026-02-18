"""Ultrasonic Distance Sensor component - DUS1"""

import time
import threading

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class UltrasonicSensor(BaseComponent):
    """
    Door Ultrasonic Sensor - DUS1
    Measures distance in centimeters.
    Publishes every reading and optionally calls on_alert when alert state changes.
    """

    ALERT_THRESHOLD_CM = 30

    def __init__(self, settings, publisher=None, on_alert=None):
        super().__init__('DUS1', settings, publisher)
        self.trigger_pin = settings.get('trigger_pin', 23)
        self.echo_pin = settings.get('echo_pin', 24)
        self.on_alert = on_alert  # Optional external hook for controller logic

        self.running = False
        self.thread = None
        self.distance = 100.0
        self._last_alert = False

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.trigger_pin, GPIO.OUT)
            GPIO.setup(self.echo_pin, GPIO.IN)
            GPIO.output(self.trigger_pin, GPIO.LOW)

    def measure_distance(self):
        """Measure distance in centimeters"""
        if self.simulate:
            return self.distance
        elif RPI_AVAILABLE:
            GPIO.output(self.trigger_pin, GPIO.HIGH)
            time.sleep(0.00001)
            GPIO.output(self.trigger_pin, GPIO.LOW)

            pulse_start = time.time()
            timeout = pulse_start + 0.1
            while GPIO.input(self.echo_pin) == GPIO.LOW:
                pulse_start = time.time()
                if pulse_start > timeout:
                    return -1

            pulse_end = time.time()
            timeout = pulse_end + 0.1
            while GPIO.input(self.echo_pin) == GPIO.HIGH:
                pulse_end = time.time()
                if pulse_end > timeout:
                    return -1

            pulse_duration = pulse_end - pulse_start
            return round(pulse_duration * 17150, 2)
        return -1

    def set_distance(self, distance):
        """Set distance (simulation only)"""
        self.distance = distance

    def start_monitoring(self, interval=2.0):
        """Start background monitoring thread"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
        self.thread.start()

    def _monitor_loop(self, interval):
        """Measure periodically; print and publish on every reading"""
        while self.running:
            dist = self.measure_distance()
            is_alert = 0 <= dist < self.ALERT_THRESHOLD_CM
            self._on_measurement(dist, is_alert)
            self._last_alert = is_alert
            time.sleep(interval)

    def _on_measurement(self, distance, is_alert):
        """
        Internal handler: called on every measurement.
        Prints only when alert state changes; always publishes.
        """
        # Print only on state transitions to avoid console spam
        if is_alert != self._last_alert:
            if is_alert:
                print(f"\n[DUS1] ALERT — Object at {distance:.1f} cm!")
            else:
                print(f"\n[DUS1] Object moved away ({distance:.1f} cm)")

        self._publish_sensor(distance, {'alert': is_alert})

        if self.on_alert:
            self.on_alert(distance, is_alert)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.trigger_pin)
            GPIO.cleanup(self.echo_pin)
