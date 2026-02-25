"""Gyroscope component (MPU-6050) - GSG"""

import math
import threading
import time

from components.base import BaseComponent

try:
    import smbus2
    SMBUS_AVAILABLE = True
except ImportError:
    SMBUS_AVAILABLE = False
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
        self.i2c_bus = int(settings.get('i2c_bus', 1))
        self.i2c_address = int(settings.get('i2c_address', 0x68))
        self.poll_interval = float(settings.get('poll_interval', 0.2))
        self.accel_threshold_g = float(settings.get('accel_threshold_g', 0.35))
        self.gyro_threshold_dps = float(settings.get('gyro_threshold_dps', 60.0))

        self._bus = None
        self._thread = None
        self._running = False

        if not self.simulate and SMBUS_AVAILABLE:
            self._bus = smbus2.SMBus(self.i2c_bus)
            # Wake up MPU-6050
            self._bus.write_byte_data(self.i2c_address, 0x6B, 0)

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
    
    def start_monitoring(self):
        if self.simulate or not SMBUS_AVAILABLE or self._bus is None:
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self):
        while self._running:
            moving = self._detect_movement()
            self._handle_movement(moving)
            time.sleep(self.poll_interval)

    def _read_word_2c(self, reg):
        high = self._bus.read_byte_data(self.i2c_address, reg)
        low = self._bus.read_byte_data(self.i2c_address, reg + 1)
        val = (high << 8) + low
        if val >= 0x8000:
            val = -((65535 - val) + 1)
        return val

    def _detect_movement(self):
        # Accelerometer registers (0x3B - 0x40), Gyro registers (0x43 - 0x48)
        ax = self._read_word_2c(0x3B) / 16384.0
        ay = self._read_word_2c(0x3D) / 16384.0
        az = self._read_word_2c(0x3F) / 16384.0
        gx = self._read_word_2c(0x43) / 131.0
        gy = self._read_word_2c(0x45) / 131.0
        gz = self._read_word_2c(0x47) / 131.0

        accel_mag = math.sqrt(ax * ax + ay * ay + az * az)
        gyro_mag = math.sqrt(gx * gx + gy * gy + gz * gz)

        accel_delta = abs(accel_mag - 1.0)
        return accel_delta >= self.accel_threshold_g or gyro_mag >= self.gyro_threshold_dps

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if self._bus:
            try:
                self._bus.close()
            except Exception:
                pass
