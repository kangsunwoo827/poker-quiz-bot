#!/usr/bin/env python3
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from telegram.constants import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    TELEGRAM_BOT_TOKEN, QUIZ_TIMES_UTC, EXPLANATION_TIMES_UTC
)
from quiz import QuizManager
from score import ScoreManager
from persistence import load_state, save_state, format_time_until_explanation

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global managers
quiz_manager = QuizManager()
score_manager = ScoreManager()

# Load persisted state
_state = load_state()

# Store chat_id for scheduled quizzes
active_chats: set[int] = set(_state.get("active_chats", []))

# Store users who started bot (can receive DM)
dm_enabled_users: set[int] = set(_state.get("dm_enabled_users", []))

# Current active quiz per chat
active_quiz_messages: dict[int, dict] = {}  # chat_id -> {"message_id": x, "question": q}

# Restore quiz_manager state
quiz_manager.used_questions = set(_state.get("used_questions", []))
quiz_manager.user_answers = {int(k): v for k, v in _state.get("user_answers", {}).items()}

# Restore current question if exists
_current_q_id = _state.get("current_question_id")
if _current_q_id:
    for q in quiz_manager.questions:
        if q.id == _current_q_id:
            quiz_manager.current_question = q
            break

# Store last question for /explain command
last_question = None
_last_q_id = _state.get("last_question_id")
if _last_q_id:
    for q in quiz_manager.questions:
        if q.id == _last_q_id:
            last_question = q
            break

logger.info(f"Loaded state: {len(active_chats)} chats, {len(dm_enabled_users)} DM users, {len(quiz_manager.used_questions)} used questions")


