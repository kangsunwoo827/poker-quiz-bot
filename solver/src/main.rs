use postflop_solver::*;

use serde::Serialize;
use std::collections::HashMap;
use std::fs;
use std::path::Path;

#[derive(serde::Deserialize, Clone)]
struct Scenario {
    id: String,
    #[serde(rename = "type")]
    scenario_type: String,
    name: String,
    hero_position: String,
    villain_position: Option<String>,
    actions: Vec<String>,
}

#[derive(Serialize)]
struct EvTable {
    scenario_id: String,
    source: String,
    hands: HashMap<String, HandData>,
}

#[derive(Serialize, Clone)]
struct HandData {
    strategy: HashMap<String, f64>,
    ev_vs_best: HashMap<String, f64>,
    ev_normalized: HashMap<String, f64>,
}

const RANKS: [&str; 13] = ["A","K","Q","J","T","9","8","7","6","5","4","3","2"];

fn get_opening_range(pos: &str) -> &'static str {
    match pos {
        "UTG" => "AA-22,AKs-A2s,KQs-K9s,QJs-QTs,JTs-J9s,T9s,98s,87s,76s,65s,AKo-ATo,KQo-KJo,QJo",
        "MP"  => "AA-22,AKs-A2s,KQs-K8s,QJs-Q9s,JTs-J9s,T9s-T8s,98s,87s,76s,65s,54s,AKo-A9o,KQo-KTo,QJo-QTo,JTo",
        "CO"  => "AA-22,AKs-A2s,KQs-K5s,QJs-Q8s,JTs-J8s,T9s-T8s,98s-97s,87s-86s,76s-75s,65s-64s,54s,43s,AKo-A7o,KQo-K9o,QJo-Q9o,JTo-J9o,T9o,98o",
        "BTN" => "AA-22,AKs-A2s,KQs-K2s,QJs-Q5s,JTs-J7s,T9s-T7s,98s-96s,87s-85s,76s-74s,65s-63s,54s-53s,43s,32s,AKo-A2o,KQo-K7o,QJo-Q8o,JTo-J8o,T9o-T8o,98o-97o,87o,76o",
        "SB"  => "AA-22,AKs-A2s,KQs-K4s,QJs-Q7s,JTs-J7s,T9s-T7s,98s-96s,87s-85s,76s-75s,65s-64s,54s,43s,AKo-A5o,KQo-K9o,QJo-Q9o,JTo-J9o,T9o",
        "BB"  => "AA-22,AKs-A2s,KQs-K2s,QJs-Q2s,JTs-J5s,T9s-T6s,98s-95s,87s-84s,76s-74s,65s-63s,54s-53s,43s,32s,AKo-A2o,KQo-K5o,QJo-Q7o,JTo-J8o,T9o-T8o,98o-97o,87o,76o",
        _ => "AA-TT,AKs-ATs,AKo-AJo,KQs",
    }
}

/// Villain's range when calling a 3bet (much tighter than open range)
fn get_call_3bet_range(pos: &str) -> &'static str {
    match pos {
        "UTG" => "QQ-99,AKs-AJs,KQs,AKo-AQo",
        "MP"  => "QQ-88,AKs-ATs,KQs-KJs,QJs,AKo-AJo,KQo",
        "CO"  => "QQ-77,AKs-A9s,KQs-KTs,QJs-QTs,JTs,AKo-ATo,KQo-KJo,QJo",
        "BTN" => "QQ-66,AKs-A7s,KQs-K9s,QJs-Q9s,JTs-J9s,T9s,AKo-A9o,KQo-KTo,QJo-QTo,JTo",
        "SB"  => "QQ-77,AKs-A8s,KQs-KTs,QJs-QTs,JTs,AKo-ATo,KQo-KJo,QJo",
        _ => "QQ-TT,AKs-AJs,KQs,AKo",
    }
}

/// Hero's 4bet range (subset of opening range used when 4betting)
fn get_4bet_range(pos: &str) -> &'static str {
    match pos {
        "UTG" => "QQ+,AKs,AKo",
        "MP"  => "QQ+,AKs,AQs,AKo",
        "CO"  => "TT+,AKs,AQs,A5s-A4s,AKo,AQo",
        "BTN" => "TT+,AKs-AJs,A5s-A4s,KQs,AKo,AQo",
        "SB"  => "TT+,AKs,AQs,A5s-A4s,AKo",
        _ => "QQ+,AKs,AKo",
    }
}

