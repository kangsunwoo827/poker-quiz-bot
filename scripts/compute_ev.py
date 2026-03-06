#!/usr/bin/env python3
"""
Compute preflop EV for all scenarios using Monte Carlo equity calculation.

Model:
  For each hero hand vs villain's range:
  - Fold EV = 0 (baseline)
  - Call EV = equity × pot × EQR - call_cost
  - Raise/3bet EV = fold_eq × pot_won + (1-fold_eq) × called_EV
  - All-in EV = fold_eq × pot_won + (1-fold_eq) × (equity × total_pot - allin_cost)

Where:
  - equity = Monte Carlo simulation vs villain's range
  - EQR = equity realization factor (position-dependent)
  - fold_eq = estimated fold equity based on action type and villain tendency
"""
import json
import random
import time
import sys
from pathlib import Path
from typing import Optional

from treys import Card, Evaluator, Deck

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SCENARIOS_FILE = DATA_DIR / "scenarios.json"
EV_TABLES_DIR = DATA_DIR / "ev_tables"

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
SUITS = ["s", "h", "d", "c"]

evaluator = Evaluator()
FULL_DECK = Deck.GetFullDeck()

# Number of Monte Carlo simulations per hand
SIMS_PER_HAND = 5000


# ============================================================
# Standard GTO opening ranges per position (6-max, 100bb)
# Expressed as set of hand classes (e.g., "AKs", "TT", "A5o")
# Based on widely published solver outputs
# ============================================================

def _parse_range_str(range_str: str) -> set:
    """Parse a range string like 'AA-TT,AKs-ATs,AKo-AJo' into hand classes."""
    hands = set()
    for part in range_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part and len(part) > 3:
            # Range like "AA-TT" or "AKs-ATs"
            start, end = part.split("-")
            _expand_range(start, end, hands)
        elif part.endswith("+"):
            # Like "TT+" or "A5s+"
            _expand_plus(part[:-1], hands)
        else:
            hands.add(part)
    return hands


def _expand_range(start: str, end: str, hands: set):
    """Expand range like AA-TT or AKs-ATs."""
    ri = {r: i for i, r in enumerate(RANKS)}

    if len(start) == 2 and start[0] == start[1]:
        # Pair range: AA-TT
        i1, i2 = ri[start[0]], ri[end[0]]
        for i in range(i1, i2 + 1):
            hands.add(f"{RANKS[i]}{RANKS[i]}")
    elif start[0] == end[0]:
        # Same first card: AKs-ATs
        suffix = start[-1] if start[-1] in ("s", "o") else ""
        i1, i2 = ri[start[1]], ri[end[1]]
        for i in range(i1, i2 + 1):
            hands.add(f"{start[0]}{RANKS[i]}{suffix}")
    else:
        # Different first cards - just add both
        hands.add(start)
        hands.add(end)


def _expand_plus(base: str, hands: set):
    """Expand TT+ or A5s+."""
    ri = {r: i for i, r in enumerate(RANKS)}

    if len(base) == 2 and base[0] == base[1]:
        # Pair+: TT+ = TT,JJ,QQ,KK,AA
        idx = ri[base[0]]
        for i in range(0, idx + 1):
            hands.add(f"{RANKS[i]}{RANKS[i]}")
    elif len(base) == 3:
        # Suited/offsuit+: A5s+ = A5s,A6s,...,AKs
        suffix = base[2]
        high = base[0]
        low_idx = ri[base[1]]
        high_idx = ri[high]
        for i in range(high_idx + 1, low_idx + 1):
            hands.add(f"{high}{RANKS[i]}{suffix}")


