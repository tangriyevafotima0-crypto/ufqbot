"""
Update checker module for Video Analyzer.
Checks GitHub releases API for new versions and provides update information.
"""

import json
import os
import urllib.request
import urllib.error


class UpdateChecker:
    """Checks for application updates via GitHub releases API."""

    def __init__(self):
        version_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'version.json'
        )
        with open(version_path, 'r', encoding='utf-8') as f:
            self._version_info = json.load(f)

        self._current_version = self._version_info.get("version", "0.0.0")
        self._update_url = self._version_info.get("update_url", "")

    def get_current_version(self):
        """Return the current application version string."""
        return self._current_version

    def compare_versions(self, v1, v2):
        """
        Compare two semver version strings.

        Returns:
            -1 if v1 < v2
             0 if v1 == v2
             1 if v1 > v2
        """
        parts1 = [int(x) for x in v1.strip().split('.')]
        parts2 = [int(x) for x in v2.strip().split('.')]

        # Pad shorter version with zeros
        while len(parts1) < 3:
            parts1.append(0)
        while len(parts2) < 3:
            parts2.append(0)

        for a, b in zip(parts1, parts2):
            if a < b:
                return -1
            elif a > b:
                return 1
        return 0

    def check_for_update(self):
        """
        Check GitHub releases API for available updates.

        Returns:
            dict with keys:
                - available (bool): whether an update is available
                - current_version (str): current local version
                - latest_version (str or None): latest remote version
                - download_url (str or None): URL to download the update
                - changelog (list or None): list of changes in the new version
                - error (str or None): error message if check failed
        """
        result = {
            "available": False,
            "current_version": self._current_version,
            "latest_version": None,
            "download_url": None,
            "changelog": None,
            "error": None,
        }

        if not self._update_url:
            result["error"] = "No update URL configured"
            return result

        try:
            req = urllib.request.Request(
                self._update_url,
                headers={"User-Agent": "VideoAnalyzer-UpdateChecker"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))

            # Parse version from tag_name (strip leading 'v' if present)
            tag = data.get("tag_name", "")
            latest_version = tag.lstrip("v")

            if not latest_version:
                result["error"] = "Could not parse version from release tag"
                return result

            result["latest_version"] = latest_version

            # Compare versions
            cmp = self.compare_versions(self._current_version, latest_version)
            if cmp < 0:
                result["available"] = True
                result["download_url"] = data.get("html_url", "")

                # Try to parse changelog from release body
                body = data.get("body", "")
                if body:
                    lines = [
                        line.lstrip("- ").strip()
                        for line in body.strip().split("\n")
                        if line.strip() and not line.startswith("#")
                    ]
                    result["changelog"] = lines if lines else None

        except urllib.error.URLError as e:
            result["error"] = f"Network error: {e.reason}"
        except urllib.error.HTTPError as e:
            result["error"] = f"HTTP error {e.code}: {e.reason}"
        except json.JSONDecodeError:
            result["error"] = "Invalid response from update server"
        except OSError as e:
            result["error"] = f"Connection error: {e}"
        except Exception as e:
            result["error"] = f"Unexpected error: {e}"

        return result
