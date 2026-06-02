#!/usr/bin/env python3
"""
True Self Video Editor - v2 (Artistic Illustrated Version)

Produces a professional video with:
- Whisper-based audio transcription for accurate subtitles
- Beautiful generated artistic/illustrated images depicting spiritual awakening themes
- Smooth crossfade transitions between images using ffmpeg xfade filter
- Elegant PlayfairDisplay font styling for subtitles
"""

import math
import os
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

# === Configuration ===
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SOURCE_VIDEO = PROJECT_ROOT / "YTMP3GG_Shorts_Fang-yuan-s-perseverance-webnovel-anime-_Media_Z3sbrdiKn1g_001_1080p.mp4"
OUTPUT_DIR = PROJECT_ROOT / "edited_videos"
OUTPUT_VIDEO = OUTPUT_DIR / "true_self_edit.mp4"
OUTPUT_SRT = OUTPUT_DIR / "true_self_edit.srt"
FONTS_DIR = PROJECT_ROOT / "assets" / "fonts"
FONT_PATH = FONTS_DIR / "PlayfairDisplay.ttf"
FFMPEG = "/usr/local/bin/ffmpeg"
FFPROBE = "/usr/local/bin/ffprobe"

WIDTH = 1080
HEIGHT = 1920
FPS = 30


# ============================================================
# AUDIO EXTRACTION
# ============================================================

def extract_audio_aac(source_video, output_path):
    """Extract AAC audio from source video without re-encoding."""
    print("[1/6] Extracting audio (AAC copy)...")
    cmd = [
        FFMPEG, "-y", "-i", str(source_video),
        "-vn", "-acodec", "copy", str(output_path)
    ]
    _run(cmd)
    print(f"  -> {output_path}")


def extract_audio_wav(source_video, output_path):
    """Extract audio as 16kHz mono WAV for Whisper."""
    print("[2/6] Extracting audio (WAV for Whisper)...")
    cmd = [
        FFMPEG, "-y", "-i", str(source_video),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(output_path)
    ]
    _run(cmd)
    print(f"  -> {output_path}")


# ============================================================
# WHISPER TRANSCRIPTION
# ============================================================

def transcribe_audio(wav_path, srt_path):
    """Transcribe audio using Whisper and write SRT file."""
    print("[3/6] Transcribing audio with Whisper (base model)...")
    try:
        import whisper
    except ImportError:
        print("  ERROR: openai-whisper is not installed.")
        print("  Install it with: pip install openai-whisper")
        sys.exit(1)

    try:
        model = whisper.load_model("base")
    except Exception as e:
        print(f"  ERROR: Failed to load Whisper model: {e}")
        print("  This may be a network issue (model download) or a torch incompatibility.")
        sys.exit(1)

    result = model.transcribe(str(wav_path), language=None)

    segments = result.get("segments", [])
    print(f"  Found {len(segments)} segments")

    if len(segments) == 0:
        print("  WARNING: Whisper returned 0 segments. Audio may be silent or unrecognizable.")
        print("  Writing a minimal placeholder SRT so the video can still be built.")
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("1\n")
            f.write("00:00:00,000 --> 00:00:05,000\n")
            f.write("[No speech detected]\n\n")
        return segments

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, 1):
            start = seg["start"]
            end = seg["end"]
            text = seg["text"].strip()
            f.write(f"{i}\n")
            f.write(f"{_srt_time(start)} --> {_srt_time(end)}\n")
            f.write(f"{text}\n\n")

    print(f"  -> SRT saved to {srt_path}")
    return segments


def _srt_time(seconds):
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ============================================================
# ARTISTIC IMAGE GENERATION (Pillow)
# ============================================================

def generate_all_images(output_dir, num_images=8):
    """Generate artistic illustrated images for spiritual awakening themes."""
    print(f"[4/6] Generating {num_images} artistic images...")

    generators = [
        _img_meditating_silhouette,
        _img_inner_light,
        _img_breaking_chains,
        _img_cosmic_consciousness,
        _img_lotus_flower,
        _img_phoenix_transformation,
        _img_aurora_figure,
        _img_sacred_geometry,
    ]

    paths = []
    for i, gen_func in enumerate(generators[:num_images]):
        path = output_dir / f"art_{i:02d}.png"
        img = gen_func(i)
        img.save(str(path), "PNG")
        paths.append(path)
        print(f"  Generated art_{i:02d}.png")

    return paths