# Standard 6-max GTO opening ranges (approximate, based on solver consensus)
OPENING_RANGES = {
    "UTG": _parse_range_str(
        "AA-22,"
        "AKs-A2s,KQs-K9s,QJs-QTs,JTs-J9s,T9s,98s,87s,76s,65s,"
        "AKo-ATo,KQo-KJo,QJo"
    ),
    "MP": _parse_range_str(
        "AA-22,"
        "AKs-A2s,KQs-K8s,QJs-Q9s,JTs-J9s,T9s-T8s,98s,87s,76s,65s,54s,"
        "AKo-A9o,KQo-KTo,QJo-QTo,JTo"
    ),
    "CO": _parse_range_str(
        "AA-22,"
        "AKs-A2s,KQs-K5s,QJs-Q8s,JTs-J8s,T9s-T8s,98s-97s,87s-86s,76s-75s,65s-64s,54s,43s,"
        "AKo-A7o,KQo-K9o,QJo-Q9o,JTo-J9o,T9o,98o"
    ),
    "BTN": _parse_range_str(
        "AA-22,"
        "AKs-A2s,KQs-K2s,QJs-Q5s,JTs-J7s,T9s-T7s,98s-96s,87s-85s,76s-74s,65s-63s,54s-53s,43s,32s,"
        "AKo-A2o,KQo-K7o,QJo-Q8o,JTo-J8o,T9o-T8o,98o-97o,87o,76o"
    ),
    "SB": _parse_range_str(
        "AA-22,"
        "AKs-A2s,KQs-K4s,QJs-Q7s,JTs-J7s,T9s-T7s,98s-96s,87s-85s,76s-75s,65s-64s,54s,43s,"
        "AKo-A5o,KQo-K9o,QJo-Q9o,JTo-J9o,T9o"
    ),
    "BB": _parse_range_str(
        "AA-22,"
        "AKs-A2s,KQs-K2s,QJs-Q2s,JTs-J5s,T9s-T6s,98s-95s,87s-84s,76s-74s,65s-63s,54s-53s,43s,32s,"
        "AKo-A2o,KQo-K5o,QJo-Q7o,JTo-J8o,T9o-T8o,98o-97o,87o,76o"
    ),
}

# 3bet ranges (vs open): tighter, polarized
THREEBET_RANGES = {
    "BB_vs_UTG": _parse_range_str("AA-QQ,AKs,AKo,A5s-A4s"),
    "BB_vs_MP": _parse_range_str("AA-QQ,AKs,AJs,AKo,A5s-A4s,KQs"),
    "BB_vs_CO": _parse_range_str("AA-TT,AKs-AJs,AKo-AQo,A5s-A3s,KQs,KJs"),
    "BB_vs_BTN": _parse_range_str("AA-99,AKs-A9s,AKo-ATo,A5s-A2s,KQs-KTs,QJs-QTs,JTs,KQo"),
    "SB_vs_CO": _parse_range_str("AA-TT,AKs-ATs,AKo-AJo,A5s-A3s,KQs-KJs"),
    "SB_vs_BTN": _parse_range_str("AA-88,AKs-A8s,AKo-ATo,A5s-A2s,KQs-KTs,QJs-QTs,JTs,KQo-KJo"),
    "BTN_vs_CO": _parse_range_str("AA-TT,AKs-AJs,AKo-AQo,A5s-A4s,KQs"),
    "CO_vs_UTG": _parse_range_str("AA-QQ,AKs,AKo"),
}

# 4bet ranges (vs 3bet)
FOURBET_RANGES = {
    "UTG_vs_3bet": _parse_range_str("AA-QQ,AKs,AKo"),
    "CO_vs_BTN_3bet": _parse_range_str("AA-QQ,AKs,AKo,A5s"),
    "BTN_vs_BB_3bet": _parse_range_str("AA-JJ,AKs,AKo,AQs,A5s"),
    "BTN_vs_SB_3bet": _parse_range_str("AA-JJ,AKs,AKo,AQs,A5s"),
}

# Fold-to-3bet frequencies by position
FOLD_TO_3BET = {
    "UTG": 0.60,
    "MP": 0.55,
    "CO": 0.50,
    "BTN": 0.45,
    "SB": 0.55,
}

