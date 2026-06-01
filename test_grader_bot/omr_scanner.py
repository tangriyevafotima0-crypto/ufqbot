"""
OMR (Optical Mark Recognition) scanner - detects filled bubbles on answer sheets
using ArUco marker detection for alignment and 3-method consensus voting for
bubble fill detection.

Uses cv2.aruco.ArucoDetector with DICT_4X4_50 for robust corner detection.
If ArUco markers are not found, attempts to decode the QR code on the sheet
to provide a more helpful diagnostic error message.

Bubble detection uses a 3-method consensus voting approach:
  Method A: Relative comparison with baseline subtraction (handles printed letters)
  Method B: Global Otsu threshold with circular mask (handles varying lighting)
  Method C: Morphological opening (removes thin strokes, keeps thick fill)

Two out of three methods must agree for a confident detection.
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

# Known marker center positions on the generated sheet
_MARKER_CENTERS = {
    0: (MARKER_MARGIN + MARKER_SIZE / 2, MARKER_MARGIN + MARKER_SIZE / 2),
    1: (SHEET_WIDTH - MARKER_MARGIN - MARKER_SIZE / 2, MARKER_MARGIN + MARKER_SIZE / 2),
    2: (SHEET_WIDTH - MARKER_MARGIN - MARKER_SIZE / 2, SHEET_HEIGHT - MARKER_MARGIN - MARKER_SIZE / 2),
    3: (MARKER_MARGIN + MARKER_SIZE / 2, SHEET_HEIGHT - MARKER_MARGIN - MARKER_SIZE / 2),
}


def _detect_aruco_markers(gray: np.ndarray) -> dict:
    """
    Detect ArUco markers (DICT_4X4_50, IDs 0-3) in the grayscale image.
    Returns dict mapping marker_id -> center point (x, y).
    """
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    params = cv2.aruco.DetectorParameters()
    detector = cv2.aruco.ArucoDetector(aruco_dict, params)

    corners, ids, _ = detector.detectMarkers(gray)

    detected = {}
    if ids is not None:
        for i, marker_id in enumerate(ids.flatten()):
            if marker_id in (0, 1, 2, 3):
                marker_corners = corners[i][0]
                cx = np.mean(marker_corners[:, 0])
                cy = np.mean(marker_corners[:, 1])
                detected[int(marker_id)] = (cx, cy)

    return detected


def _estimate_fourth_corner(detected: dict) -> Optional[dict]:
    """
    Given exactly 3 detected ArUco markers, estimate the 4th using
    parallelogram geometry.
    """
    if len(detected) != 3:
        return None

    missing_id = None
    for i in range(4):
        if i not in detected:
            missing_id = i
            break

    if missing_id is None:
        return None

    opposite_id = (missing_id + 2) % 4
    adj1_id = (missing_id + 1) % 4
    adj2_id = (missing_id + 3) % 4

    if opposite_id not in detected or adj1_id not in detected or adj2_id not in detected:
        return None

    opp = np.array(detected[opposite_id])
    a1 = np.array(detected[adj1_id])
    a2 = np.array(detected[adj2_id])

    estimated = a1 + a2 - opp

    result = dict(detected)
    result[missing_id] = (float(estimated[0]), float(estimated[1]))
    return result


def _try_qr_decode(gray: np.ndarray) -> Optional[str]:
    """
    Try to decode the QR code on the sheet to extract metadata.
    Returns the decoded string data if successful, None otherwise.
    Used as a diagnostic tool when ArUco markers cannot be found.
    """
    try:
        qr_detector = cv2.QRCodeDetector()
        data, points, _ = qr_detector.detectAndDecode(gray)
        if data:
            return data
    except Exception:
        pass
    return None


def _get_perspective_corners(detected_markers: dict) -> Optional[tuple]:
    """
    Build source and destination point arrays for perspective transform.
    Returns (src_points, dst_points) or None.
    """
    if len(detected_markers) < 3:
        return None

    if len(detected_markers) == 3:
        detected_markers = _estimate_fourth_corner(detected_markers)
        if detected_markers is None:
            return None

    src = np.array([
        detected_markers[0],
        detected_markers[1],
        detected_markers[2],
        detected_markers[3],
    ], dtype=np.float32)

    dst = np.array([
        _MARKER_CENTERS[0],
        _MARKER_CENTERS[1],
        _MARKER_CENTERS[2],
        _MARKER_CENTERS[3],
    ], dtype=np.float32)

    return src, dst


def _detect_markers_with_rotation(gray: np.ndarray) -> Optional[tuple]:
    """
    Attempt ArUco detection with auto-rotation fallback.
    Returns (src_points, dst_points, rotated_gray, rotation_angle) or None.

    If ArUco detection fails in all orientations, attempts QR code decoding
    to provide better diagnostics (the QR metadata is stored on the instance
    attribute _last_qr_metadata for the caller to use in error messages).
    """
    detected = _detect_aruco_markers(gray)
    if len(detected) >= 3:
        result = _get_perspective_corners(detected)
        if result is not None:
            return result[0], result[1], gray, 0

    rotations = [
        (180, cv2.ROTATE_180),
        (90, cv2.ROTATE_90_CLOCKWISE),
        (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
    ]

    for angle, rotate_code in rotations:
        rotated = cv2.rotate(gray, rotate_code)
        detected = _detect_aruco_markers(rotated)
        if len(detected) >= 3:
            result = _get_perspective_corners(detected)
            if result is not None:
                return result[0], result[1], rotated, angle

    # All ArUco detection attempts failed.
    # Try QR code decoding for diagnostics - store result for caller.
    qr_data = _try_qr_decode(gray)
    if qr_data is None:
        # Also try rotated versions for QR
        for _, rotate_code in rotations:
            rotated = cv2.rotate(gray, rotate_code)
            qr_data = _try_qr_decode(rotated)
            if qr_data is not None:
                break

    _detect_markers_with_rotation._last_qr_data = qr_data
    return None


def _perspective_transform(gray: np.ndarray, src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Apply perspective transform to get a flat top-down view."""
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(gray, matrix, (SHEET_WIDTH, SHEET_HEIGHT))
    return warped



