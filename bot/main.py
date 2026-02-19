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

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global managers
quiz_manager = QuizManager()
score_manager = ScoreManager()

# Store chat_id for scheduled quizzes
active_chats: set[int] = set()

# Store users who started bot (can receive DM)
dm_enabled_users: set[int] = set()

# Current active quiz per chat
active_quiz_messages: dict[int, dict] = {}  # chat_id -> {"message_id": x, "question": q}


def escape_html(text: str) -> str:
    """Escape HTML special characters"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if update.effective_chat.type == "private":
        dm_enabled_users.add(user_id)
        await update.message.reply_text(
            "🃏 <b>SunPokerQuizBot</b>에 오신 것을 환영합니다!\n\n"
            "이제 퀴즈 결과를 DM으로 받을 수 있습니다.\n"
            "그룹에서 퀴즈에 참여하세요!",
            parse_mode=ParseMode.HTML
        )
    else:
        active_chats.add(chat_id)
        await update.message.reply_text(
            "🃏 <b>SunPokerQuizBot</b> 활성화!\n\n"
            "<b>퀴즈 시간:</b>\n"
            "• 오전 6시 (KST)\n"
            "• 오후 6시 (KST)\n\n"
            "<b>명령어:</b>\n"
            "/quiz - 현재 퀴즈 보기\n"
            "/score - 내 점수\n"
            "/leaderboard - 순위표\n\n"
            "💡 봇에게 DM으로 /start 하면 정답을 DM으로 받아요!",
            parse_mode=ParseMode.HTML
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "🃏 <b>Poker Quiz Bot</b>\n\n"
        "<b>퀴즈 스케줄:</b>\n"
        "• 오전 6시, 오후 6시 자동 출제\n"
        "• 다음 퀴즈 10분 전에 해설 공개\n\n"
        "<b>사용법:</b>\n"
        "1. 퀴즈가 오면 버튼으로 답변\n"
        "2. 즉시 정답 여부 확인\n"
        "3. 해설에서 자세한 설명 확인\n\n"
        "🔥 매일 참여해서 스트릭 유지!",
        parse_mode=ParseMode.HTML
    )


async def send_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE, question=None) -> Optional[int]:
    """Send a quiz to the chat."""
    try:
        if question is None:
            question = quiz_manager.get_random_question()
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton(opt, callback_data=f"ans_{question.id}_{i}")]
            for i, opt in enumerate(question.options)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Format question text (HTML)
        text = f"🃏 <b>Poker Quiz #{question.id}</b>\n\n"
        text += f"<pre>{escape_html(question.situation)}</pre>\n\n"
        text += f"Hero's hand: <b>{question.hand}</b>\n\n"
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
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    
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
            # Create new quiz (first time or after explanation cleared it)
            question = quiz_manager.get_random_question()
            await send_quiz(chat_id, context, question)


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
    
    # Prepare feedback
    correct_answer = current_q.options[current_q.answer]
    selected_answer = current_q.options[answer_index]
    
    if is_correct:
        feedback = f"✅ 정답! ({selected_answer})"
        popup = "✅ 정답입니다!"
    else:
        feedback = f"❌ 오답 ({selected_answer})\n정답: {correct_answer}"
        popup = "❌ 오답입니다."
    
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
    logger.info("Scheduled quiz triggered")
    
    # Get new question (shared across all chats)
    question = quiz_manager.get_random_question()
    
    for chat_id in active_chats.copy():
        try:
            await send_quiz(chat_id, context, question)
        except Exception as e:
            logger.error(f"Failed scheduled quiz to {chat_id}: {e}")


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
    application.add_handler(CommandHandler("score", score_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^ans_\d+_\d+$"))
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
