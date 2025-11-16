import io
import random
import time
import json
import math
import discord
import logging
import asyncio
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
from google.cloud import firestore
from src.firebase_utils import get_user, update_berries, update_bounty, add_to_crew, db, get_ship, claim_daily_reward, gift_berries, buy_item, sell_item, add_ship_xp, use_medical_kit, escrow_wager, resolve_duel, create_auction, bid_on_auction, claim_sold_auction, claim_won_auction, buy_title, equip_title, update_recruit_cooldown, update_private_adventure_cooldown, update_auction_claim_cooldown, update_wanted_poster_cooldown
from src.gemini_ai import get_adventure_description, get_recruit_description

log = logging.getLogger(__name__)

CHARACTERS = {
    "Common": ["Alvida", "Higuma", "Morgan"],
    "Rare": ["Buggy", "Arlong", "Wapol"],
    "Legendary": ["Crocodile", "Enel", "Lucci"],
    "Mythical": ["Shanks", "Mihawk", "Rayleigh"]
}
RARITY_CHANCES = {"Common": 60, "Rare": 30, "Legendary": 9, "Mythical": 1}

async def create_wanted_poster(user, bounty):
    # Load template and font
    template = Image.open("wanted_template.png")
    name_font = ImageFont.truetype("font.ttf", 105)
    bounty_font = ImageFont.truetype("font.ttf", 155)
    
    # Get user avatar
    avatar_data = await user.display_avatar.read()
    avatar = Image.open(io.BytesIO(avatar_data)).resize((880, 880))
    
    # Paste avatar
    template.paste(avatar, (360, 640))
    
    # Draw text
    draw = ImageDraw.Draw(template)
    draw.text((585, 1735), user.name, font=name_font, fill="black")
    draw.text((850, 1870), f"{bounty:,}", font=bounty_font, fill="black")
    
    # Save to buffer
    buffer = io.BytesIO()
    template.save(buffer, format="PNG")
    buffer.seek(0)
    
    return discord.File(buffer, filename="wanted.png")

