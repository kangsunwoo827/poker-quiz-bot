import json
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from config import (
    SCENARIOS_FILE, EV_TABLES_DIR, ALL_HANDS_169,
    MARGINAL_EV_THRESHOLD, OBVIOUS_FOLD_EV_GAP, RECENT_HISTORY_SIZE
)


@dataclass
class Scenario:
    id: str
    type: str
    name: str
    description: str
    hero_position: str
    villain_position: Optional[str]
    stack_bb: int
    actions: list[str]


@dataclass
class QuizQuestion:
    scenario: Scenario
    hand: str           # e.g. "ATs", "72o", "QQ"
    hand_display: str   # e.g. "A\u2660 T\u2660"
    ev_vs_best: dict    # action -> ev relative to best (best=0, rest negative)
    ev_normalized: dict # action -> normalized ev (average=0)
    strategy: dict      # action -> GTO frequency
    best_action: str
    correct_actions: list[str]  # actions with strategy > 0


SUIT_SYMBOLS = ["\u2660", "\u2665", "\u2666", "\u2663"]  # spade, heart, diamond, club


def hand_to_display(hand: str) -> str:
    """Convert hand notation to display with suit symbols."""
    if len(hand) == 2:
        # Pocket pair like "AA"
        return f"{hand[0]}\u2660 {hand[1]}\u2665"
    elif hand.endswith("s"):
        return f"{hand[0]}\u2660 {hand[1]}\u2660"
    else:
        return f"{hand[0]}\u2660 {hand[1]}\u2665"


class QuizManager:
    def __init__(self):
        self.scenarios: dict[str, Scenario] = {}
        self.ev_tables: dict[str, dict] = {}
        self._load_scenarios()
        self._load_ev_tables()

    def _load_scenarios(self):
        with open(SCENARIOS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for s in data:
            self.scenarios[s["id"]] = Scenario(
                id=s["id"],
                type=s["type"],
                name=s["name"],
                description=s["description"],
                hero_position=s["hero_position"],
                villain_position=s.get("villain_position"),
                stack_bb=s["stack_bb"],
                actions=s["actions"],
            )

    def _load_ev_tables(self):
        if not EV_TABLES_DIR.exists():
            return
        for path in EV_TABLES_DIR.glob("*.json"):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            scenario_id = data.get("scenario_id", path.stem)
            self.ev_tables[scenario_id] = data

    def get_available_scenarios(self) -> list[str]:
        """Return scenario IDs that have EV tables loaded."""
        return [sid for sid in self.scenarios if sid in self.ev_tables]

    def generate_question(
        self,
        recent_history: list[tuple] = None,
        scenario_id: str = None,
    ) -> Optional[QuizQuestion]:
        available = self.get_available_scenarios()
        if not available:
            return None

        if scenario_id and scenario_id in available:
            chosen_scenario_id = scenario_id
        else:
            chosen_scenario_id = random.choice(available)

        scenario = self.scenarios[chosen_scenario_id]
        ev_table = self.ev_tables[chosen_scenario_id]
        hands = ev_table.get("hands", {})

        if not hands:
            return None

        # Build weighted hand list
        recent_set = set()
        if recent_history:
            recent_set = {
                (sid, h) for sid, h in recent_history[:RECENT_HISTORY_SIZE]
            }

        weighted_hands = []
        for hand_name, hand_data in hands.items():
            # Skip recently seen
            if (chosen_scenario_id, hand_name) in recent_set:
                continue

            ev_best = hand_data.get("ev_vs_best", {})
            if not ev_best:
                continue

            # Calculate EV gap (difference between best and second-best)
            evs = sorted(ev_best.values(), reverse=True)
            if len(evs) < 2:
                continue
            ev_gap = abs(evs[0] - evs[1])

            # Weight: marginal decisions get highest weight
            if ev_gap < MARGINAL_EV_THRESHOLD:
                weight = 3.0
            elif ev_gap > OBVIOUS_FOLD_EV_GAP:
                weight = 0.5
            else:
                weight = 1.5

            # Boost non-fold optimal hands
            best_action = max(ev_best, key=ev_best.get)
            if best_action.lower() != "fold" and best_action.lower() != "check":
                weight *= 1.3

            weighted_hands.append((hand_name, hand_data, weight))

        if not weighted_hands:
            # Fallback: pick any hand
            hand_name = random.choice(list(hands.keys()))
            hand_data = hands[hand_name]
        else:
            names, datas, weights = zip(*weighted_hands)
            idx = random.choices(range(len(names)), weights=weights, k=1)[0]
            hand_name = names[idx]
            hand_data = datas[idx]

        ev_vs_best = hand_data["ev_vs_best"]
        ev_normalized = hand_data["ev_normalized"]
        strategy = hand_data.get("strategy", {})

        best_action = max(ev_vs_best, key=ev_vs_best.get)
        correct_actions = [a for a, freq in strategy.items() if freq > 0] if strategy else [best_action]

        return QuizQuestion(
            scenario=scenario,
            hand=hand_name,
            hand_display=hand_to_display(hand_name),
            ev_vs_best=ev_vs_best,
            ev_normalized=ev_normalized,
            strategy=strategy,
            best_action=best_action,
            correct_actions=correct_actions,
        )

    def get_hand_data(self, scenario_id: str, hand: str) -> Optional[dict]:
        """Get full hand data for a scenario."""
        if scenario_id not in self.ev_tables:
            return None
        return self.ev_tables[scenario_id].get("hands", {}).get(hand)

    def get_scenario_hands(self, scenario_id: str) -> dict:
        """Get all hands for a scenario (for range chart)."""
        if scenario_id not in self.ev_tables:
            return {}
        return self.ev_tables[scenario_id].get("hands", {})
