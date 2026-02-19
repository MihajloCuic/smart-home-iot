"""
Alarm State Machine for PI1 and PI3 controllers.

States:
  DISARMED  - system is off; door/motion violations do not trigger alarm
  ARMING    - correct PIN entered while DISARMED; counting down arm_delay
  ARMED     - system is active; door open starts grace period
  GRACE     - door opened while ARMED; counting down grace_period
  ALARMING  - alarm is sounding; only correct PIN stops it

Transitions:
  DISARMED + correct PIN + '#'  -> ARMING  (starts arm_delay timer)
  ARMING   + arm_delay expires  -> ARMED
  ARMING   + correct PIN + '#'  -> DISARMED (cancel arm)
  ARMED    + door_opened()      -> GRACE   (starts grace_period timer)
  GRACE    + door_closed()      -> ARMED   (cancel grace timer)
  GRACE    + grace_period expires -> ALARMING (on_alarm_start)
  ARMED/DISARMED/GRACE + trigger_alarm() -> ALARMING (on_alarm_start)
  ALARMING + correct PIN + '#'  -> DISARMED (on_alarm_stop)
"""

import threading


class AlarmStateMachine:
    """
    Thread-safe alarm state machine shared by PI1 and PI3 controllers.

    Parameters:
        correct_pin    (str)       - PIN that arms/disarms the system
        arm_delay      (int)       - seconds between ARMING and ARMED states
        grace_period   (int)       - seconds in GRACE before ALARMING
        on_alarm_start (callable)  - called when entering ALARMING state
        on_alarm_stop  (callable)  - called when leaving ALARMING state
    """

    DISARMED = 'DISARMED'
    ARMING   = 'ARMING'
    ARMED    = 'ARMED'
    GRACE    = 'GRACE'
    ALARMING = 'ALARMING'

    def __init__(self, correct_pin, arm_delay, grace_period,
                 on_alarm_start=None, on_alarm_stop=None):
        self._correct_pin    = str(correct_pin)
        self._arm_delay      = int(arm_delay)
        self._grace_period   = int(grace_period)
        self._on_alarm_start = on_alarm_start
        self._on_alarm_stop  = on_alarm_stop

        self._state       = self.DISARMED
        self._lock        = threading.Lock()
        self._pin_buffer  = []        # accumulates keys until '#'
        self._arm_timer   = None      # threading.Timer: ARMING -> ARMED
        self._grace_timer = None      # threading.Timer: GRACE -> ALARMING

    # ========== PUBLIC API ==========

    def get_state(self):
        """Return current state string"""
        with self._lock:
            return self._state

    def handle_key(self, key):
        """
        Called by the controller on every keypad key press.
        Accumulates digit keys; '#' submits the PIN; '*' clears the buffer.
        """
        with self._lock:
            if key == '*':
                self._pin_buffer.clear()
                print("[ALARM] PIN entry cleared")
                return

            if key == '#':
                entered = ''.join(self._pin_buffer)
                self._pin_buffer.clear()
                self._process_pin(entered)
                return

            self._pin_buffer.append(key)

    def door_opened(self):
        """
        Called by the controller when the door opens.
        Starts grace period only when ARMED.
        """
        with self._lock:
            if self._state == self.ARMED:
                self._enter_grace_locked()

    def door_closed(self):
        """
        Called by the controller when the door closes.
        Cancels grace period if in GRACE, returning to ARMED.
        """
        with self._lock:
            if self._state == self.GRACE:
                self._cancel_grace_timer_locked()
                self._state = self.ARMED
                print("[ALARM] Door closed during GRACE -> back to ARMED")

    def trigger_alarm(self):
        """
        Externally trigger the alarm.
        Used by Rule 3 (door open >5s) and Rule 5 (motion with no occupants).
        Only activates if not already in ALARMING state.
        """
        with self._lock:
            if self._state != self.ALARMING:
                self._cancel_arm_timer_locked()
                self._cancel_grace_timer_locked()
                self._enter_alarming_locked()

    # ========== INTERNAL TRANSITIONS (called while holding _lock) ==========

    def _process_pin(self, entered):
        """Evaluate the entered PIN and perform appropriate transition."""
        correct = (entered == self._correct_pin)

        if self._state == self.DISARMED:
            if correct:
                self._enter_arming_locked()
            else:
                print(f"[ALARM] Wrong PIN while DISARMED")

        elif self._state == self.ARMING:
            if correct:
                self._cancel_arm_timer_locked()
                self._state = self.DISARMED
                print("[ALARM] Arming cancelled -> DISARMED")
            else:
                print("[ALARM] Wrong PIN while ARMING")

        elif self._state == self.ARMED:
            if correct:
                self._state = self.DISARMED
                print("[ALARM] System disarmed -> DISARMED")
            else:
                print("[ALARM] Wrong PIN while ARMED")

        elif self._state == self.GRACE:
            if correct:
                self._cancel_grace_timer_locked()
                self._state = self.DISARMED
                print("[ALARM] Disarmed during GRACE -> DISARMED")
            else:
                print("[ALARM] Wrong PIN during GRACE - alarm will trigger soon!")

        elif self._state == self.ALARMING:
            if correct:
                self._state = self.DISARMED
                print("[ALARM] Alarm stopped -> DISARMED")
                # Call on_alarm_stop outside the lock to prevent deadlock
                self._lock.release()
                try:
                    if self._on_alarm_stop:
                        self._on_alarm_stop()
                finally:
                    self._lock.acquire()
            else:
                print("[ALARM] Wrong PIN - alarm continues")

    def _enter_arming_locked(self):
        self._state = self.ARMING
        print(f"[ALARM] ARMING... ({self._arm_delay}s until armed)")
        self._arm_timer = threading.Timer(self._arm_delay, self._arm_timer_fired)
        self._arm_timer.daemon = True
        self._arm_timer.start()

    def _arm_timer_fired(self):
        with self._lock:
            if self._state == self.ARMING:
                self._state = self.ARMED
                print("[ALARM] System ARMED")

    def _enter_grace_locked(self):
        self._state = self.GRACE
        print(f"[ALARM] GRACE PERIOD - enter PIN within {self._grace_period}s!")
        self._grace_timer = threading.Timer(self._grace_period, self._grace_timer_fired)
        self._grace_timer.daemon = True
        self._grace_timer.start()

    def _grace_timer_fired(self):
        with self._lock:
            if self._state == self.GRACE:
                self._enter_alarming_locked()

    def _enter_alarming_locked(self):
        self._state = self.ALARMING
        print("[ALARM] *** ALARM TRIGGERED! ***")
        # Release lock before calling callback to prevent potential deadlock
        # (callback calls buzzer.start_alarm() which is thread-safe but
        # should not wait on this lock)
        self._lock.release()
        try:
            if self._on_alarm_start:
                self._on_alarm_start()
        finally:
            self._lock.acquire()

    def _cancel_arm_timer_locked(self):
        if self._arm_timer is not None:
            self._arm_timer.cancel()
            self._arm_timer = None

    def _cancel_grace_timer_locked(self):
        if self._grace_timer is not None:
            self._grace_timer.cancel()
            self._grace_timer = None