class Game(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.items = db.collection('config').document('items').get().to_dict()
        self.cosmetics = db.collection('config').document('cosmetics').get().to_dict()

    shop = app_commands.Group(name="shop", description="Buy and sell items.")
    auction = app_commands.Group(name="auction", description="Manage auctions.")

    @app_commands.command(name="profile", description="Check your pirate profile.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def profile(self, interaction: discord.Interaction, user: discord.User = None):
        log.info(f"{interaction.user.name} used /profile")
        if user is None:
            user = interaction.user

        player = get_user(str(user.id))
        
        embed_title = f"{user.name}'s Profile"
        current_title = player.get('current_title')
        if current_title:
            # Clean up the title string e.g., "Title: 'Rookie'" -> "Rookie"
            clean_title = current_title.replace("Title: ", "").strip("'")
            embed_title = f"[{clean_title}] {user.name}"

        embed = discord.Embed(title=embed_title, color=discord.Color.dark_blue())
        embed.set_thumbnail(url=user.display_avatar.url)

        embed.add_field(name="HP", value=f"{player.get('hp', 100)}/{player.get('max_hp', 100)}", inline=True)
        embed.add_field(name="Berries", value=f"{player.get('berries', 0):,}", inline=True)
        embed.add_field(name="Bounty", value=f"{player.get('bounty', 0):,}", inline=True)

        ship_info = "Not in a ship"
        if player.get('ship_id'):
            ship = get_ship(player['ship_id'])
            if ship:
                ship_info = ship['name']
        embed.add_field(name="Ship", value=ship_info, inline=True)

        crew = player.get('crew', [])
        if crew:
            embed.add_field(name="Crew", value=", ".join(crew), inline=False)

        bag = player.get('bag', {})
        if bag:
            bag_contents = [f"{item.replace('_', ' ').title()}: {quantity}" for item, quantity in bag.items() if quantity > 0]
            if bag_contents:
                embed.add_field(name="Bag", value="\n".join(bag_contents), inline=False)

        daily_cooldown = player.get('daily_claim_timestamp')
        if daily_cooldown and time.time() - daily_cooldown < 79200:
            remaining_time = time.strftime('%Hh %Mm %Ss', time.gmtime(79200 - (time.time() - daily_cooldown)))
            embed.add_field(name="Daily Cooldown", value=remaining_time, inline=True)

        duel_cooldown = player.get('duel_cooldown')
        if duel_cooldown and time.time() - duel_cooldown < 600:
            remaining_time = time.strftime('%Mm %Ss', time.gmtime(600 - (time.time() - duel_cooldown)))
            embed.add_field(name="Duel Cooldown", value=remaining_time, inline=True)

        recruit_cooldown = player.get('last_recruit_timestamp')
        if recruit_cooldown and time.time() - recruit_cooldown < 600:
            remaining_time = time.strftime('%Mm %Ss', time.gmtime(600 - (time.time() - recruit_cooldown)))
            embed.add_field(name="Recruit Cooldown", value=remaining_time, inline=True)

        private_adventure_cooldown = player.get('last_private_adventure_timestamp')
        if private_adventure_cooldown and time.time() - private_adventure_cooldown < 3600:
            remaining_time = time.strftime('%Hh %Mm %Ss', time.gmtime(3600 - (time.time() - private_adventure_cooldown)))
            embed.add_field(name="Private Adventure Cooldown", value=remaining_time, inline=True)

        auction_claim_cooldown = player.get('last_auction_claim_timestamp')
        if auction_claim_cooldown and time.time() - auction_claim_cooldown < 3600:
            remaining_time = time.strftime('%Hh %Mm %Ss', time.gmtime(3600 - (time.time() - auction_claim_cooldown)))
            embed.add_field(name="Auction Claim Cooldown", value=remaining_time, inline=True)

        wanted_poster_cooldown = player.get('last_wanted_poster_timestamp')
        if wanted_poster_cooldown and time.time() - wanted_poster_cooldown < 60:
            remaining_time = time.strftime('%Mm %Ss', time.gmtime(60 - (time.time() - wanted_poster_cooldown)))
            embed.add_field(name="Wanted Poster Cooldown", value=remaining_time, inline=True)

        chat_reward_cooldown_ends = player.get('chat_reward_cooldown_ends')
        if chat_reward_cooldown_ends and time.time() < chat_reward_cooldown_ends:
            remaining_time = time.strftime('%Mm %Ss', time.gmtime(chat_reward_cooldown_ends - time.time()))
            next_reward_text = f"in {remaining_time}"
        else:
            next_reward_text = "Ready!"
        
        last_reward = player.get('last_reward_amount', 0)
        embed.add_field(name="Chat Rewards", value=f"Last Reward: {last_reward} Berries\nNext Reward: {next_reward_text}", inline=False)

        await interaction.response.send_message(embed=embed)

    @profile.error
    async def on_profile_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"You can check your profile again in {int(error.retry_after)}s.", ephemeral=True)

    @app_commands.command(name="bal", description="Check your balance and ship info.")
    @app_commands.checks.cooldown(1, 5, key=lambda i: i.user.id)
    async def bal(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /bal")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        embed = discord.Embed(title=f"{interaction.user.name}'s Balance", color=discord.Color.green())
        
        embed.add_field(name="Berries", value=player.get('berries', 0), inline=True)

        ship_info = "Not in a ship"
        if player.get('ship_id'):
            ship = get_ship(player['ship_id'])
            if ship:
                ship_info = ship['name']
        
        embed.add_field(name="Ship", value=ship_info, inline=True)

        await interaction.response.send_message(embed=embed)

    @bal.error
    async def on_bal_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"You can check your balance again in {int(error.retry_after)}s.", ephemeral=True)

    @app_commands.command(name="adventure", description="Go on a pirate adventure!")
    @app_commands.checks.cooldown(1, 14400, key=lambda i: i.user.id)
    async def adventure(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /adventure")
        user_id = str(interaction.user.id)
        
        scenarios = ["Fight Marines", "Steal Treasure", "Find Meat", "Train"]
        scenario = random.choice(scenarios)
        success = random.randint(1, 100) <= 70

        await interaction.response.defer()
        description = await get_adventure_description(scenario, success)

        if success:
            bounty_gain = random.randint(500, 5000)
            berry_gain = random.randint(500, 2000)
            
            player = get_user(user_id)
            if player.get('ship_id'):
                ship = get_ship(player['ship_id'])
                if ship:
                    crew_bonus = ship.get('crew_bonus', 1.0)
                    berry_gain = int(berry_gain * crew_bonus)

            update_bounty(user_id, bounty_gain)
            update_berries(user_id, berry_gain)
            result_text = f"You gained {bounty_gain:,} bounty and {berry_gain:,} berries."
        else:
            berry_loss = random.randint(100, 1000)
            update_berries(user_id, -berry_loss)
            result_text = f"You lost {berry_loss:,} berries."

        await interaction.followup.send(f"**{description}**\n{result_text}")

    @app_commands.command(name="private", description="Go on a private pirate adventure! (Cost: 1000 Berries)")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: i.user.id)
    async def private_adventure(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /adventure private")
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        cost = 1000
        if player['berries'] < cost:
            await interaction.followup.send(f"You need {cost} berries for a private adventure!", ephemeral=True)
            return

        update_berries(user_id, -cost)
        update_private_adventure_cooldown(user_id)

        scenarios = ["Explore a Hidden Island", "Raid a Marine Base", "Hunt a Sea King", "Discover an Ancient Ruin"]
        scenario = random.choice(scenarios)
        success = random.randint(1, 100) <= 85 # Higher success chance for private adventures

        description = await get_adventure_description(scenario, success)

        if success:
            bounty_gain = random.randint(1000, 10000)
            berry_gain = random.randint(1000, 5000)
            
            if player.get('ship_id'):
                ship = get_ship(player['ship_id'])
                if ship:
                    crew_bonus = ship.get('crew_bonus', 1.0)
                    berry_gain = int(berry_gain * crew_bonus)

            update_bounty(user_id, bounty_gain)
            update_berries(user_id, berry_gain)
            result_text = f"You gained {bounty_gain:,} bounty and {berry_gain:,} berries."
        else:
            berry_loss = random.randint(500, 2000)
            update_berries(user_id, -berry_loss)
            result_text = f"You lost {berry_loss:,} berries."

        await interaction.followup.send(f"**{description}**\n{result_text}")

    @adventure.error
    async def on_adventure_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"I'm sleeping... come back later! You can go on another adventure in {time.strftime('%Hh %Mm %Ss', time.gmtime(error.retry_after))}", ephemeral=True)

    @app_commands.command(name="recruit", description="Recruit a new crew member!")
    @app_commands.checks.cooldown(1, 600, key=lambda i: i.user.id)
    async def recruit(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /recruit")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if player['berries'] < 500:
            await interaction.response.send_message("You don't have enough berries to recruit! You need 500 berries.")
            return

        await interaction.response.defer()

        update_berries(user_id, -500)

        rarity = random.choices(list(RARITY_CHANCES.keys()), weights=list(RARITY_CHANCES.values()))[0]
        character = random.choice(CHARACTERS[rarity])

        add_to_crew(user_id, character)
        update_recruit_cooldown(user_id)

        description = await get_recruit_description(character)

        await interaction.followup.send(f"**{description}**\nYou recruited {character} ({rarity})!")

    @recruit.error
    async def on_recruit_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"You can recruit again in {time.strftime('%Hh %Mm %Ss', time.gmtime(error.retry_after))}", ephemeral=True)

    @app_commands.command(name="leaderboard", description="See the top 5 pirates.")
    async def leaderboard(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /leaderboard")
        
        # Efficiently query the top 5 pirates by bounty
        query = db.collection('pirates').order_by('bounty', direction=firestore.Query.DESCENDING).limit(5)
        top_pirates = query.stream()

        embed = discord.Embed(
            title="Top 5 Pirates",
            color=discord.Color.dark_red()
        )

        i = 1
        for user_doc in top_pirates:
            try:
                user_id = int(user_doc.id)
                user = await self.bot.fetch_user(user_id)
                player_data = user_doc.to_dict()
                embed.add_field(
                    name=f"{i}. {user.name}",
                    value=f"Bounty: {player_data.get('bounty', 0):,}",
                    inline=False
                )
                i += 1
            except (discord.NotFound, ValueError):
                log.warning(f"Could not find user with ID: {user_doc.id} for leaderboard.")
                continue
        
        if i == 1: # No pirates found
            embed.description = "The seas are quiet... no top pirates to show yet."

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="event", description="Check the current world event.")
    async def event(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /event")
        events_doc = db.collection('config').document('events').get()
        if events_doc.exists:
            active_event = events_doc.to_dict().get('active_event')
        else:
            active_event = None
        
        if active_event:
            await interaction.response.send_message(f"Current event: **{active_event}**!")
        else:
            await interaction.response.send_message("There is no active event.")

    @app_commands.command(name="daily", description="Claim your daily reward.")
    async def daily(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /daily")
        await interaction.response.defer()
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        last_claim = player.get('daily_claim_timestamp')
        if last_claim:
            # 22 hours = 79200 seconds
            if time.time() - last_claim < 79200:
                remaining_time = time.strftime('%Hh %Mm %Ss', time.gmtime(79200 - (time.time() - last_claim)))
                await interaction.followup.send(f"You have already claimed your daily reward. Try again in {remaining_time}.")
                return

        base_reward = 500
        reward = base_reward
        ship_xp_gain = 0

        if player.get('ship_id'):
            ship = get_ship(player['ship_id'])
            reward = int(base_reward * 1.5)
            ship_xp_gain = 100

            if ship:
                crew_bonus = ship.get('crew_bonus', 1.0)
                reward = int(reward * crew_bonus)
                ship_xp_gain = int(ship_xp_gain * crew_bonus)
                
                badge_id = ship.get('equipped_badge')
                if badge_id:
                    items = db.collection('config').document('items').get().to_dict()
                    badge = items.get(badge_id)
                    if badge and badge.get('effect', {}).get('type') == 'reward_boost':
                        reward = int(reward * (1 + badge['effect']['value']))
                    if badge and badge.get('effect', {}).get('type') == 'xp_boost':
                        ship_xp_gain = int(ship_xp_gain * (1 + badge['effect']['value']))
            
            add_ship_xp(player['ship_id'], ship_xp_gain)
            ship_cog = self.bot.get_cog('Ship')
            if ship_cog:
                await ship_cog.check_ship_level_up(player['ship_id'])

        claim_daily_reward(user_id, reward)
        await interaction.followup.send(f"You have received {reward} Berries!")

    @app_commands.command(name="bag", description="Check your inventory.")
    async def bag(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /bag")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        bag = player.get('bag')
        if not bag:
            await interaction.response.send_message("Your bag is empty!")
            return

        embed = discord.Embed(title=f"{interaction.user.name}'s Bag", color=discord.Color.gold())
        for item, quantity in bag.items():
            embed.add_field(name=item, value=quantity, inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="gift", description="Gift berries to another player.")
    async def gift(self, interaction: discord.Interaction, user: discord.User, amount: int):
        log.info(f"{interaction.user.name} used /gift with user={user.name} amount={amount}")
        if amount <= 0:
            await interaction.response.send_message("You must gift a positive amount of berries.")
            return

        sender_id = str(interaction.user.id)
        recipient_id = str(user.id)

        if sender_id == recipient_id:
            await interaction.response.send_message("You cannot gift berries to yourself.")
            return

        try:
            gift_berries(sender_id, recipient_id, amount)
            await interaction.response.send_message(f"You gave {user.name} {amount} Berries!")
        except Exception as e:
            await interaction.response.send_message(str(e))

    @app_commands.command(name="vote", description="Get the link to vote for the bot and get 10,000 Berries!")
    async def vote(self, interaction: discord.Interaction):
        await interaction.response.send_message("Shishishi! Click here to vote for me and get 10,000 Berries! \nhttps://top.gg/bot/1436703976350552084/vote")

    @app_commands.command(name="coinflip", description="Gamble your berries in a coin flip!")
    @app_commands.checks.cooldown(1, 10, key=lambda i: i.user.id)
    async def coinflip(self, interaction: discord.Interaction, amount: int, side: str):
        log.info(f"{interaction.user.name} used /coinflip with amount={amount} side={side}")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if amount <= 0:
            await interaction.response.send_message("You must bet a positive amount of berries.")
            return

        if player['berries'] < amount:
            await interaction.response.send_message("You don't have enough berries for this bet.")
            return

        side = side.lower()
        if side not in ["heads", "tails"]:
            await interaction.response.send_message("Please choose either 'heads' or 'tails'.")
            return

        await interaction.response.defer()

        result = random.choice(["heads", "tails"])

        if side == result:
            update_berries(user_id, amount)
            await interaction.followup.send(f"It's {result}! You won {amount * 2} berries!")
        else:
            update_berries(user_id, -amount)
            await interaction.followup.send(f"It's {result}! You lost {amount} berries.")

    @coinflip.error
    async def on_coinflip_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"You can flip a coin again in {int(error.retry_after)}s.", ephemeral=True)

    shop = app_commands.Group(name="shop", description="Buy and sell items.")

    @shop.command(name="list", description="List all items in the shop.")
    async def shop_list(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /shop list")
        embed = discord.Embed(title="Shop", color=discord.Color.blue())
        for item_id, item in self.items.items():
            if not item.get('limited_time'):
                embed.add_field(name=f"{item['name']} - {item['price']} Berries", value=f"ID: `{item_id}`\n{item['description']}", inline=False)
        await interaction.response.send_message(embed=embed)

    @shop.command(name="limited", description="List all limited-time items in the shop.")
    async def shop_limited(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /shop limited")
        embed = discord.Embed(title="Limited-Time Shop", color=discord.Color.gold())
        for item_id, item in self.items.items():
            if item.get('limited_time'):
                embed.add_field(name=f"{item['name']} - {item['price']} Berries", value=f"ID: `{item_id}`\n{item['description']}", inline=False)
        await interaction.response.send_message(embed=embed)

    @shop.command(name="buy", description="Buy an item from the shop.")
    async def shop_buy(self, interaction: discord.Interaction, item_id: str, quantity: int = 1):
        log.info(f"{interaction.user.name} used /shop buy with item_id={item_id} quantity={quantity}")
        await interaction.response.defer()

        if quantity <= 0 or quantity > 100:
            await interaction.followup.send("Quantity must be between 1 and 100.")
            return

        item = self.items.get(item_id)
        if not item:
            await interaction.followup.send("Item not found.")
            return

        user_id = str(interaction.user.id)
        player = get_user(user_id)
        total_cost = item['price'] * quantity

        if player['berries'] < total_cost:
            await interaction.followup.send("You don't have enough berries.")
            return

        try:
            buy_item(user_id, item_id, quantity, item['price'])
            if player.get('ship_id'):
                xp_gain = int(total_cost * 0.1)
                ship = get_ship(player['ship_id'])
                if ship:
                    crew_bonus = ship.get('crew_bonus', 1.0)
                    xp_gain = int(xp_gain * crew_bonus)

                    badge_id = ship.get('equipped_badge')
                    if badge_id:
                        items = db.collection('config').document('items').get().to_dict()
                        badge = items.get(badge_id)
                        if badge and badge.get('effect', {}).get('type') == 'xp_boost':
                            xp_gain = int(xp_gain * (1 + badge['effect']['value']))
                add_ship_xp(player['ship_id'], xp_gain)
                ship_cog = self.bot.get_cog('Ship')
                if ship_cog:
                    await ship_cog.check_ship_level_up(player['ship_id'])
            await interaction.followup.send(f"You bought {quantity}x {item['name']}!")
        except Exception as e:
            await interaction.followup.send(f"An error occurred: {e}")

    @shop.command(name="sell", description="Sell an item from your bag.")
    async def shop_sell(self, interaction: discord.Interaction, item_id: str, quantity: int = 1):
        log.info(f"{interaction.user.name} used /shop sell with item_id={item_id} quantity={quantity}")
        if quantity <= 0 or quantity > 100:
            await interaction.response.send_message("Quantity must be between 1 and 100.")
            return
        
        item = self.items.get(item_id)
        if not item:
            await interaction.response.send_message("Item not found.")
            return

        user_id = str(interaction.user.id)
        player = get_user(user_id)
        
        if player.get('bag', {}).get(item_id, 0) < quantity:
            await interaction.response.send_message("You don't have enough of this item to sell.")
            return

        sell_price = math.floor(item['price'] * 0.5)
        total_sell_price = sell_price * quantity

        try:
            sell_item(user_id, item_id, quantity, sell_price)
            await interaction.response.send_message(f"You sold {quantity}x {item['name']} for {total_sell_price} Berries!")
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}")

    @app_commands.command(name="use", description="Use an item from your bag.")
    async def use(self, interaction: discord.Interaction, item_id: str):
        log.info(f"{interaction.user.name} used /use with item_id={item_id}")
        user_id = str(interaction.user.id)

        if item_id == "medical_kit":
            try:
                use_medical_kit(user_id)
                await interaction.response.send_message("You used a Medical Kit and healed 50 HP!")
            except Exception as e:
                await interaction.response.send_message(str(e))
        else:
            await interaction.response.send_message("This item is not usable.")

    @app_commands.command(name="duel", description="Challenge another player to a duel.")
    async def duel(self, interaction: discord.Interaction, user: discord.User, wager: int = 0):
        log.info(f"{interaction.user.name} used /duel with user={user.name} wager={wager}")
        
        challenger_id = str(interaction.user.id)
        opponent_id = str(user.id)

        if challenger_id == opponent_id:
            await interaction.response.send_message("You cannot duel yourself.")
            return

        challenger = get_user(challenger_id)
        opponent = get_user(opponent_id)

        # Cooldown check
        last_duel = challenger.get('duel_cooldown')
        if last_duel and time.time() - last_duel < 600: # 10 minutes
            remaining_time = time.strftime('%Mm %Ss', time.gmtime(600 - (time.time() - last_duel)))
            await interaction.response.send_message(f"You are on cooldown. You can duel again in {remaining_time}.")
            return

        if wager < 0:
            await interaction.response.send_message("Wager must be non-negative.")
            return
            
        if challenger['berries'] < wager:
            await interaction.response.send_message("You don't have enough berries for this wager.")
            return
            
        if opponent['berries'] < wager:
            await interaction.response.send_message(f"{user.name} doesn't have enough berries for this wager.")
            return

        view = DuelView(self.bot, challenger_id, opponent_id, wager)
        await interaction.response.send_message(f"{user.mention}, {interaction.user.name} has challenged you to a duel for {wager} Berries! Do you accept?", view=view)

    auction = app_commands.Group(name="auction", description="Manage auctions.")

    @auction.command(name="list", description="List all active auctions.")
    async def auction_list(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /auction list")
        
        auctions_ref = db.collection('auctions').where('end_time', '>', time.time()).stream()
        
        embed = discord.Embed(title="Active Auctions", color=discord.Color.purple())
        
        auctions_found = False
        for auction_doc in auctions_ref:
            auctions_found = True
            auction = auction_doc.to_dict()
            end_time = auction['end_time']
            remaining_time = time.strftime('%Hh %Mm %Ss', time.gmtime(end_time - time.time()))
            embed.add_field(
                name=f"{auction['item_name']} (Qty: {auction['quantity']})",
                value=f"Current Bid: {auction['current_bid']} Berries\nEnds In: {remaining_time}\nAuction ID: `{auction_doc.id}`",
                inline=False
            )
            
        if not auctions_found:
            embed.description = "There are no active auctions."
            
        await interaction.response.send_message(embed=embed)

    @auction.command(name="sell", description="Sell an item or crew member on the auction house.")
    async def auction_sell(self, interaction: discord.Interaction, item_type: str, item_id: str, quantity: int, starting_bid: int):
        log.info(f"{interaction.user.name} used /auction sell with item_type={item_type} item_id={item_id} quantity={quantity} starting_bid={starting_bid}")
        
        if item_type not in ['item', 'crew']:
            await interaction.response.send_message("Invalid item type. Must be 'item' or 'crew'.")
            return
            
        if quantity <= 0:
            await interaction.response.send_message("Quantity must be positive.")
            return
            
        if starting_bid < 0:
            await interaction.response.send_message("Starting bid must be non-negative.")
            return

        seller_id = str(interaction.user.id)
        seller_name = interaction.user.name
        
        item_name = "TBD"
        if item_type == 'item':
            items = db.collection('config').document('items').get().to_dict()
            if item_id not in items:
                await interaction.response.send_message("Item not found.")
                return
            item_name = items[item_id]['name']
        elif item_type == 'crew':
            item_name = item_id

        try:
            auction_id = create_auction(seller_id, item_type, item_id, item_name, quantity, seller_name, starting_bid)
            await interaction.response.send_message(f"You have listed {item_name} on the Auction House for {starting_bid} Berries! (Auction ID: `{auction_id}`)")
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}")

    @auction.command(name="bid", description="Bid on an auction.")
    async def auction_bid(self, interaction: discord.Interaction, auction_id: str, bid_amount: int):
        log.info(f"{interaction.user.name} used /auction bid with auction_id={auction_id} bid_amount={bid_amount}")
        
        if bid_amount <= 0:
            await interaction.response.send_message("Bid amount must be positive.")
            return

        bidder_id = str(interaction.user.id)

        try:
            bid_on_auction(bidder_id, auction_id, bid_amount)
            await interaction.response.send_message("You are now the highest bidder!")
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}")

    @auction.command(name="claim", description="Claim winnings or sold items from ended auctions.")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: i.user.id)
    async def auction_claim(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /auction claim")
        await interaction.response.defer()
        user_id = str(interaction.user.id)

        claimed_something = False

        # Claim sold auctions
        sold_auctions_ref = db.collection('auctions').where('seller_id', '==', user_id).stream()
        for auction_doc in sold_auctions_ref:
            auction_data = auction_doc.to_dict()
            if auction_data['end_time'] <= time.time():
                try:
                    payout = claim_sold_auction(user_id, auction_doc.id)
                    update_auction_claim_cooldown(user_id)
                    await interaction.followup.send(f"Your auction for {auction_data['item_name']} sold! You receive {payout} Berries (after 5% tax).")
                    claimed_something = True
                except Exception as e:
                    await interaction.followup.send(f"An error occurred while claiming sold auction {auction_doc.id}: {e}")

        # Claim won auctions
        won_auctions_ref = db.collection('auctions').where('highest_bidder_id', '==', user_id).stream()
        for auction_doc in won_auctions_ref:
            auction_data = auction_doc.to_dict()
            if auction_data['end_time'] <= time.time():
                try:
                    claim_won_auction(user_id, auction_doc.id)
                    update_auction_claim_cooldown(user_id)
                    await interaction.followup.send(f"You won the auction for {auction_data['item_name']}!")
                    claimed_something = True
                except Exception as e:
                    await interaction.followup.send(f"An error occurred while claiming won auction {auction_doc.id}: {e}")
        
        if claimed_something:
            await interaction.followup.send("You have claimed all available auction items and earnings.")
        else:
            await interaction.followup.send("You have no ended auctions to claim.")

    @auction_claim.error
    async def on_auction_claim_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"You can claim again in {time.strftime('%Hh %Mm %Ss', time.gmtime(error.retry_after))}", ephemeral=True)

    asset = app_commands.Group(name="asset", description="Download various game assets.")

    @asset.command(name="wanted_poster", description="Download your wanted poster.")
    @app_commands.checks.cooldown(1, 60, key=lambda i: i.user.id)
    async def asset_wanted_poster(self, interaction: discord.Interaction, user: discord.User = None):
        log.info(f"{interaction.user.name} used /asset wanted_poster")
        if user is None:
            user = interaction.user
        
        player = get_user(str(user.id))
        
        await interaction.response.defer()

        wanted_poster = await create_wanted_poster(user, player['bounty'])
        update_wanted_poster_cooldown(str(user.id))
        
        await interaction.followup.send(file=wanted_poster)

    @asset_wanted_poster.error
    async def on_asset_wanted_poster_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(f"You're on cooldown! Try again in {int(error.retry_after)}s", ephemeral=True)

    @app_commands.command(name="guide", description="Get a guide to the Grand Line!")
    async def guide(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /guide")
        embed = discord.Embed(title="Welcome to the Grand Line!", color=discord.Color.gold())
        embed.set_thumbnail(url="https://img.freepik.com/premium-vector/pirate-ship-vintage-illustration_1188798-270.jpg")
        embed.description = (
            "Ahoy, matey! Welcome to the world of pirates! I'm Luffy, and I'm gonna be King of the Pirates! "
            "Join my crew and let's find the One Piece! Here's how you can get started:"
        )

        embed.add_field(name="⛵ Your Ship", value=(
            "- `/ship create <name>`: Start your own pirate crew!\n"
            "- `/ship join <name>`: Join an existing crew!\n"
            "- `/ship info`: See your ship's stats.\n"
            "- `/ship leave`: Abandon ship (if you're not the captain!).\n"
            "- `/ship disband`: Captains can disband their ship.\n"
            "- `/ship promote @user`: Promote a crew member to officer.\n"
            "- `/ship demote @user`: Demote an officer to a member.\n"
            "- `/ship upgrade`: Improve your ship's hull or storage.\n"
            "- `/ship storage deposit <item_id> <quantity>`: Store items on your ship.\n"
            "- `/ship storage view`: See what's in your ship's hold.\n"
            "- `/ship war <target_ship_name> [wager]`: Challenge another ship to battle!\n"
            "- `/ship repair [amount]`: Repair your ship using repair tools."
        ), inline=False)

        embed.add_field(name="💰 Economy & Items", value=(
            "- `/vote`: Get the link to vote for the bot and get 10,000 Berries!\n"
            "- `/bal`: Check your berries (money) and ship info.\n"
            "- `/daily`: Claim your daily reward!\n"
            "- `/shop list`: See what items are for sale.\n"
            "- `/shop limited`: Check out limited-time offers!\n"
            "- `/shop buy <item_id> [quantity]`: Buy items from the shop.\n"
            "- `/shop sell <item_id> [quantity]`: Sell items from your bag.\n"
            "- `/bag`: See what items you have.\n"
            "- `/use <item_id>`: Use an item from your bag (like a medical kit!).\n"
            "- `/gift @user <amount>`: Give berries to a friend!"
        ), inline=False)

        embed.add_field(name="⚔️ Adventures & Bounties", value=(
            "- `/adventure`: Go on a random adventure!\n"
            "- `/adventure private`: Embark on a more rewarding (and costly) private adventure!\n"
            "- `/recruit`: Recruit a new crew member!\n"
            "- `/duel @user [wager]`: Challenge another pirate to a duel!\n"
            "- `/asset wanted_poster [user]`: Generate a wanted poster!\n"
            "- `/leaderboard`: See the top pirates by bounty!\n"
            "- `/event`: Check for active world events!"
        ), inline=False)

        embed.add_field(name="🏴‍☠️ Auctions", value=(
            "- `/auction list`: See items up for bid.\n"
            "- `/auction sell <item_type> <item_id> <quantity> <starting_bid>`: Sell your treasures!\n"
            "- `/auction bid <auction_id> <bid_amount>`: Bid on items!\n"
            "- `/auction claim`: Claim your winnings or earnings!"
        ), inline=False)

        embed.add_field(name="✨ Customization", value=(
            "- `/profile [user]`: Check your (or another pirate's) profile.\n"
            "- `/title buy <title_id> <price>`: Unlock new titles!\n"
            "- `/title equip <title_id>`: Show off your title!\n"
            "- `/ship badge equip <badge_id>`: Equip a badge to your ship!\n"
            "- `/ship badge unequip`: Remove your ship's badge."
        ), inline=False)

        embed.add_field(name="🎰 Gambling", value=(
            "- `/coinflip <amount> <side>`: Bet your berries on a coin flip!"
        ), inline=False)

        embed.set_footer(text="Shishishi! Now go out there and become a great pirate!")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Game(bot))

class DuelView(discord.ui.View):
    def __init__(self, bot, challenger_id, opponent_id, wager):
        super().__init__(timeout=60)
        self.bot = bot
        self.challenger_id = challenger_id
        self.opponent_id = opponent_id
        self.wager = wager

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.opponent_id):
            await interaction.response.send_message("You are not the one being challenged.", ephemeral=True)
            return
        
        await interaction.response.defer()

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        try:
            escrow_wager(self.challenger_id, self.opponent_id, self.wager)
        except Exception as e:
            await interaction.followup.send(f"An error occurred while escrowing the wager: {e}")
            return

        challenger = get_user(self.challenger_id)
        opponent = get_user(self.opponent_id)

        challenger_hp = challenger.get('hp', 100)
        opponent_hp = opponent.get('hp', 100)
        
        challenger_max_hp = challenger.get('max_hp', 100)
        opponent_max_hp = opponent.get('max_hp', 100)

        challenger_user = await self.bot.fetch_user(self.challenger_id)
        opponent_user = await self.bot.fetch_user(self.opponent_id)
        challenger_name = challenger_user.name
        opponent_name = opponent_user.name

        message = await interaction.followup.send("The duel begins!")


        while challenger_hp > 0 and opponent_hp > 0:
            # Challenger's turn
            damage = random.randint(10, 20)
            opponent_hp -= damage
            await message.edit(content=f"{challenger_name} attacks {opponent_name} for {damage} damage! ({opponent_name} HP: {opponent_hp}/{opponent_max_hp})")
            await asyncio.sleep(3)

            if opponent_hp <= 0:
                break

            # Opponent's turn
            damage = random.randint(10, 20)
            challenger_hp -= damage
            await message.edit(content=f"{opponent_name} fights back for {damage} damage! ({challenger_name} HP: {challenger_hp}/{challenger_max_hp})")
            await asyncio.sleep(3)

        if challenger_hp > opponent_hp:
            winner_id = self.challenger_id
            loser_id = self.opponent_id
            winner_name = challenger_name
        else:
            winner_id = self.opponent_id
            loser_id = self.challenger_id
            winner_name = opponent_name

        resolve_duel(winner_id, loser_id, self.wager)
        
        winner = get_user(winner_id)
        if winner.get('ship_id'):
            xp_gain = 500
            ship = get_ship(winner['ship_id'])
            if ship:
                badge_id = ship.get('equipped_badge')
                if badge_id:
                    items = db.collection('config').document('items').get().to_dict()
                    badge = items.get(badge_id)
                    if badge and badge.get('effect', {}).get('type') == 'xp_boost':
                        xp_gain = int(xp_gain * (1 + badge['effect']['value']))
            add_ship_xp(winner['ship_id'], xp_gain)
            ship_cog = self.bot.get_cog('Ship')
            if ship_cog:
                await ship_cog.check_ship_level_up(winner['ship_id'])

        await message.edit(content=f"The duel is over! {winner_name} is the winner!")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.opponent_id) and interaction.user.id != int(self.challenger_id):
            await interaction.response.send_message("This is not your duel to decline.", ephemeral=True)
            return
            
        await interaction.response.defer()

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.followup.send("The duel has been declined.")