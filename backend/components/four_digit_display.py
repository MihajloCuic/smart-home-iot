"""4-Digit 7-Segment Display (4SD) component - TM1637 based"""

import threading
import time

try:
    import tm1637
    TM1637_AVAILABLE = True
except ImportError:
    TM1637_AVAILABLE = False

from components.base import BaseComponent


class FourDigitDisplay(BaseComponent):
    """
    4-digit 7-segment display (TM1637 module).

    Primary use: kitchen timer (Rule 8) displaying MM:SS.
    Secondary use: display any 4-character text.

    In simulation : all operations print to console.
    In real HW    : TM1637 driven via CLK and DIO GPIO pins.
    """

    def __init__(self, code, settings, publisher=None):
        super().__init__(code, settings, publisher)
        self.pin_clk = settings.get('pin_clk', 18)
        self.pin_dio = settings.get('pin_dio', 23)

        self._display       = None
        self._blink_thread  = None
        self._blink_active  = False
        self._current_text  = "    "

        if not self.simulate and TM1637_AVAILABLE:
            try:
                self._display = tm1637.TM1637(clk=self.pin_clk, dio=self.pin_dio)
                print(f"[{self.code}] TM1637 initialized (CLK={self.pin_clk}, DIO={self.pin_dio})")
            except Exception as e:
                print(f"[{self.code}] TM1637 init error: {e}")

    # ========== DISPLAY OPERATIONS ==========

    def show_time(self, total_seconds):
        """Display time as MM:SS.  Used by kitchen timer (Rule 8)."""
        total_seconds = max(0, int(total_seconds))
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        text    = f"{minutes:02d}{seconds:02d}"
        self._current_text = text

        self._publish_sensor(
            total_seconds,
            extra={'display': f"{minutes:02d}:{seconds:02d}", 'action': 'show_time'},
        )
        print(f"[{self.code}] Timer: {minutes:02d}:{seconds:02d}")

        if self._display:
            try:
                self._display.numbers(minutes, seconds)
            except Exception:
                pass

    def show_text(self, text):
        """Display up to 4 characters of arbitrary text."""
        text = str(text)[:4].ljust(4)
        self._current_text = text

        self._publish_sensor(text, extra={'action': 'show_text'})
        print(f"[{self.code}] Display: {text!r}")

        if self._display:
            try:
                self._display.show(text)
            except Exception:
                pass

    def clear(self):
        """Turn off all segments."""
        self._current_text = "    "
        if self._display:
            try:
                self._display.show("    ")
            except Exception:
                pass

    # ========== BLINK (Rule 8c: timer expired) ==========

    def start_blink(self, text="0000", interval=0.5):
        """
        Blink the display repeatedly.
        Called when the kitchen timer reaches zero (Rule 8c).
        """
        self.stop_blink()
        self._blink_active = True
        self._blink_thread = threading.Thread(
            target=self._blink_loop,
            args=(text, interval),
            daemon=True,
        )
        self._blink_thread.start()
        self._publish_sensor(text, extra={'action': 'blink_start'})
        print(f"[{self.code}] Blinking {text!r}")

    def stop_blink(self):
        """Stop blinking and clear the display."""
        if self._blink_active:
            self._blink_active = False
            self._publish_sensor(self._current_text, extra={'action': 'blink_stop'})
            print(f"[{self.code}] Blink stopped")
            if self._blink_thread:
                self._blink_thread.join(timeout=1)
                self._blink_thread = None
            self.clear()

    def _blink_loop(self, text, interval):
        visible = True
        while self._blink_active:
            if visible:
                self.show_text(text)
            else:
                self.clear()
            visible = not visible
            time.sleep(interval)

    # ========== QUERY ==========

    def is_blinking(self):
        return self._blink_active

    def get_display_text(self):
        return self._current_text

    # ========== LIFECYCLE ==========

    def stop(self):
        self.stop_blink()

    def cleanup(self):
        self.stop()
        self.clear()
