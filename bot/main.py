#!/usr/bin/env python3
"""Open Range Quiz Telegram Bot."""
import json
import logging
from collections import deque
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN
from quiz import QuizManager, OpenRangeQuizManager, OPEN_RANGE_POSITIONS

FORMAT_URLS = {
    "6max_100bb_highRake": "https://rangeconverter.com/articles/preflop-charts-6-max-100bb-small-stakes-no-limit-texas-holdem",
    "6max_100bb":          "https://rangeconverter.com/articles/poker-charts-6-max-100bb-no-limit-texas-holdem",
    "6max_40bb":           "https://rangeconverter.com/articles/poker-charts-6-max-40bb-no-limit-texas-holdem",
    "6max_200bb":          "https://rangeconverter.com/articles/poker-charts-6-max-200bb-no-limit-texas-holdem",
    "9max_100bb":          "https://rangeconverter.com/articles/poker-charts-9-max-100bb-no-limit-texas-holdem",
    "mtt_100bb":           "https://rangeconverter.com/articles/poker-charts-8max-mtt-100bb-no-limit-texas-holdem-tournaments",
    "mtt_60bb":            "https://rangeconverter.com/articles/poker-charts-8max-mtt-60bb-no-limit-texas-holdem-tournaments",
    "mtt_50bb":            "https://rangeconverter.com/articles/poker-charts-8max-mtt-50bb-no-limit-texas-holdem-tournaments",
    "mtt_40bb":            "https://rangeconverter.com/articles/poker-charts-8max-mtt-40bb-no-limit-texas-holdem-tournaments",
    "mtt_30bb":            "https://rangeconverter.com/articles/poker-charts-8max-mtt-30bb-no-limit-texas-holdem-tournaments",
    "mtt_20bb":            "https://rangeconverter.com/articles/poker-charts-8max-mtt-20bb-no-limit-texas-holdem-tournaments",
    "mtt_10bb":            "https://rangeconverter.com/articles/poker-charts-8max-mtt-10bb-no-limit-texas-holdem-tournaments",
}

# Players left to act after hero opens (varies by format)
PLAYERS_LEFT = {
    "UTG": 5, "UTG+1": 4, "MP": 4, "LJ": 3, "HJ": 3, "CO": 3, "BTN": 2, "SB": 1,
}
from bankroll import BankrollManager
from chart import generate_open_range_chart, combine_with_crop
from config import DATA_DIR
from persistence import load_state, save_state

CROPS_DIR = DATA_DIR / "crops"

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
    fmt  = escape_html(question.format_name)
    left = PLAYERS_LEFT.get(pos, "?")
    fkey = question.format_key

    text = (
        f"<b>{pos} Open Range</b>  <code>({left} left)</code>\n\n"
        f"<code>{fmt} · Folds to Hero in {pos}</code>\n\n"
        f"Your hand:  <b>{hand}</b>\n\n"
    )
    # SB has 3 options (raise/call/fold), others have 2
    has_call = bool(question.call_hands)
    if has_call:
        text += "Raise, Call, or Fold?"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Raise", callback_data=f"rfi:{fkey}:{pos}:{question.hand}:O"),
            InlineKeyboardButton("Call",  callback_data=f"rfi:{fkey}:{pos}:{question.hand}:C"),
            InlineKeyboardButton("Fold",  callback_data=f"rfi:{fkey}:{pos}:{question.hand}:F"),
        ]])
    else:
        text += "Open or Fold?"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("Open", callback_data=f"rfi:{fkey}:{pos}:{question.hand}:O"),
            InlineKeyboardButton("Fold", callback_data=f"rfi:{fkey}:{pos}:{question.hand}:F"),
        ]])
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
                # find format by case-insensitive match
                fmt_arg = next((f for f in open_range_quiz.FORMATS if f.upper() == a), None)

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

    # Parse: rfi:{fmt}:{pos}:{hand}:{O|C|F}
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Invalid data.", show_alert=True)
        return

    _, fmt, pos, hand, action_code = parts
    chosen = {"O": "Open", "C": "Call", "F": "Fold"}.get(action_code, "Fold")

    question = pending_quizzes.get(user_id)
    if not question or question.position != pos or question.hand != hand:
        await query.answer("Quiz expired — use /quiz for a new one.", show_alert=True)
        return

    correct = question.correct_action
    is_mixed = hand in question.mixed_hands
    was_correct = chosen == correct or is_mixed

    bankroll_manager.get_or_create_user(user_id, username)
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
    fmt_name = escape_html(question.format_name)

    if is_mixed:
        verdict = f"<b>{h_disp}</b> is mixed in {pos} — both raise and fold are OK."
    elif was_correct:
        if correct == "Fold":
            verdict = f"Correct! <b>{h_disp}</b> is NOT in the {pos} open range."
        elif correct == "Call":
            verdict = f"Correct! <b>{h_disp}</b> is a limp/call in {pos}."
        else:
            verdict = f"Correct! <b>{h_disp}</b> is in the {pos} open range."
    else:
        if correct == "Open":
            verdict = f"Wrong. <b>{h_disp}</b> IS in the {pos} open range."
        elif correct == "Call":
            verdict = f"Wrong. <b>{h_disp}</b> should be called/limped in {pos}."
        else:
            verdict = f"Wrong. <b>{h_disp}</b> is NOT in the {pos} open range."

    url = FORMAT_URLS.get(fmt, "")
    url_line = f'\n<a href="{url}">rangeconverter.com ↗</a>' if url else ""
    result_text = (
        f"{icon} <b>{escape_html(pos)} — {h_disp}</b>\n\n"
        f"{verdict}\n"
        f"<code>{fmt_name}</code>{url_line}\n\n"
        f"Session: {stats['correct']}/{stats['total']} ({accuracy:.0f}%)"
    )

    await query.answer("✅ Correct!" if was_correct else "❌ Wrong")
    await query.edit_message_text(result_text, parse_mode=ParseMode.HTML)

    # Send range chart (extracted grid) + original PDF crop side-by-side
    try:
        chart_bytes = generate_open_range_chart(
            in_range_hands=question.raise_hands,
            call_hands=question.call_hands,
            highlight_hand=hand,
            title=f"{pos} Open Range ({question.format_name})",
        )
        crop_path = str(CROPS_DIR / f"{fmt}_rfi_{pos}.png")
        combined  = combine_with_crop(chart_bytes, crop_path)
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=BytesIO(combined),
            caption=f"{pos} — {hand}  |  left: extracted · right: PDF",
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

    # Parse: next:{fmt}:{pos}
    parts = query.data.split(":")
    fmt_arg = parts[1] if len(parts) >= 2 else None
    pos_arg = parts[2] if len(parts) >= 3 and parts[2] in OPEN_RANGE_POSITIONS else None

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
    _init_stats(user_id)
    stats = user_stats[user_id]

    if stats["total"] == 0:
        await update.message.reply_text("No answers yet — use /quiz to start!")
        return

    accuracy = stats["correct"] / stats["total"] * 100
    await update.message.reply_text(
        f"<b>Session Stats</b>\n\n"
        f"Correct: {stats['correct']}/{stats['total']} ({accuracy:.1f}%)",
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
