"""사용자 설정(config.json) 읽기/쓰기"""
import json
import os

from .paths import CONFIG_FILE


def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"hymn_folder": "", "template_file": "", "hymn_slots": []}


def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
