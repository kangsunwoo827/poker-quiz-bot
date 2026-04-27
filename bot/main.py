#!/usr/bin/env python3
"""Open Range Quiz Telegram Bot."""
import json
import logging
import random
from collections import deque
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN
from quiz import (
    QuizManager, OpenRangeQuizManager, OPEN_RANGE_POSITIONS,
    QuizQuestion, OpenRangeQuestion,
)


# Players left to act after hero opens (varies by format)
PLAYERS_LEFT = {
    "UTG": 5, "UTG+1": 4, "MP": 4, "LJ": 3, "HJ": 3, "CO": 3, "BTN": 2, "SB": 1,
}

# Who is left to act (by name)
PLAYERS_AFTER = {
    "UTG": "MP, CO, BTN, SB, BB",
    "UTG+1": "MP, CO, BTN, SB, BB",
    "MP": "CO, BTN, SB, BB",
    "LJ": "HJ, CO, BTN, SB, BB",
    "HJ": "CO, BTN, SB, BB",
    "CO": "BTN, SB, BB",
    "BTN": "SB, BB",
    "SB": "BB",
}

FORMAT_META = {
    "6max_100bb_highRake": {"game": "6-max Cash", "stack": "100bb", "rake": "Rake 5% (max 2.5bb/hand)"},
    "6max_100bb":          {"game": "6-max Cash", "stack": "100bb", "rake": "Rake 5% (max 1bb/hand)"},
    "6max_40bb":           {"game": "6-max Cash", "stack": "40bb",  "rake": "Rake 5% (max 1bb/hand)"},
    "6max_200bb":          {"game": "6-max Cash", "stack": "200bb", "rake": "Rake 5% (max 1bb/hand)"},
    "9max_100bb":          {"game": "9-max Live Casino", "stack": "100bb", "rake": "Rake varies by venue"},
    "mtt_100bb":           {"game": "MTT 8-max",  "stack": "100bb", "rake": "0.125bb ante"},
    "mtt_60bb":            {"game": "MTT 8-max",  "stack": "60bb",  "rake": "0.125bb ante"},
    "mtt_50bb":            {"game": "MTT 8-max",  "stack": "50bb",  "rake": "0.125bb ante"},
    "mtt_40bb":            {"game": "MTT 8-max",  "stack": "40bb",  "rake": "0.125bb ante"},
    "mtt_30bb":            {"game": "MTT 8-max",  "stack": "30bb",  "rake": "0.125bb ante"},
    "mtt_20bb":            {"game": "MTT 8-max",  "stack": "20bb",  "rake": "0.125bb ante"},
    "mtt_10bb":            {"game": "MTT 8-max",  "stack": "10bb",  "rake": "0.125bb ante"},
}
from bankroll import BankrollManager
from chart import generate_open_range_chart, combine_with_crop
from config import DATA_DIR
from persistence import load_state, save_state


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

quiz_manager = QuizManager()
open_range_quiz = OpenRangeQuizManager(quiz_manager.ev_tables)
_available_formats = open_range_quiz.get_available_formats()
logger.info(f"Loaded formats: {_available_formats}")
bankroll_manager = BankrollManager()
CROPS_DIR = DATA_DIR / "crops"

# Verified format/position combos (range editor pages 1-26)
VERIFIED_SLOTS = [
    ("6max_100bb_highRake", "UTG"), ("6max_100bb_highRake", "MP"),
    ("6max_100bb_highRake", "CO"), ("6max_100bb_highRake", "BTN"),
    ("6max_100bb_highRake", "SB"),
    ("6max_100bb", "UTG"), ("6max_100bb", "MP"),
    ("6max_100bb", "CO"), ("6max_100bb", "BTN"),
    ("6max_100bb", "SB"),
    ("6max_40bb", "UTG"), ("6max_40bb", "MP"),
    ("6max_40bb", "CO"), ("6max_40bb", "BTN"),
    ("6max_40bb", "SB"),
    ("6max_200bb", "UTG"), ("6max_200bb", "MP"),
    ("6max_200bb", "CO"), ("6max_200bb", "BTN"),
    ("6max_200bb", "SB"),
    ("9max_100bb", "UTG"), ("9max_100bb", "UTG+1"),
    ("9max_100bb", "MP"), ("9max_100bb", "LJ"),
    ("9max_100bb", "HJ"), ("9max_100bb", "CO"),
]
VERIFIED_SET = set(VERIFIED_SLOTS)

# Bankroll scoring: symmetric random 1-5bb, mixed half (0.5-2.5bb)
BB_MIN, BB_MAX = 1.0, 5.0
BB_MIXED_MIN, BB_MIXED_MAX = 0.5, 2.5

_state = load_state()
active_chats: set[int] = set(_state.get("active_chats", []))
subscribed_chats: set[int] = set(_state.get("subscribed_chats", []))

# Auto-broadcast interval (seconds). Override via env BROADCAST_INTERVAL_SEC.
import os
BROADCAST_INTERVAL_SEC = int(os.getenv("BROADCAST_INTERVAL_SEC", "3600"))

