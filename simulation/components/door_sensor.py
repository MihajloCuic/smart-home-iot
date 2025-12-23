import time
import threading

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError: 
    RPI_AVAILABLE = False


class DoorSensor: 
    """Door Sensor (Button) - DS1"""
    
    def __init__(self, settings, callback=None):
        self.settings = settings
        self.pin = settings.get('pin', 17)
        self.simulate = settings.get('simulate', True)
        self.callback = callback
        
        self.running = False
        self.thread = None
        self.state = False  # False = closed, True = open
        self._last_state = False
        
        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    def read(self):
        """Read current door state"""
        if self.simulate:
            return self.state
        elif RPI_AVAILABLE:
            return GPIO.input(self.pin) == GPIO.HIGH
        return False
    
    def set_state(self, state):
        """Set door state (for simulation)"""
        self.state = state
    
    def start_monitoring(self):
        """Start monitoring in background"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    def _monitor_loop(self):
        """Monitor loop - only triggers callback on change"""
        while self.running:
            current_state = self.read()
            if current_state != self._last_state:
                if self.callback:
                    self.callback(current_state)
                self._last_state = current_state
            time.sleep(0.1)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)