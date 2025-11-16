import os
import asyncio
import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import logging
import time

from flask import Flask, request, abort
import threading
from src.firebase_utils import reward_vote

# --- Logging Setup ---
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, handlers=[
    logging.FileHandler("bot.log"),
    logging.StreamHandler()
])
log.info("Luffy bot is starting...")

load_dotenv()

# --- Flask Web Server ---
app = Flask(__name__)

@app.route('/topgg-webhook', methods=['POST'])
def topgg_webhook():
    auth = request.headers.get('Authorization')
    if auth != os.getenv('TOPGG_AUTH_TOKEN'):
        abort(401)

    data = request.json
    if data.get('type') == 'upvote':
        user_id = data.get('user')
        print(f"Received upvote from {user_id}")
        reward_vote(user_id)
    
    return 'OK'

def run_flask():
    app.run(host='0.0.0.0', port=os.environ.get('PORT', 8080))

# --- Discord Bot ---
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

from src.firebase_utils import db

bot = commands.Bot(command_prefix='!', intents=intents)

# Load server settings from Firestore
try:
    settings_ref = db.collection('config').document('settings')
    settings_doc = settings_ref.get()
    if settings_doc.exists:
        bot.settings = settings_doc.to_dict()
        log.info("Successfully loaded server settings from Firestore.")
    else:
        log.warning("Firestore 'settings' document not found! Using empty settings.")
        bot.settings = {}
except Exception as e:
    log.error(f"Failed to load settings from Firestore: {e}")
    bot.settings = {}

@tasks.loop(hours=6)
async def cleanup_task():
    log.info("Running periodic cleanup task...")
    now = time.time()
    
    # Cleanup active_conversations (older than 2 minutes)
    active_conv_ref = db.collection('active_conversations')
    stale_convs = active_conv_ref.where('timestamp', '<', now - 120).stream()
    for conv in stale_convs:
        log.info(f"Deleting stale active conversation: {conv.id}")
        conv.reference.delete()

    # Cleanup chat_sessions (older than 1 day)
    chat_sessions_ref = db.collection('chat_sessions')
    stale_sessions = chat_sessions_ref.where('last_used', '<', now - 86400).stream()
    for session in stale_sessions:
        log.info(f"Deleting stale chat session: {session.id}")
        session.reference.delete()
    log.info("Cleanup task finished.")

async def main():
    await bot.load_extension('src.cogs.events')
    await bot.load_extension('src.cogs.admin')
    await bot.load_extension('src.cogs.game')
    await bot.load_extension('src.cogs.ship')
    await bot.load_extension('src.cogs.cosmetic')
    
    cleanup_task.start()
    
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    # Start the bot
    await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())