# Per-user pending quiz
pending_quizzes: dict[int, object] = {}

# Per-user recent hands: deque of (position, hand) tuples
user_recent: dict[int, deque] = {}

# Per-user recent scenarios: deque of (scenario_id, hand) tuples for QuizManager weighting
user_recent_scenarios: dict[int, deque] = {}

RECENT_LIMIT = 50

# Narrative scenario routing
SCENARIO_POOL: list[str] = sorted(quiz_manager.get_available_scenarios())
SCENARIO_RATIO = 1.0  # always pick narrative scenario unless RFI hint (fmt/pos) given

ACTION_EMOJI = {
    "fold":  "❌ 폴드",
    "limp":  "🟢 림프",
    "call":  "🟡 콜",
    "raise": "🔴 레이즈",
    "3bet":  "🔴 3벳",
    "4bet":  "🔴 4벳",
    "check": "✅ 체크",
}


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _get_recent_set(user_id: int, position: str) -> set:
    """Return hands recently seen by this user for the given position."""
    recent = user_recent.get(user_id, deque())
    return {hand for pos, hand in recent if pos == position}


def _record_recent(user_id: int, position: str, hand: str):
    if user_id not in user_recent:
        user_recent[user_id] = deque(maxlen=RECENT_LIMIT)
    user_recent[user_id].append((position, hand))


def _build_quiz_message(question) -> tuple[str, InlineKeyboardMarkup]:
    pos  = question.position
    hand = escape_html(question.hand_display)
    fkey = question.format_key
    left = PLAYERS_LEFT.get(pos, "?")
    after = PLAYERS_AFTER.get(pos, "")

    has_allin = bool(question.allin_hands)
    has_call  = bool(question.call_hands)
    has_raise = bool(question.raise_hands)

    meta = FORMAT_META.get(fkey, {"game": fkey, "stack": "?", "rake": "?"})
    bnd_tag = "  ◆ boundary" if question.is_boundary else ""

    # Title
    if has_allin and not has_raise:
        title = f"Push or Fold — {pos}"
    elif has_allin:
        title = f"Open Raise — {pos}"
    else:
        title = f"Open Raise — {pos}"

    # Format line
    fmt_line = f"{meta['game']} | Stack {meta['stack']} | {meta['rake']}"

    # Situation
    situation = f"Everyone folds to Hero on <b>{pos}</b>.\n{left} players left to act ({after})."

    text = (
        f"<b>{title}</b>{bnd_tag}\n\n"
        f"<code>{fmt_line}</code>\n"
        f"{situation}\n\n"
        f"Your hand:  <b>{hand}</b>\n\n"
    )

    # Build buttons based on available actions
    buttons = []
    if has_allin:
        buttons.append(InlineKeyboardButton("Push", callback_data=f"rfi:{fkey}:{pos}:{question.hand}:P"))
    if has_raise:
        buttons.append(InlineKeyboardButton("Raise", callback_data=f"rfi:{fkey}:{pos}:{question.hand}:O"))
    if has_call:
        buttons.append(InlineKeyboardButton("Call", callback_data=f"rfi:{fkey}:{pos}:{question.hand}:C"))
    buttons.append(InlineKeyboardButton("Fold", callback_data=f"rfi:{fkey}:{pos}:{question.hand}:F"))

    labels = [b.text for b in buttons]
    if len(labels) == 2:
        text += f"{labels[0]} or {labels[1]}?"
    else:
        text += ", ".join(labels[:-1]) + f", or {labels[-1]}?"

    keyboard = InlineKeyboardMarkup([buttons])
    return text, keyboard


def _format_key_for_scenario(scenario) -> str:
    """Map a scenario's stack/format hint to FORMAT_META key. Currently 6-max 100bb only."""
    return "6max_100bb"


def _format_action_step(step: dict, hero_position: str) -> str:
    """Render one action_sequence step as a single narrative line."""
    pos = step["position"]
    verb = ACTION_EMOJI.get(step["action"], step["action"])
    amt = f" ({step['amount_bb']}bb)" if "amount_bb" in step else ""
    if step.get("hero"):
        return f"<b>{pos}</b> {verb}{amt}  ← 너"
    return f"{pos} {verb}{amt}"


def _scenario_action_emoji(action_label: str) -> str:
    """Pick a small emoji prefix for action button labels."""
    a = action_label.lower()
    if a.startswith("fold"):
        return "❌"
    if a.startswith("check"):
        return "✅"
    if a.startswith("call"):
        return "🟡"
    if a.startswith("limp"):
        return "🟢"
    if "all-in" in a or "allin" in a or a.startswith("push") or a.startswith("shove"):
        return "💥"
    return "🔴"


