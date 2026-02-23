"""PI1 Simulator - entrance door sensors simulation"""

from simulators.base_simulator import BaseSimulator


class PI1Simulator(BaseSimulator):
    """
    Simulator for PI1 (Entrance) components.

    Simulates automatically:
      - DUS1  : ultrasonic distance sensor (random approach events)
      - DPIR1 : PIR motion sensor (random motion events)

    Not simulated here (done via CLI commands in the controller):
      - DS1   : door sensor  -> commands 7 (open) / 8 (close)
      - DMS   : keypad       -> command 0 (press key)
    """

    def start(self):
        self.running = True
        self._maybe_start("DUS1",  self._simulate_ultrasonic)
        self._maybe_start("DPIR1", self._simulate_motion)
