import time
import threading

try: 
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError:
    RPI_AVAILABLE = False


class UltrasonicSensor:
    """Door Ultrasonic Sensor - DUS1"""
    
    def __init__(self, settings, callback=None):
        self.settings = settings
        self.trigger_pin = settings.get('trigger_pin', 23)
        self.echo_pin = settings.get('echo_pin', 24)
        self.simulate = settings.get('simulate', True)
        self.callback = callback
        
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
        """Set distance (for simulation)"""
        self.distance = distance
    
    def start_monitoring(self, interval=2.0):
        """Start monitoring in background"""
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, args=(interval,), daemon=True)
        self.thread.start()
    
    def _monitor_loop(self, interval):
        """Monitor loop - triggers callback each interval and on alert changes"""
        while self.running:
            dist = self.measure_distance()
            is_alert = 0 <= dist < 30

            if self.callback:
                self.callback(dist, is_alert)
            self._last_alert = is_alert
            
            time.sleep(interval)
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def cleanup(self):
        self.stop()
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.trigger_pin)
            GPIO.cleanup(self.echo_pin)