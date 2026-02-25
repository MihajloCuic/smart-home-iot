"""Base simulator - minimal shared infrastructure for all PI simulators"""


class BaseSimulator:
    """
    Base class for PI simulators.

    All simulation is driven exclusively by CLI commands entered by the user.
    There are NO background threads, NO random events, and NO auto-firing sensors.

    Each controller's handle_command() method dispatches commands directly to
    component inject_* / set_* calls.  The simulator's only purpose in life is
    to provide a uniform start() / stop() interface expected by the controller.
    """

    def __init__(self, components):
        self.components = components
        self.running    = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