# Fold-to-4bet frequencies
FOLD_TO_4BET = {
    "BB": 0.55,
    "SB": 0.55,
    "BTN": 0.50,
    "CO": 0.55,
}

# Equity realization factors
# IP (in position) gets more value, OOP (out of position) gets less
EQR = {
    "IP_caller": 1.05,    # caller in position
    "OOP_caller": 0.75,   # caller out of position (BB calling)
    "IP_3bettor": 1.10,   # 3bettor in position
    "OOP_3bettor": 0.90,  # 3bettor out of position
    "IP_raiser": 1.05,    # original raiser in position postflop
    "OOP_raiser": 0.85,   # original raiser OOP postflop
}


# ============================================================
# Equity calculation
# ============================================================

def hand_class_to_combos(hand_class: str) -> list:
    """Convert hand class like 'AKs' to list of specific card tuples."""
    combos = []
    if len(hand_class) == 2:
        # Pair: AA
        rank = hand_class[0]
        cards = [Card.new(f"{rank}{s}") for s in SUITS]
        for i in range(4):
            for j in range(i + 1, 4):
                combos.append((cards[i], cards[j]))
    elif hand_class.endswith("s"):
        r1, r2 = hand_class[0], hand_class[1]
        for s in SUITS:
            combos.append((Card.new(f"{r1}{s}"), Card.new(f"{r2}{s}")))
    else:  # offsuit
        r1, r2 = hand_class[0], hand_class[1]
        for s1 in SUITS:
            for s2 in SUITS:
                if s1 != s2:
                    combos.append((Card.new(f"{r1}{s1}"), Card.new(f"{r2}{s2}")))
    return combos


def range_to_weighted_combos(range_set: set) -> list:
    """Convert a range set to list of (card1, card2, weight) tuples."""
    combos = []
    for hc in range_set:
        for c1, c2 in hand_class_to_combos(hc):
            combos.append((c1, c2, 1.0))
    return combos


def compute_equity(hero_cards: list, villain_range: list, n_sims: int = SIMS_PER_HAND) -> float:
    """Compute equity of hero hand vs villain range using Monte Carlo.

    Args:
        hero_cards: [card1, card2]
        villain_range: list of (card1, card2, weight) tuples
        n_sims: number of simulations

    Returns:
        equity as float 0-1
    """
    hero_set = set(hero_cards)

    # Filter villain combos that don't conflict with hero
    valid_villains = [(c1, c2, w) for c1, c2, w in villain_range
                      if c1 not in hero_set and c2 not in hero_set]
    if not valid_villains:
        return 0.5

    total_weight = sum(w for _, _, w in valid_villains)
    cum_weights = []
    cum = 0
    for _, _, w in valid_villains:
        cum += w
        cum_weights.append(cum)

    remaining = [c for c in FULL_DECK if c not in hero_set]
    wins = 0.0
    total = 0.0

    for _ in range(n_sims):
        # Sample villain hand from range
        r = random.random() * total_weight
        vi = 0
        for i, cw in enumerate(cum_weights):
            if r <= cw:
                vi = i
                break

        vc1, vc2, vw = valid_villains[vi]
        villain_set = {vc1, vc2}

        # Sample board
        board_pool = [c for c in remaining if c not in villain_set]
        random.shuffle(board_pool)
        board = board_pool[:5]

        h_score = evaluator.evaluate(board, list(hero_cards))
        v_score = evaluator.evaluate(board, [vc1, vc2])

        if h_score < v_score:
            wins += 1.0
        elif h_score == v_score:
            wins += 0.5
        total += 1.0

    return wins / total if total > 0 else 0.5


# ============================================================
# EV calculation per scenario
# ============================================================

