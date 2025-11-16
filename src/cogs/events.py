import random
import time
import logging
import discord
import asyncio
from collections import deque
from discord.ext import commands, tasks
from src.firebase_utils import db, get_user, update_spam_warnings, suspend_user, lift_suspension, grant_chat_reward
from src.gemini_ai import get_luffy_response, is_interesting_to_luffy

log = logging.getLogger(__name__)

# --- 1. GLOBAL STATE (REMOVED) ---
ACTIVE_DURATION = 120  # 2 minutes
REJECTION_PHRASES = ["stop", "shut up", "quiet", "not you", "go away", "bad bot"]

class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f'Logged in as {self.bot.user.name}')
        try:
            synced = await self.bot.tree.sync()
            log.info(f"Synced {len(synced)} commands")
        except Exception as e:
            log.error(f"Failed to sync commands: {e}")

    @commands.Cog.listener()
    async def on_command_error(self, interaction: discord.Interaction, error: Exception):
        log.error(f"Error in command '{interaction.command.name}' used by '{interaction.user.name}': {error}", exc_info=True)
        if interaction.response.is_done():
            await interaction.followup.send("An unexpected error occurred. The crew is looking into it!", ephemeral=True)
        else:
            await interaction.response.send_message("An unexpected error occurred. The crew is looking into it!", ephemeral=True)



    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        # Ignore DMs
        if message.guild is None:
            return

        user_id = str(message.author.id)
        player = get_user(user_id)

        # --- Suspension Enforcement ---
        if 'suspended_until' in player and player['suspended_until'] > time.time():
            return
        elif 'suspended_until' in player:
            lift_suspension(user_id)

        # --- Spam Detection ---
        current_time = time.time()
        user_message_counts_ref = db.collection('user_message_counts').document(user_id)
        user_message_counts_doc = user_message_counts_ref.get()
        if user_message_counts_doc.exists:
            user_message_counts = user_message_counts_doc.to_dict().get('timestamps', [])
        else:
            user_message_counts = []

        user_message_counts.append(current_time)
        user_message_counts = [t for t in user_message_counts if current_time - t < 5]
        user_message_counts_ref.set({'timestamps': user_message_counts})

        if len(user_message_counts) > 5:
            try:
                await message.channel.purge(limit=6, check=lambda m: m.author == message.author)
            except discord.Forbidden:
                pass # Can't delete messages

            update_spam_warnings(user_id, 1)
            warnings = player.get('spam_warnings', 0) + 1
            
            if warnings >= 3:
                suspension_end_time = time.time() + 86400 # 24 hours
                suspend_user(user_id, suspension_end_time)
                await message.channel.send(f"That's it! {message.author.mention}, you're suspended from the crew for 24 hours!")
            else:
                await message.channel.send(f"Oi! {message.author.mention}, stop spamming or I'll throw you off the ship! (Warning {warnings}/3)")
            return

        channel_id = str(message.channel.id)
        
        # --- "Take a Hint" Logic ---
        if any(phrase in message.content.lower() for phrase in REJECTION_PHRASES):
            active_conversations_ref = db.collection('active_conversations').document(channel_id)
            if active_conversations_ref.get().exists:
                active_conversations_ref.delete()
                await message.reply("Oh, okay...")
            return

        # --- 2. MESSAGE BUFFER ---
        message_buffers_ref = db.collection('message_buffers').document(channel_id)
        message_buffers_doc = message_buffers_ref.get()
        if message_buffers_doc.exists:
            message_buffer = message_buffers_doc.to_dict().get('messages', [])
        else:
            message_buffer = []
        
        message_buffer.append(f"{message.author.name}: {message.content}")
        if len(message_buffer) > 10:
            message_buffer.pop(0)
        message_buffers_ref.set({'messages': message_buffer})


        # --- 3. ACTIVE MODE & THE JUDGE ---
        server_id = str(message.guild.id)
        server_settings = self.bot.settings.get(server_id, {})
        intrusion_level = server_settings.get('intrusion_level', 20)

        is_mention = self.bot.user.mentioned_in(message)
        contains_luffy = 'luffy' in message.content.lower()
        
        active_conversations_ref = db.collection('active_conversations').document(channel_id)
        active_conversations_doc = active_conversations_ref.get()
        is_active = False
        if active_conversations_doc.exists:
            is_active = time.time() - active_conversations_doc.to_dict().get('timestamp', 0) < ACTIVE_DURATION

        should_reply = False
        message_is_interesting = False

        if is_mention or contains_luffy:
            should_reply = True
            active_conversations_ref.set({'timestamp': time.time()})
        elif is_active:
            if random.randint(1, 100) <= 50:
                should_reply = True
        elif random.randint(1, 100) <= intrusion_level:
            if await is_interesting_to_luffy(message_buffer):
                message_is_interesting = True
                should_reply = True
                active_conversations_ref.set({'timestamp': time.time()})

        # AI Chat Rewards
        reward_chance = 10 # 10% base chance
        if is_active:
            reward_chance = 30 # 30% chance during active conversation
        if message_is_interesting or random.randint(1, 100) <= reward_chance:
            last_reward_time = player.get('chat_reward_cooldown_ends')
            if not last_reward_time or time.time() > last_reward_time:
                berry_reward = random.randint(5, 25)
                xp_reward = random.randint(1, 5)
                grant_chat_reward(user_id, berry_reward, xp_reward)

        if should_reply:
            trigger = "Mention" if is_mention else "Keyword" if contains_luffy else "Intrusion"
            log.info(f"Trigger: {trigger} | Server: {message.guild.name} | User {message.author.name} said: {message.content}")
            
            # Get conversation history
            history = "\n".join(message_buffer)

            async with message.channel.typing():
                try:
                    response_text = get_luffy_response(message.author.id, history)
                    
                    log.info(f"Luffy bot replied: {response_text}")
                    await message.reply(response_text)
                except Exception as e:
                    log.error(f"Error generating response: {e}")
                    await message.reply("Argh! I can't seem to think of a response right now. Maybe ask me later?")

async def setup(bot):
    await bot.add_cog(Events(bot))
