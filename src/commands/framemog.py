import asyncio
import glob
import logging
from pathlib import Path
import os
import shutil
import subprocess
import sqlite3

import discord
import numpy as np
from PIL import Image, ImageSequence, ImageFilter
from PIL.Image import Palette


def replace_color_squares_in_gif(
        framemog_template: Path,
        image_path_mogger,
        image_path_moggee,
        output_path,
        size=None,
        gifsicle_lossy=30,
        blur_radius=0.5,
        colors=256,
):
    """
    Replace colored screen areas in a GIF with custom images.

    Purple (#ff00ff) square -> mogger image
    Green (#00ff00) square -> moggee image

    Args:
        framemog_template: Path to template GIF with green and purple squares
        image_path_mogger: Path to image to insert into the purple square
        image_path_moggee: Path to image to insert into the green square
        output_path: Path to save output GIF
        size: Optional tuple (width, height) for image size. If None, auto-detect from colored areas
        gifsicle_lossy: Lossy compression level for gifsicle (0-200, higher = smaller/lossier). Set to None to skip.
        blur_radius: Gaussian blur radius applied to the insert images to reduce compression-hostile detail. Set to 0 to skip.
        colors: Number of colors in the palette
    """
    # Load the template GIF and the images to insert
    template = Image.open(framemog_template)
    mogger_image = Image.open(image_path_mogger).convert('RGBA')
    moggee_image = Image.open(image_path_moggee).convert('RGBA')

    frames = []
    durations = []

    # Keep originals for per-frame resizing
    mogger_original = mogger_image.copy()
    moggee_original = moggee_image.copy()

    def make_green_mask(arr):
        """Detect #00ff00 green pixels."""
        return (
            (arr[:, :, 1] > 200) &
            (arr[:, :, 0] < 100) &
            (arr[:, :, 2] < 100)
        )

    def make_purple_mask(arr):
        """Detect #ff00ff purple/magenta pixels."""
        return (
            (arr[:, :, 0] > 200) &
            (arr[:, :, 1] < 100) &
            (arr[:, :, 2] > 200)
        )

    def find_bounding_box(mask):
        """Find bounding box of a boolean mask. Returns (pos, size) or None."""
        rows = np.any(mask, axis=1)
        cols = np.any(mask, axis=0)
        if not rows.any() or not cols.any():
            return None
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]
        pos = (int(x_min), int(y_min))
        size = (int(x_max - x_min + 1), int(y_max - y_min + 1))
        return pos, size

    def paste_into_region(frame, insert_original, mask, blur_rad):
        """Resize and paste an image into the region defined by the mask."""
        bbox = find_bounding_box(mask)
        if bbox is None:
            return frame

        pos, region_size = bbox

        resized = insert_original.resize(region_size, Image.Resampling.LANCZOS)

        if blur_rad and blur_rad > 0:
            resized = resized.filter(ImageFilter.GaussianBlur(radius=blur_rad))

        result = frame.copy()
        result.paste(resized, pos, resized)
        return result

    # Process each frame
    for frame in ImageSequence.Iterator(template):
        frame = frame.convert('RGBA')
        frame_array = np.array(frame)

        green_mask = make_green_mask(frame_array)
        purple_mask = make_purple_mask(frame_array)

        result = frame

        # Paste moggee into green square
        if np.sum(green_mask) > 0:
            result = paste_into_region(result, moggee_original, green_mask, blur_radius)

        # Paste mogger into purple square
        if np.sum(purple_mask) > 0:
            result = paste_into_region(result, mogger_original, purple_mask, blur_radius)

        # Convert back to P mode (palette) for smaller file size
        result = result.convert('RGB').convert(
            'P', palette=Palette.ADAPTIVE, colors=colors
        )

        frames.append(result)
        durations.append(frame.info.get('duration', 100))

    # Save as new GIF with optimization
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=True,
        colors=colors,
    )

    # gifsicle post-processing for frame differencing and lossy compression
    if gifsicle_lossy is not None and shutil.which('gifsicle'):
        try:
            subprocess.run(
                [
                    'gifsicle',
                    '--optimize=3',
                    f'--lossy={gifsicle_lossy}',
                    '--colors', str(colors),
                    str(output_path),
                    '-o', str(output_path),
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"gifsicle optimization failed (non-fatal): {e.stderr.decode()}")
    elif gifsicle_lossy is not None:
        print("gifsicle not found on PATH — skipping post-processing optimization")


async def framemogger(
        interaction:discord.Interaction,
        user:discord.User,
        framemog_template:Path,
        # boilboard_db:Path,
        logger:logging.Logger
):
    if user is None:
        await interaction.followup.send(f"please enter a user to framemog 😤🔥")

    # Use display_name or global_name for logging to avoid discriminator issues
    requester_name = interaction.user.display_name or interaction.user.name
    target_name = user.display_name or user.name
    logger.info(f"Framemog request: {requester_name} wants to framemog {target_name}'s avatar")

    # Defer the response since this might take a moment
    await interaction.response.defer() # type: ignore

    try:
        # Get avatar hash for cache key
        avatar_hash = user.display_avatar.key + "_" + interaction.user.display_avatar.key
        user_ids = str(user.id) + "_" + str(interaction.user.id)
        cache_file = f'cache/framemog/{user_ids}_{avatar_hash}.gif'

        # Check if cached version exists
        if os.path.exists(cache_file):
            logger.info(f"Using cached GIF for {target_name} and {requester_name} (hash: {avatar_hash})")

            await interaction.followup.send(
                content=f'{user.mention} ran into a frat leader at {interaction.guild.name} and got brutally frame mogged by them 👀😂',
                file=discord.File(cache_file)
            )
            return

        # Not cached - process new avatar
        logger.info(f"No cache found, processing new avatars for {target_name} and {requester_name}")

        # Get the user's avatar URL (highest quality)
        avatar_url_mogger = user.display_avatar.url
        avatar_url_moggee = interaction.user.display_avatar.url
        logger.info(f"Downloading avatar from: {avatar_url_mogger}")
        logger.info(f"Downloading avatar from: {avatar_url_moggee}")

        # Download the avatar
        temp_input_mogger = f'temp/input_{interaction.user.id}.png'
        temp_input_moggee = f'temp/input_{user.id}.png'
        temp_output = f'temp/output_{interaction.user.id}_{user.id}.gif'

        # Save the avatar image
        try:
            await interaction.user.display_avatar.save(temp_input_mogger)
            avatar_size = os.path.getsize(temp_input_mogger)
            logger.info(f"Avatar downloaded: {avatar_size / 1024:.1f} KB")

            await user.display_avatar.save(temp_input_moggee)
            avatar_size = os.path.getsize(temp_input_moggee)
            logger.info(f"Avatar downloaded: {avatar_size / 1024:.1f} KB")
        except Exception as e:
            logger.error(f"Failed to download avatar: {e}")
            await interaction.followup.send(f"❌ Failed to download avatar: {e}")
            return

        # Process the image (run in executor to avoid blocking)
        await asyncio.to_thread(
            replace_color_squares_in_gif,
            framemog_template,
            temp_input_mogger,
            temp_input_moggee,
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
                os.remove(temp_input_mogger)
                os.remove(temp_input_moggee)
                os.remove(temp_output)
            except FileNotFoundError or OSError:
                pass
            return

        shutil.copy(temp_output, cache_file)
        logger.info(f"Saved to cache: {cache_file}")

        # Clean up old cached versions for this user (different avatar hashes)
        for old_cache in glob.glob(f'cache/framemog/{user.id}_*.gif'):
            if old_cache != cache_file:
                try:
                    os.remove(old_cache)
                    logger.info(f"Removed old cache: {old_cache}")
                except FileNotFoundError or OSError:
                    pass

        # Send the result
        await interaction.followup.send(
            content=f'{user.mention} ran into a frat leader at {interaction.guild.name} and got brutally frame mogged by them 👀😂',
            file=discord.File(temp_output)
        )

        # # TODO: use user_id instead of name? how to covert?
        # #       figure out how to render/embed tables in discord
        # user_boiler = interaction.user.name
        # if user_boiler != user.name:
        #     con = sqlite3.connect(str(boilboard_db))
        #     cur = con.cursor()
        #
        #     if interaction.guild_id is 0:
        #         table_id = interaction.channel_id
        #     else:
        #         table_id = interaction.guild_id
        #
        #     cur.execute(
        #         "CREATE TABLE IF NOT EXISTS ? (user_id int, user_name string, boiler int, boilee int)",
        #                 (table_id,)
        #                 )

            # add 1 to user_boiler under boiler and total
            # add 1 to user.name under boilee and total
            # close db con

        # Clean up temp files
        try:
            os.remove(temp_input_mogger)
            os.remove(temp_input_moggee)
            os.remove(temp_output)
        except FileNotFoundError or OSError:
            pass

    except Exception as e:
        await interaction.followup.send(f"❌ Error processing image: {str(e)}")
        logger.error(f"Error: {e}")