/// Hero's range when calling a 3bet (subset of opening range, excluding 4bet and fold hands)
/// Ranges calibrated from PokerTrainer.se GTO preflop charts
fn get_hero_call_3bet_range(hero_pos: &str, villain_pos: &str) -> &'static str {
    match (hero_pos, villain_pos) {
        // UTG opens, faces 3bet
        ("UTG", "BB")  => "JJ-99,AQs,AJs,KQs,AQo",
        ("UTG", "SB")  => "JJ-99,AQs,AJs,88",
        ("UTG", _)     => "JJ-99,AQs,AJs",
        // MP opens, faces 3bet
        ("MP", "BB")   => "JJ-88,AQs-ATs,KQs-KJs,QJs,AQo,AJo",
        ("MP", _)      => "JJ-88,AQs-ATs,KQs-KJs,QJs,AQo",
        // CO opens, faces 3bet
        ("CO", "BTN")  => "JJ-88,AQs-ATs,KQs-KJs,QJs,AQo",
        ("CO", "SB")   => "JJ-99,AQs-ATs,KQs,AQo",
        ("CO", "BB")   => "JJ-88,AQs-ATs,KQs-KJs,QJs,JTs,AQo,KQo",
        ("CO", _)      => "JJ-88,AQs-ATs,KQs-KJs,QJs,AQo",
        // BTN opens, faces 3bet
        ("BTN", "BB")  => "JJ-77,AQs-A9s,KQs-KJs,QJs-QTs,JTs,T9s,98s,AQo,AJo",
        ("BTN", "SB")  => "JJ-88,AQs-ATs,KQs-KJs,QJs,98s,AQo",
        ("BTN", _)     => "JJ-88,AQs-ATs,KQs-KJs,QJs,AQo",
        // SB opens, faces 3bet
        ("SB", "BB")   => "JJ-77,AQs-ATs,KQs-KJs,QJs-QTs,JTs,T9s,AQo,AJo,KQo",
        ("SB", _)      => "JJ-88,AQs-ATs,KQs-KJs,QJs,AQo",
        _ => "JJ-99,AQs,AJs,KQs,AQo",
    }
}

/// Hero's 3bet range when facing an open (polarized: value + bluffs)
fn get_hero_3bet_range(hero_pos: &str, villain_pos: &str) -> &'static str {
    match (hero_pos, villain_pos) {
        ("BB", "UTG") => "QQ+,AKs,AQs,A5s-A4s,AKo",
        ("BB", "MP")  => "QQ+,AKs,AQs,A5s-A4s,KQs,AKo,AQo",
        ("BB", "CO")  => "QQ+,AKs-AQs,A5s-A3s,KQs,AKo,AQo",
        ("BB", "BTN") => "QQ+,AKs-AQs,A5s-A2s,KQs,K9s,87s,76s,65s,AKo,AQo",
        ("SB", "CO")  => "QQ+,AKs,AQs,A5s-A4s,KQs,AKo",
        ("SB", "BTN") => "QQ+,AKs-AQs,A5s-A4s,KQs,AKo,AQo",
        ("BTN","CO")  => "TT+,AKs-AJs,A5s-A4s,KQs,AKo-AQo",
        ("CO", "UTG") => "QQ+,AKs,AQs,AKo",
        _ => "QQ+,AKs,AQs,A5s-A4s,AKo",
    }
}

fn all_169_hands() -> Vec<String> {
    let mut hands = Vec::with_capacity(169);
    for (i, r1) in RANKS.iter().enumerate() {
        for (j, r2) in RANKS.iter().enumerate() {
            if i < j { hands.push(format!("{}{}s", r1, r2)); }
            else if i > j { hands.push(format!("{}{}o", r2, r1)); }
            else { hands.push(format!("{}{}", r1, r2)); }
        }
    }
    hands
}

/// Generate evenly-spaced representative flops from all C(52,3)=22100 flops.
fn representative_flops(n: usize) -> Vec<[u8; 3]> {
    let mut all: Vec<[u8; 3]> = Vec::with_capacity(22100);
    for i in 0u8..52 {
        for j in (i+1)..52 {
            for k in (j+1)..52 {
                all.push([i, j, k]);
            }
        }
    }
    let step = all.len() as f64 / n as f64;
    (0..n).map(|i| all[(i as f64 * step) as usize]).collect()
}

