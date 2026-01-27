import json
import os


def load_settings(filePath='settings.json'):
    if not os.path.isabs(filePath):
        base_dir = os.path.dirname(__file__)
        filePath = os.path.join(base_dir, filePath)
    with open(filePath, 'r') as f:
        return json.load(f)