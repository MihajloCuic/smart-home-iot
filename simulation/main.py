#!/usr/bin/env python3
"""
Smart Home IoT - Multi-PI Controller
"""

from settings import load_settings
from controllers import PI1Controller
# from controllers import PI2Controller  # uncomment when implemented
# from controllers import PI3Controller  # uncomment when implemented


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
=================================================="""

# Add PI2_HELP and PI3_HELP here when implemented


# ========== CONTROLLER REGISTRY ==========
# Each entry: key -> (display label, ControllerClass, help_text)

CONTROLLERS = {
    '1': ("PI1 — Entrance Controller", PI1Controller, PI1_HELP),
    # '2': ("PI2 — Kitchen Controller",  PI2Controller, PI2_HELP),
    # '3': ("PI3 — Bedroom Controller",  PI3Controller, PI3_HELP),
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
    for key, (label, _, _) in CONTROLLERS.items():
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
    Returns when the user types 'b' (back) or 'q' (quit).
    Returns True  → caller should show PI menu again
    Returns False → caller should exit the program
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
            except Exception as e:
                print(f"[ERROR] {e}")


# ========== MAIN ==========

def main():
    """Main entry point — loads settings then loops over the PI selection menu"""
    settings = load_settings()

    while True:
        choice = choose_pi()

        if choice is None:
            # User chose to quit from the PI menu
            print("\n[SYSTEM] Goodbye!\n")
            break

        label, ControllerClass, help_text = CONTROLLERS[choice]

        print(f"\n[SYSTEM] Starting {label}...")
        controller = ControllerClass(settings)
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
