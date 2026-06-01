"""
Handwritten name reader V6 - attempts to recognize block capital letters
(BOSMA HARFLAR) from the name/surname fields on the answer sheet.

Uses image processing (thresholding, contour detection, character segmentation)
for best-effort OCR of neat handwritten block capitals.
"""

import cv2
import numpy as np
from typing import Optional

from sheet_generator import NAME_FIELD_BOX, SURNAME_FIELD_BOX


# Name field coordinates on the warped (perspective-corrected) sheet
# Derived from sheet_generator box coordinates with a small inset from drawn borders
NAME_BOX = (NAME_FIELD_BOX[0] + 5, NAME_FIELD_BOX[1] + 3, NAME_FIELD_BOX[2] - 5, NAME_FIELD_BOX[3] - 3)
SURNAME_BOX = (SURNAME_FIELD_BOX[0] + 5, SURNAME_FIELD_BOX[1] + 3, SURNAME_FIELD_BOX[2] - 5, SURNAME_FIELD_BOX[3] - 3)


def get_name_region_coords():
    """Return coordinates for name and surname writing areas."""
    return {
        "name": NAME_BOX,
        "surname": SURNAME_BOX,
    }


def _extract_region(gray_image: np.ndarray, box: tuple) -> np.ndarray:
    """Extract a rectangular region from the image."""
    x1, y1, x2, y2 = box
    return gray_image[y1:y2, x1:x2]


