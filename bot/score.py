import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional

class ScoreManager:
    def __init__(self):
        db_path = Path(__file__).parent.parent / "data" / "scores.db"
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_db()
    
    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                correct INTEGER DEFAULT 0,
                total INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                last_answer_time TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS answer_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question_id INTEGER,
                answer INTEGER,
                correct INTEGER,
                timestamp TEXT
            )
        """)
        self.conn.commit()
    
    def record_answer(self, user_id: int, username: str, question_id: int, 
                      answer: int, is_correct: bool):
        cursor = self.conn.cursor()
        now = datetime.now().isoformat()
        
        # Update scores
        cursor.execute("SELECT correct, total, streak, best_streak FROM scores WHERE user_id = ?", 
                      (user_id,))
        row = cursor.fetchone()
        
        if row:
            correct, total, streak, best_streak = row
            # +1 for correct, -1 for wrong (minimum 0)
            if is_correct:
                correct += 1
                streak += 1
            else:
                correct = max(0, correct - 1)  # 감점 (최소 0)
                streak = 0
            total += 1
            best_streak = max(best_streak, streak)
            
            cursor.execute("""
                UPDATE scores SET username=?, correct=?, total=?, streak=?, 
                best_streak=?, last_answer_time=? WHERE user_id=?
            """, (username, correct, total, streak, best_streak, now, user_id))
        else:
            cursor.execute("""
                INSERT INTO scores (user_id, username, correct, total, streak, best_streak, last_answer_time)
                VALUES (?, ?, ?, 1, ?, ?, ?)
            """, (user_id, username, 1 if is_correct else 0, 1 if is_correct else 0, 
                  1 if is_correct else 0, now))
        
        # Record history
        cursor.execute("""
            INSERT INTO answer_history (user_id, question_id, answer, correct, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, question_id, answer, 1 if is_correct else 0, now))
        
        self.conn.commit()
    
    def get_leaderboard(self, limit: int = 10) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT username, correct, total, streak, best_streak
            FROM scores
            ORDER BY correct DESC, total ASC
            LIMIT ?
        """, (limit,))
        
        return [
            {
                "username": row[0],
                "correct": row[1],
                "total": row[2],
                "streak": row[3],
                "best_streak": row[4],
                "accuracy": row[1] / row[2] * 100 if row[2] > 0 else 0
            }
            for row in cursor.fetchall()
        ]
    
    def get_user_stats(self, user_id: int) -> Optional[dict]:
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT username, correct, total, streak, best_streak
            FROM scores WHERE user_id = ?
        """, (user_id,))
        row = cursor.fetchone()
        
        if row:
            return {
                "username": row[0],
                "correct": row[1],
                "total": row[2],
                "streak": row[3],
                "best_streak": row[4],
                "accuracy": row[1] / row[2] * 100 if row[2] > 0 else 0
            }
        return None
