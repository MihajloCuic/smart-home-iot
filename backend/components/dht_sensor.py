"""DHT Temperature and Humidity Sensor - DHT1 / DHT2"""

import random

from components.base import BaseComponent

try:
    import Adafruit_DHT
    DHT_AVAILABLE = True
except ImportError:
    DHT_AVAILABLE = False


class DHTSensor(BaseComponent):
    """
    DHT Temperature and Humidity Sensor.
    Code is passed as a parameter (DHT1 or DHT2) so the same class
    can represent both sensors on PI3.

    Simulation: generates random temperature (18-28 C) and humidity (40-70%).
    Real HW: uses Adafruit_DHT library with DHT22 sensor type.
    """

    DHT_SENSOR_TYPE = 22  # DHT22

    def __init__(self, code, settings, publisher=None):
        super().__init__(code, settings, publisher)
        self.pin = settings.get('pin', 4)
        self._temp = round(random.uniform(18.0, 28.0), 1)
        self._humidity = round(random.uniform(40.0, 70.0), 1)

    def read(self):
        """
        Read temperature and humidity.
        Returns (temperature_celsius, humidity_percent) tuple.
        In simulation, returns the last simulated values.
        On real HW, calls Adafruit_DHT.read_retry().
        """
        if self.simulate:
            return (self._temp, self._humidity)
        elif DHT_AVAILABLE:
            humidity, temperature = Adafruit_DHT.read_retry(
                self.DHT_SENSOR_TYPE, self.pin
            )
            if humidity is not None and temperature is not None:
                self._temp = round(temperature, 1)
                self._humidity = round(humidity, 1)
        return (self._temp, self._humidity)

    def set_values(self, temp, humidity):
        """Inject simulated values (used by SensorSimulator)"""
        self._temp = round(temp, 1)
        self._humidity = round(humidity, 1)

    def read_and_publish(self, silent=False):
        """Read current values, publish them, optionally print, and return them."""
        temp, humidity = self.read()
        self._publish_sensor({'temperature': temp, 'humidity': humidity})
        if not silent:
            print(f"[{self.code}] Temp={temp}C  Humidity={humidity}%")
        return (temp, humidity)

    def cleanup(self):
        pass