/// Solve one postflop spot. Returns a map from combo_index -> EV for the given player.
fn solve_spot(
    oop_range: &str, ip_range: &str,
    flop: [u8; 3], pot: i32, stack: i32,
    player: usize,
) -> Option<HashMap<usize, f32>> {
    let card_config = CardConfig {
        range: [oop_range.parse().ok()?, ip_range.parse().ok()?],
        flop,
        turn: NOT_DEALT,
        river: NOT_DEALT,
    };
    // Minimal bet tree for fast computation: single bet + all-in per street
    let flop_bets = BetSizeOptions::try_from(("50%, a", "")).ok()?;
    let turn_bets = BetSizeOptions::try_from(("66%, a", "")).ok()?;
    let river_bets = BetSizeOptions::try_from(("75%, a", "")).ok()?;
    let tree_config = TreeConfig {
        initial_state: BoardState::Flop,
        starting_pot: pot,
        effective_stack: stack,
        rake_rate: 0.0, rake_cap: 0.0,
        flop_bet_sizes: [flop_bets.clone(), flop_bets],
        turn_bet_sizes: [turn_bets.clone(), turn_bets],
        river_bet_sizes: [river_bets.clone(), river_bets],
        turn_donk_sizes: None, river_donk_sizes: None,
        add_allin_threshold: 1.5,
        force_allin_threshold: 0.15,
        merging_threshold: 0.2,
    };
    let action_tree = ActionTree::new(tree_config).ok()?;
    let mut game = PostFlopGame::with_config(card_config, action_tree).ok()?;
    game.allocate_memory(false);
    let target = pot as f32 * 0.01; // 1% pot accuracy
    solve(&mut game, 200, target, false);
    game.cache_normalized_weights();

    let evs = game.expected_values(player);
    let hands = game.private_cards(player);
    let mut result = HashMap::new();
    for (i, &(c1, c2)) in hands.iter().enumerate() {
        let idx = combo_index(c1 as usize, c2 as usize);
        result.insert(idx, evs[i]);
    }
    Some(result)
}

/// postflop-solver rank encoding: A=12, K=11, ..., 2=0
fn char_to_rank(c: char) -> Option<u8> {
    match c {
        'A' => Some(12), 'K' => Some(11), 'Q' => Some(10), 'J' => Some(9),
        'T' => Some(8), '9' => Some(7), '8' => Some(6), '7' => Some(5),
        '6' => Some(4), '5' => Some(3), '4' => Some(2), '3' => Some(1), '2' => Some(0),
        _ => None,
    }
}

/// Replicate postflop-solver's card_pair_to_index (pub(crate), not exported)
/// card encoding: card = rank * 4 + suit, where rank: A=12..2=0, suit: c=0,d=1,h=2,s=3
/// index formula: card1 * (101 - card1) / 2 + card2 - 1  (card1 < card2)
fn combo_index(card1: usize, card2: usize) -> usize {
    let (lo, hi) = if card1 < card2 { (card1, card2) } else { (card2, card1) };
    lo * (101 - lo) / 2 + hi - 1
}

/// Map hand class (e.g. "AKs") to average EV from combo-indexed EV map.
fn hand_class_ev(range: &Range, hand: &str, evs: &HashMap<usize, f32>) -> Option<f64> {
    let chars: Vec<char> = hand.chars().collect();
    let r1 = char_to_rank(chars[0])? as usize;
    let r2 = char_to_rank(chars[1])? as usize;
    let suited = chars.len() == 3 && chars[2] == 's';
    let pair = r1 == r2;

    let data = range.raw_data();
    let mut total_ev = 0.0f64;
    let mut total_w = 0.0f64;
    for s1 in 0..4usize {
        for s2 in 0..4usize {
            if pair && s1 >= s2 { continue; }
            if !pair && suited && s1 != s2 { continue; }
            if !pair && !suited && s1 == s2 { continue; }
            let c1 = r1 * 4 + s1;
            let c2 = r2 * 4 + s2;
            let idx = combo_index(c1, c2);
            if let Some(&ev) = evs.get(&idx) {
                let w = data[idx] as f64; // already f32 in [0.0, 1.0]
                if w > 0.0 {
                    total_ev += ev as f64 * w;
                    total_w += w;
                }
            }
        }
    }
    if total_w > 0.0 { Some(total_ev / total_w) } else { None }
}

/// Solve postflop across representative flops and average EVs.
/// Returns a map from combo_index -> average EV in bb.
fn avg_postflop_ev(
    oop_range: &str, ip_range: &str,
    pot_bb: f64, stack_bb: f64, n_flops: usize,
    player: usize,
) -> HashMap<usize, f32> {
    let pot = (pot_bb * 100.0) as i32;
    let stack = (stack_bb * 100.0) as i32;
    let flops = representative_flops(n_flops);

    // Solve flops sequentially to control memory usage
    let results: Vec<Option<HashMap<usize, f32>>> = flops.iter()
        .map(|f| solve_spot(oop_range, ip_range, *f, pot, stack, player))
        .collect();

    let valid: Vec<&HashMap<usize, f32>> = results.iter().filter_map(|r| r.as_ref()).collect();
    let n = valid.len();
    eprint!("({}/{} flops) ", n, n_flops);
    if n == 0 { return HashMap::new(); }

    // Accumulate EVs per combo index
    let mut sum: HashMap<usize, f64> = HashMap::new();
    let mut count: HashMap<usize, usize> = HashMap::new();
    for v in &valid {
        for (&idx, &ev) in v.iter() {
            *sum.entry(idx).or_insert(0.0) += ev as f64;
            *count.entry(idx).or_insert(0) += 1;
        }
    }

    // Average and convert chips -> bb
    sum.into_iter()
        .map(|(idx, total)| {
            let c = count[&idx] as f64;
            (idx, (total / c / 100.0) as f32)
        })
        .collect()
}

