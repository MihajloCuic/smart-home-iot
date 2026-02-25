"""Gyroscope / Accelerometer sensor (GSG) - MPU-6050 via I2C"""

import math
import random
import threading
import time

try:
    from mpu6050 import mpu6050
    MPU6050_AVAILABLE = True
except ImportError:
    MPU6050_AVAILABLE = False

from components.base import BaseComponent


class GyroscopeSensor(BaseComponent):
    """
    6-axis IMU sensor (accelerometer + gyroscope) using MPU-6050 over I2C.

    Monitors for significant physical displacement / tilt.
    Fires on_displacement callback when acceleration delta exceeds threshold.

    Used for Rule 6: significant movement of a monitored object → alarm trigger.

    In simulation : inject_displacement(ax, ay, az) or inject_significant_move().
    In real HW    : continuous I2C polling at POLL_INTERVAL seconds.
    """

    # Minimum acceleration delta (in g) that counts as a significant move
    DISPLACEMENT_THRESHOLD = 0.5
    POLL_INTERVAL          = 0.2   # seconds between readings

    def __init__(self, code, settings, publisher=None, on_displacement=None):
        super().__init__(code, settings, publisher)
        self.i2c_address    = int(settings.get('address', '0x68'), 16)
        self.on_displacement = on_displacement

        self._monitoring  = False
        self._thread      = None
        self._sensor      = None

        # Last known accelerometer reading (used to compute delta)
        self._last_accel = {'x': 0.0, 'y': 0.0, 'z': 1.0}  # resting: 1 g on z-axis

        # Simulated state
        self._sim_accel = {'x': 0.0, 'y': 0.0, 'z': 1.0}
        self._sim_gyro  = {'x': 0.0, 'y': 0.0, 'z': 0.0}

        if not self.simulate and MPU6050_AVAILABLE:
            try:
                self._sensor = mpu6050(self.i2c_address)
                print(f"[{self.code}] MPU-6050 at 0x{self.i2c_address:02X}")
            except Exception as e:
                print(f"[{self.code}] MPU-6050 init error: {e}")

    # ========== READ ==========

    def read(self):
        """Return current accelerometer + gyroscope data as a dict."""
        if self.simulate:
            return {
                'accel': self._sim_accel.copy(),
                'gyro':  self._sim_gyro.copy(),
            }
        if self._sensor:
            try:
                return {
                    'accel': self._sensor.get_accel_data(),
                    'gyro':  self._sensor.get_gyro_data(),
                }
            except Exception:
                pass
        return {'accel': {'x': 0.0, 'y': 0.0, 'z': 1.0},
                'gyro':  {'x': 0.0, 'y': 0.0, 'z': 0.0}}

    # ========== SIMULATION ==========

    def inject_displacement(self, ax, ay, az, gx=0.0, gy=0.0, gz=0.0):
        """
        Simulation: inject specific sensor values and evaluate displacement.
        Triggers on_displacement if delta exceeds DISPLACEMENT_THRESHOLD.
        """
        self._sim_accel = {'x': ax, 'y': ay, 'z': az}
        self._sim_gyro  = {'x': gx, 'y': gy, 'z': gz}
        self._evaluate_accel({'x': ax, 'y': ay, 'z': az})

    def inject_significant_move(self):
        """Simulation: inject a clearly significant movement (guaranteed to exceed threshold)."""
        ax = random.uniform(0.9, 1.5)
        ay = random.uniform(0.9, 1.5)
        az = random.uniform(0.0, 0.3)
        print(f"[{self.code}] Injecting significant move (ax={ax:.2f}, ay={ay:.2f}, az={az:.2f}) (SIM)")
        self.inject_displacement(ax, ay, az)

    # ========== REAL HW MONITORING ==========

    def start_monitoring(self):
        if self.simulate or self._monitoring:
            return
        if self._sensor is None:
            print(f"[{self.code}] No HW sensor – skipping monitoring")
            return
        self._monitoring = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        print(f"[{self.code}] Monitoring started (threshold={self.DISPLACEMENT_THRESHOLD} g)")

    def _monitor_loop(self):
        while self._monitoring:
            try:
                accel = self._sensor.get_accel_data()
                self._evaluate_accel(accel)
            except Exception:
                pass
            time.sleep(self.POLL_INTERVAL)

    # ========== INTERNAL ==========

    def _evaluate_accel(self, accel):
        """Compute acceleration delta vs last reading; fire callback if threshold exceeded."""
        dx = accel.get('x', 0.0) - self._last_accel['x']
        dy = accel.get('y', 0.0) - self._last_accel['y']
        dz = accel.get('z', 1.0) - self._last_accel['z']
        delta = math.sqrt(dx*dx + dy*dy + dz*dz)

        # Always update last reading
        self._last_accel = {
            'x': accel.get('x', 0.0),
            'y': accel.get('y', 0.0),
            'z': accel.get('z', 1.0),
        }

        if delta >= self.DISPLACEMENT_THRESHOLD:
            self._publish_sensor(
                round(delta, 4),
                extra={
                    'ax':          round(accel.get('x', 0.0), 4),
                    'ay':          round(accel.get('y', 0.0), 4),
                    'az':          round(accel.get('z', 1.0), 4),
                    'delta':       round(delta, 4),
                    'significant': True,
                },
            )
            print(f"[{self.code}] Significant displacement! delta={delta:.3f} g")
            if self.on_displacement:
                self.on_displacement(delta, accel)

    # ========== LIFECYCLE ==========

    def stop(self):
        self._monitoring = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def cleanup(self):
        self.stop()
