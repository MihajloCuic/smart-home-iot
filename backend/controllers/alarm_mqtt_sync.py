"""
MQTT-based alarm state and person count synchronization across PI devices.

Architecture
------------
PI1 is the alarm **master**:
  - Owns the AlarmStateMachine and the physical buzzer (DB).
  - Subscribes to  iot/alarm/trigger   – trigger requests from PI2/PI3.
  - Subscribes to  iot/alarm/door_pi2  – DS2 open/close events from PI2
                                          (needed for Rule 3 and Rule 4 grace).
  - Publishes to   iot/alarm/state     – broadcasts state on every transition
                                          (retained so new subscribers get it).

PI2 and PI3 are **slaves**:
  - Subscribe to   iot/alarm/state     – track current alarm state locally.
  - Publish to     iot/alarm/trigger   – request PI1 to trigger the alarm
                                          (Rule 5, Rule 6 from PI2/PI3 sensors).
  - PI2 also publishes iot/alarm/door_pi2 when DS2 changes state.

Person count synchronization:
  - PI1 (master) owns the person count. Publishes absolute count on
    iot/home/person_count (retained) whenever it changes.
  - PI2 publishes delta requests (+1/-1) on iot/home/person_delta.
    PI1 receives, applies the delta, and re-broadcasts the absolute count.
  - PI2 and PI3 subscribe to iot/home/person_count to stay in sync.

This design works identically:
  • In simulation  – all three controllers connect to the same localhost broker.
  • On real HW     – each Pi runs its own controller and connects to the shared broker.
"""

import json
import threading

import paho.mqtt.client as mqtt


