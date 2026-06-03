"""
check_update.py - Dependency update checker for Video Analyzer.

Compares version.json against install_info.json. If versions differ
(or install_info.json is missing), runs pip install -r requirements.txt
to ensure dependencies match the current app version.

Usage:
    python check_update.py          # Only update if version mismatch
    python check_update.py --force  # Always run pip install
"""

import datetime
import json
import os
import subprocess
import sys


def main():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))

        version_path = os.path.join(script_dir, "version.json")
        install_info_path = os.path.join(script_dir, "install_info.json")
        requirements_path = os.path.join(script_dir, "requirements.txt")

        force = "--force" in sys.argv

        # Read current app version
        if not os.path.exists(version_path):
            print("  [check_update] WARNING: version.json not found, skipping.")
            return

        with open(version_path, "r", encoding="utf-8") as f:
            version_data = json.load(f)
        current_version = version_data.get("version", "0.0.0")

        # Read installed version
        installed_version = None
        if os.path.exists(install_info_path):
            try:
                with open(install_info_path, "r", encoding="utf-8") as f:
                    install_data = json.load(f)
                installed_version = install_data.get("version", None)
            except (json.JSONDecodeError, OSError):
                installed_version = None

        # Decide whether to update
        if not force and installed_version == current_version:
            return

        if force:
            print("  [check_update] Force update requested.")
        else:
            print(f"  [check_update] Version mismatch: installed={installed_version}, current={current_version}")
            print("  [check_update] Updating dependencies...")

        # Run pip install
        if not os.path.exists(requirements_path):
            print("  [check_update] WARNING: requirements.txt not found, skipping.")
            return

        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", requirements_path, "--quiet"],
            cwd=script_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print("  [check_update] WARNING: pip install had issues, but continuing.")
            if result.stderr:
                print(f"  {result.stderr.strip()[:200]}")
            # Do NOT update install_info.json on failure so it retries next launch
            return
        else:
            print("  [check_update] Dependencies updated successfully.")

        # Write/update install_info.json only after successful pip install
        install_data = {}
        if os.path.exists(install_info_path):
            try:
                with open(install_info_path, "r", encoding="utf-8") as f:
                    install_data = json.load(f)
            except (json.JSONDecodeError, OSError):
                install_data = {}

        install_data["version"] = current_version
        install_data["install_date"] = datetime.datetime.now().isoformat()
        install_data["python_path"] = sys.executable
        install_data["install_dir"] = os.path.abspath(script_dir)
        with open(install_info_path, "w", encoding="utf-8") as f:
            json.dump(install_data, f, indent=2)

    except Exception as e:
        print(f"  [check_update] WARNING: {e}")


if __name__ == "__main__":
    main()
