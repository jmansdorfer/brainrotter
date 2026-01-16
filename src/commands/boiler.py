import asyncio
import glob
import logging
from pathlib import Path
import os
import shutil

import discord
import numpy as np
from PIL import Image, ImageSequence
from PIL.Image import Palette


def replace_green_square_in_gif(
        boiler_template: Path,
        image_path,
        output_path,
        size=None
):
    """
    Replace green screen area in a GIF with a custom image.

    Args:
        boiler_template: Path to template GIF with green square
        image_path: Path to image to insert
        output_path: Path to save output GIF
        size: Optional tuple (width, height) for image size. If None, auto-detect from green area
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

                result = frame.copy()

                # Simply paste the insert image at the position
                # The insert_image is already the right size (constant across all frames)
                # We'll paste it, and it will show through where it fits
                result.paste(insert_image_for_frame, pos_this_frame, insert_image_for_frame)

                # Replace green pixels with the resized insert image
                frame_with_insert = result
            else:
                # No valid green area, just use the frame as-is
                frame_with_insert = frame
        else:
            # No green in this frame, don't add the image at all
            frame_with_insert = frame

        # Convert back to P mode (palette) for smaller file size, matching original GIF format
        frame_with_insert = frame_with_insert.convert('RGB').convert('P', palette=Palette.ADAPTIVE, colors=64)

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


async def boiler(interaction:discord.Interaction, user:discord.User, boiler_template:Path, logger:logging.Logger):
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