fn compute_vs_open(scenario: &Scenario, n_flops: usize) -> HashMap<String, HashMap<String, f64>> {
    let villain_pos = scenario.villain_position.as_deref().unwrap_or("CO");
    let hero_pos = &scenario.hero_position;

    let villain_range = get_opening_range(villain_pos);
    let hero_range = get_opening_range(hero_pos);

    let open_size = 2.5f64;
    let blinds = 1.5f64;
    let ft3b: f64 = match villain_pos {
        "UTG" => 0.60, "MP" => 0.55, "CO" => 0.50, "BTN" => 0.45, _ => 0.50,
    };

    // OOP = player 0, IP = player 1
    let hero_is_oop = matches!(hero_pos.as_str(), "BB" | "SB")
        || (hero_pos == "CO" && villain_pos == "UTG");
    let (oop_range, ip_range, hero_player) = if hero_is_oop {
        (hero_range, villain_range, 0usize)
    } else {
        (villain_range, hero_range, 1usize)
    };

    // Solve CALL branch postflop
    eprint!("  Call branch: ");
    let call_pot = open_size * 2.0 + blinds;
    let call_stack = 100.0 - open_size;
    let call_evs = avg_postflop_ev(oop_range, ip_range, call_pot, call_stack, n_flops, hero_player);
    eprintln!();

    // Solve 3BET-CALLED branch postflop (for each 3bet size)
    let bet3_sizes: Vec<(String, f64)> = scenario.actions.iter()
        .filter(|a| {
            let l = a.to_lowercase();
            l.contains("3bet") || l.contains("squeeze")
        })
        .map(|a| {
            let s = a.to_lowercase();
            let num: f64 = s.split_whitespace().last()
                .and_then(|x| x.replace("bb","").parse().ok())
                .unwrap_or(8.0);
            (a.clone(), num)
        })
        .collect();

    // When villain calls a 3bet, they use a tighter range
    let villain_call_3bet = get_call_3bet_range(villain_pos);
    // Hero's 3bet range is a polarized subset (not the full opening range)
    let hero_3bet_range_str = get_hero_3bet_range(hero_pos, villain_pos);
    let (oop_3b, ip_3b) = if hero_is_oop {
        (hero_3bet_range_str, villain_call_3bet)
    } else {
        (villain_call_3bet, hero_3bet_range_str)
    };

    let mut bet3_evs: HashMap<String, HashMap<usize, f32>> = HashMap::new();
    for (name, size) in &bet3_sizes {
        eprint!("  {} branch: ", name);
        let pot = size * 2.0 + blinds;
        let stack = 100.0 - size;
        let evs = avg_postflop_ev(oop_3b, ip_3b, pot, stack, n_flops, hero_player);
        eprintln!();
        bet3_evs.insert(name.clone(), evs);
    }

    // Build hand-level EVs
    // Baseline: fold = 0 (sunk blind cost ignored)
    // Hero's blind contribution already posted:
    let blind_posted: f64 = match hero_pos.as_str() {
        "BB" => 1.0, "SB" => 0.5, _ => 0.0,
    };
    // Dead money from others when villain folds to 3bet
    let dead_money = open_size + blinds - blind_posted; // what hero wins net when villain folds

    let range_parsed: Range = hero_range.parse().unwrap();
    let range_3bet: Range = hero_3bet_range_str.parse().unwrap();
    let all = all_169_hands();
    let mut result = HashMap::new();

    for hand in &all {
        let mut evs = HashMap::new();

        for action in &scenario.actions {
            let lower = action.to_lowercase();
            if lower == "fold" || lower == "check" {
                evs.insert(action.clone(), 0.0);
            } else if lower == "call" {
                let add_cost = open_size - blind_posted;
                let call_pot = open_size * 2.0 + blinds;
                let oor_fallback = -(call_pot * 0.4 + add_cost * 0.6);
                let ev = hand_class_ev(&range_parsed, hand, &call_evs)
                    .map(|pf_ev| pf_ev - add_cost)
                    .unwrap_or(oor_fallback);
                evs.insert(action.clone(), ev);
            } else if lower.contains("3bet") || lower.contains("squeeze") {
                let size: f64 = lower.split_whitespace().last()
                    .and_then(|x| x.replace("bb","").parse().ok())
                    .unwrap_or(8.0);
                let add_cost = size - blind_posted;
                let bet3_pot = size * 2.0 + blinds;
                let oor_fallback = -(bet3_pot * 0.4 + add_cost * 0.6);

                let called_net = bet3_evs.get(action)
                    .and_then(|ev_map| hand_class_ev(&range_3bet, hand, ev_map))
                    .map(|pf_ev| pf_ev - add_cost)
                    .unwrap_or(oor_fallback);

                let ev = ft3b * dead_money + (1.0 - ft3b) * called_net;
                evs.insert(action.clone(), ev);
            }
        }
        result.insert(hand.clone(), evs);
    }
    result
}

