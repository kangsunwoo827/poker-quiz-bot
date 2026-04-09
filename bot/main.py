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
from quiz import QuizManager, OpenRangeQuizManager, OPEN_RANGE_POSITIONS


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
    "6max_100bb_highRake": {"game": "6-max Cash", "stack": "100bb", "rake": "PS 100z (high rake)"},
    "6max_100bb":          {"game": "6-max Cash", "stack": "100bb", "rake": "PS 500z"},
    "6max_40bb":           {"game": "6-max Cash", "stack": "40bb",  "rake": "PS 500z"},
    "6max_200bb":          {"game": "6-max Cash", "stack": "200bb", "rake": "PS 500z"},
    "9max_100bb":          {"game": "9-max Cash", "stack": "100bb", "rake": "Live"},
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

# Per-user pending quiz
pending_quizzes: dict[int, object] = {}

# Per-user recent hands: deque of (position, hand) tuples
user_recent: dict[int, deque] = {}

# Per-user session accuracy
user_stats: dict[int, dict] = {}

RECENT_LIMIT = 50


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


def _init_stats(user_id: int):
    if user_id not in user_stats:
        user_stats[user_id] = {"correct": 0, "total": 0}


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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)

    active_chats.add(chat_id)
    save_state(active_chats)
    bankroll_manager.get_or_create_user(user_id, username)

    await update.message.reply_text(
        "<b>Open Range Quiz Trainer</b>\n\n"
        "Memorise GTO preflop open ranges (6-max, 100bb).\n"
        "Boundary hands are asked most often.\n\n"
        "<b>Commands:</b>\n"
        "/quiz (/q) — Get a quiz\n"
        "/stats — Your session accuracy\n"
        "/help — How to play",
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>Open Range Quiz — How to Play</b>\n\n"
        "Each question shows your position and hand.\n"
        "Decide: <b>Open</b> (raise 2.5bb) or <b>Fold</b>.\n\n"
        "<b>Positions:</b> UTG · MP · CO · BTN · SB\n\n"
        "<b>Boundary hands</b> (range edge) appear 3× more often.\n"
        "After each answer you see the full range chart with your hand highlighted.\n\n"
        "Ranges based on rangeconverter.com (6-max GTO charts).",
        parse_mode=ParseMode.HTML,
    )


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)
    chat_id = update.effective_chat.id

    active_chats.add(chat_id)
    save_state(active_chats)
    bankroll_manager.get_or_create_user(user_id, username)
    _init_stats(user_id)

    # Parse optional args: /quiz utg  or  /quiz 100bb utg
    pos_arg = None
    fmt_arg = None
    if context.args:
        for arg in context.args:
            a = arg.upper()
            if a in OPEN_RANGE_POSITIONS:
                pos_arg = a
            elif a in {f.upper() for f in open_range_quiz.FORMATS}:
                fmt_arg = next((f for f in open_range_quiz.FORMATS if f.upper() == a), None)

    # Pick from verified slots only
    if not fmt_arg and not pos_arg:
        fmt_arg, pos_arg = random.choice(VERIFIED_SLOTS)
    elif fmt_arg and not pos_arg:
        candidates = [p for f, p in VERIFIED_SLOTS if f == fmt_arg]
        pos_arg = random.choice(candidates) if candidates else None
    # If specific (fmt, pos) given, allow even if not verified

    question = open_range_quiz.generate_question(
        format_key=fmt_arg,
        position=pos_arg,
        recent=_get_recent_set(user_id, pos_arg or ""),
    )
    pending_quizzes[user_id] = question

    text, keyboard = _build_quiz_message(question)
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


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
    if not question or question.position != pos or question.hand != hand:
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

    _init_stats(user_id)
    user_stats[user_id]["total"] += 1
    if was_correct:
        user_stats[user_id]["correct"] += 1

    _record_recent(user_id, pos, hand)
    pending_quizzes.pop(user_id, None)

    stats = user_stats[user_id]
    accuracy = stats["correct"] / stats["total"] * 100 if stats["total"] else 0

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
                f"Session: {stats['correct']}/{stats['total']} ({accuracy:.0f}%)"
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


async def handle_next_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or str(user_id)

    bankroll_manager.get_or_create_user(user_id, username)
    _init_stats(user_id)

    # Parse: next:{fmt}:{pos} — pick next from verified slots (same format, random position)
    parts = query.data.split(":")
    fmt_arg = parts[1] if len(parts) >= 2 else None
    pos_arg = parts[2] if len(parts) >= 3 and parts[2] in OPEN_RANGE_POSITIONS else None

    if fmt_arg and (fmt_arg, pos_arg) in VERIFIED_SET:
        candidates = [p for f, p in VERIFIED_SLOTS if f == fmt_arg]
        pos_arg = random.choice(candidates) if candidates else pos_arg
    elif not fmt_arg or (fmt_arg, pos_arg) not in VERIFIED_SET:
        fmt_arg, pos_arg = random.choice(VERIFIED_SLOTS)

    question = open_range_quiz.generate_question(
        format_key=fmt_arg,
        position=pos_arg,
        recent=_get_recent_set(user_id, pos_arg or ""),
    )
    pending_quizzes[user_id] = question

    text, keyboard = _build_quiz_message(question)
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


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

    streak_txt = f"  🔥{streak}" if streak >= 3 else ""
    await update.message.reply_text(
        f"<b>Stats</b>\n\n"
        f"Bankroll: <b>{br:.0f}bb</b> (peak {best_br:.0f}bb){streak_txt}\n"
        f"Correct: {correct}/{total} ({acc:.1f}%)\n"
        f"Best streak: {best_streak}",
        parse_mode=ParseMode.HTML,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)


async def post_init(application):
    commands = [
        BotCommand("quiz", "Open range quiz (add position: /quiz utg)"),
        BotCommand("q", "Open range quiz"),
        BotCommand("stats", "Session accuracy"),
        BotCommand("help", "How to play"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


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
    application.add_handler(CallbackQueryHandler(handle_open_range_answer, pattern=r"^rfi:"))
    application.add_handler(CallbackQueryHandler(handle_next_quiz, pattern=r"^next:"))
    application.add_handler(CallbackQueryHandler(handle_fix_prompt, pattern=r"^fix:"))
    application.add_handler(CallbackQueryHandler(handle_fix_apply, pattern=r"^fixdo:"))
    application.add_error_handler(error_handler)

    logger.info("Starting Open Range Quiz Bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
