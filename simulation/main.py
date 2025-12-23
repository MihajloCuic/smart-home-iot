#!/usr/bin/env python3
"""
Smart Home IoT - PI1 Controller
"""

from settings import load_settings
from controllers import PI1Controller


def show_help():
    """Display help menu"""
    print("""
==================================================
COMMANDS
==================================================
  s - Status          h - Help            q - Quit

  ACTUATORS: 
  1 - Toggle light    4 - Beep
  2 - Light ON        5 - Start alarm
  3 - Light OFF       6 - Stop alarm

  SIMULATION:
  7 - Door OPEN       9 - Trigger motion
  8 - Door CLOSE      0 - Press key
==================================================""")


def main():
    """Main entry point"""
    print("\n" + "=" * 50)
    print("  SMART HOME IoT - PI1 Controller")
    print("=" * 50 + "\n")
    
    # Load settings
    settings = load_settings()
    
    # Create controller
    controller = PI1Controller(settings)
    
    # Start monitoring
    controller.start()
    print("\n[SYSTEM] Running...  (press 'h' for help)\n")
    show_help()
    
    # Main loop
    running = True
    while running: 
        try:
            cmd = input("\n> ").strip().lower()
            
            if not cmd:
                continue
            elif cmd == 'h':
                show_help()
            elif cmd == 'q':
                running = False
                print("\nExiting...")
            else:
                result = controller.handle_command(cmd)
                if result is None:
                    print("Unknown command. Press 'h' for help.")
                    
        except KeyboardInterrupt: 
            running = False
            print("\n\nExiting...")
        except Exception as e:
            print(f"[ERROR] {e}")
    
    # Cleanup
    controller.cleanup()
    print("[SYSTEM] Done.")


if __name__ == "__main__":
    main()