def get_all_169_hands():
    hands = []
    for i, r1 in enumerate(RANKS):
        for j, r2 in enumerate(RANKS):
            if i < j:
                hands.append(f"{r1}{r2}s")
            elif i > j:
                hands.append(f"{r2}{r1}o")
            else:
                hands.append(f"{r1}{r2}")
    return hands


def is_hero_ip(hero_pos: str, villain_pos: str) -> bool:
    """Is hero in position vs villain postflop?"""
    position_order = ["SB", "BB", "UTG", "MP", "CO", "BTN"]
    # Higher index = later position = in position postflop (except SB/BB)
    # BTN is always IP. BB is OOP to everyone except SB.
    if hero_pos == "BTN":
        return True
    if hero_pos == "BB" and villain_pos == "SB":
        return True
    if hero_pos == "SB":
        return False
    if hero_pos == "BB":
        return False
    hi = position_order.index(hero_pos)
    vi = position_order.index(villain_pos)
    return hi > vi


def compute_rfi_ev(hand_class: str, hero_pos: str, actions: list) -> dict:
    """Compute EV for RFI (raise first in) scenario.

    Actions: [Fold, Limp, Raise small, Raise big]
    """
    # Villain range = everyone behind hero who might call/3bet
    # Simplified: assume some percentage of 3bet from blinds
    # and some fold equity

    # Who acts after hero? Depends on position
    behind_positions = {
        "UTG": ["MP", "CO", "BTN", "SB", "BB"],
        "MP": ["CO", "BTN", "SB", "BB"],
        "CO": ["BTN", "SB", "BB"],
        "BTN": ["SB", "BB"],
        "SB": ["BB"],
    }

    hero_combos = hand_class_to_combos(hand_class)
    if not hero_combos:
        return {a: 0.0 for a in actions}

    hero_cards = list(hero_combos[0])  # Representative combo

    # Number of players behind
    n_behind = len(behind_positions.get(hero_pos, []))

    # Probability no one wakes up with a hand (everyone folds)
    # Approximate: each player folds ~85% of time vs open (tighter for EP)
    fold_prob_each = 0.88 if hero_pos in ("UTG", "MP") else 0.85
    all_fold_prob = fold_prob_each ** n_behind

    # If called, we face a caller. Build an approximate calling range
    # (typically BB defends widest)
    caller_range_set = OPENING_RANGES.get("BB", set())  # BB has widest defense
    caller_range = range_to_weighted_combos(caller_range_set)

    ip = hero_pos != "SB"  # Raiser is IP vs BB (except SB)
    eqr_key = "IP_raiser" if ip else "OOP_raiser"
    eqr_val = EQR[eqr_key]

    equity = compute_equity(hero_cards, caller_range) if caller_range else 0.5

    evs = {}
    for action in actions:
        a_lower = action.lower()
        if a_lower == "fold":
            evs[action] = 0.0
        elif a_lower == "limp" or a_lower == "limp behind":
            # Limp: see flop cheaply but OOP, no fold equity
            # EV = equity × pot(2bb) × EQR_low - 1bb (limp cost)
            # Can get raised behind (iso-raise)
            iso_raise_prob = 0.3 * n_behind  # rough estimate
            iso_raise_prob = min(iso_raise_prob, 0.7)
            # If iso-raised, we usually fold marginal hands
            limp_ev = (1 - iso_raise_prob) * (equity * 2.0 * 0.70 - 1.0) + \
                      iso_raise_prob * (-1.0)  # Lose our limp
            evs[action] = limp_ev
        elif a_lower.startswith("raise"):
            # Extract raise size
            size = float(a_lower.split()[-1].replace("bb", ""))
            pot_after_call = size + 1.0 + 0.5  # raise + BB + SB (simplified)
            # If everyone folds: win blinds (1.5bb)
            # If called: play postflop with equity
            win_dead = 1.5  # blinds
            called_ev = equity * pot_after_call * 2.0 * eqr_val - size
            evs[action] = all_fold_prob * win_dead + (1 - all_fold_prob) * called_ev
        else:
            evs[action] = 0.0

    return evs


