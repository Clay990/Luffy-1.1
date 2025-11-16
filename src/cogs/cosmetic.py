import discord
from discord import app_commands
from discord.ext import commands
from src.firebase_utils import get_user, buy_title, equip_title, db

class Cosmetic(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cosmetics = db.collection('config').document('cosmetics').get().to_dict()

    @app_commands.command(name="cosmetic_shop", description="Browse available cosmetic items.")
    async def cosmetic_shop(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Cosmetic Shop", color=discord.Color.gold())
        for cos_id, cos_data in self.cosmetics.items():
            embed.add_field(name=f"{cos_data['name']} (ID: {cos_id})", value=f"Price: {cos_data['price']:,} Berries\n{cos_data['description']}", inline=False)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy_cosmetic", description="Purchase a cosmetic item.")
    @app_commands.describe(identifier="The cosmetic name or ID")
    async def buy_cosmetic(self, interaction: discord.Interaction, identifier: str):
        item_to_buy = None
        # Check if the identifier is an ID
        if identifier in self.cosmetics:
            item_to_buy = self.cosmetics[identifier]
        else:
            # Check if the identifier is a name (case-insensitive)
            for cos_data in self.cosmetics.values():
                if cos_data['name'].lower() == identifier.lower():
                    item_to_buy = cos_data
                    break

        if item_to_buy is None:
            await interaction.response.send_message("That item doesn't exist.", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        
        try:
            buy_title(user_id, item_to_buy['name'], item_to_buy['price'])
            await interaction.response.send_message(f"You have unlocked the {item_to_buy['name']} title!")
        except Exception as e:
            await interaction.response.send_message(str(e), ephemeral=True)

    @app_commands.command(name="equip", description="Equip a title you've unlocked.")
    @app_commands.describe(identifier="The cosmetic name or ID")
    async def equip(self, interaction: discord.Interaction, identifier: str):
        user_id = str(interaction.user.id)
        player = get_user(user_id)
        unlocked_titles = player.get('unlocked_titles', [])
        
        title_to_equip = None

        # Find the corresponding title name from the identifier
        item_to_equip = None
        if identifier in self.cosmetics:
            item_to_equip = self.cosmetics[identifier]
        else:
            for cos_data in self.cosmetics.values():
                if cos_data['name'].lower() == identifier.lower():
                    item_to_equip = cos_data
                    break
        
        if item_to_equip and item_to_equip['name'] in unlocked_titles:
            title_to_equip = item_to_equip['name']
        elif identifier in unlocked_titles: # Direct name match
            title_to_equip = identifier

        if title_to_equip:
            try:
                equip_title(user_id, title_to_equip)
                await interaction.response.send_message(f"Profile title set to {title_to_equip}!")
            except Exception as e:
                await interaction.response.send_message(f"An error occurred: {e}", ephemeral=True)
        else:
            await interaction.response.send_message("You don't own that title.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Cosmetic(bot))
