"""
OMR (Optical Mark Recognition) scanner - detects filled bubbles on answer sheets
using OpenCV image processing and perspective correction.

Uses relative bubble comparison (comparing fill ratios within the same question)
instead of absolute thresholds for more robust detection across varying
lighting and printing conditions.
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

# Relative comparison thresholds
RELATIVE_RATIO_THRESHOLD = 1.8  # Darkest must be 1.8x the second darkest
MIN_FILL_RATIO = 0.12  # Minimum fill ratio to consider as marked
EMPTY_THRESHOLD = 0.08  # Below this, bubble is considered empty

# ROI size around each bubble center for analysis
ROI_SIZE = int(BUBBLE_RADIUS * 1.5)

# Student number ROI size
STUDENT_NUM_ROI_SIZE = int(STUDENT_NUM_BUBBLE_RADIUS * 1.5)


def _preprocess_image(gray: np.ndarray) -> np.ndarray:
    """
    Preprocess image for better OMR detection.
    Applies Gaussian blur and CLAHE for contrast normalization.
    """
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
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


def _find_square_markers(binary: np.ndarray, gray: np.ndarray) -> list:
    """
    Find square marker candidates from a binary image.
    Returns list of (cx, cy, area) tuples.
    """
    h, w = gray.shape
    min_area = (MARKER_SIZE * 0.3) ** 2
    max_area = (w * h) * 0.02

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        if len(approx) != 4:
            continue

        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = float(bw) / bh if bh > 0 else 0
        if 0.6 < aspect < 1.4:
            cx = x + bw // 2
            cy = y + bh // 2
            candidates.append((cx, cy, area))

    return candidates


def _select_best_four_corners(candidates: list, w: int, h: int) -> Optional[np.ndarray]:
    """
    From a list of candidates, select the 4 closest to the image corners.
    Returns ordered points or None.
    """
    if len(candidates) < 4:
        return None

    candidates.sort(key=lambda c: c[2], reverse=True)

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


def _estimate_fourth_corner(three_corners: list, w: int, h: int) -> Optional[np.ndarray]:
    """
    Given exactly 3 detected corners, estimate the 4th using geometric relationship.
    Returns 4 ordered points or None if geometry is unreliable.
    """
    if len(three_corners) != 3:
        return None

    pts = np.array([c[:2] for c in three_corners], dtype="float32")

    img_corners = np.array([
        [0, 0], [w, 0], [w, h], [0, h]
    ], dtype="float32")

    # Assign each detected point to nearest image corner
    assignments = {}
    used_pts = set()
    for i, ic in enumerate(img_corners):
        best_dist = float("inf")
        best_j = -1
        for j in range(3):
            if j in used_pts:
                continue
            dist = np.sqrt((pts[j][0] - ic[0])**2 + (pts[j][1] - ic[1])**2)
            if dist < best_dist:
                best_dist = dist
                best_j = j
        if best_j >= 0:
            assignments[i] = pts[best_j]
            used_pts.add(best_j)

    if len(assignments) != 3:
        return None

    # Find which corner index (0-3) is missing
    missing_idx = -1
    for i in range(4):
        if i not in assignments:
            missing_idx = i
            break

    if missing_idx == -1:
        return None

    # Estimate the missing corner using parallelogram property
    # For a rectangle: P_missing = P_opposite_diagonal_start + (P_adj1 - P_opp) + (P_adj2 - P_opp)
    # Simpler: missing = adj1 + adj2 - opposite
    opposite_idx = (missing_idx + 2) % 4
    adj1_idx = (missing_idx + 1) % 4
    adj2_idx = (missing_idx + 3) % 4

    if opposite_idx not in assignments or adj1_idx not in assignments or adj2_idx not in assignments:
        return None

    estimated = assignments[adj1_idx] + assignments[adj2_idx] - assignments[opposite_idx]

    all_four = np.zeros((4, 2), dtype="float32")
    for i in range(4):
        if i == missing_idx:
            all_four[i] = estimated
        else:
            all_four[i] = assignments[i]

    return _order_points(all_four)


def _detect_corner_markers(gray: np.ndarray) -> Optional[np.ndarray]:
    """
    Detect the 4 corner alignment markers in the image.
    Uses multiple fallback strategies for robust detection:
      1. Standard Otsu threshold
      2. Dilated binary image
      3. Multiple manual threshold values
      4. 3-corner estimation (if 3 found, estimate 4th)
      5. Largest contour paper boundary approach

    Returns ordered corner points (centers) or None if all strategies fail.
    """
    h, w = gray.shape
    preprocessed = _preprocess_image(gray)

    # Strategy 1: Standard Otsu threshold
    _, binary_otsu = cv2.threshold(preprocessed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    candidates = _find_square_markers(binary_otsu, gray)
    result = _select_best_four_corners(candidates, w, h)
    if result is not None:
        return result

    # Strategy 2: Dilated binary image (helps with thin/broken markers)
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(binary_otsu, kernel, iterations=1)
    candidates = _find_square_markers(dilated, gray)
    result = _select_best_four_corners(candidates, w, h)
    if result is not None:
        return result

    # Strategy 3: Multiple manual threshold values
    all_candidates = []
    for thresh_val in [80, 100, 120, 140]:
        _, binary_manual = cv2.threshold(preprocessed, thresh_val, 255, cv2.THRESH_BINARY_INV)
        candidates = _find_square_markers(binary_manual, gray)
        result = _select_best_four_corners(candidates, w, h)
        if result is not None:
            return result
        all_candidates.extend(candidates)

    # Strategy 4: If we have exactly 3 corners from any attempt, estimate the 4th
    # Combine all candidates from all strategies
    combined = _find_square_markers(binary_otsu, gray) + all_candidates
    # Remove duplicates (close points)
    unique_candidates = []
    for c in combined:
        is_dup = False
        for u in unique_candidates:
            if np.sqrt((c[0] - u[0])**2 + (c[1] - u[1])**2) < 30:
                is_dup = True
                break
        if not is_dup:
            unique_candidates.append(c)

    if len(unique_candidates) >= 3:
        # Sort by area and try top candidates
        unique_candidates.sort(key=lambda c: c[2], reverse=True)
        # Try to select 3 from corners
        img_corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype="float32")
        corner_assigned = []
        used = set()
        for corner in img_corners:
            best_dist = float("inf")
            best_idx = -1
            for i, (cx, cy, _) in enumerate(unique_candidates[:15]):
                if i in used:
                    continue
                dist = np.sqrt((cx - corner[0])**2 + (cy - corner[1])**2)
                # Only accept if reasonably close to the corner
                if dist < max(w, h) * 0.3 and dist < best_dist:
                    best_dist = dist
                    best_idx = i
            if best_idx >= 0:
                used.add(best_idx)
                corner_assigned.append(unique_candidates[best_idx])

        if len(corner_assigned) == 3:
            result = _estimate_fourth_corner(corner_assigned, w, h)
            if result is not None:
                return result

    # Strategy 5: Largest contour approach (find paper boundary)
    _, binary_paper = cv2.threshold(preprocessed, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    # Invert to find white paper on dark background
    binary_inv = cv2.bitwise_not(binary_paper)
    contours, _ = cv2.findContours(binary_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        # Paper should be at least 20% of image area
        if area > (w * h) * 0.2:
            peri = cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
            if len(approx) == 4:
                points = approx.reshape(4, 2).astype("float32")
                return _order_points(points)

    return None


def _create_binary_image(warped_gray: np.ndarray) -> np.ndarray:
    """
    Apply a single adaptive threshold on the entire warped grayscale image.
    This replaces per-bubble Otsu thresholding.
    """
    # Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(warped_gray, (5, 5), 0)

    # Single adaptive threshold for the whole image
    binary = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=51,
        C=10
    )

    return binary


def _get_fill_ratio(binary_image: np.ndarray, cx: int, cy: int, roi_size: int) -> float:
    """
    Count dark pixels in a circular ROI from the pre-thresholded binary image.

    Args:
        binary_image: Pre-thresholded binary image (white=marked, black=empty)
        cx: Center X of bubble
        cy: Center Y of bubble
        roi_size: Radius of the ROI to analyze

    Returns:
        Ratio of dark (marked) pixels within the circular region.
    """
    h, w = binary_image.shape
    x1 = max(0, cx - roi_size)
    y1 = max(0, cy - roi_size)
    x2 = min(w, cx + roi_size)
    y2 = min(h, cy + roi_size)

    roi = binary_image[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    # Create circular mask
    mask = np.zeros_like(roi, dtype=np.uint8)
    center = (roi.shape[1] // 2, roi.shape[0] // 2)
    radius = min(center[0], center[1], roi_size)
    cv2.circle(mask, center, radius, 255, -1)

    # Count dark pixels within the circular mask
    masked = cv2.bitwise_and(roi, mask)
    total_pixels = cv2.countNonZero(mask)
    dark_pixels = cv2.countNonZero(masked)

    return dark_pixels / total_pixels if total_pixels > 0 else 0.0


def _detect_answer_for_question(
    binary_image: np.ndarray,
    bubble_positions: list,
    roi_size: int = ROI_SIZE
) -> Optional[int]:
    """
    Detect the answer for a single question using relative comparison.

    Compares fill ratios of ALL bubbles in one question:
    - If max_ratio < EMPTY_THRESHOLD: nothing marked -> return None
    - If darkest is >= RELATIVE_RATIO_THRESHOLD times second darkest
      AND has ratio > MIN_FILL_RATIO: that is the answer
    - Otherwise: ambiguous -> return -1

    Args:
        binary_image: Pre-thresholded binary image
        bubble_positions: List of (option_index, cx, cy) for this question
        roi_size: Size of ROI around bubble center

    Returns:
        option_index (0-based) if clearly detected,
        None if nothing marked,
        -1 if ambiguous
    """
    ratios = []
    for opt_idx, cx, cy in bubble_positions:
        ratio = _get_fill_ratio(binary_image, cx, cy, roi_size)
        ratios.append((opt_idx, ratio))

    if not ratios:
        return None

    # Sort by fill ratio descending
    sorted_ratios = sorted(ratios, key=lambda x: x[1], reverse=True)
    max_opt, max_ratio = sorted_ratios[0]

    # If max ratio is below empty threshold, nothing is marked
    if max_ratio < EMPTY_THRESHOLD:
        return None

    # If max ratio does not meet minimum fill ratio, treat as empty
    if max_ratio < MIN_FILL_RATIO:
        return None

    # Compare with second darkest
    if len(sorted_ratios) > 1:
        _, second_ratio = sorted_ratios[1]
        # Avoid division by zero
        if second_ratio < 0.001:
            # Second is essentially empty, first is clearly marked
            return max_opt
        if max_ratio >= RELATIVE_RATIO_THRESHOLD * second_ratio:
            return max_opt
        else:
            # Ambiguous - not enough relative difference
            return -1
    else:
        # Only one option (shouldn't happen normally)
        return max_opt


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


def detect_student_number(warped_gray: np.ndarray) -> Optional[int]:
    """
    Detect the student number from the student number bubble section.
    Uses relative comparison within each row (tens and units).

    Args:
        warped_gray: Grayscale perspective-corrected image

    Returns:
        Detected student number (1-50) or None if not detected
    """
    # Create single binary image for the warped sheet
    binary = _create_binary_image(warped_gray)

    section_start_y = STUDENT_NUM_Y + 50
    base_x = 350

    # Row 1: Tens digit (0-4) - use relative comparison
    tens_positions = []
    for i in range(5):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y
        tens_positions.append((i, cx, cy))

    tens_result = _detect_answer_for_question(binary, tens_positions, STUDENT_NUM_ROI_SIZE)

    # Row 2: Units digit (0-9) - use relative comparison
    units_positions = []
    for i in range(10):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y + STUDENT_NUM_SPACING_Y
        units_positions.append((i, cx, cy))

    units_result = _detect_answer_for_question(binary, units_positions, STUDENT_NUM_ROI_SIZE)

    # Handle tens digit
    tens_digit = tens_result if tens_result is not None and tens_result >= 0 else None

    # Handle units digit
    units_digit = units_result if units_result is not None and units_result >= 0 else None

    # Combine digits
    if tens_digit is not None and units_digit is not None:
        number = tens_digit * 10 + units_digit
        if 1 <= number <= 50:
            return number
    elif tens_digit is None and units_digit is not None:
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
            - uncertain_questions: list of question numbers that were ambiguous
            - error: error message if processing failed, else None
    """
    option_letters = "ABCDE"[:num_options]

    result = {
        "answers": [],
        "score": 0,
        "total": num_questions,
        "details": [],
        "student_number": None,
        "uncertain_questions": [],
        "error": None,
    }

    # Load image
    image = cv2.imread(image_path)
    if image is None:
        result["error"] = "Rasmni o'qib bo'lmadi. Iltimos qaytadan yuboring."
        return result

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Detect corner markers with multi-stage fallbacks
    corners = _detect_corner_markers(gray)
    if corners is None:
        result["error"] = (
            "Burchak belgilari topilmadi. Barcha usullar sinab ko'rildi:\n"
            "1) Oddiy aniqlash - muvaffaqiyatsiz\n"
            "2) Kengaytirilgan tasvir - muvaffaqiyatsiz\n"
            "3) Turli chegara qiymatlari (80-140) - muvaffaqiyatsiz\n"
            "4) 3 burchakdan 4-ni hisoblash - muvaffaqiyatsiz\n"
            "5) Varaq chegarasini aniqlash - muvaffaqiyatsiz\n\n"
            "Iltimos qaytadan suratga oling:\n"
            "- Varaqni tekis joyga qo'ying\n"
            "- 4 ta burchak belgilari aniq ko'rinsin\n"
            "- Yaxshi yorug'likda, to'g'ri burchakda suratga oling\n"
            "- Soya tushmasin"
        )
        return result

    # Apply perspective transform
    warped = _perspective_transform(image, corners)
    warped_gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)

    # Create single adaptive threshold binary image for the entire warped sheet
    binary = _create_binary_image(warped_gray)

    # Detect student number if enabled
    if include_student_numbers:
        student_num = detect_student_number(warped_gray)
        result["student_number"] = student_num

    # Calculate grid start Y based on whether student numbers are included
    if include_student_numbers:
        grid_y = STUDENT_NUM_Y + 50 + 2 * STUDENT_NUM_SPACING_Y + 30 + 60
    else:
        grid_y = GRID_START_Y

    # Get bubble positions
    positions = _get_bubble_positions(num_questions, num_options, grid_y)

    # Group positions by question
    question_bubbles = {}
    for q_idx, opt_idx, cx, cy in positions:
        if q_idx not in question_bubbles:
            question_bubbles[q_idx] = []
        question_bubbles[q_idx].append((opt_idx, cx, cy))

    # Detect answers using relative comparison per question
    score = 0
    uncertain_questions = []

    for q_idx in range(num_questions):
        bubbles = question_bubbles.get(q_idx, [])
        detected_opt = _detect_answer_for_question(binary, bubbles)

        if detected_opt is None:
            # No answer detected
            letter = "-"
            detected = None
        elif detected_opt == -1:
            # Ambiguous - uncertain
            letter = "X"
            detected = None
            uncertain_questions.append(q_idx + 1)
        else:
            # Clear answer
            detected = detected_opt
            letter = option_letters[detected] if detected < len(option_letters) else "?"

        correct = correct_answers[q_idx] if q_idx < len(correct_answers) else None
        is_correct = (detected is not None and detected == correct)
        if is_correct:
            score += 1

        correct_letter = option_letters[correct] if correct is not None and correct < len(option_letters) else "?"

        result["answers"].append(letter)
        result["details"].append({
            "question": q_idx + 1,
            "detected": letter,
            "correct": correct_letter,
            "is_correct": is_correct,
        })

    result["score"] = score
    result["uncertain_questions"] = uncertain_questions
    return result