class AlarmMQTTSync:

    TOPIC_TRIGGER  = "iot/alarm/trigger"    # PI2/PI3  →  PI1
    TOPIC_STATE    = "iot/alarm/state"      # PI1      →  all  (retained)
    TOPIC_DOOR_PI2 = "iot/alarm/door_pi2"   # PI2      →  PI1

    TOPIC_PERSON_COUNT = "iot/home/person_count"  # PI1 → all (retained)
    TOPIC_PERSON_DELTA = "iot/home/person_delta"  # PI2 → PI1

    TOPIC_WEB_COMMAND  = "iot/web/command"        # Web app → any PI

    def __init__(
        self,
        mqtt_cfg,
        device_id,
        role='slave',
        on_trigger_received=None,
        on_door_pi2_received=None,
        on_state_received=None,
        on_person_count_received=None,
        on_person_delta_received=None,
        on_web_command=None,
    ):
        """
        Parameters
        ----------
        mqtt_cfg             : dict  – MQTT broker settings (host, port, …)
        device_id            : str   – 'PI1', 'PI2', or 'PI3'
        role                 : str   – 'master' (PI1) or 'slave' (PI2/PI3)
        on_trigger_received  : callable(source: str, reason: str)
                               PI1 only – called when a trigger arrives from PI2/PI3.
        on_door_pi2_received : callable(is_open: bool)
                               PI1 only – called when PI2's DS2 changes state.
        on_state_received    : callable(state: str)
                               PI2/PI3 – called whenever PI1 broadcasts a new state.
        on_person_count_received : callable(count: int)
                               PI2/PI3 – called when PI1 broadcasts absolute person count.
        on_person_delta_received : callable(source: str, delta: int)
                               PI1 only – called when PI2 requests a person count change.
        on_web_command           : callable(command: str, params: dict)
                               All roles – called when the web app sends a command
                               targeting this device.
        """
        self._cfg       = mqtt_cfg
        self._device_id = device_id
        self._role      = role

        self.on_trigger_received      = on_trigger_received
        self.on_door_pi2_received     = on_door_pi2_received
        self.on_state_received        = on_state_received
        self.on_person_count_received = on_person_count_received
        self.on_person_delta_received = on_person_delta_received
        self.on_web_command           = on_web_command

        self._known_state = 'DISARMED'
        self._state_lock  = threading.Lock()
        self._client      = None
        self._connected   = False

    # ========== LIFECYCLE ==========

    def start(self):
        if not self._cfg.get('enabled', True):
            print(f"[{self._device_id}] MQTT disabled – alarm sync inactive")
            return

        host = self._cfg.get('host', 'localhost')
        port = self._cfg.get('port', 1883)

        self._client = mqtt.Client(
            client_id=f"alarm-sync-{self._device_id}",
            clean_session=True,
        )

        user = self._cfg.get('username')
        pwd  = self._cfg.get('password')
        if user:
            self._client.username_pw_set(user, pwd)

        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

        try:
            self._client.connect(host, port, keepalive=60)
            self._client.loop_start()          # background network thread
        except Exception as exc:
            print(f"[{self._device_id}] Connection failed: {exc}")

    def stop(self):
        if self._client:
            self._client.loop_stop()
            try:
                self._client.disconnect()
            except Exception:
                pass
        self._connected = False

    # ========== MQTT CALLBACKS ==========

    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self._connected = True
            if self._role == 'master':
                client.subscribe(self.TOPIC_TRIGGER)
                client.subscribe(self.TOPIC_DOOR_PI2)
                client.subscribe(self.TOPIC_PERSON_DELTA)
            else:
                # Subscribe with QoS 1; retained message delivers current state immediately
                client.subscribe(self.TOPIC_STATE, qos=1)
                client.subscribe(self.TOPIC_PERSON_COUNT, qos=1)
            # All roles subscribe to web commands
            client.subscribe(self.TOPIC_WEB_COMMAND, qos=1)
        else:
            print(f"[{self._device_id}] Connection refused (rc={rc})")

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False
        if rc != 0:
            print(f"[{self._device_id}] Unexpected disconnect (rc={rc})")

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
        except Exception:
            return

        topic = msg.topic

        if topic == self.TOPIC_TRIGGER and self._role == 'master':
            if self.on_trigger_received:
                self.on_trigger_received(
                    payload.get('source', 'unknown'),
                    payload.get('reason', ''),
                )

        elif topic == self.TOPIC_DOOR_PI2 and self._role == 'master':
            if self.on_door_pi2_received:
                self.on_door_pi2_received(payload.get('is_open', False))

        elif topic == self.TOPIC_STATE and self._role == 'slave':
            state = payload.get('state', 'DISARMED')
            with self._state_lock:
                self._known_state = state
            if self.on_state_received:
                self.on_state_received(state)

        elif topic == self.TOPIC_PERSON_DELTA and self._role == 'master':
            if self.on_person_delta_received:
                self.on_person_delta_received(
                    payload.get('source', 'unknown'),
                    payload.get('delta', 0),
                )

        elif topic == self.TOPIC_PERSON_COUNT and self._role == 'slave':
            if self.on_person_count_received:
                self.on_person_count_received(payload.get('count', 0))

        elif topic == self.TOPIC_WEB_COMMAND:
            target = payload.get('target', '')
            if target == self._device_id and self.on_web_command:
                self.on_web_command(
                    payload.get('command', ''),
                    payload.get('params', {}),
                )

    # ========== PUBLISH API ==========

    def publish_trigger(self, reason=''):
        """PI2/PI3: ask PI1 to trigger the alarm (Rules 5, 6)."""
        if not self._connected or self._client is None:
            print(f"[{self._device_id}] Not connected – trigger not sent ({reason})")
            return
        payload = json.dumps({'source': self._device_id, 'reason': reason})
        self._client.publish(self.TOPIC_TRIGGER, payload, qos=1)
        print(f"[{self._device_id}] Trigger → PI1 ({reason})")

    def publish_door_event(self, is_open):
        """PI2: notify PI1 about DS2 door open/close (Rules 3, 4)."""
        if not self._connected or self._client is None:
            return
        payload = json.dumps({'source': self._device_id, 'is_open': is_open})
        self._client.publish(self.TOPIC_DOOR_PI2, payload, qos=1)

    def publish_state(self, state):
        """PI1: broadcast the current alarm state to PI2 and PI3 (retained)."""
        if not self._connected or self._client is None:
            return
        payload = json.dumps({'source': self._device_id, 'state': state})
        self._client.publish(self.TOPIC_STATE, payload, qos=1, retain=True)

    def publish_person_count(self, count):
        """PI1: broadcast absolute person count to PI2 and PI3 (retained)."""
        if not self._connected or self._client is None:
            return
        payload = json.dumps({'source': self._device_id, 'count': count})
        self._client.publish(self.TOPIC_PERSON_COUNT, payload, qos=1, retain=True)

    def publish_person_delta(self, delta):
        """PI2: request PI1 to adjust person count by delta (+1 or -1)."""
        if not self._connected or self._client is None:
            print(f"[{self._device_id}] Not connected – person delta not sent")
            return
        payload = json.dumps({'source': self._device_id, 'delta': delta})
        self._client.publish(self.TOPIC_PERSON_DELTA, payload, qos=1)

    # ========== QUERY ==========

    def get_known_state(self):
        """PI2/PI3: returns the last alarm state received from PI1."""
        with self._state_lock:
            return self._known_state

    def is_connected(self):
        return self._connected
