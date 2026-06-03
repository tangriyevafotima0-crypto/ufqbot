"""Video Analyzer - Main application entry point.

Comprehensive video analysis tool that processes videos and generates
detailed reports including face detection, eye gaze tracking, head pose,
emotion detection, body pose, action recognition, and object detection.
"""

import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox

os.environ.setdefault("YOLO_AUTOINSTALL", "0")

import cv2
import numpy as np
import mediapipe as mp
from tqdm import tqdm

from config import Config
from modules.face_detector import FaceDetector
from modules.eye_tracker import EyeTracker
from modules.head_pose import HeadPoseEstimator
from modules.emotion_detector import EmotionDetector
from modules.body_pose import BodyPoseEstimator
from modules.action_recognizer import ActionRecognizer
from modules.object_detector import ObjectDetector
from modules.report_generator import ReportGenerator
from modules.video_annotator import VideoAnnotator


def select_video_file():
    """Open file dialog to select a video file."""
    root = tk.Tk()
    root.withdraw()

    file_path = filedialog.askopenfilename(
        title="Select Video File",
        filetypes=[
            ("Video Files", "*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm"),
            ("MP4", "*.mp4"),
            ("AVI", "*.avi"),
            ("All Files", "*.*"),
        ],
    )

    root.destroy()
    return file_path


def compute_sample_interval(video_fps, target_fps=2.5):
    """Compute frame sampling interval for efficient processing.

    Args:
        video_fps: original video FPS
        target_fps: target analysis FPS (default 2.5 fps)

    Returns:
        int: analyze every Nth frame
    """
    if video_fps <= 0:
        return 1
    interval = max(1, int(video_fps / target_fps))
    return interval