def _segment_characters(binary_roi: np.ndarray, min_char_height: int = 15, min_char_width: int = 8) -> list:
    """
    Segment individual characters from a binary image ROI.
    Returns list of (x, y, w, h) bounding boxes sorted left to right.
    """
    contours, _ = cv2.findContours(binary_roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    char_boxes = []
    roi_h, roi_w = binary_roi.shape

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        # Filter by size - block capitals should be reasonable size
        if h < min_char_height or w < min_char_width:
            continue
        # Filter out very large blobs (noise, borders)
        if h > roi_h * 0.95 or w > roi_w * 0.5:
            continue
        # Filter out very small area contours
        if cv2.contourArea(cnt) < 50:
            continue
        char_boxes.append((x, y, w, h))

    # Sort left to right
    char_boxes.sort(key=lambda b: b[0])

    # Merge overlapping boxes (for characters like 'SH' that might have separate strokes)
    merged = []
    for box in char_boxes:
        if merged and box[0] < merged[-1][0] + merged[-1][2] * 0.5:
            # Merge with previous
            prev = merged[-1]
            new_x = min(prev[0], box[0])
            new_y = min(prev[1], box[1])
            new_x2 = max(prev[0] + prev[2], box[0] + box[2])
            new_y2 = max(prev[1] + prev[3], box[1] + box[3])
            merged[-1] = (new_x, new_y, new_x2 - new_x, new_y2 - new_y)
        else:
            merged.append(box)

    return merged


def _recognize_character(char_img: np.ndarray) -> Optional[str]:
    """
    Attempt to recognize a single block capital letter using feature analysis.

    Uses simple geometric features:
    - Aspect ratio
    - Fill density
    - Vertical/horizontal projections
    - Number of contour components (holes)

    This is a best-effort heuristic approach for neat block capitals.
    Returns the recognized letter or None.
    """
    if char_img is None or char_img.size == 0:
        return None

    # Resize to standard size for analysis
    std_size = 32
    try:
        resized = cv2.resize(char_img, (std_size, std_size), interpolation=cv2.INTER_AREA)
    except Exception:
        return None

    h, w = char_img.shape
    aspect_ratio = w / h if h > 0 else 0

    # Fill density (how much of the bounding box is filled)
    total_pixels = resized.shape[0] * resized.shape[1]
    filled_pixels = cv2.countNonZero(resized)
    density = filled_pixels / total_pixels if total_pixels > 0 else 0

    # Horizontal projection (sum of pixels per row)
    h_proj = np.sum(resized, axis=1) / 255.0
    # Vertical projection (sum of pixels per column)
    v_proj = np.sum(resized, axis=0) / 255.0

    # Count internal holes (contours with parent)
    contours, hierarchy = cv2.findContours(resized, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    num_holes = 0
    if hierarchy is not None:
        for i in range(len(contours)):
            # A hole has a parent (hierarchy[0][i][3] != -1)
            if hierarchy[0][i][3] != -1:
                num_holes += 1

    # Top/bottom/middle density
    top_third = np.sum(resized[:std_size // 3, :]) / 255.0
    mid_third = np.sum(resized[std_size // 3:2 * std_size // 3, :]) / 255.0
    bot_third = np.sum(resized[2 * std_size // 3:, :]) / 255.0

    # Left/right density
    left_half = np.sum(resized[:, :std_size // 2]) / 255.0
    right_half = np.sum(resized[:, std_size // 2:]) / 255.0

    # Simple heuristic classification
    # This is intentionally simple and best-effort

    # Letters with holes
    if num_holes >= 2:
        # B, 8-like shapes
        if aspect_ratio < 0.8:
            return 'B'

    if num_holes == 1:
        if density > 0.35:
            if top_third > bot_third * 1.2:
                return 'D'
            elif bot_third > top_third * 1.2:
                return 'Q'
            elif aspect_ratio > 0.85:
                return 'O'
            else:
                # Could be A, D, O, P, Q, R, or 0
                if mid_third > top_third and mid_third > bot_third:
                    return 'A'
                else:
                    return 'O'

    # Letters without holes - use projections and density
    if density < 0.15:
        # Very sparse - likely I or L
        if aspect_ratio < 0.4:
            return 'I'
        else:
            return 'L'

    if density > 0.45:
        # Very dense
        if aspect_ratio > 1.0:
            return 'M'
        elif num_holes == 0 and bot_third > top_third:
            return 'N'

    # Check for T shape (top heavy, center column)
    top_row_density = np.sum(resized[:std_size // 4, :]) / 255.0
    if top_row_density > bot_third * 2 and v_proj[std_size // 2] > v_proj.mean() * 1.5:
        return 'T'

    # Check for L shape (left column + bottom row)
    if left_half > right_half * 2 and bot_third > top_third * 1.5:
        return 'L'

    # Check for wide letters
    if aspect_ratio > 1.0:
        if density > 0.3:
            return 'M'
        else:
            return 'W'

    # Narrow tall letters
    if aspect_ratio < 0.5:
        if density > 0.3:
            return 'I'
        else:
            return 'J'

    # V shape (top wide, bottom narrow)
    top_width = np.count_nonzero(resized[2, :])
    bot_width = np.count_nonzero(resized[-3, :])
    if top_width > bot_width * 2 and density < 0.35:
        return 'V'

    # Default - return None for unrecognized
    return None


def read_name_from_image(warped_gray: np.ndarray, region: str = "name") -> Optional[str]:
    """
    Attempt to read handwritten block capital letters from the name/surname field.

    Args:
        warped_gray: Grayscale perspective-corrected image (2480x3508 pixels)
        region: "name" for ISM field, "surname" for FAMILIYA field

    Returns:
        Detected name string, or None if unreadable/empty
    """
    if warped_gray is None or warped_gray.size == 0:
        return None

    # Verify image dimensions are reasonable
    h, w = warped_gray.shape[:2]
    if h < 500 or w < 500:
        return None

    # Select the appropriate region
    coords = get_name_region_coords()
    box = coords.get(region, coords["name"])

    # Check bounds
    x1, y1, x2, y2 = box
    if y2 > h or x2 > w:
        return None

    # Extract the region
    roi = _extract_region(warped_gray, box)
    if roi.size == 0:
        return None

    # Preprocess: blur slightly and apply adaptive threshold
    blurred = cv2.GaussianBlur(roi, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=21, C=10
    )

    # Remove thin noise with morphological opening
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # Segment characters
    char_boxes = _segment_characters(binary)

    # Need at least 2 characters for a valid name
    if len(char_boxes) < 2:
        return None

    # Limit to reasonable name length
    if len(char_boxes) > 20:
        char_boxes = char_boxes[:20]

    # Recognize each character
    recognized = []
    for (x, y, w_c, h_c) in char_boxes:
        char_roi = binary[y:y + h_c, x:x + w_c]
        letter = _recognize_character(char_roi)
        if letter:
            recognized.append(letter)
        else:
            recognized.append('?')

    # Build result string
    if not recognized or all(c == '?' for c in recognized):
        return None

    result = ''.join(recognized)

    # If more than 40% are unrecognized, consider it failed
    unknown_count = result.count('?')
    if unknown_count > len(result) * 0.4:
        return None

    # Filter out '?' characters for clean output
    result = result.replace('?', '')

    if not result:
        return None

    return result
