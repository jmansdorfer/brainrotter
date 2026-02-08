import logging
import os
from pathlib import Path
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from src.commands.boiler import boiler


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.all()  # Use all intents to ensure on_ready fires
bot = commands.Bot(command_prefix='!', intents=intents)

BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Paths to template GIFs with green square
BOILER_TEMPLATE = Path("/app/templates/boiler_template.gif")
PET_TEMPLATE = Path("/app/templates/pet_template.gif")
# BOILBOARD_DB = Path("/app/databases/boilboard.db")

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is ready to boil images!')

    # Sync slash commands to specific guilds for instant availability
    try:
        # Parse comma-separated guild IDs from env var (e.g., "123,456,789")
        guild_ids_str = os.getenv('DISCORD_BOT_GUILD_IDS', '')
        guild_ids = [int(gid.strip()) for gid in guild_ids_str.split(',') if gid.strip()]

        # Sync globally first for DMs (this makes commands available in DMs)
        logger.info("Syncing commands globally for DM support...")
        global_synced = await bot.tree.sync()
        logger.info(f"Synced {len(global_synced)} command(s) globally")

        if not guild_ids:
            logger.info(guild_ids)
            logger.warning("No guild IDs configured - only global sync performed")
            return

        # Also sync to specific guilds for instant availability in servers
        synced_count = 0
        for guild_id in guild_ids:
            guild = discord.Object(id=guild_id)
            # Clear old commands first to prevent duplicates
            bot.tree.clear_commands(guild=guild)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            synced_count += len(synced)
            logger.info(f"Synced {len(synced)} command(s) to guild {guild_id}")

        logger.info(f"Total: Synced globally + to {len(guild_ids)} guild(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
        logger.error(traceback.format_exc())


@bot.tree.command(name='boil', description='Boil a user\'s profile picture!')
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(user='The user whose profile picture you want to boil (leave empty for yourself)')
async def boil(interaction: discord.Interaction, user: discord.User = None):
    """
    Slash command to boil a user's profile picture.
    Usage: /boil @user or /boil (to boil your own avatar)
    Works in servers, DMs, and group DMs!
    """

    await boiler(interaction, user, BOILER_TEMPLATE, logger)
    # await boiler(interaction, user, BOILER_TEMPLATE, BOILBOARD_DB, logger)


@bot.tree.command(name='pet', description='Pet a user\'s profile picture!')
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe() #user='The user whose profile picture you want to boil (leave empty to pet the bot)')
async def pet(interaction: discord.Interaction):
    """
    Slash command to pet boiler bot.
    Usage: /pet @user or /pet (to pet the bot)
    Works in servers, DMs, and group DMs!
    """
    # uncomment when function is done
    # await petter(interaction, user, PET_TEMPLATE, logger)

    # Defer the response since this might take a moment
    await interaction.response.defer() # type: ignore

    try:
        # Send the result
        await interaction.followup.send(
            content=f'"thanks for petting me 🥰" -boiler bot',
            file=discord.File(PET_TEMPLATE)
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Error petting boiler bot: {str(e)}")
        logger.error(f"Error: {e}")


# @bot.tree.command(name='boilboard', description='')
# @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
# @app_commands.describe(user='Leaderboard of times users have been boiled.')
# async def boilboard(interaction: discord.Interaction, user: discord.User = None):
#     """
#     Slash command to boil a user's profile picture.
#     Usage: /boil @user or /boil (to boil your own avatar)
#     Works in servers, DMs, and group DMs!
#     """
#
#     await boilboard(interaction, user, BOILBOARD_DB)


if __name__ == "__main__":
    if not os.path.exists(BOILER_TEMPLATE):
        logger.warning(f"WARNING: Template GIF not found at '{BOILER_TEMPLATE}'")
        logger.warning(f"Please create or add your boiling water GIF with a green square (#00FF00)")
        logger.warning(f"The bot will still start, but the /boil command won't work until you add it.")

    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("ERROR: Please set your bot token in the BOT_TOKEN variable!")
        logger.error("Get your token from: https://discord.com/developers/applications")
    else:
        logger.info("Starting bot...")
        bot.run(BOT_TOKEN)