def _make_canvas():
    """Create a new RGBA canvas."""
    return Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 255))


def _gradient_bg(img, colors):
    """Apply a vertical gradient with multiple color stops."""
    draw = ImageDraw.Draw(img)
    n_stops = len(colors)
    for y in range(HEIGHT):
        # Determine which segment we're in
        pos = y / HEIGHT * (n_stops - 1)
        idx = min(int(pos), n_stops - 2)
        t = pos - idx
        c1 = colors[idx]
        c2 = colors[idx + 1]
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b, 255))


def _star_field(img, seed, count=200):
    """Draw a field of stars (small bright dots)."""
    rng = random.Random(seed)
    draw = ImageDraw.Draw(img)
    for _ in range(count):
        x = rng.randint(0, WIDTH - 1)
        y = rng.randint(0, HEIGHT - 1)
        size = rng.choice([1, 1, 1, 2, 2, 3])
        brightness = rng.randint(150, 255)
        color = (brightness, brightness, rng.randint(200, 255), rng.randint(100, 255))
        if size == 1:
            draw.point((x, y), fill=color)
        else:
            draw.ellipse([x, y, x + size, y + size], fill=color)


def _radial_glow(img, cx, cy, radius, color, intensity=0.6):
    """Draw a radial glow effect using concentric circles."""
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    steps = min(radius, 80)
    for i in range(steps, 0, -1):
        r = int(radius * i / steps)
        alpha = int(255 * intensity * (1 - i / steps) * 0.5)
        alpha = max(0, min(255, alpha))
        c = (color[0], color[1], color[2], alpha)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    img.paste(Image.alpha_composite(img, overlay))


def _nebula_effect(img, seed, colors=None):
    """Add nebula-like blobs using large semi-transparent ellipses."""
    rng = random.Random(seed)
    if colors is None:
        colors = [(120, 40, 180), (40, 80, 180), (180, 40, 120)]
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(6):
        cx = rng.randint(100, WIDTH - 100)
        cy = rng.randint(200, HEIGHT - 200)
        rx = rng.randint(150, 400)
        ry = rng.randint(150, 400)
        color = rng.choice(colors)
        alpha = rng.randint(20, 50)
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry],
                     fill=(color[0], color[1], color[2], alpha))
    img.paste(Image.alpha_composite(img, overlay))


def _particles(img, seed, cx, cy, spread, count=80, color=(255, 220, 100)):
    """Scatter particles around a center point."""
    rng = random.Random(seed)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for _ in range(count):
        angle = rng.uniform(0, 2 * math.pi)
        dist = rng.gauss(0, spread / 2)
        x = int(cx + dist * math.cos(angle))
        y = int(cy + dist * math.sin(angle))
        size = rng.randint(1, 4)
        alpha = rng.randint(80, 220)
        c = (color[0], color[1], color[2], alpha)
        draw.ellipse([x - size, y - size, x + size, y + size], fill=c)
    img.paste(Image.alpha_composite(img, overlay))


def _silhouette_person(img, cx, cy, scale=1.0, color=(0, 0, 0, 255)):
    """Draw a simple person silhouette (circle head + body shape)."""
    draw = ImageDraw.Draw(img)
    head_r = int(40 * scale)
    # Head
    draw.ellipse([cx - head_r, cy - head_r - int(120 * scale),
                  cx + head_r, cy + head_r - int(120 * scale)], fill=color)
    # Body (trapezoid)
    body_top = cy - int(80 * scale)
    body_bot = cy + int(120 * scale)
    top_half = int(30 * scale)
    bot_half = int(70 * scale)
    draw.polygon([
        (cx - top_half, body_top),
        (cx + top_half, body_top),
        (cx + bot_half, body_bot),
        (cx - bot_half, body_bot),
    ], fill=color)
    # Legs
    leg_bot = cy + int(250 * scale)
    draw.polygon([
        (cx - bot_half, body_bot),
        (cx - int(20 * scale), body_bot),
        (cx - int(30 * scale), leg_bot),
        (cx - int(60 * scale), leg_bot),
    ], fill=color)
    draw.polygon([
        (cx + int(20 * scale), body_bot),
        (cx + bot_half, body_bot),
        (cx + int(60 * scale), leg_bot),
        (cx + int(30 * scale), leg_bot),
    ], fill=color)