def compute_vs_open_ev(hand_class: str, hero_pos: str, villain_pos: str,
                       actions: list, scenario: dict) -> dict:
    """Compute EV for facing an open raise.

    Actions: [Fold, Call, 3bet small, 3bet big]
    """
    hero_combos = hand_class_to_combos(hand_class)
    if not hero_combos:
        return {a: 0.0 for a in actions}

    hero_cards = list(hero_combos[0])

    # Villain's opening range
    villain_range_set = OPENING_RANGES.get(villain_pos, OPENING_RANGES["CO"])
    villain_range = range_to_weighted_combos(villain_range_set)

    equity = compute_equity(hero_cards, villain_range)

    ip = is_hero_ip(hero_pos, villain_pos)
    open_size = 2.5  # Standard open size
    pot_preflop = open_size + 1.0 + 0.5  # open + BB + SB

    # Fold-to-3bet for villain
    ft3b = FOLD_TO_3BET.get(villain_pos, 0.50)

    evs = {}
    for action in actions:
        a_lower = action.lower()
        if a_lower == "fold":
            evs[action] = 0.0
        elif a_lower == "call":
            # Call: pay open_size, see flop
            eqr_key = "IP_caller" if ip else "OOP_caller"
            eqr_val = EQR[eqr_key]
            pot_after_call = open_size * 2 + 1.0 + 0.5  # both put in open_size, + blinds
            # Hero in BB already posted 1bb, so additional cost = open_size - 1
            call_cost = open_size - (1.0 if hero_pos == "BB" else
                                     0.5 if hero_pos == "SB" else open_size)
            called_pot = pot_preflop + call_cost
            evs[action] = equity * called_pot * eqr_val - call_cost
        elif "3bet" in a_lower or "squeeze" in a_lower:
            size_str = a_lower.replace("3bet", "").replace("squeeze", "").strip()
            size = float(size_str.replace("bb", ""))
            bet_cost = size - (1.0 if hero_pos == "BB" else
                               0.5 if hero_pos == "SB" else 0)

            # If villain folds: win dead money
            dead_money = pot_preflop

            # If villain calls: play bigger pot
            eqr_key = "IP_3bettor" if ip else "OOP_3bettor"
            eqr_val = EQR[eqr_key]
            called_pot = size + open_size + 1.0 + 0.5

            # Compute equity vs villain's continuing range (tighter)
            # Villain continues with ~top 40% of their opening range
            continue_range = _narrow_range(villain_range_set, 0.40)
            continue_combo = range_to_weighted_combos(continue_range)
            eq_vs_continue = compute_equity(hero_cards, continue_combo) if continue_combo else equity

            called_ev = eq_vs_continue * called_pot * eqr_val - bet_cost

            evs[action] = ft3b * dead_money + (1 - ft3b) * called_ev
        else:
            evs[action] = 0.0

    return evs


