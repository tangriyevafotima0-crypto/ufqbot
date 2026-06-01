"""
OMR (Optical Mark Recognition) scanner V5 - detects filled bubbles on answer sheets
using OpenCV image processing and perspective correction.

Uses a 3-method consensus voting approach:
  Method A: Relative comparison with baseline subtraction (handles printed letters)
  Method B: Global Otsu threshold with circular mask (handles varying lighting)
  Method C: Morphological opening (removes thin strokes, keeps thick fill)

Two out of three methods must agree for a confident detection.

V5 fix: corrected perspective transform destination coordinates to use marker
inset positions instead of page corners, fixing the 0-score bug.
"""

import cv2
import numpy as np
from collections import Counter
from typing import Optional

from sheet_generator import (
    SHEET_WIDTH, SHEET_HEIGHT, MARKER_SIZE, MARKER_MARGIN,
    GRID_START_Y, BUBBLE_RADIUS, BUBBLE_SPACING_X,
    BUBBLE_SPACING_Y, QUESTION_NUM_WIDTH,
    STUDENT_NUM_Y, STUDENT_NUM_BUBBLE_RADIUS,
    STUDENT_NUM_SPACING_X, STUDENT_NUM_SPACING_Y,
)

# ROI size around each bubble center for analysis
ROI_SIZE = int(BUBBLE_RADIUS * 1.5)

# Student number ROI size
STUDENT_NUM_ROI_SIZE = int(STUDENT_NUM_BUBBLE_RADIUS * 1.5)


def _preprocess_image(gray: np.ndarray) -> np.ndarray:
    """
    Preprocess image for better OMR detection.
    Pipeline: sharpen -> denoise -> CLAHE contrast enhancement.
    """
    # Step 1: Unsharp mask sharpening
    blurred = cv2.GaussianBlur(gray, (9, 9), 10.0)
    sharpened = cv2.addWeighted(gray, 1.5, blurred, -0.5, 0)

    # Step 2: Denoising for noisy phone photos
    denoised = cv2.fastNlMeansDenoising(sharpened, None, h=10, templateWindowSize=7, searchWindowSize=21)

    # Step 3: CLAHE contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(denoised)

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
    # missing = adj1 + adj2 - opposite
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

    # Strategy 1: Standard Otsu threshold
    _, binary_otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
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
        _, binary_manual = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY_INV)
        candidates = _find_square_markers(binary_manual, gray)
        result = _select_best_four_corners(candidates, w, h)
        if result is not None:
            return result
        all_candidates.extend(candidates)

    # Strategy 4: If we have exactly 3 corners from any attempt, estimate the 4th
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
        unique_candidates.sort(key=lambda c: c[2], reverse=True)
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
    _, binary_paper = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    binary_inv = cv2.bitwise_not(binary_paper)
    contours, _ = cv2.findContours(binary_inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if contours:
        largest = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest)
        if area > (w * h) * 0.2:
            peri = cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
            if len(approx) == 4:
                points = approx.reshape(4, 2).astype("float32")
                return _order_points(points)

    return None


def _perspective_transform(image: np.ndarray, corners: np.ndarray) -> np.ndarray:
    """Apply perspective transform to get a flat top-down view.

    IMPORTANT: The detected ``corners`` are the *centers* of the corner
    markers, which sheet_generator draws inset from the page edge by
    ``MARKER_MARGIN + MARKER_SIZE / 2`` pixels. We must map them back to those
    exact inset coordinates (NOT to the page corners 0..W/0..H), so that the
    warped image keeps the SAME coordinate system used by
    ``_get_bubble_positions``. Mapping to the page corners would shift/scale
    every bubble by ~50-70px, far more than ROI_SIZE, causing all bubbles to
    be sampled on blank areas (resulting in a score of 0).
    """
    # Marker center coordinates in the original full-sheet coordinate system.
    inset = MARKER_MARGIN + MARKER_SIZE / 2.0
    left = inset
    top = inset
    right = SHEET_WIDTH - inset
    bottom = SHEET_HEIGHT - inset

    dst = np.array([
        [left, top],       # top-left marker center
        [right, top],      # top-right marker center
        [right, bottom],   # bottom-right marker center
        [left, bottom],    # bottom-left marker center
    ], dtype="float32")

    matrix = cv2.getPerspectiveTransform(corners, dst)
    warped = cv2.warpPerspective(image, matrix, (SHEET_WIDTH, SHEET_HEIGHT))
    return warped


