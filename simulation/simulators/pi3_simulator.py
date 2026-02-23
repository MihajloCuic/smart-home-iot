"""PI3 Simulator - bedroom sensors simulation"""

from simulators.base_simulator import BaseSimulator


class PI3Simulator(BaseSimulator):
    """
    Simulator for PI3 (Bedroom) components.

    Simulates automatically:
      - DPIR3 : PIR motion sensor (random motion events)
      - DHT1  : temperature & humidity sensor (slow drift)
      - DHT2  : temperature & humidity sensor (slow drift)
      - IR    : IR remote control (occasional random code)

    Not simulated here (done via CLI commands in the controller):
      - DS2   : door sensor  -> commands 7 (open) / 8 (close)
      - DMS   : keypad       -> command 0 (press key)
      - IR    : manual inject -> command i (inject IR code)
    """

    def start(self):
        self.running = True
        self._maybe_start("DPIR3", self._simulate_motion)
        self._maybe_start("DHT1",  self._simulate_dht)
        self._maybe_start("DHT2",  self._simulate_dht)
        self._maybe_start("IR",    self._simulate_ir)