def compute_vs_3bet_ev(hand_class: str, hero_pos: str, villain_pos: str,
                       actions: list, scenario: dict) -> dict:
    """Compute EV for facing a 3bet after hero opened.

    Actions: [Fold, Call, 4bet, All-in]
    """
    hero_combos = hand_class_to_combos(hand_class)
    if not hero_combos:
        return {a: 0.0 for a in actions}

    hero_cards = list(hero_combos[0])

    # Villain's 3bet range
    range_key = f"{hero_pos}_vs_3bet"
    threebet_key = f"{villain_pos}_vs_{hero_pos}"
    # Find appropriate 3bet range
    for key in [f"BB_vs_{hero_pos}", f"SB_vs_{hero_pos}", f"BTN_vs_{hero_pos}"]:
        if key in THREEBET_RANGES:
            villain_range_set = THREEBET_RANGES[key]
            break
    else:
        villain_range_set = THREEBET_RANGES.get("BB_vs_CO", set())

    villain_range = range_to_weighted_combos(villain_range_set)
    equity = compute_equity(hero_cards, villain_range)

    ip = is_hero_ip(hero_pos, villain_pos)
    open_size = 2.5
    threebet_size = 10.0  # Typical 3bet size
    pot_after_3bet = open_size + threebet_size + 1.5  # open + 3bet + blinds
    ft4b = FOLD_TO_4BET.get(villain_pos, 0.55)

    evs = {}
    for action in actions:
        a_lower = action.lower()
        if a_lower == "fold":
            evs[action] = 0.0  # Lose our open (2.5bb), but normalize to 0
        elif a_lower == "call":
            eqr_key = "IP_caller" if ip else "OOP_caller"
            eqr_val = EQR[eqr_key]
            call_cost = threebet_size - open_size
            called_pot = pot_after_3bet
            evs[action] = equity * called_pot * eqr_val - call_cost
        elif "4bet" in a_lower:
            size_str = a_lower.replace("4bet", "").strip()
            size = float(size_str.replace("bb", ""))
            bet_cost = size - open_size

            dead_money = pot_after_3bet
            eqr_key = "IP_3bettor" if ip else "OOP_3bettor"
            eqr_val = EQR[eqr_key]
            called_pot = size + threebet_size + 1.5

            # Villain 5bets or calls
            called_ev = equity * called_pot * eqr_val - bet_cost
            evs[action] = ft4b * dead_money + (1 - ft4b) * called_ev
        elif a_lower == "all-in":
            allin_size = 100.0  # 100bb
            bet_cost = allin_size - open_size

            dead_money = pot_after_3bet

            # If called, pure equity (all money in)
            total_pot = allin_size * 2 + 1.5
            called_ev = equity * total_pot - allin_size

            # Villain folds more vs all-in than vs 4bet
            ft_allin = ft4b + 0.10
            evs[action] = ft_allin * dead_money + (1 - ft_allin) * called_ev
        else:
            evs[action] = 0.0

    return evs


def compute_vs_limp_ev(hand_class: str, hero_pos: str, villain_pos: str,
                       actions: list) -> dict:
    """Compute EV for facing a limp."""
    hero_combos = hand_class_to_combos(hand_class)
    if not hero_combos:
        return {a: 0.0 for a in actions}

    hero_cards = list(hero_combos[0])

    # Limper's range is wide
    villain_range_set = OPENING_RANGES.get("BB", set())  # Very wide
    villain_range = range_to_weighted_combos(villain_range_set)
    equity = compute_equity(hero_cards, villain_range)

    ip = is_hero_ip(hero_pos, villain_pos)

    evs = {}
    for action in actions:
        a_lower = action.lower()
        if a_lower in ("fold", "check"):
            if hero_pos == "BB":
                # Free check in BB
                eqr_val = EQR["OOP_caller"]
                evs[action] = equity * 2.5 * eqr_val - 1.0  # Already posted 1bb
            else:
                evs[action] = 0.0
        elif a_lower == "limp behind":
            eqr_key = "IP_caller" if ip else "OOP_caller"
            eqr_val = EQR[eqr_key]
            pot = 3.5  # 1(limp) + 1(BB) + 0.5(SB) + 1(hero limp)
            cost = 1.0 if hero_pos == "SB" else 0.5
            evs[action] = equity * pot * eqr_val - cost
        elif a_lower.startswith("raise"):
            size_str = a_lower.replace("raise", "").strip()
            size = float(size_str.replace("bb", ""))
            cost = size - (1.0 if hero_pos == "BB" else 0.5 if hero_pos == "SB" else 0)

            fold_eq = 0.55  # Limpers fold often vs raise
            dead_money = 2.5  # limp + blinds
            eqr_key = "IP_raiser" if ip else "OOP_raiser"
            eqr_val = EQR[eqr_key]
            called_pot = size + 1.0 + 1.5  # raise + limp call + blinds

            called_ev = equity * called_pot * eqr_val - cost
            evs[action] = fold_eq * dead_money + (1 - fold_eq) * called_ev
        else:
            evs[action] = 0.0

    return evs


