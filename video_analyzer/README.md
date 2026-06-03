# Video Analyzer

A comprehensive video analysis desktop application that processes videos and generates detailed reports with face detection, eye gaze tracking, head pose estimation, emotion detection, body pose analysis, action recognition, and object detection.

## Features

- **Face Detection** - Detect all faces in each frame using MediaPipe FaceDetection
- **Eye Gaze Tracking** - Track iris position and gaze direction using MediaPipe FaceMesh
- **Head Pose Estimation** - Compute yaw, pitch, roll angles using solvePnP
- **Emotion Detection** - Detect emotions (happy, sad, angry, neutral, etc.) using DeepFace
- **Body Pose Estimation** - Full body keypoint detection (33 landmarks) using MediaPipe Pose
- **Action Recognition** - Classify actions (sitting, standing, walking, hand raising, writing) from pose data
- **Object Detection** - Detect common objects using YOLOv8
- **Camera Gaze Statistics** - Track when a person is looking directly at the camera
- **Annotated Video Output** - Visual overlays on video with all detections drawn
- **Report Generation** - JSON data report, TXT human-readable report, and PNG charts/graphs

## Supported Video Formats

- MP4 (.mp4)
- AVI (.avi)
- MKV (.mkv)
- MOV (.mov)
- WMV (.wmv)
- FLV (.flv)
- WebM (.webm)

## Installation

1. Ensure Python 3.11 or later is installed.

2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

Run the application:

```bash
python main.py
```

A file dialog will open. Select a video file to analyze. The application will:

1. Open the selected video
2. Process frames at ~2.5 fps (configurable)
3. Display a progress bar with estimated time remaining
4. Generate all output files in a directory next to the input video

## Output Files

All output is saved in a `{video_name}_analysis/` folder next to the input video:

| File | Description |
|------|-------------|
| `analysis_report.json` | Complete numerical data for all frames |
| `analysis_report.txt` | Human-readable summary report |
| `chart_gaze_direction.png` | Gaze direction over time graph |
| `chart_emotions.png` | Emotion changes over time graph |
| `chart_actions.png` | Action timeline graph |
| `{video_name}_annotated.mp4` | Video with all visual annotations drawn |

## Building as EXE (Windows)

To build a standalone executable:

```bash
build.bat
```

Or manually:

```bash
pip install -r requirements.txt
pyinstaller --onefile --windowed --name VideoAnalyzer main.py
```

The executable will be in `dist/VideoAnalyzer.exe`.

## Performance Notes for Long Videos

The application is designed to handle videos up to 30 minutes or longer:

- **Frame Sampling**: Instead of analyzing every frame, it samples at ~2.5 fps by default. For a 30fps video, this means analyzing every 12th frame.
- **Memory Efficiency**: Frames are processed one at a time and only compact result dictionaries are stored (no image data in memory).
- **Streaming Output**: The annotated video is written frame-by-frame as processing occurs.
- **Batch Emotion Detection**: Emotion analysis only runs on frames where faces are detected.
- **Graceful Error Handling**: If one module fails on a frame, other modules continue processing.

## Project Structure

```
video_analyzer/
├── main.py                    # Entry point with tkinter GUI
├── requirements.txt           # Dependencies
├── build.bat                  # PyInstaller build script
├── README.md                  # This file
└── modules/
    ├── __init__.py
    ├── face_detector.py       # Face detection (MediaPipe)
    ├── eye_tracker.py         # Eye gaze tracking (MediaPipe FaceMesh)
    ├── head_pose.py           # Head pose estimation (solvePnP)
    ├── emotion_detector.py    # Emotion detection (DeepFace)
    ├── body_pose.py           # Body pose estimation (MediaPipe Pose)
    ├── action_recognizer.py   # Action classification
    ├── object_detector.py     # Object detection (YOLOv8)
    ├── report_generator.py    # JSON/TXT reports + charts
    └── video_annotator.py     # Video annotation overlays
```

## Requirements

- Python 3.11+
- OpenCV
- MediaPipe
- NumPy
- Matplotlib
- tqdm
- Pillow
- Ultralytics (YOLOv8)
- DeepFace
- tf-keras
- dlib
- PyInstaller (for building EXE)
