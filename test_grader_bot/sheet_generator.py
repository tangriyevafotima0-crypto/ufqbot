"""
Answer sheet generator - creates printable A4 answer sheets with alignment markers
and bubble grids for OMR scanning.
"""

from PIL import Image, ImageDraw, ImageFont


# A4 at 300 DPI
SHEET_WIDTH = 2480
SHEET_HEIGHT = 3508

# Corner marker settings
MARKER_SIZE = 50
MARKER_MARGIN = 60

# Layout settings
TITLE_Y = 180
NAME_Y = 320
GRID_START_Y = 550
BUBBLE_RADIUS = 22
BUBBLE_SPACING_X = 90
BUBBLE_SPACING_Y = 80
QUESTION_NUM_WIDTH = 80
COLUMN_GAP = 200


def _draw_corner_markers(draw: ImageDraw.Draw) -> None:
    """Draw 4 filled black squares at corners for alignment detection."""
    positions = [
        (MARKER_MARGIN, MARKER_MARGIN),  # top-left
        (SHEET_WIDTH - MARKER_MARGIN - MARKER_SIZE, MARKER_MARGIN),  # top-right
        (MARKER_MARGIN, SHEET_HEIGHT - MARKER_MARGIN - MARKER_SIZE),  # bottom-left
        (SHEET_WIDTH - MARKER_MARGIN - MARKER_SIZE,
         SHEET_HEIGHT - MARKER_MARGIN - MARKER_SIZE),  # bottom-right
    ]
    for x, y in positions:
        draw.rectangle([x, y, x + MARKER_SIZE, y + MARKER_SIZE], fill="black")


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    """Try to load a system font, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def generate_answer_sheet(num_questions: int, num_options: int = 4) -> Image.Image:
    """
    Generate an A4 answer sheet image.

    Args:
        num_questions: Number of questions (1-100)
        num_options: Number of answer options per question (2-5, default 4)

    Returns:
        PIL Image object of the answer sheet
    """
    if num_options < 2:
        num_options = 2
    elif num_options > 5:
        num_options = 5

    option_letters = "ABCDE"[:num_options]

    img = Image.new("RGB", (SHEET_WIDTH, SHEET_HEIGHT), "white")
    draw = ImageDraw.Draw(img)

    # Draw corner markers
    _draw_corner_markers(draw)

    # Title
    title_font = _get_font(72)
    title = "TEST JAVOB VARAQASI"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_width = bbox[2] - bbox[0]
    draw.text(
        ((SHEET_WIDTH - title_width) // 2, TITLE_Y),
        title, fill="black", font=title_font
    )

    # Name and surname fields
    field_font = _get_font(48)
    draw.text((200, NAME_Y), "Ism: ____________________", fill="black", font=field_font)
    draw.text((200, NAME_Y + 80), "Familiya: ____________________", fill="black", font=field_font)

    # Info line
    info_font = _get_font(36)
    info_text = f"Savollar soni: {num_questions}   Variantlar: {option_letters}"
    draw.text((200, NAME_Y + 180), info_text, fill="black", font=info_font)

    # Determine layout: 2 columns if more than 20 questions
    use_two_columns = num_questions > 20
    if use_two_columns:
        col1_count = (num_questions + 1) // 2
        col2_count = num_questions - col1_count
    else:
        col1_count = num_questions
        col2_count = 0

    # Column starting positions
    col1_x = 200
    col2_x = SHEET_WIDTH // 2 + 100

    bubble_font = _get_font(28)
    q_font = _get_font(32)

    def draw_question_row(q_num: int, start_x: int, y: int) -> None:
        """Draw one question row with number and bubbles."""
        # Question number
        q_text = f"{q_num}."
        draw.text((start_x, y - 16), q_text, fill="black", font=q_font)

        # Bubbles
        bubble_start_x = start_x + QUESTION_NUM_WIDTH
        for i, letter in enumerate(option_letters):
            cx = bubble_start_x + i * BUBBLE_SPACING_X
            cy = y
            # Draw hollow circle
            draw.ellipse(
                [cx - BUBBLE_RADIUS, cy - BUBBLE_RADIUS,
                 cx + BUBBLE_RADIUS, cy + BUBBLE_RADIUS],
                outline="black", width=2
            )
            # Draw letter inside
            lbbox = draw.textbbox((0, 0), letter, font=bubble_font)
            lw = lbbox[2] - lbbox[0]
            lh = lbbox[3] - lbbox[1]
            draw.text(
                (cx - lw // 2, cy - lh // 2 - 2),
                letter, fill="black", font=bubble_font
            )

    # Draw column 1
    for i in range(col1_count):
        y = GRID_START_Y + i * BUBBLE_SPACING_Y
        draw_question_row(i + 1, col1_x, y)

    # Draw column 2
    for i in range(col2_count):
        y = GRID_START_Y + i * BUBBLE_SPACING_Y
        draw_question_row(col1_count + i + 1, col2_x, y)

    # Footer
    footer_font = _get_font(28)
    footer_text = "Diqqat: Javobni to'liq qora rangda bo'yang. Har bir savolga faqat 1 javob."
    bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    fw = bbox[2] - bbox[0]
    draw.text(
        ((SHEET_WIDTH - fw) // 2, SHEET_HEIGHT - 200),
        footer_text, fill="black", font=footer_font
    )

    return img
