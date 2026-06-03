"""Object detection module using YOLOv8."""

import numpy as np


class ObjectDetector:
    """Detects objects in frames using YOLOv8 (ultralytics)."""

    def __init__(self, model_name="yolov8n.pt", confidence_threshold=0.5):
        self._model = None
        self._model_name = model_name
        self._confidence_threshold = confidence_threshold

    def _get_model(self):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self._model_name)
        return self._model

    def analyze_frame(self, frame):
        """Detect objects in a frame.

        Args:
            frame: BGR image (numpy array)

        Returns:
            dict with keys:
                - objects: list of dicts with class_name, bbox, confidence
                - object_count: total number of objects detected
        """
        model = self._get_model()
        results = model(frame, verbose=False, conf=self._confidence_threshold)

        objects = []
        if results and len(results) > 0:
            result = results[0]
            boxes = result.boxes

            if boxes is not None:
                for i in range(len(boxes)):
                    box = boxes[i]
                    cls_id = int(box.cls[0])
                    confidence = float(box.conf[0])
                    xyxy = box.xyxy[0].cpu().numpy()

                    class_name = result.names.get(cls_id, f"class_{cls_id}")

                    objects.append({
                        "class_name": class_name,
                        "bbox": {
                            "x1": float(xyxy[0]),
                            "y1": float(xyxy[1]),
                            "x2": float(xyxy[2]),
                            "y2": float(xyxy[3]),
                        },
                        "confidence": confidence,
                    })

        return {
            "objects": objects,
            "object_count": len(objects),
        }

    def close(self):
        """Release resources."""
        self._model = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
