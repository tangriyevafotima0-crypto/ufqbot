"""Emotion detection module using MediaPipe face mesh landmarks."""

import numpy as np


class EmotionDetector:
    """Detects emotions using geometric analysis of face mesh landmarks.

    Uses ratios and distances between facial landmarks to classify
    emotions without requiring any additional ML dependencies.
    """

    EMOTIONS = ["happy", "angry", "sad", "neutral", "surprise", "fear", "disgust"]

    # Landmark indices
    _MOUTH_LEFT = 61
    _MOUTH_RIGHT = 291
    _UPPER_LIP = 13
    _LOWER_LIP = 14
    _LEFT_EYE_UPPER = 159
    _LEFT_EYE_LOWER = 145
    _RIGHT_EYE_UPPER = 386
    _RIGHT_EYE_LOWER = 374
    _LEFT_BROW_INNER = 70
    _RIGHT_BROW_INNER = 300
    _LEFT_BROW_MID = 105
    _RIGHT_BROW_MID = 334

    # Default thresholds (can be overridden via config)
    SMILE_THRESHOLD = 0.28
    SURPRISE_MOUTH_THRESHOLD = 0.06
    SURPRISE_EYE_THRESHOLD = 0.30
    SAD_THRESHOLD = 0.015
    ANGRY_BROW_THRESHOLD = 0.018

    def __init__(self, config=None):
        """Initialize emotion detector.

        Args:
            config: optional Config instance with emotion thresholds
        """
        if config is not None:
            self.SMILE_THRESHOLD = getattr(config, 'SMILE_THRESHOLD', self.SMILE_THRESHOLD)
            self.SURPRISE_MOUTH_THRESHOLD = getattr(config, 'SURPRISE_MOUTH_THRESHOLD', self.SURPRISE_MOUTH_THRESHOLD)
            self.SURPRISE_EYE_THRESHOLD = getattr(config, 'SURPRISE_EYE_THRESHOLD', self.SURPRISE_EYE_THRESHOLD)
            self.SAD_THRESHOLD = getattr(config, 'SAD_THRESHOLD', self.SAD_THRESHOLD)
            self.ANGRY_BROW_THRESHOLD = getattr(config, 'ANGRY_BROW_THRESHOLD', self.ANGRY_BROW_THRESHOLD)

    def _get_landmark(self, landmarks, idx):
        """Get (x, y) coordinates from a landmark by index."""
        lm = landmarks[idx]
        return np.array([lm.x, lm.y])

    def _compute_distance(self, p1, p2):
        """Compute Euclidean distance between two points."""
        return np.linalg.norm(p1 - p2)

    def _analyze_landmarks(self, landmarks):
        """Analyze facial landmarks to determine emotion scores.

        Args:
            landmarks: list of landmarks with .x, .y, .z attributes

        Returns:
            dict with emotion scores and dominant emotion
        """
        # Mouth measurements
        mouth_left = self._get_landmark(landmarks, self._MOUTH_LEFT)
        mouth_right = self._get_landmark(landmarks, self._MOUTH_RIGHT)
        upper_lip = self._get_landmark(landmarks, self._UPPER_LIP)
        lower_lip = self._get_landmark(landmarks, self._LOWER_LIP)

        mouth_width = self._compute_distance(mouth_left, mouth_right)
        mouth_height = self._compute_distance(upper_lip, lower_lip)
        mouth_center_y = (upper_lip[1] + lower_lip[1]) / 2.0
        mouth_corner_avg_y = (mouth_left[1] + mouth_right[1]) / 2.0

        # Eye measurements
        left_eye_upper = self._get_landmark(landmarks, self._LEFT_EYE_UPPER)
        left_eye_lower = self._get_landmark(landmarks, self._LEFT_EYE_LOWER)
        right_eye_upper = self._get_landmark(landmarks, self._RIGHT_EYE_UPPER)
        right_eye_lower = self._get_landmark(landmarks, self._RIGHT_EYE_LOWER)

        left_eye_openness = self._compute_distance(left_eye_upper, left_eye_lower)
        right_eye_openness = self._compute_distance(right_eye_upper, right_eye_lower)
        avg_eye_openness = (left_eye_openness + right_eye_openness) / 2.0

        # Eyebrow measurements
        left_brow_inner = self._get_landmark(landmarks, self._LEFT_BROW_INNER)
        right_brow_inner = self._get_landmark(landmarks, self._RIGHT_BROW_INNER)
        left_brow_mid = self._get_landmark(landmarks, self._LEFT_BROW_MID)
        right_brow_mid = self._get_landmark(landmarks, self._RIGHT_BROW_MID)

        # Distance from brow to eye (lower = angrier)
        left_brow_eye_dist = left_brow_mid[1] - left_eye_upper[1]
        right_brow_eye_dist = right_brow_mid[1] - right_eye_upper[1]
        avg_brow_eye_dist = (left_brow_eye_dist + right_brow_eye_dist) / 2.0

        # Mouth aspect ratio (height / width)
        mouth_ratio = mouth_height / mouth_width if mouth_width > 0 else 0

        # Smile detection: corners above center line (in image coords, y increases downward)
        # When smiling, corners go up (lower y) relative to mouth center
        smile_indicator = mouth_center_y - mouth_corner_avg_y

        # Compute emotion scores
        scores = {
            "happy": 0.0,
            "surprise": 0.0,
            "sad": 0.0,
            "angry": 0.0,
            "neutral": 0.0,
            "fear": 0.0,
            "disgust": 0.0,
        }

        # Happy: mouth corners raised relative to center
        if smile_indicator > self.SMILE_THRESHOLD * mouth_width:
            scores["happy"] = min(1.0, smile_indicator / (mouth_width * 0.5))
        elif mouth_ratio > self.SMILE_THRESHOLD:
            # Wide mouth with raised corners
            scores["happy"] = min(1.0, mouth_ratio / 0.5)

        # Surprise: mouth open wide + eyes wide open
        if mouth_height > self.SURPRISE_MOUTH_THRESHOLD and avg_eye_openness > self.SURPRISE_EYE_THRESHOLD * mouth_width:
            mouth_score = min(1.0, mouth_height / 0.1)
            eye_score = min(1.0, avg_eye_openness / (mouth_width * 0.5))
            scores["surprise"] = (mouth_score + eye_score) / 2.0

        # Sad: mouth corners below center (in image coords, corners have higher y)
        sad_indicator = mouth_corner_avg_y - mouth_center_y
        if sad_indicator > self.SAD_THRESHOLD:
            scores["sad"] = min(1.0, sad_indicator / 0.04)

        # Angry: eyebrows lowered toward eyes (brow-eye distance more negative/smaller)
        # In normalized coords, brow above eye means brow y < eye y, so distance is negative
        if avg_brow_eye_dist > -self.ANGRY_BROW_THRESHOLD:
            scores["angry"] = min(1.0, (avg_brow_eye_dist + self.ANGRY_BROW_THRESHOLD) / 0.02)

        # Neutral: when no strong indicators
        max_emotion_score = max(scores["happy"], scores["surprise"], scores["sad"], scores["angry"])
        if max_emotion_score < 0.3:
            scores["neutral"] = 1.0 - max_emotion_score
        else:
            scores["neutral"] = max(0.0, 0.3 - max_emotion_score * 0.5)

        # Fear: similar to surprise but with brow lowering
        if scores["surprise"] > 0.3 and avg_brow_eye_dist > -self.ANGRY_BROW_THRESHOLD:
            scores["fear"] = scores["surprise"] * 0.5

        # Normalize scores to sum to 1
        total = sum(scores.values())
        if total > 0:
            scores = {k: v / total for k, v in scores.items()}

        # Determine dominant emotion
        dominant = max(scores, key=scores.get)

        return {"scores": scores, "dominant": dominant}

    def analyze_frame(self, face_mesh_landmarks=None):
        """Detect emotions from face mesh landmarks.

        Args:
            face_mesh_landmarks: list of landmarks from shared FaceMesh
                                 (protobuf landmark list with .x, .y, .z)

        Returns:
            dict with keys:
                - emotions: list of dicts per face with emotion labels and scores
                - dominant_emotion: dominant emotion string or None
        """
        if face_mesh_landmarks is None:
            return {"emotions": [], "dominant_emotion": None}

        try:
            result = self._analyze_landmarks(face_mesh_landmarks)
            emotions_list = [result]
            dominant_emotion = result["dominant"]
        except Exception:
            return {"emotions": [], "dominant_emotion": None}

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