def _build_scenario_message(question: QuizQuestion) -> tuple[str, InlineKeyboardMarkup]:
    """Build narrative-style preflop scenario message (action-by-action)."""
    sc = question.scenario
    fkey = _format_key_for_scenario(sc)
    meta = FORMAT_META.get(fkey, {"game": "6-max", "stack": "100bb", "rake": ""})
    hand = escape_html(question.hand_display)

    header = f"<b>{escape_html(sc.name)}</b>"
    fmt_line = f"<code>{meta['game']} | Stack {meta['stack']} | {meta['rake']}</code>"

    if sc.action_sequence:
        action_lines = "\n".join(
            _format_action_step(step, sc.hero_position) for step in sc.action_sequence
        )
    else:
        action_lines = "<i>모두 폴드, 너에게 액션이 왔다.</i>"

    text = (
        f"{header}\n"
        f"{fmt_line}\n\n"
        f"{action_lines}\n\n"
        f"👉 너는 <b>{sc.hero_position}</b>. 손패: <b>{hand}</b>\n"
    )

    buttons = []
    for i, label in enumerate(sc.actions):
        emoji = _scenario_action_emoji(label)
        buttons.append(
            InlineKeyboardButton(
                f"{emoji} {label}",
                callback_data=f"sc:{sc.id}:{question.hand}:{i}",
            )
        )
    # Telegram inline buttons: split into rows of 2 if > 3 actions
    if len(buttons) > 3:
        keyboard = InlineKeyboardMarkup([buttons[:2], buttons[2:]])
    else:
        keyboard = InlineKeyboardMarkup([buttons])
    return text, keyboard


def _record_recent_scenario(user_id: int, scenario_id: str, hand: str):
    if user_id not in user_recent_scenarios:
        user_recent_scenarios[user_id] = deque(maxlen=RECENT_LIMIT)
    user_recent_scenarios[user_id].append((scenario_id, hand))


def _scenario_recent_history(user_id: int) -> list[tuple]:
    return list(user_recent_scenarios.get(user_id, deque()))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)

    active_chats.add(chat_id)
    save_state(active_chats, subscribed_chats)
    bankroll_manager.get_or_create_user(user_id, username)

    await update.message.reply_text(
        "<b>Open Range Quiz Trainer</b>\n\n"
        "Memorise GTO preflop open ranges (6-max, 100bb).\n"
        "Boundary hands are asked most often.\n\n"
        "<b>Commands:</b>\n"
        "/quiz (/q) — Get a quiz\n"
        "/stats — Your stats & ranking\n"
        "/ranking — Leaderboard\n"
        "/help — How to play",
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Open Range Quiz — How to Play</b>\n\n"
        "Each question shows your position, stack, rake, and hand.\n"
        "Decide: <b>Raise</b>, <b>Call</b>, or <b>Fold</b>.\n\n"
        "<b>Scoring (start 100bb):</b>\n"
        "✅ Correct: <b>+1~5bb</b> (random)\n"
        "❌ Wrong: <b>-1~5bb</b> (random)\n"
        "🔀 Mixed: <b>+0.5~2.5bb</b> (half reward)\n\n"
        "<b>Boundary hands</b> ◆ — hands next to the range edge "
        "(adjacent to a different action on the chart). "
        "These appear more often.\n\n"
        "After each answer you see the range chart + PDF reference.\n\n"
        "<b>Commands:</b>\n"
        "/quiz (/q) — Get a quiz\n"
        "/stats — Bankroll, accuracy, ranking\n"
        "/ranking — Leaderboard",
        parse_mode=ParseMode.HTML,
    )


async def _send_scenario_quiz_message(send_target, user_id: int, scenario_id: str) -> bool:
    """Generate a narrative scenario question and send it. Returns True on success."""
    question = quiz_manager.generate_question(
        recent_history=_scenario_recent_history(user_id),
        scenario_id=scenario_id,
    )
    if question is None:
        return False
    pending_quizzes[user_id] = question
    text, keyboard = _build_scenario_message(question)
    if hasattr(send_target, "edit_message_text"):
        await send_target.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        await send_target.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    return True


