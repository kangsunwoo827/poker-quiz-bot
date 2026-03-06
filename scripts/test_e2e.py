#!/usr/bin/env python3
"""End-to-end test of quiz + bankroll logic."""
import sys
import tempfile
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "bot"))

from quiz import QuizManager
from bankroll import BankrollManager

# Test QuizManager
qm = QuizManager()
available = qm.get_available_scenarios()
print(f"Available scenarios: {len(available)}")
assert len(available) == 20, f"Expected 20 scenarios, got {len(available)}"

# Generate a question
q = qm.generate_question()
print(f"Question: {q.scenario.name} | {q.hand} ({q.hand_display})")
print(f"  Actions: {q.scenario.actions}")
print(f"  Best action: {q.best_action}")
print(f"  Correct actions: {q.correct_actions}")
print(f"  EV vs best: {q.ev_vs_best}")
print(f"  EV normalized: {q.ev_normalized}")
print()

# Test BankrollManager with temp DB
with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
    db_path = Path(f.name)
try:
    bm = BankrollManager(db_path)
    user = bm.get_or_create_user(12345, "testuser")
    print(f"New user bankroll: {user['bankroll']}")
    assert user["bankroll"] == 100.0

    # Record a correct answer
    result = bm.record_answer(
        user_id=12345, username="testuser",
        scenario_id=q.scenario.id, hand=q.hand,
        chosen_action=q.best_action,
        chosen_ev_normalized=q.ev_normalized[q.best_action],
        best_action=q.best_action,
        ev_vs_best=0.0,
        was_correct=True,
    )
    print(f"After correct answer: bankroll={result['bankroll']:.2f}, streak={result['streak']}")
    assert result["streak"] == 1
    assert result["was_correct"] is True

    # Record a wrong answer
    wrong_action = [a for a in q.scenario.actions if a != q.best_action][0]
    result2 = bm.record_answer(
        user_id=12345, username="testuser",
        scenario_id=q.scenario.id, hand=q.hand,
        chosen_action=wrong_action,
        chosen_ev_normalized=q.ev_normalized[wrong_action],
        best_action=q.best_action,
        ev_vs_best=q.ev_vs_best[wrong_action],
        was_correct=False,
    )
    print(f"After wrong answer: bankroll={result2['bankroll']:.2f}, streak={result2['streak']}")
    assert result2["streak"] == 0

    # Check stats
    stats = bm.get_user_stats(12345)
    print(f"Stats: {stats['correct_count']}/{stats['total_questions']} correct, accuracy={stats['accuracy']:.1f}%")
    assert stats["total_questions"] == 2
    assert stats["correct_count"] == 1

    # Check leaderboard
    lb = bm.get_leaderboard()
    print(f"Leaderboard: {len(lb)} entries")
    assert len(lb) == 1

    # Check history
    hist = bm.get_recent_history(12345)
    print(f"Recent history: {len(hist)} entries")
    assert len(hist) == 2

    # Test chart generation
    from chart import generate_range_chart
    scenario_hands = qm.get_scenario_hands(q.scenario.id)
    chart_bytes = generate_range_chart(
        scenario_hands=scenario_hands,
        actions=q.scenario.actions,
        highlight_hand=q.hand,
        title=q.scenario.name,
    )
    print(f"Chart generated: {len(chart_bytes)} bytes")
    assert len(chart_bytes) > 1000

finally:
    os.unlink(db_path)

print()
print("All E2E tests passed!")