def _img_meditating_silhouette(seed):
    """A silhouette of a person meditating with cosmic energy radiating."""
    img = _make_canvas()
    _gradient_bg(img, [(5, 0, 30), (20, 5, 60), (40, 10, 80), (10, 0, 40)])
    _star_field(img, seed * 10, count=300)
    _nebula_effect(img, seed * 11, colors=[(80, 30, 160), (30, 60, 140), (140, 30, 100)])

    cx, cy = WIDTH // 2, HEIGHT // 2 + 200

    # Radial energy around the figure
    _radial_glow(img, cx, cy - 50, 500, (100, 50, 200), intensity=0.4)
    _radial_glow(img, cx, cy - 50, 300, (150, 100, 255), intensity=0.5)

    # Energy rays
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rng = random.Random(seed * 12)
    for i in range(24):
        angle = i * math.pi / 12
        length = rng.randint(300, 600)
        x2 = int(cx + length * math.cos(angle))
        y2 = int((cy - 50) + length * math.sin(angle))
        draw.line([(cx, cy - 50), (x2, y2)],
                  fill=(180, 120, 255, 30), width=3)
    img.paste(Image.alpha_composite(img, overlay))

    # Particles radiating out
    _particles(img, seed * 13, cx, cy - 50, 350, count=120, color=(180, 140, 255))

    # Meditating figure silhouette (seated cross-legged)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    sil_color = (10, 5, 20, 240)
    # Head
    draw.ellipse([cx - 35, cy - 140, cx + 35, cy - 70], fill=sil_color)
    # Body
    draw.polygon([(cx - 25, cy - 70), (cx + 25, cy - 70),
                  (cx + 60, cy + 40), (cx - 60, cy + 40)], fill=sil_color)
    # Crossed legs (wider at bottom)
    draw.ellipse([cx - 90, cy + 20, cx + 90, cy + 100], fill=sil_color)
    img.paste(Image.alpha_composite(img, overlay))

    return img.convert("RGB")


def _img_inner_light(seed):
    """A figure with bright light emanating from chest area."""
    img = _make_canvas()
    _gradient_bg(img, [(5, 5, 15), (10, 5, 30), (5, 5, 20)])
    _star_field(img, seed * 20, count=150)

    cx, cy = WIDTH // 2, HEIGHT // 2 + 100
    chest_y = cy - 30

    # Bright core light from chest
    _radial_glow(img, cx, chest_y, 600, (255, 230, 150), intensity=0.3)
    _radial_glow(img, cx, chest_y, 350, (255, 200, 80), intensity=0.5)
    _radial_glow(img, cx, chest_y, 150, (255, 255, 200), intensity=0.8)

    # Light rays from chest
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rng = random.Random(seed * 21)
    for i in range(36):
        angle = i * math.pi / 18
        length = rng.randint(200, 500)
        x2 = int(cx + length * math.cos(angle))
        y2 = int(chest_y + length * math.sin(angle))
        draw.line([(cx, chest_y), (x2, y2)],
                  fill=(255, 240, 180, 40), width=2)
    img.paste(Image.alpha_composite(img, overlay))

    # Figure silhouette
    _silhouette_person(img, cx, cy, scale=1.2, color=(5, 3, 10, 230))

    # Bright spot at center of chest
    _radial_glow(img, cx, chest_y, 60, (255, 255, 255), intensity=1.0)

    _particles(img, seed * 22, cx, chest_y, 300, count=60, color=(255, 230, 100))

    return img.convert("RGB")