fn compute_rfi(scenario: &Scenario, n_flops: usize) -> HashMap<String, HashMap<String, f64>> {
    let hero_pos = &scenario.hero_position;
    let bb_range = get_opening_range("BB");
    let blinds = 1.5f64;

    // Probability all players behind fold to hero's open
    // SB: BB defends ~45% vs SB open (position + pot odds), so fold rate ≈ 55%
    let all_fold: f64 = match hero_pos.as_str() {
        "SB" => 0.55,
        _ => {
            let n_behind: i32 = match hero_pos.as_str() {
                "UTG"=>5, "MP"=>4, "CO"=>3, "BTN"=>2, _=>3,
            };
            0.85f64.powi(n_behind)
        }
    };

    // Solve postflop for each raise size (hero raised, BB called)
    let raise_actions: Vec<(String, f64)> = scenario.actions.iter()
        .filter(|a| a.to_lowercase().starts_with("raise"))
        .map(|a| {
            let s = a.to_lowercase().replace("raise","");
            let num: f64 = s.trim().replace("bb","").parse().unwrap_or(2.5);
            (a.clone(), num)
        })
        .collect();

    let hero_is_ip = hero_pos != "SB";
    let hero_player = if hero_is_ip { 1usize } else { 0usize };
    let hero_range = get_opening_range(hero_pos);
    let mut raise_evs: HashMap<String, HashMap<usize, f32>> = HashMap::new();

    for (name, size) in &raise_actions {
        eprint!("  {} branch: ", name);
        let pot = size * 2.0 + blinds;
        let stack = 100.0 - size;
        let (oop, ip) = if hero_is_ip { (bb_range, hero_range) } else { (hero_range, bb_range) };
        let evs = avg_postflop_ev(oop, ip, pot, stack, n_flops, hero_player);
        eprintln!();
        raise_evs.insert(name.clone(), evs);
    }

    let hero_parsed: Range = hero_range.parse().unwrap();
    let blind_posted: f64 = match hero_pos.as_str() {
        "BB" => 1.0, "SB" => 0.5, _ => 0.0,
    };
    let all = all_169_hands();
    let mut result = HashMap::new();

    for hand in &all {
        let mut evs = HashMap::new();
        for action in &scenario.actions {
            let lower = action.to_lowercase();
            if lower == "fold" {
                evs.insert(action.clone(), 0.0);
            } else if lower == "limp" || lower == "limp behind" {
                // Open-limping is always dominated in GTO
                // More punishing from earlier positions (more iso-raises)
                let limp_penalty: f64 = match hero_pos.as_str() {
                    "UTG" => -2.5, "MP" => -2.0, "CO" => -1.5,
                    "BTN" => -1.2, "SB" => -1.5, _ => -1.5,
                };
                evs.insert(action.clone(), limp_penalty);
            } else if lower.starts_with("raise") {
                let size: f64 = lower.replace("raise","").trim()
                    .replace("bb","").parse().unwrap_or(2.5);
                let add_cost = size - blind_posted;

                // When everyone folds: hero wins blinds (net = blinds - 0 since fold = 0 baseline)
                // When BB calls: solver_ev is hero's share of pot, net = solver_ev - add_cost
                // For out-of-range hands (not in hero's opening range):
                // They perform terribly postflop + sometimes face 3bets
                let pot_when_called = size * 2.0 + blinds;
                let oor_fallback = -(add_cost * 2.5 + pot_when_called * 0.4);
                let called_net = if let Some(ev_map) = raise_evs.get(action) {
                    hand_class_ev(&hero_parsed, hand, ev_map)
                        .map(|pf_ev| pf_ev - add_cost)
                        .unwrap_or(oor_fallback)
                } else { oor_fallback };

                let ev = all_fold * blinds + (1.0 - all_fold) * called_net;
                evs.insert(action.clone(), ev);
            }
        }
        result.insert(hand.clone(), evs);
    }
    result
}

