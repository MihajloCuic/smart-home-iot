try:
    import RPi.GPIO as GPIO
    RPI_AVAILABLE = True
except ImportError: 
    RPI_AVAILABLE = False


class DoorLight: 
    """Door Light (LED diode) - DL"""
    
    def __init__(self, settings):
        self.settings = settings
        self.pin = settings.get('pin', 27)
        self.simulate = settings.get('simulate', True)
        self.state = False
        
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
    
    def toggle(self):
        if self.state:
            self.turn_off()
        else:
            self.turn_on()
    
    def is_on(self):
        return self.state
    
    def cleanup(self):
        if not self.simulate and RPI_AVAILABLE:
            GPIO.cleanup(self.pin)