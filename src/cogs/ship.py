import discord
import logging
import asyncio
import random
from discord.ext import commands
from discord import app_commands
from src.firebase_utils import get_user, update_berries, get_ship_by_name, join_ship, leave_ship, get_ship, db, deposit_item_to_ship, upgrade_ship, set_war_cooldown, resolve_ship_war, repair_ship, escrow_wager, equip_badge, unequip_badge
from firebase_admin import firestore
import uuid
import math
import json

log = logging.getLogger(__name__)

class Ship(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    ship = app_commands.Group(name="ship", description="Manage your pirate ship.")
    badge = app_commands.Group(parent=ship, name="badge", description="Manage your ship's badge.")

    @badge.command(name="equip", description="Equip a badge to your ship.")
    async def equip(self, interaction: discord.Interaction, badge_id: str):
        log.info(f"{interaction.user.name} used /ship badge equip with badge_id={badge_id}")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not in a ship.")
            return

        if player.get('role') not in ['captain', 'officer']:
            await interaction.response.send_message("You are not authorized to equip badges.")
            return

        ship = get_ship(player['ship_id'])
        if ship.get('equipped_badge'):
            await interaction.response.send_message("Your ship already has a badge equipped. Unequip it first.")
            return

        items = db.collection('config').document('items').get().to_dict()
        if badge_id not in items or items[badge_id]['type'] != 'badge':
            await interaction.response.send_message("This is not a valid badge ID.")
            return

        try:
            equip_badge(user_id, player['ship_id'], badge_id)
            await interaction.response.send_message(f"You have equipped the {items[badge_id]['name']} on your ship!")
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}")

    @badge.command(name="unequip", description="Unequip the badge from your ship.")
    async def unequip(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /ship badge unequip")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not in a ship.")
            return

        if player.get('role') not in ['captain', 'officer']:
            await interaction.response.send_message("You are not authorized to unequip badges.")
            return

        ship = get_ship(player['ship_id'])
        badge_id = ship.get('equipped_badge')
        if not badge_id:
            await interaction.response.send_message("Your ship does not have a badge equipped.")
            return

        items = db.collection('config').document('items').get().to_dict()

        try:
            unequip_badge(user_id, player['ship_id'], badge_id)
            await interaction.response.send_message(f"You have unequipped the {items[badge_id]['name']} and returned it to your bag.")
        except Exception as e:
            await interaction.response.send_message(f"An error occurred: {e}")

    @ship.command(name="create", description="Create a new pirate ship.")
    async def create(self, interaction: discord.Interaction, name: str):
        log.info(f"{interaction.user.name} used /ship create with name={name}")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if player.get('ship_id'):
            await interaction.response.send_message("You are already part of a crew!")
            return

        if player['berries'] < 5000:
            await interaction.response.send_message("You don't have enough berries to create a ship! You need 5,000 berries.")
            return

        ship_id = str(uuid.uuid4())
        
        try:
            transaction = db.transaction()
            Ship._create_ship_transaction(transaction, user_id, name, ship_id, interaction.guild.id)
            await interaction.response.send_message(f"The ship '{name}' has set sail!")
        except Exception as e:
            await interaction.response.send_message("Failed to create ship. Please try again.")
            log.error(f"Error creating ship: {e}")

    @staticmethod
    @firestore.transactional
    def _create_ship_transaction(transaction, user_id, name, ship_id, server_id):
        user_ref = db.collection('pirates').document(user_id)
        ship_ref = db.collection('ships').document(ship_id)

        player_snapshot = user_ref.get(transaction=transaction)
        if player_snapshot.get('berries') < 5000:
            raise Exception("Not enough berries.")

        transaction.update(user_ref, {
            'berries': firestore.Increment(-5000),
            'ship_id': ship_id,
            'role': 'captain'
        })

        transaction.set(ship_ref, {
            "id": ship_id,
            "server_id": str(server_id),
            "name": name,
            "captain_id": user_id,
            "members": [user_id],
            "level": 1,
            "xp": 0,
            "xp_to_next_level": 1000,
            "upgrades": {"hull_lvl": 1, "cannon_lvl": 1, "storage_lvl": 1},
            "stats": {
                "max_hp": 2000,
                "max_storage": 1000
            },
            "storage": {},
            "hp": 2000,
            "war_cooldown": None,
            "equipped_badge": None,
            "crew_bonus": 1.0
        })

    @ship.command(name="join", description="Join a pirate ship.")
    async def join(self, interaction: discord.Interaction, name: str):
        log.info(f"{interaction.user.name} used /ship join with name={name}")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if player.get('ship_id'):
            await interaction.response.send_message("You are already part of a crew!")
            return

        ship = get_ship_by_name(name)
        if not ship:
            await interaction.response.send_message(f"Couldn't find a ship named '{name}'.")
            return

        if len(ship['members']) >= 100:
            await interaction.response.send_message("This ship's crew is full!")
            return

        join_ship(user_id, ship['id'])
        await interaction.response.send_message(f"Welcome to the '{name}' crew!")

    @ship.command(name="leave", description="Leave your current pirate ship.")
    async def leave(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /ship leave")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not part of a crew.")
            return

        if player.get('role') == 'captain':
            await interaction.response.send_message("Captains can't abandon their ship! You must disband it first (coming soon).")
            return

        leave_ship(user_id, player['ship_id'])
        await interaction.response.send_message("You have left the crew.")

    @ship.command(name="disband", description="Disband your pirate ship.")
    async def disband(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /ship disband")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not part of a crew.")
            return

        if player.get('role') != 'captain':
            await interaction.response.send_message("Only the captain can disband the ship.")
            return

        ship = get_ship(player['ship_id'])
        ship_name = ship['name']
        
        # Confirmation view
        view = DisbandConfirmationView(user_id, ship)
        await interaction.response.send_message(f"Are you sure you want to disband the '{ship_name}'? This action is irreversible.", view=view)

    @ship.command(name="info", description="Get information about your ship.")
    async def info(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /ship info")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not in a crew.")
            return

        ship = get_ship(player['ship_id'])
        if not ship:
            await interaction.response.send_message("Could not find your ship's information.")
            return
        
        captain = await self.bot.fetch_user(int(ship['captain_id']))

        embed = discord.Embed(title=f"The {ship['name']}", color=discord.Color.blue())
        embed.set_thumbnail(url="https://img.freepik.com/premium-vector/pirate-ship-vintage-illustration_1188798-270.jpg")
        embed.add_field(name="Captain", value=captain.name, inline=True)
        
        level = ship.get('level', 1)
        xp = ship.get('xp', 0)
        xp_to_next_level = ship.get('xp_to_next_level', 1000)
        hp = ship.get('hp', 1000)
        max_hp = ship.get('stats', {}).get('max_hp', 2000)
        max_storage = ship.get('stats', {}).get('max_storage', 1000)
        current_storage = sum(ship.get('storage', {}).values())

        upgrades = ship.get('upgrades', {})
        hull_lvl = upgrades.get('hull_lvl', 1)
        cannon_lvl = upgrades.get('cannon_lvl', 1)
        storage_lvl = upgrades.get('storage_lvl', 1)

        embed.add_field(name="Level", value=f"**{level}**", inline=True)
        embed.add_field(name="XP", value=f"{xp}/{xp_to_next_level}", inline=True)
        embed.add_field(name="HP", value=f"{hp}/{max_hp}", inline=False)
        embed.add_field(name="Crew", value=f"{len(ship['members'])}/100", inline=True)
        embed.add_field(name="Storage", value=f"{current_storage}/{max_storage}", inline=True)
        embed.add_field(name="Crew Bonus", value=f"x{ship.get('crew_bonus', 1.0)}", inline=True)
        
        embed.add_field(name="Upgrades", value=f"Hull: Lvl {hull_lvl}\nCannon: Lvl {cannon_lvl}\nStorage: Lvl {storage_lvl}", inline=False)

        badge_id = ship.get('equipped_badge')
        if badge_id:
            items = db.collection('config').document('items').get().to_dict()
            badge_name = items.get(badge_id, {}).get('name', "Unknown Badge")
            embed.add_field(name="Equipped Badge", value=badge_name, inline=False)

        await interaction.response.send_message(embed=embed)

    async def check_ship_level_up(self, ship_id):
        ship_ref = db.collection('ships').document(str(ship_id))
        
        while True:
            ship_data = ship_ref.get().to_dict()

            # Handle old schema or missing data
            xp_to_next_level = ship_data.get('xp_to_next_level', 1000)
            level = ship_data.get('level', 1)
            xp = ship_data.get('xp', 0)

            if xp >= xp_to_next_level:
                new_level = level + 1
                new_xp = xp - xp_to_next_level
                new_xp_to_next = math.floor(1000 * (1.4 ** (new_level - 1)))

                update_data = {
                    'level': new_level,
                    'xp': new_xp,
                    'xp_to_next_level': new_xp_to_next
                }
                
                ship_ref.update(update_data)

                captain_id = ship_data['captain_id']
                try:
                    captain = await self.bot.fetch_user(int(captain_id))
                    if captain:
                        await captain.send(f"Your ship '{ship_data['name']}' has reached Level {new_level}!")
                except discord.NotFound:
                    log.warning(f"Could not find captain with ID {captain_id} to send level up notification.")
                
                # Continue loop to check for another level up
                continue
            else:
                # Exit loop if not enough XP for the next level
                break

    storage = app_commands.Group(name="storage", description="Manage your ship's storage.")

    @storage.command(name="deposit", description="Deposit an item into your ship's storage.")
    async def storage_deposit(self, interaction: discord.Interaction, item_id: str, quantity: int):
        log.info(f"{interaction.user.name} used /ship storage deposit with item_id={item_id} quantity={quantity}")
        if quantity <= 0:
            await interaction.response.send_message("Quantity must be positive.")
            return
            
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not in a ship.")
            return

        items = db.collection('config').document('items').get().to_dict()
        if item_id not in items:
            await interaction.response.send_message("Item not found.")
            return

        try:
            deposit_item_to_ship(user_id, player['ship_id'], item_id, quantity)
            await interaction.response.send_message(f"You deposited {quantity}x {items[item_id]['name']} into the ship's hold.")
        except Exception as e:
            log.error(f"Error depositing item to ship: {e}")
            await interaction.response.send_message(f"An error occurred: {e}")

    @storage.command(name="view", description="View your ship's storage.")
    async def storage_view(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /ship storage view")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not in a ship.")
            return
            
        ship = get_ship(player['ship_id'])
        if not ship:
            await interaction.response.send_message("Could not find your ship's information.")
            return

        storage_data = ship.get('storage', {})
        
        # Handle old and new schema
        if 'contents' in storage_data:
            storage = storage_data['contents']
        else:
            storage = storage_data

        max_storage = ship.get('stats', {}).get('max_storage', 1000) # Default to 1000 for old schema
        current_storage = sum(storage.values())

        embed = discord.Embed(title=f"{ship['name']}'s Storage", color=discord.Color.dark_gold())
        embed.set_footer(text=f"Capacity: {current_storage}/{max_storage}")

        if not storage:
            embed.description = "The hold is empty."
        else:
            items = db.collection('config').document('items').get().to_dict()
            for item_id, quantity in storage.items():
                item_name = items.get(item_id, {}).get('name', item_id)
                embed.add_field(name=item_name, value=quantity, inline=True)
        
        await interaction.response.send_message(embed=embed)

    @ship.command(name="upgrade", description="Upgrade your ship.")
    async def upgrade(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /ship upgrade")
        user_id = str(interaction.user.id)
        player = get_user(user_id)

        if not player.get('ship_id'):
            await interaction.response.send_message("You are not in a ship.")
            return

        if player.get('role') != 'captain':
            await interaction.response.send_message("Only the captain can upgrade the ship.")
            return

        view = ShipUpgradeView(bot=self.bot, ship_id=player['ship_id'], user_id=user_id)
        await interaction.response.send_message("Select an upgrade for your ship:", view=view)

    @ship.command(name="war", description="Challenge another ship to a war.")
    async def war(self, interaction: discord.Interaction, target_ship_name: str, wager: int = 0):
        log.info(f"{interaction.user.name} used /ship war with target_ship_name={target_ship_name} wager={wager}")
        
        challenger_player = get_user(str(interaction.user.id))
        if not challenger_player.get('ship_id'):
            await interaction.response.send_message("You are not in a ship.")
            return

        if challenger_player.get('role') not in ['captain', 'officer']:
            await interaction.response.send_message("You are not authorized to start a war.")
            return

        challenger_ship = get_ship(challenger_player['ship_id'])
        
        last_war = challenger_ship.get('war_cooldown')
        if last_war and time.time() - last_war < 3600: # 1 hour cooldown
            remaining_time = time.strftime('%Hh %Mm %Ss', time.gmtime(3600 - (time.time() - last_war)))
            await interaction.response.send_message(f"Your ship is on cooldown. You can start a war again in {remaining_time}.")
            return

        target_ship = get_ship_by_name(target_ship_name)
        if not target_ship:
            await interaction.response.send_message(f"Could not find a ship named '{target_ship_name}'.")
            return
            
        if challenger_ship['id'] == target_ship['id']:
            await interaction.response.send_message("You cannot declare war on your own ship.")
            return

        if wager < 0:
            await interaction.response.send_message("Wager must be non-negative.")
            return
        
        challenger_captain = get_user(challenger_ship['captain_id'])
        target_captain = get_user(target_ship['captain_id'])

        if challenger_captain['berries'] < wager:
            await interaction.response.send_message("Your captain doesn't have enough berries for this wager.")
            return
        
        if target_captain['berries'] < wager:
            await interaction.response.send_message(f"The captain of '{target_ship_name}' doesn't have enough berries for this wager.")
            return

        target_captain_user = await self.bot.fetch_user(int(target_ship['captain_id']))
        if not target_captain_user:
            await interaction.response.send_message("Could not find the captain of the target ship.")
            return

        view = ShipWarView(self.bot, challenger_ship, target_ship, wager)
        await interaction.response.send_message(f"{target_captain_user.mention}, the '{challenger_ship['name']}' (Level {challenger_ship['level']}) challenges you to a Ship War! Wager: {wager} Berries. Do you accept?", view=view)

    @ship.command(name="repair", description="Repair your ship.")
    async def repair(self, interaction: discord.Interaction, amount: int = None):
        log.info(f"{interaction.user.name} used /ship repair with amount={amount}")
        
        player = get_user(str(interaction.user.id))
        if not player.get('ship_id'):
            await interaction.response.send_message("You are not in a ship.")
            return

        if player.get('role') not in ['captain', 'officer']:
            await interaction.response.send_message("You are not authorized to repair the ship.")
            return

        ship = get_ship(player['ship_id'])
        
        if ship['hp'] >= ship['stats']['max_hp']:
            await interaction.response.send_message("Your ship is already at full HP!")
            return

        if amount is None:
            hp_to_heal = ship['stats']['max_hp'] - ship['hp']
        else:
            if amount <= 0:
                await interaction.response.send_message("Amount must be positive.")
                return
            hp_to_heal = min(amount, ship['stats']['max_hp'] - ship['hp'])

        tools_needed = math.ceil(hp_to_heal / 200)
        
        if ship.get('storage', {}).get('repair_tool', 0) < tools_needed:
            await interaction.response.send_message(f"You don't have enough repair tools. You need {tools_needed}.")
            return

        try:
            repair_ship(player['ship_id'], tools_needed, hp_to_heal)
            await interaction.response.send_message(f"You used {tools_needed} Repair Tools and healed the ship for {hp_to_heal} HP!")
        except Exception as e:
            await interaction.response.send_message(f"An error occurred while repairing the ship: {e}")


    @ship.command(name="promote", description="Promote a crew member to officer.")
    async def promote(self, interaction: discord.Interaction, user: discord.User):
        log.info(f"{interaction.user.name} used /ship promote with user={user.name}")
        captain_id = str(interaction.user.id)
        target_id = str(user.id)

        captain_player = get_user(captain_id)
        target_player = get_user(target_id)

        if captain_player.get('role') != 'captain':
            await interaction.response.send_message("Only the captain can promote members.", ephemeral=True)
            return

        if not captain_player.get('ship_id') or captain_player['ship_id'] != target_player.get('ship_id'):
            await interaction.response.send_message("The user is not in your ship.", ephemeral=True)
            return

        if target_player.get('role') == 'officer':
            await interaction.response.send_message(f"{user.name} is already an officer.", ephemeral=True)
            return

        if target_player.get('role') == 'captain':
            await interaction.response.send_message(f"{user.name} is the captain and cannot be promoted.", ephemeral=True)
            return

        try:
            user_ref = db.collection('pirates').document(target_id)
            user_ref.update({'role': 'officer'})
            await interaction.response.send_message(f"{user.name} has been promoted to Officer!")
        except Exception as e:
            log.error(f"Error promoting user: {e}")
            await interaction.response.send_message(f"An error occurred: {e}")

    @ship.command(name="demote", description="Demote a crew officer to member.")
    async def demote(self, interaction: discord.Interaction, user: discord.User):
        log.info(f"{interaction.user.name} used /ship demote with user={user.name}")
        captain_id = str(interaction.user.id)
        target_id = str(user.id)

        captain_player = get_user(captain_id)
        target_player = get_user(target_id)

        if captain_player.get('role') != 'captain':
            await interaction.response.send_message("Only the captain can demote members.", ephemeral=True)
            return

        if not captain_player.get('ship_id') or captain_player['ship_id'] != target_player.get('ship_id'):
            await interaction.response.send_message("The user is not in your ship.", ephemeral=True)
            return

        if target_player.get('role') != 'officer':
            await interaction.response.send_message(f"{user.name} is not an officer.", ephemeral=True)
            return

        if target_player.get('role') == 'captain':
            await interaction.response.send_message(f"{user.name} is the captain and cannot be demoted.", ephemeral=True)
            return

        try:
            user_ref = db.collection('pirates').document(target_id)
            user_ref.update({'role': 'member'})
            await interaction.response.send_message(f"{user.name} has been demoted to Member.")
        except Exception as e:
            log.error(f"Error demoting user: {e}")
            await interaction.response.send_message(f"An error occurred: {e}")


class DisbandConfirmationView(discord.ui.View):
    def __init__(self, captain_id, ship):
        super().__init__(timeout=60)
        self.captain_id = captain_id
        self.ship = ship

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.red)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.captain_id:
            await interaction.response.send_message("You are not the captain of this ship.", ephemeral=True)
            return

        await interaction.response.defer()

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        ship_name = self.ship['name']
        ship_id = self.ship['id']
        members = self.ship['members']

        # Remove ship_id from all members
        for member_id in members:
            user_ref = db.collection('pirates').document(member_id)
            user_ref.update({
                'ship_id': None,
                'role': None
            })

        # Delete the ship
        db.collection('ships').document(ship_id).delete()

        await interaction.followup.send(f"The ship '{ship_name}' has been disbanded.")

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.captain_id:
            await interaction.response.send_message("You are not the captain of this ship.", ephemeral=True)
            return
            
        await interaction.response.defer()

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.followup.send("Ship disbandment has been cancelled.")




