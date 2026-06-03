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
- **Version & Update System** - Built-in update checker with semver comparison
- **Professional Installer** - One-click Windows installation with install.bat

## Supported Video Formats

- MP4 (.mp4)
- AVI (.avi)
- MKV (.mkv)
- MOV (.mov)
- WMV (.wmv)
- FLV (.flv)
- WebM (.webm)

## Quick Start (Windows)

**Just double-click `start.bat` - that is all you need to do.**

On the first run, `start.bat` will automatically:
- Check that Python 3.11+ is installed
- Create a virtual environment
- Install all dependencies
- Download AI models (YOLO, DeepFace)
- Launch the application

On subsequent runs, it skips installation and launches immediately.

> **Prerequisite:** Python 3.11 or later must be installed and added to PATH.
> Download it from https://www.python.org/downloads/ and check "Add Python to PATH" during installation.

## Alternative Installation

### Using install.bat

If you prefer to install separately, double-click `install.bat`. It performs the same setup as `start.bat` but does not launch the app afterward. It also creates a desktop shortcut.

### Manual Install

1. Ensure Python 3.11 or later is installed.

2. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
.venv\Scripts\activate
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

## Usage

The easiest way to run is to double-click `start.bat`.

Alternatively, run the application manually:

```bash
python main.py
```

A file dialog will open. Select a video file to analyze. The application will:

1. Open the selected video
2. Process frames at ~2.5 fps (configurable via `config.py`)
3. Display a progress bar with estimated time remaining
4. Generate all output files in a directory next to the input video

## Updating

### Using update.bat (Recommended)

Run `update.bat` to automatically check for and apply updates. The script will:

1. Check the current installed version
2. Query GitHub releases for the latest version
3. If an update is available, show the changelog and apply the update via `git pull`
4. Reinstall dependencies to pick up any new requirements
5. Update `install_info.json` with the new version

### Manual Update

1. Pull the latest code: `git pull`
2. Re-install dependencies: `pip install -r requirements.txt`
3. Check `version.json` for the current version number

## Configuration

All application settings are centralized in `config.py`:

| Setting | Default | Description |
|---------|---------|-------------|
| `TARGET_FPS` | 2.5 | Frames per second to sample from video |
| `OBJECT_DETECTION_INTERVAL` | 3 | Run YOLO every Nth sampled frame |
| `CAMERA_LOOK_THRESHOLD_X` | 0.18 | Horizontal gaze threshold for camera look |
| `CAMERA_LOOK_THRESHOLD_Y` | 0.12 | Vertical gaze threshold for camera look |
| `YOLO_MODEL` | yolov8n.pt | YOLO model file to use |
| `YOLO_CONFIDENCE` | 0.5 | Minimum confidence for object detection |
| `OUTPUT_COMPACT_THRESHOLD` | 3000 | Frame count above which JSON omits per-frame data |

To modify settings, edit `config.py` or import the `Config` class in your code:

```python
from config import Config
cfg = Config()
print(cfg.VERSION)
```

## Version & Update System

The application uses a version tracking system based on `version.json`:

- **version**: Current semver version (e.g., "1.1.0")
- **channel**: Release channel ("stable", "beta", or "dev")
- **update_url**: GitHub API endpoint for checking releases
- **changelog**: List of changes in the current version

The `modules/updater.py` module provides the `UpdateChecker` class that can programmatically check for updates using the GitHub releases API. It compares semver versions and returns download URLs and changelogs.

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

To build a standalone executable, run `build.bat`. The script will:

1. Activate the virtual environment (or use system Python)
2. Install/upgrade PyInstaller
3. Install all requirements
4. Build a single-file executable with PyInstaller
5. Copy `version.json` to the dist folder
6. Report the output file size

The executable will be at `dist/VideoAnalyzer.exe`.

## Performance Notes for Long Videos

The application is designed to handle videos up to 30 minutes or longer:

- **Frame Sampling**: Instead of analyzing every frame, it samples at ~2.5 fps by default. For a 30fps video, this means analyzing every 12th frame.
- **Memory Efficiency**: Frames are processed one at a time and only compact result dictionaries are stored (no image data in memory).
- **Streaming Output**: The annotated video is written frame-by-frame as processing occurs.
- **Batch Emotion Detection**: Emotion analysis only runs on frames where faces are detected.
- **YOLO Frequency Control**: Object detection runs every Nth sampled frame (default: every 3rd) and caches results for intermediate frames.
- **Graceful Error Handling**: If one module fails on a frame, other modules continue processing.
- **Compact Reports**: For videos exceeding 3000 frames, per-frame data is omitted from JSON output.

## Project Structure

```
video_analyzer/
├── main.py                    # Entry point with tkinter GUI
├── config.py                  # Centralized configuration
├── version.json               # Version tracking and metadata
├── requirements.txt           # Python dependencies
├── start.bat                  # Single-click install + launch (recommended)
├── install.bat                # Standalone installer (creates desktop shortcut)
├── update.bat                 # Update checker and applier
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
    ├── video_annotator.py     # Video annotation overlays
    └── updater.py             # Update checker (GitHub releases API)
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

## Changelog

### v1.1.0 (2025-01-15)

- Fixed camera look event counting - now counts distinct events (transitions)
- Added separate x/y gaze thresholds for more accurate camera look detection
- Improved walking detection using hip displacement instead of ankle positions
- Added professional installer (install.bat) and updater system
- Optimized frame processing with single RGB conversion
- Added YOLO detection frequency control
- Added camera look visual indicator on annotated video
- Head pose angle normalization to prevent gimbal lock issues
- Emotion detector handles edge cases with zero-dimension crops

### v1.0.0 (2025-01-14)

- Initial release with full video analysis pipeline
- Face detection, eye tracking, head pose, emotion detection
- Body pose estimation and action recognition
- Object detection with YOLOv8
- Report generation (JSON, TXT, charts)
- Annotated video output
