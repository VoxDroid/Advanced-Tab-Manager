import requests
from packaging import version
from PyQt6.QtCore import QThread, pyqtSignal

CURRENT_VERSION = "1.3.0"
GITHUB_REPO = "VoxDroid/Advanced-Tab-Manager"

class VersionChecker(QThread):
    update_available = pyqtSignal(str, str)  # Emits new_version, release_url
    error_occurred = pyqtSignal(str)        # Emits error message

    def __init__(self):
        super().__init__()
        self.current_version = CURRENT_VERSION
        self.github_repo = GITHUB_REPO

    def run(self):
        """Check for updates from GitHub releases."""
        try:
            url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            latest_version = data["tag_name"].lstrip("v")
            release_url = data["html_url"]
            if version.parse(latest_version) > version.parse(self.current_version):
                self.update_available.emit(latest_version, release_url)
        except requests.exceptions.ConnectionError:
            self.error_occurred.emit("No internet connection. Update check failed.")
        except requests.exceptions.RequestException as e:
            self.error_occurred.emit(f"Failed to check for updates: {str(e)}")

    def check_for_updates(self):
        """Check for updates from GitHub releases synchronously."""
        try:
            url = f"https://api.github.com/repos/{self.github_repo}/releases/latest"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            latest_version = data["tag_name"].lstrip("v")
            release_url = data["html_url"]
            if version.parse(latest_version) > version.parse(self.current_version):
                return latest_version, release_url
        except requests.exceptions.ConnectionError:
            return None, "No internet connection. Update check failed."
        except requests.exceptions.RequestException as e:
            return None, f"Failed to check for updates: {str(e)}"
        return None, None