import asyncio
import glob
import logging
import os
import shutil
import traceback

import discord
from discord import app_commands
from discord.ext import commands
import numpy as np
from PIL import Image, ImageSequence


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

intents = discord.Intents.all()  # Use all intents to ensure on_ready fires
bot = commands.Bot(command_prefix='!', intents=intents)

BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Path to your template GIF with green square
TEMPLATE_PATH = os.path.join("data", "template_boiling.gif")
PET_GIF = os.path.join("data", "boiler_pet.gif")


def replace_green_square_in_gif(template_path, image_path, output_path,
                                green_threshold=100, position=None, size=None):
    """
    Replace green screen area in a GIF with a custom image.

    Args:
        template_path: Path to template GIF with green square
        image_path: Path to image to insert
        output_path: Path to save output GIF
        green_threshold: How close to pure green (0-255). Lower = stricter green detection
        position: Optional tuple (x, y) for where to place image. If None, auto-detect green area
        size: Optional tuple (width, height) for image size. If None, auto-detect from green area
    """
    # Load the template GIF and the image to insert
    template = Image.open(template_path)
    insert_image = Image.open(image_path).convert('RGBA')

    frames = []
    durations = []

    # Detect the size from the largest green area across all frames
    max_size = (0, 0)
    max_green_pixels = 0
    best_frame = None

    if size is None:
        for frame in ImageSequence.Iterator(template):
            test_frame = frame.convert('RGBA')
            test_array = np.array(test_frame)
            test_mask = (
                    (test_array[:, :, 1] > 200) &
                    (test_array[:, :, 0] < 100) &
                    (test_array[:, :, 2] < 100)
            )
            green_count = np.sum(test_mask)

            if green_count > max_green_pixels:
                max_green_pixels = green_count
                best_frame = test_frame

            # Also track the maximum size seen
            if green_count > 0:
                # Detect size for this frame
                rows = np.any(test_mask, axis=1)
                cols = np.any(test_mask, axis=0)
                if rows.any() and cols.any():
                    y_min, y_max = np.where(rows)[0][[0, -1]]
                    x_min, x_max = np.where(cols)[0][[0, -1]]
                    frame_size = (int(x_max - x_min + 1), int(y_max - y_min + 1))
                    if frame_size[0] * frame_size[1] > max_size[0] * max_size[1]:
                        max_size = frame_size

        if best_frame is not None and max_green_pixels > 0:
            logger.info(f"Found frame with {max_green_pixels} green pixels, max size: {max_size}")
            pos, sz = detect_green_area(best_frame, green_threshold)
        else:
            logger.warning("No green pixels found in any frame!")
            pos, sz = (50, 50), (100, 100)
            max_size = (100, 100)

        if position is None:
            position = pos
        if size is None:
            # Use the maximum size found across all frames so image stays constant size
            if max_size == (0, 0):
                logger.warning("Max size is (0,0), using detected size from best frame")
                size = sz
            else:
                size = max_size
                logger.info(f"Using max size for all frames: {size}")

    # Resize the insert image to fit the detected max area (for fallback)
    insert_image_resized = insert_image.resize(size, Image.Resampling.LANCZOS)

    # Keep original image for per-frame resizing
    insert_image_original = insert_image.copy()

    # Process each frame - resize image per frame to match green square size
    frame_num = 0
    for frame in ImageSequence.Iterator(template):
        frame_num += 1

        # Convert frame to RGBA
        frame = frame.convert('RGBA')

        # Get frame as numpy array for color replacement
        frame_array = np.array(frame)

        # Create mask for green pixels (more tolerant for compressed GIFs)
        # Green channel is high, red and blue are low
        green_mask = (
                (frame_array[:, :, 1] > 200) &  # Green channel very high (was 100)
                (frame_array[:, :, 0] < 100) &  # Red channel low (was green_threshold)
                (frame_array[:, :, 2] < 100)  # Blue channel low (was green_threshold)
        )

        # Count green pixels in this frame
        green_count = np.sum(green_mask)
        if frame_num <= 3 or green_count > 0:  # Log first 3 frames and any with green
            logger.info(f"Frame {frame_num}: Found {green_count} green pixels")

        # Detect position AND size for THIS specific frame from the mask
        if green_count > 0:
            # Find bounding box from the green mask
            rows = np.any(green_mask, axis=1)
            cols = np.any(green_mask, axis=0)

            if rows.any() and cols.any():
                y_min, y_max = np.where(rows)[0][[0, -1]]
                x_min, x_max = np.where(cols)[0][[0, -1]]
                pos_this_frame = (int(x_min), int(y_min))
                size_this_frame = (int(x_max - x_min + 1), int(y_max - y_min + 1))

                # Resize the profile picture to match THIS frame's green size
                insert_image_for_frame = insert_image_original.resize(size_this_frame, Image.Resampling.LANCZOS)

                # Replace green pixels with the resized insert image
                frame_with_insert = replace_area(frame, insert_image_for_frame, pos_this_frame, green_mask)
            else:
                # No valid green area, just use the frame as-is
                frame_with_insert = frame
        else:
            # No green in this frame, don't add the image at all
            frame_with_insert = frame

        # Convert back to P mode (palette) for smaller file size, matching original GIF format
        frame_with_insert = frame_with_insert.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=64)

        frames.append(frame_with_insert)

        # Preserve frame duration
        durations.append(frame.info.get('duration', 100))

    # Save as new GIF with optimization
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,  # Clear frame before rendering next
        optimize=True,  # Enable optimization
        colors=64  # Reduce color palette for smaller size
    )