async def setup(bot):
    await bot.add_cog(Ship(bot))

class ShipWarView(discord.ui.View):
    def __init__(self, bot, challenger_ship, target_ship, wager):
        super().__init__(timeout=120)
        self.bot = bot
        self.challenger_ship = challenger_ship
        self.target_ship = target_ship
        self.wager = wager

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.target_ship['captain_id']):
            await interaction.response.send_message("You are not the captain of the challenged ship.", ephemeral=True)
            return

        await interaction.response.defer()

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

        try:
            escrow_wager(self.challenger_ship['captain_id'], self.target_ship['captain_id'], self.wager)
            set_war_cooldown(self.challenger_ship['id'], self.target_ship['id'])
        except Exception as e:
            await interaction.followup.send(f"An error occurred while starting the war: {e}")
            return

        message = await interaction.followup.send(f"The war has begun! {self.challenger_ship['name']} vs {self.target_ship['name']}!")

        ship1_data = self.challenger_ship
        ship2_data = self.target_ship

        items = db.collection('config').document('items').get().to_dict()

        for i in range(1, 6): # 5 rounds
            await asyncio.sleep(5)

            # Ship 1 attacks
            cannons1 = ship1_data['upgrades']['cannon_lvl'] * 2
            balls_to_use1 = min(ship1_data['storage'].get('cannonball_x10', 0) * 10, cannons1)
            if balls_to_use1 == 0:
                dmg1 = 0
            else:
                base_dmg1 = (cannons1 * 50) * (1 + ship1_data['level'] * 0.1)
                defense2 = 1 - (ship2_data['upgrades']['hull_lvl'] * 0.05)
                
                badge_id2 = ship2_data.get('equipped_badge')
                if badge_id2 and items.get(badge_id2, {}).get('effect', {}).get('type') == 'defense_boost':
                    defense2 -= items[badge_id2]['effect']['value']

                dmg1 = math.floor(base_dmg1 * defense2)
            
            ship2_data['hp'] -= dmg1
            ship1_data['storage']['cannonball_x10'] = ship1_data['storage'].get('cannonball_x10', 0) - math.ceil(balls_to_use1 / 10)


            # Ship 2 attacks
            cannons2 = ship2_data['upgrades']['cannon_lvl'] * 2
            balls_to_use2 = min(ship2_data['storage'].get('cannonball_x10', 0) * 10, cannons2)
            if balls_to_use2 == 0:
                dmg2 = 0
            else:
                base_dmg2 = (cannons2 * 50) * (1 + ship2_data['level'] * 0.1)
                defense1 = 1 - (ship1_data['upgrades']['hull_lvl'] * 0.05)

                badge_id1 = ship1_data.get('equipped_badge')
                if badge_id1 and items.get(badge_id1, {}).get('effect', {}).get('type') == 'defense_boost':
                    defense1 -= items[badge_id1]['effect']['value']

                dmg2 = math.floor(base_dmg2 * defense1)

            ship1_data['hp'] -= dmg2
            ship2_data['storage']['cannonball_x10'] = ship2_data['storage'].get('cannonball_x10', 0) - math.ceil(balls_to_use2 / 10)

            await message.edit(content=f"**Round {i}**!\n{ship1_data['name']} fires for {dmg1}! {ship2_data['name']} fires for {dmg2}!\n> {ship1_data['name']} HP: {ship1_data['hp']}/{ship1_data['stats']['max_hp']}\n> {ship2_data['name']} HP: {ship2_data['hp']}/{ship2_data['stats']['max_hp']}")

            if ship1_data['hp'] <= 0 or ship2_data['hp'] <= 0:
                break

        if ship1_data['hp'] > ship2_data['hp']:
            winner_ship = ship1_data
            loser_ship = ship2_data
        else:
            winner_ship = ship2_data
            loser_ship = ship1_data

        loser_item_loss = random.random() < 0.3
        
        xp_gain = 5000
        badge_id = winner_ship.get('equipped_badge')
        if badge_id and items.get(badge_id, {}).get('effect', {}).get('type') == 'xp_boost':
            xp_gain = int(xp_gain * (1 + items[badge_id]['effect']['value']))

        resolve_ship_war(winner_ship['captain_id'], winner_ship['id'], loser_ship['id'], self.wager, xp_gain, loser_item_loss)

        # Update ship documents with new hp and storage
        db.collection('ships').document(ship1_data['id']).update({'hp': ship1_data['hp'], 'storage': ship1_data['storage']})
        db.collection('ships').document(ship2_data['id']).update({'hp': ship2_data['hp'], 'storage': ship2_data['storage']})

        await self.bot.get_cog('Ship').check_ship_level_up(winner_ship['id'])

        await message.edit(content=f"The war is over! The '{winner_ship['name']}' is victorious!")

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.target_ship['captain_id']) and interaction.user.id != int(self.challenger_ship['captain_id']):
            await interaction.response.send_message("This is not your war to decline.", ephemeral=True)
            return
            
        await interaction.response.defer()

        # Disable buttons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)
        
        await interaction.followup.send("The ship war has been declined.")

