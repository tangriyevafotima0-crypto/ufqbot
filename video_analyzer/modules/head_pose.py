"""Head pose estimation module using MediaPipe FaceMesh and solvePnP."""

import numpy as np
import cv2
import mediapipe as mp


class HeadPoseEstimator:
    """Estimates head pose (yaw, pitch, roll) from face landmarks."""

    # Key landmark indices for pose estimation
    NOSE_TIP = 1
    CHIN = 152
    LEFT_EYE_CORNER = 33
    RIGHT_EYE_CORNER = 263
    LEFT_MOUTH_CORNER = 61
    RIGHT_MOUTH_CORNER = 291

    # 3D model points (generic face model)
    MODEL_POINTS = np.array([
        (0.0, 0.0, 0.0),        # Nose tip
        (0.0, -330.0, -65.0),   # Chin
        (-225.0, 170.0, -135.0),  # Left eye corner
        (225.0, 170.0, -135.0),   # Right eye corner
        (-150.0, -150.0, -125.0),  # Left mouth corner
        (150.0, -150.0, -125.0),   # Right mouth corner
    ], dtype=np.float64)

    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def analyze_frame(self, frame):
        """Estimate head pose angles.

        Args:
            frame: BGR image (numpy array)

        Returns:
            dict with keys:
                - yaw: left/right rotation in degrees
                - pitch: up/down rotation in degrees
                - roll: tilt rotation in degrees
                - landmarks_2d: the 6 key landmark positions used
        """
        h, w, _ = frame.shape
        rgb_frame = frame[:, :, ::-1]
        results = self.face_mesh.process(rgb_frame)

        if not results.multi_face_landmarks:
            return {"yaw": None, "pitch": None, "roll": None, "landmarks_2d": None}

        face_landmarks = results.multi_face_landmarks[0]
        landmarks = face_landmarks.landmark

        # Get 2D image points
        landmark_indices = [
            self.NOSE_TIP, self.CHIN,
            self.LEFT_EYE_CORNER, self.RIGHT_EYE_CORNER,
            self.LEFT_MOUTH_CORNER, self.RIGHT_MOUTH_CORNER,
        ]

        image_points = np.array([
            (landmarks[idx].x * w, landmarks[idx].y * h)
            for idx in landmark_indices
        ], dtype=np.float64)

        # Camera matrix (approximate)
        focal_length = w
        center = (w / 2, h / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)

        dist_coeffs = np.zeros((4, 1))

        # Solve PnP
        success, rotation_vector, translation_vector = cv2.solvePnP(
            self.MODEL_POINTS, image_points, camera_matrix, dist_coeffs
        )

        if not success:
            return {"yaw": None, "pitch": None, "roll": None, "landmarks_2d": None}

        # Convert rotation vector to rotation matrix
        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)

        # Get Euler angles
        proj_matrix = np.hstack((rotation_matrix, translation_vector))
        euler_angles = cv2.decomposeProjectionMatrix(proj_matrix)[6]

        pitch = float(euler_angles[0][0])
        yaw = float(euler_angles[1][0])
        roll = float(euler_angles[2][0])

        return {
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
            "landmarks_2d": image_points.tolist(),
        }

    def close(self):
        """Release resources."""
        self.face_mesh.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
