"""
Centralized configuration module for Video Analyzer.
Loads version info from version.json and provides all configurable parameters.
"""

import json
import os


def load_version():
    """Load version information from version.json."""
    version_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'version.json')
    with open(version_path, 'r', encoding='utf-8') as f:
        return json.load(f)


class Config:
    """Central configuration class for the Video Analyzer application."""

    def __init__(self):
        version_info = load_version()

        # Application metadata
        self.APP_NAME = "Video Analyzer"
        self.VERSION = version_info.get("version", "0.0.0")
        self.RELEASE_DATE = version_info.get("release_date", "")
        self.CHANNEL = version_info.get("channel", "stable")
        self.MIN_PYTHON = version_info.get("min_python", "3.11")
        self.UPDATE_URL = version_info.get("update_url", "")

        # Frame processing
        self.TARGET_FPS = 2.5

        # Object detection
        self.OBJECT_DETECTION_INTERVAL = 3
        self.YOLO_MODEL = "yolov8n.pt"
        self.YOLO_CONFIDENCE = 0.5

        # Eye tracking / camera look detection
        self.CAMERA_LOOK_THRESHOLD_X = 0.18
        self.CAMERA_LOOK_THRESHOLD_Y = 0.12

        # Emotion detection thresholds (landmark-based)
        self.SMILE_THRESHOLD = 0.28
        self.SURPRISE_MOUTH_THRESHOLD = 0.06
        self.SURPRISE_EYE_THRESHOLD = 0.30
        self.SAD_THRESHOLD = 0.015
        self.ANGRY_BROW_THRESHOLD = 0.018

        # Report generation
        self.OUTPUT_COMPACT_THRESHOLD = 3000
