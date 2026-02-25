#!/usr/bin/env python3
"""
Smart Home IoT - Multi-PI Controller
"""

from settings import load_settings
from controllers import PI1Controller, PI2Controller, PI3Controller


# ========== HELP MENUS ==========

PI1_HELP = """
==================================================
  PI1 - ENTRANCE CONTROLLER
==================================================
  s - Status          h - Help
  b - Back to PI menu q - Quit

  ACTUATORS:
  1 - Toggle light    4 - Beep
  2 - Light ON        5 - Start alarm
  3 - Light OFF       6 - Stop alarm

  SIMULATION:
  7 - Door OPEN       9 - Trigger motion
  8 - Door CLOSE      0 - Press key

  OCCUPANCY (Rule 5):
  p+ - Person enters  p- - Person leaves
=================================================="""

PI3_HELP = """
==================================================
  PI3 - BEDROOM CONTROLLER
==================================================
  s - Status          h - Help
  b - Back to PI menu q - Quit

  ACTUATORS:
  1 - Toggle light    4 - Beep
  2 - Light ON        5 - Start alarm
  3 - Light OFF       6 - Stop alarm

  RGB LIGHT (Rule 9):
  r - Red             g - Green
  bu - Blue            x - RGB off

  SIMULATION:
  7 - Door OPEN       9 - Trigger motion
  8 - Door CLOSE      0 - Press key
  i - Inject IR code

  OCCUPANCY (Rule 5):
  p+ - Person enters  p- - Person leaves
=================================================="""

PI2_HELP = """
==================================================
    PI2 - KITCHEN CONTROLLER
==================================================
    s - Status          h - Help
    b - Back to PI menu q - Quit

    ACTUATORS:
    5 - Start alarm     6 - Stop alarm

    TIMER (Rule 8):
        t - Set timer sec   i - Set BTN increment
        a - Add seconds
    k - Press button

    SIMULATION:
    7 - Door OPEN       9 - Trigger motion
    8 - Door CLOSE      u - Set distance
    g - Gyro movement

    OCCUPANCY (Rule 5):
    p+ - Person enters  p- - Person leaves
=================================================="""


# ========== SHARED STATE ==========

# Mutable list so both PI controllers share the same person count.
# A lambda over person_count[0] always reads the current value.
# Rule 5: alarm triggers when person_count[0] == 0 and motion is detected.
person_count = [0]


# ========== CONTROLLER REGISTRY ==========
# Each entry: key -> (display label, ControllerClass, help_text, pi_key)

CONTROLLERS = {
    '1': ("PI1 - Entrance Controller", PI1Controller, PI1_HELP, 'PI1'),
    '2': ("PI2 - Kitchen Controller",  PI2Controller, PI2_HELP, 'PI2'),
    '3': ("PI3 - Bedroom Controller",  PI3Controller, PI3_HELP, 'PI3'),
}


# ========== PI SELECTION MENU ==========

def choose_pi():
    """
    Display the PI selection menu and return the chosen key,
    or None if the user wants to quit.
    """
    print("\n" + "=" * 50)
    print("  SMART HOME IoT")
    print("=" * 50)
    print("  Select a PI device to control:\n")
    for key, (label, _, _, _) in CONTROLLERS.items():
        print(f"    {key} - {label}")
    print("\n    q - Quit")
    print("=" * 50)

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
    Handles 'p+' and 'p-' for occupancy management (Rule 5).
    Returns True  -> caller should show PI menu again
    Returns False -> caller should exit the program
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

        # Occupancy management (Rule 5)
        elif cmd == 'p+':
            person_count[0] = person_count[0] + 1
            print(f"[HOME] Persons in home: {person_count[0]}")
            if hasattr(controller, "publish_status"):
                controller.publish_status()
        elif cmd == 'p-':
            person_count[0] = max(0, person_count[0] - 1)
            print(f"[HOME] Persons in home: {person_count[0]}")
            if hasattr(controller, "publish_status"):
                controller.publish_status()

        else:
            try:
                result = controller.handle_command(cmd)
                if result is None:
                    print("Unknown command. Press 'h' for help.")
            except Exception as e:
                print(f"[ERROR] {e}")


# ========== MAIN ==========

def main():
    """Main entry point - loads settings then loops over the PI selection menu"""
    all_settings = load_settings()  # full dict: {"mqtt": {...}, "influx": {...}, "PI1": {...}, ...}
    mqtt_cfg = all_settings.get("mqtt", {})

    while True:
        choice = choose_pi()

        if choice is None:
            print("\n[SYSTEM] Goodbye!\n")
            break

        label, ControllerClass, help_text, pi_key = CONTROLLERS[choice]
        pi_settings = all_settings[pi_key]

        print(f"\n[SYSTEM] Starting {label}...")
        # Both controllers receive shared mqtt_cfg and a lambda over the shared person_count list
        def set_person_count(value):
            person_count[0] = max(0, int(value))

        controller = ControllerClass(
            pi_settings,
            mqtt_cfg=mqtt_cfg,
            get_person_count=lambda: person_count[0],
            set_person_count=set_person_count,
        )
        controller.start()

        keep_running = run_loop(controller, help_text)

        print(f"\n[SYSTEM] Stopping {label}...")
        controller.cleanup()
        print(f"[SYSTEM] {label} stopped.\n")

        if not keep_running:
            print("[SYSTEM] Goodbye!\n")
            break


if __name__ == "__main__":
    main()