def detect_green_area(frame, threshold=100):
    """Detect the bounding box of the green area in a frame."""
    frame_array = np.array(frame)

    # Create mask for green pixels (very tolerant for any kind of green)
    # Look for pixels where green is dominant (higher than red AND blue)
    green_mask = (
            (frame_array[:, :, 1] > frame_array[:, :, 0] + 50) &  # Green > Red + threshold
            (frame_array[:, :, 1] > frame_array[:, :, 2] + 50) &  # Green > Blue + threshold
            (frame_array[:, :, 1] > 150)  # Green channel reasonably bright
    )

    # Debug: Print how many green pixels found
    green_pixel_count = np.sum(green_mask)
    logger.info(f"Debug: Found {green_pixel_count} green pixels in frame")

    # Find bounding box of green area
    rows = np.any(green_mask, axis=1)
    cols = np.any(green_mask, axis=0)

    if not rows.any() or not cols.any():
        # No green found, return default
        return (50, 50), (100, 100)

    y_min, y_max = np.where(rows)[0][[0, -1]]
    x_min, x_max = np.where(cols)[0][[0, -1]]

    position = (x_min, y_min)
    size = (x_max - x_min + 1, y_max - y_min + 1)

    # Convert numpy integers to Python integers for PIL compatibility
    position = (int(position[0]), int(position[1]))
    size = (int(size[0]), int(size[1]))

    return position, size


def replace_area(background, insert_image, position, mask=None):
    """Replace an area in the background with the insert image."""
    result = background.copy()

    x, y = position

    # Simply paste the insert image at the position
    # The insert_image is already the right size (constant across all frames)
    # We'll paste it and it will show through where it fits
    result.paste(insert_image, position, insert_image)

    return result


