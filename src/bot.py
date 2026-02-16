import logging
import os
from pathlib import Path
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from src.commands.boiler import boiler
from src.commands.framemog import framemogger


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.all()  # Use all intents to ensure on_ready fires
bot = commands.Bot(command_prefix='!', intents=intents)

BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Paths to template GIFs with green square
COALTHROW_IMAGE = Path("/app/templates/coalthrow.png")
BOILER_TEMPLATE = Path("/app/templates/boiler_template.gif")
FRAMEMOG_TEMPLATE = Path("/app/templates/framemog_template.gif")
PET_TEMPLATE = Path("/app/templates/pet_template.gif")
# BOILBOARD_DB = Path("/app/databases/boilboard.db")

# Coal reaction settings
COAL_EMOJI = "coal"  # Replace with your custom coal emoji name if needed (e.g., "coal")
COAL_THRESHOLD = 5
coal_replied_messages = set()  # Track messages already replied to

has_synced = False

@bot.event
async def on_ready():
    global has_synced
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'bot is ready to rot brains')

    if has_synced:
        logger.info("Skipping sync - already synced this session")
        return

    has_synced = True

    try:
        # Parse comma-separated guild IDs from env var (e.g., "123,456,789")
        guild_ids_str = os.getenv('DISCORD_BOT_GUILD_IDS', '')
        guild_ids = [int(gid.strip()) for gid in guild_ids_str.split(',') if gid.strip()]

        # Sync globally (works in both servers and DMs)
        logger.info("Syncing commands globally...")
        global_synced = await bot.tree.sync()
        logger.info(f"Synced {len(global_synced)} command(s) globally")

        # Clear guild-specific commands to prevent duplicates in the menu
        for guild_id in guild_ids:
            guild = discord.Object(id=guild_id)
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
            logger.info(f"Cleared guild-specific commands from {guild_id}")

        logger.info(f"Total: Synced globally, cleared {len(guild_ids)} guild(s)")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")
        logger.error(traceback.format_exc())


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """Watch for coal emoji reactions and reply when threshold is reached."""
    # Check if the emoji matches the coal emoji
    emoji_name = str(payload.emoji.name) if payload.emoji.name else ""
    if emoji_name != COAL_EMOJI:
        return

    # Skip if we already replied to this message
    if payload.message_id in coal_replied_messages:
        return

    try:
        channel = bot.get_channel(payload.channel_id)
        if channel is None:
            channel = await bot.fetch_channel(payload.channel_id)

        message = await channel.fetch_message(payload.message_id)

        # Find the coal reaction and check its count
        for reaction in message.reactions:
            if str(reaction.emoji.name if hasattr(reaction.emoji, 'name') else reaction.emoji) == COAL_EMOJI:
                if reaction.count >= COAL_THRESHOLD:
                    coal_replied_messages.add(message.id)
                    await message.reply(file=discord.File(COALTHROW_IMAGE))
                    logger.info(f"Coal threshold reached on message {message.id} with {reaction.count} reactions")
                break
    except Exception as e:
        logger.error(f"Error handling coal reaction: {e}")
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

    # Defer the response since this might take a moment
    await interaction.response.defer() # type: ignore

    await boiler(interaction, user, BOILER_TEMPLATE, logger)
    # await boiler(interaction, user, BOILER_TEMPLATE, BOILBOARD_DB, logger)


@bot.tree.command(name='framemog', description='Framemog a user')
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(user='The user you framemog', location='The location of the framemog')
async def framemog(interaction: discord.Interaction, user: discord.User, location: str = None):
    """
    Slash command to framemog someone.
    Usage: /framemog @user
    Works in servers, DMs, and group DMs!
    """

    # Defer the response since this might take a moment
    await interaction.response.defer() # type: ignore

    await framemogger(interaction, user, location, FRAMEMOG_TEMPLATE, logger)
    # await framemogger(interaction, user, FRAMEMOG_TEMPLATE, _DB, logger)


@bot.tree.command(name='pet', description='Pet a user\'s profile picture!')
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe() #user='The user whose profile picture you want to boil (leave empty to pet the bot)')
async def pet(interaction: discord.Interaction):
    """
    Slash command to pet boiler bot.
    Usage: /pet @user or /pet (to pet the bot)
    Works in servers, DMs, and group DMs!
    """

    # Defer the response since this might take a moment
    await interaction.response.defer() # type: ignore

    # uncomment when function is done
    # await petter(interaction, user, PET_TEMPLATE, logger)

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
