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
    BUBBLE_SPACING_Y, QUESTION_NUM_WIDTH, BUBBLE_SPACING_X as _BSX
)

# Threshold for considering a bubble as filled
FILL_THRESHOLD = 0.3

# ROI size around each bubble center for analysis
ROI_SIZE = int(BUBBLE_RADIUS * 1.5)


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

    Returns ordered corner points (centers) or None if not found.
    """
    # Apply binary threshold
    _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY_INV)

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


def _get_bubble_positions(num_questions: int, num_options: int) -> list:
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

        y = GRID_START_Y + row * BUBBLE_SPACING_Y

        for opt in range(num_options):
            cx = base_x + opt * BUBBLE_SPACING_X
            cy = y
            positions.append((q, opt, cx, cy))

    return positions


def _analyze_bubble(gray: np.ndarray, cx: int, cy: int) -> float:
    """
    Analyze a single bubble position and return the fill ratio.

    Returns the ratio of dark pixels in the bubble ROI.
    """
    h, w = gray.shape
    x1 = max(0, cx - ROI_SIZE)
    y1 = max(0, cy - ROI_SIZE)
    x2 = min(w, cx + ROI_SIZE)
    y2 = min(h, cy + ROI_SIZE)

    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    # Threshold the ROI
    _, roi_binary = cv2.threshold(roi, 127, 255, cv2.THRESH_BINARY_INV)

    # Calculate fill ratio
    total_pixels = roi_binary.size
    dark_pixels = cv2.countNonZero(roi_binary)
    return dark_pixels / total_pixels if total_pixels > 0 else 0.0


def scan_answer_sheet(
    image_path: str,
    num_questions: int,
    num_options: int,
    correct_answers: list
) -> dict:
    """
    Scan an answer sheet image and grade it.

    Args:
        image_path: Path to the photo of the filled answer sheet
        num_questions: Number of questions on the sheet
        num_options: Number of options per question (2-5)
        correct_answers: List of correct answer indices (0-based)

    Returns:
        dict with keys:
            - answers: list of detected answers (letter or None for no mark, 'X' for multiple)
            - score: number of correct answers
            - total: total number of questions
            - details: list of dicts with per-question breakdown
            - error: error message if processing failed, else None
    """
    option_letters = "ABCDE"[:num_options]

    result = {
        "answers": [],
        "score": 0,
        "total": num_questions,
        "details": [],
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
    else:
        # Apply perspective transform
        warped = _perspective_transform(image, corners)
        warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # Get bubble positions
    positions = _get_bubble_positions(num_questions, num_options)

    # Analyze each bubble
    fill_ratios = {}
    for q_idx, opt_idx, cx, cy in positions:
        ratio = _analyze_bubble(warped_gray, cx, cy)
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
