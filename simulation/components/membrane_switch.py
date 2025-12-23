import time
import threading

try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class MembraneSwitch:
    """Door Membrane Switch (4x4 Keypad) - DMS"""
    
    KEYS = [
        ['1', '2', '3', 'A'],
        ['4', '5', '6', 'B'],
        ['7', '8', '9', 'C'],
        ['*', '0', '#', 'D']
    ]
    
    def __init__(self, settings, callback=None):
        self.settings = settings
        self.row_pins = settings.get('row_pins', [6, 13, 19, 26])
        self.col_pins = settings.get('col_pins', [12, 16, 20, 21])
        self.simulate = settings.get('simulate', True)
        self.callback = callback
        
        self.running = False
        self.thread = None
        self.last_key = None
        self._simulated_key = None
        
        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            for pin in self.row_pins:
                GPIO.setup(pin, GPIO.OUT)
                GPIO.output(pin, GPIO.LOW)
            for pin in self.col_pins:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    
    def read_key(self):
        """Read pressed key"""
        if self.simulate:
            key = self._simulated_key
            self._simulated_key = None
            return key
        elif RPI_AVAILABLE:
            for i, row_pin in enumerate(self.row_pins):
                GPIO.output(row_pin, GPIO.HIGH)
                for j, col_pin in enumerate(self.col_pins):
                    if GPIO.input(col_pin) == GPIO.HIGH:
                        GPIO.output(row_pin, GPIO.LOW)
                        return self.KEYS[i][j]
                GPIO.output(row_pin, GPIO.LOW)
        return None
    
    def set_key(self, key):
        """Set simulated key press"""
        self._simulated_key = key
        self.last_key = key
    
    def start_monitoring(self):
        """Start monitoring in background"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
    
    def _monitor_loop(self):
        """Monitor loop - triggers callback on key press"""
        while self.running:
            key = self.read_key()
            if key: 
                self.last_key = key
                if self.callback:
                    self.callback(key)
                time.sleep(0.3)
            time.sleep(0.05)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            for pin in self.row_pins + self.col_pins:
                GPIO.cleanup(pin)