def format_duration(seconds):
    """Format seconds to HH:MM:SS string."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def analyze_video(video_path, target_fps=None):
    """Main analysis pipeline for a video file.

    Args:
        video_path: path to the video file
        target_fps: frames per second to analyze (default from Config)
    """
    cfg = Config()
    if target_fps is None:
        target_fps = cfg.TARGET_FPS
    # Open video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"ERROR: Cannot open video file: {video_path}")
        return

    # Video properties
    video_fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / video_fps if video_fps > 0 else 0

    sample_interval = compute_sample_interval(video_fps, target_fps)
    frames_to_analyze = total_frames // sample_interval

    print("=" * 60)
    print("VIDEO ANALYZER")
    print("=" * 60)
    print(f"Video: {os.path.basename(video_path)}")
    print(f"Duration: {format_duration(duration)}")
    print(f"FPS: {video_fps:.1f}")
    print(f"Resolution: {width}x{height}")
    print(f"Total frames: {total_frames}")
    print(f"Sampling: every {sample_interval} frame(s) (~{video_fps/sample_interval:.1f} fps)")
    print(f"Frames to analyze: ~{frames_to_analyze}")
    print("=" * 60)

    # Create output directory
    video_dir = os.path.dirname(os.path.abspath(video_path))
    video_name = os.path.splitext(os.path.basename(video_path))[0]
    output_dir = os.path.join(video_dir, f"{video_name}_analysis")
    os.makedirs(output_dir, exist_ok=True)

    # Video info for reports
    video_info = {
        "path": video_path,
        "fps": video_fps,
        "total_frames": total_frames,
        "width": width,
        "height": height,
        "duration": duration,
        "duration_str": format_duration(duration),
        "frames_analyzed": 0,
        "sample_interval": sample_interval,
    }

    # Initialize modules
    print("\nInitializing analysis modules...")
    face_detector = FaceDetector()
    eye_tracker = EyeTracker()
    head_pose_estimator = HeadPoseEstimator()
    emotion_detector = EmotionDetector(config=cfg)
    body_pose_estimator = BodyPoseEstimator()
    action_recognizer = ActionRecognizer(sample_interval=sample_interval)
    object_detector = ObjectDetector(detection_interval=cfg.OBJECT_DETECTION_INTERVAL)

    # Shared FaceMesh instance (refine_landmarks=True is the superset
    # needed by EyeTracker for iris landmarks; HeadPoseEstimator uses
    # a subset of the same landmarks)
    mp_face_mesh = mp.solutions.face_mesh
    shared_face_mesh = mp_face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    # Output annotated video path
    annotated_video_path = os.path.join(output_dir, f"{video_name}_annotated.mp4")
    output_fps = video_fps / sample_interval
    annotator = VideoAnnotator(annotated_video_path, output_fps, width, height)

    # Accumulated results
    frame_data = []
    frame_idx = 0
    analyzed_count = 0

    # Error counters per module
    error_counts = {
        "face_detection": 0,
        "eye_tracking": 0,
        "head_pose": 0,
        "emotions": 0,
        "body_pose": 0,
        "actions": 0,
        "objects": 0,
        "annotator": 0,
    }

    print("\nProcessing video...")
    start_time = time.time()

    with tqdm(total=frames_to_analyze, desc="Analyzing", unit="frame") as pbar:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Only process sampled frames
            if frame_idx % sample_interval == 0:
                timestamp = frame_idx / video_fps if video_fps > 0 else 0

                frame_results = {"timestamp": timestamp, "frame_index": frame_idx}

                # Convert to RGB once for all modules that need it
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Run shared FaceMesh once for both eye_tracker and head_pose
                face_mesh_landmarks = None
                try:
                    mesh_results = shared_face_mesh.process(rgb_frame)
                    if mesh_results.multi_face_landmarks:
                        face_mesh_landmarks = mesh_results.multi_face_landmarks[0].landmark
                except Exception:
                    face_mesh_landmarks = None

                # Face detection
                try:
                    face_result = face_detector.analyze_frame(frame, rgb_frame=rgb_frame)
                    frame_results["face_detection"] = face_result
                except Exception:
                    error_counts["face_detection"] += 1
                    frame_results["face_detection"] = {"faces": [], "face_count": 0}

                # Eye gaze tracking (uses shared landmarks)
                try:
                    eye_result = eye_tracker.analyze_frame(frame, face_mesh_landmarks)
                    frame_results["eye_tracking"] = eye_result
                except Exception:
                    error_counts["eye_tracking"] += 1
                    frame_results["eye_tracking"] = {
                        "gaze_x": None, "gaze_y": None,
                        "looking_at_camera": False, "iris_landmarks": None,
                    }

                # Head pose estimation (uses shared landmarks)
                try:
                    head_result = head_pose_estimator.analyze_frame(frame, face_mesh_landmarks)
                    frame_results["head_pose"] = head_result
                except Exception:
                    error_counts["head_pose"] += 1
                    frame_results["head_pose"] = {
                        "yaw": None, "pitch": None, "roll": None,
                    }

                # Emotion detection (uses shared face mesh landmarks)
                # Note: processes only the primary face (shared FaceMesh max_num_faces=1)
                try:
                    emotion_result = emotion_detector.analyze_frame(face_mesh_landmarks)
                    frame_results["emotions"] = emotion_result
                except Exception:
                    error_counts["emotions"] += 1
                    frame_results["emotions"] = {"emotions": [], "dominant_emotion": None}

                # Body pose estimation
                try:
                    pose_result = body_pose_estimator.analyze_frame(frame, rgb_frame=rgb_frame)
                    frame_results["body_pose"] = pose_result
                except Exception:
                    error_counts["body_pose"] += 1
                    frame_results["body_pose"] = {"landmarks": None, "detected": False}

                # Action recognition
                try:
                    landmarks = frame_results["body_pose"].get("landmarks")
                    action_result = action_recognizer.analyze_frame(landmarks)
                    frame_results["actions"] = action_result
                except Exception:
                    error_counts["actions"] += 1
                    frame_results["actions"] = {
                        "actions": [], "primary_action": "unknown", "details": {},
                    }

                # Object detection
                try:
                    object_result = object_detector.analyze_frame(frame)
                    frame_results["objects"] = object_result
                except Exception:
                    error_counts["objects"] += 1
                    frame_results["objects"] = {"objects": [], "object_count": 0}

                # Annotate and write frame
                try:
                    annotator.annotate_and_write(frame, frame_results)
                except Exception:
                    error_counts["annotator"] += 1

                # Store compact frame data (no images, just results)
                frame_data.append(frame_results)
                analyzed_count += 1
                pbar.update(1)

            frame_idx += 1

    # Cleanup video resources
    cap.release()
    annotator.close()
    shared_face_mesh.close()

    elapsed = time.time() - start_time
    video_info["frames_analyzed"] = analyzed_count

    print(f"\nProcessing complete! ({elapsed:.1f}s)")
    print(f"Frames analyzed: {analyzed_count}")

    # Print error summary per module
    has_errors = any(v > 0 for v in error_counts.values())
    if has_errors:
        print("\n--- Module Error Summary ---")
        for module_name, count in error_counts.items():
            if count > 0:
                print(
                    f"  WARNING: {module_name} failed on "
                    f"{count}/{analyzed_count} frames"
                )
        print("----------------------------")

    # Generate reports
    print("\nGenerating reports...")
    analysis_results = {"frame_data": frame_data}
    report_gen = ReportGenerator(output_dir)
    report_files = report_gen.generate_all(analysis_results, video_info)

    print(f"\nOutput directory: {output_dir}")
    print("Generated files:")
    print(f"  - JSON report: {os.path.basename(report_files['json_report'])}")
    print(f"  - TXT report: {os.path.basename(report_files['txt_report'])}")
    for chart in report_files.get("charts", []):
        print(f"  - Chart: {os.path.basename(chart)}")
    print(f"  - Annotated video: {os.path.basename(annotated_video_path)}")

    # Cleanup modules
    face_detector.close()
    eye_tracker.close()
    head_pose_estimator.close()
    body_pose_estimator.close()
    action_recognizer.close()
    object_detector.close()

    print("\nDone!")


def main():
    """Main entry point."""
    print(f"Video Analyzer v{Config().VERSION}")
    print("Select a video file to analyze...\n")

    video_path = select_video_file()

    if not video_path:
        print("No file selected. Exiting.")
        sys.exit(0)

    if not os.path.isfile(video_path):
        print(f"ERROR: File not found: {video_path}")
        sys.exit(1)

    analyze_video(video_path)


if __name__ == "__main__":
    main()
