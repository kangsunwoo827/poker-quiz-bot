#!/usr/bin/env python3
import asyncio
import logging
from datetime import timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import TELEGRAM_BOT_TOKEN, QUIZ_INTERVAL_HOURS, ANSWER_REVEAL_DELAY_MINUTES
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    
    await update.message.reply_text(
        "🃏 **SunPokerQuizBot** 에 오신 것을 환영합니다!\n\n"
        "**명령어:**\n"
        "/quiz - 새 퀴즈 출제\n"
        "/score - 내 점수 확인\n"
        "/leaderboard - 순위표\n"
        "/help - 도움말\n\n"
        f"매 {QUIZ_INTERVAL_HOURS}시간마다 자동으로 퀴즈가 출제됩니다!",
        parse_mode="Markdown"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await update.message.reply_text(
        "🃏 **Poker Quiz Bot 사용법**\n\n"
        "1. 퀴즈가 출제되면 버튼을 눌러 답변\n"
        "2. 즉시 정답 여부 DM으로 전송\n"
        f"3. {ANSWER_REVEAL_DELAY_MINUTES}분 후 해설 공개\n"
        "4. 점수는 자동 기록!\n\n"
        "**팁:** 꾸준히 참여해서 스트릭을 유지하세요! 🔥",
        parse_mode="Markdown"
    )

async def send_quiz(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """Send a quiz to the chat"""
    question = quiz_manager.get_random_question()
    
    # Create keyboard
    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"answer_{i}")]
        for i, opt in enumerate(question.options)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send question
    message = await context.bot.send_message(
        chat_id=chat_id,
        text=quiz_manager.format_question(question),
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )
    
    # Schedule explanation reveal
    context.job_queue.run_once(
        reveal_explanation,
        timedelta(minutes=ANSWER_REVEAL_DELAY_MINUTES),
        data={"chat_id": chat_id, "question": question},
        name=f"reveal_{chat_id}"
    )
    
    return message

async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /quiz command"""
    chat_id = update.effective_chat.id
    active_chats.add(chat_id)
    await send_quiz(chat_id, context)

async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle answer button press"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    username = query.from_user.username or query.from_user.first_name
    
    # Parse answer
    answer_index = int(query.data.split("_")[1])
    
    # Check if already answered
    if user_id in quiz_manager.user_answers:
        await query.answer("이미 답변하셨습니다!", show_alert=True)
        return
    
    # Record answer
    is_correct = quiz_manager.record_answer(user_id, answer_index)
    
    if quiz_manager.current_question:
        score_manager.record_answer(
            user_id, username, 
            quiz_manager.current_question.id,
            answer_index, is_correct
        )
    
    # Send DM to user
    try:
        correct_text = "✅ 정답입니다!" if is_correct else "❌ 오답입니다."
        correct_answer = quiz_manager.current_question.options[quiz_manager.current_question.answer]
        
        await context.bot.send_message(
            chat_id=user_id,
            text=f"{correct_text}\n\n정답: **{correct_answer}**\n\n잠시 후 그룹에 상세 해설이 올라갑니다.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.warning(f"Could not send DM to {user_id}: {e}")

async def reveal_explanation(context: ContextTypes.DEFAULT_TYPE):
    """Reveal the explanation after delay"""
    job_data = context.job.data
    chat_id = job_data["chat_id"]
    question = job_data["question"]
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=quiz_manager.format_explanation(question),
        parse_mode="Markdown"
    )

async def score_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /score command"""
    user_id = update.effective_user.id
    stats = score_manager.get_user_stats(user_id)
    
    if stats:
        await update.message.reply_text(
            f"📊 **{stats['username']}님의 성적**\n\n"
            f"정답: {stats['correct']}/{stats['total']} ({stats['accuracy']:.1f}%)\n"
            f"현재 스트릭: {stats['streak']} 🔥\n"
            f"최고 스트릭: {stats['best_streak']} ⭐",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("아직 참여 기록이 없습니다. /quiz 로 시작하세요!")

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /leaderboard command"""
    leaders = score_manager.get_leaderboard(10)
    
    if not leaders:
        await update.message.reply_text("아직 참여자가 없습니다!")
        return
    
    text = "🏆 **리더보드**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, leader in enumerate(leaders):
        medal = medals[i] if i < 3 else f"{i+1}."
        text += f"{medal} **{leader['username']}** - {leader['correct']}점 ({leader['accuracy']:.0f}%)\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def scheduled_quiz(context: ContextTypes.DEFAULT_TYPE):
    """Send quiz to all active chats"""
    for chat_id in active_chats.copy():
        try:
            await send_quiz(chat_id, context)
        except Exception as e:
            logger.error(f"Failed to send quiz to {chat_id}: {e}")
            active_chats.discard(chat_id)

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
    application.add_handler(CallbackQueryHandler(handle_answer, pattern="^answer_"))
    
    # Schedule periodic quizzes
    job_queue = application.job_queue
    job_queue.run_repeating(
        scheduled_quiz,
        interval=timedelta(hours=QUIZ_INTERVAL_HOURS),
        first=timedelta(hours=QUIZ_INTERVAL_HOURS)
    )
    
    # Run bot
    logger.info("Starting SunPokerQuizBot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
