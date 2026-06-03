"""Face detection module using MediaPipe FaceDetection."""

import mediapipe as mp
import numpy as np


class FaceDetector:
    """Detects faces in video frames using MediaPipe FaceDetection."""

    def __init__(self, min_detection_confidence=0.5):
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detection = self.mp_face_detection.FaceDetection(
            min_detection_confidence=min_detection_confidence
        )

    def analyze_frame(self, frame, rgb_frame=None):
        """Detect faces in a frame.

        Args:
            frame: BGR image (numpy array)
            rgb_frame: optional pre-converted RGB image. If provided, used
                directly instead of converting from BGR.

        Returns:
            dict with keys:
                - faces: list of dicts with 'bbox' (x, y, w, h normalized)
                - face_count: number of faces detected
        """
        if rgb_frame is None:
            rgb_frame = frame[:, :, ::-1]
        results = self.face_detection.process(rgb_frame)

        faces = []
        if results.detections:
            for detection in results.detections:
                bbox = detection.location_data.relative_bounding_box
                faces.append({
                    "bbox": {
                        "x": bbox.xmin,
                        "y": bbox.ymin,
                        "w": bbox.width,
                        "h": bbox.height,
                    },
                    "confidence": detection.score[0] if detection.score else 0.0,
                })

        return {
            "faces": faces,
            "face_count": len(faces),
        }

    def close(self):
        """Release resources."""
        self.face_detection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
