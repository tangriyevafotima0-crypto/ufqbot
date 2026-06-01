"""
Answer sheet generator V6 - creates printable A4 answer sheets with alignment markers
and bubble grids for OMR scanning.

V6 improvements:
- Bordered name/surname input fields with clear labels
- Visual section separators between title, name fields, student numbers, and bubble grid
- Improved overall layout and readability
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
GRID_START_Y = 550
BUBBLE_RADIUS = 22
BUBBLE_SPACING_X = 90
BUBBLE_SPACING_Y = 80
QUESTION_NUM_WIDTH = 80
COLUMN_GAP = 200

# Student number section settings
STUDENT_NUM_Y = 450  # Y position for student number section
STUDENT_NUM_BUBBLE_RADIUS = 18
STUDENT_NUM_SPACING_X = 70
STUDENT_NUM_SPACING_Y = 55


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


def _draw_student_number_section(draw: ImageDraw.Draw, start_y: int) -> int:
    """
    Draw a student number bubble section with 2 rows:
    - Tens digit (0-4)
    - Units digit (0-9)

    Returns the Y position after this section.
    """
    label_font = _get_font(32)
    bubble_font = _get_font(20)

    # Section label
    draw.text((200, start_y), "O'quvchi raqami:", fill="black", font=label_font)
    start_y += 50

    # Row labels and bubbles
    rows = [
        ("O'nlik:", list(range(5))),   # 0, 1, 2, 3, 4
        ("Birlik:", list(range(10))),   # 0, 1, 2, 3, 4, 5, 6, 7, 8, 9
    ]

    row_label_font = _get_font(26)
    base_x = 350  # Starting X for bubbles after label

    for row_label, digits in rows:
        draw.text((200, start_y - 10), row_label, fill="black", font=row_label_font)

        for i, digit in enumerate(digits):
            cx = base_x + i * STUDENT_NUM_SPACING_X
            cy = start_y
            r = STUDENT_NUM_BUBBLE_RADIUS

            # Draw hollow circle
            draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                outline="black", width=2
            )
            # Draw digit inside
            digit_str = str(digit)
            lbbox = draw.textbbox((0, 0), digit_str, font=bubble_font)
            lw = lbbox[2] - lbbox[0]
            lh = lbbox[3] - lbbox[1]
            draw.text(
                (cx - lw // 2, cy - lh // 2 - 2),
                digit_str, fill="black", font=bubble_font
            )

        start_y += STUDENT_NUM_SPACING_Y

    # Add separator line
    start_y += 10
    draw.line([(200, start_y), (SHEET_WIDTH - 200, start_y)], fill="gray", width=1)
    start_y += 20

    return start_y


def generate_answer_sheet(
    num_questions: int,
    num_options: int = 4,
    include_student_numbers: bool = True,
) -> Image.Image:
    """
    Generate an A4 answer sheet image.

    Args:
        num_questions: Number of questions (1-100)
        num_options: Number of answer options per question (2-5, default 4)
        include_student_numbers: Whether to include student number bubbles

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

    # Decorative horizontal line below title
    draw.line([(200, 260), (SHEET_WIDTH - 200, 260)], fill="black", width=2)

    # Name and surname fields with bordered boxes
    label_font_small = _get_font(28)
    # ISM (first name) field
    draw.text((200, 278), "ISM (BOSMA HARFLAR):", fill="black", font=label_font_small)
    draw.rectangle([(200, 295), (1050, 360)], outline="black", width=2)

    # FAMILIYA (surname) field
    draw.text((200, 365), "FAMILIYA (BOSMA HARFLAR):", fill="black", font=label_font_small)
    draw.rectangle([(200, 382), (1050, 435)], outline="black", width=2)

    # Separator line between name fields and student number section
    draw.line([(200, 445), (SHEET_WIDTH - 200, 445)], fill="black", width=2)

    # Student number section
    if include_student_numbers:
        grid_start = _draw_student_number_section(draw, STUDENT_NUM_Y)
    else:
        grid_start = GRID_START_Y

    # Info line
    info_font = _get_font(36)
    info_text = f"Savollar soni: {num_questions}   Variantlar: {option_letters}"
    draw.text((200, grid_start), info_text, fill="black", font=info_font)
    grid_start += 60

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
        y = grid_start + i * BUBBLE_SPACING_Y
        draw_question_row(i + 1, col1_x, y)

    # Draw column 2
    for i in range(col2_count):
        y = grid_start + i * BUBBLE_SPACING_Y
        draw_question_row(col1_count + i + 1, col2_x, y)

    # Footer
    footer_font = _get_font(28)
    footer_text = "V6 | Diqqat: Javobni to'liq qora rangda bo'yang. Har bir savolga faqat 1 javob."
    bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    fw = bbox[2] - bbox[0]
    draw.text(
        ((SHEET_WIDTH - fw) // 2, SHEET_HEIGHT - 200),
        footer_text, fill="black", font=footer_font
    )

    return img
