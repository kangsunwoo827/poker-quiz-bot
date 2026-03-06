"""Simple JSON persistence for bot state."""
import json
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "data" / "bot_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"active_chats": []}


def save_state(active_chats: set[int]):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state = {"active_chats": list(active_chats)}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
