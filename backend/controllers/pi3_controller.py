"""PI3 Controller - Bedroom / Living Room sensors and actuators"""

import json
import threading
import time

import paho.mqtt.client as mqtt

from mqtt_publisher import MQTTBatchPublisher

from components import (
    DHTSensor,
    LCDDisplay,
    IRReceiver,
    RGBLight,
    MotionSensor,
)
from controllers.alarm_mqtt_sync import AlarmMQTTSync
from simulators import PI3Simulator


class PI3Controller:
    """
    Controller for PI3 (Bedroom / Living Room).

    Components   : DPIR3, DHT1, DHT2, IR, BRGB, LCD
    Alarm role   : slave  -  subscribes to alarm state from PI1 (master),
                             publishes trigger events when sensors fire.

    Rules fully implemented:
    - Rule 5 : Motion (DPIR3) + person_count == 0  ->  publish alarm trigger to PI1.
    - Rule 7 : LCD cycles DHT1 / DHT2 / DHT3 readings every LCD_CYCLE_INTERVAL s.
               DHT3 data arrives from PI2 via MQTT (iot/sensors topic).
    - Rule 9 : IR remote codes control the RGB light.
    """

    LCD_CYCLE_INTERVAL = 3   # Rule 7: seconds between DHT display updates

    IR_CODE_TOGGLE = 'TOGGLE'
    IR_CODE_RED    = 'RED'
    IR_CODE_GREEN  = 'GREEN'
    IR_CODE_BLUE   = 'BLUE'

    def __init__(self, settings, mqtt_cfg=None,
                 get_person_count=None, set_person_count=None):
        self.settings         = settings
        self.device_info      = settings.get("device", {})
        self.sensors_settings = settings.get("sensors", {})
        alarm_cfg             = settings.get("alarm", {})
        _mqtt_cfg             = mqtt_cfg or {}

        self._mqtt_cfg = _mqtt_cfg   # needed for sensor sync client

        self.components = {}
        self.running    = False
        self.simulator  = None

        self.get_person_count = get_person_count or (lambda: 0)
        self.set_person_count = set_person_count

        # Shared MQTT publisher for all sensor / actuator data
        self.publisher = MQTTBatchPublisher(_mqtt_cfg, self.device_info)

        # Rule 7 state
        self._lcd_thread = None
        self._dht3_cache = None   # (temp, humidity) received from PI2 via MQTT

        # DHT3 sensor sync: subscribe to iot/sensors to receive PI2's DHT3 data
        self._sensor_sync_client = None

        # Alarm sync: PI3 is a slave
        self.alarm_sync = AlarmMQTTSync(
            mqtt_cfg                  = _mqtt_cfg,
            device_id                 = self.device_info.get('id', 'PI3'),
            role                      = 'slave',
            on_state_received         = self._on_alarm_state_received,
            on_person_count_received  = self._on_person_count_received,
        )
        self._known_alarm_state = alarm_cfg.get('initial_state', 'DISARMED')

        self._init_components()

    # ========== INIT ==========

    def _init_components(self):
        """Initialise all PI3 components."""
        s = self.sensors_settings

        print("=" * 50)
        print("Initializing PI3 Components...")
        print("=" * 50)

        if "DHT1" in s:
            self.components["DHT1"] = DHTSensor('DHT1', s["DHT1"], publisher=self.publisher)
            self._log_init("DHT1")

        if "DHT2" in s:
            self.components["DHT2"] = DHTSensor('DHT2', s["DHT2"], publisher=self.publisher)
            self._log_init("DHT2")

        if "IR" in s:
            self.components["IR"] = IRReceiver(
                'IR', s["IR"],
                publisher=self.publisher,
                on_code=self._on_ir_code,      # Rule 9
            )
            self._log_init("IR")

        if "BRGB" in s:
            self.components["BRGB"] = RGBLight('BRGB', s["BRGB"], publisher=self.publisher)
            self._log_init("BRGB")

        if "LCD" in s:
            self.components["LCD"] = LCDDisplay('LCD', s["LCD"], publisher=self.publisher)
            self._log_init("LCD")

        if "DPIR3" in s:
            self.components["DPIR3"] = MotionSensor(
                'DPIR3', s["DPIR3"],
                publisher=self.publisher,
                on_motion=self._on_motion,     # Rule 5
            )
            self._log_init("DPIR3")

        print("=" * 50)

    def _log_init(self, code):
        s    = self.sensors_settings[code]
        mode = "SIM" if s.get('simulate', True) else "HW"
        print(f"  [{code}] {s.get('name', code)} ({mode})")

    # ========== ALARM SYNC CALLBACK ==========

    def _on_alarm_state_received(self, state):
        """Called by AlarmMQTTSync when PI1 broadcasts a new alarm state."""
        self._known_alarm_state = state
        print(f"[PI3] Alarm state updated -> {state}")

    def _on_person_count_received(self, count):
        """Called by AlarmMQTTSync when PI1 broadcasts absolute person count."""
        if self.set_person_count:
            self.set_person_count(count)
        print(f"[PI3] Person count updated -> {count}")

    # ========== SENSOR HOOKS ==========

    def _on_motion(self):
        """
        DPIR3 motion event.
        Rule 5: if person_count == 0 -> publish alarm trigger to PI1.
        """
        print("[DPIR3] Motion detected")
        # --- Rule 5 ---
        if self.get_person_count() == 0 and self._known_alarm_state != 'ALARMING':
            print("[DPIR3] Motion with no occupants -> triggering alarm")
            self.alarm_sync.publish_trigger(reason='motion_no_occupants')

    def _on_ir_code(self, code):
        """
        Rule 9: IR remote code controls the BRGB light.
          TOGGLE -> toggle on/off (restores last colour)
          RED    -> set red
          GREEN  -> set green
          BLUE   -> set blue
        """
        rgb = self.components.get("BRGB")
        if rgb is None:
            return

        if code == self.IR_CODE_TOGGLE:
            if rgb.is_on():
                rgb.turn_off()
            else:
                rgb.set_color(*rgb.get_last_color())
        elif code == self.IR_CODE_RED:
            rgb.set_red()
        elif code == self.IR_CODE_GREEN:
            rgb.set_green()
        elif code == self.IR_CODE_BLUE:
            rgb.set_blue()
        else:
            print(f"[IR] Unknown code: '{code}'")

    # ========== RULE 7: DHT3 SYNC FROM PI2 VIA MQTT ==========

    def _start_sensor_sync(self):
        """Subscribe to iot/sensors to receive DHT3 data published by PI2."""
        if not self._mqtt_cfg.get('enabled', True):
            return

        host = self._mqtt_cfg.get('host', 'localhost')
        port = self._mqtt_cfg.get('port', 1883)

        self._sensor_sync_client = mqtt.Client(
            client_id="sensor-sync-PI3",
            clean_session=True,
        )

        user = self._mqtt_cfg.get('username')
        pwd  = self._mqtt_cfg.get('password')
        if user:
            self._sensor_sync_client.username_pw_set(user, pwd)

        self._sensor_sync_client.on_connect = self._sensor_sync_on_connect
        self._sensor_sync_client.on_message = self._sensor_sync_on_message

        try:
            self._sensor_sync_client.connect(host, port, keepalive=60)
            self._sensor_sync_client.loop_start()
        except Exception as exc:
            print(f"[PI3] DHT3 sync connection failed: {exc}")

    def _stop_sensor_sync(self):
        if self._sensor_sync_client:
            self._sensor_sync_client.loop_stop()
            try:
                self._sensor_sync_client.disconnect()
            except Exception:
                pass
            self._sensor_sync_client = None

    def _sensor_sync_on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            topic = self._mqtt_cfg.get('topic', 'iot/sensors')
            client.subscribe(topic, qos=1)

    def _sensor_sync_on_message(self, client, userdata, msg):
        """Parse incoming batch messages and cache DHT3 readings from PI2."""
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return

        if not isinstance(payload, dict):
            return

        # Only process PI2 messages  ('device' is a plain string in batch payloads)
        if payload.get('device') != 'PI2':
            return

        for item in payload.get('items', []):
            if item.get('sensor') == 'DHT3':
                val = item.get('value', {})
                if isinstance(val, dict):
                    t = val.get('temperature')
                    h = val.get('humidity')
                    if t is not None and h is not None:
                        self._dht3_cache = (float(t), float(h))

    # ========== RULE 7: LCD DHT CYCLING ==========

    def _lcd_cycle_loop(self):
        """
        Rule 7: background thread.
        Cycles DHT1 and DHT2 (local sensors) and DHT3 (received from PI2 via
        MQTT) on the LCD every LCD_CYCLE_INTERVAL seconds.
        """
        idx = 0
        while self.running:
            sources = []
            for key in ('DHT1', 'DHT2'):
                if key in self.components:
                    temp, humidity = self.components[key].read()
                    sources.append((key, temp, humidity))
            if self._dht3_cache is not None:
                temp, humidity = self._dht3_cache
                sources.append(('DHT3', temp, humidity))

            if sources:
                label, temp, humidity = sources[idx % len(sources)]
                lcd = self.components.get("LCD")
                if lcd:
                    lcd.show(f"{label}: {temp:.1f}C {humidity:.0f}%")
                idx += 1

            time.sleep(self.LCD_CYCLE_INTERVAL)

    # ========== LIFECYCLE ==========

    def start(self):
        self.running = True
        self.publisher.start()
        self.alarm_sync.start()
        self._start_sensor_sync()

        if "DPIR3" in self.components:
            self.components["DPIR3"].start_monitoring()
        if "IR" in self.components:
            self.components["IR"].start_monitoring()

        # Rule 7: start LCD cycling thread (always if LCD present)
        if "LCD" in self.components:
            self._lcd_thread = threading.Thread(
                target=self._lcd_cycle_loop,
                daemon=True,
            )
            self._lcd_thread.start()

        self.simulator = PI3Simulator(self.components)
        self.simulator.start()

    def stop(self):
        self.running = False
        if self.simulator:
            self.simulator.stop()
        self._stop_sensor_sync()
        self.alarm_sync.stop()
        self.publisher.stop()
        for comp in self.components.values():
            if hasattr(comp, 'stop'):
                comp.stop()

    def cleanup(self):
        self.stop()
        for comp in self.components.values():
            comp.cleanup()

    # ========== STATUS ==========

    def get_status(self):
        status = {}
        if "DPIR3" in self.components:
            status["DPIR3"] = "DETECTED" if self.components["DPIR3"].read() else "CLEAR"
        if "DHT1" in self.components:
            t, h = self.components["DHT1"].read()
            status["DHT1"] = f"{t:.1f}C {h:.0f}%"
        if "DHT2" in self.components:
            t, h = self.components["DHT2"].read()
            status["DHT2"] = f"{t:.1f}C {h:.0f}%"
        if self._dht3_cache is not None:
            t, h = self._dht3_cache
            status["DHT3"] = f"{t:.1f}C {h:.0f}%"
        if "BRGB" in self.components:
            r, g, b = self.components["BRGB"].get_color()
            status["BRGB"] = f"R={r} G={g} B={b}"
        if "IR" in self.components:
            status["IR"] = "monitoring"
        status["ALARM"]   = self._known_alarm_state
        status["PERSONS"] = self.get_person_count()
        return status

    def show_status(self):
        print("\n" + "=" * 40)
        print("PI3 STATUS")
        print("=" * 40)
        s = self.get_status()
        if "DPIR3" in s: print(f"  [DPIR3] Motion:    {s['DPIR3']}")
        if "DHT1"  in s: print(f"  [DHT1]  Temp/Hum:  {s['DHT1']}")
        if "DHT2"  in s: print(f"  [DHT2]  Temp/Hum:  {s['DHT2']}")
        if "DHT3"  in s: print(f"  [DHT3]  Temp/Hum:  {s['DHT3']}")
        if "BRGB"  in s: print(f"  [BRGB]  RGB:       {s['BRGB']}")
        if "IR"    in s: print(f"  [IR]    Receiver:  {s['IR']}")
        print(f"  [ALARM] State:     {s['ALARM']}")
        print(f"  [HOME]  Persons:   {s['PERSONS']}")
        print("=" * 40)

    # ========== COMMANDS ==========

    def handle_command(self, cmd):
        """
        CLI commands:
          s          - status
          r/g/bu/x   - RGB light
          t          - DHT1 / DHT2 on-demand read + show cached DHT3 (from PI2)
          9          - simulate DPIR3 motion
          i          - inject IR code
        """
        if cmd == 's':
            self.show_status()

        # --- RGB light ---
        elif cmd == 'r':
            self.components["BRGB"].set_red()
        elif cmd == 'g':
            self.components["BRGB"].set_green()
        elif cmd == 'bu':
            self.components["BRGB"].set_blue()
        elif cmd == 'x':
            self.components["BRGB"].turn_off()

        # --- DHT on-demand ---
        elif cmd == 't':
            for key in ('DHT1', 'DHT2'):
                if key in self.components:
                    self.components[key].read_and_publish()
            if self._dht3_cache is not None:
                temp, humidity = self._dht3_cache
                print(f"[DHT3] Temp={temp:.1f}C  Humidity={humidity:.1f}%")
            else:
                print("[DHT3] No data received yet")

        # --- Simulation ---
        elif cmd == '9':
            self.components["DPIR3"].set_motion(True)
            print("[SIM] DPIR3 Motion ON")
            time.sleep(1)
            self.components["DPIR3"].set_motion(False)

        elif cmd == 'i':
            code = input("IR code (TOGGLE/RED/GREEN/BLUE): ").strip().upper()
            if code:
                self.components["IR"].inject_code(code)
                print(f"[SIM] IR code '{code}' injected")

        else:
            return None

        return True