def _img_breaking_chains(seed):
    """Abstract chains breaking with light bursting through."""
    img = _make_canvas()
    _gradient_bg(img, [(10, 5, 25), (25, 10, 50), (60, 20, 80), (20, 5, 40)])
    _star_field(img, seed * 30, count=100)

    cx, cy = WIDTH // 2, HEIGHT // 2

    # Central burst of light
    _radial_glow(img, cx, cy, 500, (255, 200, 50), intensity=0.4)
    _radial_glow(img, cx, cy, 250, (255, 255, 150), intensity=0.6)

    # Draw chain links (broken)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    chain_color = (80, 80, 90, 200)

    # Left chain fragments
    for i in range(5):
        lx = cx - 200 - i * 40
        ly = cy - 100 + i * 80
        draw.ellipse([lx - 25, ly - 15, lx + 25, ly + 15],
                     outline=chain_color, width=6)

    # Right chain fragments
    for i in range(5):
        rx = cx + 200 + i * 40
        ry = cy - 100 + i * 80
        draw.ellipse([rx - 25, ry - 15, rx + 25, ry + 15],
                     outline=chain_color, width=6)

    # Breaking fragments in center
    rng = random.Random(seed * 31)
    for _ in range(12):
        fx = cx + rng.randint(-80, 80)
        fy = cy + rng.randint(-80, 80)
        size = rng.randint(5, 15)
        draw.rectangle([fx, fy, fx + size, fy + size],
                       fill=(100, 100, 110, 180))

    img.paste(Image.alpha_composite(img, overlay))

    # Light burst particles
    _particles(img, seed * 32, cx, cy, 250, count=150, color=(255, 220, 80))
    _particles(img, seed * 33, cx, cy, 150, count=80, color=(255, 255, 200))

    # Energy explosion lines
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    for i in range(20):
        angle = i * math.pi / 10 + 0.1
        length = rng.randint(150, 400)
        x2 = int(cx + length * math.cos(angle))
        y2 = int(cy + length * math.sin(angle))
        draw.line([(cx, cy), (x2, y2)], fill=(255, 255, 200, 60), width=3)
    img.paste(Image.alpha_composite(img, overlay))

    return img.convert("RGB")


def _img_cosmic_consciousness(seed):
    """Galaxy/nebula background with an eye shape."""
    img = _make_canvas()
    _gradient_bg(img, [(0, 0, 10), (5, 10, 40), (15, 5, 50), (5, 0, 20)])
    _star_field(img, seed * 40, count=400)
    _nebula_effect(img, seed * 41, colors=[(60, 20, 120), (20, 60, 150), (100, 20, 80)])

    cx, cy = WIDTH // 2, HEIGHT // 2

    # Cosmic eye shape
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Eye outline using arcs (almond shape from two curves)
    eye_w, eye_h = 300, 150
    # Upper lid
    points_upper = []
    points_lower = []
    for i in range(50):
        t = i / 49
        x = cx - eye_w + 2 * eye_w * t
        y_upper = cy - eye_h * math.sin(math.pi * t)
        y_lower = cy + eye_h * math.sin(math.pi * t)
        points_upper.append((int(x), int(y_upper)))
        points_lower.append((int(x), int(y_lower)))

    # Draw eye shape
    eye_points = points_upper + list(reversed(points_lower))
    draw.polygon(eye_points, outline=(100, 150, 255, 180), fill=(20, 30, 80, 100))

    # Iris
    draw.ellipse([cx - 80, cy - 80, cx + 80, cy + 80],
                 fill=(30, 60, 140, 180), outline=(100, 150, 255, 200), width=3)
    # Pupil
    draw.ellipse([cx - 35, cy - 35, cx + 35, cy + 35], fill=(5, 5, 20, 240))
    # Highlight
    draw.ellipse([cx - 15, cy - 20, cx + 5, cy - 5], fill=(200, 220, 255, 150))

    img.paste(Image.alpha_composite(img, overlay))

    # Glow around the eye
    _radial_glow(img, cx, cy, 400, (60, 100, 200), intensity=0.3)
    _particles(img, seed * 42, cx, cy, 400, count=100, color=(100, 150, 255))

    return img.convert("RGB")


def _img_lotus_flower(seed):
    """Lotus flower with ethereal glow and particles floating around."""
    img = _make_canvas()
    _gradient_bg(img, [(5, 10, 25), (10, 20, 50), (20, 40, 70), (5, 15, 35)])
    _star_field(img, seed * 50, count=150)

    cx, cy = WIDTH // 2, HEIGHT // 2 + 150

    # Glow behind lotus
    _radial_glow(img, cx, cy, 400, (200, 100, 180), intensity=0.3)
    _radial_glow(img, cx, cy, 200, (255, 150, 200), intensity=0.4)

    # Draw lotus petals
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Multiple layers of petals
    petal_colors = [
        (200, 80, 150, 160),
        (220, 120, 170, 140),
        (240, 160, 200, 120),
    ]

    for layer, color in enumerate(petal_colors):
        num_petals = 8 + layer * 2
        petal_len = 120 + layer * 40
        petal_width = 50 + layer * 10
        for i in range(num_petals):
            angle = (2 * math.pi * i / num_petals) + layer * 0.15
            # Petal as an ellipse rotated to the angle
            px = cx + int(petal_len * 0.4 * math.cos(angle))
            py = cy + int(petal_len * 0.4 * math.sin(angle))
            # Approximate petal with polygon
            tip_x = cx + int(petal_len * math.cos(angle))
            tip_y = cy + int(petal_len * math.sin(angle))
            perp_angle = angle + math.pi / 2
            side_x = int(petal_width * 0.4 * math.cos(perp_angle))
            side_y = int(petal_width * 0.4 * math.sin(perp_angle))
            draw.polygon([
                (cx + side_x, cy + side_y),
                (tip_x, tip_y),
                (cx - side_x, cy - side_y),
            ], fill=color)

    # Center of lotus
    draw.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=(255, 220, 100, 200))
    draw.ellipse([cx - 15, cy - 15, cx + 15, cy + 15], fill=(255, 255, 200, 220))

    img.paste(Image.alpha_composite(img, overlay))

    # Floating particles
    _particles(img, seed * 51, cx, cy - 200, 400, count=100, color=(255, 180, 220))
    _particles(img, seed * 52, cx, cy, 300, count=60, color=(255, 255, 150))

    return img.convert("RGB")


