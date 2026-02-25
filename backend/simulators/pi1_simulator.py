"""PI1 Simulator - entrance door sensors simulation"""

from simulators.base_simulator import BaseSimulator


class PI1Simulator(BaseSimulator):
    """
    Simulator for PI1 (Entrance) components.

    Nothing is auto-simulated for PI1. All events are driven by CLI commands:
      - e / o : person enters / exits  (DUS1 + DPIR1, Rule 2)
      - 9     : raw PIR motion          (DPIR1 only,  Rule 1)
      - 7 / 8 : door open / close       (DS1,         Rule 3 / 4)
      - 0     : keypad key(s)            (DMS,         Rule 4)

    Why no auto-simulation?
    DPIR1 random events without a matching DUS1 reading produce meaningless
    output (only Rule 1 light, no Rule 2 counting). DUS1 random oscillation
    caused incorrect Rule 2b exits. Full manual control makes testing clear.
    """

    def start(self):
        self.running = True
        # No background threads — PI1 is fully CLI-driven in simulation.
