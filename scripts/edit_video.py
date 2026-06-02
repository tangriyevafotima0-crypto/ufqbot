#!/usr/bin/env python3
"""
True Self Video Editor
Extracts audio from source video, generates themed images, creates subtitles,
and combines everything into a final edited video.
"""

import os
import sys
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# === Configuration ===
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_VIDEO = PROJECT_ROOT / "YTMP3GG_Shorts_Fang-yuan-s-perseverance-webnovel-anime-_Media_Z3sbrdiKn1g_001_1080p.mp4"
OUTPUT_DIR = PROJECT_ROOT / "edited_videos"
OUTPUT_VIDEO = OUTPUT_DIR / "true_self_edit.mp4"
FFMPEG = "/usr/local/bin/ffmpeg"
FFPROBE = "/usr/local/bin/ffprobe"

WIDTH = 1080
HEIGHT = 1920
FPS = 30
DURATION = 56.354830

FONT_PATH = "/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf"

# Slide content
SLIDES = [
    {
        "title": "Discover Your\nTrue Self",
        "color_top": (15, 5, 40),
        "color_bottom": (5, 0, 25),
        "accent": (130, 80, 220),
    },
    {
        "title": "The Path\nWithin",
        "color_top": (5, 15, 45),
        "color_bottom": (0, 5, 25),
        "accent": (60, 130, 220),
    },
    {
        "title": "Awaken\nYour Power",
        "color_top": (30, 5, 35),
        "color_bottom": (15, 0, 20),
        "accent": (200, 100, 180),
    },
    {
        "title": "Inner\nStrength",
        "color_top": (5, 20, 35),
        "color_bottom": (0, 10, 20),
        "accent": (50, 180, 160),
    },
    {
        "title": "Beyond\nthe Illusion",
        "color_top": (20, 5, 40),
        "color_bottom": (10, 0, 25),
        "accent": (160, 60, 200),
    },
    {
        "title": "Perseverance",
        "color_top": (10, 10, 35),
        "color_bottom": (5, 5, 20),
        "accent": (220, 150, 50),
    },
    {
        "title": "The Real\nYou",
        "color_top": (5, 10, 40),
        "color_bottom": (0, 5, 25),
        "accent": (80, 160, 240),
    },
    {
        "title": "Transcendence",
        "color_top": (25, 5, 30),
        "color_bottom": (12, 0, 18),
        "accent": (180, 120, 255),
    },
    {
        "title": "Embrace\nthe Journey",
        "color_top": (5, 15, 30),
        "color_bottom": (0, 8, 18),
        "accent": (100, 200, 180),
    },
]

SUBTITLE_TEXTS = [
    "Your true self awaits beyond every challenge...",
    "Look within to find the strength you seek.",
    "The power to change lies inside you.",
    "True strength is born from perseverance.",
    "See through the illusions of doubt and fear.",
    "Every step forward reveals more of who you are.",
    "You are more than what the world sees.",
    "Rise above limitations, embrace your infinite nature.",
    "The journey inward is the greatest adventure.",
]


def run_cmd(cmd, desc=""):
    """Run a subprocess command and check for errors."""
    print(f"  Running: {desc or ' '.join(cmd[:3])}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:500]}")
        sys.exit(1)
    return result


