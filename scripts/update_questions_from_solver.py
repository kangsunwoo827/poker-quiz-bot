#!/usr/bin/env python3
"""
Parse solver results and update questions.json with actual GTO frequencies.
"""

import json
import re
from pathlib import Path

RESULTS_DIR = Path("/home/ubuntu/AIde/projects/poker-quiz-bot/data/solver_results")
QUESTIONS_FILE = Path("/home/ubuntu/AIde/projects/poker-quiz-bot/data/questions.json")

def hand_to_solver_format(hand: str) -> list:
    """Convert hand like A♠A♣ to solver combos like ['AsAc']."""
    # Map suits
    suit_map = {'♠': 's', '♦': 'd', '♣': 'c', '♥': 'h'}
    hand = hand.strip()
    
    # Parse the hand
    cards = []
    i = 0
    while i < len(hand):
        rank = hand[i]
        i += 1
        if i < len(hand) and hand[i] in suit_map:
            suit = suit_map[hand[i]]
            i += 1
        else:
            suit = ''
        cards.append((rank, suit))
    
    if len(cards) == 2:
        r1, s1 = cards[0]
        r2, s2 = cards[1]
        # Generate all possible combos
        combos = []
        if s1 and s2:
            # Specific suits given
            combos.append(f"{r1}{s1}{r2}{s2}")
        else:
            # All combos
            suits = ['s', 'h', 'd', 'c']
            for suit1 in suits:
                for suit2 in suits:
                    if suit1 != suit2 or r1 != r2:
                        combo = f"{r1}{suit1}{r2}{suit2}"
                        combos.append(combo)
        return combos
    return []

def get_strategy_for_hand(solver_result: dict, hand_combos: list) -> dict:
    """Extract strategy frequencies for given hand combos."""
    actions = solver_result.get('actions', [])
    strategy = solver_result.get('strategy', {}).get('strategy', {})
    
    if not strategy:
        return None
    
    # Aggregate frequencies across combos
    freq_sum = [0.0] * len(actions)
    count = 0
    
    for combo in hand_combos:
        if combo in strategy:
            freqs = strategy[combo]
            for i, f in enumerate(freqs):
                freq_sum[i] += f
            count += 1
        # Try reversed combo
        rev_combo = combo[2:4] + combo[0:2]
        if rev_combo in strategy:
            freqs = strategy[rev_combo]
            for i, f in enumerate(freqs):
                freq_sum[i] += f
            count += 1
    
    if count == 0:
        return None
    
    # Average and convert to percentages
    result = {}
    for i, action in enumerate(actions):
        avg = (freq_sum[i] / count) * 100
        # Simplify action names
        if 'CHECK' in action:
            name = 'Check'
        elif 'FOLD' in action:
            name = 'Fold'
        elif 'CALL' in action:
            name = 'Call'
        elif 'BET' in action:
            # Extract bet size
            match = re.search(r'BET\s+([\d.]+)', action)
            if match:
                size = float(match.group(1))
                name = f'Bet {size:.0f}%' if size < 10 else f'Bet {size:.1f}'
            else:
                name = 'Bet'
        elif 'RAISE' in action:
            name = 'Raise'
        else:
            name = action
        result[name] = round(avg, 1)
    
    return result

def find_best_action(frequencies: dict, options: list) -> int:
    """Find which option has highest frequency."""
    best_idx = 0
    best_freq = 0
    
    for i, opt in enumerate(options):
        opt_lower = opt.lower()
        for action, freq in frequencies.items():
            action_lower = action.lower()
            # Match check
            if 'check' in opt_lower and 'check' in action_lower:
                if freq > best_freq:
                    best_freq = freq
                    best_idx = i
            # Match fold
            elif 'fold' in opt_lower and 'fold' in action_lower:
                if freq > best_freq:
                    best_freq = freq
                    best_idx = i
            # Match call
            elif 'call' in opt_lower and 'call' in action_lower:
                if freq > best_freq:
                    best_freq = freq
                    best_idx = i
            # Match bet with percentage
            elif 'bet' in opt_lower and 'bet' in action_lower:
                # Try to match sizing
                opt_pct = re.search(r'(\d+)%', opt)
                if opt_pct:
                    pct = int(opt_pct.group(1))
                    if str(pct) in action or f'{pct}.0' in action:
                        if freq > best_freq:
                            best_freq = freq
                            best_idx = i
    
    return best_idx, best_freq

def main():
    with open(QUESTIONS_FILE) as f:
        questions = json.load(f)
    
    print("Parsing solver results and updating questions...\n")
    
    updates = []
    for q in questions:
        if q['type'] != 'postflop':
            continue
        
        qid = q['id']
        result_file = RESULTS_DIR / f"q{qid}_result.json"
        
        if not result_file.exists():
            print(f"Q{qid}: No solver result")
            continue
        
        with open(result_file) as f:
            solver_result = json.load(f)
        
        hand_combos = hand_to_solver_format(q['hand'])
        frequencies = get_strategy_for_hand(solver_result, hand_combos)
        
        if not frequencies:
            print(f"Q{qid}: Could not extract frequencies for {q['hand']}")
            continue
        
        # Determine correct answer
        best_idx, best_freq = find_best_action(frequencies, q['options'])
        
        print(f"Q{qid}: {q['hand']}")
        print(f"  Solver: {frequencies}")
        print(f"  Current answer: {q['answer']} ({q['options'][q['answer']]})")
        print(f"  Best action: {best_idx} ({q['options'][best_idx]}) @ {best_freq:.1f}%")
        
        if best_idx != q['answer']:
            print(f"  ⚠️  ANSWER CHANGE NEEDED!")
        print()
        
        updates.append({
            'id': qid,
            'frequencies': frequencies,
            'best_idx': best_idx,
            'best_freq': best_freq,
            'current_answer': q['answer'],
            'needs_change': best_idx != q['answer']
        })
    
    # Summary
    print("\n" + "="*50)
    changes = [u for u in updates if u['needs_change']]
    print(f"Total postflop: {len(updates)}")
    print(f"Answer changes needed: {len(changes)}")
    for c in changes:
        print(f"  Q{c['id']}: {c['current_answer']} → {c['best_idx']}")

if __name__ == "__main__":
    main()