def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if update.effective_chat.type == "private":
        dm_enabled_users.add(user_id)
        save_state(active_chats, dm_enabled_users)
        await update.message.reply_text(
            "🃏 <b>SunPokerQuizBot</b>에 오신 것을 환영합니다!\n\n"
            "이제 퀴즈 결과를 DM으로 받을 수 있습니다.\n"
            "그룹에서 퀴즈에 참여하세요!",
            parse_mode=ParseMode.HTML
        )
    else:
        active_chats.add(chat_id)
        save_state(active_chats, dm_enabled_users)
        
        time_str = format_time_until_explanation()
        await update.message.reply_text(
            "🃏 <b>SunPokerQuizBot</b> 활성화!\n\n"
            "<b>퀴즈 시간:</b>\n"
            "• 오전 6시 (KST)\n"
            "• 오후 6시 (KST)\n\n"
            "<b>명령어:</b>\n"
            "/quiz - 현재 퀴즈 보기\n"
            "/explain - 이전 문제 해설\n"
            "/score - 내 점수\n"
            "/leaderboard - 순위표\n"
            "/help - 용어 설명\n\n"
            f"⏰ 다음 해설까지: <b>{time_str}</b>",
            parse_mode=ParseMode.HTML
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command - show poker terms"""
    await update.message.reply_text(
        "🃏 <b>Poker Quiz Bot - 용어 설명</b>\n\n"
        
        "<b>📍 포지션</b>\n"
        "• <b>UTG</b> (Under The Gun): 빅블라인드 다음, 첫 액션\n"
        "• <b>MP</b> (Middle Position): 중간 위치\n"
        "• <b>CO</b> (Cutoff): 버튼 오른쪽\n"
        "• <b>BTN</b> (Button): 딜러 위치, 가장 유리\n"
        "• <b>SB</b> (Small Blind): 스몰 블라인드\n"
        "• <b>BB</b> (Big Blind): 빅 블라인드\n"
        "• <b>IP</b>: In Position (유리한 위치)\n"
        "• <b>OOP</b>: Out of Position (불리한 위치)\n\n"
        
        "<b>🎯 액션</b>\n"
        "• <b>Open/Raise</b>: 첫 번째 레이즈\n"
        "• <b>3-bet</b>: 오픈에 대한 리레이즈\n"
        "• <b>4-bet</b>: 3-bet에 대한 리레이즈\n"
        "• <b>Cbet</b>: 프리플랍 레이저의 플랍 베팅\n"
        "• <b>Donk bet</b>: 콜러가 먼저 베팅\n"
        "• <b>Check-raise</b>: 체크 후 레이즈\n\n"
        
        "<b>🃏 핸드 & 보드</b>\n"
        "• <b>Suited (s)</b>: 같은 무늬 (예: AKs)\n"
        "• <b>Offsuit (o)</b>: 다른 무늬 (예: AKo)\n"
        "• <b>Overpair</b>: 보드보다 높은 포켓페어\n"
        "• <b>Set</b>: 포켓페어 + 보드 = 트리플\n"
        "• <b>Dry board</b>: 드로우 없는 보드\n"
        "• <b>Wet board</b>: 드로우 많은 보드\n\n"
        
        "<b>📊 전략 용어</b>\n"
        "• <b>GTO</b>: Game Theory Optimal (최적 전략)\n"
        "• <b>Equity</b>: 승률\n"
        "• <b>EV</b>: Expected Value (기대값)\n"
        "• <b>SPR</b>: Stack to Pot Ratio\n"
        "• <b>Range</b>: 가능한 핸드 범위\n"
        "• <b>Blocker</b>: 상대 핸드 확률 낮추는 카드\n"
        "• <b>Fold equity</b>: 폴드시켜 얻는 가치\n\n"
        
        "<b>📈 Range Table 읽는 법</b>\n"
        "• <b>R</b> = Raise (오픈)\n"
        "• <b>3</b> = 3-bet\n"
        "• <b>4</b> = 4-bet\n"
        "• <b>C</b> = Call\n"
        "• <b>.</b> = Fold",
        parse_mode=ParseMode.HTML
    )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command - cancel/end current quiz"""
    chat_id = update.effective_chat.id
    
    question = None
    
    # Check active_quiz_messages first
    if chat_id in active_quiz_messages:
        question = active_quiz_messages[chat_id]["question"]
        del active_quiz_messages[chat_id]
    # Fall back to quiz_manager.current_question
    elif quiz_manager.current_question:
        question = quiz_manager.current_question
    
    if question:
        # Clear quiz state
        quiz_manager.current_question = None
        quiz_manager.user_answers.clear()
        
        # Save cleared state
        save_state(
            active_chats, dm_enabled_users,
            None,  # no current question
            quiz_manager.used_questions,
            {}  # clear user answers
        )
        
        await update.message.reply_text(
            f"🚫 Quiz #{question.id} 종료됨\n\n"
            f"/quiz 로 새 문제를 받거나, 다음 정규 시간(6시/18시)에 자동 출제됩니다.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("현재 활성화된 퀴즈가 없습니다.")


async def send_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE, question=None) -> Optional[int]:
    """Send a quiz to the chat."""
    try:
        if question is None:
            question = quiz_manager.get_random_question()
        
        # Create keyboard - options + cancel button
        keyboard = [
            [InlineKeyboardButton(opt, callback_data=f"ans_{question.id}_{i}")]
            for i, opt in enumerate(question.options)
        ]
        keyboard.append([InlineKeyboardButton("❌ 취소", callback_data=f"cancel_{question.id}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Format question text (HTML)
        time_str = format_time_until_explanation()
        
        text = f"🃏 <b>Poker Quiz #{question.id}</b>\n\n"
        text += f"<pre>{escape_html(question.situation)}\n\nHero's hand: {question.hand}</pre>\n\n"
        text += f"⏰ 해설까지: {time_str}\n\n"
        text += "Your action?"
        
        # Send question
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML
        )
        
        # Store active quiz
        active_quiz_messages[chat_id] = {
            "message_id": message.message_id,
            "question": question
        }
        
        logger.info(f"Quiz #{question.id} sent to chat {chat_id}")
        return message.message_id
        
    except Exception as e:
        logger.error(f"Failed to send quiz to {chat_id}: {e}")
        return None


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /quiz command - shows current active quiz or creates one if none exists"""
    global last_question
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    save_state(active_chats, dm_enabled_users)
    
    # Check if there's an active quiz for this chat
    if chat_id in active_quiz_messages:
        # Show existing quiz
        question = active_quiz_messages[chat_id]["question"]
        await send_quiz(chat_id, context, question)
    else:
        # No active quiz - check if there's a global current question
        if quiz_manager.current_question is not None:
            # Use the current global question
            await send_quiz(chat_id, context, quiz_manager.current_question)
        else:
            # Save current as last before creating new
            if quiz_manager.current_question:
                last_question = quiz_manager.current_question
            
            # Create new quiz (first time or after explanation cleared it)
            question = quiz_manager.get_random_question()
            await send_quiz(chat_id, context, question)
            
            # Save state
            save_state(
                active_chats, dm_enabled_users,
                question.id,
                quiz_manager.used_questions,
                quiz_manager.user_answers,
                last_question.id if last_question else None
            )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle answer button press"""
    query = update.callback_query
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name or f"User{user_id}"
    chat_id = query.message.chat_id
    
    # Parse callback data
    try:
        parts = query.data.split("_")
        question_id = int(parts[1])
        answer_index = int(parts[2])
    except (IndexError, ValueError):
        await query.answer("오류가 발생했습니다.", show_alert=True)
        return
    
    # Check if this is the current question
    if chat_id not in active_quiz_messages:
        await query.answer("이 퀴즈는 이미 종료되었습니다.", show_alert=True)
        return
    
    current_q = active_quiz_messages[chat_id]["question"]
    if current_q.id != question_id:
        await query.answer("이 퀴즈는 이미 종료되었습니다.", show_alert=True)
        return
    
    # Check if already answered
    if user_id in quiz_manager.user_answers:
        await query.answer("이미 답변하셨습니다!", show_alert=True)
        return
    
    # Record answer
    is_correct = quiz_manager.record_answer(user_id, answer_index)
    
    # Record to score DB
    score_manager.record_answer(
        user_id, username,
        question_id,
        answer_index, is_correct
    )
    
    # Save user answers to persist
    save_state(
        active_chats, dm_enabled_users,
        current_q.id,
        quiz_manager.used_questions,
        quiz_manager.user_answers
    )
    
    # Check if all members answered → auto next question
    try:
        member_count = await context.bot.get_chat_member_count(chat_id)
        # Subtract 1 for the bot itself
        expected_answers = member_count - 1
        current_answers = len(quiz_manager.user_answers)
        
        if current_answers >= expected_answers and expected_answers > 0:
            # All members answered! Send explanation and next quiz
            logger.info(f"All {current_answers} members answered, sending next quiz")
            await send_explanation(chat_id, current_q, context)
            
            # Clear and get next question
            global last_question
            last_question = current_q
            quiz_manager.user_answers.clear()
            
            new_question = quiz_manager.get_random_question()
            save_state(
                active_chats, dm_enabled_users,
                new_question.id,
                quiz_manager.used_questions,
                quiz_manager.user_answers,
                last_question.id if last_question else None
            )
            await send_quiz(chat_id, context, new_question)
    except Exception as e:
        logger.warning(f"Could not check member count: {e}")
    
    # Prepare feedback
    correct_answer = current_q.options[current_q.answer]
    selected_answer = current_q.options[answer_index]
    
    if is_correct:
        feedback = "✅ 정답!"
        popup = "✅ 정답입니다!"
    else:
        feedback = "❌ 오답"
        popup = "❌ 오답입니다. 해설에서 정답을 확인하세요."
    
    await query.answer(popup)
    
    # Try DM, fallback to group reply
    dm_sent = False
    if user_id in dm_enabled_users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"{feedback}\n\n다음 퀴즈 10분 전에 상세 해설이 공개됩니다.",
                parse_mode=ParseMode.HTML
            )
            dm_sent = True
        except Exception as e:
            logger.warning(f"DM failed for {user_id}: {e}")
            dm_enabled_users.discard(user_id)
    
    if not dm_sent:
        try:
            reply_msg = await query.message.reply_text(
                f"@{username}: {feedback}",
                parse_mode=ParseMode.HTML
            )
            # Delete after 10 seconds
            context.job_queue.run_once(
                delete_message,
                timedelta(seconds=10),
                data={"chat_id": chat_id, "message_id": reply_msg.message_id}
            )
        except Exception as e:
            logger.error(f"Reply failed: {e}")
    
    logger.info(f"User {username} answered Q#{question_id}: {'correct' if is_correct else 'wrong'}")


async def handle_cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle cancel button press - delete the quiz message"""
    query = update.callback_query
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    
    # Delete the message
    try:
        await query.message.delete()
        await query.answer("퀴즈 메시지가 삭제되었습니다.")
        
        # Remove from active_quiz_messages if this was the active one
        if chat_id in active_quiz_messages:
            if active_quiz_messages[chat_id].get("message_id") == message_id:
                del active_quiz_messages[chat_id]
        
        logger.info(f"Quiz message deleted in chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to delete quiz message: {e}")
        await query.answer("메시지 삭제 실패", show_alert=True)


async def delete_message(context: ContextTypes.DEFAULT_TYPE):
    """Delete a message"""
    try:
        data = context.job.data
        await context.bot.delete_message(
            chat_id=data["chat_id"],
            message_id=data["message_id"]
        )
    except Exception:
        pass


async def scheduled_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Send new quiz to all active chats"""
    global last_question
    logger.info("Scheduled quiz triggered")
    
    # Save current question as last question before getting new one
    if quiz_manager.current_question:
        last_question = quiz_manager.current_question
    
    # Get new question (shared across all chats)
    question = quiz_manager.get_random_question()
    
    # Save state with current question, last question, and used questions
    save_state(
        active_chats, dm_enabled_users, 
        question.id, 
        quiz_manager.used_questions,
        quiz_manager.user_answers,
        last_question.id if last_question else None
    )
    
    for chat_id in active_chats.copy():
        try:
            await send_quiz(chat_id, context, question)
        except Exception as e:
            logger.error(f"Failed scheduled quiz to {chat_id}: {e}")
            active_chats.discard(chat_id)
            save_state(active_chats, dm_enabled_users)


async def scheduled_explanation(context: ContextTypes.DEFAULT_TYPE):
    """Send explanation to all active chats"""
    logger.info("Scheduled explanation triggered")
    
    for chat_id in active_chats.copy():
        if chat_id not in active_quiz_messages:
            continue
        
        question = active_quiz_messages[chat_id]["question"]
        
        try:
            await send_explanation(chat_id, question, context)
            # Clear active quiz after explanation
            del active_quiz_messages[chat_id]
        except Exception as e:
            logger.error(f"Failed explanation to {chat_id}: {e}")


async def send_explanation(chat_id: int, question, context: ContextTypes.DEFAULT_TYPE):
    """Send explanation for a question"""
    import re
    
    correct_option = question.options[question.answer]
    
    # Format explanation with HTML
    explanation_html = question.explanation
    explanation_html = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', explanation_html)
    
    text = f"📖 <b>Quiz #{question.id} 해설</b>\n\n"
    text += f"<b>정답:</b> {escape_html(correct_option)}\n\n"
    text += explanation_html
    
    # Add range table for preflop questions
    range_table = quiz_manager.get_range_table(question)
    if range_table:
        text += f"\n\n<pre>{escape_html(range_table)}</pre>"
    
    if question.terms:
        text += "\n\n<b>📚 용어 설명</b>\n"
        for term, definition in question.terms.items():
            text += f"• <b>{escape_html(term)}</b>: {escape_html(definition)}\n"
    
    # Stats
    total = len(quiz_manager.user_answers)
    if total > 0:
        correct_count = sum(1 for a in quiz_manager.user_answers.values() if a == question.answer)
        pct = int(correct_count / total * 100)
        text += f"\n📊 정답률: {pct}% ({correct_count}/{total})"
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML
    )
    logger.info(f"Explanation for Q#{question.id} sent to {chat_id}")


async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /explain command - show explanation for last question"""
    global last_question
    chat_id = update.effective_chat.id
    
    # Show last question's explanation (previous quiz)
    if last_question:
        await send_explanation(chat_id, last_question, context)
    elif quiz_manager.current_question:
        # If no last question, show current one
        await update.message.reply_text(
            "이전 문제가 없습니다. 현재 문제 해설을 보시겠습니까?\n"
            "현재 문제: /quiz 로 확인"
        )
    else:
        await update.message.reply_text(
            "표시할 해설이 없습니다.\n/quiz 로 새 문제를 받으세요."
        )


async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /score command"""
    user_id = update.effective_user.id
    stats = score_manager.get_user_stats(user_id)
    
    if stats:
        streak_emoji = "🔥" if stats['streak'] > 0 else ""
        await update.message.reply_text(
            f"📊 <b>{escape_html(stats['username'])}님의 성적</b>\n\n"
            f"정답: {stats['correct']}/{stats['total']} ({stats['accuracy']:.1f}%)\n"
            f"현재 스트릭: {stats['streak']} {streak_emoji}\n"
            f"최고 스트릭: {stats['best_streak']} ⭐",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text("아직 참여 기록이 없습니다.")


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /leaderboard command"""
    leaders = score_manager.get_leaderboard(10)
    
    if not leaders:
        await update.message.reply_text("아직 참여자가 없습니다!")
        return
    
    text = "🏆 <b>리더보드</b>\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, leader in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} <b>{escape_html(leader['username'])}</b> - {leader['correct']}점 ({leader['accuracy']:.0f}%)\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Exception: {context.error}")


def main():
    """Start the bot"""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set!")
        return
    
    # Build application
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    # /cancel removed - use cancel button on quiz instead
    application.add_handler(CommandHandler("score", score_command))
    application.add_handler(CommandHandler("explain", explain_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^ans_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(handle_cancel_button, pattern=r"^cancel_\d+$"))
    application.add_error_handler(error_handler)
    
    # Schedule quizzes (06:00, 18:00 KST = 21:00, 09:00 UTC)
    job_queue = application.job_queue
    
    for qt in QUIZ_TIMES_UTC:
        job_queue.run_daily(
            scheduled_quiz,
            time=datetime.strptime(f"{qt['hour']:02d}:{qt['minute']:02d}", "%H:%M").time(),
            name=f"quiz_{qt['hour']}_{qt['minute']}"
        )
    
    # Schedule explanations (05:50, 17:50 KST = 20:50, 08:50 UTC)
    for et in EXPLANATION_TIMES_UTC:
        job_queue.run_daily(
            scheduled_explanation,
            time=datetime.strptime(f"{et['hour']:02d}:{et['minute']:02d}", "%H:%M").time(),
            name=f"explain_{et['hour']}_{et['minute']}"
        )
    
    logger.info("Starting SunPokerQuizBot...")
    logger.info("Quiz times: 06:00 KST (21:00 UTC), 18:00 KST (09:00 UTC)")
    logger.info("Explanation times: 05:50 KST (20:50 UTC), 17:50 KST (08:50 UTC)")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
