"""Buzzer component - DB"""

import time
import threading

from components.base import BaseComponent

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class Buzzer(BaseComponent):
    """
    Door Buzzer - DB
    Controls a buzzer with single beep and continuous alarm modes.
    Publishes its own actuator events on every action.
    """

    def __init__(self, settings, publisher=None):
        super().__init__('DB', settings, publisher)
        self.pin = settings.get('pin', 22)

        self.state = False
        self.alarming = False
        self._alarm_thread = None

        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT)
            GPIO.output(self.pin, GPIO.LOW)

    def _gpio_on(self):
        self.state = True
        if not self.simulate and RPI_AVAILABLE:
            GPIO.output(self.pin, GPIO.HIGH)

    def _gpio_off(self):
        self.state = False
        if not self.simulate and RPI_AVAILABLE:
            GPIO.output(self.pin, GPIO.LOW)

    def beep(self, duration=0.5):
        """Single beep — publishes start and end"""
        print(f"[DB] Beeping ({duration}s)...")
        self._publish_actuator(True, {'action': 'beep'})
        self._gpio_on()
        time.sleep(duration)
        self._gpio_off()
        self._publish_actuator(False, {'action': 'beep'})

    def start_alarm(self, on_time=0.5, off_time=0.5):
        """Start continuous alarm"""
        if self.alarming:
            return
        self.alarming = True
        print("[DB] Alarm STARTED")
        self._publish_actuator(True, {'action': 'alarm'})
        self._alarm_thread = threading.Thread(
            target=self._alarm_loop,
            args=(on_time, off_time),
            daemon=True
        )
        self._alarm_thread.start()

    def _alarm_loop(self, on_time, off_time):
        while self.alarming:
            self._gpio_on()
            time.sleep(on_time)
            if not self.alarming:
                break
            self._gpio_off()
            time.sleep(off_time)

    def stop_alarm(self):
        """Stop continuous alarm"""
        self.alarming = False
        self._gpio_off()
        if self._alarm_thread:
            self._alarm_thread.join(timeout=1)
        print("[DB] Alarm STOPPED")
        self._publish_actuator(False, {'action': 'alarm'})

    def is_on(self):
        return self.state

    def is_alarming(self):
        return self.alarming

    def cleanup(self):
        self.stop_alarm()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)
