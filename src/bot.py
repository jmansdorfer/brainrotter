import logging
import os
from pathlib import Path
import traceback

import discord
from discord import app_commands
from discord.ext import commands

from commands.boiler import boiler


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.all()  # Use all intents to ensure on_ready fires
bot = commands.Bot(command_prefix='!', intents=intents)

BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Paths to template GIFs with green square
BOILER_TEMPLATE = Path("app/templates/boiler_template.gif")
PET_TEMPLATE = Path("app/templates/pet_template.gif")

@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is ready to boil images!')

    # Sync slash commands to specific guilds for instant availability
    try:
        # Parse comma-separated guild IDs from env var (e.g., "123,456,789")
        guild_ids_str = os.getenv('DISCORD_GUILD_IDS', '')
        guild_ids = [int(gid.strip()) for gid in guild_ids_str.split(',') if gid.strip()]

        # Sync globally first for DMs (this makes commands available in DMs)
        logger.info("Syncing commands globally for DM support...")
        global_synced = await bot.tree.sync()
        logger.info(f"Synced {len(global_synced)} command(s) globally")

        if not guild_ids:
            print(guild_ids)
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


@bot.tree.command(name='pet', description='pet boiler bot')
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
async def pet(interaction: discord.Interaction):
    """
    Slash command to pet boiler bot.
    Usage: /pet
    Works in servers, DMs, and group DMs!
    """
    # Defer the response since this might take a moment
    await interaction.response.defer()

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
#     Slash command to fetch times a user has been boiled.
#     Usage: /boilboard @user or /boilboard (to get the full list)
#     Works in servers, DMs, and group DMs!
#     """
#     # Check if template exists
#     if not os.path.exists(TEMPLATE_PATH):
#         await interaction.response.send_message(
#             f"Error: Template GIF not found at `{TEMPLATE_PATH}`. Please add your template!",
#             ephemeral=True
#         )
#         return
#
#     # If no user specified, use the command author
#     if user is None:
#         user = interaction.user
#
#     # Use display_name or global_name for logging to avoid discriminator issues
#     requester_name = interaction.user.display_name or interaction.user.name
#     target_name = user.display_name or user.name
#     logger.info(f"Boil request: {requester_name} wants to boil {target_name}'s avatar")
#
#     # Defer the response since this might take a moment
#     await interaction.response.defer()
#
#     try:
#         # Create cache directory if it doesn't exist
#         os.makedirs('../cache', exist_ok=True)
#         os.makedirs('../temp', exist_ok=True)
#
#         # Get avatar hash for cache key
#         avatar_hash = user.display_avatar.key
#         cache_file = f'cache/{user.id}_{avatar_hash}.gif'
#
#         # Check if cached version exists
#         if os.path.exists(cache_file):
#             logger.info(f"Using cached GIF for {target_name} (hash: {avatar_hash})")
#             file_size = os.path.getsize(cache_file)
#             file_size_mb = file_size / (1024 * 1024)
#
#             await interaction.followup.send(
#                 content=f'"hey {user.mention}" and they\'re boiled 😭😭😭😭',
#                 file=discord.File(cache_file)
#             )
#             return
#
#         # Not cached - process new avatar
#         logger.info(f"No cache found, processing new avatar for {target_name}")
#
#         # Get the user's avatar URL (highest quality)
#         avatar_url = user.display_avatar.url
#         logger.info(f"Downloading avatar from: {avatar_url}")
#
#         # Download the avatar
#         temp_input = f'temp/input_{interaction.user.id}_{user.id}.png'
#         temp_output = f'temp/output_{interaction.user.id}_{user.id}.gif'
#
#         # Save the avatar image
#         try:
#             await user.display_avatar.save(temp_input)
#             avatar_size = os.path.getsize(temp_input)
#             logger.info(f"Avatar downloaded: {avatar_size / 1024:.1f} KB")
#         except Exception as e:
#             logger.error(f"Failed to download avatar: {e}")
#             await interaction.followup.send(f"❌ Failed to download avatar: {e}")
#             return
#
#         # Process the image (run in executor to avoid blocking)
#         await asyncio.get_event_loop().run_in_executor(
#             None,
#             replace_green_square_in_gif,
#             TEMPLATE_PATH,
#             temp_input,
#             temp_output
#         )
#
#         # Check file size (Discord limit is 25MB for non-Nitro users)
#         file_size = os.path.getsize(temp_output)
#         file_size_mb = file_size / (1024 * 1024)
#         logger.info(f"Output GIF size: {file_size_mb:.2f} MB")
#
#         if file_size_mb > 24:  # Leave some margin
#             await interaction.followup.send(
#                 f"❌ The output GIF is too large ({file_size_mb:.1f} MB)! "
#                 f"Discord's limit is 25 MB. Please use a smaller/shorter template GIF."
#             )
#             # Clean up
#             try:
#                 os.remove(temp_input)
#                 os.remove(temp_output)
#             except:
#                 pass
#             return
#
#         shutil.copy(temp_output, cache_file)
#         logger.info(f"Saved to cache: {cache_file}")
#
#         for old_cache in glob.glob(f'cache/{user.id}_*.gif'):
#             if old_cache != cache_file:
#                 try:
#                     os.remove(old_cache)
#                     logger.info(f"Removed old cache: {old_cache}")
#                 except:
#                     pass
#
#         # Send the result
#         await interaction.followup.send(
#             content=f'"hey {user.mention}" and they\'re boiled 😭😭😭😭',
#             file=discord.File(temp_output)
#         )
#
#         try:
#             os.remove(temp_input)
#             os.remove(temp_output)
#         except:
#             pass
#
#     except Exception as e:
#         await interaction.followup.send(f"❌ Error processing image: {str(e)}")
#         logger.error(f"Error: {e}")


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