/// vs_3bet: Hero opened, villain 3bet. Hero decides fold/call/4bet/all-in.
fn compute_vs_3bet(scenario: &Scenario, n_flops: usize) -> HashMap<String, HashMap<String, f64>> {
    let hero_pos = &scenario.hero_position;
    let villain_pos = scenario.villain_position.as_deref().unwrap_or("BB");

    // Hero opened, villain 3bet. Typical 3bet size depends on villain position.
    let open_size = match hero_pos.as_str() {
        "BTN" => 2.5f64, _ => 2.5f64,
    };
    let threeb_size = match villain_pos {
        "BB" | "SB" => 10.0f64,
        "BTN" => 8.0f64,
        _ => 9.0f64,
    };
    // Dead money from folded blinds (not hero or villain)
    let dead_blinds: f64 = match villain_pos {
        "BB" => 0.5,   // only SB dead
        "SB" => 1.0,   // only BB dead
        _ => 1.5,      // both blinds dead (villain is BTN/CO/MP)
    };

    // Villain's response to hero's 4bet: fold, call, or 5bet-shove
    // Derived from PokerTrainer.se GTO charts (5bet / call-4bet / fold fractions of 3bet range)
    let (ft4b_fold, ft4b_call, ft4b_5bet) = match villain_pos {
        "BB"  => (0.50, 0.15, 0.35),  // BB 3bets polar, 5bets aggressively
        "SB"  => (0.55, 0.12, 0.33),
        "BTN" => (0.53, 0.21, 0.26),  // BTN has more flats in 3bet range
        _ => (0.50, 0.15, 0.35),
    };

    // Hero is IP (opened from EP/MP/CO/BTN), villain 3bet from blinds/BTN
    let hero_is_ip = !matches!(villain_pos, "BTN" | "CO");
    let hero_player = if hero_is_ip { 1usize } else { 0usize };

    // Villain's 3bet range (approximate - includes value + bluffs)
    let villain_3bet_range = match villain_pos {
        "BB" => "QQ+,AKs,AQs,A5s-A4s,KQs,AKo,AQo",
        "SB" => "QQ+,AKs,AQs,A5s-A3s,KQs,AKo",
        "BTN" => "TT+,AKs-AJs,KQs,A5s-A4s,AKo-AQo",
        _ => "QQ+,AKs,AQs,AKo",
    };

    // Villain's call-4bet range (wider than just premiums)
    let villain_call_4bet = "TT+,AQs+,AKo";

    // Hero's 4bet range (tighter than full opening range)
    let hero_4bet = get_4bet_range(hero_pos);

    // Solve CALL branch (hero calls the 3bet)
    eprint!("  Call branch: ");
    let call_pot = threeb_size * 2.0 + dead_blinds; // both players match 3bet + dead blinds
    let call_stack = 100.0 - threeb_size;
    let hero_call_range = get_hero_call_3bet_range(hero_pos, villain_pos);
    let (oop_call, ip_call) = if hero_is_ip {
        (villain_3bet_range, hero_call_range)
    } else {
        (hero_call_range, villain_3bet_range)
    };
    let call_evs = avg_postflop_ev(oop_call, ip_call, call_pot, call_stack, n_flops, hero_player);
    eprintln!();

    // Solve 4BET-CALLED branch
    let fourbet_actions: Vec<(String, f64)> = scenario.actions.iter()
        .filter(|a| {
            let l = a.to_lowercase();
            l.contains("4bet") && !l.contains("all")
        })
        .map(|a| {
            let s = a.to_lowercase();
            let num: f64 = s.split_whitespace().last()
                .and_then(|x| x.replace("bb","").parse().ok())
                .unwrap_or(20.0);
            (a.clone(), num)
        })
        .collect();

    let mut fourbet_evs: HashMap<String, HashMap<usize, f32>> = HashMap::new();
    for (name, size) in &fourbet_actions {
        eprint!("  {} branch: ", name);
        let pot = size * 2.0 + dead_blinds;
        let stack = 100.0 - size;
        let (oop_4b, ip_4b) = if hero_is_ip {
            (villain_call_4bet, hero_4bet)
        } else {
            (hero_4bet, villain_call_4bet)
        };
        let evs = avg_postflop_ev(oop_4b, ip_4b, pot, stack, n_flops, hero_player);
        eprintln!();
        fourbet_evs.insert(name.clone(), evs);
    }

    // All-in branch: solve with tiny stack to compute pure equity
    // Villain calls all-in tighter than calling a 4bet
    let villain_call_allin = "QQ+,AKs,AKo";
    let ft_allin: f64 = 0.55; // Slightly higher fold rate vs all-in
    eprint!("  All-in equity branch: ");
    let allin_pot = 200.0 + dead_blinds; // Both players put in 100bb + dead blinds
    let allin_stack = 0.5; // Tiny stack = effectively all-in (equity only)
    let (oop_ai, ip_ai) = if hero_is_ip {
        (villain_call_allin, hero_4bet)
    } else {
        (hero_4bet, villain_call_allin)
    };
    let allin_evs = avg_postflop_ev(oop_ai, ip_ai, allin_pot, allin_stack, n_flops, hero_player);
    eprintln!();

    let range_call: Range = hero_call_range.parse().unwrap();
    let range_4bet: Range = hero_4bet.parse().unwrap();
    let blind_posted: f64 = match hero_pos.as_str() {
        "BB" => 1.0, "SB" => 0.5, _ => 0.0,
    };
    let all = all_169_hands();
    let mut result = HashMap::new();

    for hand in &all {
        let mut evs = HashMap::new();
        for action in &scenario.actions {
            let lower = action.to_lowercase();
            if lower == "fold" {
                // Hero loses their open raise
                let open_cost = open_size - blind_posted;
                evs.insert(action.clone(), -open_cost);
            } else if lower == "call" {
                let add_cost = threeb_size - blind_posted;
                let call_pot = threeb_size * 2.0 + dead_blinds;
                let oor_fallback = -(call_pot * 0.4 + add_cost * 0.4);
                let ev = hand_class_ev(&range_call, hand, &call_evs)
                    .map(|pf_ev| pf_ev - add_cost)
                    .unwrap_or(oor_fallback);
                evs.insert(action.clone(), ev);
            } else if lower.contains("4bet") {
                let size: f64 = lower.split_whitespace().last()
                    .and_then(|x| x.replace("bb","").parse().ok())
                    .unwrap_or(20.0);
                let add_cost = size - blind_posted;
                let dead = threeb_size + dead_blinds;
                let fourbet_pot = size * 2.0 + dead_blinds;
                let oor_fallback = -(fourbet_pot * 0.3 + add_cost * 0.3);

                // Use hero's 4bet range for EV lookup (not full opening range)
                let called_net = fourbet_evs.get(action)
                    .and_then(|ev_map| hand_class_ev(&range_4bet, hand, ev_map))
                    .map(|pf_ev| pf_ev - add_cost)
                    .unwrap_or(oor_fallback);

                let fold_profit = dead - open_size + blind_posted;
                let five_bet_loss = -(size - blind_posted); // hero folds to villain 5bet
                let ev = ft4b_fold * fold_profit + ft4b_call * called_net + ft4b_5bet * five_bet_loss;
                evs.insert(action.clone(), ev);
            } else if lower.contains("all") {
                // All-in shove: hero goes all-in for 100bb
                // When villain folds: hero wins dead money
                // When villain calls: pure equity battle (solver with tiny stack)
                let add_cost = 100.0 - blind_posted;
                let dead = threeb_size + dead_blinds - (open_size - blind_posted);
                let allin_pot_total = 200.0 + dead_blinds;
                let oor_fallback = -(allin_pot_total * 0.35);

                // Use hero's 4bet range for EV lookup
                let called_net = hand_class_ev(&range_4bet, hand, &allin_evs)
                    .map(|pf_ev| pf_ev - add_cost)
                    .unwrap_or(oor_fallback);

                let ev = ft_allin * dead + (1.0 - ft_allin) * called_net;
                evs.insert(action.clone(), ev);
            }
        }
        result.insert(hand.clone(), evs);
    }
    result
}

