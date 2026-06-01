"""
OMR (Optical Mark Recognition) scanner - detects filled bubbles on answer sheets
using OpenCV image processing and perspective correction.
"""

import cv2
import numpy as np
from typing import Optional

from sheet_generator import (
    SHEET_WIDTH, SHEET_HEIGHT, MARKER_SIZE, MARKER_MARGIN,
    GRID_START_Y, BUBBLE_RADIUS, BUBBLE_SPACING_X,
    BUBBLE_SPACING_Y, QUESTION_NUM_WIDTH,
    STUDENT_NUM_Y, STUDENT_NUM_BUBBLE_RADIUS,
    STUDENT_NUM_SPACING_X, STUDENT_NUM_SPACING_Y,
)

# Threshold for considering a bubble as filled
FILL_THRESHOLD = 0.3

# ROI size around each bubble center for analysis
ROI_SIZE = int(BUBBLE_RADIUS * 1.5)

# Student number ROI size
STUDENT_NUM_ROI_SIZE = int(STUDENT_NUM_BUBBLE_RADIUS * 1.5)


def _preprocess_image(gray: np.ndarray) -> np.ndarray:
    """
    Preprocess image for better OMR detection.
    Applies Gaussian blur and CLAHE for contrast normalization.
    """
    # Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # CLAHE for better contrast in different lighting conditions
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(blurred)

    return enhanced


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order points as: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left has smallest sum
    rect[2] = pts[np.argmax(s)]  # bottom-right has largest sum
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right has smallest difference
    rect[3] = pts[np.argmax(diff)]  # bottom-left has largest difference
    return rect


