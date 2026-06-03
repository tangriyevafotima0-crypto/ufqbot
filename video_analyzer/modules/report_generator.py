"""Report generation module - JSON, TXT reports and matplotlib charts."""

import json
import os
from datetime import timedelta

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


class ReportGenerator:
    """Generates analysis reports: JSON data, TXT summary, and PNG charts."""

    def __init__(self, output_dir):
        """Initialize report generator.

        Args:
            output_dir: directory path where reports will be saved
        """
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate_all(self, analysis_results, video_info):
        """Generate all report types.

        Args:
            analysis_results: dict with all accumulated analysis data
            video_info: dict with video metadata (path, fps, total_frames, duration)

        Returns:
            dict with paths to generated files
        """
        json_path = self._generate_json_report(analysis_results, video_info)
        txt_path = self._generate_txt_report(analysis_results, video_info)
        chart_paths = self._generate_charts(analysis_results, video_info)

        return {
            "json_report": json_path,
            "txt_report": txt_path,
            "charts": chart_paths,
        }

    def _generate_json_report(self, results, video_info):
        """Generate JSON report with all numerical data."""
        report = {
            "video_info": video_info,
            "summary": self._compute_summary(results),
            "frame_data": results.get("frame_data", []),
            "statistics": results.get("statistics", {}),
        }

        path = os.path.join(self.output_dir, "analysis_report.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, default=str)

        return path

    def _generate_txt_report(self, results, video_info):
        """Generate human-readable TXT report."""
        path = os.path.join(self.output_dir, "analysis_report.txt")
        summary = self._compute_summary(results)

        with open(path, "w", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write("VIDEO ANALYSIS REPORT\n")
            f.write("=" * 60 + "\n\n")

            # Video info
            f.write("--- VIDEO INFORMATION ---\n")
            f.write(f"File: {video_info.get('path', 'N/A')}\n")
            f.write(f"Duration: {video_info.get('duration_str', 'N/A')}\n")
            f.write(f"FPS: {video_info.get('fps', 'N/A')}\n")
            f.write(f"Total Frames: {video_info.get('total_frames', 'N/A')}\n")
            f.write(f"Frames Analyzed: {video_info.get('frames_analyzed', 'N/A')}\n")
            f.write(f"Resolution: {video_info.get('width', '?')}x{video_info.get('height', '?')}\n\n")

            # Face detection summary
            f.write("--- FACE DETECTION ---\n")
            f.write(f"Frames with faces: {summary.get('frames_with_faces', 0)}\n")
            f.write(f"Average face count: {summary.get('avg_face_count', 0):.2f}\n")
            f.write(f"Max faces in frame: {summary.get('max_face_count', 0)}\n\n")

            # Eye gaze summary
            f.write("--- EYE GAZE TRACKING ---\n")
            f.write(f"Camera look events: {summary.get('camera_look_count', 0)}\n")
            f.write(f"Camera look percentage: {summary.get('camera_look_percentage', 0):.1f}%\n\n")

            # Head pose summary
            f.write("--- HEAD POSE ---\n")
            f.write(f"Average yaw: {summary.get('avg_yaw', 0):.1f} degrees\n")
            f.write(f"Average pitch: {summary.get('avg_pitch', 0):.1f} degrees\n")
            f.write(f"Average roll: {summary.get('avg_roll', 0):.1f} degrees\n\n")

            # Emotion summary
            f.write("--- EMOTION DETECTION ---\n")
            emotion_dist = summary.get("emotion_distribution", {})
            for emotion, count in sorted(emotion_dist.items(), key=lambda x: -x[1]):
                f.write(f"  {emotion}: {count} frames\n")
            f.write(f"Dominant emotion: {summary.get('overall_dominant_emotion', 'N/A')}\n\n")

            # Body pose summary
            f.write("--- BODY POSE & ACTIONS ---\n")
            action_dist = summary.get("action_distribution", {})
            for action, count in sorted(action_dist.items(), key=lambda x: -x[1]):
                f.write(f"  {action}: {count} frames\n")
            f.write(f"Primary action: {summary.get('primary_action', 'N/A')}\n\n")

            # Object detection summary
            f.write("--- OBJECT DETECTION ---\n")
            object_counts = summary.get("object_counts", {})
            for obj, count in sorted(object_counts.items(), key=lambda x: -x[1])[:20]:
                f.write(f"  {obj}: detected {count} times\n")
            f.write(f"Total unique objects: {len(object_counts)}\n\n")

            f.write("=" * 60 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 60 + "\n")

        return path

    def _generate_charts(self, results, video_info):
        """Generate matplotlib charts as PNG files."""
        chart_paths = []

        frame_data = results.get("frame_data", [])
        if not frame_data:
            return chart_paths

        timestamps = [fd.get("timestamp", i) for i, fd in enumerate(frame_data)]

        # Gaze direction over time
        gaze_chart = self._generate_gaze_chart(frame_data, timestamps)
        if gaze_chart:
            chart_paths.append(gaze_chart)

        # Emotion changes over time
        emotion_chart = self._generate_emotion_chart(frame_data, timestamps)
        if emotion_chart:
            chart_paths.append(emotion_chart)

        # Action timeline
        action_chart = self._generate_action_chart(frame_data, timestamps)
        if action_chart:
            chart_paths.append(action_chart)

        return chart_paths

    def _generate_gaze_chart(self, frame_data, timestamps):
        """Generate gaze direction chart."""
        gaze_x = []
        gaze_y = []
        gaze_times = []

        for i, fd in enumerate(frame_data):
            eye_data = fd.get("eye_tracking", {})
            if eye_data.get("gaze_x") is not None:
                gaze_x.append(eye_data["gaze_x"])
                gaze_y.append(eye_data["gaze_y"])
                gaze_times.append(timestamps[i])

        if not gaze_x:
            return None

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 6))
        fig.suptitle("Gaze Direction Over Time")

        ax1.plot(gaze_times, gaze_x, "b-", linewidth=0.5, alpha=0.7)
        ax1.set_ylabel("Horizontal Gaze (left < 0 > right)")
        ax1.axhline(y=0, color="r", linestyle="--", alpha=0.3)
        ax1.set_xlabel("Time (s)")

        ax2.plot(gaze_times, gaze_y, "g-", linewidth=0.5, alpha=0.7)
        ax2.set_ylabel("Vertical Gaze (up < 0 > down)")
        ax2.axhline(y=0, color="r", linestyle="--", alpha=0.3)
        ax2.set_xlabel("Time (s)")

        plt.tight_layout()
        path = os.path.join(self.output_dir, "chart_gaze_direction.png")
        plt.savefig(path, dpi=100)
        plt.close(fig)

        return path

    def _generate_emotion_chart(self, frame_data, timestamps):
        """Generate emotion changes chart."""
        emotion_map = {
            "happy": 1, "surprise": 2, "neutral": 3,
            "sad": 4, "angry": 5, "fear": 6, "disgust": 7
        }

        emotion_values = []
        emotion_times = []

        for i, fd in enumerate(frame_data):
            emotion_data = fd.get("emotions", {})
            dominant = emotion_data.get("dominant_emotion")
            if dominant and dominant in emotion_map:
                emotion_values.append(emotion_map[dominant])
                emotion_times.append(timestamps[i])

        if not emotion_values:
            return None

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.scatter(emotion_times, emotion_values, s=10, alpha=0.6, c="purple")
        ax.set_yticks(list(emotion_map.values()))
        ax.set_yticklabels(list(emotion_map.keys()))
        ax.set_xlabel("Time (s)")
        ax.set_title("Emotion Changes Over Time")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        path = os.path.join(self.output_dir, "chart_emotions.png")
        plt.savefig(path, dpi=100)
        plt.close(fig)

        return path

    def _generate_action_chart(self, frame_data, timestamps):
        """Generate action timeline chart."""
        action_map = {
            "standing": 1, "sitting": 2, "walking": 3,
            "hand_raising_left": 4, "hand_raising_right": 5,
            "writing": 6, "unknown": 0
        }

        action_values = []
        action_times = []

        for i, fd in enumerate(frame_data):
            action_data = fd.get("actions", {})
            primary = action_data.get("primary_action", "unknown")
            if primary in action_map:
                action_values.append(action_map[primary])
                action_times.append(timestamps[i])

        if not action_values:
            return None

        fig, ax = plt.subplots(figsize=(12, 4))
        ax.scatter(action_times, action_values, s=10, alpha=0.6, c="teal")
        ax.set_yticks(list(action_map.values()))
        ax.set_yticklabels(list(action_map.keys()))
        ax.set_xlabel("Time (s)")
        ax.set_title("Action Timeline")
        ax.grid(True, alpha=0.3)

        plt.tight_layout()
        path = os.path.join(self.output_dir, "chart_actions.png")
        plt.savefig(path, dpi=100)
        plt.close(fig)

        return path

    def _compute_summary(self, results):
        """Compute summary statistics from frame data."""
        frame_data = results.get("frame_data", [])
        if not frame_data:
            return {}

        summary = {}

        # Face detection stats
        face_counts = [fd.get("face_detection", {}).get("face_count", 0) for fd in frame_data]
        summary["frames_with_faces"] = sum(1 for c in face_counts if c > 0)
        summary["avg_face_count"] = np.mean(face_counts) if face_counts else 0
        summary["max_face_count"] = max(face_counts) if face_counts else 0

        # Eye gaze stats
        camera_looks = [
            fd.get("eye_tracking", {}).get("looking_at_camera", False)
            for fd in frame_data
        ]
        summary["camera_look_count"] = sum(camera_looks)
        summary["camera_look_percentage"] = (
            sum(camera_looks) / len(camera_looks) * 100 if camera_looks else 0
        )

        # Head pose stats
        yaws = [fd.get("head_pose", {}).get("yaw") for fd in frame_data]
        pitches = [fd.get("head_pose", {}).get("pitch") for fd in frame_data]
        rolls = [fd.get("head_pose", {}).get("roll") for fd in frame_data]
        yaws = [y for y in yaws if y is not None]
        pitches = [p for p in pitches if p is not None]
        rolls = [r for r in rolls if r is not None]
        summary["avg_yaw"] = np.mean(yaws) if yaws else 0
        summary["avg_pitch"] = np.mean(pitches) if pitches else 0
        summary["avg_roll"] = np.mean(rolls) if rolls else 0

        # Emotion stats
        emotion_dist = {}
        for fd in frame_data:
            dominant = fd.get("emotions", {}).get("dominant_emotion")
            if dominant:
                emotion_dist[dominant] = emotion_dist.get(dominant, 0) + 1
        summary["emotion_distribution"] = emotion_dist
        summary["overall_dominant_emotion"] = (
            max(emotion_dist, key=emotion_dist.get) if emotion_dist else "N/A"
        )

        # Action stats
        action_dist = {}
        for fd in frame_data:
            primary = fd.get("actions", {}).get("primary_action")
            if primary and primary != "unknown":
                action_dist[primary] = action_dist.get(primary, 0) + 1
        summary["action_distribution"] = action_dist
        summary["primary_action"] = (
            max(action_dist, key=action_dist.get) if action_dist else "N/A"
        )

        # Object detection stats
        object_counts = {}
        for fd in frame_data:
            for obj in fd.get("objects", {}).get("objects", []):
                name = obj.get("class_name", "unknown")
                object_counts[name] = object_counts.get(name, 0) + 1
        summary["object_counts"] = object_counts

        return summary
