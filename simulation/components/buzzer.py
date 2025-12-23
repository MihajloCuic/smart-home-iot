import time
import threading

try: 
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class Buzzer:
    """Door Buzzer - DB"""
    
    def __init__(self, settings):
        self.settings = settings
        self.pin = settings.get('pin', 22)
        self.simulate = settings.get('simulate', True)
        
        self.state = False
        self.alarming = False
        self._alarm_thread = None
        
        if not self.simulate and RPI_AVAILABLE:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.pin, GPIO.OUT)
            GPIO.output(self.pin, GPIO.LOW)
    
    def turn_on(self):
        self.state = True
        if not self.simulate and RPI_AVAILABLE:
            GPIO.output(self.pin, GPIO.HIGH)
    
    def turn_off(self):
        self.state = False
        if not self.simulate and RPI_AVAILABLE: 
            GPIO.output(self.pin, GPIO.LOW)
    
    def beep(self, duration=0.5):
        """Single beep"""
        self.turn_on()
        time.sleep(duration)
        self.turn_off()
    
    def start_alarm(self, on_time=0.5, off_time=0.5):
        """Start continuous alarm"""
        self.alarming = True
        self._alarm_thread = threading.Thread(
            target=self._alarm_loop,
            args=(on_time, off_time),
            daemon=True
        )
        self._alarm_thread.start()
    
    def _alarm_loop(self, on_time, off_time):
        while self.alarming:
            self.turn_on()
            time.sleep(on_time)
            if not self.alarming:
                break
            self.turn_off()
            time.sleep(off_time)
    
    def stop_alarm(self):
        """Stop alarm"""
        self.alarming = False
        self.turn_off()
        if self._alarm_thread:
            self._alarm_thread.join(timeout=1)
    
    def is_on(self):
        return self.state
    
    def is_alarming(self):
        return self.alarming
    
    def cleanup(self):
        self.stop_alarm()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)