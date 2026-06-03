"""Eye gaze tracking module using MediaPipe FaceMesh."""

import numpy as np
import mediapipe as mp


class EyeTracker:
    """Tracks eye gaze direction using MediaPipe FaceMesh iris landmarks."""

    # Iris landmark indices (468-477)
    LEFT_IRIS = [468, 469, 470, 471, 472]
    RIGHT_IRIS = [473, 474, 475, 476, 477]

    # Eye corner landmarks
    LEFT_EYE_INNER = 133
    LEFT_EYE_OUTER = 33
    RIGHT_EYE_INNER = 362
    RIGHT_EYE_OUTER = 263

    # Threshold for "looking at camera" (normalized distance from center)
    CAMERA_LOOK_THRESHOLD = 0.15

    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def analyze_frame(self, frame):
        """Analyze eye gaze in a frame.

        Args:
            frame: BGR image (numpy array)

        Returns:
            dict with keys:
                - gaze_x: horizontal gaze position (-1 left to 1 right)
                - gaze_y: vertical gaze position (-1 up to 1 down)
                - looking_at_camera: bool
                - iris_landmarks: dict with left/right iris centers
        """
        rgb_frame = frame[:, :, ::-1]
        results = self.face_mesh.process(rgb_frame)

        if not results.multi_face_landmarks:
            return {
                "gaze_x": None,
                "gaze_y": None,
                "looking_at_camera": False,
                "iris_landmarks": None,
            }

        face_landmarks = results.multi_face_landmarks[0]
        landmarks = face_landmarks.landmark

        # Get iris centers
        left_iris_center = self._get_landmark_center(landmarks, self.LEFT_IRIS)
        right_iris_center = self._get_landmark_center(landmarks, self.RIGHT_IRIS)

        # Get eye corners
        left_inner = np.array([landmarks[self.LEFT_EYE_INNER].x, landmarks[self.LEFT_EYE_INNER].y])
        left_outer = np.array([landmarks[self.LEFT_EYE_OUTER].x, landmarks[self.LEFT_EYE_OUTER].y])
        right_inner = np.array([landmarks[self.RIGHT_EYE_INNER].x, landmarks[self.RIGHT_EYE_INNER].y])
        right_outer = np.array([landmarks[self.RIGHT_EYE_OUTER].x, landmarks[self.RIGHT_EYE_OUTER].y])

        # Compute gaze for left eye
        left_eye_center = (left_inner + left_outer) / 2
        left_eye_width = np.linalg.norm(left_inner - left_outer)
        left_gaze = (left_iris_center - left_eye_center) / (left_eye_width + 1e-6)

        # Compute gaze for right eye
        right_eye_center = (right_inner + right_outer) / 2
        right_eye_width = np.linalg.norm(right_inner - right_outer)
        right_gaze = (right_iris_center - right_eye_center) / (right_eye_width + 1e-6)

        # Average both eyes
        gaze_x = float((left_gaze[0] + right_gaze[0]) / 2)
        gaze_y = float((left_gaze[1] + right_gaze[1]) / 2)

        # Check if looking at camera (iris centered in eye)
        gaze_magnitude = np.sqrt(gaze_x**2 + gaze_y**2)
        looking_at_camera = gaze_magnitude < self.CAMERA_LOOK_THRESHOLD

        return {
            "gaze_x": gaze_x,
            "gaze_y": gaze_y,
            "looking_at_camera": bool(looking_at_camera),
            "iris_landmarks": {
                "left_center": left_iris_center.tolist(),
                "right_center": right_iris_center.tolist(),
            },
        }

    def _get_landmark_center(self, landmarks, indices):
        """Compute center point of a set of landmarks."""
        points = np.array([[landmarks[i].x, landmarks[i].y] for i in indices])
        return points.mean(axis=0)

    def close(self):
        """Release resources."""
        self.face_mesh.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