def _get_fill_ratio_rect(binary_image: np.ndarray, cx: int, cy: int, roi_size: int) -> float:
    """Get fill ratio from a rectangular ROI in the binary image."""
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
    """Get fill ratio using a circular mask within the ROI."""
    h, w = binary_image.shape
    x1 = max(0, cx - roi_size)
    y1 = max(0, cy - roi_size)
    x2 = min(w, cx + roi_size)
    y2 = min(h, cy + roi_size)

    roi = binary_image[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0

    mask = np.zeros_like(roi, dtype=np.uint8)
    center = (roi.shape[1] // 2, roi.shape[0] // 2)
    radius = min(center[0], center[1], roi_size)
    cv2.circle(mask, center, radius, 255, -1)

    masked = cv2.bitwise_and(roi, mask)
    total_pixels = cv2.countNonZero(mask)
    dark_pixels = cv2.countNonZero(masked)

    return dark_pixels / total_pixels if total_pixels > 0 else 0.0


def _method_a_detect(binary_adaptive: np.ndarray, bubble_positions: list, roi_size: int) -> Optional[int]:
    """
    Method A: Relative comparison with baseline subtraction.
    Returns: option_index or None or -1 (ambiguous)
    """
    if not bubble_positions:
        return None

    ratios = []
    for opt_idx, cx, cy in bubble_positions:
        ratio = _get_fill_ratio_rect(binary_adaptive, cx, cy, roi_size)
        ratios.append((opt_idx, ratio))

    all_ratios = [r for _, r in ratios]
    baseline = np.median(all_ratios)

    adjusted = [(opt_idx, max(0.0, ratio - baseline)) for opt_idx, ratio in ratios]

    sorted_adj = sorted(adjusted, key=lambda x: x[1], reverse=True)
    max_opt, max_adj = sorted_adj[0]

    if max_adj < 0.10:
        return None

    if len(sorted_adj) > 1:
        _, second_adj = sorted_adj[1]
        if second_adj < 0.001:
            return max_opt
        if max_adj >= 1.5 * second_adj:
            return max_opt
        else:
            return -1
    else:
        return max_opt


def _method_b_detect(binary_otsu: np.ndarray, bubble_positions: list, roi_size: int) -> Optional[int]:
    """
    Method B: Global Otsu threshold with circular mask.
    Returns: option_index or None or -1
    """
    if not bubble_positions:
        return None

    ratios = []
    for opt_idx, cx, cy in bubble_positions:
        ratio = _get_fill_ratio_circular(binary_otsu, cx, cy, roi_size)
        ratios.append((opt_idx, ratio))

    filled = [(opt_idx, ratio) for opt_idx, ratio in ratios if ratio >= 0.35]

    if len(filled) == 0:
        return None
    elif len(filled) == 1:
        return filled[0][0]
    else:
        return -1


def _method_c_detect(binary_adaptive: np.ndarray, bubble_positions: list, roi_size: int) -> Optional[int]:
    """
    Method C: Morphological approach.
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

        opened = cv2.morphologyEx(roi, cv2.MORPH_OPEN, kernel)
        total_pixels = roi.shape[0] * roi.shape[1]
        dark_pixels = cv2.countNonZero(opened)
        ratio = dark_pixels / total_pixels if total_pixels > 0 else 0.0
        ratios.append((opt_idx, ratio))

    filled = [(opt_idx, ratio) for opt_idx, ratio in ratios if ratio >= 0.20]

    if len(filled) == 0:
        return None
    elif len(filled) == 1:
        return filled[0][0]
    else:
        return -1



def _determine_answer(method_a_result: Optional[int], method_b_result: Optional[int], method_c_result: Optional[int]) -> Optional[int]:
    """Consensus voting across three detection methods."""
    results = [method_a_result, method_b_result, method_c_result]
    non_none = [r for r in results if r is not None and r >= 0]

    if len(non_none) >= 2:
        counts = Counter(non_none)
        most_common = counts.most_common(1)[0]
        if most_common[1] >= 2:
            return most_common[0]

    if len(non_none) == 1:
        return non_none[0]

    if any(r == -1 for r in results):
        return -1

    return None


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
    """Detect the student number from the student number bubble section."""
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

    tens_positions = []
    for i in range(5):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y
        tens_positions.append((i, cx, cy))

    tens_a = _method_a_detect(binary_adaptive, tens_positions, STUDENT_NUM_ROI_SIZE)
    tens_b = _method_b_detect(binary_otsu, tens_positions, STUDENT_NUM_ROI_SIZE)
    tens_c = _method_c_detect(binary_adaptive, tens_positions, STUDENT_NUM_ROI_SIZE)
    tens_result = _determine_answer(tens_a, tens_b, tens_c)

    units_positions = []
    for i in range(10):
        cx = base_x + i * STUDENT_NUM_SPACING_X
        cy = section_start_y + STUDENT_NUM_SPACING_Y
        units_positions.append((i, cx, cy))

    units_a = _method_a_detect(binary_adaptive, units_positions, STUDENT_NUM_ROI_SIZE)
    units_b = _method_b_detect(binary_otsu, units_positions, STUDENT_NUM_ROI_SIZE)
    units_c = _method_c_detect(binary_adaptive, units_positions, STUDENT_NUM_ROI_SIZE)
    units_result = _determine_answer(units_a, units_b, units_c)

    tens_digit = tens_result if tens_result is not None and tens_result >= 0 else None
    units_digit = units_result if units_result is not None and units_result >= 0 else None

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
    Scan an answer sheet image and grade it using ArUco marker detection
    for alignment and 3-method consensus voting for bubble detection.

    Args:
        image_path: Path to the photo of the filled answer sheet
        num_questions: Number of questions on the sheet
        num_options: Number of options per question (2-5)
        correct_answers: List of correct answer indices (0-based)
        include_student_numbers: Whether to detect student number bubbles

    Returns:
        dict with keys:
            - answers: list of detected answers (letter or - for no mark, X for multiple)
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

    image = cv2.imread(image_path)
    if image is None:
        result["error"] = "Rasmni o\'qib bo\'lmadi. Iltimos qaytadan yuboring."
        return result

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    detection = _detect_markers_with_rotation(gray)

    if detection is None:
        # Check if QR code was readable even though markers weren't found
        qr_data = getattr(_detect_markers_with_rotation, '_last_qr_data', None)
        if qr_data:
            result["error"] = (
                "ArUco belgilari topilmadi, lekin QR kod o\'qildi.\n"
                "Varaq aniqlandi (QR ma\'lumot: " + qr_data + "), "
                "ammo burchak markerlari ko\'rinmayapti.\n\n"
                "Iltimos qaytadan suratga oling:\n"
                "- 4 ta burchak belgilari aniq ko\'rinsin\n"
                "- Burchaklarni barmog\'ingiz bilan yopib qo\'ymang\n"
                "- Varaqni tekis joyga qo\'ying\n"
                "- Yaxshi yorug\'likda suratga oling"
            )
        else:
            result["error"] = (
                "ArUco belgilari topilmadi. Barcha usullar sinab ko\'rildi:\n"
                "1) ArUco markerlari aniqlash - muvaffaqiyatsiz\n"
                "2) 3 markerdan 4-ni hisoblash - muvaffaqiyatsiz\n"
                "3) QR kod orqali aniqlash - muvaffaqiyatsiz\n"
                "4) 90/180/270 daraja aylantirish - muvaffaqiyatsiz\n\n"
                "Iltimos qaytadan suratga oling:\n"
                "- Varaqni tekis joyga qo\'ying\n"
                "- 4 ta burchak belgilari aniq ko\'rinsin\n"
                "- Yaxshi yorug\'likda, to\'g\'ri burchakda suratga oling\n"
                "- Soya tushmasin"
            )
        return result

    src_pts, dst_pts, oriented_gray, rotation_angle = detection

    warped_gray = _perspective_transform(oriented_gray, src_pts, dst_pts)

    blurred_warped = cv2.GaussianBlur(warped_gray, (5, 5), 0)
    binary_adaptive = cv2.adaptiveThreshold(
        blurred_warped, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=51, C=10
    )
    _, binary_otsu = cv2.threshold(warped_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    if include_student_numbers:
        student_num = detect_student_number(warped_gray, binary_adaptive, binary_otsu)
        result["student_number"] = student_num

    if include_student_numbers:
        grid_y = STUDENT_NUM_Y + 50 + 2 * STUDENT_NUM_SPACING_Y + 30 + 60
    else:
        grid_y = GRID_START_Y

    positions = _get_bubble_positions(num_questions, num_options, grid_y)

    question_bubbles = {}
    for q_idx, opt_idx, cx, cy in positions:
        if q_idx not in question_bubbles:
            question_bubbles[q_idx] = []
        question_bubbles[q_idx].append((opt_idx, cx, cy))

    score = 0
    uncertain_questions = []

    for q_idx in range(num_questions):
        bubbles = question_bubbles.get(q_idx, [])

        result_a = _method_a_detect(binary_adaptive, bubbles, ROI_SIZE)
        result_b = _method_b_detect(binary_otsu, bubbles, ROI_SIZE)
        result_c = _method_c_detect(binary_adaptive, bubbles, ROI_SIZE)

        detected_opt = _determine_answer(result_a, result_b, result_c)

        if detected_opt is None:
            letter = "-"
            detected = None
        elif detected_opt == -1:
            letter = "X"
            detected = None
            uncertain_questions.append(q_idx + 1)
        else:
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



if __name__ == "__main__":
    """Self-test: generate a sheet, fill in specific bubbles, scan, and verify."""
    import os
    import tempfile
    from sheet_generator import generate_answer_sheet

    print("=" * 60)
    print("OMR Scanner Self-Test (ArUco-based)")
    print("=" * 60)

    NUM_Q = 10
    NUM_OPT = 4

    # Known answers to fill in (0-based option indices)
    expected_answers = [0, 1, 2, 3, 0, 1, 2, 3, 0, 1]

    # Step 1: Generate sheet
    print("\n[1] Generating answer sheet...")
    sheet = generate_answer_sheet(NUM_Q, NUM_OPT, include_student_numbers=True)
    print(f"    Sheet size: {sheet.size}")

    # Step 2: Fill in bubbles programmatically
    print("[2] Filling in bubbles...")
    from PIL import ImageDraw as PilDraw
    draw = PilDraw.Draw(sheet)

    # Calculate grid_y same as scanner does
    grid_y = STUDENT_NUM_Y + 50 + 2 * STUDENT_NUM_SPACING_Y + 30 + 60

    col1_x = 200
    col1_count = NUM_Q  # <= 20, single column

    for q_idx, opt_idx in enumerate(expected_answers):
        base_x = col1_x + QUESTION_NUM_WIDTH
        row = q_idx
        cy = grid_y + row * BUBBLE_SPACING_Y
        cx = base_x + opt_idx * BUBBLE_SPACING_X

        # Fill the bubble solid black
        r = BUBBLE_RADIUS
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill="black")

    # Also fill student number: mark student 12 (tens=1, units=2)
    section_start_y = STUDENT_NUM_Y + 50
    base_x_sn = 350
    # Tens digit = 1
    tens_cx = base_x_sn + 1 * STUDENT_NUM_SPACING_X
    tens_cy = section_start_y
    r_sn = STUDENT_NUM_BUBBLE_RADIUS
    draw.ellipse([tens_cx - r_sn, tens_cy - r_sn, tens_cx + r_sn, tens_cy + r_sn], fill="black")
    # Units digit = 2
    units_cx = base_x_sn + 2 * STUDENT_NUM_SPACING_X
    units_cy = section_start_y + STUDENT_NUM_SPACING_Y
    draw.ellipse([units_cx - r_sn, units_cy - r_sn, units_cx + r_sn, units_cy + r_sn], fill="black")

    # Step 3: Save the filled sheet
    tmp_path = os.path.join(tempfile.gettempdir(), "omr_selftest_filled.png")
    sheet.save(tmp_path)
    print(f"    Saved filled sheet to: {tmp_path}")

    # Step 4: Scan it
    print("[3] Scanning filled sheet...")
    result = scan_answer_sheet(
        image_path=tmp_path,
        num_questions=NUM_Q,
        num_options=NUM_OPT,
        correct_answers=expected_answers,
        include_student_numbers=True,
    )

    # Step 5: Check results
    print("\n[4] Results:")
    if result["error"]:
        print(f"    ERROR: {result['error']}")
    else:
        option_letters = "ABCD"
        expected_letters = [option_letters[i] for i in expected_answers]
        print(f"    Score: {result['score']}/{result['total']}")
        print(f"    Student number: {result['student_number']}")
        print(f"    Expected answers: {expected_letters}")
        print(f"    Detected answers: {result['answers']}")
        print(f"    Uncertain: {result['uncertain_questions']}")

        # Assertions
        all_correct = True
        for i, (exp, det) in enumerate(zip(expected_letters, result["answers"])):
            if exp != det:
                print(f"    MISMATCH Q{i+1}: expected {exp}, got {det}")
                all_correct = False

        if result["student_number"] != 12:
            print(f"    MISMATCH student number: expected 12, got {result['student_number']}")
            all_correct = False

        if all_correct and result["score"] == NUM_Q:
            print("\n    === ALL TESTS PASSED ===")
        else:
            print(f"\n    === SOME TESTS FAILED (score: {result['score']}/{NUM_Q}) ===")

    # Cleanup
    os.remove(tmp_path)
    print("\n[5] Cleaned up temp files.")
    print("=" * 60)