/// squeeze: Hero in BB, villain opened, someone called. Hero can squeeze.
fn compute_squeeze(scenario: &Scenario, n_flops: usize) -> HashMap<String, HashMap<String, f64>> {
    // Treat squeeze similarly to vs_open but with bigger dead money
    compute_vs_open(scenario, n_flops)
}

/// vs_limp: Someone limped, hero decides to raise or check/limp behind.
fn compute_vs_limp(scenario: &Scenario, n_flops: usize) -> HashMap<String, HashMap<String, f64>> {
    let hero_pos = &scenario.hero_position;
    let hero_range = get_opening_range(hero_pos);
    let limper_range = "22+,A2s+,K2s+,Q2s+,J5s+,T6s+,96s+,86s+,76s,65s,54s,A2o+,K5o+,Q7o+,J8o+,T8o+,98o";
    let blinds = 1.5f64;

    let hero_is_ip = hero_pos == "BB"; // BB is IP vs SB limp; SB is OOP
    let hero_player = if hero_is_ip { 1usize } else { 0usize };

    // Limp pot: limper put 1bb (or called 0.5bb more if SB), plus blinds
    let limp_cost = 1.0f64;
    let fold_to_raise = 0.50f64;

    let raise_actions: Vec<(String, f64)> = scenario.actions.iter()
        .filter(|a| a.to_lowercase().starts_with("raise"))
        .map(|a| {
            let s = a.to_lowercase().replace("raise","");
            let num: f64 = s.trim().replace("bb","").parse().unwrap_or(4.0);
            (a.clone(), num)
        })
        .collect();

    let mut raise_evs: HashMap<String, HashMap<usize, f32>> = HashMap::new();
    for (name, size) in &raise_actions {
        eprint!("  {} branch: ", name);
        let pot = size + limp_cost + blinds;
        let stack = 100.0 - size;
        let (oop, ip) = if hero_is_ip {
            (limper_range, hero_range)
        } else {
            (hero_range, limper_range)
        };
        let evs = avg_postflop_ev(oop, ip, pot, stack, n_flops, hero_player);
        eprintln!();
        raise_evs.insert(name.clone(), evs);
    }

    // Solve limp/check behind postflop
    eprint!("  Check/Limp branch: ");
    let limp_pot = limp_cost + blinds;
    let limp_stack = 100.0 - limp_cost;
    let (oop_l, ip_l) = if hero_is_ip {
        (limper_range, hero_range)
    } else {
        (hero_range, limper_range)
    };
    let limp_evs = avg_postflop_ev(oop_l, ip_l, limp_pot, limp_stack, n_flops, hero_player);
    eprintln!();

    let hero_parsed: Range = hero_range.parse().unwrap();
    let blind_posted: f64 = match hero_pos.as_str() {
        "BB" => 1.0, "SB" => 0.5, _ => 0.0,
    };
    let all = all_169_hands();
    let mut result = HashMap::new();

    for hand in &all {
        let mut evs = HashMap::new();
        for action in &scenario.actions {
            let lower = action.to_lowercase();
            if lower == "fold" {
                evs.insert(action.clone(), 0.0);
            } else if lower == "check" || lower == "limp behind" {
                let add_cost = if lower == "check" { 0.0 } else { limp_cost - blind_posted };
                let ev = hand_class_ev(&hero_parsed, hand, &limp_evs)
                    .map(|pf_ev| pf_ev - add_cost)
                    .unwrap_or(-add_cost.max(0.1));
                evs.insert(action.clone(), ev);
            } else if lower.starts_with("raise") {
                let size: f64 = lower.replace("raise","").trim()
                    .replace("bb","").parse().unwrap_or(4.0);
                let add_cost = size - blind_posted;
                let dead = limp_cost + blinds - blind_posted;

                let raise_pot = size + limp_cost + blinds;
                let oor_fallback = -(raise_pot * 0.4 + add_cost * 0.6);
                let called_net = if let Some(ev_map) = raise_evs.get(action) {
                    hand_class_ev(&hero_parsed, hand, ev_map)
                        .map(|pf_ev| pf_ev - add_cost)
                        .unwrap_or(oor_fallback)
                } else { oor_fallback };

                let ev = fold_to_raise * dead + (1.0 - fold_to_raise) * called_net;
                evs.insert(action.clone(), ev);
            }
        }
        result.insert(hand.clone(), evs);
    }
    result
}

