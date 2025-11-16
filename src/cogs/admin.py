import json
import discord
import logging
from discord.ext import commands
from discord import app_commands
import typing
from src.firebase_utils import get_ship_by_name, db
import math

log = logging.getLogger(__name__)

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="config_intrusion", description="Configure the bot's intrusion level (0-100).")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_intrusion(self, interaction: discord.Interaction, level: int):
        log.info(f"{interaction.user.name} used /config_intrusion with level={level}")
        if 0 <= level <= 100:
            server_id = str(interaction.guild.id)
            db.collection('config').document('settings').update({
                server_id: {
                    'intrusion_level': level,
                    'set_by': interaction.user.name
                }
            })
            await interaction.response.send_message(f"Intrusion level for this server set to {level}% by {interaction.user.name}.")
        else:
            await interaction.response.send_message("Please enter a number between 0 and 100.")

    @app_commands.command(name="recalculate_ship_level", description="Recalculate a ship's level based on its XP.")
    @app_commands.checks.has_permissions(administrator=True)
    async def recalculate_ship_level(self, interaction: discord.Interaction, ship_name: str):
        log.info(f"{interaction.user.name} used /recalculate_ship_level with ship_name={ship_name}")
        await interaction.response.defer()

        ship = get_ship_by_name(ship_name)
        if not ship:
            await interaction.followup.send(f"Ship '{ship_name}' not found.")
            return

        ship_ref = db.collection('ships').document(ship['id'])
        ship_data = ship_ref.get().to_dict()

        level = 1
        xp = ship_data.get('xp', 0)
        xp_to_next = 1000

        while xp >= xp_to_next:
            xp -= xp_to_next
            level += 1
            xp_to_next = math.floor(1000 * (1.4 ** (level - 1)))

        ship_ref.update({
            'level': level,
            'xp': xp,
            'xp_to_next_level': xp_to_next
        })

        await interaction.followup.send(f"'{ship_name}' has been recalculated to Level {level} with {xp} XP.")

    events = app_commands.Group(name="events", description="Manage world events.")

    @events.command(name="start", description="Start a world event.")
    @app_commands.checks.has_permissions(administrator=True)
    async def event_start(self, interaction: discord.Interaction, event_name: str):
        log.info(f"{interaction.user.name} used /event start with event_name={event_name}")
        if event_name == "Double XP Day":
            db.collection('config').document('events').update({
                'active_event': "Double XP Day"
            })
            await interaction.response.send_message("Double XP Day has begun!")
        else:
            await interaction.response.send_message("Invalid event name.")

    @events.command(name="stop", description="Stop the current world event.")
    @app_commands.checks.has_permissions(administrator=True)
    async def event_stop(self, interaction: discord.Interaction):
        log.info(f"{interaction.user.name} used /event stop")
        db.collection('config').document('events').update({
            'active_event': None
        })
        await interaction.response.send_message("The world event has ended.")

async def setup(bot):
    await bot.add_cog(Admin(bot))