def _img_phoenix_transformation(seed):
    """Bird-like shape made of fire/light particles."""
    img = _make_canvas()
    _gradient_bg(img, [(20, 5, 5), (40, 10, 15), (60, 15, 10), (20, 5, 5)])
    _star_field(img, seed * 60, count=100)

    cx, cy = WIDTH // 2, HEIGHT // 2

    # Fire glow
    _radial_glow(img, cx, cy, 500, (200, 80, 20), intensity=0.3)
    _radial_glow(img, cx, cy, 300, (255, 150, 30), intensity=0.4)

    # Phoenix shape using particles along wing curves
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rng = random.Random(seed * 61)

    # Body line
    for t in range(100):
        tt = t / 99.0
        bx = cx
        by = int(cy + 200 - 400 * tt)
        size = rng.randint(3, 8)
        alpha = rng.randint(150, 255)
        color = (255, rng.randint(100, 200), rng.randint(0, 50), alpha)
        draw.ellipse([bx - size, by - size, bx + size, by + size], fill=color)

    # Wings (curved arcs of particles)
    for wing_dir in [-1, 1]:
        for t in range(80):
            tt = t / 79.0
            angle = tt * math.pi * 0.7
            wx = int(cx + wing_dir * (50 + 350 * tt) * math.cos(angle * 0.5))
            wy = int(cy - 50 - 250 * math.sin(angle) * tt)
            size = rng.randint(2, 6)
            alpha = rng.randint(120, 230)
            r = rng.randint(200, 255)
            g = rng.randint(80, 180)
            color = (r, g, 20, alpha)
            draw.ellipse([wx - size, wy - size, wx + size, wy + size], fill=color)

    # Tail feathers (downward flowing)
    for t in range(60):
        tt = t / 59.0
        spread = rng.gauss(0, 30)
        tx = int(cx + spread)
        ty = int(cy + 200 + 300 * tt)
        size = rng.randint(2, 5)
        alpha = int(200 * (1 - tt))
        color = (255, rng.randint(60, 130), 10, alpha)
        draw.ellipse([tx - size, ty - size, tx + size, ty + size], fill=color)

    img.paste(Image.alpha_composite(img, overlay))

    # Bright core
    _radial_glow(img, cx, cy - 50, 100, (255, 255, 200), intensity=0.8)
    _particles(img, seed * 62, cx, cy, 300, count=80, color=(255, 200, 50))

    return img.convert("RGB")