async def _send_rfi_quiz_message(send_target, user_id: int, fmt_arg: str, pos_arg: str):
    question = open_range_quiz.generate_question(
        format_key=fmt_arg,
        position=pos_arg,
        recent=_get_recent_set(user_id, pos_arg or ""),
    )
    pending_quizzes[user_id] = question
    text, keyboard = _build_quiz_message(question)
    if hasattr(send_target, "edit_message_text"):
        await send_target.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    else:
        await send_target.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)
    chat_id = update.effective_chat.id

    active_chats.add(chat_id)
    save_state(active_chats, subscribed_chats)
    bankroll_manager.get_or_create_user(user_id, username)

    # Parse optional args:
    #   /quiz utg | /quiz 100bb utg            → RFI route
    #   /quiz scenario | /quiz story           → force narrative scenario route
    #   /quiz <scenario_id>                    → force a specific scenario (e.g. /quiz sb_vs_limp)
    pos_arg = None
    fmt_arg = None
    forced_scenario_id = None
    force_scenario_mode = False
    if context.args:
        for arg in context.args:
            a_upper = arg.upper()
            if a_upper in OPEN_RANGE_POSITIONS:
                pos_arg = a_upper
                continue
            fmt_match = next((f for f in open_range_quiz.FORMATS if f.upper() == a_upper), None)
            if fmt_match:
                fmt_arg = fmt_match
                continue
            if arg.lower() in {"scenario", "story", "narrative", "rfi"}:
                if arg.lower() == "rfi":
                    force_scenario_mode = False
                    pos_arg = pos_arg or None
                else:
                    force_scenario_mode = True
                continue
            if arg in quiz_manager.scenarios:
                forced_scenario_id = arg
                continue

    # Route: explicit scenario id > forced scenario mode > 50/50 random > RFI
    if forced_scenario_id and forced_scenario_id in SCENARIO_POOL:
        if await _send_scenario_quiz_message(update.message, user_id, forced_scenario_id):
            return

    no_rfi_hint = pos_arg is None and fmt_arg is None
    if (force_scenario_mode or (no_rfi_hint and random.random() < SCENARIO_RATIO)) and SCENARIO_POOL:
        scenario_id = random.choice(SCENARIO_POOL)
        if await _send_scenario_quiz_message(update.message, user_id, scenario_id):
            return

    # RFI fallback
    if not fmt_arg and not pos_arg:
        fmt_arg, pos_arg = random.choice(VERIFIED_SLOTS)
    elif fmt_arg and not pos_arg:
        candidates = [p for f, p in VERIFIED_SLOTS if f == fmt_arg]
        pos_arg = random.choice(candidates) if candidates else None

    await _send_rfi_quiz_message(update.message, user_id, fmt_arg, pos_arg)


