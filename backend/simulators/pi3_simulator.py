"""PI3 Simulator - all simulation driven by CLI commands"""

from simulators.base_simulator import BaseSimulator


class PI3Simulator(BaseSimulator):
    """
    Simulator for PI3 (Bedroom / Living Room) components.

    All events are driven exclusively by CLI commands in PI3Controller:
      9   - DPIR3 motion event
      i   - inject IR code (TOGGLE / RED / GREEN / BLUE)
      t   - on-demand DHT1 / DHT2 read
      r/g/bu/x - direct RGB light control
    """

    def start(self):
        self.running = True
        # No background threads – PI3 is fully CLI-driven in simulation.
