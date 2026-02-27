#!/usr/bin/env python3
"""
Smart Home IoT - Multi-PI Controller

Alarm architecture
------------------
PI1 is the alarm MASTER:
  - Owns AlarmStateMachine, DB buzzer, DMS keypad.
  - Broadcasts alarm state to PI2/PI3 via MQTT topic  iot/alarm/state
  - Receives trigger events from PI2/PI3 via MQTT topic  iot/alarm/trigger
  - Receives DS2 door events from PI2     via MQTT topic  iot/alarm/door_pi2

PI2 and PI3 are alarm SLAVES:
  - Subscribe to iot/alarm/state  to track current state.
  - Publish to   iot/alarm/trigger  when their sensors detect threats.
  - PI2 also publishes DS2 events to  iot/alarm/door_pi2.

For simulation on one machine: all three controllers connect to the same
localhost MQTT broker (run via Docker).  Each controller is selected from the
menu and runs in its own session (sequential).

For real hardware: run main.py on each Pi separately; they share the MQTT
broker on the network.
"""

import subprocess
import socket

from settings import load_settings
from controllers import PI1Controller, PI2Controller, PI3Controller


# ========== HELP MENUS ==========

PI1_HELP = """
==================================================
  PI1 - ENTRANCE CONTROLLER  [ALARM MASTER]
==================================================
  s - Status          h - Help
  b - Back to PI menu q - Quit

  ACTUATORS:
  1 - Toggle light    4 - Beep
  2 - Light ON        5 - Alarm ON
  3 - Light OFF       6 - Alarm OFF

  SIMULATION:
  7 - Door OPEN       9 - Raw motion (Rule 1)
  8 - Door CLOSE      0 - DMS keys (e.g. 1234#)
  e - Person enters   o - Person exits
=================================================="""

PI2_HELP = """
==================================================
  PI2 - KITCHEN / UPSTAIRS CONTROLLER
==================================================
  s - Status          h - Help
  b - Back to PI menu q - Quit

  SIMULATION:
  7 - Door OPEN       8 - Door CLOSE
  e - Person enters   o - Person exits
  9 - Room motion only (no door, Rule 5)
  g - Gyroscope move  (Rule 6)
  p - Button press    (Rule 8b)
  d - DUS2 custom distance
=================================================="""

PI3_HELP = """
==================================================
  PI3 - BEDROOM / LIVING ROOM CONTROLLER
==================================================
  s - Status          h - Help
  b - Back to PI menu q - Quit

  RGB LIGHT (Rule 9):
  r - Red   g - Green   bu - Blue   x - Off

  SENSORS:
  t - DHT temp/humidity

  SIMULATION:
  9 - Trigger DPIR3 motion
  i - Inject IR code (TOGGLE/RED/GREEN/BLUE)
=================================================="""


# ========== WEB CAMERA (MJPG_STREAMER) ==========

