#!/usr/bin/env python3
"""
Extract and convert GTO preflop data to ev_tables format.

Usage:
  python scripts/extract_gto_data.py --input raw_data.json --scenario bb_vs_co
  python scripts/extract_gto_data.py --generate-sample

Input format (raw): hand -> action -> ev
Output format: ev_tables/{scenario_id}.json with ev_vs_best and ev_normalized

Can also generate sample data for testing.
"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EV_TABLES_DIR = DATA_DIR / "ev_tables"
SCENARIOS_FILE = DATA_DIR / "scenarios.json"

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]


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


def compute_ev_vs_best(raw_evs: dict) -> dict:
    """Convert raw EVs to relative-to-best format (best=0, rest negative)."""
    best_ev = max(raw_evs.values())
    return {action: round(ev - best_ev, 4) for action, ev in raw_evs.items()}


def compute_ev_normalized(ev_vs_best: dict) -> dict:
    """Normalize so average across actions = 0."""
    values = list(ev_vs_best.values())
    avg = sum(values) / len(values)
    return {action: round(ev - avg, 4) for action, ev in ev_vs_best.items()}


def convert_raw_to_ev_table(raw_data: dict, scenario_id: str, source: str = "") -> dict:
    """Convert raw EV data to full ev_table format.

    raw_data format:
    {
        "AA": {"Fold": -15.0, "Call": -5.0, "3bet 8bb": 12.3, "3bet 10bb": 12.5},
        ...
    }
    """
    hands = {}
    for hand_name, raw_evs in raw_data.items():
        ev_vs_best = compute_ev_vs_best(raw_evs)
        ev_normalized = compute_ev_normalized(ev_vs_best)

        # Default strategy: 100% on best action
        best_action = max(ev_vs_best, key=ev_vs_best.get)
        strategy = {a: 0.0 for a in raw_evs}
        strategy[best_action] = 1.0

        hands[hand_name] = {
            "strategy": strategy,
            "ev_vs_best": ev_vs_best,
            "ev_normalized": ev_normalized,
        }

    return {
        "scenario_id": scenario_id,
        "source": source,
        "hands": hands,
    }


def generate_sample_ev_data(scenario: dict) -> dict:
    """Generate realistic sample EV data for a scenario.

    Uses heuristic hand strength ranking to produce plausible EV values.
    This is for TESTING ONLY - real data should come from GTO solvers.
    """
    import random
    random.seed(42)

    actions = scenario["actions"]
    scenario_type = scenario["type"]
    hero_pos = scenario["hero_position"]

    # Hand strength heuristic (0-1 scale)
    def hand_strength(hand: str) -> float:
        rank_values = {r: 14 - i for i, r in enumerate(RANKS)}
        if len(hand) == 2:  # pair
            return 0.5 + rank_values[hand[0]] / 28.0
        r1, r2 = rank_values[hand[0]], rank_values[hand[1]]
        suited = hand.endswith("s")
        base = (r1 + r2) / 28.0
        if suited:
            base += 0.08
        gap = r1 - r2
        base -= gap * 0.01
        return max(0, min(1, base))

    all_hands = get_all_169_hands()
    hands_data = {}

    for hand in all_hands:
        strength = hand_strength(hand)

        if scenario_type == "rfi":
            # RFI: strong hands raise, weak fold
            fold_ev = 0.0
            if strength > 0.6:
                raise_ev = strength * 8 - 2 + random.uniform(-0.3, 0.3)
                raise2_ev = raise_ev - random.uniform(0, 0.5)
            elif strength > 0.35:
                raise_ev = strength * 3 - 0.5 + random.uniform(-0.3, 0.3)
                raise2_ev = raise_ev - random.uniform(0, 0.3)
            else:
                raise_ev = -1.0 - (1 - strength) * 3 + random.uniform(-0.2, 0.2)
                raise2_ev = raise_ev - random.uniform(0.1, 0.5)

            # Limp always worse than best raise (GTO never open-limps)
            best_raise = max(raise_ev, raise2_ev)
            limp_ev = best_raise - 0.5 - random.uniform(0, 1.0)

            raw_evs = dict(zip(actions, [fold_ev, limp_ev, raise_ev, raise2_ev]))

        elif scenario_type == "vs_open":
            # vs open: fold/call/3bet
            fold_ev = 0.0

            if strength > 0.7:
                call_ev = strength * 5 - 1 + random.uniform(-0.3, 0.3)
                bet3_small = strength * 8 - 2 + random.uniform(-0.3, 0.3)
                bet3_big = bet3_small - random.uniform(0, 0.5)
            elif strength > 0.4:
                call_ev = strength * 2 - 0.3 + random.uniform(-0.2, 0.2)
                bet3_small = strength * 3 - 1.5 + random.uniform(-0.3, 0.3)
                bet3_big = bet3_small - random.uniform(0, 0.4)
            else:
                call_ev = -0.5 - (1 - strength) * 2 + random.uniform(-0.2, 0.2)
                bet3_small = -1.0 - (1 - strength) * 3 + random.uniform(-0.2, 0.2)
                bet3_big = bet3_small - random.uniform(0.1, 0.5)

            raw_evs = dict(zip(actions, [fold_ev, call_ev, bet3_small, bet3_big]))

        elif scenario_type == "vs_3bet":
            fold_ev = 0.0

            if strength > 0.8:
                call_ev = strength * 6 - 2 + random.uniform(-0.3, 0.3)
                bet4_ev = strength * 10 - 4 + random.uniform(-0.3, 0.3)
                allin_ev = strength * 12 - 5 + random.uniform(-0.3, 0.3)
            elif strength > 0.5:
                call_ev = strength * 3 - 1 + random.uniform(-0.2, 0.2)
                bet4_ev = -1.0 + random.uniform(-0.5, 0.5)
                allin_ev = -2.0 + random.uniform(-0.5, 0.5)
            else:
                call_ev = -1.0 - (1 - strength) * 3
                bet4_ev = -2.0 - (1 - strength) * 4
                allin_ev = -3.0 - (1 - strength) * 5

            raw_evs = dict(zip(actions, [fold_ev, call_ev, bet4_ev, allin_ev]))

        elif scenario_type == "squeeze":
            fold_ev = 0.0
            if strength > 0.65:
                call_ev = strength * 4 - 1 + random.uniform(-0.2, 0.2)
                sq_small = strength * 7 - 2 + random.uniform(-0.3, 0.3)
                sq_big = sq_small - random.uniform(0, 0.4)
            else:
                call_ev = -0.5 - (1 - strength) * 2
                sq_small = -1.5 - (1 - strength) * 3
                sq_big = sq_small - random.uniform(0.1, 0.4)

            raw_evs = dict(zip(actions, [fold_ev, call_ev, sq_small, sq_big]))

        elif scenario_type == "vs_limp":
            # Check/fold is free
            check_ev = 0.0

            if strength > 0.5:
                raise_small = strength * 4 - 1 + random.uniform(-0.2, 0.2)
                raise_mid = raise_small - random.uniform(0, 0.3)
                raise_big = raise_mid - random.uniform(0, 0.3)
            else:
                raise_small = -0.5 - (1 - strength) * 2
                raise_mid = raise_small - random.uniform(0.1, 0.3)
                raise_big = raise_mid - random.uniform(0.1, 0.3)

            if len(actions) == 4 and actions[0].lower() in ("fold", "check"):
                if actions[1].lower() == "limp behind":
                    limp_ev = -0.2 - random.uniform(0, 0.3)
                    raw_evs = dict(zip(actions, [check_ev, limp_ev, raise_small, raise_mid]))
                else:
                    raw_evs = dict(zip(actions, [check_ev, raise_small, raise_mid, raise_big]))
            else:
                raw_evs = dict(zip(actions, [check_ev, raise_small, raise_mid, raise_big]))
        else:
            raw_evs = {a: 0.0 for a in actions}

        # Round
        raw_evs = {a: round(v, 2) for a, v in raw_evs.items()}
        hands_data[hand] = raw_evs

    return hands_data


def generate_sample_tables():
    """Generate sample EV tables for all scenarios."""
    with open(SCENARIOS_FILE, encoding="utf-8") as f:
        scenarios = json.load(f)

    EV_TABLES_DIR.mkdir(parents=True, exist_ok=True)

    for scenario in scenarios:
        sid = scenario["id"]
        print(f"Generating sample data for {sid}...")

        raw_data = generate_sample_ev_data(scenario)
        ev_table = convert_raw_to_ev_table(
            raw_data, sid,
            source="Sample data (heuristic, NOT solver-based)"
        )

        out_path = EV_TABLES_DIR / f"{sid}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(ev_table, f, indent=2, ensure_ascii=False)

        print(f"  -> {out_path} ({len(ev_table['hands'])} hands)")

    print(f"\nDone! Generated {len(scenarios)} EV tables.")


def convert_raw_file(input_path: str, scenario_id: str, source: str = ""):
    """Convert a raw EV data file to ev_table format."""
    with open(input_path, encoding="utf-8") as f:
        raw_data = json.load(f)

    ev_table = convert_raw_to_ev_table(raw_data, scenario_id, source)

    EV_TABLES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EV_TABLES_DIR / f"{scenario_id}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(ev_table, f, indent=2, ensure_ascii=False)

    print(f"Converted {input_path} -> {out_path} ({len(ev_table['hands'])} hands)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract/convert GTO preflop data")
    parser.add_argument("--input", help="Raw EV data file")
    parser.add_argument("--scenario", help="Scenario ID")
    parser.add_argument("--source", default="", help="Data source description")
    parser.add_argument("--generate-sample", action="store_true",
                        help="Generate sample EV tables for all scenarios")

    args = parser.parse_args()

    if args.generate_sample:
        generate_sample_tables()
    elif args.input and args.scenario:
        convert_raw_file(args.input, args.scenario, args.source)
    else:
        parser.print_help()
        sys.exit(1)