async def handle_open_range_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or str(user_id)

    # Parse: rfi:{fmt}:{pos}:{hand}:{O|P|C|F}
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Invalid data.", show_alert=True)
        return

    _, fmt, pos, hand, action_code = parts
    chosen = {"O": "Open", "P": "Push", "C": "Call", "F": "Fold"}.get(action_code, "Fold")

    question = pending_quizzes.get(user_id)
    if (not isinstance(question, OpenRangeQuestion)
            or question.position != pos or question.hand != hand):
        await query.answer("Quiz expired — use /quiz for a new one.", show_alert=True)
        return

    correct = question.correct_action
    is_mixed = hand in question.mixed_hands
    was_correct = chosen == correct or is_mixed

    # Bankroll scoring (random 1-5bb, mixed 0.5-2.5bb)
    prev_br = bankroll_manager.get_or_create_user(user_id, username)["bankroll"]

    if is_mixed:
        bb_change = round(random.uniform(BB_MIXED_MIN, BB_MIXED_MAX), 1)
    elif was_correct:
        bb_change = round(random.uniform(BB_MIN, BB_MAX), 1)
    else:
        bb_change = -round(random.uniform(BB_MIN, BB_MAX), 1)

    br = bankroll_manager.record_answer(
        user_id=user_id, username=username,
        scenario_id=f"{fmt}:{pos}", hand=hand,
        chosen_action=chosen, chosen_ev_normalized=bb_change,
        best_action=correct, ev_vs_best=0.0 if was_correct else bb_change,
        was_correct=was_correct,
    )

    _record_recent(user_id, pos, hand)
    pending_quizzes.pop(user_id, None)

    accuracy = br["correct_count"] / br["total_questions"] * 100 if br["total_questions"] else 0

    icon = "✅" if was_correct else "❌"
    if is_mixed:
        icon = "🔀"
    h_disp = escape_html(question.hand_display)
    bnd_tag = "  ◆ boundary" if question.is_boundary else ""

    action_labels = {
        "Open": "open-raise", "Push": "push all-in",
        "Call": "call/limp", "Fold": "fold",
    }
    if is_mixed:
        verdict = f"<b>{h_disp}</b> is mixed on {pos} — both raise and fold are OK."
    elif was_correct:
        verdict = f"Correct! <b>{h_disp}</b> is an {action_labels[correct]} on {pos}."
    else:
        verdict = f"Wrong. <b>{h_disp}</b> should {action_labels[correct]} on {pos}."

    # Format meta + range breakdown
    meta = FORMAT_META.get(fmt, {"game": fmt, "stack": "?", "rake": "?"})
    fmt_line = f"{meta['game']} | Stack {meta['stack']} | {meta['rake']}"
    pcts = getattr(question, "range_pcts", {})
    pct_parts = []
    if pcts.get("raise"):
        pct_parts.append(f"Raise {pcts['raise']}%")
    if pcts.get("allin"):
        pct_parts.append(f"Push {pcts['allin']}%")
    if pcts.get("call"):
        pct_parts.append(f"Call {pcts['call']}%")
    if pcts.get("fold"):
        pct_parts.append(f"Fold {pcts['fold']}%")
    pct_line = " · ".join(pct_parts)
    mixed_line = f"\n(Mixed: {pcts['mixed_count']} hands)" if pcts.get("mixed_count") else ""

    bb_sign = "+" if bb_change >= 0 else ""
    bankroll = br["bankroll"]
    streak = br["streak"]
    streak_txt = f"  🔥{streak}" if streak >= 3 else ""
    rank, total_players = bankroll_manager.get_rank(user_id)
    rank_txt = f"#{rank}/{total_players}" if total_players > 1 else ""

    result_text = (
        f"{icon} <b>{escape_html(pos)} — {h_disp}</b>{bnd_tag}\n\n"
        f"{verdict}\n\n"
        f"<code>{fmt_line}</code>\n"
        f"{pct_line}{mixed_line}"
    )

    await query.answer("✅ Correct!" if was_correct else "❌ Wrong")
    await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)

    # Send range chart + PDF crop side-by-side
    try:
        has_allin = bool(question.allin_hands)
        chart_title = f"{pos} {'Push/Fold' if has_allin else 'Open Raise'} ({meta['game']} {meta['stack']})"
        chart_bytes = generate_open_range_chart(
            in_range_hands=question.raise_hands,
            allin_hands=question.allin_hands,
            call_hands=question.call_hands,
            mixed_hands=question.mixed_pcts,
            highlight_hand=hand,
            title=chart_title,
        )
        crop_path = str(CROPS_DIR / f"{fmt}_rfi_{pos}.png")
        combined = combine_with_crop(chart_bytes, crop_path)
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=BytesIO(combined),
            caption=(
                f"{icon} {pos} — {hand}  {bb_sign}{bb_change:.1f}bb\n"
                f"Bankroll: {prev_br:.1f} → {bankroll:.1f}bb  {rank_txt}{streak_txt}\n"
                f"Total: {br['correct_count']}/{br['total_questions']} ({accuracy:.0f}%)"
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to send range chart: {e}")

    # Next + Fix buttons
    keyboard = [[
        InlineKeyboardButton("➡️ Next", callback_data=f"next:{fmt}:{pos}"),
        InlineKeyboardButton("Fix", callback_data=f"fix:{fmt}:{pos}:{hand}"),
    ]]
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Ready?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_scenario_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle answer for narrative scenario quizzes. Callback: sc:{scenario_id}:{hand}:{action_index}"""
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or str(user_id)

    parts = query.data.split(":", 3)
    if len(parts) != 4:
        await query.answer("Invalid data.", show_alert=True)
        return
    _, scenario_id, hand, idx_str = parts
    try:
        action_idx = int(idx_str)
    except ValueError:
        await query.answer("Invalid action.", show_alert=True)
        return

    question = pending_quizzes.get(user_id)
    if (not isinstance(question, QuizQuestion)
            or question.scenario.id != scenario_id
            or question.hand != hand):
        await query.answer("Quiz expired — use /quiz for a new one.", show_alert=True)
        return

    sc = question.scenario
    if not (0 <= action_idx < len(sc.actions)):
        await query.answer("Invalid action index.", show_alert=True)
        return
    chosen_label = sc.actions[action_idx]

    strategy = question.strategy or {}
    chosen_freq = strategy.get(chosen_label, 0.0)

    if chosen_freq >= 0.99:
        was_correct = True
        is_mixed = False
    elif chosen_freq > 0.0:
        was_correct = True
        is_mixed = True
    else:
        was_correct = False
        is_mixed = False

    prev_br = bankroll_manager.get_or_create_user(user_id, username)["bankroll"]
    if is_mixed:
        bb_change = round(random.uniform(BB_MIXED_MIN, BB_MIXED_MAX), 1)
    elif was_correct:
        bb_change = round(random.uniform(BB_MIN, BB_MAX), 1)
    else:
        bb_change = -round(random.uniform(BB_MIN, BB_MAX), 1)

    br = bankroll_manager.record_answer(
        user_id=user_id, username=username,
        scenario_id=sc.id, hand=hand,
        chosen_action=chosen_label, chosen_ev_normalized=bb_change,
        best_action=question.best_action,
        ev_vs_best=0.0 if was_correct else bb_change,
        was_correct=was_correct,
    )

    _record_recent_scenario(user_id, sc.id, hand)
    pending_quizzes.pop(user_id, None)

    accuracy = br["correct_count"] / br["total_questions"] * 100 if br["total_questions"] else 0
    icon = "🔀" if is_mixed else ("✅" if was_correct else "❌")
    h_disp = escape_html(question.hand_display)

    correct_actions = [a for a, f in strategy.items() if f > 0] or [question.best_action]
    correct_str = ", ".join(correct_actions)
    if is_mixed:
        verdict = f"<b>{h_disp}</b> 는 mixed — {escape_html(correct_str)} 모두 OK."
    elif was_correct:
        verdict = f"정답! <b>{h_disp}</b> 는 {escape_html(sc.hero_position)}에서 <b>{escape_html(chosen_label)}</b>."
    else:
        verdict = f"오답. <b>{h_disp}</b> 는 {escape_html(sc.hero_position)}에서 <b>{escape_html(correct_str)}</b> 가 정답."

    ev_vs_best = question.ev_vs_best or {}
    ev_lines = []
    for action, ev in sorted(ev_vs_best.items(), key=lambda kv: kv[1], reverse=True):
        freq = strategy.get(action, 0.0) * 100
        marker = " ◆" if action == chosen_label else ""
        ev_lines.append(f"  {action}: {ev:+.2f}bb ({freq:.0f}%){marker}")
    ev_block = "\n".join(ev_lines) if ev_lines else ""

    bb_sign = "+" if bb_change >= 0 else ""
    bankroll = br["bankroll"]
    streak = br["streak"]
    streak_txt = f"  🔥{streak}" if streak >= 3 else ""
    rank, total_players = bankroll_manager.get_rank(user_id)
    rank_txt = f"#{rank}/{total_players}" if total_players > 1 else ""

    parts_out = [
        f"{icon} <b>{escape_html(sc.name)} — {h_disp}</b>",
        "",
        verdict,
    ]
    if ev_block:
        parts_out += ["", f"<code>{ev_block}</code>"]
    parts_out += [
        "",
        f"{bb_sign}{bb_change:.1f}bb · Bankroll: {prev_br:.1f} → {bankroll:.1f}bb  {rank_txt}{streak_txt}",
        f"Total: {br['correct_count']}/{br['total_questions']} ({accuracy:.0f}%)",
    ]
    result_text = "\n".join(parts_out)

    await query.answer("✅ 정답" if was_correct else ("🔀 Mixed" if is_mixed else "❌ 오답"))
    await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)

    # Next button (no fmt/pos hint → 50/50 routing on next call)
    keyboard = [[InlineKeyboardButton("➡️ Next", callback_data="next:")]]
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="Ready?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def handle_next_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or str(user_id)

    bankroll_manager.get_or_create_user(user_id, username)

    # Parse: next: | next:{fmt}:{pos}
    parts = query.data.split(":")
    fmt_arg = parts[1] if len(parts) >= 2 and parts[1] else None
    pos_arg = parts[2] if len(parts) >= 3 and parts[2] in OPEN_RANGE_POSITIONS else None
    has_rfi_hint = bool(fmt_arg and pos_arg)

    # Route: 50/50 narrative scenario unless an RFI hint was passed
    if not has_rfi_hint and SCENARIO_POOL and random.random() < SCENARIO_RATIO:
        scenario_id = random.choice(SCENARIO_POOL)
        if await _send_scenario_quiz_message(query, user_id, scenario_id):
            return

    # RFI route
    if fmt_arg and (fmt_arg, pos_arg) in VERIFIED_SET:
        candidates = [p for f, p in VERIFIED_SLOTS if f == fmt_arg]
        pos_arg = random.choice(candidates) if candidates else pos_arg
    elif not fmt_arg or (fmt_arg, pos_arg) not in VERIFIED_SET:
        fmt_arg, pos_arg = random.choice(VERIFIED_SLOTS)

    await _send_rfi_quiz_message(query, user_id, fmt_arg, pos_arg)


async def handle_fix_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show fix options: what should this hand actually be?"""
    query = update.callback_query
    await query.answer()

    # fix:{fmt}:{pos}:{hand}
    parts = query.data.split(":")
    if len(parts) != 4:
        return
    _, fmt, pos, hand = parts

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Raise", callback_data=f"fixdo:{fmt}:{pos}:{hand}:R"),
        InlineKeyboardButton("Call",  callback_data=f"fixdo:{fmt}:{pos}:{hand}:C"),
        InlineKeyboardButton("Fold",  callback_data=f"fixdo:{fmt}:{pos}:{hand}:F"),
        InlineKeyboardButton("Mixed", callback_data=f"fixdo:{fmt}:{pos}:{hand}:M"),
    ]])
    await query.edit_message_text(
        f"<b>Fix {pos} — {escape_html(hand)}</b>\n\nCorrect action?",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )


