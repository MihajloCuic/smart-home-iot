"""PI2 Simulator - all simulation driven by CLI commands"""

from simulators.base_simulator import BaseSimulator


class PI2Simulator(BaseSimulator):
    """
    Simulator for PI2 (Kitchen / Upstairs) components.

    All events are driven exclusively by CLI commands in PI2Controller:
      7   - DS2 door OPEN
      8   - DS2 door CLOSE
      e   - person ENTERING  (DUS2 close distance + DPIR2 trigger)
      o   - person EXITING   (direct count decrement)
      m   - room MOTION only (DPIR2 trigger, no DUS2 change) -> Rule 5
      g   - gyroscope SIGNIFICANT MOVE -> Rule 6
      b   - BTN button press
      t   - DHT3 on-demand read
      d   - custom DUS2 distance input
    """

    def start(self):
        self.running = True
        # No background threads – PI2 is fully CLI-driven in simulation.
