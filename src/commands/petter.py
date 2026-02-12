#!/usr/bin/env python3
"""
PetPet GIF Generator
Creates a petting hand animation over any image.

The key technique: Hand frames have transparent centers, and are drawn
OVER the squished image to create the layered effect.
"""

from PIL import Image, ImageDraw, ImageFont
import math


def create_hand_frame(frame_num, total_frames=10):
    """
    Create a hand sprite with transparent center.
    In production, you'd load actual PNG sprites with alpha channels.
    This generates simple hand shapes to demonstrate the concept.
    """
    size = 112
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Animation parameters
    t = frame_num / total_frames
    angle = math.sin(t * math.pi * 2) * 0.2

    # Hand position varies with animation
    hand_y = 20 + int(math.sin(t * math.pi * 2) * 10)

    # Draw a simple hand shape (in real version, load PNG with alpha)
    # Upper part of hand
    draw.ellipse([25, hand_y - 10, 87, hand_y + 15], fill=(255, 220, 177, 255))

    # Fingers
    for i, x_offset in enumerate([30, 45, 60, 75]):
        finger_y = hand_y - 15 + (i % 2) * 5
        draw.ellipse([x_offset, finger_y, x_offset + 12, finger_y + 20],
                     fill=(255, 220, 177, 255))

    # Palm area - this covers the top of the image
    draw.ellipse([20, hand_y + 10, 92, hand_y + 45], fill=(255, 220, 177, 255))

    # Wrist
    draw.rectangle([35, hand_y + 40, 77, hand_y + 60], fill=(255, 220, 177, 255))

    # Add shading for depth
    draw.ellipse([25, hand_y + 15, 87, hand_y + 40], fill=(240, 200, 160, 100))

    # The CENTER stays transparent - that's where the pet image shows through!
    # In a real hand sprite, this would be a PNG with alpha channel

    return img


def create_squish_parameters(frame_num, total_frames=10):
    """
    Calculate how much to squish the image for each frame.
    Returns: (scale_x, scale_y, offset_y)
    """
    t = frame_num / total_frames

    # Squish cycle - sinusoidal motion
    squish_amount = 1.0 - (math.sin(t * math.pi * 2) * 0.2 + 0.2)

    # When hand presses down, image squishes and shifts
    offset_y = int(math.sin(t * math.pi * 2) * 5)

    return (1.0, squish_amount, offset_y)


def generate_petpet_gif(input_image_path, output_path='petpet.gif', frames=10, duration=40):
    """
    Generate a petpet GIF from an input image.

    Args:
        input_image_path: Path to the image to pet
        output_path: Output GIF path
        frames: Number of frames in animation
        duration: Duration per frame in milliseconds
    """
    # Load and prepare the input image
    pet_img = Image.open(input_image_path).convert('RGBA')

    # Resize to fit the petting area (leave room for hand)
    pet_size = 90
    pet_img = pet_img.resize((pet_size, pet_size), Image.Resampling.LANCZOS)

    gif_frames = []

    for i in range(frames):
        # Create base canvas
        frame = Image.new('RGBA', (112, 112), (255, 255, 255, 0))

        # Get squish parameters for this frame
        scale_x, scale_y, offset_y = create_squish_parameters(i, frames)

        # Calculate squished dimensions
        squished_width = int(pet_size * scale_x)
        squished_height = int(pet_size * scale_y)

        # Squish the pet image
        squished_pet = pet_img.resize((squished_width, squished_height),
                                      Image.Resampling.LANCZOS)

        # Position the squished pet (centered, with offset)
        pet_x = (112 - squished_width) // 2
        pet_y = (112 - squished_height) // 2 + offset_y

        # STEP 1: Draw the pet image on the base layer
        frame.paste(squished_pet, (pet_x, pet_y), squished_pet)

        # STEP 2: Draw the hand OVER the pet (this is the key!)
        hand = create_hand_frame(i, frames)
        frame = Image.alpha_composite(frame, hand)

        # Convert to RGB for GIF
        frame_rgb = Image.new('RGB', (112, 112), (255, 255, 255))
        frame_rgb.paste(frame, (0, 0), frame)

        gif_frames.append(frame_rgb)

    # Save as GIF
    gif_frames[0].save(
        output_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration,
        loop=0,
        optimize=False
    )

    print(f"✅ PetPet GIF saved to: {output_path}")
    print(f"   Frames: {frames}")
    print(f"   Size: 112x112")


def create_demo_image():
    """Create a simple demo image if none provided"""
    img = Image.new('RGB', (200, 200), (100, 150, 255))
    draw = ImageDraw.Draw(img)

    # Draw a simple cat face
    # Face
    draw.ellipse([50, 50, 150, 150], fill=(255, 200, 100))
    # Eyes
    draw.ellipse([70, 80, 90, 100], fill=(50, 50, 50))
    draw.ellipse([110, 80, 130, 100], fill=(50, 50, 50))
    # Nose
    draw.polygon([(100, 105), (95, 115), (105, 115)], fill=(255, 150, 150))
    # Mouth
    draw.arc([80, 105, 120, 130], 0, 180, fill=(50, 50, 50), width=2)
    # Ears
    draw.polygon([(60, 50), (50, 20), (80, 40)], fill=(255, 200, 100))
    draw.polygon([(140, 50), (120, 40), (150, 20)], fill=(255, 200, 100))

    img.save('/tmp/demo_cat.png')
    return '/tmp/demo_cat.png'


if __name__ == '__main__':
    import sys

    print("🐾 PetPet GIF Generator")
    print("=" * 50)

    if len(sys.argv) > 1:
        input_image = sys.argv[1]
        output = sys.argv[2] if len(sys.argv) > 2 else 'petpet.gif'
    else:
        print("No image provided, creating demo image...")
        input_image = create_demo_image()
        output = 'petpet_demo.gif'

    print(f"\nInput: {input_image}")
    print(f"Output: {output}")
    print("\nGenerating animation...")

    generate_petpet_gif(input_image, output)

    print("\n📖 How it works:")
    print("1. Create hand frames with TRANSPARENT centers (alpha channel)")
    print("2. For each frame:")
    print("   a. Squish/deform the pet image")
    print("   b. Draw pet image on base layer")
    print("   c. Draw transparent hand OVER the pet")
    print("3. The hand appears to wrap around because it's layered on top!")