def create_gradient(draw, width, height, color_top, color_bottom):
    """Create a vertical gradient background."""
    for y in range(height):
        ratio = y / height
        r = int(color_top[0] + (color_bottom[0] - color_top[0]) * ratio)
        g = int(color_top[1] + (color_bottom[1] - color_top[1]) * ratio)
        b = int(color_top[2] + (color_bottom[2] - color_top[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def draw_orbs(draw, width, height, accent, seed):
    """Draw decorative glowing orbs."""
    import random
    rng = random.Random(seed)

    for _ in range(5):
        x = rng.randint(50, width - 50)
        y = rng.randint(100, height - 100)
        radius = rng.randint(20, 80)

        for r in range(radius, 0, -2):
            alpha_ratio = r / radius
            color = (
                int(accent[0] * (1 - alpha_ratio) * 0.3),
                int(accent[1] * (1 - alpha_ratio) * 0.3),
                int(accent[2] * (1 - alpha_ratio) * 0.3),
            )
            draw.ellipse(
                [x - r, y - r, x + r, y + r],
                fill=color,
            )


def draw_mandala(draw, cx, cy, accent, seed):
    """Draw a mandala-like pattern of circles."""
    import random
    rng = random.Random(seed)

    num_rings = rng.randint(2, 4)
    for ring in range(1, num_rings + 1):
        ring_radius = ring * 80
        num_circles = ring * 6
        for i in range(num_circles):
            angle = (2 * math.pi * i) / num_circles
            x = int(cx + ring_radius * math.cos(angle))
            y = int(cy + ring_radius * math.sin(angle))
            small_r = rng.randint(5, 15)
            opacity = max(10, int(40 / ring))
            color = (
                min(255, accent[0] // 3 + opacity),
                min(255, accent[1] // 3 + opacity),
                min(255, accent[2] // 3 + opacity),
            )
            draw.ellipse([x - small_r, y - small_r, x + small_r, y + small_r], fill=color)

    # Central circle
    draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=accent)


def draw_light_rays(draw, width, height, accent, seed):
    """Draw subtle light rays from top."""
    import random
    rng = random.Random(seed)

    num_rays = rng.randint(3, 6)
    for _ in range(num_rays):
        start_x = rng.randint(0, width)
        end_x = start_x + rng.randint(-200, 200)
        ray_color = (
            accent[0] // 8,
            accent[1] // 8,
            accent[2] // 8,
        )
        for offset in range(-3, 4):
            draw.line(
                [(start_x + offset, 0), (end_x + offset, height // 2)],
                fill=ray_color,
                width=1,
            )


def generate_image(slide_data, index, output_path):
    """Generate a single themed image."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)

    # Background gradient
    create_gradient(draw, WIDTH, HEIGHT, slide_data["color_top"], slide_data["color_bottom"])

    accent = slide_data["accent"]
    seed = index * 42

    # Decorative elements
    draw_light_rays(draw, WIDTH, HEIGHT, accent, seed + 1)
    draw_orbs(draw, WIDTH, HEIGHT, accent, seed + 2)
    draw_mandala(draw, WIDTH // 2, HEIGHT // 2 + 300, accent, seed + 3)

    # Outer ring decoration at top
    cx, cy = WIDTH // 2, 400
    ring_color = (accent[0] // 4, accent[1] // 4, accent[2] // 4)
    draw.ellipse([cx - 120, cy - 120, cx + 120, cy + 120], outline=ring_color, width=2)
    draw.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], outline=ring_color, width=1)

    # Title text
    try:
        font_large = ImageFont.truetype(FONT_PATH, 90)
    except Exception:
        font_large = ImageFont.load_default()

    title = slide_data["title"]
    lines = title.split("\n")

    # Calculate total text height
    line_heights = []
    line_widths = []
    for line in lines:
        bbox = font_large.getbbox(line)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        line_heights.append(lh)
        line_widths.append(lw)

    total_text_height = sum(line_heights) + (len(lines) - 1) * 30
    start_y = (HEIGHT - total_text_height) // 2 - 100

    for i, line in enumerate(lines):
        lw = line_widths[i]
        x = (WIDTH - lw) // 2
        y = start_y + sum(line_heights[:i]) + i * 30

        # Text shadow
        draw.text((x + 3, y + 3), line, font=font_large, fill=(0, 0, 0))
        # Main text
        draw.text((x, y), line, font=font_large, fill=(255, 255, 255))

    # Subtitle decorative line below text
    line_y = start_y + total_text_height + 60
    draw.line(
        [(WIDTH // 2 - 100, line_y), (WIDTH // 2 + 100, line_y)],
        fill=accent,
        width=2,
    )

    img.save(output_path, "PNG")


def extract_audio(source_video, output_audio):
    """Extract audio from source video."""
    print("\n[Step 1] Extracting audio...")
    cmd = [
        FFMPEG, "-y", "-i", str(source_video),
        "-vn", "-acodec", "copy", str(output_audio)
    ]
    run_cmd(cmd, "Extract audio")
    print(f"  Audio saved to: {output_audio}")


def generate_images(temp_dir):
    """Generate all themed images."""
    print("\n[Step 2] Generating True Self themed images...")
    image_paths = []
    for i, slide in enumerate(SLIDES):
        img_path = temp_dir / f"slide_{i:02d}.png"
        generate_image(slide, i, img_path)
        image_paths.append(img_path)
        print(f"  Generated: slide_{i:02d}.png")
    return image_paths


def create_subtitles(srt_path):
    """Create SRT subtitle file."""
    print("\n[Step 3] Creating subtitles...")
    num_subs = len(SUBTITLE_TEXTS)
    interval = DURATION / num_subs

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, text in enumerate(SUBTITLE_TEXTS):
            start_time = i * interval
            end_time = (i + 1) * interval

            start_str = format_srt_time(start_time)
            end_str = format_srt_time(end_time)

            f.write(f"{i + 1}\n")
            f.write(f"{start_str} --> {end_str}\n")
            f.write(f"{text}\n\n")

    print(f"  Subtitles saved to: {srt_path}")


def format_srt_time(seconds):
    """Convert seconds to SRT time format HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def create_final_video(image_paths, audio_path, srt_path, output_path, temp_dir):
    """Combine images, audio, and subtitles into final video."""
    print("\n[Step 4] Creating final video...")

    num_images = len(image_paths)
    duration_per_image = DURATION / num_images

    # Create concat file for ffmpeg
    concat_file = temp_dir / "filelist.txt"
    with open(concat_file, "w") as f:
        for img_path in image_paths:
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {duration_per_image:.4f}\n")
        # Repeat last image to avoid ffmpeg cutting it short
        f.write(f"file '{image_paths[-1]}'\n")

    # Copy SRT to temp_dir for subtitle filter (avoids path escaping issues)
    temp_srt = temp_dir / "subtitles.srt"
    shutil.copy2(srt_path, temp_srt)

    # Build ffmpeg command
    # Use concat demuxer for images, add audio, burn in subtitles
    cmd = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(audio_path),
        "-vf", f"subtitles={str(temp_srt)}:force_style='FontSize=22,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Alignment=2,MarginV=80'",
        "-c:v", "libx264",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "copy",
        "-shortest",
        "-t", str(DURATION),
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print("  Subtitle burn-in failed, trying with drawtext fallback...")
        print(f"  Error was: {result.stderr[:300]}")

        # Fallback: use drawtext filter instead
        # We'll skip subtitles burn-in and just create the video without them
        # but keep the SRT file for reference
        cmd_fallback = [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(audio_path),
            "-c:v", "libx264",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-c:a", "copy",
            "-shortest",
            "-t", str(DURATION),
            str(output_path),
        ]
        run_cmd(cmd_fallback, "Create video without subtitles (fallback)")
        print("  Video created without burned-in subtitles (SRT file kept for reference)")
    else:
        print("  Video created with burned-in subtitles")

    print(f"  Output: {output_path}")


def verify_output(output_path):
    """Verify the output video with ffprobe."""
    print("\n[Step 5] Verifying output...")
    cmd = [
        FFPROBE, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ERROR: ffprobe failed!")
        sys.exit(1)

    import json
    info = json.loads(result.stdout)

    streams = info.get("streams", [])
    has_video = any(s["codec_type"] == "video" for s in streams)
    has_audio = any(s["codec_type"] == "audio" for s in streams)
    duration = float(info.get("format", {}).get("duration", 0))

    print(f"  Has video stream: {has_video}")
    print(f"  Has audio stream: {has_audio}")
    print(f"  Duration: {duration:.2f}s (expected ~{DURATION:.2f}s)")
    print(f"  File size: {os.path.getsize(output_path) / (1024*1024):.2f} MB")

    if not has_video or not has_audio:
        print("  ERROR: Missing streams!")
        sys.exit(1)
    if abs(duration - DURATION) > 5:
        print("  WARNING: Duration mismatch is large!")

    print("\n  Verification PASSED!")


def main():
    print("=" * 60)
    print("  TRUE SELF VIDEO EDITOR")
    print("=" * 60)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create temp working directory
    with tempfile.TemporaryDirectory(prefix="true_self_") as temp_dir:
        temp_path = Path(temp_dir)

        # Step 1: Extract audio
        audio_path = temp_path / "extracted_audio.aac"
        extract_audio(SOURCE_VIDEO, audio_path)

        # Step 2: Generate images
        image_paths = generate_images(temp_path)

        # Step 3: Create subtitles (save in output dir for reference)
        srt_path = OUTPUT_DIR / "true_self_edit.srt"
        create_subtitles(srt_path)

        # Step 4: Create final video
        create_final_video(image_paths, audio_path, srt_path, OUTPUT_VIDEO, temp_path)

    # Step 5: Verify
    verify_output(OUTPUT_VIDEO)

    print("\n" + "=" * 60)
    print("  COMPLETE! Output: edited_videos/true_self_edit.mp4")
    print("=" * 60)


if __name__ == "__main__":
    main()