def _img_aurora_figure(seed):
    """Aurora borealis sky with a small contemplative figure at bottom."""
    img = _make_canvas()
    _gradient_bg(img, [(0, 5, 15), (5, 15, 35), (10, 30, 50), (5, 10, 25)])
    _star_field(img, seed * 70, count=300)

    # Aurora bands
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    rng = random.Random(seed * 71)

    aurora_colors = [
        (50, 200, 100),
        (30, 180, 150),
        (80, 220, 80),
        (40, 150, 200),
        (100, 255, 120),
    ]

    for band in range(5):
        base_y = 200 + band * 180
        color = aurora_colors[band % len(aurora_colors)]
        points = []
        for x in range(0, WIDTH + 20, 20):
            y_offset = int(60 * math.sin(x / 150.0 + band * 1.5 + seed))
            y_offset += rng.randint(-20, 20)
            points.append((x, base_y + y_offset))

        # Draw thick aurora band
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            for dy in range(-40, 40, 2):
                alpha = int(40 * (1 - abs(dy) / 40.0))
                c = (color[0], color[1], color[2], alpha)
                draw.line([(x1, y1 + dy), (x2, y2 + dy)], fill=c, width=2)

    img.paste(Image.alpha_composite(img, overlay))

    # Ground silhouette at bottom
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    ground_y = HEIGHT - 300
    draw.rectangle([0, ground_y, WIDTH, HEIGHT], fill=(5, 5, 10, 250))

    # Small figure silhouette
    fig_x, fig_y = WIDTH // 2, ground_y - 10
    # Standing figure (small)
    draw.ellipse([fig_x - 12, fig_y - 70, fig_x + 12, fig_y - 46], fill=(5, 5, 10, 250))
    draw.polygon([(fig_x - 10, fig_y - 46), (fig_x + 10, fig_y - 46),
                  (fig_x + 20, fig_y), (fig_x - 20, fig_y)], fill=(5, 5, 10, 250))

    img.paste(Image.alpha_composite(img, overlay))

    # Subtle glow on horizon
    _radial_glow(img, WIDTH // 2, ground_y, 300, (40, 150, 100), intensity=0.2)

    return img.convert("RGB")


def _img_sacred_geometry(seed):
    """Overlapping circles forming flower of life pattern with glow."""
    img = _make_canvas()
    _gradient_bg(img, [(5, 0, 20), (15, 5, 40), (25, 10, 60), (10, 0, 30)])
    _star_field(img, seed * 80, count=200)

    cx, cy = WIDTH // 2, HEIGHT // 2

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Flower of life: 7 circles (1 center + 6 around it)
    radius = 120
    centers = [(cx, cy)]
    for i in range(6):
        angle = i * math.pi / 3
        x = int(cx + radius * math.cos(angle))
        y = int(cy + radius * math.sin(angle))
        centers.append((x, y))

    # Second ring
    for i in range(6):
        angle = i * math.pi / 3 + math.pi / 6
        x = int(cx + radius * 1.73 * math.cos(angle))
        y = int(cy + radius * 1.73 * math.sin(angle))
        centers.append((x, y))

    # Third ring
    for i in range(12):
        angle = i * math.pi / 6
        x = int(cx + radius * 2 * math.cos(angle))
        y = int(cy + radius * 2 * math.sin(angle))
        centers.append((x, y))

    # Draw all circles
    circle_color = (100, 160, 255, 80)
    glow_color = (80, 140, 220, 30)
    for (x, y) in centers:
        # Glow
        draw.ellipse([x - radius - 10, y - radius - 10,
                      x + radius + 10, y + radius + 10], fill=glow_color)
        # Circle outline
        draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                     outline=circle_color, width=2)

    img.paste(Image.alpha_composite(img, overlay))

    # Central glow
    _radial_glow(img, cx, cy, 350, (80, 120, 220), intensity=0.3)
    _radial_glow(img, cx, cy, 150, (150, 200, 255), intensity=0.4)

    # Particles at intersections
    _particles(img, seed * 81, cx, cy, 250, count=80, color=(150, 200, 255))

    return img.convert("RGB")


# ============================================================
# VIDEO ASSEMBLY WITH XFADE TRANSITIONS
# ============================================================

def get_video_duration(source_video):
    """Get duration of source video using ffprobe."""
    import json

    source_path = Path(source_video)
    if not source_path.exists():
        print(f"  ERROR: Source video not found: {source_video}")
        print("  Please check that the file path is correct and the file exists.")
        sys.exit(1)

    cmd = [
        FFPROBE, "-v", "quiet", "-print_format", "json",
        "-show_format", str(source_video)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  ERROR: ffprobe failed (exit code {result.returncode})")
            print(f"  stderr: {result.stderr[:500]}")
            print("  The source video may be corrupted or unreadable.")
            sys.exit(1)
        info = json.loads(result.stdout)
        return float(info["format"]["duration"])
    except subprocess.TimeoutExpired:
        print("  ERROR: ffprobe timed out reading the source video.")
        sys.exit(1)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"  ERROR: Could not parse video duration from ffprobe output: {e}")
        print(f"  ffprobe stdout: {result.stdout[:300]}")
        print("  The source video may be missing duration metadata.")
        sys.exit(1)


