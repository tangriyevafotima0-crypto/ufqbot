"""Body pose estimation module using MediaPipe Pose."""

import numpy as np
import mediapipe as mp
import mediapipe.solutions.pose


class BodyPoseEstimator:
    """Estimates body pose using MediaPipe Pose (33 landmarks)."""

    # MediaPipe Pose landmark names
    LANDMARK_NAMES = [
        "nose", "left_eye_inner", "left_eye", "left_eye_outer",
        "right_eye_inner", "right_eye", "right_eye_outer",
        "left_ear", "right_ear", "mouth_left", "mouth_right",
        "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
        "left_wrist", "right_wrist", "left_pinky", "right_pinky",
        "left_index", "right_index", "left_thumb", "right_thumb",
        "left_hip", "right_hip", "left_knee", "right_knee",
        "left_ankle", "right_ankle", "left_heel", "right_heel",
        "left_foot_index", "right_foot_index",
    ]

    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def analyze_frame(self, frame, rgb_frame=None):
        """Estimate body pose in a frame.

        Args:
            frame: BGR image (numpy array)
            rgb_frame: optional pre-converted RGB image. If provided, used
                directly instead of converting from BGR.

        Returns:
            dict with keys:
                - landmarks: dict mapping landmark name to (x, y, z, visibility)
                - detected: bool indicating if a body was found
        """
        if rgb_frame is None:
            rgb_frame = frame[:, :, ::-1]
        results = self.pose.process(rgb_frame)

        if not results.pose_landmarks:
            return {"landmarks": None, "detected": False}

        landmarks = {}
        for i, landmark in enumerate(results.pose_landmarks.landmark):
            if i < len(self.LANDMARK_NAMES):
                landmarks[self.LANDMARK_NAMES[i]] = {
                    "x": landmark.x,
                    "y": landmark.y,
                    "z": landmark.z,
                    "visibility": landmark.visibility,
                }

        return {"landmarks": landmarks, "detected": True}

    def close(self):
        """Release resources."""
        self.pose.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