def _narrow_range(range_set: set, keep_fraction: float) -> set:
    """Keep top fraction of a range based on hand strength heuristic."""
    ri = {r: 14 - i for i, r in enumerate(RANKS)}

    def strength(h):
        if len(h) == 2:
            return ri[h[0]] * 2 + 15
        r1, r2 = ri[h[0]], ri[h[1]]
        base = r1 + r2
        if h.endswith("s"):
            base += 2
        return base

    ranked = sorted(range_set, key=strength, reverse=True)
    keep = max(1, int(len(ranked) * keep_fraction))
    return set(ranked[:keep])


def compute_ev_vs_best(raw_evs: dict) -> dict:
    best_ev = max(raw_evs.values())
    return {a: round(ev - best_ev, 4) for a, ev in raw_evs.items()}


def compute_ev_normalized(ev_vs_best: dict) -> dict:
    values = list(ev_vs_best.values())
    avg = sum(values) / len(values)
    return {a: round(ev - avg, 4) for a, ev in ev_vs_best.items()}


def compute_scenario(scenario: dict) -> dict:
    """Compute EV table for one scenario."""
    sid = scenario["id"]
    stype = scenario["type"]
    hero_pos = scenario["hero_position"]
    villain_pos = scenario.get("villain_position")
    actions = scenario["actions"]

    all_hands = get_all_169_hands()
    hands_data = {}

    for i, hand_class in enumerate(all_hands):
        if (i + 1) % 20 == 0 or i == 0:
            print(f"    {hand_class} ({i+1}/169)", end="\r", flush=True)

        if stype == "rfi":
            raw_evs = compute_rfi_ev(hand_class, hero_pos, actions)
        elif stype == "vs_open":
            raw_evs = compute_vs_open_ev(hand_class, hero_pos, villain_pos, actions, scenario)
        elif stype == "vs_3bet":
            raw_evs = compute_vs_3bet_ev(hand_class, hero_pos, villain_pos, actions, scenario)
        elif stype == "squeeze":
            raw_evs = compute_vs_open_ev(hand_class, hero_pos, villain_pos, actions, scenario)
        elif stype == "vs_limp":
            raw_evs = compute_vs_limp_ev(hand_class, hero_pos, villain_pos, actions)
        else:
            raw_evs = {a: 0.0 for a in actions}

        ev_vs_best = compute_ev_vs_best(raw_evs)
        ev_normalized = compute_ev_normalized(ev_vs_best)

        best_action = max(ev_vs_best, key=ev_vs_best.get)
        strategy = {a: 0.0 for a in actions}
        strategy[best_action] = 1.0

        hands_data[hand_class] = {
            "strategy": strategy,
            "ev_vs_best": ev_vs_best,
            "ev_normalized": ev_normalized,
        }

    print(f"    Done: {len(hands_data)} hands" + " " * 20)
    return {
        "scenario_id": sid,
        "source": "Computed: Monte Carlo equity + game tree EV model (treys)",
        "hands": hands_data,
    }


def main():
    with open(SCENARIOS_FILE, encoding="utf-8") as f:
        scenarios = json.load(f)

    EV_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    random.seed(42)

    specific = sys.argv[1] if len(sys.argv) > 1 else None

    for scenario in scenarios:
        sid = scenario["id"]
        if specific and sid != specific:
            continue

        print(f"\n  Computing {sid}...")
        start = time.time()
        ev_table = compute_scenario(scenario)
        elapsed = time.time() - start
        print(f"  Time: {elapsed:.1f}s")

        out_path = EV_TABLES_DIR / f"{sid}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ev_table, f, indent=2, ensure_ascii=False)
        print(f"  Saved: {out_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
