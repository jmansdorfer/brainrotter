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


def replace_green_square_in_gif(
        boiler_template: Path,
        image_path,
        output_path,
        size=None,
        gifsicle_lossy=30,
        blur_radius=0.5,
        colors=60,
):
    """
    Replace green screen area in a GIF with a custom image.

    Args:
        boiler_template: Path to template GIF with green square
        image_path: Path to image to insert
        output_path: Path to save output GIF
        size: Optional tuple (width, height) for image size. If None, auto-detect from green area
        gifsicle_lossy: Lossy compression level for gifsicle (0-200, higher = smaller/lossier). Set to None to skip.
        blur_radius: Gaussian blur radius applied to the insert image to reduce compression-hostile detail. Set to 0 to skip.
        colors: Number of colors in the palette
    """
    # Load the template GIF and the image to insert
    template = Image.open(boiler_template)
    insert_image = Image.open(image_path).convert('RGBA')

    frames = []
    durations = []

    # Detect the size from the largest green area across all frames
    max_size = (0, 0)
    max_green_pixels = 0

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

            if green_count > 0:
                rows = np.any(test_mask, axis=1)
                cols = np.any(test_mask, axis=0)
                if rows.any() and cols.any():
                    y_min, y_max = np.where(rows)[0][[0, -1]]
                    x_min, x_max = np.where(cols)[0][[0, -1]]
                    frame_size = (int(x_max - x_min + 1), int(y_max - y_min + 1))
                    if frame_size[0] * frame_size[1] > max_size[0] * max_size[1]:
                        max_size = frame_size

    # Keep original image for per-frame resizing
    insert_image_original = insert_image.copy()

    # Process each frame
    for frame in ImageSequence.Iterator(template):
        frame = frame.convert('RGBA')
        frame_array = np.array(frame)

        green_mask = (
                (frame_array[:, :, 1] > 200) &
                (frame_array[:, :, 0] < 100) &
                (frame_array[:, :, 2] < 100)
        )

        green_count = np.sum(green_mask)

        if green_count > 0:
            rows = np.any(green_mask, axis=1)
            cols = np.any(green_mask, axis=0)

            if rows.any() and cols.any():
                y_min, y_max = np.where(rows)[0][[0, -1]]
                x_min, x_max = np.where(cols)[0][[0, -1]]
                pos_this_frame = (int(x_min), int(y_min))
                size_this_frame = (int(x_max - x_min + 1), int(y_max - y_min + 1))

                insert_image_for_frame = insert_image_original.resize(
                    size_this_frame, Image.Resampling.LANCZOS
                )

                # Slight blur to reduce compression-hostile detail from the insert image
                if blur_radius and blur_radius > 0:
                    insert_image_for_frame = insert_image_for_frame.filter(
                        ImageFilter.GaussianBlur(radius=blur_radius)
                    )

                result = frame.copy()
                result.paste(insert_image_for_frame, pos_this_frame, insert_image_for_frame)
                frame_with_insert = result
            else:
                frame_with_insert = frame
        else:
            frame_with_insert = frame

        # Convert back to P mode (palette) for smaller file size, matching original GIF format
        frame_with_insert = frame_with_insert.convert('RGB').convert(
            'P', palette=Palette.ADAPTIVE, colors=colors
        )

        frames.append(frame_with_insert)
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


async def boiler(
        interaction:discord.Interaction,
        user:discord.User,
        boiler_template:Path,
        # boilboard_db:Path,
        logger:logging.Logger
):
    # If no user specified, use the command author
    if user is None:
        user = interaction.user

    # Use display_name or global_name for logging to avoid discriminator issues
    requester_name = interaction.user.display_name or interaction.user.name
    target_name = user.display_name or user.name
    logger.info(f"Boil request: {requester_name} wants to boil {target_name}'s avatar")

    # Defer the response since this might take a moment
    await interaction.response.defer() # type: ignore

    try:
        # Get avatar hash for cache key
        avatar_hash = user.display_avatar.key
        cache_file = f'cache/{user.id}_{avatar_hash}.gif'

        # Check if cached version exists
        if os.path.exists(cache_file):
            logger.info(f"Using cached GIF for {target_name} (hash: {avatar_hash})")

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
        await asyncio.to_thread(
            replace_green_square_in_gif,
            boiler_template,
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
            except FileNotFoundError or OSError:
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
                except FileNotFoundError or OSError:
                    pass

        # Send the result
        await interaction.followup.send(
            content=f'"hey {user.mention}" and they\'re boiled 😭😭😭😭',
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
            os.remove(temp_input)
            os.remove(temp_output)
        except FileNotFoundError or OSError:
            pass

    except Exception as e:
        await interaction.followup.send(f"❌ Error processing image: {str(e)}")
        logger.error(f"Error: {e}")