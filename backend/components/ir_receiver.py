"""IR Receiver component"""

import threading
import time

from components.base import BaseComponent

try:
    import evdev
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False


class IRReceiver(BaseComponent):
    """
    IR Remote Control Receiver.

    Simulation: inject_code(code) simulates receiving a remote code string.
    Real HW: uses evdev to read key events from /dev/input/event*.

    The on_code callback is wired by the controller (Rule 9).
    Follows the same monitoring pattern as MotionSensor and MembraneSwitch.
    """

    def __init__(self, code, settings, publisher=None, on_code=None):
        super().__init__(code, settings, publisher)
        self.pin = settings.get('pin', 27)
        self.on_code = on_code

        self.running = False
        self._thread = None
        self._injected_code = None
        self._device = None

        if not self.simulate and EVDEV_AVAILABLE:
            self._device = self._find_device()

    def _find_device(self):
        """Locate the IR receiver input device under /dev/input/"""
        for path in evdev.list_devices():
            try:
                dev = evdev.InputDevice(path)
                if 'ir' in dev.name.lower() or 'remote' in dev.name.lower():
                    return dev
            except Exception:
                pass
        return None

    def inject_code(self, code):
        """
        Inject a simulated IR code (simulation mode).
        The monitoring thread picks this up on the next poll cycle.
        Mirrors set_motion() and set_key() on other components.
        """
        self._injected_code = code

    def start_monitoring(self):
        """Start background thread to listen for IR codes"""
        self.running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def _monitor_loop(self):
        if self.simulate:
            self._sim_loop()
        elif self._device is not None:
            self._hw_loop()

    def _sim_loop(self):
        """Poll for injected codes in simulation mode"""
        while self.running:
            code = self._injected_code
            if code is not None:
                self._injected_code = None
                self._on_code_received(code)
            time.sleep(0.05)

    def _hw_loop(self):
        """Read evdev events from the IR receiver device"""
        for event in self._device.read_loop():
            if not self.running:
                break
            if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                code = str(event.code)
                self._on_code_received(code)

    def _on_code_received(self, code):
        """Internal handler: print, publish, then call the controller hook."""
        print(f"\n[{self.code}] IR code received: '{code}'")
        self._publish_sensor(code)
        if self.on_code:
            self.on_code(code)

    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)

    def cleanup(self):
        self.stop()
        if self._device is not None:
            try:
                self._device.close()
            except Exception:
                pass
