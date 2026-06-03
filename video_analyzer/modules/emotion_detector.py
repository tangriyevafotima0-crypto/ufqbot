"""Emotion detection module using DeepFace."""

import numpy as np


class EmotionDetector:
    """Detects emotions in face regions using DeepFace."""

    EMOTIONS = ["happy", "angry", "sad", "neutral", "surprise", "fear", "disgust"]

    def __init__(self):
        # Lazy import to avoid loading heavy model at init
        self._deepface = None

    def _get_deepface(self):
        if self._deepface is None:
            print(
                "INFO: Loading DeepFace emotion model. "
                "First run may download model files (~100MB)..."
            )
            try:
                from deepface import DeepFace
                self._deepface = DeepFace
            except ImportError as e:
                raise RuntimeError(
                    "DeepFace is not installed. Install it with: "
                    "pip install deepface"
                ) from e
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load DeepFace: {e}. "
                    "Check your internet connection for model download "
                    "or verify the installation with: pip install deepface"
                ) from e
        return self._deepface

    def analyze_frame(self, frame, face_bboxes=None):
        """Detect emotions in a frame.

        Args:
            frame: BGR image (numpy array)
            face_bboxes: list of face bounding boxes from face_detector
                         Each bbox is dict with x, y, w, h (normalized 0-1)

        Returns:
            dict with keys:
                - emotions: list of dicts per face with emotion labels and scores
                - dominant_emotion: most common emotion across all faces
        """
        if face_bboxes is None or len(face_bboxes) == 0:
            return {"emotions": [], "dominant_emotion": None}

        h, w, _ = frame.shape
        DeepFace = self._get_deepface()
        emotions_list = []

        for bbox in face_bboxes:
            # Convert normalized coords to pixel coords
            x = int(bbox["x"] * w)
            y = int(bbox["y"] * h)
            bw = int(bbox["w"] * w)
            bh = int(bbox["h"] * h)

            # Add padding
            pad = 20
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w, x + bw + pad)
            y2 = min(h, y + bh + pad)

            face_crop = frame[y1:y2, x1:x2]

            if face_crop.size == 0:
                continue

            try:
                result = DeepFace.analyze(
                    face_crop,
                    actions=["emotion"],
                    enforce_detection=False,
                    silent=True,
                )
                if isinstance(result, list):
                    result = result[0]

                emotion_scores = result.get("emotion", {})
                dominant = result.get("dominant_emotion", "neutral")

                emotions_list.append({
                    "scores": emotion_scores,
                    "dominant": dominant,
                })
            except Exception:
                emotions_list.append({
                    "scores": {},
                    "dominant": "unknown",
                })

        # Get overall dominant emotion
        dominant_emotion = None
        if emotions_list:
            dominant_counts = {}
            for e in emotions_list:
                d = e["dominant"]
                dominant_counts[d] = dominant_counts.get(d, 0) + 1
            dominant_emotion = max(dominant_counts, key=dominant_counts.get)

        return {
            "emotions": emotions_list,
            "dominant_emotion": dominant_emotion,
        }

    def close(self):
        """Release resources."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
