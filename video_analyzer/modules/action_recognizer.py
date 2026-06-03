"""Action recognition module using body pose keypoints."""

import numpy as np


class ActionRecognizer:
    """Classifies actions from body pose data using geometric rules."""

    # Base thresholds (calibrated for consecutive frames at ~30fps)
    BASE_WALKING_THRESHOLD = 0.02
    BASE_WRITING_MIN_THRESHOLD = 0.005
    BASE_WRITING_MAX_THRESHOLD = 0.03

    def __init__(self, sample_interval=1):
        """Initialize action recognizer.

        Args:
            sample_interval: number of source frames between analyzed frames.
                Thresholds are scaled by this value to account for larger
                inter-frame deltas at lower sampling rates.
        """
        self._prev_landmarks = None
        self._prev_actions = []
        self._sample_interval = max(1, sample_interval)
        self._writing_frame_count = 0

        # Scale thresholds proportionally to sample interval
        self._walking_threshold = self.BASE_WALKING_THRESHOLD * self._sample_interval
        self._writing_min_threshold = self.BASE_WRITING_MIN_THRESHOLD * self._sample_interval
        self._writing_max_threshold = self.BASE_WRITING_MAX_THRESHOLD * self._sample_interval

    def analyze_frame(self, pose_landmarks):
        """Classify action based on body pose landmarks.

        Args:
            pose_landmarks: dict mapping landmark names to {x, y, z, visibility}
                           (from BodyPoseEstimator)

        Returns:
            dict with keys:
                - actions: list of detected action strings
                - primary_action: most likely single action
                - details: dict with computed angles/values
        """
        if pose_landmarks is None:
            self._prev_landmarks = None
            return {"actions": [], "primary_action": "unknown", "details": {}}

        actions = []
        details = {}

        # Compute knee angles for sitting/standing detection
        left_knee_angle = self._compute_angle(
            pose_landmarks.get("left_hip"),
            pose_landmarks.get("left_knee"),
            pose_landmarks.get("left_ankle"),
        )
        right_knee_angle = self._compute_angle(
            pose_landmarks.get("right_hip"),
            pose_landmarks.get("right_knee"),
            pose_landmarks.get("right_ankle"),
        )

        details["left_knee_angle"] = left_knee_angle
        details["right_knee_angle"] = right_knee_angle

        avg_knee_angle = None
        if left_knee_angle is not None and right_knee_angle is not None:
            avg_knee_angle = (left_knee_angle + right_knee_angle) / 2
        elif left_knee_angle is not None:
            avg_knee_angle = left_knee_angle
        elif right_knee_angle is not None:
            avg_knee_angle = right_knee_angle

        # Sitting: knee angle < 120 degrees
        if avg_knee_angle is not None and avg_knee_angle < 120:
            actions.append("sitting")
        # Standing: knee angle > 160 degrees
        elif avg_knee_angle is not None and avg_knee_angle > 160:
            actions.append("standing")

        # Hand raising: wrist above shoulder
        left_wrist = pose_landmarks.get("left_wrist")
        left_shoulder = pose_landmarks.get("left_shoulder")
        right_wrist = pose_landmarks.get("right_wrist")
        right_shoulder = pose_landmarks.get("right_shoulder")

        if left_wrist and left_shoulder:
            if left_wrist["y"] < left_shoulder["y"] - 0.05:
                actions.append("hand_raising_left")
        if right_wrist and right_shoulder:
            if right_wrist["y"] < right_shoulder["y"] - 0.05:
                actions.append("hand_raising_right")

        # Walking: detect hip displacement between frames (more stable than ankles)
        if self._prev_landmarks is not None:
            left_hip_curr = pose_landmarks.get("left_hip")
            right_hip_curr = pose_landmarks.get("right_hip")
            left_hip_prev = self._prev_landmarks.get("left_hip")
            right_hip_prev = self._prev_landmarks.get("right_hip")

            if all([left_hip_curr, right_hip_curr, left_hip_prev, right_hip_prev]):
                left_movement = abs(left_hip_curr["x"] - left_hip_prev["x"])
                right_movement = abs(right_hip_curr["x"] - right_hip_prev["x"])
                avg_hip_movement = (left_movement + right_movement) / 2
                if avg_hip_movement > self._walking_threshold:
                    if "standing" in actions:
                        actions.remove("standing")
                    actions.append("walking")

        # Writing: hand near table level with small movements
        # Require writing condition for 2+ consecutive frames to reduce false positives
        writing_detected = False
        if left_wrist and left_shoulder:
            left_hip = pose_landmarks.get("left_hip")
            if left_hip:
                if left_wrist["y"] > left_shoulder["y"] and left_wrist["y"] < left_hip["y"]:
                    if self._prev_landmarks:
                        prev_left_wrist = self._prev_landmarks.get("left_wrist")
                        if prev_left_wrist:
                            movement = np.sqrt(
                                (left_wrist["x"] - prev_left_wrist["x"])**2 +
                                (left_wrist["y"] - prev_left_wrist["y"])**2
                            )
                            if self._writing_min_threshold < movement < self._writing_max_threshold:
                                writing_detected = True

        if writing_detected:
            self._writing_frame_count += 1
            if self._writing_frame_count >= 2:
                actions.append("writing")
        else:
            self._writing_frame_count = 0

        self._prev_landmarks = pose_landmarks

        # Determine primary action
        priority = ["walking", "hand_raising_left", "hand_raising_right",
                    "writing", "sitting", "standing"]
        primary_action = "unknown"
        for action in priority:
            if action in actions:
                primary_action = action
                break

        return {
            "actions": actions,
            "primary_action": primary_action,
            "details": details,
        }

    def _compute_angle(self, point_a, point_b, point_c):
        """Compute angle at point_b formed by points a-b-c.

        Returns angle in degrees, or None if any point is missing.
        """
        if not all([point_a, point_b, point_c]):
            return None

        a = np.array([point_a["x"], point_a["y"]])
        b = np.array([point_b["x"], point_b["y"]])
        c = np.array([point_c["x"], point_c["y"]])

        ba = a - b
        bc = c - b

        cosine = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
        cosine = np.clip(cosine, -1.0, 1.0)
        angle = np.degrees(np.arccos(cosine))

        return float(angle)

    def close(self):
        """Release resources."""
        self._prev_landmarks = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