@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')
    logger.info(f'Bot is ready to boil images!')

    # Sync slash commands to specific guilds for instant availability
    try:
        guild_ids = [
            os.getenv('DISCORD_BOT_GUILD_ID_1'),
            os.getenv('DISCORD_BOT_GUILD_ID_2'),
            os.getenv('DISCORD_BOT_GUILD_ID_3'),
        ]

        # Filter out None values and convert to integers
        guild_ids = [int(gid) for gid in guild_ids if gid is not None and gid.strip()]

        # Sync globally first for DMs (this makes commands available in DMs)
        logger.info("Syncing commands globally for DM support...")
        global_synced = await bot.tree.sync()
        logger.info(f"Synced {len(global_synced)} command(s) globally")

        if not guild_ids:
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
    # Check if template exists
    if not os.path.exists(TEMPLATE_PATH):
        await interaction.response.send_message(
            f"Error: Template GIF not found at `{TEMPLATE_PATH}`. Please add your template!",
            ephemeral=True
        )
        return

    # If no user specified, use the command author
    if user is None:
        user = interaction.user

    # Use display_name or global_name for logging to avoid discriminator issues
    requester_name = interaction.user.display_name or interaction.user.name
    target_name = user.display_name or user.name
    logger.info(f"Boil request: {requester_name} wants to boil {target_name}'s avatar")

    # Defer the response since this might take a moment
    await interaction.response.defer()

    try:
        # Create cache directory if it doesn't exist
        os.makedirs('../cache', exist_ok=True)
        os.makedirs('../temp', exist_ok=True)

        # Get avatar hash for cache key
        avatar_hash = user.display_avatar.key
        cache_file = f'cache/{user.id}_{avatar_hash}.gif'

        # Check if cached version exists
        if os.path.exists(cache_file):
            logger.info(f"Using cached GIF for {target_name} (hash: {avatar_hash})")
            file_size = os.path.getsize(cache_file)
            file_size_mb = file_size / (1024 * 1024)

            await interaction.followup.send(
                content=f'"hey {user.mention}" and they\'re boiled 😭😭😭😭',
                file=discord.File(cache_file)
            )
            return

        # Not cached - process new avatar
        logger.info(f"No cache found, processing new avatar for {target_name}")

        # Get the user's avatar URL (highest quality)
        avatar_url = user.display_avatar.url
        logger.info(f"Downloading avatar from: {avatar_url}")

        # Download the avatar
        temp_input = f'temp/input_{interaction.user.id}_{user.id}.png'
        temp_output = f'temp/output_{interaction.user.id}_{user.id}.gif'

        # Save the avatar image
        try:
            await user.display_avatar.save(temp_input)
            avatar_size = os.path.getsize(temp_input)
            logger.info(f"Avatar downloaded: {avatar_size / 1024:.1f} KB")
        except Exception as e:
            logger.error(f"Failed to download avatar: {e}")
            await interaction.followup.send(f"❌ Failed to download avatar: {e}")
            return

        # Process the image (run in executor to avoid blocking)
        await asyncio.get_event_loop().run_in_executor(
            None,
            replace_green_square_in_gif,
            TEMPLATE_PATH,
            temp_input,
            temp_output
        )

        # Check file size (Discord limit is 25MB for non-Nitro users)
        file_size = os.path.getsize(temp_output)
        file_size_mb = file_size / (1024 * 1024)
        logger.info(f"Output GIF size: {file_size_mb:.2f} MB")

        if file_size_mb > 24:  # Leave some margin
            await interaction.followup.send(
                f"❌ The output GIF is too large ({file_size_mb:.1f} MB)! "
                f"Discord's limit is 25 MB. Please use a smaller/shorter template GIF."
            )
            # Clean up
            try:
                os.remove(temp_input)
                os.remove(temp_output)
            except:
                pass
            return

        shutil.copy(temp_output, cache_file)
        logger.info(f"Saved to cache: {cache_file}")

        # Clean up old cached versions for this user (different avatar hashes)
        for old_cache in glob.glob(f'cache/{user.id}_*.gif'):
            if old_cache != cache_file:
                try:
                    os.remove(old_cache)
                    logger.info(f"Removed old cache: {old_cache}")
                except:
                    pass

        # Send the result
        await interaction.followup.send(
            content=f'"hey {user.mention}" and they\'re boiled 😭😭😭😭',
            file=discord.File(temp_output)
        )

        # Clean up temp files
        try:
            os.remove(temp_input)
            os.remove(temp_output)
        except:
            pass

    except Exception as e:
        await interaction.followup.send(f"❌ Error processing image: {str(e)}")
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
            file=discord.File(PET_GIF)
        )

    except Exception as e:
        await interaction.followup.send(f"❌ Error petting boiler bot: {str(e)}")
        logger.error(f"Error: {e}")


if __name__ == "__main__":
    if not os.path.exists(TEMPLATE_PATH):
        logger.warning(f"WARNING: Template GIF not found at '{TEMPLATE_PATH}'")
        logger.warning(f"Please create or add your boiling water GIF with a green square (#00FF00)")
        logger.warning(f"The bot will still start, but the /boil command won't work until you add it.")

    if BOT_TOKEN == 'YOUR_BOT_TOKEN_HERE':
        logger.error("ERROR: Please set your bot token in the BOT_TOKEN variable!")
        logger.error("Get your token from: https://discord.com/developers/applications")
    else:
        logger.info("Starting bot...")
        bot.run(BOT_TOKEN)