async def handle_fix_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Apply the fix: update corrections.json + in-memory ranges."""
    query = update.callback_query

    # fixdo:{fmt}:{pos}:{hand}:{R|C|F}
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Invalid.", show_alert=True)
        return
    _, fmt, pos, hand, action_code = parts
    new_action = {"R": "raise", "C": "call", "F": "fold", "M": "mixed"}.get(action_code)
    if not new_action:
        await query.answer("Invalid.", show_alert=True)
        return

    # Determine current action from in-memory ranges
    range_data = open_range_quiz.ranges.get(fmt, {}).get(pos, {})
    if hand in range_data.get("raise", frozenset()):
        old_action = "raise"
    elif hand in range_data.get("call", frozenset()):
        old_action = "call"
    else:
        old_action = "fold"

    if old_action == new_action and new_action != "mixed":
        await query.answer(f"Already {new_action}.", show_alert=True)
        return

    # Update corrections.json
    corr_path = DATA_DIR / "corrections.json"
    if corr_path.exists():
        with open(corr_path, encoding="utf-8") as f:
            corrections = json.load(f)
    else:
        corrections = {}

    if fmt not in corrections:
        corrections[fmt] = {}
    if pos not in corrections[fmt]:
        corrections[fmt][pos] = {}
    c = corrections[fmt][pos]

    if new_action == "mixed":
        c.setdefault("mixed", [])
        if hand not in c["mixed"]:
            c["mixed"].append(hand)
    else:
        # Remove from mixed if present
        if "mixed" in c and hand in c["mixed"]:
            c["mixed"].remove(hand)

        if old_action == "raise":
            c.setdefault("raise_remove", [])
            if hand not in c["raise_remove"]:
                c["raise_remove"].append(hand)
            if "raise_add" in c and hand in c["raise_add"]:
                c["raise_add"].remove(hand)
        elif new_action == "raise":
            c.setdefault("raise_add", [])
            if hand not in c["raise_add"]:
                c["raise_add"].append(hand)
            if "raise_remove" in c and hand in c["raise_remove"]:
                c["raise_remove"].remove(hand)

        if old_action == "call":
            c.setdefault("call_remove", [])
            if hand not in c["call_remove"]:
                c["call_remove"].append(hand)
        elif new_action == "call":
            c.setdefault("call_add", [])
            if hand not in c["call_add"]:
                c["call_add"].append(hand)

    # Clean up empty lists
    for key in list(c.keys()):
        if isinstance(c[key], list) and not c[key]:
            del c[key]
    if not corrections[fmt][pos]:
        del corrections[fmt][pos]
    if not corrections[fmt]:
        del corrections[fmt]

    with open(corr_path, "w", encoding="utf-8") as f:
        json.dump(corrections, f, indent=2)

    # Update in-memory ranges
    raise_h = set(range_data.get("raise", frozenset()))
    call_h  = set(range_data.get("call", frozenset()))
    mixed_h = set(range_data.get("mixed", frozenset()))

    if new_action == "mixed":
        mixed_h.add(hand)
    else:
        mixed_h.discard(hand)
        if old_action == "raise":
            raise_h.discard(hand)
        if old_action == "call":
            call_h.discard(hand)
        if new_action == "raise":
            raise_h.add(hand)
        if new_action == "call":
            call_h.add(hand)

    open_range_quiz.ranges[fmt][pos] = {
        "raise": frozenset(raise_h),
        "call": frozenset(call_h),
        "mixed": frozenset(mixed_h),
    }

    await query.answer(f"Fixed: {hand} → {new_action}")
    await query.edit_message_text(
        f"Fixed <b>{pos} {escape_html(hand)}</b>: {old_action} → {new_action}",
        parse_mode=ParseMode.HTML,
    )


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Opt in to hourly auto-quiz delivery (private chats only)."""
    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_text(
            "구독은 1:1(갠톡)에서만 사용할 수 있어. 봇과의 개인 대화에서 /subscribe 해줘."
        )
        return

    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)
    chat_id = chat.id

    active_chats.add(chat_id)
    subscribed_chats.add(chat_id)
    save_state(active_chats, subscribed_chats)
    bankroll_manager.get_or_create_user(user_id, username)

    interval_min = BROADCAST_INTERVAL_SEC // 60
    await update.message.reply_text(
        f"✅ 구독 완료! {interval_min}분마다 한 문제씩 보내줄게.\n"
        f"중단하려면 /unsubscribe."
    )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in subscribed_chats:
        subscribed_chats.discard(chat_id)
        save_state(active_chats, subscribed_chats)
        await update.message.reply_text("⏹️ 구독 해제. 더 이상 자동 발송 안 함.")
    else:
        await update.message.reply_text("이미 구독 중이 아니야. /subscribe 로 시작 가능.")


