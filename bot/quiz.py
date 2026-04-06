import json
import random
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from config import (
    SCENARIOS_FILE, EV_TABLES_DIR, ALL_HANDS_169,
    MARGINAL_EV_THRESHOLD, OBVIOUS_FOLD_EV_GAP, RECENT_HISTORY_SIZE,
    PDF_RANGES_FILE, DATA_DIR,
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


# ─── Open Range Quiz ──────────────────────────────────────────────────────────

_RANKS_STR = "AKQJT98765432"
_RANK_VAL = {r: i for i, r in enumerate(_RANKS_STR)}

OPEN_RANGE_POSITIONS = ["UTG", "UTG+1", "MP", "LJ", "HJ", "CO", "BTN", "SB"]
RANGES_DIR = DATA_DIR / "ranges"

# Hand strength rank: lower = stronger (0=AA, 168=32o)
def _hand_strength(hand: str) -> int:
    rv = _RANK_VAL
    if len(hand) == 2:  # pair
        return rv[hand[0]]                          # 0(AA) - 12(22)
    hi, lo = rv[hand[0]], rv[hand[1]]
    suited = hand.endswith("s")
    # suited before offsuit; within type, hi card then lo card
    base = 13 + hi * 12 + (lo - 1)
    return base if suited else base + 91

_HAND_RANK_ORDER = sorted(ALL_HANDS_169, key=_hand_strength)
_HAND_RANK = {h: i for i, h in enumerate(_HAND_RANK_ORDER)}


@dataclass
class OpenRangeQuestion:
    format_key: str        # e.g. "6max_100bb_highRake"
    format_name: str       # e.g. "6-max 100bb High Rake"
    position: str          # "UTG" / "MP" / "CO" / "BTN" / "SB"
    hand: str              # e.g. "K9s"
    hand_display: str      # e.g. "K♠ 9♠"
    correct_action: str    # "Open", "Call", or "Fold"
    in_range_hands: frozenset  # raise ∪ call (for chart display)
    raise_hands: frozenset     # pure raise hands
    call_hands: frozenset      # call/limp hands (SB)
    is_boundary: bool      # whether near the range edge


class OpenRangeQuizManager:
    """Quiz manager for memorising open (RFI) ranges from rangeconverter.com.

    Supports multiple formats (stack depths) and positions.
    Boundary hands (near range edge) are asked most frequently.
    """
    FORMATS = {
        "6max_100bb_highRake": "6-max 100bb High Rake",
        "6max_100bb":          "6-max 100bb",
        "6max_40bb":           "6-max 40bb",
        "6max_200bb":          "6-max 200bb",
        "9max_100bb":          "9-max 100bb",
        "mtt_100bb":           "MTT 100bb",
        "mtt_60bb":            "MTT 60bb",
        "mtt_50bb":            "MTT 50bb",
        "mtt_40bb":            "MTT 40bb",
        "mtt_30bb":            "MTT 30bb",
        "mtt_20bb":            "MTT 20bb",
        "mtt_10bb":            "MTT 10bb",
    }
    BOUNDARY_WINDOW = 8   # hands within this rank-distance from boundary get 3x weight

    def __init__(self, ev_tables: dict = None):
        # fmt -> pos -> {"raise": frozenset, "call": frozenset}
        self.ranges: dict[str, dict[str, dict]] = {}
        # fmt -> pos -> hand -> weight
        self.weights: dict[str, dict[str, dict]] = {}
        self._load(ev_tables or {})

    def _load(self, ev_tables: dict):
        corrections_path = DATA_DIR / "corrections.json"
        corrections: dict = {}
        if corrections_path.exists():
            with open(corrections_path, encoding="utf-8") as f:
                raw = json.load(f)
            corrections = {k: v for k, v in raw.items() if not k.startswith("_")}

        for fmt in self.FORMATS:
            fmt_dir = RANGES_DIR / fmt / "rfi"
            if not fmt_dir.exists():
                continue
            self.ranges[fmt] = {}
            self.weights[fmt] = {}
            for pos in OPEN_RANGE_POSITIONS:
                path = fmt_dir / f"{pos}.json"
                if not path.exists():
                    continue
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                raise_hands = frozenset(data.get("raise", []))
                call_hands  = frozenset(data.get("call", []))

                # Apply manual corrections
                corr = corrections.get(fmt, {}).get(pos, {})
                raise_hands = (raise_hands - frozenset(corr.get("raise_remove", [])))
                raise_hands = raise_hands | frozenset(corr.get("raise_add", []))
                call_hands  = (call_hands - frozenset(corr.get("call_remove", [])))
                call_hands  = call_hands  | frozenset(corr.get("call_add", []))

                self.ranges[fmt][pos] = {"raise": raise_hands, "call": call_hands}
                self.weights[fmt][pos] = self._compute_weights(
                    raise_hands | call_hands, ev_tables, pos, fmt
                )

    def _compute_weights(
        self,
        in_range: frozenset,
        ev_tables: dict,
        pos: str,
        fmt: str,
    ) -> dict:
        """Compute per-hand quiz weights. Boundary hands get higher weight."""
        _POS_TO_SCENARIO = {
            "UTG": "rfi_utg", "MP": "rfi_mp", "CO": "rfi_co",
            "BTN": "rfi_btn", "SB": "rfi_sb",
        }
        # Try EV-based boundary (only for 6max_100bb_highRake which has solver data)
        if fmt == "6max_100bb_highRake":
            scenario_id = _POS_TO_SCENARIO.get(pos, "")
            ev_hands = ev_tables.get(scenario_id, {}).get("hands", {})
            if ev_hands:
                scores = {}
                for h in ALL_HANDS_169:
                    if h not in ev_hands: continue
                    ev = ev_hands[h].get("ev_vs_best", {})
                    fold_ev = ev.get("Fold", 0.0)
                    non_fold = [v for k, v in ev.items() if k.lower() != "fold"]
                    best_play = max(non_fold) if non_fold else fold_ev
                    scores[h] = best_play - fold_ev
                in_s  = [scores[h] for h in in_range if h in scores]
                out_s = [scores[h] for h in ALL_HANDS_169 if h not in in_range and h in scores]
                if in_s and out_s:
                    bp = (min(in_s) + max(out_s)) / 2
                    w = {}
                    for h in ALL_HANDS_169:
                        if h not in scores: continue
                        dist = abs(scores[h] - bp)
                        if dist <= 1.5:
                            w[h] = 1.0 / (dist + 0.15)
                    if w:
                        return w
        # Rank-based boundary fallback
        if not in_range:
            return {h: 1.0 for h in ALL_HANDS_169}
        in_ranks = sorted(_HAND_RANK[h] for h in in_range if h in _HAND_RANK)
        boundary_rank = in_ranks[-1] if in_ranks else 84  # weakest in-range hand rank
        w = {}
        for h in ALL_HANDS_169:
            rank = _HAND_RANK.get(h, 84)
            dist = abs(rank - boundary_rank)
            if dist <= self.BOUNDARY_WINDOW:
                w[h] = 3.0 / (dist + 1)
            elif h in in_range:
                w[h] = 0.3
            else:
                w[h] = 0.1
        return w

    def get_available_formats(self) -> list[str]:
        return [f for f in self.FORMATS if f in self.ranges and self.ranges[f]]

    def generate_question(
        self,
        format_key: str = None,
        position: str = None,
        recent: set = None,
    ) -> Optional[OpenRangeQuestion]:
        available = self.get_available_formats()
        if not available:
            return None

        fmt = format_key if format_key in available else random.choice(available)
        fmt_ranges = self.ranges[fmt]
        available_pos = [p for p in OPEN_RANGE_POSITIONS if p in fmt_ranges]
        if not available_pos:
            return None

        pos = position if position in available_pos else random.choice(available_pos)
        range_data = fmt_ranges[pos]
        weights    = self.weights[fmt][pos]
        skip       = recent or set()

        pool = [(h, w) for h, w in weights.items() if h not in skip]
        if not pool:
            pool = [(h, 1.0) for h in ALL_HANDS_169]

        names, wts = zip(*pool)
        idx  = random.choices(range(len(names)), weights=list(wts), k=1)[0]
        hand = names[idx]

        raise_h = range_data["raise"]
        call_h  = range_data["call"]

        if hand in raise_h:
            action = "Open"
        elif hand in call_h:
            action = "Call"
        else:
            action = "Fold"

        rank    = _HAND_RANK.get(hand, 84)
        in_r    = [_HAND_RANK[h] for h in (raise_h | call_h) if h in _HAND_RANK]
        bnd     = max(in_r) if in_r else 84
        is_bnd  = abs(rank - bnd) <= self.BOUNDARY_WINDOW

        return OpenRangeQuestion(
            format_key=fmt,
            format_name=self.FORMATS.get(fmt, fmt),
            position=pos,
            hand=hand,
            hand_display=hand_to_display(hand),
            correct_action=action,
            in_range_hands=(raise_h | call_h),
            raise_hands=raise_h,
            call_hands=call_h,
            is_boundary=is_bnd,
        )
