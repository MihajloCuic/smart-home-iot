import json
import os


def load_settings(filePath='settings.json'):
    if not os.path.isabs(filePath):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        filePath = os.path.join(base_dir, filePath)
    # print(f"[SETTINGS] Loading from: {filePath}", flush=True)
    with open(filePath, 'r') as f:
        settings = json.load(f)
    # print(f"[SETTINGS] MQTT host={settings.get('mqtt', {}).get('host')} port={settings.get('mqtt', {}).get('port')}", flush=True)
    # print(f"[SETTINGS] MQTT enabled={settings.get('mqtt', {}).get('enabled')}", flush=True)
    return settings