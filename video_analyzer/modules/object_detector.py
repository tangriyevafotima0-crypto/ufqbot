"""Object detection module using YOLOv8."""

import numpy as np


class ObjectDetector:
    """Detects objects in frames using YOLOv8 (ultralytics)."""

    def __init__(self, model_name="yolov8n.pt", confidence_threshold=0.5, detection_interval=1):
        self._model = None
        self._model_name = model_name
        self._confidence_threshold = confidence_threshold
        self._detection_interval = max(1, detection_interval)
        self._call_count = 0
        self._cached_result = {"objects": [], "object_count": 0}

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
                - objects: list of dicts with class_name, bbox (normalized 0-1), confidence
                - object_count: total number of objects detected
        """
        # Only run YOLO every Nth call; return cached result otherwise
        self._call_count += 1
        if self._detection_interval > 1 and (self._call_count - 1) % self._detection_interval != 0:
            return self._cached_result

        model = self._get_model()
        h, w = frame.shape[:2]
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

                    # Normalize bbox coordinates to [0,1] range
                    objects.append({
                        "class_name": class_name,
                        "bbox": {
                            "x1": float(xyxy[0]) / w,
                            "y1": float(xyxy[1]) / h,
                            "x2": float(xyxy[2]) / w,
                            "y2": float(xyxy[3]) / h,
                        },
                        "confidence": confidence,
                    })

        result = {
            "objects": objects,
            "object_count": len(objects),
        }
        self._cached_result = result
        return result

    def close(self):
        """Release resources."""
        self._model = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