async def sub_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    interval_min = BROADCAST_INTERVAL_SEC // 60
    if chat_id in subscribed_chats:
        await update.message.reply_text(
            f"🔔 구독 중 — {interval_min}분마다 자동 발송.\n해제: /unsubscribe"
        )
    else:
        await update.message.reply_text(
            f"🔕 미구독. /subscribe 로 {interval_min}분마다 한 문제씩 자동 받기."
        )


async def broadcast_quiz_job(context: ContextTypes.DEFAULT_TYPE):
    """Send a narrative scenario quiz to every subscribed private chat."""
    if not subscribed_chats:
        return
    targets = list(subscribed_chats)
    logger.info(f"Auto-broadcast quiz to {len(targets)} subscriber(s)")

    failed: list[int] = []
    for chat_id in targets:
        try:
            # In private chats, chat_id == user_id — pending_quizzes uses user_id
            user_id = chat_id

            # Skip if a quiz is already pending for this user (don't pile up)
            if user_id in pending_quizzes:
                continue

            if SCENARIO_POOL and random.random() < SCENARIO_RATIO:
                scenario_id = random.choice(SCENARIO_POOL)
                question = quiz_manager.generate_question(
                    recent_history=_scenario_recent_history(user_id),
                    scenario_id=scenario_id,
                )
                if question is None:
                    continue
                pending_quizzes[user_id] = question
                text, keyboard = _build_scenario_message(question)
            else:
                fmt_arg, pos_arg = random.choice(VERIFIED_SLOTS)
                question = open_range_quiz.generate_question(
                    format_key=fmt_arg, position=pos_arg,
                    recent=_get_recent_set(user_id, pos_arg or ""),
                )
                pending_quizzes[user_id] = question
                text, keyboard = _build_quiz_message(question)

            await context.bot.send_message(
                chat_id=chat_id, text=text,
                reply_markup=keyboard, parse_mode=ParseMode.HTML,
            )
        except Exception as e:
            logger.warning(f"Auto-broadcast failed for chat {chat_id}: {e}")
            # Telegram blocks: 403 → user blocked the bot. Auto-unsubscribe.
            if "Forbidden" in str(e) or "blocked" in str(e).lower():
                failed.append(chat_id)

    if failed:
        for cid in failed:
            subscribed_chats.discard(cid)
        save_state(active_chats, subscribed_chats)
        logger.info(f"Auto-unsubscribed blocked chats: {failed}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)

    db_stats = bankroll_manager.get_user_stats(user_id)
    if not db_stats or db_stats["total_questions"] == 0:
        await update.message.reply_text("No answers yet — use /quiz to start!")
        return

    acc = db_stats["accuracy"]
    br = db_stats["bankroll"]
    total = db_stats["total_questions"]
    correct = db_stats["correct_count"]
    streak = db_stats["streak"]
    best_streak = db_stats["best_streak"]
    best_br = db_stats["best_bankroll"]

    rank, total_players = bankroll_manager.get_rank(user_id)
    rank_txt = f"Rank: #{rank}/{total_players}\n" if total_players > 1 else ""
    streak_txt = f"  🔥{streak}" if streak >= 3 else ""
    await update.message.reply_text(
        f"<b>Stats</b>\n\n"
        f"Bankroll: <b>{br:.0f}bb</b> (peak {best_br:.0f}bb){streak_txt}\n"
        f"{rank_txt}"
        f"Correct: {correct}/{total} ({acc:.1f}%)\n"
        f"Best streak: {best_streak}",
        parse_mode=ParseMode.HTML,
    )


async def ranking_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    leaderboard = bankroll_manager.get_leaderboard(limit=10)
    if not leaderboard:
        await update.message.reply_text("No players yet — use /quiz to start!")
        return

    lines = ["<b>Leaderboard</b>\n"]
    medals = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}
    for i, entry in enumerate(leaderboard, 1):
        medal = medals.get(i, f"#{i}")
        name = escape_html(entry["username"] or "???")
        streak_txt = f" \U0001f525{entry['streak']}" if entry["streak"] >= 3 else ""
        lines.append(
            f"{medal} <b>{name}</b> — {entry['bankroll']:.0f}bb "
            f"({entry['accuracy']:.0f}%, {entry['total_questions']}Q){streak_txt}"
        )

    # Show caller's own rank if not in top 10
    top_ids = {e["user_id"] for e in leaderboard}
    if user_id not in top_ids:
        rank, total = bankroll_manager.get_rank(user_id)
        my_stats = bankroll_manager.get_user_stats(user_id)
        if my_stats and my_stats["total_questions"] > 0:
            lines.append(
                f"\n---\nYou: #{rank}/{total} — {my_stats['bankroll']:.0f}bb"
            )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)