def _get_local_ip():
    """Auto-detect the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def start_camera(webc_settings):
    """
    Start mjpg_streamer as a background subprocess.
    Returns the subprocess.Popen object, or None if simulated / failed.
    """
    if webc_settings.get("simulate", True):
        port = webc_settings.get("port", 8081)
        ip = _get_local_ip()
        print(f"[WEBC] Simulated camera (no real stream)")
        print(f"[WEBC] In HW mode, stream would be at: http://{ip}:{port}/?action=stream")
        return None

    port = webc_settings.get("port", 8081)
    cmd = (
        f'mjpg_streamer '
        f'-i "input_uvc.so" '
        f'-o "output_http.so -p {port} '
        f'-w /usr/local/share/mjpg-streamer/www"'
    )
    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        ip = _get_local_ip()
        print(f"[WEBC] Camera started (PID {proc.pid})")
        print(f"[WEBC] Stream at: http://{ip}:{port}/?action=stream")
        return proc
    except Exception as e:
        print(f"[WEBC] Failed to start camera: {e}")
        return None


def stop_camera(proc):
    """Terminate the mjpg_streamer subprocess."""
    if proc is None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    print("[WEBC] Camera stopped")


# ========== SHARED PERSON COUNT ==========
# Mutable list so all three controllers share the same occupant count.
# PI1 and PI2 both update it via Rule 2a (ultrasonic + PIR).
# Rule 5: alarm triggers when count == 0 and motion is detected.

person_count = [0]


def update_count(delta):
    """Adjust shared occupant count by delta (+1 enter, -1 exit), clamped >= 0."""
    person_count[0] = max(0, person_count[0] + delta)
    print(f"[HOME] Persons in home: {person_count[0]}")


def set_count(value):
    """Set absolute person count (received from MQTT sync)."""
    person_count[0] = max(0, int(value))


# ========== CONTROLLER REGISTRY ==========
# key -> (display label, ControllerClass, help_text, settings_key, extra_kwargs_fn)

def _pi1_extra():
    return {"update_person_count": update_count, "set_person_count": set_count}

def _pi2_extra():
    return {"update_person_count": update_count, "set_person_count": set_count}

def _pi3_extra():
    return {"set_person_count": set_count}

CONTROLLERS = {
    '1': ("PI1 - Entrance Controller [MASTER]", PI1Controller, PI1_HELP, 'PI1', _pi1_extra),
    '2': ("PI2 - Kitchen Controller",           PI2Controller, PI2_HELP, 'PI2', _pi2_extra),
    '3': ("PI3 - Bedroom Controller",           PI3Controller, PI3_HELP, 'PI3', _pi3_extra),
}


# ========== PI SELECTION MENU ==========

def choose_pi():
    """Display the PI selection menu; return chosen key or None to quit."""
    print("\n" + "=" * 52)
    print("  SMART HOME IoT")
    print("=" * 52)
    print("  Select a PI device to control:\n")
    for key, (label, *_) in CONTROLLERS.items():
        print(f"    {key} - {label}")
    print("\n    q - Quit")
    print("=" * 52)

    while True:
        try:
            cmd = input("\n> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            return None

        if cmd == 'q':
            return None
        if cmd in CONTROLLERS:
            return cmd
        print(f"  Invalid choice. Enter one of: {', '.join(CONTROLLERS.keys())}, q")


# ========== COMMAND LOOP ==========

def run_loop(controller, help_text):
    """
    Generic interactive command loop for any controller.
    Returns True  -> back to PI menu
    Returns False -> exit program
    """
    print(f"\n[SYSTEM] Running...  (press 'h' for help, 'b' to go back)\n")
    print(help_text)

    while True:
        try:
            cmd = input("\n> ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting...")
            return False

        if not cmd:
            continue
        elif cmd == 'q':
            print("\nExiting...")
            return False
        elif cmd == 'b':
            print("\n[SYSTEM] Returning to PI menu...")
            return True
        elif cmd == 'h':
            print(help_text)
        elif cmd == 's':
            controller.show_status()
        else:
            try:
                result = controller.handle_command(cmd)
                if result is None:
                    print("Unknown command. Press 'h' for help.")
            except Exception as exc:
                print(f"[ERROR] {exc}")


# ========== MAIN ==========

def main():
    """Load settings then loop over the PI selection menu."""
    all_settings = load_settings()
    mqtt_cfg     = all_settings.get("mqtt", {})

    while True:
        choice = choose_pi()

        if choice is None:
            print("\n[SYSTEM] Goodbye!\n")
            break

        label, ControllerClass, help_text, pi_key, extra_fn = CONTROLLERS[choice]
        pi_settings = all_settings[pi_key]

        print(f"\n[SYSTEM] Starting {label}...")

        # Start web camera for PI1 (Rule 10)
        camera_proc = None
        if pi_key == 'PI1':
            webc_cfg = pi_settings.get("sensors", {}).get("WEBC", {})
            if webc_cfg:
                camera_proc = start_camera(webc_cfg)

        extra = extra_fn()
        controller = ControllerClass(
            pi_settings,
            mqtt_cfg          = mqtt_cfg,
            get_person_count  = lambda: person_count[0],
            **extra,
        )
        controller.start()

        keep_running = run_loop(controller, help_text)

        print(f"\n[SYSTEM] Stopping {label}...")
        stop_camera(camera_proc)
        controller.cleanup()
        print(f"[SYSTEM] {label} stopped.\n")

        if not keep_running:
            print("[SYSTEM] Goodbye!\n")
            break


if __name__ == "__main__":
    main()
