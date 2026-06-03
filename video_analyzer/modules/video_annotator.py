"""Video annotation module - draws overlays on frames and writes annotated video."""

import cv2
import numpy as np


class VideoAnnotator:
    """Draws analysis results on video frames and writes annotated output."""

    # Colors (BGR)
    COLOR_FACE = (0, 255, 0)       # Green
    COLOR_GAZE = (255, 0, 255)     # Magenta
    COLOR_POSE = (0, 255, 255)     # Yellow
    COLOR_OBJECT = (255, 165, 0)   # Orange
    COLOR_TEXT = (255, 255, 255)   # White
    COLOR_EMOTION = (0, 200, 255)  # Gold

    # Body pose skeleton connections
    POSE_CONNECTIONS = [
        ("left_shoulder", "right_shoulder"),
        ("left_shoulder", "left_elbow"),
        ("left_elbow", "left_wrist"),
        ("right_shoulder", "right_elbow"),
        ("right_elbow", "right_wrist"),
        ("left_shoulder", "left_hip"),
        ("right_shoulder", "right_hip"),
        ("left_hip", "right_hip"),
        ("left_hip", "left_knee"),
        ("left_knee", "left_ankle"),
        ("right_hip", "right_knee"),
        ("right_knee", "right_ankle"),
    ]

    def __init__(self, output_path, fps, width, height):
        """Initialize video writer.

        Args:
            output_path: path for output annotated video
            fps: frames per second for output
            width: frame width
            height: frame height
        """
        self.output_path = output_path
        self.width = width
        self.height = height
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        self.writer_active = self.writer.isOpened()
        if not self.writer_active:
            print(
                f"WARNING: VideoWriter failed to open '{output_path}'. "
                "Annotated video will not be written. "
                "Check codec availability (mp4v) and output path permissions."
            )

    def annotate_and_write(self, frame, frame_results):
        """Draw annotations on frame and write to output video.

        Args:
            frame: BGR image (numpy array)
            frame_results: dict with all analysis results for this frame
        """
        annotated = frame.copy()

        # Draw face bounding boxes
        face_data = frame_results.get("face_detection", {})
        faces = face_data.get("faces", [])
        for face in faces:
            bbox = face.get("bbox", {})
            x = int(bbox.get("x", 0) * self.width)
            y = int(bbox.get("y", 0) * self.height)
            w = int(bbox.get("w", 0) * self.width)
            h = int(bbox.get("h", 0) * self.height)
            cv2.rectangle(annotated, (x, y), (x + w, y + h), self.COLOR_FACE, 2)

        # Draw emotion labels above faces
        emotions_data = frame_results.get("emotions", {})
        emotion_list = emotions_data.get("emotions", [])
        for i, (face, emotion) in enumerate(zip(faces, emotion_list)):
            bbox = face.get("bbox", {})
            x = int(bbox.get("x", 0) * self.width)
            y = int(bbox.get("y", 0) * self.height)
            label = emotion.get("dominant", "")
            if label:
                cv2.putText(
                    annotated, label, (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.COLOR_EMOTION, 2,
                )

        # Draw eye gaze direction arrows
        eye_data = frame_results.get("eye_tracking", {})
        if eye_data.get("iris_landmarks"):
            iris = eye_data["iris_landmarks"]
            gaze_x = eye_data.get("gaze_x", 0) or 0
            gaze_y = eye_data.get("gaze_y", 0) or 0

            for key in ["left_center", "right_center"]:
                center = iris.get(key)
                if center:
                    cx = int(center[0] * self.width)
                    cy = int(center[1] * self.height)
                    end_x = int(cx + gaze_x * 50)
                    end_y = int(cy + gaze_y * 50)
                    cv2.arrowedLine(
                        annotated, (cx, cy), (end_x, end_y),
                        self.COLOR_GAZE, 2, tipLength=0.3,
                    )

        # Draw head pose angles text
        head_data = frame_results.get("head_pose", {})
        if head_data.get("yaw") is not None:
            yaw = head_data["yaw"]
            pitch = head_data["pitch"]
            roll = head_data["roll"]
            text = f"Y:{yaw:.0f} P:{pitch:.0f} R:{roll:.0f}"
            cv2.putText(
                annotated, text, (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, self.COLOR_TEXT, 2,
            )

        # Draw body pose skeleton
        pose_data = frame_results.get("body_pose", {})
        landmarks = pose_data.get("landmarks")
        if landmarks:
            for start_name, end_name in self.POSE_CONNECTIONS:
                start = landmarks.get(start_name)
                end = landmarks.get(end_name)
                if start and end:
                    if start.get("visibility", 0) > 0.5 and end.get("visibility", 0) > 0.5:
                        pt1 = (int(start["x"] * self.width), int(start["y"] * self.height))
                        pt2 = (int(end["x"] * self.width), int(end["y"] * self.height))
                        cv2.line(annotated, pt1, pt2, self.COLOR_POSE, 2)

        # Draw action label
        action_data = frame_results.get("actions", {})
        primary_action = action_data.get("primary_action", "")
        if primary_action and primary_action != "unknown":
            cv2.putText(
                annotated, f"Action: {primary_action}",
                (10, self.height - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, self.COLOR_TEXT, 2,
            )

        # Draw object detection boxes with labels
        obj_data = frame_results.get("objects", {})
        for obj in obj_data.get("objects", []):
            bbox = obj.get("bbox", {})
            x1 = int(bbox.get("x1", 0) * self.width)
            y1 = int(bbox.get("y1", 0) * self.height)
            x2 = int(bbox.get("x2", 0) * self.width)
            y2 = int(bbox.get("y2", 0) * self.height)
            label = f"{obj.get('class_name', '')} {obj.get('confidence', 0):.2f}"
            cv2.rectangle(annotated, (x1, y1), (x2, y2), self.COLOR_OBJECT, 2)
            cv2.putText(
                annotated, label, (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.COLOR_OBJECT, 1,
            )

        # Write annotated frame
        if self.writer_active:
            self.writer.write(annotated)

    def close(self):
        """Release video writer resources."""
        if self.writer:
            self.writer.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
