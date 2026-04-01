import os
import sqlite3
import logging
import random
import string
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration from environment variables
BOT_TOKEN = os.environ.get("8768132611:AAHSt87lbN-2RC4T7ggDeLzccDKpkzF9-Vg")
OWNER_ID = int(os.environ.get("7310228945", 0))

# Database setup
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    # Groups table
    c.execute('''CREATE TABLE IF NOT EXISTS groups
                 (id INTEGER PRIMARY KEY, group1 TEXT, group2 TEXT, group3 TEXT)''')
    
    # Videos table
    c.execute('''CREATE TABLE IF NOT EXISTS videos
                 (id TEXT PRIMARY KEY, file_id TEXT, created_at TIMESTAMP, 
                  clicks INTEGER DEFAULT 0, completions INTEGER DEFAULT 0)''')
    
    # Completions table
    c.execute('''CREATE TABLE IF NOT EXISTS completions
                 (user_id INTEGER, video_id TEXT, completed_at TIMESTAMP,
                  PRIMARY KEY (user_id, video_id))''')
    
    conn.commit()
    conn.close()

init_db()

# Helper functions
def is_owner(user_id):
    return user_id == OWNER_ID

def generate_video_id():
    return 'vid_' + ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))

def get_groups():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT group1, group2, group3 FROM groups WHERE id = 1")
    result = c.fetchone()
    conn.close()
    return result if result else (None, None, None)

def set_groups(group1, group2, group3):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM groups")
    c.execute("INSERT INTO groups (id, group1, group2, group3) VALUES (1, ?, ?, ?)", 
              (group1, group2, group3))
    conn.commit()
    conn.close()

def save_video(video_id, file_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO videos (id, file_id, created_at) VALUES (?, ?, ?)",
              (video_id, file_id, datetime.now()))
    conn.commit()
    conn.close()