def _detect_corner_markers(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Detect the 4 corner alignment markers in the image.
    Uses Otsu's method for adaptive thresholding.

    Returns ordered corner points (centers) or None if not found.
    """
    # Preprocess for marker detection
    preprocessed = _preprocess_image(gray)

    # Use Otsu's method for adaptive binary threshold
    _, binary = cv2.threshold(preprocessed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Filter for square-like contours of appropriate size
    h, w = gray.shape
    min_area = (MARKER_SIZE * 0.3) ** 2  # Allow smaller due to image scaling
    max_area = (w * h) * 0.02  # Not too large (2% of image)

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        # Check if approximately square
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) != 4:
            continue

        # Check aspect ratio
        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = float(bw) / bh if bh > 0 else 0
        if 0.6 < aspect < 1.4:
            # Use center of bounding rect
            cx = x + bw // 2
            cy = y + bh // 2
            candidates.append((cx, cy, area))

    if len(candidates) < 4:
        return None

    # Sort by area descending and take top candidates
    candidates.sort(key=lambda c: c[2], reverse=True)

    # From top candidates, find the 4 that are closest to corners
    img_corners = np.array([
        [0, 0], [w, 0], [w, h], [0, h]
    ], dtype="float32")

    best_four = []
    used = set()
    for corner in img_corners:
        best_dist = float("inf")
        best_idx = -1
        for i, (cx, cy, _) in enumerate(candidates[:20]):
            if i in used:
                continue
            dist = np.sqrt((cx - corner[0])**2 + (cy - corner[1])**2)
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        if best_idx >= 0:
            used.add(best_idx)
            best_four.append(candidates[best_idx][:2])

    if len(best_four) != 4:
        return None

    points = np.array(best_four, dtype="float32")
    return _order_points(points)


def _perspective_transform(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Apply perspective transform to get a flat top-down view."""
    dst = np.array([
        [0, 0],
        [SHEET_WIDTH - 1, 0],
        [SHEET_WIDTH - 1, SHEET_HEIGHT - 1],
        [0, SHEET_HEIGHT - 1]
    ], dtype="float32")

    matrix = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(image, matrix, (SHEET_WIDTH, SHEET_HEIGHT))
    return warped


def _get_bubble_positions(num_questions: int, num_options: int, grid_start_y: int = GRID_START_Y) -> list:
    """
    Calculate expected positions of each bubble based on the sheet layout.

    Returns list of (question_index, option_index, center_x, center_y).
    """
    positions = []
    use_two_columns = num_questions > 20
    if use_two_columns:
        col1_count = (num_questions + 1) // 2
    else:
        col1_count = num_questions

    col1_x = 200
    col2_x = SHEET_WIDTH // 2 + 100

    for q in range(num_questions):
        if q < col1_count:
            base_x = col1_x + QUESTION_NUM_WIDTH
            row = q
        else:
            base_x = col2_x + QUESTION_NUM_WIDTH
            row = q - col1_count

        y = grid_start_y + row * BUBBLE_SPACING_Y

        for opt in range(num_options):
            cx = base_x + opt * BUBBLE_SPACING_X
            cy = y
            positions.append((q, opt, cx, cy))

    return positions


def _analyze_bubble(gray: np.ndarray, cx: int, cy: int, roi_size: int = ROI_SIZE) -> float:
    """
    Analyze a single bubble position and return the fill ratio.
    Uses Otsu's method on the ROI for adaptive thresholding.

    Returns the ratio of dark pixels in the bubble ROI.
    """
    h, w = gray.shape
    x1 = max(0, cx - roi_size)
    y1 = max(0, cy - roi_size)
    x2 = min(w, cx + roi_size)
    y2 = min(h, cy + roi_size)

    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    # Use Otsu's method on the ROI for adaptive thresholding
    _, roi_binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Calculate fill ratio
    total_pixels = roi_binary.size
    dark_pixels = cv2.countNonZero(roi_binary)
    return dark_pixels / total_pixels if total_pixels > 0 else 0.0


def detect_student_number(warped_gray: np.ndarray) -> Optional[int]:
    """
    Detect the student number from the student number bubble section.
    Reads two rows: tens digit (0-4) and units digit (0-9).

    Args:
        warped_gray: Grayscale perspective-corrected image

    Returns:
        Detected student number (1-50) or None if not detected
    """
    # Preprocess the warped image for better bubble detection
    preprocessed = _preprocess_image(warped_gray)

    # Student number section starts at STUDENT_NUM_Y + 50 (after label)
    section_start_y = STUDENT_NUM_Y + 50
    base_x = 350  # Same as in sheet_generator

    # Row 1: Tens digit (0-4)
    tens_ratios = []
    for i in range(5):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y
        ratio = _analyze_bubble(preprocessed, cx, cy, STUDENT_NUM_ROI_SIZE)
        tens_ratios.append(ratio)

    # Row 2: Units digit (0-9)
    units_ratios = []
    for i in range(10):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y + STUDENT_NUM_SPACING_Y
        ratio = _analyze_bubble(preprocessed, cx, cy, STUDENT_NUM_ROI_SIZE)
        units_ratios.append(ratio)

    # Detect tens digit
    tens_filled = [(i, r) for i, r in enumerate(tens_ratios) if r > FILL_THRESHOLD]
    if len(tens_filled) == 1:
        tens_digit = tens_filled[0][0]
    elif len(tens_filled) > 1:
        # Take highest fill ratio
        tens_filled.sort(key=lambda x: x[1], reverse=True)
        tens_digit = tens_filled[0][0]
    else:
        tens_digit = None

    # Detect units digit
    units_filled = [(i, r) for i, r in enumerate(units_ratios) if r > FILL_THRESHOLD]
    if len(units_filled) == 1:
        units_digit = units_filled[0][0]
    elif len(units_filled) > 1:
        units_filled.sort(key=lambda x: x[1], reverse=True)
        units_digit = units_filled[0][0]
    else:
        units_digit = None

    # Combine digits
    if tens_digit is not None and units_digit is not None:
        number = tens_digit * 10 + units_digit
        if 1 <= number <= 50:
            return number
    elif tens_digit is None and units_digit is not None:
        # Only units filled (number 1-9)
        if 1 <= units_digit <= 9:
            return units_digit

    return None


def scan_answer_sheet(
    image_path: str,
    num_questions: int,
    num_options: int,
    correct_answers: list,
    include_student_numbers: bool = True,
) -> dict:
    """
    Scan an answer sheet image and grade it.

    Args:
        image_path: Path to the photo of the filled answer sheet
        num_questions: Number of questions on the sheet
        num_options: Number of options per question (2-5)
        correct_answers: List of correct answer indices (0-based)
        include_student_numbers: Whether to detect student number bubbles

    Returns:
        dict with keys:
            - answers: list of detected answers (letter or None for no mark, 'X' for multiple)
            - score: number of correct answers
            - total: total number of questions
            - details: list of dicts with per-question breakdown
            - student_number: detected student number or None
            - error: error message if processing failed, else None
    """
    option_letters = "ABCDE"[:num_options]

    result = {
        "answers": [],
        "score": 0,
        "total": num_questions,
        "details": [],
        "student_number": None,
        "error": None,
    }

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        result["error"] = "Rasmni o'qib bo'lmadi. Iltimos qaytadan yuboring."
        return result

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Detect corner markers
    corners = _detect_corner_markers(gray)
    if corners is None:
        result["error"] = (
            "Burchak belgilari topilmadi. Iltimos qaytadan suratga oling:\n"
            "- Varaqani tekis joyga qo'ying\n"
            "- 4 ta burchak belgilari ko'rinsin\n"
            "- Yaxshi yorug'likda suratga oling"
        )
        return result

    # Apply perspective transform
    warped = _perspective_transform(image, corners)
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # Preprocess the warped image
    preprocessed = _preprocess_image(warped_gray)

    # Detect student number if enabled
    if include_student_numbers:
        student_num = detect_student_number(warped_gray)
        result["student_number"] = student_num

    # Calculate grid start Y based on whether student numbers are included
    if include_student_numbers:
        # Match the layout from sheet_generator when student numbers are present
        # STUDENT_NUM_Y + 50 (label) + 2 rows * STUDENT_NUM_SPACING_Y + 30 (separator) + 60 (info)
        grid_y = STUDENT_NUM_Y + 50 + 2 * STUDENT_NUM_SPACING_Y + 30 + 60
    else:
        grid_y = GRID_START_Y

    # Get bubble positions
    positions = _get_bubble_positions(num_questions, num_options, grid_y)

    # Analyze each bubble using preprocessed image
    fill_ratios = {}
    for q_idx, opt_idx, cx, cy in positions:
        ratio = _analyze_bubble(preprocessed, cx, cy)
        if q_idx not in fill_ratios:
            fill_ratios[q_idx] = []
        fill_ratios[q_idx].append((opt_idx, ratio))

    # Determine answers
    score = 0
    for q_idx in range(num_questions):
        ratios = fill_ratios.get(q_idx, [])
        filled = [(opt_idx, ratio) for opt_idx, ratio in ratios if ratio > FILL_THRESHOLD]

        if len(filled) == 0:
            # No answer detected
            detected = None
            letter = "-"
        elif len(filled) == 1:
            # Single answer
            detected = filled[0][0]
            letter = option_letters[detected]
        else:
            # Multiple marks - take the one with highest fill ratio
            # but mark as potentially invalid if close
            filled.sort(key=lambda x: x[1], reverse=True)
            if filled[0][1] - filled[1][1] > 0.15:
                # Clear winner
                detected = filled[0][0]
                letter = option_letters[detected]
            else:
                # Too close - mark as invalid
                detected = None
                letter = "X"

        correct = correct_answers[q_idx] if q_idx < len(correct_answers) else None
        is_correct = (detected is not None and detected == correct)
        if is_correct:
            score += 1

        correct_letter = option_letters[correct] if correct is not None else "?"

        result["answers"].append(letter)
        result["details"].append({
            "question": q_idx + 1,
            "detected": letter,
            "correct": correct_letter,
            "is_correct": is_correct,
        })

    result["score"] = score
    return result
