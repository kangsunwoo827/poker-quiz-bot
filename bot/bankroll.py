import sqlite3
from datetime import datetime
from typing import Optional
from config import DB_PATH


class BankrollManager:
    def __init__(self, db_path=None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                bankroll REAL DEFAULT 100.0,
                total_questions INTEGER DEFAULT 0,
                correct_count INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                best_bankroll REAL DEFAULT 100.0,
                created_at TEXT,
                last_active TEXT
            );

            CREATE TABLE IF NOT EXISTS answer_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                scenario_id TEXT,
                hand TEXT,
                chosen_action TEXT,
                chosen_ev REAL,
                best_action TEXT,
                ev_vs_best REAL,
                bankroll_after REAL,
                was_correct INTEGER,
                timestamp TEXT
            );
        """)
        self.conn.commit()

    def get_or_create_user(self, user_id: int, username: str) -> dict:
        now = datetime.now().isoformat()
        row = self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()

        if row:
            self.conn.execute(
                "UPDATE users SET username = ?, last_active = ? WHERE user_id = ?",
                (username, now, user_id)
            )
            self.conn.commit()
            return dict(row)

        self.conn.execute(
            "INSERT INTO users (user_id, username, bankroll, total_questions, "
            "correct_count, streak, best_streak, best_bankroll, created_at, last_active) "
            "VALUES (?, ?, 100.0, 0, 0, 0, 0, 100.0, ?, ?)",
            (user_id, username, now, now)
        )
        self.conn.commit()
        return dict(self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone())

    def record_answer(
        self, user_id: int, username: str,
        scenario_id: str, hand: str,
        chosen_action: str, chosen_ev_normalized: float,
        best_action: str, ev_vs_best: float,
        was_correct: bool
    ) -> dict:
        now = datetime.now().isoformat()
        user = self.get_or_create_user(user_id, username)

        new_bankroll = user["bankroll"] + chosen_ev_normalized
        new_total = user["total_questions"] + 1
        new_correct = user["correct_count"] + (1 if was_correct else 0)
        new_streak = (user["streak"] + 1) if was_correct else 0
        new_best_streak = max(user["best_streak"], new_streak)
        new_best_bankroll = max(user["best_bankroll"], new_bankroll)

        self.conn.execute(
            "UPDATE users SET bankroll = ?, total_questions = ?, correct_count = ?, "
            "streak = ?, best_streak = ?, best_bankroll = ?, last_active = ? "
            "WHERE user_id = ?",
            (new_bankroll, new_total, new_correct, new_streak,
             new_best_streak, new_best_bankroll, now, user_id)
        )

        self.conn.execute(
            "INSERT INTO answer_history "
            "(user_id, scenario_id, hand, chosen_action, chosen_ev, "
            "best_action, ev_vs_best, bankroll_after, was_correct, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, scenario_id, hand, chosen_action, chosen_ev_normalized,
             best_action, ev_vs_best, new_bankroll, 1 if was_correct else 0, now)
        )
        self.conn.commit()

        return {
            "bankroll": new_bankroll,
            "total_questions": new_total,
            "correct_count": new_correct,
            "streak": new_streak,
            "best_streak": new_best_streak,
            "was_correct": was_correct,
        }

    def get_user_stats(self, user_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        d["accuracy"] = (d["correct_count"] / d["total_questions"] * 100
                         if d["total_questions"] > 0 else 0)
        return d

    def get_leaderboard(self, limit: int = 10) -> list[dict]:
        rows = self.conn.execute(
            "SELECT user_id, username, bankroll, total_questions, correct_count, "
            "streak, best_streak, best_bankroll FROM users "
            "ORDER BY bankroll DESC LIMIT ?",
            (limit,)
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["accuracy"] = (d["correct_count"] / d["total_questions"] * 100
                             if d["total_questions"] > 0 else 0)
            result.append(d)
        return result

    def get_recent_history(self, user_id: int, limit: int = 50) -> list[tuple]:
        rows = self.conn.execute(
            "SELECT scenario_id, hand FROM answer_history "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
        return [(r["scenario_id"], r["hand"]) for r in rows]
