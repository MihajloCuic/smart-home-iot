"""Simulated 4-digit 7-segment display component (4SD)

API:
 - show_time(seconds): display MMSS or HHMM as appropriate
 - blink(): start blinking display (simulated)
 - stop_blink(): stop blinking
 - add_seconds(n): add seconds to currently shown timer
 - set_text(text): show arbitrary text (up to 4 chars)
"""
import threading
import time

from components.base import BaseComponent


class FourDigitDisplay(BaseComponent):
    def __init__(self, code, cfg, publisher=None):
        super().__init__(code, cfg, publisher)
        self._lock = threading.Lock()
        self._text = "    "
        self._blink = False
        self._blink_thread = None
        self._timer_seconds = 0

    def show_time(self, seconds: int):
        with self._lock:
            self._timer_seconds = max(0, int(seconds))
            mm = self._timer_seconds // 60
            ss = self._timer_seconds % 60
            # format as MMSS (e.g., 01:23 -> '0123') with colon implied
            self._text = f"{mm:02d}{ss:02d}"
            self._publish_state()

    def set_text(self, text: str):
        with self._lock:
            t = str(text)[:4].rjust(4)
            self._text = t
            self._publish_state()

    def add_seconds(self, n: int):
        with self._lock:
            self._timer_seconds = max(0, self._timer_seconds + int(n))
            self.show_time(self._timer_seconds)

    def blink(self):
        with self._lock:
            if self._blink:
                return
            self._blink = True
            self._blink_thread = threading.Thread(target=self._blink_loop, daemon=True)
            self._blink_thread.start()

    def stop_blink(self):
        with self._lock:
            self._blink = False

    def _blink_loop(self):
        visible = True
        while True:
            with self._lock:
                if not self._blink:
                    break
                if visible:
                    # show current time
                    self._publish_state()
                else:
                    # show blank
                    self._publish_state(blank=True)
            visible = not visible
            time.sleep(0.5)

    def _publish_state(self, blank=False):
        payload = {
            'display': '' if blank else self._text,
            'seconds': self._timer_seconds,
            'blinking': self._blink,
        }
        try:
            self._publish_actuator(payload)
        except Exception:
            pass

    # Helper for simulators and status
    def get_state(self):
        with self._lock:
            return {'text': self._text, 'seconds': self._timer_seconds, 'blinking': self._blink}
