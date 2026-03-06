#!/usr/bin/env python3
"""GTO Preflop Quiz Telegram Bot."""
import logging
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN
from quiz import QuizManager
from bankroll import BankrollManager
from chart import generate_range_chart
from persistence import load_state, save_state

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

quiz_manager = QuizManager()
bankroll_manager = BankrollManager()

_state = load_state()
active_chats: set[int] = set(_state.get("active_chats", []))

# Per-user pending quiz: user_id -> QuizQuestion
pending_quizzes: dict[int, object] = {}


def escape_html(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)

    active_chats.add(chat_id)
    save_state(active_chats)
    bankroll_manager.get_or_create_user(user_id, username)

    available = quiz_manager.get_available_scenarios()
    scenario_count = len(available)

    await update.message.reply_text(
        "<b>GTO Preflop Quiz Trainer</b>\n\n"
        f"Scenarios loaded: {scenario_count}\n"
        "Starting bankroll: 100.0bb\n\n"
        "<b>Commands:</b>\n"
        "/quiz (/q) - Get a quiz\n"
        "/stats - Your bankroll & accuracy\n"
        "/leaderboard - Rankings\n"
        "/help - How to play",
        parse_mode=ParseMode.HTML
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "<b>GTO Preflop Quiz - How to Play</b>\n\n"
        "<b>Quiz:</b>\n"
        "Each question shows a preflop scenario with your hand.\n"
        "Pick the GTO-optimal action from the buttons.\n\n"
        "<b>Scoring:</b>\n"
        "- <b>Correct</b>: GTO frequency &gt; 0 for your action\n"
        "- <b>Bankroll</b>: Changes by normalized EV\n"
        "  (random play = 0, GTO play = positive)\n"
        "- Start at 100bb, grow by playing GTO!\n\n"
        "<b>EV Table (after answer):</b>\n"
        "- <b>vs Best</b>: EV loss vs optimal (0 = best)\n"
        "- <b>Bankroll</b>: Actual bankroll change\n\n"
        "<b>Positions:</b>\n"
        "UTG / MP / CO / BTN / SB / BB\n\n"
        "<b>Actions:</b>\n"
        "Fold / Call / Raise / 3bet / 4bet / All-in / Limp / Squeeze",
        parse_mode=ParseMode.HTML
    )


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name or str(user_id)
    chat_id = update.effective_chat.id

    active_chats.add(chat_id)
    save_state(active_chats)
    bankroll_manager.get_or_create_user(user_id, username)

    # Get recent history for dedup
    recent = bankroll_manager.get_recent_history(user_id, 50)

    question = quiz_manager.generate_question(recent_history=recent)
    if not question:
        await update.message.reply_text(
            "No EV data loaded. Add data to data/ev_tables/ first."
        )
        return

    pending_quizzes[user_id] = question

    # Build keyboard
    keyboard = []
    for i, action in enumerate(question.scenario.actions):
        keyboard.append([InlineKeyboardButton(
            action,
            callback_data=f"a:{question.scenario.id}:{question.hand}:{i}"
        )])

    text = (
        f"<b>Preflop Quiz</b>\n\n"
        f"<code>{escape_html(question.scenario.description)}</code>\n\n"
        f"Your hand: <b>{escape_html(question.hand_display)}</b>"
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.HTML
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or str(user_id)

    # Parse callback: a:scenario_id:hand:action_index
    parts = query.data.split(":")
    if len(parts) != 4:
        await query.answer("Invalid data.", show_alert=True)
        return

    _, scenario_id, hand, action_idx_str = parts
    try:
        action_idx = int(action_idx_str)
    except ValueError:
        await query.answer("Invalid data.", show_alert=True)
        return

    # Get the pending question
    question = pending_quizzes.get(user_id)
    if not question or question.scenario.id != scenario_id or question.hand != hand:
        await query.answer("This quiz has expired. Use /quiz for a new one.", show_alert=True)
        return

    scenario = question.scenario
    if action_idx < 0 or action_idx >= len(scenario.actions):
        await query.answer("Invalid action.", show_alert=True)
        return

    chosen_action = scenario.actions[action_idx]

    # Determine correctness and EV
    ev_vs_best = question.ev_vs_best
    ev_normalized = question.ev_normalized
    best_action = question.best_action
    chosen_ev_vs_best = ev_vs_best.get(chosen_action, 0)
    chosen_ev_normalized = ev_normalized.get(chosen_action, 0)
    was_correct = chosen_action in question.correct_actions

    # Record to bankroll
    result = bankroll_manager.record_answer(
        user_id=user_id,
        username=username,
        scenario_id=scenario_id,
        hand=hand,
        chosen_action=chosen_action,
        chosen_ev_normalized=chosen_ev_normalized,
        best_action=best_action,
        ev_vs_best=chosen_ev_vs_best,
        was_correct=was_correct,
    )

    # Remove from pending
    pending_quizzes.pop(user_id, None)

    # Build result message
    mark = "OK" if was_correct else "X"
    lines = [
        f"<b>{escape_html(hand)} | {escape_html(scenario.name)}</b>\n",
        f"Your action: {escape_html(chosen_action)} {'<b>OK</b>' if was_correct else '<b>X</b>'}\n",
    ]

    # EV table
    lines.append("<pre>")
    lines.append(f"{'Action':<14} {'vs Best':>8} {'Bankroll':>9}")
    lines.append(f"{'':->14} {'':->8} {'':->9}")

    for action in scenario.actions:
        ev_b = ev_vs_best.get(action, 0)
        ev_n = ev_normalized.get(action, 0)
        marker = " <- You" if action == chosen_action else ""
        ev_b_str = f"{ev_b:+.2f}" if ev_b != 0 else " 0.00"
        ev_n_str = f"{ev_n:+.2f}"
        lines.append(f"{action:<14} {ev_b_str:>8} {ev_n_str:>9}{marker}")

    lines.append("</pre>")

    # Stats line
    bankroll = result["bankroll"]
    ev_change = chosen_ev_normalized
    correct_count = result["correct_count"]
    total = result["total_questions"]
    streak = result["streak"]

    sign = "+" if ev_change >= 0 else ""
    lines.append(
        f"\n<b>{bankroll:.2f}bb</b> ({sign}{ev_change:.2f})"
    )
    lines.append(
        f"{correct_count}/{total} correct | Streak: {streak}"
    )

    await query.answer("OK!" if was_correct else "X")

    # Edit original message to remove buttons and show result
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML
    )

    # Send range chart
    try:
        scenario_hands = quiz_manager.get_scenario_hands(scenario_id)
        if scenario_hands:
            chart_bytes = generate_range_chart(
                scenario_hands=scenario_hands,
                actions=scenario.actions,
                highlight_hand=hand,
                title=scenario.name,
            )
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=BytesIO(chart_bytes),
            )
    except Exception as e:
        logger.warning(f"Failed to send range chart: {e}")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = bankroll_manager.get_user_stats(user_id)

    if not stats:
        await update.message.reply_text("No stats yet. Use /quiz to start!")
        return

    streak_str = f" (best: {stats['best_streak']})" if stats['best_streak'] > 0 else ""
    await update.message.reply_text(
        f"<b>{escape_html(stats['username'])}</b>\n\n"
        f"Bankroll: <b>{stats['bankroll']:.2f}bb</b>"
        f" (best: {stats['best_bankroll']:.2f}bb)\n"
        f"Correct: {stats['correct_count']}/{stats['total_questions']}"
        f" ({stats['accuracy']:.1f}%)\n"
        f"Streak: {stats['streak']}{streak_str}",
        parse_mode=ParseMode.HTML
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    leaders = bankroll_manager.get_leaderboard(10)

    if not leaders:
        await update.message.reply_text("No players yet!")
        return

    medals = ["1.", "2.", "3."]
    lines = ["<b>Leaderboard</b>\n"]
    for i, p in enumerate(leaders):
        prefix = medals[i] if i < 3 else f"{i+1}."
        lines.append(
            f"{prefix} <b>{escape_html(p['username'])}</b> "
            f"- {p['bankroll']:.1f}bb "
            f"({p['accuracy']:.0f}%)"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)


async def post_init(application):
    commands = [
        BotCommand("quiz", "Get a preflop quiz"),
        BotCommand("q", "Get a preflop quiz"),
        BotCommand("stats", "Your bankroll & accuracy"),
        BotCommand("leaderboard", "Rankings"),
        BotCommand("help", "How to play"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("q", quiz_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^a:"))
    application.add_error_handler(error_handler)

    logger.info("Starting GTO Preflop Quiz Bot...")
    logger.info(f"Scenarios loaded: {len(quiz_manager.get_available_scenarios())}")

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