def _get_fill_ratio_rect(binary_image: np.ndarray, cx: int, cy: int, roi_size: int) -> float:
    """
    Get fill ratio from a rectangular ROI in the binary image.
    Used by Method A and Method C.
    """
    h, w = binary_image.shape
    x1 = max(0, cx - roi_size)
    y1 = max(0, cy - roi_size)
    x2 = min(w, cx + roi_size)
    y2 = min(h, cy + roi_size)

    roi = binary_image[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    total_pixels = roi.shape[0] * roi.shape[1]
    dark_pixels = cv2.countNonZero(roi)
    return dark_pixels / total_pixels if total_pixels > 0 else 0.0


def _get_fill_ratio_circular(binary_image: np.ndarray, cx: int, cy: int, roi_size: int) -> float:
    """
    Get fill ratio using a circular mask within the ROI.
    Used by Method B for more accurate bubble measurement.
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


def _method_a_detect(binary_adaptive: np.ndarray, bubble_positions: list, roi_size: int) -> Optional[int]:
    """
    Method A: Relative comparison with baseline subtraction.

    For each question's bubbles:
    1. Get fill ratios from adaptive threshold binary
    2. Calculate MEDIAN fill ratio (= empty bubble baseline from printed letters)
    3. Subtract baseline from all ratios
    4. Adjusted max must be > 0.10 AND > 1.5x adjusted second max

    Returns: option_index or None (nothing detected) or -1 (ambiguous)
    """
    if not bubble_positions:
        return None

    ratios = []
    for opt_idx, cx, cy in bubble_positions:
        ratio = _get_fill_ratio_rect(binary_adaptive, cx, cy, roi_size)
        ratios.append((opt_idx, ratio))

    # Calculate median as baseline (represents empty bubble with printed letters)
    all_ratios = [r for _, r in ratios]
    baseline = np.median(all_ratios)

    # Subtract baseline
    adjusted = [(opt_idx, max(0.0, ratio - baseline)) for opt_idx, ratio in ratios]

    # Sort by adjusted ratio descending
    sorted_adj = sorted(adjusted, key=lambda x: x[1], reverse=True)
    max_opt, max_adj = sorted_adj[0]

    # Must exceed minimum threshold after baseline subtraction
    if max_adj < 0.10:
        return None

    # Compare with second highest
    if len(sorted_adj) > 1:
        _, second_adj = sorted_adj[1]
        if second_adj < 0.001:
            return max_opt
        if max_adj >= 1.5 * second_adj:
            return max_opt
        else:
            return -1  # Ambiguous
    else:
        return max_opt


def _method_b_detect(binary_otsu: np.ndarray, bubble_positions: list, roi_size: int) -> Optional[int]:
    """
    Method B: Global Otsu threshold with circular mask.

    1. Uses Otsu-thresholded image (pre-computed for entire warped image)
    2. For each bubble, count dark pixels in CIRCULAR mask
    3. Normalize by circle area
    4. Fixed threshold: 0.35 (filled) vs ~0.05-0.15 (empty)

    Returns: option_index or None or -1
    """
    if not bubble_positions:
        return None

    ratios = []
    for opt_idx, cx, cy in bubble_positions:
        ratio = _get_fill_ratio_circular(binary_otsu, cx, cy, roi_size)
        ratios.append((opt_idx, ratio))

    # Find bubbles above the fixed threshold
    filled = [(opt_idx, ratio) for opt_idx, ratio in ratios if ratio >= 0.35]

    if len(filled) == 0:
        return None
    elif len(filled) == 1:
        return filled[0][0]
    else:
        # Multiple filled - ambiguous
        return -1


def _method_c_detect(binary_adaptive: np.ndarray, bubble_positions: list, roi_size: int) -> Optional[int]:
    """
    Method C: Morphological approach.

    1. For each bubble ROI from adaptive threshold
    2. Apply morphological OPENING (kernel 5x5) - removes thin letter strokes, keeps thick fill
    3. Count remaining dark pixels
    4. Threshold at 0.20

    Returns: option_index or None or -1
    """
    if not bubble_positions:
        return None

    kernel = np.ones((5, 5), np.uint8)
    h, w = binary_adaptive.shape

    ratios = []
    for opt_idx, cx, cy in bubble_positions:
        x1 = max(0, cx - roi_size)
        y1 = max(0, cy - roi_size)
        x2 = min(w, cx + roi_size)
        y2 = min(h, cy + roi_size)

        roi = binary_adaptive[y1:y2, x1:x2]
        if roi.size == 0:
            ratios.append((opt_idx, 0.0))
            continue

        # Morphological opening removes thin strokes but keeps thick fill
        opened = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)
        total_pixels = roi.shape[0] * roi.shape[1]
        dark_pixels = cv2.countNonZero(opened)
        ratio = dark_pixels / total_pixels if total_pixels > 0 else 0.0
        ratios.append((opt_idx, ratio))

    # Find bubbles above threshold
    filled = [(opt_idx, ratio) for opt_idx, ratio in ratios if ratio >= 0.20]

    if len(filled) == 0:
        return None
    elif len(filled) == 1:
        return filled[0][0]
    else:
        # Multiple filled - ambiguous
        return -1


def _determine_answer(method_a_result: Optional[int], method_b_result: Optional[int], method_c_result: Optional[int]) -> Optional[int]:
    """
    Consensus voting across three detection methods.

    - If 2+ of 3 methods agree on the same option: use that answer
    - If all 3 disagree: return -1 (uncertain)
    - If only 1 method detected something (others None): use it
    """
    results = [method_a_result, method_b_result, method_c_result]
    non_none = [r for r in results if r is not None and r >= 0]

    if len(non_none) >= 2:
        counts = Counter(non_none)
        most_common = counts.most_common(1)[0]
        if most_common[1] >= 2:
            return most_common[0]

    if len(non_none) == 1:
        return non_none[0]

    # Check for ambiguous (-1) results
    if any(r == -1 for r in results):
        return -1

    return None  # Nothing detected by any method


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


def detect_student_number(warped_gray: np.ndarray, binary_adaptive: np.ndarray = None, binary_otsu: np.ndarray = None) -> Optional[int]:
    """
    Detect the student number from the student number bubble section.
    Uses multi-method consensus for each row (tens and units).

    Args:
        warped_gray: Grayscale perspective-corrected image
        binary_adaptive: Pre-computed adaptive threshold binary (optional)
        binary_otsu: Pre-computed Otsu threshold binary (optional)

    Returns:
        Detected student number (1-50) or None if not detected
    """
    # Create binary images only if not provided
    if binary_adaptive is None:
        blurred = cv2.GaussianBlur(warped_gray, (5, 5), 0)
        binary_adaptive = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, blockSize=51, C=10
        )
    if binary_otsu is None:
        _, binary_otsu = cv2.threshold(warped_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    section_start_y = STUDENT_NUM_Y + 50
    base_x = 350

    # Row 1: Tens digit (0-4)
    tens_positions = []
    for i in range(5):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y
        tens_positions.append((i, cx, cy))

    tens_a = _method_a_detect(binary_adaptive, tens_positions, STUDENT_NUM_ROI_SIZE)
    tens_b = _method_b_detect(binary_otsu, tens_positions, STUDENT_NUM_ROI_SIZE)
    tens_c = _method_c_detect(binary_adaptive, tens_positions, STUDENT_NUM_ROI_SIZE)
    tens_result = _determine_answer(tens_a, tens_b, tens_c)

    # Row 2: Units digit (0-9)
    units_positions = []
    for i in range(10):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y + STUDENT_NUM_SPACING_Y
        units_positions.append((i, cx, cy))

    units_a = _method_a_detect(binary_adaptive, units_positions, STUDENT_NUM_ROI_SIZE)
    units_b = _method_b_detect(binary_otsu, units_positions, STUDENT_NUM_ROI_SIZE)
    units_c = _method_c_detect(binary_adaptive, units_positions, STUDENT_NUM_ROI_SIZE)
    units_result = _determine_answer(units_a, units_b, units_c)

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
    Scan an answer sheet image and grade it using 3-method consensus voting.

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

    # Preprocessing: sharpen and denoise
    preprocessed = _preprocess_image(gray)

    # Detect corner markers with auto-rotation fallback
    corners = _detect_corner_markers(preprocessed)

    if corners is None:
        # Auto-rotation: try common orientations (180 most common mistake first)
        for angle in [180, 90, 270]:
            if angle == 90:
                rotated = cv2.rotate(preprocessed, cv2.ROTATE_90_CLOCKWISE)
                rotated_img = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
            elif angle == 180:
                rotated = cv2.rotate(preprocessed, cv2.ROTATE_180)
                rotated_img = cv2.rotate(image, cv2.ROTATE_180)
            else:
                rotated = cv2.rotate(preprocessed, cv2.ROTATE_90_COUNTERCLOCKWISE)
                rotated_img = cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)

            corners = _detect_corner_markers(rotated)
            if corners is not None:
                preprocessed = rotated
                image = rotated_img
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                break

    if corners is None:
        result["error"] = (
            "Burchak belgilari topilmadi. Barcha usullar sinab ko'rildi:\n"
            "1) Oddiy aniqlash - muvaffaqiyatsiz\n"
            "2) Kengaytirilgan tasvir - muvaffaqiyatsiz\n"
            "3) Turli chegara qiymatlari (80-140) - muvaffaqiyatsiz\n"
            "4) 3 burchakdan 4-ni hisoblash - muvaffaqiyatsiz\n"
            "5) Varaq chegarasini aniqlash - muvaffaqiyatsiz\n"
            "6) 90/180/270 daraja aylantirish - muvaffaqiyatsiz\n\n"
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

    # Create BOTH binary images on the warped result
    blurred_warped = cv2.GaussianBlur(warped_gray, (5, 5), 0)
    binary_adaptive = cv2.adaptiveThreshold(
        blurred_warped, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=51, C=10
    )
    _, binary_otsu = cv2.threshold(warped_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Detect student number if enabled
    if include_student_numbers:
        student_num = detect_student_number(warped_gray, binary_adaptive, binary_otsu)
        result["student_number"] = student_num

    # Calculate grid start Y based on whether student numbers are included
    # This offset formula stays in sync with sheet_generator._draw_student_number_section layout
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

    # Detect answers using 3-method consensus voting per question
    score = 0
    uncertain_questions = []

    for q_idx in range(num_questions):
        bubbles = question_bubbles.get(q_idx, [])

        # Run all three methods
        result_a = _method_a_detect(binary_adaptive, bubbles, ROI_SIZE)
        result_b = _method_b_detect(binary_otsu, bubbles, ROI_SIZE)
        result_c = _method_c_detect(binary_adaptive, bubbles, ROI_SIZE)

        # Consensus voting
        detected_opt = _determine_answer(result_a, result_b, result_c)

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