def build_video_with_xfade(image_paths, audio_path, srt_path, output_path, total_duration, temp_dir):
    """
    Build final video using xfade transitions between image clips.

    Strategy: Create each image as a short video clip, then chain xfade filters.
    """
    print("[5/6] Building video with xfade transitions...")

    num_images = len(image_paths)
    transition_duration = 1.0
    # Each image shows for: (total + (n-1)*transition) / n
    # Because xfade overlaps transition_duration between adjacent clips
    clip_duration = (total_duration + (num_images - 1) * transition_duration) / num_images

    print(f"  Total duration: {total_duration:.2f}s")
    print(f"  Clip duration: {clip_duration:.2f}s")
    print(f"  Transition: {transition_duration}s crossfade")

    # Build complex ffmpeg command with all images as inputs
    # Each image input is looped for clip_duration
    inputs = []
    for i, img_path in enumerate(image_paths):
        inputs.extend([
            "-loop", "1", "-t", f"{clip_duration:.3f}",
            "-framerate", str(FPS), "-i", str(img_path)
        ])

    # Build xfade filter chain
    # First xfade: [0][1]xfade=transition=fade:duration=1:offset=X[v01]
    # Second: [v01][2]xfade=...[v012]
    # etc.
    filter_parts = []
    offset = clip_duration - transition_duration

    if num_images == 1:
        filter_complex = "[0:v]scale=1080:1920,format=yuv420p[outv]"
    else:
        prev_label = "0:v"
        for i in range(1, num_images):
            out_label = f"v{i}"
            curr_offset = offset + (i - 1) * (clip_duration - transition_duration)
            filter_parts.append(
                f"[{prev_label}][{i}:v]xfade=transition=fade:duration={transition_duration}:offset={curr_offset:.3f}[{out_label}]"
            )
            prev_label = out_label

        # Add scale and format to the final output
        filter_parts.append(f"[{prev_label}]scale=1080:1920,format=yuv420p[outv]")
        filter_complex = ";".join(filter_parts)

    # Copy SRT to temp dir to avoid path escaping issues
    temp_srt = temp_dir / "subs.srt"
    import shutil
    shutil.copy2(srt_path, temp_srt)

    # Subtitle filter using fontsdir for custom font
    fonts_dir_str = str(FONTS_DIR).replace("'", "'\\''").replace(":", "\\:")
    srt_str = str(temp_srt).replace("'", "'\\''").replace(":", "\\:")
    sub_filter = (
        f"subtitles={srt_str}"
        f":fontsdir={fonts_dir_str}"
        f":force_style='FontName=PlayfairDisplay,FontSize=24,"
        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"Outline=2,Shadow=1,Alignment=2,MarginV=60'"
    )

    # Full filter: xfade chain -> subtitles
    full_filter = filter_complex.replace("[outv]", "[previd]") + f";[previd]{sub_filter}[outv]"

    cmd = [
        FFMPEG, "-y",
    ] + inputs + [
        "-i", str(audio_path),
        "-filter_complex", full_filter,
        "-map", "[outv]",
        "-map", f"{num_images}:a",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "copy",
        "-shortest",
        str(output_path),
    ]

    print("  Running ffmpeg xfade assembly...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        print(f"  xfade with subtitles failed: {result.stderr[-500:]}")
        print("  Trying without subtitle burn-in...")

        # Try without subtitles
        cmd_nosub = [
            FFMPEG, "-y",
        ] + inputs + [
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", f"{num_images}:a",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "copy",
            "-shortest",
            str(output_path),
        ]

        result2 = subprocess.run(cmd_nosub, capture_output=True, text=True, timeout=600)
        if result2.returncode != 0:
            print(f"  xfade without subs also failed: {result2.stderr[-500:]}")
            print("  Falling back to simpler approach...")
            _fallback_concat(image_paths, audio_path, srt_path, output_path, total_duration, temp_dir)
        else:
            print("  Video created without burned-in subtitles (SRT available separately)")
    else:
        print("  Video assembled with xfade transitions and subtitles!")


def _fallback_concat(image_paths, audio_path, srt_path, output_path, total_duration, temp_dir):
    """Fallback: use concat demuxer with zoompan for motion effect."""
    print("  Using concat demuxer fallback with zoompan...")
    import shutil

    num_images = len(image_paths)
    clip_dur = total_duration / num_images

    concat_file = temp_dir / "concat.txt"
    with open(concat_file, "w") as f:
        for img_path in image_paths:
            f.write(f"file '{img_path}'\n")
            f.write(f"duration {clip_dur:.4f}\n")
        f.write(f"file '{image_paths[-1]}'\n")

    temp_srt = temp_dir / "subs.srt"
    shutil.copy2(srt_path, temp_srt)

    fonts_dir_str = str(FONTS_DIR).replace("'", "'\\''").replace(":", "\\:")
    srt_str = str(temp_srt).replace("'", "'\\''").replace(":", "\\:")
    sub_filter = (
        f"subtitles={srt_str}"
        f":fontsdir={fonts_dir_str}"
        f":force_style='FontName=PlayfairDisplay,FontSize=24,"
        f"PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        f"Outline=2,Shadow=1,Alignment=2,MarginV=60'"
    )

    cmd = [
        FFMPEG, "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(audio_path),
        "-vf", f"format=yuv420p,{sub_filter}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-r", str(FPS),
        "-c:a", "copy",
        "-shortest",
        "-t", str(total_duration),
        str(output_path),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        print(f"  Concat with subs failed: {result.stderr[-300:]}")
        # Last resort: no subtitles
        cmd2 = [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", str(audio_path),
            "-vf", "format=yuv420p",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-r", str(FPS),
            "-c:a", "copy",
            "-shortest",
            "-t", str(total_duration),
            str(output_path),
        ]
        result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
        if result2.returncode != 0:
            print(f"  FATAL: {result2.stderr[-500:]}")
            sys.exit(1)
        print("  Created video without subtitles (fallback)")
    else:
        print("  Created video with concat + subtitles")


# ============================================================
# VERIFICATION
# ============================================================

def verify_output(output_path):
    """Verify the output video with ffprobe."""
    print("\n[6/6] Verifying output...")
    import json
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

    info = json.loads(result.stdout)
    streams = info.get("streams", [])
    has_video = any(s["codec_type"] == "video" for s in streams)
    has_audio = any(s["codec_type"] == "audio" for s in streams)
    duration = float(info.get("format", {}).get("duration", 0))

    print(f"  Has video: {has_video}")
    print(f"  Has audio: {has_audio}")
    print(f"  Duration: {duration:.2f}s")
    print(f"  File size: {os.path.getsize(output_path) / (1024*1024):.2f} MB")

    if not has_video or not has_audio:
        print("  ERROR: Missing streams!")
        sys.exit(1)
    if abs(duration - 56.35) > 5:
        print("  WARNING: Duration deviation > 5s from expected 56.35s!")

    print("  PASSED!")


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("  TRUE SELF VIDEO EDITOR v2 - Artistic Illustrated")
    print("=" * 60)

    # Ensure directories exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FONTS_DIR.mkdir(parents=True, exist_ok=True)

    # Get source video duration
    total_duration = get_video_duration(SOURCE_VIDEO)
    print(f"\nSource video duration: {total_duration:.2f}s")

    with tempfile.TemporaryDirectory(prefix="true_self_v2_") as temp_dir:
        temp_path = Path(temp_dir)

        # Step 1: Extract AAC audio
        audio_aac = temp_path / "audio.aac"
        extract_audio_aac(SOURCE_VIDEO, audio_aac)

        # Step 2: Extract WAV for Whisper
        audio_wav = temp_path / "audio.wav"
        extract_audio_wav(SOURCE_VIDEO, audio_wav)

        # Step 3: Transcribe with Whisper (write SRT to temp first)
        temp_srt = temp_path / "true_self_edit.srt"
        segments = transcribe_audio(audio_wav, temp_srt)

        # Step 4: Generate artistic images
        image_paths = generate_all_images(temp_path, num_images=8)

        # Step 5: Build final video with xfade transitions
        build_video_with_xfade(
            image_paths, audio_aac, temp_srt, OUTPUT_VIDEO,
            total_duration, temp_path
        )

        # Step 6: Verify
        verify_output(OUTPUT_VIDEO)

        # Only copy SRT to final output path after video assembly succeeds
        import shutil
        shutil.copy2(temp_srt, OUTPUT_SRT)
        print(f"  SRT copied to final path: {OUTPUT_SRT}")

    print("\n" + "=" * 60)
    print("  COMPLETE!")
    print(f"  Video: {OUTPUT_VIDEO}")
    print(f"  Subtitles: {OUTPUT_SRT}")
    print("=" * 60)


def _run(cmd):
    """Run a command and check return code."""
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"  CMD FAILED: {' '.join(cmd[:5])}")
        print(f"  STDERR: {result.stderr[-500:]}")
        sys.exit(1)
    return result


if __name__ == "__main__":
    main()
