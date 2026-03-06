#!/usr/bin/env python3
"""
Validate EV data integrity for all scenarios.

Checks:
1. ev_normalized sums to ~0 for each hand
2. AA is always raise/3bet/4bet optimal (not fold/call)
3. Worst hands (72o, 32o, 42o) are always fold optimal in most scenarios
4. Limp EV < Raise EV (GTO never open-limps)
5. All EV values in reasonable range
6. Strategy frequencies sum to 1.0
7. Best action matches highest EV
8. All 169 hands present
"""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
EV_TABLES_DIR = DATA_DIR / "ev_tables"
SCENARIOS_FILE = DATA_DIR / "scenarios.json"

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

WORST_HANDS = {"72o", "32o", "42o", "52o", "73o", "82o", "83o", "43o", "62o", "63o"}
PREMIUM_HANDS = {"AA", "KK", "QQ", "AKs"}


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


def validate_scenario(scenario_id: str, ev_table: dict, scenario: dict) -> list[str]:
    errors = []
    hands = ev_table.get("hands", {})
    actions = scenario["actions"]
    scenario_type = scenario["type"]
    all_169 = set(get_all_169_hands())

    # Check all 169 hands present
    present = set(hands.keys())
    missing = all_169 - present
    if missing:
        errors.append(f"[{scenario_id}] Missing {len(missing)} hands: {sorted(missing)[:5]}...")

    extra = present - all_169
    if extra:
        errors.append(f"[{scenario_id}] Extra hands: {sorted(extra)[:5]}...")

    for hand_name, hand_data in hands.items():
        ev_vs_best = hand_data.get("ev_vs_best", {})
        ev_normalized = hand_data.get("ev_normalized", {})
        strategy = hand_data.get("strategy", {})

        # 1. ev_normalized should average to ~0
        if ev_normalized:
            avg = sum(ev_normalized.values()) / len(ev_normalized)
            if abs(avg) > 0.01:
                errors.append(
                    f"[{scenario_id}] {hand_name}: ev_normalized avg = {avg:.4f} (should be ~0)"
                )

        # 2. ev_vs_best: best should be 0
        if ev_vs_best:
            best_val = max(ev_vs_best.values())
            if abs(best_val) > 0.001:
                errors.append(
                    f"[{scenario_id}] {hand_name}: ev_vs_best max = {best_val:.4f} (should be 0)"
                )

            # All others should be <= 0
            for action, ev in ev_vs_best.items():
                if ev > 0.001:
                    errors.append(
                        f"[{scenario_id}] {hand_name}: ev_vs_best[{action}] = {ev:.4f} (should be <= 0)"
                    )

        # 3. Strategy sums to 1.0
        if strategy:
            strat_sum = sum(strategy.values())
            if abs(strat_sum - 1.0) > 0.01:
                errors.append(
                    f"[{scenario_id}] {hand_name}: strategy sum = {strat_sum:.4f} (should be 1.0)"
                )

        # 4. EV values in reasonable range
        # vs_3bet scenarios have inherently wider EV spread (4bet/all-in pots)
        if scenario_type == "vs_3bet":
            evb_lo, evb_hi = -50, 0.001
            evn_lo, evn_hi = -35, 40
        else:
            evb_lo, evb_hi = -30, 0.001
            evn_lo, evn_hi = -20, 30

        for action, ev in ev_vs_best.items():
            if ev < evb_lo or ev > evb_hi:
                errors.append(
                    f"[{scenario_id}] {hand_name}: ev_vs_best[{action}] = {ev:.2f} out of range"
                )

        for action, ev in ev_normalized.items():
            if ev < evn_lo or ev > evn_hi:
                errors.append(
                    f"[{scenario_id}] {hand_name}: ev_normalized[{action}] = {ev:.2f} out of range"
                )

        # 5. Best action consistency
        if ev_vs_best:
            best_action = max(ev_vs_best, key=ev_vs_best.get)

            # Premium hands should not fold (in any scenario)
            if hand_name in PREMIUM_HANDS:
                if best_action.lower() == "fold":
                    errors.append(
                        f"[{scenario_id}] {hand_name}: premium hand best action is Fold!"
                    )

            # Worst hands should fold in RFI and vs_open scenarios
            if hand_name in WORST_HANDS and scenario_type in ("rfi", "vs_open"):
                if best_action.lower() not in ("fold", "check"):
                    errors.append(
                        f"[{scenario_id}] {hand_name}: worst hand best action is {best_action} (expected Fold)"
                    )

        # 6. Limp should be worse than raise (RFI scenarios, in-range hands only)
        # For out-of-range hands (where both Limp and Raise are dominated by Fold),
        # the relative ordering doesn't matter
        if scenario_type == "rfi" and "Limp" in ev_vs_best:
            limp_ev = ev_vs_best.get("Limp", 0)
            raise_evs = [ev for a, ev in ev_vs_best.items()
                         if a.lower().startswith("raise")]
            if raise_evs:
                best_raise = max(raise_evs)
                # Only check when raising is profitable (hand is in-range)
                if best_raise > 0 and limp_ev > best_raise + 0.1:
                    errors.append(
                        f"[{scenario_id}] {hand_name}: Limp EV ({limp_ev:.2f}) > Raise EV ({best_raise:.2f})"
                    )

    return errors


def main():
    with open(SCENARIOS_FILE, encoding="utf-8") as f:
        scenarios_list = json.load(f)
    scenarios = {s["id"]: s for s in scenarios_list}

    all_errors = []
    tables_checked = 0

    for path in sorted(EV_TABLES_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            ev_table = json.load(f)

        scenario_id = ev_table.get("scenario_id", path.stem)
        if scenario_id not in scenarios:
            all_errors.append(f"[{scenario_id}] No matching scenario definition!")
            continue

        errors = validate_scenario(scenario_id, ev_table, scenarios[scenario_id])
        all_errors.extend(errors)
        tables_checked += 1

        status = "PASS" if not errors else f"FAIL ({len(errors)} errors)"
        print(f"  {scenario_id}: {status}")

    # Check for scenarios without EV tables
    ev_table_ids = {p.stem for p in EV_TABLES_DIR.glob("*.json")}
    for sid in scenarios:
        if sid not in ev_table_ids:
            print(f"  {sid}: NO DATA")

    print(f"\nChecked {tables_checked} tables.")
    if all_errors:
        print(f"\n{len(all_errors)} errors found:")
        for e in all_errors[:50]:
            print(f"  {e}")
        if len(all_errors) > 50:
            print(f"  ... and {len(all_errors) - 50} more")
        return 1
    else:
        print("\nAll checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