class ShipUpgradeView(discord.ui.View):
    def __init__(self, bot, ship_id, user_id):
        super().__init__()
        self.bot = bot
        self.ship_id = ship_id
        self.user_id = user_id
        self.add_item(ShipUpgradeSelect(bot=bot, ship_id=ship_id, user_id=user_id))

class ShipUpgradeSelect(discord.ui.Select):
    def __init__(self, bot, ship_id, user_id):
        self.bot = bot
        self.ship_id = ship_id
        self.user_id = user_id
        options = [
            discord.SelectOption(label="Hull (HP)", value="hull"),
            discord.SelectOption(label="Storage (Capacity)", value="storage"),
        ]
        super().__init__(placeholder="Choose an upgrade...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /ship upgrade with upgrade_type={self.values[0]}")
        await interaction.response.defer()
        upgrade_type = self.values[0]
        ship = get_ship(self.ship_id)
        
        if upgrade_type == 'hull':
            current_level = ship['upgrades']['hull_lvl']
            cost = math.floor(5000 * (1.5 ** current_level))
            new_level = current_level + 1
            new_stat_value = 2000 * (1.2 ** (new_level -1))
        elif upgrade_type == 'storage':
            current_level = ship['upgrades']['storage_lvl']
            cost = math.floor(5000 * (1.5 ** current_level))
            new_level = current_level + 1
            new_stat_value = 1000 * (1.2 ** (new_level-1))
        else:
            await interaction.followup.send("Invalid upgrade type.")
            return

        player = get_user(self.user_id)
        if player['berries'] < cost:
            await interaction.followup.send(f"You need {cost} berries to upgrade this.")
            return

        try:
            upgrade_ship(self.user_id, self.ship_id, upgrade_type, cost, new_level, new_stat_value)
            await interaction.followup.send(f"Upgraded {upgrade_type} to Level {new_level}!")
        except Exception as e:
            log.error(f"Error upgrading ship: {e}")
            await interaction.followup.send(f"An error occurred: {e}")