async def post_init(application):
    commands = [
        BotCommand("quiz", "Open range quiz (add position: /quiz utg)"),
        BotCommand("q", "Open range quiz"),
        BotCommand("stats", "Your stats & ranking"),
        BotCommand("ranking", "Leaderboard"),
        BotCommand("subscribe", "1시간마다 한 문제씩 자동 받기"),
        BotCommand("unsubscribe", "자동 발송 해제"),
        BotCommand("sub_status", "자동 발송 구독 상태"),
        BotCommand("help", "How to play"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")

    if application.job_queue is not None:
        application.job_queue.run_repeating(
            broadcast_quiz_job,
            interval=BROADCAST_INTERVAL_SEC,
            first=BROADCAST_INTERVAL_SEC,  # first run after 1 interval, not at boot
            name="broadcast_quiz",
        )
        logger.info(f"Auto-broadcast scheduled every {BROADCAST_INTERVAL_SEC}s")
    else:
        logger.warning("JobQueue unavailable — auto-broadcast disabled")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("q", quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("ranking", ranking_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("sub", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("unsub", unsubscribe_command))
    application.add_handler(CommandHandler("sub_status", sub_status_command))
    application.add_handler(CallbackQueryHandler(handle_open_range_answer, pattern=r"^rfi:"))
    application.add_handler(CallbackQueryHandler(handle_scenario_answer, pattern=r"^sc:"))
    application.add_handler(CallbackQueryHandler(handle_next_quiz, pattern=r"^next:"))
    application.add_handler(CallbackQueryHandler(handle_fix_prompt, pattern=r"^fix:"))
    application.add_handler(CallbackQueryHandler(handle_fix_apply, pattern=r"^fixdo:"))
    application.add_error_handler(error_handler)

    logger.info("Starting Open Range Quiz Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
