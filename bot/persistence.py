"""Persistence layer for bot state"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

STATE_FILE = Path(__file__).parent.parent / "data" / "bot_state.json"


def load_state() -> dict:
    """Load persisted state"""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "active_chats": [],
        "dm_enabled_users": [],
        "current_question_id": None,
        "last_quiz_time": None
    }


def save_state(
    active_chats: set[int],
    dm_enabled_users: set[int],
    current_question_id: Optional[int] = None
):
    """Save state to file"""
    state = {
        "active_chats": list(active_chats),
        "dm_enabled_users": list(dm_enabled_users),
        "current_question_id": current_question_id,
        "last_quiz_time": datetime.now().isoformat()
    }
    
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def get_next_quiz_time() -> tuple[int, int]:
    """Get hours and minutes until next quiz (06:00 or 18:00 KST)"""
    from datetime import timezone, timedelta
    
    KST = timezone(timedelta(hours=9))
    now = datetime.now(KST)
    
    # Quiz times: 06:00 and 18:00 KST
    quiz_times = [6, 18]
    
    current_hour = now.hour
    current_min = now.minute
    
    # Find next quiz time
    for qt in quiz_times:
        if current_hour < qt or (current_hour == qt and current_min == 0):
            hours_left = qt - current_hour - (1 if current_min > 0 else 0)
            mins_left = (60 - current_min) % 60
            if current_min == 0:
                hours_left = qt - current_hour
                mins_left = 0
            return hours_left, mins_left
    
    # Next is tomorrow 06:00
    hours_left = (24 - current_hour + 6 - 1)
    mins_left = (60 - current_min) % 60
    if current_min == 0:
        hours_left = 24 - current_hour + 6
        mins_left = 0
    return hours_left, mins_left


def format_time_until_explanation() -> str:
    """Format time until next explanation (10 min before quiz)"""
    hours, mins = get_next_quiz_time()
    
    # Explanation is 10 min before quiz
    total_mins = hours * 60 + mins - 10
    if total_mins < 0:
        total_mins += 24 * 60  # wrap around
    
    hours = total_mins // 60
    mins = total_mins % 60
    
    if hours > 0:
        return f"{hours}시간 {mins}분"
    else:
        return f"{mins}분"
