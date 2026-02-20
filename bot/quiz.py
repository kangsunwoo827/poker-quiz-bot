import json
import random
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class Question:
    id: int
    type: str
    situation: str
    hand: str
    options: list[str]
    answer: int
    explanation: str
    terms: dict
    range_key: str = ""  # Key to lookup range table

class QuizManager:
    def __init__(self):
        self.questions: list[Question] = []
        self.used_questions: set[int] = set()
        self.current_question: Optional[Question] = None
        self.user_answers: dict[int, int] = {}  # user_id -> answer_index
        self.preflop_ranges: dict = {}
        self._load_questions()
        self._load_ranges()
    
    def _load_questions(self):
        data_path = Path(__file__).parent.parent / "data" / "questions.json"
        with open(data_path, encoding="utf-8") as f:
            data = json.load(f)
        
        self.questions = [
            Question(
                id=q["id"],
                type=q["type"],
                situation=q["situation"],
                hand=q["hand"],
                options=q["options"],
                answer=q["answer"],
                explanation=q["explanation"],
                terms=q.get("terms", {}),
                range_key=q.get("range_key", "")
            )
            for q in data
        ]
    
    def _load_ranges(self):
        """Load preflop range charts"""
        range_path = Path(__file__).parent.parent / "data" / "preflop_ranges.json"
        if range_path.exists():
            with open(range_path, encoding="utf-8") as f:
                data = json.load(f)
            self.preflop_ranges = data.get("6max_100bb", {})
    
    def get_range_table(self, question: Question) -> Optional[str]:
        """Get range table for a question based on situation analysis"""
        if question.type != "preflop":
            return None
        
        situation = question.situation.lower()
        
        # Auto-detect range key from situation
        range_key = question.range_key
        if not range_key:
            if "hero is bb" in situation:
                if "co raises" in situation or "co open" in situation:
                    range_key = "BB_defend_vs_CO"
                elif "btn raises" in situation:
                    range_key = "BB_defend_vs_BTN"
            elif "hero is co" in situation:
                if "3-bet" in situation or "3bet" in situation:
                    range_key = "CO_vs_BTN_3bet"
                elif "folds to hero" in situation:
                    range_key = "CO_open"
            elif "hero is btn" in situation and "folds to hero" in situation:
                range_key = "BTN_open"
            elif "hero is sb" in situation and "folds to hero" in situation:
                range_key = "SB_open"
            elif "hero is utg" in situation:
                range_key = "UTG_open"
        
        if range_key and range_key in self.preflop_ranges:
            range_data = self.preflop_ranges[range_key]
            table_lines = range_data.get("table", [])
            legend = range_data.get("legend", "R = Raise/Open")
            desc = range_data.get("description", "")
            
            table_str = "\n".join(table_lines)
            return f"📊 {desc}\n\n{table_str}\n\n{legend}"
        
        return None
    
    def get_random_question(self) -> Question:
        available = [q for q in self.questions if q.id not in self.used_questions]
        
        if not available:
            # Reset if all used
            self.used_questions.clear()
            available = self.questions
        
        question = random.choice(available)
        self.used_questions.add(question.id)
        self.current_question = question
        self.user_answers.clear()
        return question
    
    def record_answer(self, user_id: int, answer_index: int) -> bool:
        """Record user's answer. Returns True if correct."""
        if self.current_question is None:
            return False
        
        self.user_answers[user_id] = answer_index
        return answer_index == self.current_question.answer
    
    def format_question(self, question: Question) -> str:
        """Format question for Telegram message."""
        text = f"🃏 **Poker Quiz #{question.id}**\n\n"
        text += f"```\n{question.situation}\n```\n\n"
        text += f"Hero's hand: **{question.hand}**\n\n"
        text += "Your action?"
        return text
    
    def format_explanation(self, question: Question) -> str:
        """Format explanation for Telegram message."""
        correct_option = question.options[question.answer]
        
        text = f"📖 **Quiz #{question.id} 해설**\n\n"
        text += f"```\n{question.situation}\n```\n"
        text += f"Hero's hand: **{question.hand}**\n\n"
        text += f"**정답:** {correct_option}\n\n"
        text += question.explanation
        
        if question.terms:
            text += "\n\n**📚 용어 설명**\n"
            for term, definition in question.terms.items():
                text += f"• **{term}**: {definition}\n"
        
        # Stats
        total = len(self.user_answers)
        if total > 0:
            correct = sum(1 for a in self.user_answers.values() if a == question.answer)
            pct = int(correct / total * 100)
            text += f"\n📊 정답률: {pct}% ({correct}/{total})"
        
        return text
    
    def get_stats(self) -> dict:
        return {
            "total_questions": len(self.questions),
            "used_questions": len(self.used_questions),
            "current_participants": len(self.user_answers)
        }