def get_video(video_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT file_id FROM videos WHERE id = ?", (video_id,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def increment_clicks(video_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE videos SET clicks = clicks + 1 WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()

def increment_completions(video_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("UPDATE videos SET completions = completions + 1 WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()

def is_completed(user_id, video_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT * FROM completions WHERE user_id = ? AND video_id = ?", (user_id, video_id))
    result = c.fetchone()
    conn.close()
    return result is not None

def save_completion(user_id, video_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("INSERT INTO completions (user_id, video_id, completed_at) VALUES (?, ?, ?)",
              (user_id, video_id, datetime.now()))
    conn.commit()
    conn.close()

def get_all_videos():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT id, created_at, clicks, completions FROM videos ORDER BY created_at DESC")
    results = c.fetchall()
    conn.close()
    return results

def delete_video(video_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()
    conn.close()

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    
    if args:
        video_id = args[0]
        await handle_video_link(update, context, video_id)
    else:
        welcome_msg = f"""🎉 Welcome {user.first_name}!

This bot gives you access to exclusive videos after joining required groups.

📌 Commands:
/start - Show this message
/myid - Get your Telegram ID

For support: Contact bot owner"""
        
        await update.message.reply_text(welcome_msg)

async def handle_video_link(update: Update, context: ContextTypes.DEFAULT_TYPE, video_id):
    user_id = update.effective_user.id
    
    # Check if already completed
    if is_completed(user_id, video_id):
        await update.message.reply_text("✅ You already got this video! Check your chat history.")
        return
    
    # Get video file
    file_id = get_video(video_id)
    if not file_id:
        await update.message.reply_text("❌ Video not found or expired.")
        return
    
    # Increment clicks
    increment_clicks(video_id)
    
    # Get required groups
    groups = get_groups()
    if not groups or not groups[0]:
        await update.message.reply_text("⚠️ No groups configured. Contact bot owner.")
        return
    
    group1, group2, group3 = groups
    pending_groups = []
    
    # Check each group membership
    try:
        for group in [g for g in [group1, group2, group3] if g]:
            chat_member = await context.bot.get_chat_member(group, user_id)
            if chat_member.status in ['member', 'administrator', 'creator']:
                continue
            else:
                pending_groups.append(group)
    except Exception as e:
        logger.error(f"Group check error: {e}")
        pending_groups = [g for g in [group1, group2, group3] if g]
    
    if pending_groups:
        keyboard = []
        for group in pending_groups:
            keyboard.append([InlineKeyboardButton(f"📢 Join {group}", url=f"https://t.me/{group[1:]}")])
        keyboard.append([InlineKeyboardButton("✅ Check Again", callback_data=f"check_{video_id}")])
        
        pending_list = "\n".join([f"❌ {g}" for g in pending_groups])
        joined_list = "\n".join([f"✅ {g}" for g in [group1, group2, group3] if g and g not in pending_groups])
        
        msg = f"""🔒 VIDEO LOCKED

You need to join these groups first:

{pending_list}

{joined_list if joined_list else ''}

After joining, click Check Again!"""
        
        await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # Send video
        increment_completions(video_id)
        save_completion(user_id, video_id)
        
        await update.message.reply_video(video=file_id, caption="🎬 Here's your video!")
        
        # Also show share link
        bot_username = context.bot.username
        share_link = f"https://t.me/{bot_username}?start={video_id}"
        await update.message.reply_text(f"📤 Share this link with friends:\n{share_link}")

# Callback handler for check button
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("check_"):
        video_id = data.replace("check_", "")
        file_id = get_video(video_id)
        
        if not file_id:
            await query.edit_message_text("❌ Video not found.")
            return
        
        if is_completed(user_id, video_id):
            await query.edit_message_text("✅ You already got this video!")
            return
        
        groups = get_groups()
        if not groups or not groups[0]:
            await query.edit_message_text("⚠️ No groups configured.")
            return
        
        group1, group2, group3 = groups
        pending_groups = []
        
        for group in [g for g in [group1, group2, group3] if g]:
            try:
                chat_member = await context.bot.get_chat_member(group, user_id)
                if chat_member.status not in ['member', 'administrator', 'creator']:
                    pending_groups.append(group)
            except:
                pending_groups.append(group)
        
        if pending_groups:
            keyboard = []
            for group in pending_groups:
                keyboard.append([InlineKeyboardButton(f"📢 Join {group}", url=f"https://t.me/{group[1:]}")])
            keyboard.append([InlineKeyboardButton("✅ Check Again", callback_data=f"check_{video_id}")])
            
            pending_list = "\n".join([f"❌ {g}" for g in pending_groups])
            msg = f"🔒 Still locked!\n\nJoin these groups:\n{pending_list}"
            await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            increment_completions(video_id)
            save_completion(user_id, video_id)
            
            await query.edit_message_text("✅ Verified! Sending video...")
            await context.bot.send_video(chat_id=user_id, video=file_id, caption="🎬 Here's your video!")

# My ID command
async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await update.message.reply_text(f"🆔 Your Telegram ID: `{user_id}`", parse_mode=ParseMode.MARKDOWN)

# Admin: Set groups
async def setgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /setgroups @group1 @group2 [@group3]")
        return
    
    group1 = args[0] if len(args) > 0 else None
    group2 = args[1] if len(args) > 1 else None
    group3 = args[2] if len(args) > 2 else None
    
    set_groups(group1, group2, group3)
    
    msg = "✅ Groups saved!\n\n"
    if group1: msg += f"1️⃣ {group1}\n"
    if group2: msg += f"2️⃣ {group2}\n"
    if group3: msg += f"3️⃣ {group3}\n"
    
    await update.message.reply_text(msg)

# Admin: Edit groups
async def editgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized to use this command.")
        return
    
    args = context.args
    if len(args) < 1:
        current = get_groups()
        msg = "Current groups:\n"
        if current[0]: msg += f"1️⃣ {current[0]}\n"
        if current[1]: msg += f"2️⃣ {current[1]}\n"
        if current[2]: msg += f"3️⃣ {current[2]}\n"
        msg += "\nUsage: /editgroups @newgroup1 @newgroup2 [@newgroup3]"
        await update.message.reply_text(msg)
        return
    
    group1 = args[0] if len(args) > 0 else None
    group2 = args[1] if len(args) > 1 else None
    group3 = args[2] if len(args) > 2 else None
    
    current = get_groups()
    set_groups(group1 or current[0], group2 or current[1], group3 or current[2])
    
    await update.message.reply_text("✅ Groups updated!")

# Admin: View groups
async def viewgroups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    groups = get_groups()
    if not groups or not groups[0]:
        await update.message.reply_text("No groups configured. Use /setgroups")
        return
    
    msg = "📋 Required Groups:\n\n"
    if groups[0]: msg += f"1️⃣ {groups[0]}\n"
    if groups[1]: msg += f"2️⃣ {groups[1]}\n"
    if groups[2]: msg += f"3️⃣ {groups[2]}\n"
    
    await update.message.reply_text(msg)

# Admin: Add video
async def addvideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    context.user_data['awaiting_video'] = True
    await update.message.reply_text("📤 Send me the video file (or forward a video)")

# Handle video
async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_video'):
        video = update.message.video
        if not video:
            await update.message.reply_text("Please send a video file.")
            return
        
        file_id = video.file_id
        video_id = generate_video_id()
        save_video(video_id, file_id)
        
        bot_username = context.bot.username
        link = f"https://t.me/{bot_username}?start={video_id}"
        
        context.user_data['awaiting_video'] = False
        
        msg = f"""✅ VIDEO SAVED!

🎬 Video ID: {video_id}

🔗 YOUR LINK:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{link}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[📋 COPY LINK] - {link}

📊 Users need to join required groups first."""
        
        await update.message.reply_text(msg)

# Admin: List videos
async def videos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    videos_list = get_all_videos()
    if not videos_list:
        await update.message.reply_text("No videos added yet. Use /addvideo")
        return
    
    bot_username = context.bot.username
    msg = "📁 YOUR VIDEOS:\n\n"
    
    for vid in videos_list[:10]:
        video_id, created, clicks, completions = vid
        link = f"https://t.me/{bot_username}?start={video_id}"
        msg += f"🎬 ID: {video_id}\n"
        msg += f"🔗 {link}\n"
        msg += f"📊 Clicks: {clicks} | Completed: {completions}\n"
        msg += f"📅 Added: {created[:10]}\n\n"
    
    await update.message.reply_text(msg)

# Admin: Delete video
async def deletevideo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /deletevideo video_id")
        return
    
    video_id = args[0]
    delete_video(video_id)
    await update.message.reply_text(f"✅ Video {video_id} deleted!")

# Admin: Stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    videos_list = get_all_videos()
    total_clicks = sum(v[2] for v in videos_list)
    total_completions = sum(v[3] for v in videos_list)
    
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(DISTINCT user_id) FROM completions")
    total_users = c.fetchone()[0]
    conn.close()
    
    msg = f"""📊 BOT STATISTICS

📹 Total Videos: {len(videos_list)}
👥 Total Users: {total_users}
👆 Total Clicks: {total_clicks}
✅ Total Completions: {total_completions}
🎯 Success Rate: {int((total_completions/total_clicks)*100) if total_clicks > 0 else 0}%
"""
    
    await update.message.reply_text(msg)

# Admin: Get link for existing video
async def getlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ You are not authorized.")
        return
    
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /link video_id")
        return
    
    video_id = args[0]
    file_id = get_video(video_id)
    if not file_id:
        await update.message.reply_text("Video not found.")
        return
    
    bot_username = context.bot.username
    link = f"https://t.me/{bot_username}?start={video_id}"
    await update.message.reply_text(f"🔗 {link}")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("myid", myid))
    
    # Admin commands
    app.add_handler(CommandHandler("setgroups", setgroups))
    app.add_handler(CommandHandler("editgroups", editgroups))
    app.add_handler(CommandHandler("viewgroups", viewgroups))
    app.add_handler(CommandHandler("addvideo", addvideo))
    app.add_handler(CommandHandler("videos", videos))
    app.add_handler(CommandHandler("deletevideo", deletevideo))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("link", getlink))
    
    # Handlers
    app.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, handle_video))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # Start bot
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