fn compute_ev_vs_best(raw: &HashMap<String, f64>) -> HashMap<String, f64> {
    let best = raw.values().cloned().fold(f64::NEG_INFINITY, f64::max);
    raw.iter().map(|(k, v)| (k.clone(), ((*v - best) * 10000.0).round() / 10000.0)).collect()
}

fn compute_ev_normalized(evb: &HashMap<String, f64>) -> HashMap<String, f64> {
    let vals: Vec<f64> = evb.values().cloned().collect();
    let avg = vals.iter().sum::<f64>() / vals.len() as f64;
    evb.iter().map(|(k, v)| (k.clone(), ((*v - avg) * 10000.0).round() / 10000.0)).collect()
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).parent().unwrap();
    let scenarios_json = fs::read_to_string(root.join("data/scenarios.json")).unwrap();
    let scenarios: Vec<Scenario> = serde_json::from_str(&scenarios_json).unwrap();
    let ev_dir = root.join("data/ev_tables");
    fs::create_dir_all(&ev_dir).ok();

    let filter_id = args.get(1).map(String::as_str);
    let n_flops: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(200);

    for sc in &scenarios {
        if let Some(id) = filter_id { if sc.id != id { continue; } }

        eprintln!("\n=== {} ({}) ===", sc.id, sc.name);
        let t0 = std::time::Instant::now();

        let raw_evs = match sc.scenario_type.as_str() {
            "rfi" => compute_rfi(sc, n_flops),
            "vs_open" => compute_vs_open(sc, n_flops),
            "vs_3bet" => compute_vs_3bet(sc, n_flops),
            "squeeze" => compute_squeeze(sc, n_flops),
            "vs_limp" => compute_vs_limp(sc, n_flops),
            _ => compute_vs_open(sc, n_flops),
        };

        let mut hands = HashMap::new();
        for (h, evs) in &raw_evs {
            let evb = compute_ev_vs_best(evs);
            let evn = compute_ev_normalized(&evb);
            let best = evb.iter().max_by(|a,b| a.1.partial_cmp(b.1).unwrap())
                .map(|(k,_)| k.clone()).unwrap_or_default();
            let mut strat: HashMap<String, f64> = evs.keys().map(|k| (k.clone(), 0.0)).collect();
            strat.insert(best, 1.0);
            hands.insert(h.clone(), HandData { strategy: strat, ev_vs_best: evb, ev_normalized: evn });
        }

        let table = EvTable {
            scenario_id: sc.id.clone(),
            source: format!("postflop-solver DCFR × {} flops", n_flops),
            hands,
        };

        let path = ev_dir.join(format!("{}.json", sc.id));
        fs::write(&path, serde_json::to_string_pretty(&table).unwrap()).unwrap();
        eprintln!("  {} hands, {:.1}s -> {}", table.hands.len(), t0.elapsed().as_secs_f64(), path.display());
    }
    eprintln!("\nDone!");
}
