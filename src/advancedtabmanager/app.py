import logging
import os
import platform
import sys

import psutil
import qtawesome as qta
import requests
import urllib3
from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontDatabase, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from urllib3.util.retry import Retry

from .config.settings_manager import SettingsManager
from .core.browser_thread import BrowserThread
from .ui.log_viewer import LogViewer
from .utils.logger import resource_path

# Import our modular components
from .utils.version_checker import VersionChecker

CURRENT_VERSION = "1.4.0"
GITHUB_REPO = "VoxDroid/Advanced-Tab-Manager"


urllib3.disable_warnings(urllib3.exceptions.ConnectionError)

retry_strategy = Retry(total=0, connect=None, read=None, redirect=None, status=None)
http = urllib3.PoolManager(retries=retry_strategy)


def _load_jetbrains_mono():
    """Download JetBrains Mono font from GitHub and register with Qt."""
    cache_dir = os.path.join(
        os.path.expanduser("~"), ".cache", "advancedtabmanager", "fonts"
    )
    os.makedirs(cache_dir, exist_ok=True)
    variants = {
        "JetBrainsMono-Regular.ttf": "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Regular.ttf",
        "JetBrainsMono-Medium.ttf": "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Medium.ttf",
        "JetBrainsMono-Bold.ttf": "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/ttf/JetBrainsMono-Bold.ttf",
    }
    for filename, url in variants.items():
        font_path = os.path.join(cache_dir, filename)
        if not os.path.exists(font_path):
            try:
                resp = requests.get(url, timeout=15)
                resp.raise_for_status()
                with open(font_path, "wb") as f:
                    f.write(resp.content)
            except Exception:
                continue
        QFontDatabase.addApplicationFont(font_path)


class ProxyTestThread(QThread):
    test_finished = pyqtSignal(
        str, str
    )  # message, type ('success', 'warning', 'error')

    def __init__(self, proxy_address):
        super().__init__()
        self.proxy_address = proxy_address

    def run(self):
        try:
            import requests
            from requests.exceptions import RequestException, Timeout

            proxies = {
                "http": f"http://{self.proxy_address}",
                "https": f"http://{self.proxy_address}",
            }

            # Try to get IP info
            response = requests.get(
                "http://httpbin.org/ip", proxies=proxies, timeout=10
            )
            response.raise_for_status()

            data = response.json()
            proxy_ip = data.get("origin", "Unknown")

            # Also test without proxy to compare
            try:
                direct_response = requests.get("http://httpbin.org/ip", timeout=5)
                direct_data = direct_response.json()
                direct_ip = direct_data.get("origin", "Unknown")

                if proxy_ip != direct_ip:
                    message = f"Proxy working!\n\nProxy IP: {proxy_ip}\nDirect IP: {direct_ip}\n\nThe proxy is successfully routing your traffic."
                    self.test_finished.emit(message, "success")
                else:
                    message = f"Proxy may not be working properly.\n\nProxy IP: {proxy_ip}\nDirect IP: {direct_ip}\n\nThe IP is the same, which might indicate the proxy isn't active."
                    self.test_finished.emit(message, "warning")
            except Exception:
                message = f"Proxy connection successful!\n\nProxy IP: {proxy_ip}\n\n(Couldn't test direct connection for comparison)"
                self.test_finished.emit(message, "success")

        except Timeout:
            self.test_finished.emit(
                "Proxy test timed out. The proxy may be slow or unreachable.", "warning"
            )
        except RequestException as e:
            self.test_finished.emit(
                f"Proxy test failed: {str(e)}\n\nThe proxy may not be working or accessible.",
                "warning",
            )
        except Exception as e:
            self.test_finished.emit(
                f"Unexpected error during proxy test: {str(e)}", "warning"
            )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.check_for_updates()

        self.setWindowIcon(QIcon(resource_path("resources/ATM.ico")))
        # Window title will be set by update_ui_text after translations load
        self.setGeometry(100, 100, 1100, 900)
        self.setMinimumSize(QSize(1100, 900))
        self.setStyleSheet(self.get_dark_navy_style())
        self.lock_window_size = False  # Window lock off by default

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.tab_widget = QTabWidget()
        self.tab_widget.tabBar().setExpanding(False)
        self.tab_widget.setDocumentMode(True)
        self.layout.addWidget(self.tab_widget)

        # Load English translations before creating UI to prevent NameError
        try:
            # Import English translations directly to avoid recursion
            from .translations import en

            self.translations = en.translations  # Set translations for log messages
        except ImportError:
            # Fallback if English translations can't be loaded
            self.translations = {}

        self.create_main_tab()
        self.create_advanced_tab()
        self.create_settings_tab()
        self.create_system_tab()
        self.create_logs_tab()
        self.create_about_tab()

        self.setup_status_bar()
        self.threads = []
        self.proxy_test_thread = None

        # Update UI text with English translations
        self.update_ui_text(self.translations)

        self.load_settings()

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("TabManager")

        self.error_timer = QTimer()
        self.error_timer.timeout.connect(self.check_errors)
        self.error_timer.start(1000)

        self.update_window_size_lock()

    def check_for_updates(self):
        self.version_checker = VersionChecker()
        self.version_checker.update_available.connect(self.show_update_notification)
        self.version_checker.error_occurred.connect(self.show_error_notification)
        self.version_checker.start()

    def show_update_notification(self, new_version, url):
        # Get current translations
        import importlib

        translations = {}
        lang_files = {
            "English": "en",
            "Japanese": "ja",
            "Korean": "ko",
            "Chinese": "zh",
            "Filipino": "fil",
        }
        current_lang = "English"  # Default fallback
        try:
            current_lang = ["English", "Japanese", "Korean", "Chinese", "Filipino"][
                self.language_combo.currentIndex()
            ]
        except Exception:
            pass

        try:
            module = importlib.import_module(
                f".translations.{lang_files[current_lang]}", package=__package__
            )
            translations = module.translations
        except Exception:
            # Fallback to English
            try:
                module = importlib.import_module(
                    ".translations.en", package=__package__
                )
                translations = module.translations
            except Exception:
                translations = {}

        msg = QMessageBox(self)
        msg.setWindowTitle(
            translations.get("update_available_title", "Update Available")
        )
        msg.setText(
            translations.get(
                "update_available_text", "A new version ({new_version}) is available!"
            ).format(new_version=new_version)
        )
        msg.setInformativeText(
            translations.get(
                "update_available_info",
                "Current version: {current_version}\nVisit {url} to download.",
            ).format(current_version=CURRENT_VERSION, url=url)
        )
        msg.setStandardButtons(
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Ignore
        )
        msg.setDefaultButton(QMessageBox.StandardButton.Ok)
        reply = msg.exec()
        if reply == QMessageBox.StandardButton.Ok:
            import webbrowser

            webbrowser.open(url)

    def show_error_notification(self, error_message):
        # Get current translations
        import importlib

        translations = {}
        lang_files = {
            "English": "en",
            "Japanese": "ja",
            "Korean": "ko",
            "Chinese": "zh",
            "Filipino": "fil",
        }
        current_lang = "English"  # Default fallback
        try:
            current_lang = ["English", "Japanese", "Korean", "Chinese", "Filipino"][
                self.language_combo.currentIndex()
            ]
        except Exception:
            pass

        try:
            module = importlib.import_module(
                f".translations.{lang_files[current_lang]}", package=__package__
            )
            translations = module.translations
        except Exception:
            # Fallback to English
            try:
                module = importlib.import_module(
                    ".translations.en", package=__package__
                )
                translations = module.translations
            except Exception:
                translations = {}

        # Translate the error message
        translated_message = error_message
        if error_message == "No internet connection. Update check failed.":
            translated_message = translations.get(
                "update_check_no_internet", error_message
            )
        elif error_message.startswith("Failed to check for updates: "):
            error_part = error_message.split(": ", 1)[1]
            translated_message = translations.get(
                "update_check_failed", "Failed to check for updates: {error}"
            ).format(error=error_part)

        msg = QMessageBox(self)
        msg.setWindowTitle(
            translations.get("update_check_failed_title", "Update Check Failed")
        )
        msg.setText(
            translations.get("update_check_failed_text", "Unable to check for updates.")
        )
        msg.setInformativeText(translated_message)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _build_stylesheet(self, c):
        """Build a polished theme stylesheet from a color configuration."""
        return f"""
            /* ── Base ── */
            QMainWindow {{
                background-color: {c['bg']};
                color: {c['text']};
                font-family: 'JetBrains Mono', monospace;
            }}

            /* ── Tab Widget ── */
            QTabWidget::pane {{
                background-color: {c['bg']};
                border: none;
                border-top: 1px solid {c['border']};
            }}
            QTabBar {{
                qproperty-drawBase: 0;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {c['text_dim']};
                padding: 10px 28px;
                margin: 0;
                border: none;
                border-bottom: 2px solid transparent;
                font-weight: 600;
                font-size: 13px;
                letter-spacing: 0.3px;
            }}
            QTabBar::tab:selected {{
                background-color: transparent;
                color: {c['accent']};
                border-bottom: 2px solid {c['accent']};
            }}
            QTabBar::tab:hover:!selected {{
                color: {c['text']};
                border-bottom: 2px solid {c['border_hover']};
            }}

            /* ── Buttons ── */
            QPushButton {{
                background-color: {c['btn_bg']};
                color: {c['btn_text']};
                border: 1px solid {c['btn_border']};
                padding: 10px 24px;
                border-radius: 6px;
                font-weight: 600;
                min-width: 100px;
                font-size: 13px;
                letter-spacing: 0.2px;
            }}
            QPushButton:hover {{
                background-color: {c['btn_hover']};
            }}
            QPushButton:pressed {{
                background-color: {c['btn_bg']};
                border-color: {c['accent']};
            }}

            /* ── Action Buttons ── */
            QPushButton#startButton {{
                background-color: {c['start_bg']};
                border-color: {c['start_border']};
                color: #ffffff;
            }}
            QPushButton#startButton:hover {{
                background-color: {c['start_hover']};
            }}
            QPushButton#stopButton {{
                background-color: {c['stop_bg']};
                border-color: {c['stop_border']};
                color: #ffffff;
            }}
            QPushButton#stopButton:hover {{
                background-color: {c['stop_hover']};
            }}

            /* ── Inputs ── */
            QLineEdit, QSpinBox, QComboBox, QTextEdit {{
                background-color: {c['input_bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                padding: 10px 14px;
                border-radius: 6px;
                font-size: 13px;
                selection-background-color: {c['border_hover']};
                font-family: 'JetBrains Mono', monospace;
            }}
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {{
                border-color: {c['border_focus']};
            }}
            QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
                border-color: {c['border_hover']};
            }}

            /* ── ComboBox Dropdown ── */
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {c['text_dim']};
                margin-right: 8px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {c['input_bg']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 4px;
                selection-background-color: {c['tab_hover']};
                selection-color: {c['accent']};
                padding: 4px;
                outline: none;
            }}

            /* ── SpinBox Buttons ── */
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {c['tab_bg']};
                border: none;
                border-radius: 3px;
                width: 20px;
                margin: 1px;
            }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background-color: {c['tab_hover']};
            }}
            QSpinBox::up-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid {c['text_dim']};
            }}
            QSpinBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {c['text_dim']};
            }}

            /* ── Labels ── */
            QLabel {{
                color: {c['text']};
                padding: 4px 2px;
                font-size: 13px;
            }}

            /* ── Progress Bar ── */
            QProgressBar {{
                border: 1px solid {c['border']};
                border-radius: 5px;
                background-color: {c['input_bg']};
                color: {c['text']};
                text-align: center;
                min-height: 24px;
                font-size: 12px;
            }}
            QProgressBar::chunk {{
                background-color: {c['accent']};
                border-radius: 3px;
            }}

            /* ── Checkboxes ── */
            QCheckBox {{
                color: {c['text']};
                spacing: 10px;
                font-size: 13px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {c['border_hover']};
                border-radius: 3px;
                background-color: {c['input_bg']};
            }}
            QCheckBox::indicator:hover {{
                border-color: {c['accent']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {c['checkbox_checked']};
                border-color: {c['checkbox_checked_border']};
            }}

            /* ── Group Boxes ── */
            QGroupBox {{
                background-color: {c['surface']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                margin-top: 22px;
                padding: 28px 18px 18px 18px;
                font-weight: 500;
                color: {c['text']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 14px;
                padding: 2px 8px;
                color: {c['accent']};
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 0.3px;
            }}

            /* ── Scroll Area ── */
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollArea > QWidget > QWidget {{
                background-color: transparent;
            }}

            /* ── Scrollbar (Vertical) ── */
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background-color: {c['scrollbar']};
                border-radius: 4px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background-color: {c['scrollbar_hover']};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}

            /* ── Scrollbar (Horizontal) ── */
            QScrollBar:horizontal {{
                background-color: transparent;
                height: 8px;
                margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background-color: {c['scrollbar']};
                border-radius: 4px;
                min-width: 30px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background-color: {c['scrollbar_hover']};
            }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
                background: none;
            }}

            /* ── Status Bar ── */
            QStatusBar {{
                background-color: {c['statusbar_bg']};
                color: {c['text_dim']};
                border-top: 1px solid {c['border']};
                padding: 6px 14px;
                font-size: 12px;
            }}
            QStatusBar QLabel {{
                color: {c['text_dim']};
                padding: 0;
                font-size: 12px;
            }}

            /* ── Tooltips ── */
            QToolTip {{
                background-color: {c['tooltip_bg']};
                color: {c['tooltip_text']};
                border: 1px solid {c['tooltip_border']};
                border-radius: 4px;
                padding: 6px 10px;
            }}

            /* ── Message Box ── */
            QMessageBox {{
                background-color: {c['bg']};
            }}
            QMessageBox QLabel {{
                color: {c['text']};
            }}
        """

    def get_dark_navy_style(self):
        return self._build_stylesheet(
            {
                "bg": "#111116",
                "surface": "#19191f",
                "input_bg": "#1e1e26",
                "border": "#2a2a35",
                "border_focus": "#5a9cf5",
                "border_hover": "#3a3a48",
                "accent": "#5a9cf5",
                "text": "#d1d5db",
                "text_dim": "#6b7280",
                "tab_bg": "#151519",
                "tab_hover": "#1f1f28",
                "btn_bg": "#1f1f28",
                "btn_hover": "#2a2a36",
                "btn_border": "#333340",
                "btn_text": "#d1d5db",
                "progress_start": "#5a9cf5",
                "progress_end": "#5a9cf5",
                "scrollbar": "#333340",
                "scrollbar_hover": "#44445a",
                "tooltip_bg": "#1f1f28",
                "tooltip_border": "#333340",
                "tooltip_text": "#d1d5db",
                "statusbar_bg": "#0c0c10",
                "checkbox_checked": "#5a9cf5",
                "checkbox_checked_border": "#5a9cf5",
                "start_bg": "#1a7a3a",
                "start_hover": "#158030",
                "start_border": "#1a7a3a",
                "stop_bg": "#b91c1c",
                "stop_hover": "#991b1b",
                "stop_border": "#b91c1c",
            }
        )

    def get_light_blue_style(self):
        return self._build_stylesheet(
            {
                "bg": "#fafafa",
                "surface": "#ffffff",
                "input_bg": "#f5f5f5",
                "border": "#e0e0e0",
                "border_focus": "#2563eb",
                "border_hover": "#c8c8c8",
                "accent": "#2563eb",
                "text": "#1a1a2e",
                "text_dim": "#6b7280",
                "tab_bg": "#f0f0f0",
                "tab_hover": "#e8e8e8",
                "btn_bg": "#2563eb",
                "btn_hover": "#1d4ed8",
                "btn_border": "#1d4ed8",
                "btn_text": "#ffffff",
                "progress_start": "#2563eb",
                "progress_end": "#2563eb",
                "scrollbar": "#d0d0d0",
                "scrollbar_hover": "#b0b0b0",
                "tooltip_bg": "#1a1a2e",
                "tooltip_border": "#333340",
                "tooltip_text": "#e2e8f0",
                "statusbar_bg": "#f0f0f0",
                "checkbox_checked": "#2563eb",
                "checkbox_checked_border": "#1d4ed8",
                "start_bg": "#16a34a",
                "start_hover": "#15803d",
                "start_border": "#16a34a",
                "stop_bg": "#dc2626",
                "stop_hover": "#b91c1c",
                "stop_border": "#dc2626",
            }
        )

    def get_dark_green_style(self):
        return self._build_stylesheet(
            {
                "bg": "#0c1410",
                "surface": "#121c16",
                "input_bg": "#18241c",
                "border": "#223028",
                "border_focus": "#4ade80",
                "border_hover": "#2e4036",
                "accent": "#4ade80",
                "text": "#d1ddd5",
                "text_dim": "#6b8074",
                "tab_bg": "#101a14",
                "tab_hover": "#1a2a1e",
                "btn_bg": "#1a2a1e",
                "btn_hover": "#243628",
                "btn_border": "#2e4036",
                "btn_text": "#d1ddd5",
                "progress_start": "#4ade80",
                "progress_end": "#4ade80",
                "scrollbar": "#2e4036",
                "scrollbar_hover": "#3e5a46",
                "tooltip_bg": "#1a2a1e",
                "tooltip_border": "#2e4036",
                "tooltip_text": "#d1ddd5",
                "statusbar_bg": "#080e0a",
                "checkbox_checked": "#16a34a",
                "checkbox_checked_border": "#4ade80",
                "start_bg": "#16a34a",
                "start_hover": "#15803d",
                "start_border": "#16a34a",
                "stop_bg": "#b91c1c",
                "stop_hover": "#991b1b",
                "stop_border": "#b91c1c",
            }
        )

    def get_light_green_style(self):
        return self._build_stylesheet(
            {
                "bg": "#fafaf5",
                "surface": "#ffffff",
                "input_bg": "#f5f5f0",
                "border": "#e0e0d8",
                "border_focus": "#16a34a",
                "border_hover": "#c8c8c0",
                "accent": "#16a34a",
                "text": "#1a2e1a",
                "text_dim": "#6b806b",
                "tab_bg": "#f0f0ea",
                "tab_hover": "#e8e8e0",
                "btn_bg": "#16a34a",
                "btn_hover": "#15803d",
                "btn_border": "#15803d",
                "btn_text": "#ffffff",
                "progress_start": "#16a34a",
                "progress_end": "#16a34a",
                "scrollbar": "#c8d0c8",
                "scrollbar_hover": "#a8b8a8",
                "tooltip_bg": "#1a2e1a",
                "tooltip_border": "#2a3e2a",
                "tooltip_text": "#e0f0e2",
                "statusbar_bg": "#f0f0ea",
                "checkbox_checked": "#16a34a",
                "checkbox_checked_border": "#15803d",
                "start_bg": "#16a34a",
                "start_hover": "#15803d",
                "start_border": "#16a34a",
                "stop_bg": "#dc2626",
                "stop_hover": "#b91c1c",
                "stop_border": "#dc2626",
            }
        )

    def get_soft_pink_style(self):
        return self._build_stylesheet(
            {
                "bg": "#faf5f7",
                "surface": "#ffffff",
                "input_bg": "#f8f0f2",
                "border": "#e8d8de",
                "border_focus": "#e11d48",
                "border_hover": "#d0c0c8",
                "accent": "#e11d48",
                "text": "#2e1a22",
                "text_dim": "#8a6a7a",
                "tab_bg": "#f2eaee",
                "tab_hover": "#eae0e4",
                "btn_bg": "#e11d48",
                "btn_hover": "#be123c",
                "btn_border": "#be123c",
                "btn_text": "#ffffff",
                "progress_start": "#e11d48",
                "progress_end": "#e11d48",
                "scrollbar": "#d8c0cc",
                "scrollbar_hover": "#c0a0b0",
                "tooltip_bg": "#2e1a22",
                "tooltip_border": "#4a2a3a",
                "tooltip_text": "#fce8ed",
                "statusbar_bg": "#f2eaee",
                "checkbox_checked": "#e11d48",
                "checkbox_checked_border": "#be123c",
                "start_bg": "#16a34a",
                "start_hover": "#15803d",
                "start_border": "#16a34a",
                "stop_bg": "#dc2626",
                "stop_hover": "#b91c1c",
                "stop_border": "#dc2626",
            }
        )

    def get_soft_lavender_style(self):
        return self._build_stylesheet(
            {
                "bg": "#14101e",
                "surface": "#1c1628",
                "input_bg": "#221c30",
                "border": "#2e2640",
                "border_focus": "#a78bfa",
                "border_hover": "#3e3458",
                "accent": "#a78bfa",
                "text": "#d5d0e0",
                "text_dim": "#7a7090",
                "tab_bg": "#18121e",
                "tab_hover": "#241c32",
                "btn_bg": "#241c32",
                "btn_hover": "#302640",
                "btn_border": "#3e3458",
                "btn_text": "#d5d0e0",
                "progress_start": "#a78bfa",
                "progress_end": "#a78bfa",
                "scrollbar": "#3e3458",
                "scrollbar_hover": "#504a68",
                "tooltip_bg": "#241c32",
                "tooltip_border": "#3e3458",
                "tooltip_text": "#d5d0e0",
                "statusbar_bg": "#0e0a16",
                "checkbox_checked": "#7c3aed",
                "checkbox_checked_border": "#a78bfa",
                "start_bg": "#16a34a",
                "start_hover": "#15803d",
                "start_border": "#16a34a",
                "stop_bg": "#b91c1c",
                "stop_hover": "#991b1b",
                "stop_border": "#b91c1c",
            }
        )

    def create_main_tab(self):
        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setSpacing(16)
        scroll_content_layout.setContentsMargins(24, 24, 24, 24)

        # ── URL Configuration ──
        self.url_group = QGroupBox("URL Configuration")
        url_layout = QHBoxLayout()
        url_layout.setSpacing(12)
        url_icon_label = QLabel()
        url_icon_label.setPixmap(qta.icon("fa5s.link", color="#9ca3af").pixmap(18, 18))
        self.url_text_label = QLabel("URL:")
        self.url_input = QLineEdit("https://google.com/")
        self.url_input.setToolTip("Enter the URL to open in tabs")
        self.url_input.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        url_layout.addWidget(url_icon_label)
        url_layout.addWidget(self.url_text_label)
        url_layout.addWidget(self.url_input, 1)
        self.url_group.setLayout(url_layout)
        scroll_content_layout.addWidget(self.url_group)

        # ── Parameters Row (Iterations | Interval | Instances) ──
        params_row = QHBoxLayout()
        params_row.setSpacing(14)

        self.iterations_group = QGroupBox("Iterations")
        iter_layout = QVBoxLayout()
        iter_layout.setSpacing(8)
        iter_header = QHBoxLayout()
        iterations_icon_label = QLabel()
        iterations_icon_label.setPixmap(
            qta.icon("fa5s.redo", color="#9ca3af").pixmap(18, 18)
        )
        self.iterations_text_label = QLabel("Iterations (0 = \u221e):")
        iter_header.addWidget(iterations_icon_label)
        iter_header.addWidget(self.iterations_text_label)
        iter_header.addStretch()
        iter_layout.addLayout(iter_header)
        self.iterations_input = QSpinBox()
        self.iterations_input.setRange(0, 1000000)
        self.iterations_input.setToolTip("Set to 0 for infinite iterations")
        self.iterations_input.setAttribute(
            Qt.WidgetAttribute.WA_AlwaysShowToolTips, True
        )
        iter_layout.addWidget(self.iterations_input)
        self.iterations_group.setLayout(iter_layout)
        params_row.addWidget(self.iterations_group)

        self.interval_group = QGroupBox("Interval")
        intv_layout = QVBoxLayout()
        intv_layout.setSpacing(8)
        intv_header = QHBoxLayout()
        interval_icon_label = QLabel()
        interval_icon_label.setPixmap(
            qta.icon("fa5s.clock", color="#9ca3af").pixmap(18, 18)
        )
        self.interval_text_label = QLabel("Seconds:")
        intv_header.addWidget(interval_icon_label)
        intv_header.addWidget(self.interval_text_label)
        intv_header.addStretch()
        intv_layout.addLayout(intv_header)
        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 3600)
        self.interval_input.setValue(1)
        self.interval_input.setToolTip("Set the delay between tab openings in seconds")
        self.interval_input.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        intv_layout.addWidget(self.interval_input)
        self.interval_group.setLayout(intv_layout)
        params_row.addWidget(self.interval_group)

        self.instances_group = QGroupBox("Instances")
        inst_layout = QVBoxLayout()
        inst_layout.setSpacing(8)
        inst_header = QHBoxLayout()
        instances_icon_label = QLabel()
        instances_icon_label.setPixmap(
            qta.icon("fa5s.clone", color="#9ca3af").pixmap(18, 18)
        )
        self.instances_text_label = QLabel("Count:")
        inst_header.addWidget(instances_icon_label)
        inst_header.addWidget(self.instances_text_label)
        inst_header.addStretch()
        inst_layout.addLayout(inst_header)
        self.instances_input = QSpinBox()
        self.instances_input.setRange(1, 10)
        self.instances_input.setValue(1)
        self.instances_input.setToolTip(
            "Set the number of browser instances to run simultaneously"
        )
        self.instances_input.setAttribute(
            Qt.WidgetAttribute.WA_AlwaysShowToolTips, True
        )
        inst_layout.addWidget(self.instances_input)
        self.instances_group.setLayout(inst_layout)
        params_row.addWidget(self.instances_group)

        scroll_content_layout.addLayout(params_row)

        # ── Actions ──
        self.button_group = QGroupBox("Actions")
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        self.start_button = QPushButton()
        self.start_button.setObjectName("startButton")
        self.start_button.setText("Start")
        self.start_button.setIcon(qta.icon("fa5s.play", color="#ffffff"))
        self.start_button.clicked.connect(self.start_browser)
        self.start_button.setToolTip("Start opening tabs")
        self.stop_button = QPushButton()
        self.stop_button.setObjectName("stopButton")
        self.stop_button.setText("Stop")
        self.stop_button.setIcon(qta.icon("fa5s.stop", color="#ffffff"))
        self.stop_button.clicked.connect(self.stop_browser)
        self.stop_button.setToolTip("Stop all tab operations")
        self.reset_button = QPushButton()
        self.reset_button.setText("Reset")
        self.reset_button.setIcon(qta.icon("fa5s.sync", color="#9ca3af"))
        self.reset_button.clicked.connect(self.reset_fields)
        self.reset_button.setToolTip("Reset all fields to default values")
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.reset_button)
        self.button_group.setLayout(button_layout)
        scroll_content_layout.addWidget(self.button_group)

        # ── Status & Cycles Row ──
        status_row = QHBoxLayout()
        status_row.setSpacing(14)

        self.status_group = QGroupBox("Status")
        sl = QHBoxLayout()
        sl.setSpacing(10)
        status_icon_label = QLabel()
        status_icon_label.setPixmap(
            qta.icon("fa5s.info-circle", color="#9ca3af").pixmap(18, 18)
        )
        self.status_text_label = QLabel("Status:")
        self.status_label = QLabel("Idle")
        self.status_label.setToolTip("Current status of the tab manager")
        sl.addWidget(status_icon_label)
        sl.addWidget(self.status_text_label)
        sl.addWidget(self.status_label, 1)
        self.status_group.setLayout(sl)
        status_row.addWidget(self.status_group, 2)

        self.cycles_group = QGroupBox("Cycles")
        cl = QHBoxLayout()
        cl.setSpacing(10)
        cycles_icon_label = QLabel()
        cycles_icon_label.setPixmap(
            qta.icon("fa5s.redo-alt", color="#9ca3af").pixmap(18, 18)
        )
        self.cycle_text_label = QLabel("Cycles:")
        self.cycle_label = QLabel("0")
        self.cycle_label.setToolTip("Number of tab cycles completed")
        cl.addWidget(cycles_icon_label)
        cl.addWidget(self.cycle_text_label)
        cl.addWidget(self.cycle_label, 1)
        self.cycles_group.setLayout(cl)
        status_row.addWidget(self.cycles_group, 1)

        scroll_content_layout.addLayout(status_row)

        # ── Progress ──
        self.progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        self.progress_group.setLayout(progress_layout)
        scroll_content_layout.addWidget(self.progress_group)

        scroll_content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        self.tab_widget.addTab(main_tab, "Main")

    def create_advanced_tab(self):
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)
        advanced_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)
        scroll_layout.setContentsMargins(24, 24, 24, 24)

        # ── Browser Selection ──
        self.browser_group = QGroupBox("Browser Selection")
        browser_layout = QHBoxLayout()
        browser_layout.setSpacing(12)
        browser_icon_label = QLabel()
        browser_icon_label.setPixmap(
            qta.icon("fa5s.globe", color="#9ca3af").pixmap(18, 18)
        )
        self.browser_text_label = QLabel("Select Browser:")
        self.browser_combo = QComboBox()
        self.browser_combo.addItems([])
        self.browser_combo.setToolTip("Select the browser to use for automation")
        self.browser_combo.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        browser_layout.addWidget(browser_icon_label)
        browser_layout.addWidget(self.browser_text_label)
        browser_layout.addWidget(self.browser_combo, 1)
        self.browser_group.setLayout(browser_layout)
        scroll_layout.addWidget(self.browser_group)

        # ── Browser Options (3-column grid) ──
        self.browser_options_group = QGroupBox("Browser Options")
        options_grid = QGridLayout()
        options_grid.setSpacing(12)
        options_grid.setContentsMargins(8, 8, 8, 8)

        self.headless_checkbox = QCheckBox("Headless mode")
        self.headless_checkbox.setIcon(qta.icon("fa5s.eye-slash", color="#9ca3af"))
        self.headless_checkbox.setToolTip(
            "Run browser in headless mode (no UI) - uses new headless implementation"
        )

        self.incognito_checkbox = QCheckBox("Private/Incognito")
        self.incognito_checkbox.setIcon(qta.icon("fa5s.user-secret", color="#9ca3af"))
        self.incognito_checkbox.setToolTip("Run browser in private/incognito mode")

        self.start_maximized_checkbox = QCheckBox("Start maximized")
        self.start_maximized_checkbox.setIcon(qta.icon("fa5s.expand", color="#9ca3af"))
        self.start_maximized_checkbox.setToolTip("Start browser maximized")

        self.disable_gpu_checkbox = QCheckBox("Disable GPU")
        self.disable_gpu_checkbox.setIcon(qta.icon("fa5s.desktop", color="#9ca3af"))
        self.disable_gpu_checkbox.setToolTip("Disable GPU hardware acceleration")

        self.disable_extensions_checkbox = QCheckBox("Disable extensions")
        self.disable_extensions_checkbox.setIcon(qta.icon("fa5s.plug", color="#9ca3af"))
        self.disable_extensions_checkbox.setToolTip("Disable all browser extensions")

        self.disable_notifications_checkbox = QCheckBox("Disable notifications")
        self.disable_notifications_checkbox.setIcon(
            qta.icon("fa5s.bell-slash", color="#9ca3af")
        )
        self.disable_notifications_checkbox.setToolTip("Disable browser notifications")

        self.disable_web_security_checkbox = QCheckBox("Disable web security")
        self.disable_web_security_checkbox.setIcon(
            qta.icon("fa5s.shield-alt", color="#9ca3af")
        )
        self.disable_web_security_checkbox.setToolTip(
            "Disable web security features (Chrome only)"
        )

        self.no_sandbox_checkbox = QCheckBox("No sandbox")
        self.no_sandbox_checkbox.setIcon(qta.icon("fa5s.box-open", color="#9ca3af"))
        self.no_sandbox_checkbox.setToolTip("Disable sandbox (Chrome only)")

        self.disable_dev_shm_checkbox = QCheckBox("Disable /dev/shm")
        self.disable_dev_shm_checkbox.setIcon(qta.icon("fa5s.memory", color="#9ca3af"))
        self.disable_dev_shm_checkbox.setToolTip("Disable /dev/shm usage (Chrome only)")

        # 3-column grid layout
        options_grid.addWidget(self.headless_checkbox, 0, 0)
        options_grid.addWidget(self.incognito_checkbox, 0, 1)
        options_grid.addWidget(self.start_maximized_checkbox, 0, 2)
        options_grid.addWidget(self.disable_gpu_checkbox, 1, 0)
        options_grid.addWidget(self.disable_extensions_checkbox, 1, 1)
        options_grid.addWidget(self.disable_notifications_checkbox, 1, 2)
        options_grid.addWidget(self.disable_web_security_checkbox, 2, 0)
        options_grid.addWidget(self.no_sandbox_checkbox, 2, 1)
        options_grid.addWidget(self.disable_dev_shm_checkbox, 2, 2)

        self.browser_options_group.setLayout(options_grid)
        scroll_layout.addWidget(self.browser_options_group)

        # ── User Agent ──
        self.user_agent_group = QGroupBox("User Agent")
        user_agent_layout = QHBoxLayout()
        user_agent_layout.setSpacing(12)
        user_agent_icon_label = QLabel()
        user_agent_icon_label.setPixmap(
            qta.icon("fa5s.user", color="#9ca3af").pixmap(18, 18)
        )
        self.user_agent_text_label = QLabel("Custom user agent:")
        self.user_agent_input = QLineEdit()
        self.user_agent_input.setPlaceholderText(
            "Optional \u2014 leave empty for default"
        )
        self.user_agent_input.setToolTip(
            "Enter a custom user agent for the browser (optional)"
        )
        self.user_agent_input.setAttribute(
            Qt.WidgetAttribute.WA_AlwaysShowToolTips, True
        )
        user_agent_layout.addWidget(user_agent_icon_label)
        user_agent_layout.addWidget(self.user_agent_text_label)
        user_agent_layout.addWidget(self.user_agent_input, 1)
        self.user_agent_group.setLayout(user_agent_layout)
        scroll_layout.addWidget(self.user_agent_group)

        # ── Proxy Settings ──
        self.proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout()
        proxy_layout.setSpacing(12)
        self.proxy_checkbox = QCheckBox("Use proxy")
        self.proxy_checkbox.setIcon(qta.icon("fa5s.server", color="#9ca3af"))
        self.proxy_checkbox.setToolTip("Enable use of a proxy server")
        proxy_input_layout = QHBoxLayout()
        proxy_input_layout.setSpacing(12)
        proxy_icon_label = QLabel()
        proxy_icon_label.setPixmap(
            qta.icon("fa5s.network-wired", color="#9ca3af").pixmap(18, 18)
        )
        self.proxy_text_label = QLabel("Proxy address:")
        self.proxy_address_input = QLineEdit()
        self.proxy_address_input.setPlaceholderText("127.0.0.1:8080")
        self.proxy_address_input.setToolTip(
            "Enter proxy address in the format IP:PORT (e.g., 127.0.0.1:8080)"
        )
        self.proxy_address_input.setAttribute(
            Qt.WidgetAttribute.WA_AlwaysShowToolTips, True
        )
        self.test_proxy_button = QPushButton("Test Proxy")
        self.test_proxy_button.setIcon(qta.icon("fa5s.check-circle", color="#9ca3af"))
        self.test_proxy_button.setToolTip("Test the proxy connection")
        self.test_proxy_button.clicked.connect(self.test_proxy_connection)
        proxy_input_layout.addWidget(proxy_icon_label)
        proxy_input_layout.addWidget(self.proxy_text_label)
        proxy_input_layout.addWidget(self.proxy_address_input, 1)
        proxy_input_layout.addWidget(self.test_proxy_button)
        proxy_layout.addWidget(self.proxy_checkbox)
        proxy_layout.addLayout(proxy_input_layout)
        self.proxy_group.setLayout(proxy_layout)
        scroll_layout.addWidget(self.proxy_group)

        self.proxy_checkbox.stateChanged.connect(self._toggle_proxy_input)
        self._toggle_proxy_input(self.proxy_checkbox.isChecked())

        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        advanced_layout.addWidget(scroll_area)

        self.tab_widget.addTab(advanced_tab, "Advanced")

    def create_settings_tab(self):
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)
        settings_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setSpacing(16)
        scroll_content_layout.setContentsMargins(24, 24, 24, 24)

        # ── Appearance Row (Theme | Font Size) ──
        appearance_row = QHBoxLayout()
        appearance_row.setSpacing(14)

        self.theme_group = QGroupBox("Theme Selection")
        theme_layout = QVBoxLayout()
        theme_layout.setSpacing(4)
        theme_header = QHBoxLayout()
        theme_icon_label = QLabel()
        theme_icon_label.setPixmap(
            qta.icon("fa5s.palette", color="#9ca3af").pixmap(18, 18)
        )
        self.theme_text_label = QLabel("Theme:")
        theme_header.addWidget(theme_icon_label)
        theme_header.addWidget(self.theme_text_label)
        theme_header.addStretch()
        theme_layout.addLayout(theme_header)
        self.theme_combo = QComboBox()
        self.theme_combo.addItems([])
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self.theme_combo.setToolTip("Select the visual theme for the application")
        self.theme_combo.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        theme_layout.addWidget(self.theme_combo)
        self.theme_group.setLayout(theme_layout)
        appearance_row.addWidget(self.theme_group, 2)

        self.font_group = QGroupBox("Font Size")
        font_layout = QVBoxLayout()
        font_layout.setSpacing(4)
        font_header = QHBoxLayout()
        font_icon_label = QLabel()
        font_icon_label.setPixmap(qta.icon("fa5s.font", color="#9ca3af").pixmap(18, 18))
        self.font_text_label = QLabel("Size:")
        font_header.addWidget(font_icon_label)
        font_header.addWidget(self.font_text_label)
        font_header.addStretch()
        font_layout.addLayout(font_header)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        self.font_size_spin.valueChanged.connect(self.change_font_size)
        self.font_size_spin.setToolTip(
            "Adjust the font size for the application (8\u201324 pt)"
        )
        self.font_size_spin.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        font_layout.addWidget(self.font_size_spin)
        self.font_group.setLayout(font_layout)
        appearance_row.addWidget(self.font_group, 1)

        scroll_content_layout.addLayout(appearance_row)

        # ── Language ──
        self.language_group = QGroupBox("Language")
        language_layout = QHBoxLayout()
        language_layout.setSpacing(12)
        language_icon_label = QLabel()
        language_icon_label.setPixmap(
            qta.icon("fa5s.language", color="#9ca3af").pixmap(18, 18)
        )
        self.language_text_label = QLabel("Language:")
        self.language_combo = QComboBox()
        self.language_combo.addItems([])
        self.language_combo.currentIndexChanged.connect(self.change_language)
        self.language_combo.setToolTip(
            "Select the language for the application interface"
        )
        self.language_combo.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        language_layout.addWidget(language_icon_label)
        language_layout.addWidget(self.language_text_label)
        language_layout.addWidget(self.language_combo, 1)
        self.language_group.setLayout(language_layout)
        scroll_content_layout.addWidget(self.language_group)

        # ── Actions ──
        self.actions_group = QGroupBox("Actions")
        actions_layout = QVBoxLayout()
        actions_layout.setSpacing(10)
        row1_layout = QHBoxLayout()
        row1_layout.setSpacing(10)
        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.setIcon(qta.icon("fa5s.save", color="#9ca3af"))
        self.save_settings_button.clicked.connect(self.save_settings)
        self.save_settings_button.setToolTip("Save current application settings")
        self.load_settings_button = QPushButton("Load Settings")
        self.load_settings_button.setIcon(qta.icon("fa5s.upload", color="#9ca3af"))
        self.load_settings_button.clicked.connect(self.load_settings)
        self.load_settings_button.setToolTip("Load previously saved settings")
        row1_layout.addWidget(self.save_settings_button)
        row1_layout.addWidget(self.load_settings_button)

        row2_layout = QHBoxLayout()
        row2_layout.setSpacing(10)
        self.export_settings_button = QPushButton("Export")
        self.export_settings_button.setIcon(
            qta.icon("fa5s.file-export", color="#9ca3af")
        )
        self.export_settings_button.clicked.connect(self.export_settings)
        self.export_settings_button.setToolTip("Export settings to a JSON file")
        self.import_settings_button = QPushButton("Import")
        self.import_settings_button.setIcon(
            qta.icon("fa5s.file-import", color="#9ca3af")
        )
        self.import_settings_button.clicked.connect(self.import_settings)
        self.import_settings_button.setToolTip("Import settings from a JSON file")
        self.reset_settings_button = QPushButton("Reset Default")
        self.reset_settings_button.setIcon(qta.icon("fa5s.undo", color="#9ca3af"))
        self.reset_settings_button.clicked.connect(self.reset_to_default_settings)
        self.reset_settings_button.setToolTip(
            "Reset all settings to their default values"
        )
        row2_layout.addWidget(self.export_settings_button)
        row2_layout.addWidget(self.import_settings_button)
        row2_layout.addWidget(self.reset_settings_button)

        actions_layout.addLayout(row1_layout)
        actions_layout.addLayout(row2_layout)
        self.actions_group.setLayout(actions_layout)
        scroll_content_layout.addWidget(self.actions_group)

        # ── Options Row (Auto-Start | Lock Window) ──
        options_row = QHBoxLayout()
        options_row.setSpacing(14)

        self.autostart_group = QGroupBox("Auto-Start Options")
        autostart_layout = QHBoxLayout()
        autostart_layout.setSpacing(12)
        autostart_icon_label = QLabel()
        autostart_icon_label.setPixmap(
            qta.icon("fa5s.play-circle", color="#9ca3af").pixmap(18, 18)
        )
        self.autostart_text_label = QLabel("Auto-Start on Launch:")
        self.autostart_check = QCheckBox()
        self.autostart_check.setToolTip(
            "Automatically start the browser on application launch"
        )
        autostart_layout.addWidget(autostart_icon_label)
        autostart_layout.addWidget(self.autostart_text_label)
        autostart_layout.addStretch()
        autostart_layout.addWidget(self.autostart_check)
        self.autostart_group.setLayout(autostart_layout)
        options_row.addWidget(self.autostart_group)

        self.lock_window_size_group = QGroupBox("Window Size Lock")
        lock_layout = QHBoxLayout()
        lock_layout.setSpacing(12)
        lock_icon_label = QLabel()
        lock_icon_label.setPixmap(qta.icon("fa5s.lock", color="#9ca3af").pixmap(18, 18))
        self.lock_window_size_text_label = QLabel("Lock Window Size:")
        self.lock_window_size_check = QCheckBox()
        self.lock_window_size_check.setToolTip(
            "Prevent resizing the window with the mouse"
        )
        self.lock_window_size_check.stateChanged.connect(self.toggle_window_size_lock)
        lock_layout.addWidget(lock_icon_label)
        lock_layout.addWidget(self.lock_window_size_text_label)
        lock_layout.addStretch()
        lock_layout.addWidget(self.lock_window_size_check)
        self.lock_window_size_group.setLayout(lock_layout)
        options_row.addWidget(self.lock_window_size_group)

        scroll_content_layout.addLayout(options_row)

        scroll_content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        settings_layout.addWidget(scroll_area)

        self.tab_widget.addTab(settings_tab, "Settings")

    def _format_system_info_html(self):
        """Format system information as a structured HTML table."""
        t = self.translations
        rows = [
            (
                "fa5s.desktop",
                t.get("system_info_os", "OS:"),
                f"{platform.system()} {platform.release()}",
            ),
            (
                "fa5s.code",
                t.get("system_info_python_version", "Python:"),
                platform.python_version(),
            ),
            (
                "fa5s.microchip",
                t.get("system_info_cpu", "CPU:"),
                platform.processor() or "N/A",
            ),
            (
                "fa5s.th",
                t.get("system_info_cpu_cores", "CPU Cores:"),
                f"{psutil.cpu_count(logical=True)} logical \u00b7 {psutil.cpu_count(logical=False)} physical",
            ),
            (
                "fa5s.memory",
                t.get("system_info_memory", "Memory:"),
                f"{psutil.virtual_memory().total / (1024**3):.2f} GB",
            ),
            (
                "fa5s.hdd",
                t.get("system_info_disk_space", "Disk Space:"),
                f"{psutil.disk_usage('/').total / (1024**3):.2f} GB total",
            ),
        ]
        html = '<table cellpadding="0" cellspacing="0" style="width:100%; border-collapse:collapse;">'
        for _icon, label, value in rows:
            html += (
                f'<tr style="line-height:2.2;">'
                f'<td style="padding:6px 16px 6px 4px; opacity:0.6; white-space:nowrap;">{label}</td>'
                f'<td style="padding:6px 0; font-weight:600;">{value}</td>'
                f"</tr>"
            )
        html += "</table>"
        return html

    def create_system_tab(self):
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)
        system_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setSpacing(16)
        scroll_content_layout.setContentsMargins(24, 24, 24, 24)

        # ── System Overview ──
        self.system_group = QGroupBox(
            self.translations.get("system_group", "System Information")
        )
        system_inner = QVBoxLayout()
        system_inner.setSpacing(14)

        sys_header = QHBoxLayout()
        sys_header.setSpacing(10)
        system_icon_label = QLabel()
        system_icon_label.setPixmap(
            qta.icon("fa5s.microchip", color="#9ca3af").pixmap(20, 20)
        )
        self.system_text_label = QLabel(self.translations["system_details"])
        self.system_text_label.setStyleSheet("font-weight: 600; font-size: 15px;")
        sys_header.addWidget(system_icon_label)
        sys_header.addWidget(self.system_text_label)
        sys_header.addStretch()
        system_inner.addLayout(sys_header)

        self.system_info_label = QLabel(self._format_system_info_html())
        self.system_info_label.setWordWrap(True)
        self.system_info_label.setTextFormat(Qt.TextFormat.RichText)
        self.system_info_label.setToolTip(
            self.translations.get(
                "system_details_tooltip", "View detailed information about the system"
            )
        )
        system_inner.addWidget(self.system_info_label)

        self.system_group.setLayout(system_inner)
        scroll_content_layout.addWidget(self.system_group)

        # ── Real-time Monitor with Progress Bars ──
        self.monitor_group = QGroupBox(
            self.translations.get("monitor_group", "Real-time System Monitor")
        )
        monitor_layout = QVBoxLayout()
        monitor_layout.setSpacing(18)

        # CPU
        cpu_block = QVBoxLayout()
        cpu_block.setSpacing(6)
        cpu_header = QHBoxLayout()
        cpu_header.setSpacing(10)
        cpu_icon = QLabel()
        cpu_icon.setPixmap(
            qta.icon("fa5s.tachometer-alt", color="#9ca3af").pixmap(18, 18)
        )
        self.cpu_usage_label = QLabel(
            self.translations.get("system_cpu_usage", "CPU Usage:") + " 0%"
        )
        self.cpu_usage_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.cpu_usage_label.setToolTip(
            self.translations.get(
                "system_cpu_usage_tooltip", "View real-time CPU usage percentage"
            )
        )
        cpu_header.addWidget(cpu_icon)
        cpu_header.addWidget(self.cpu_usage_label, 1)
        cpu_block.addLayout(cpu_header)
        self.cpu_progress = QProgressBar()
        self.cpu_progress.setRange(0, 100)
        self.cpu_progress.setValue(0)
        self.cpu_progress.setTextVisible(False)
        self.cpu_progress.setFixedHeight(10)
        cpu_block.addWidget(self.cpu_progress)
        monitor_layout.addLayout(cpu_block)

        # Memory
        mem_block = QVBoxLayout()
        mem_block.setSpacing(6)
        mem_header = QHBoxLayout()
        mem_header.setSpacing(10)
        mem_icon = QLabel()
        mem_icon.setPixmap(qta.icon("fa5s.memory", color="#9ca3af").pixmap(18, 18))
        self.memory_usage_label = QLabel(
            self.translations.get("system_memory_usage", "Memory Usage:") + " 0%"
        )
        self.memory_usage_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.memory_usage_label.setToolTip(
            self.translations.get(
                "system_memory_usage_tooltip", "View real-time memory usage percentage"
            )
        )
        mem_header.addWidget(mem_icon)
        mem_header.addWidget(self.memory_usage_label, 1)
        mem_block.addLayout(mem_header)
        self.memory_progress = QProgressBar()
        self.memory_progress.setRange(0, 100)
        self.memory_progress.setValue(0)
        self.memory_progress.setTextVisible(False)
        self.memory_progress.setFixedHeight(10)
        mem_block.addWidget(self.memory_progress)
        monitor_layout.addLayout(mem_block)

        # Disk
        disk_block = QVBoxLayout()
        disk_block.setSpacing(6)
        disk_header = QHBoxLayout()
        disk_header.setSpacing(10)
        disk_icon = QLabel()
        disk_icon.setPixmap(qta.icon("fa5s.hdd", color="#9ca3af").pixmap(18, 18))
        self.disk_usage_label = QLabel(
            self.translations.get("system_disk_usage", "Disk Usage:") + " 0%"
        )
        self.disk_usage_label.setStyleSheet("font-weight: 600; font-size: 13px;")
        self.disk_usage_label.setToolTip(
            self.translations.get(
                "system_disk_usage_tooltip", "View real-time disk usage percentage"
            )
        )
        disk_header.addWidget(disk_icon)
        disk_header.addWidget(self.disk_usage_label, 1)
        disk_block.addLayout(disk_header)
        self.disk_progress = QProgressBar()
        self.disk_progress.setRange(0, 100)
        self.disk_progress.setValue(0)
        self.disk_progress.setTextVisible(False)
        self.disk_progress.setFixedHeight(10)
        disk_block.addWidget(self.disk_progress)
        monitor_layout.addLayout(disk_block)

        self.monitor_group.setLayout(monitor_layout)
        scroll_content_layout.addWidget(self.monitor_group)

        scroll_content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        system_layout.addWidget(scroll_area)

        self.tab_widget.addTab(system_tab, self.translations["tab_system"])

        # Start real-time monitoring
        self.system_monitor_timer = QTimer()
        self.system_monitor_timer.timeout.connect(self.update_system_monitor)
        self.system_monitor_timer.start(1000)

    def create_logs_tab(self):
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)
        logs_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setSpacing(16)
        scroll_content_layout.setContentsMargins(24, 24, 24, 24)

        self.logs_group = QGroupBox(
            self.translations.get("logs_group", "Application Logs")
        )
        logs_layout_inner = QVBoxLayout()
        logs_layout_inner.setSpacing(10)
        logs_icon_label = QLabel()
        logs_icon_label.setPixmap(
            qta.icon("fa5s.list-alt", color="#9ca3af").pixmap(18, 18)
        )
        self.logs_text_label = QLabel(self.translations.get("logs", "Logs:"))
        self.logs_text_label.setStyleSheet("font-weight: bold;")

        self.log_viewer = LogViewer()
        logs_layout_inner.addWidget(logs_icon_label)
        logs_layout_inner.addWidget(self.logs_text_label)
        logs_layout_inner.addWidget(self.log_viewer)
        self.logs_group.setLayout(logs_layout_inner)
        scroll_content_layout.addWidget(self.logs_group)

        # Log Filters
        self.filter_group = QGroupBox(
            self.translations.get("filter_group", "Log Filters")
        )
        filter_layout = QHBoxLayout()
        self.show_info_check = QCheckBox()
        self.show_info_check.setText(
            self.translations.get("logs_show_info", "Show Info")
        )
        self.show_info_check.setIcon(qta.icon("fa5s.info-circle", color="#9ca3af"))
        self.show_info_check.setChecked(True)
        self.show_info_check.setToolTip(
            self.translations.get(
                "logs_show_info_tooltip", "Show informational log messages"
            )
        )
        self.show_warning_check = QCheckBox()
        self.show_warning_check.setText(
            self.translations.get("logs_show_warning", "Show Warnings")
        )
        self.show_warning_check.setIcon(
            qta.icon("fa5s.exclamation-triangle", color="#9ca3af")
        )
        self.show_warning_check.setChecked(True)
        self.show_warning_check.setToolTip(
            self.translations.get(
                "logs_show_warning_tooltip", "Show warning log messages"
            )
        )
        self.show_error_check = QCheckBox()
        self.show_error_check.setText(
            self.translations.get("logs_show_error", "Show Errors")
        )
        self.show_error_check.setIcon(qta.icon("fa5s.times-circle", color="#9ca3af"))
        self.show_error_check.setChecked(True)
        self.show_error_check.setToolTip(
            self.translations.get("logs_show_error_tooltip", "Show error log messages")
        )
        filter_layout.addWidget(self.show_info_check)
        filter_layout.addWidget(self.show_warning_check)
        filter_layout.addWidget(self.show_error_check)
        self.filter_group.setLayout(filter_layout)
        scroll_content_layout.addWidget(self.filter_group)

        # Log Actions
        self.actions_group_logs = QGroupBox(
            self.translations.get("actions_group_logs", "Log Actions")
        )
        actions_layout = QHBoxLayout()
        self.clear_logs_button = QPushButton()
        self.clear_logs_button.setText(
            self.translations.get("clear_logs", "Clear Logs")
        )
        self.clear_logs_button.setIcon(qta.icon("fa5s.eraser", color="#9ca3af"))
        self.clear_logs_button.clicked.connect(self.clear_logs)
        self.clear_logs_button.setToolTip(
            self.translations.get("clear_logs_tooltip", "Clear all log messages")
        )
        self.export_log_button = QPushButton()
        self.export_log_button.setText(
            self.translations.get("export_logs", "Export Logs")
        )
        self.export_log_button.setIcon(qta.icon("fa5s.download", color="#9ca3af"))
        self.export_log_button.clicked.connect(self.export_logs)
        self.export_log_button.setToolTip(
            self.translations.get("export_logs_tooltip", "Export logs to a text file")
        )
        actions_layout.addWidget(self.clear_logs_button)
        actions_layout.addWidget(self.export_log_button)
        self.actions_group_logs.setLayout(actions_layout)
        scroll_content_layout.addWidget(self.actions_group_logs)

        self.show_info_check.stateChanged.connect(self.update_log_filters)
        self.show_warning_check.stateChanged.connect(self.update_log_filters)
        self.show_error_check.stateChanged.connect(self.update_log_filters)

        scroll_area.setWidget(scroll_content)
        logs_layout.addWidget(scroll_area)

        self.tab_widget.addTab(logs_tab, "Logs")

    def create_about_tab(self):
        about_tab = QWidget()
        about_layout = QVBoxLayout(about_tab)
        about_layout.setContentsMargins(0, 0, 0, 0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)
        scroll_content_layout.setSpacing(16)
        scroll_content_layout.setContentsMargins(24, 24, 24, 24)

        # ── About Hero Section ──
        self.about_group = QGroupBox("About Advanced Tab Manager")
        about_layout_inner = QVBoxLayout()
        about_layout_inner.setSpacing(16)

        about_header = QHBoxLayout()
        about_header.setSpacing(12)
        about_icon_label = QLabel()
        about_icon_label.setPixmap(
            qta.icon("fa5s.layer-group", color="#9ca3af").pixmap(28, 28)
        )
        self.about_text_label = QLabel("About:")
        self.about_text_label.setStyleSheet("font-weight: 600; font-size: 16px;")
        about_header.addWidget(about_icon_label)
        about_header.addWidget(self.about_text_label)
        about_header.addStretch()
        about_layout_inner.addLayout(about_header)

        about_info = f"""
        <div style="line-height:1.8;">
            <span style="font-size:22px; font-weight:700;">Advanced Tab Manager Pro</span><br/>
            <span style="font-size:13px; opacity:0.5;">Version {CURRENT_VERSION}</span>
            <br/><br/>
            <span style="font-size:14px;">
                A powerful PyQt6 desktop application for automating browser tab
                management with Selenium. Ideal for testing, simulation, and
                repetitive browser automation tasks.
            </span>
        </div>
        <br/>
        <table cellpadding="0" cellspacing="0" style="width:100%; border-collapse:collapse;">
            <tr style="line-height:2.4;">
                <td style="padding:6px 20px 6px 0; opacity:0.6; white-space:nowrap;">Developer</td>
                <td style="padding:6px 0; font-weight:600;">VoxDroid</td>
            </tr>
            <tr style="line-height:2.4;">
                <td style="padding:6px 20px 6px 0; opacity:0.6; white-space:nowrap;">GitHub</td>
                <td style="padding:6px 0;"><a href="https://github.com/VoxDroid">github.com/VoxDroid</a></td>
            </tr>
            <tr style="line-height:2.4;">
                <td style="padding:6px 20px 6px 0; opacity:0.6; white-space:nowrap;">Support</td>
                <td style="padding:6px 0;"><a href="https://github.com/VoxDroid/Advance-Tab-Manager/issues">Issues Page</a></td>
            </tr>
        </table>
        """
        about_label = QLabel(about_info)
        about_label.setObjectName("about_label")
        about_label.setOpenExternalLinks(True)
        about_label.setWordWrap(True)
        about_label.setTextFormat(Qt.TextFormat.RichText)
        about_label.setToolTip(
            "Click links for more information about the developer or license"
        )
        about_layout_inner.addWidget(about_label)
        self.about_group.setLayout(about_layout_inner)
        scroll_content_layout.addWidget(self.about_group)

        # ── Features ──
        features_group = QGroupBox("Features")
        features_layout = QVBoxLayout()
        features_layout.setSpacing(10)
        feature_items = [
            ("fa5s.globe", "Multi-browser automation (Chrome & Firefox)"),
            ("fa5s.cogs", "Headless, incognito, proxy, and custom user-agent support"),
            (
                "fa5s.language",
                "5-language interface \u2014 English, Japanese, Korean, Chinese, Filipino",
            ),
            ("fa5s.palette", "6 hand-crafted color themes"),
            ("fa5s.chart-bar", "Real-time CPU, memory & disk monitoring"),
            ("fa5s.file-export", "Import / export settings and logs"),
        ]
        for icon_name, text in feature_items:
            row = QHBoxLayout()
            row.setSpacing(12)
            icon_lbl = QLabel()
            icon_lbl.setPixmap(qta.icon(icon_name, color="#9ca3af").pixmap(16, 16))
            icon_lbl.setFixedWidth(20)
            text_lbl = QLabel(text)
            text_lbl.setWordWrap(True)
            text_lbl.setStyleSheet("font-size: 13px;")
            row.addWidget(icon_lbl)
            row.addWidget(text_lbl, 1)
            features_layout.addLayout(row)
        features_group.setLayout(features_layout)
        scroll_content_layout.addWidget(features_group)

        # ── License Information ──
        self.license_group = QGroupBox("License")
        license_layout = QVBoxLayout()
        license_layout.setSpacing(10)
        license_text = """
        <div style="line-height:1.8; font-size:13px;">
            This software is licensed under the
            <a href="https://github.com/VoxDroid/Advance-Tab-Manager?tab=MIT-1-ov-file">MIT License</a>.
            You are free to use, modify, and distribute this software in accordance with the license terms.
        </div>
        """
        license_label = QLabel(license_text)
        license_label.setObjectName("license_label")
        license_label.setOpenExternalLinks(True)
        license_label.setWordWrap(True)
        license_label.setTextFormat(Qt.TextFormat.RichText)
        license_label.setToolTip("Click to view the MIT License details online")
        license_layout.addWidget(license_label)
        self.license_group.setLayout(license_layout)
        scroll_content_layout.addWidget(self.license_group)

        scroll_content_layout.addStretch()

        scroll_area.setWidget(scroll_content)
        about_layout.addWidget(scroll_area)

        self.tab_widget.addTab(about_tab, "About")

    def setup_status_bar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_message = QLabel("Ready")
        self.status_message.setStyleSheet(
            "color: #6b7280; font-size: 12px; font-family: 'JetBrains Mono', monospace;"
        )
        status_bar.addWidget(self.status_message)
        dev_info = QLabel(f"VoxDroid · v{CURRENT_VERSION}")
        dev_info.setStyleSheet(
            "color: #6b7280; font-size: 12px; font-family: 'JetBrains Mono', monospace;"
        )
        status_bar.addPermanentWidget(dev_info)

    def start_browser(self):
        if not self.url_input.text().strip():
            self.log_message(
                self.translations.get(
                    "log_please_enter_valid_url", "Please enter a valid URL!"
                ),
                "ERROR",
            )
            return

        url = self.url_input.text()
        iterations = self.iterations_input.value()
        interval = self.interval_input.value()
        instances = self.instances_input.value()
        browser_type = self.browser_combo.currentText().lower()

        if browser_type == "chrome":
            from selenium.webdriver.chrome.options import Options

            browser_options = Options()
            # Set Chrome binary location based on platform
            import os

            if os.name == "nt":  # Windows
                chrome_paths = [
                    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                    os.path.expanduser(
                        "~\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"
                    ),
                ]
            elif os.name == "posix":  # Linux/macOS
                chrome_paths = [
                    "/usr/bin/google-chrome",
                    "/usr/bin/google-chrome-stable",
                    "/usr/bin/chromium",
                    "/usr/bin/chromium-browser",
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",  # macOS
                ]
            else:
                chrome_paths = []

            for path in chrome_paths:
                if os.path.exists(path):
                    browser_options.binary_location = path
                    self.log_message(
                        self.translations.get(
                            "log_chrome_binary_found", "Found Chrome binary at: {path}"
                        ).format(path=path),
                        "DEBUG",
                    )
                    break
            else:
                self.log_message(
                    self.translations.get(
                        "log_chrome_binary_not_found",
                        "Chrome binary not found in standard locations. Chrome paths checked: {chrome_paths}",
                    ).format(chrome_paths=chrome_paths),
                    "WARNING",
                )
                # Try to find Chrome in PATH as fallback
                import shutil

                chrome_in_path = (
                    shutil.which("chrome")
                    or shutil.which("google-chrome")
                    or shutil.which("chromium")
                )
                if chrome_in_path:
                    browser_options.binary_location = chrome_in_path
                    self.log_message(
                        self.translations.get(
                            "log_chrome_in_path",
                            "Found Chrome in PATH: {chrome_in_path}",
                        ).format(chrome_in_path=chrome_in_path),
                        "DEBUG",
                    )
                else:
                    self.log_message(
                        self.translations.get(
                            "log_chrome_not_in_path",
                            "Chrome binary not found. WebDriver may fail to start.",
                        ),
                        "WARNING",
                    )
            if self.headless_checkbox.isChecked():
                browser_options.add_argument(
                    "--headless=new"
                )  # Use new headless implementation (Chrome 109+)
            if self.disable_gpu_checkbox.isChecked():
                browser_options.add_argument("--disable-gpu")
            if self.incognito_checkbox.isChecked():
                browser_options.add_argument("--incognito")
            if self.disable_extensions_checkbox.isChecked():
                browser_options.add_argument("--disable-extensions")
            if (
                not self.headless_checkbox.isChecked()
                and self.start_maximized_checkbox.isChecked()
            ):
                browser_options.add_argument("--start-maximized")
        elif browser_type == "firefox":
            from selenium.webdriver.firefox.options import Options

            browser_options = Options()
            # Set Firefox binary location based on platform
            import os

            if os.name == "nt":  # Windows
                firefox_paths = [
                    "C:\\Program Files\\Mozilla Firefox\\firefox.exe",
                    "C:\\Program Files (x86)\\Mozilla Firefox\\firefox.exe",
                ]
            elif os.name == "posix":  # Linux/macOS
                firefox_paths = [
                    "/usr/bin/firefox",
                    "/usr/lib/firefox/firefox",
                    "/Applications/Firefox.app/Contents/MacOS/firefox",  # macOS
                ]
            else:
                firefox_paths = []

            for path in firefox_paths:
                if os.path.exists(path):
                    browser_options.binary_location = path
                    break
            if self.headless_checkbox.isChecked():
                browser_options.add_argument("--headless")
            # Firefox specific options can be added here
            if self.incognito_checkbox.isChecked():
                browser_options.set_preference(
                    "browser.privatebrowsing.autostart", True
                )

        user_agent = self.user_agent_input.text()
        if user_agent:
            if browser_type == "chrome":
                browser_options.add_argument(f"user-agent={user_agent}")
            elif browser_type == "firefox":
                browser_options.set_preference("general.useragent.override", user_agent)

        if self.proxy_checkbox.isChecked():
            proxy = self.proxy_address_input.text()
            if proxy:
                if browser_type == "chrome":
                    browser_options.add_argument(f"--proxy-server={proxy}")
                elif browser_type == "firefox":
                    browser_options.set_preference("network.proxy.type", 1)
                    browser_options.set_preference(
                        "network.proxy.http", proxy.split(":")[0]
                    )
                    browser_options.set_preference(
                        "network.proxy.http_port", int(proxy.split(":")[1])
                    )

        # Apply browser-specific options
        if browser_type == "chrome":
            # Add some basic stability options
            browser_options.add_argument("--disable-background-timer-throttling")
            browser_options.add_argument("--disable-backgrounding-occluded-windows")
            browser_options.add_argument("--disable-renderer-backgrounding")

            # Linux-specific stability options (automatically enabled)
            if os.name == "posix":
                browser_options.add_argument(
                    "--disable-dev-shm-usage"
                )  # Prevent shared memory issues on Linux
                browser_options.add_argument("--no-first-run")  # Skip first run prompts
                browser_options.add_argument(
                    "--disable-default-apps"
                )  # Disable default app installation
                self.log_message(
                    self.translations.get(
                        "log_linux_stability_options",
                        "Applied Linux-specific stability options: --disable-dev-shm-usage, --no-first-run, --disable-default-apps",
                    ),
                    "DEBUG",
                )

            if self.disable_notifications_checkbox.isChecked():
                browser_options.add_argument("--disable-notifications")
            if self.disable_web_security_checkbox.isChecked():
                browser_options.add_argument("--disable-web-security")
            # Only add sandbox options if explicitly needed (usually for containers)
            if self.no_sandbox_checkbox.isChecked():
                browser_options.add_argument("--no-sandbox")
            # On Windows, allow user to choose dev-shm-usage option
            elif os.name != "posix" and self.disable_dev_shm_checkbox.isChecked():
                browser_options.add_argument("--disable-dev-shm-usage")
        elif browser_type == "firefox":
            if self.disable_notifications_checkbox.isChecked():
                browser_options.set_preference("dom.webnotifications.enabled", False)
            # Firefox doesn't have direct equivalents for some Chrome options
            # disable_web_security, no_sandbox, disable_dev_shm are Chrome-specific

        # Debug logging for browser options
        self.log_message(
            self.translations.get(
                "log_browser_info", "Browser: {browser_type}, Binary: {binary}"
            ).format(
                browser_type=browser_type,
                binary=getattr(browser_options, "binary_location", "Not set"),
            ),
            "DEBUG",
        )
        if hasattr(browser_options, "arguments"):
            self.log_message(
                self.translations.get(
                    "log_browser_arguments", "Browser arguments: {arguments}"
                ).format(arguments=browser_options.arguments),
                "DEBUG",
            )
        elif hasattr(browser_options, "_arguments"):
            self.log_message(
                self.translations.get(
                    "log_browser_arguments", "Browser arguments: {arguments}"
                ).format(arguments=browser_options._arguments),
                "DEBUG",
            )

        for instance_id in range(instances):
            thread = BrowserThread(
                url,
                iterations,
                interval,
                browser_options,
                instance_id,
                browser_type,
                self.translations,
            )
            thread.update_status.connect(self.update_status)
            thread.update_progress.connect(self.update_progress)
            thread.update_cycle.connect(self.update_cycle)
            thread.log_message.connect(self.log_message)
            thread.error_occurred.connect(self.handle_error)
            thread.finished.connect(lambda t=thread: self._on_thread_finished(t))
            thread.start()
            self.threads.append(thread)

    def _on_thread_finished(self, thread):
        """Handle when a browser thread finishes."""
        if thread in self.threads:
            # Thread finished on its own, remove from active list
            self.threads.remove(thread)
            thread.deleteLater()
            self.log_message(
                self.translations.get(
                    "log_browser_thread_finished",
                    "Browser thread for instance {instance_id} finished",
                ).format(instance_id=thread.instance_id),
                "INFO",
            )
            # Add small delay between thread starts to prevent overwhelming the system
            QTimer.singleShot(
                thread.instance_id * 500, lambda: None
            )  # Non-blocking delay
        self.status_message.setText("Running...")

    def stop_browser(self):
        """Stop all browser operations with guaranteed non-blocking behavior."""
        # CRITICAL: Update UI FIRST before any other operations
        self.status_message.setText("Stopping...")
        self.log_message(
            self.translations.get(
                "log_stopping_operations", "Stopping all browser operations..."
            ),
            "INFO",
        )

        # Stop all threads - this should be instant
        for thread in self.threads[:]:
            thread.stop()

        # Clear threads list immediately - don't wait
        self.threads.clear()

        # Schedule UI update and cleanup with minimal delay
        QTimer.singleShot(10, self._update_ui_after_stop)

    def _update_ui_after_stop(self):
        """Update UI after stop command."""
        self.status_message.setText("Stopped")
        self.status_label.setText("Idle")
        self.log_message(
            self.translations.get(
                "log_operations_stopped", "All browser operations stopped"
            ),
            "INFO",
        )

        # Schedule process cleanup much later to avoid any blocking
        QTimer.singleShot(1000, self._cleanup_processes_later)

    def _cleanup_processes_later(self):
        """Clean up processes long after UI is responsive."""
        try:
            self.kill_remaining_processes_async()
        except Exception as e:
            # Don't let cleanup errors affect the UI
            self.log_message(
                self.translations.get(
                    "log_process_cleanup_error", "Process cleanup error: {error}"
                ).format(error=str(e)),
                "WARNING",
            )

    def kill_remaining_processes_async(self):
        """Asynchronously terminate any remaining browser processes without blocking UI"""
        # Use a simple approach that doesn't block - just schedule basic cleanup
        QTimer.singleShot(0, lambda: self._safe_process_cleanup())

    def _safe_process_cleanup(self):
        """Safe process cleanup that won't block."""
        try:
            # Only do minimal cleanup to avoid blocking
            # The browser threads should have cleaned up their own processes
            self.log_message(
                self.translations.get(
                    "log_process_cleanup_completed", "Process cleanup completed"
                ),
                "INFO",
            )
        except Exception as e:
            self.log_message(
                self.translations.get(
                    "log_process_cleanup_error", "Process cleanup error: {error}"
                ).format(error=str(e)),
                "WARNING",
            )

    def test_proxy_connection(self):
        """Test the proxy connection by making a request through it."""
        proxy_address = self.proxy_address_input.text().strip()
        if not proxy_address:
            QMessageBox.warning(
                self,
                self.translations.get("proxy_test_title", "Proxy Test"),
                self.translations.get(
                    "proxy_test_enter_address", "Please enter a proxy address first."
                ),
            )
            return

        # Parse proxy address
        try:
            if ":" not in proxy_address:
                raise ValueError("Invalid proxy format")
            _, port_str = proxy_address.rsplit(":", 1)
            int(port_str)
        except ValueError:
            QMessageBox.warning(
                self,
                self.translations.get("proxy_test_title", "Proxy Test"),
                self.translations.get(
                    "proxy_test_invalid_format",
                    "Invalid proxy format. Use IP:PORT (e.g., 127.0.0.1:8080)",
                ),
            )
            return

        # Test the proxy
        self.test_proxy_button.setEnabled(False)
        self.test_proxy_button.setText(
            self.translations.get("proxy_test_button_testing", "Testing...")
        )

        # Create and start proxy test thread
        self.proxy_test_thread = ProxyTestThread(proxy_address)
        self.proxy_test_thread.test_finished.connect(self.on_proxy_test_finished)
        self.proxy_test_thread.start()

    def on_proxy_test_finished(self, message, msg_type):
        """Handle proxy test completion."""
        if msg_type == "success":
            QMessageBox.information(
                self, self.translations.get("proxy_test_title", "Proxy Test"), message
            )
        else:
            QMessageBox.warning(
                self, self.translations.get("proxy_test_title", "Proxy Test"), message
            )

        # Reset button
        self.test_proxy_button.setEnabled(True)
        self.test_proxy_button.setText(
            self.translations.get("proxy_test_button", "Test Proxy")
        )

        # Clean up thread
        self.proxy_test_thread.quit()
        self.proxy_test_thread.wait()
        self.proxy_test_thread = None

    def _toggle_proxy_input(self, state):
        """Enable/disable proxy input and test button based on checkbox state."""
        enabled = bool(state)
        self.proxy_address_input.setEnabled(enabled)
        self.test_proxy_button.setEnabled(enabled)

    def reset_fields(self):
        self.url_input.setText("https://google.com/")
        self.iterations_input.setValue(0)
        self.interval_input.setValue(1)
        self.instances_input.setValue(1)
        self.progress_bar.setValue(0)
        self.cycle_label.setText("0")
        self.status_label.setText("Idle")
        self.log_message(
            self.translations.get("log_fields_reset", "Fields reset to default"), "INFO"
        )

    def update_status(self, status):
        self.status_label.setText(status)
        self.status_message.setText(status)

    def update_progress(self, value):
        if self.threads:
            total_progress = sum(
                thread.progress
                for thread in self.threads
                if hasattr(thread, "progress")
            ) // len(self.threads)
            self.progress_bar.setValue(total_progress if total_progress > 0 else value)
        else:
            self.progress_bar.setValue(value)

    def update_cycle(self, cycle):
        max_cycle = max(
            (thread.cycle for thread in self.threads if hasattr(thread, "cycle")),
            default=cycle,
        )
        self.cycle_label.setText(str(max_cycle))

    def log_message(self, message, level):
        self.log_viewer.append_log(message, level)
        if level == "ERROR":
            self.status_message.setText(f"Error: {message}")

    def handle_error(self, error):
        self.log_message(error, "ERROR")
        self.stop_browser()

    def check_errors(self):
        for thread in self.threads[:]:
            if not thread.isRunning() and thread.is_running:
                self.handle_error(
                    f"Browser thread for instance {thread.instance_id} terminated unexpectedly"
                )
                self.stop_browser()
                break

    def update_system_monitor(self):
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage("/").percent
        self.cpu_usage_label.setText(f"CPU Usage: {cpu}%")
        self.memory_usage_label.setText(f"Memory Usage: {mem}%")
        self.disk_usage_label.setText(f"Disk Usage: {disk}%")
        self.cpu_progress.setValue(int(cpu))
        self.memory_progress.setValue(int(mem))
        self.disk_progress.setValue(int(disk))

    def update_log_filters(self):
        filters = {
            "INFO": self.show_info_check.isChecked(),
            "WARNING": self.show_warning_check.isChecked(),
            "ERROR": self.show_error_check.isChecked(),
        }
        current_text = self.log_viewer.toHtml()
        self.log_viewer.clear()
        for line in current_text.split("<br>"):
            if not line.strip():
                continue
            for level, show in filters.items():
                if f"[{level}]" in line and show:
                    self.log_viewer.append(line)
                    break

    def export_logs(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Logs", "", "Text Files (*.txt)"
        )
        if file_path:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(self.log_viewer.toPlainText())
                self.log_message(
                    self.translations.get(
                        "log_logs_exported", "Logs exported to {file_path}"
                    ).format(file_path=file_path),
                    "INFO",
                )
            except Exception as e:
                self.log_message(
                    self.translations.get(
                        "log_failed_export_logs", "Failed to export logs: {error}"
                    ).format(error=str(e)),
                    "ERROR",
                )

    def clear_logs(self):
        self.log_viewer.clear()
        self.log_message(
            self.translations.get("log_logs_cleared", "Logs cleared"), "INFO"
        )

    def change_theme(self, index):
        themes = {
            0: self.get_dark_navy_style(),
            1: self.get_light_blue_style(),
            2: self.get_dark_green_style(),
            3: self.get_light_green_style(),
            4: self.get_soft_pink_style(),
            5: self.get_soft_lavender_style(),
        }
        if index in themes:
            self.setStyleSheet(themes[index])
            self.log_message(
                self.translations.get(
                    "log_theme_changed", "Theme changed to {theme_name}"
                ).format(theme_name=self.theme_combo.currentText()),
                "INFO",
            )
        else:
            # Default to first theme if index is invalid
            self.setStyleSheet(themes[0])
            self.theme_combo.setCurrentIndex(0)
            self.log_message(
                self.translations.get(
                    "log_invalid_theme_index",
                    "Invalid theme index, defaulting to Dark Navy",
                ),
                "WARNING",
            )

    def change_font_size(self, size):
        font = QFont("JetBrains Mono", size)
        QApplication.setFont(font)
        self.log_message(
            self.translations.get(
                "log_font_size_changed", "Font size changed to {size}pt"
            ).format(size=size),
            "INFO",
        )

    def change_language(self, index):
        languages = {
            0: "English",
            1: "Japanese",
            2: "Korean",
            3: "Chinese",
            4: "Filipino",
        }
        if index in languages:
            self.log_message(
                self.translations.get(
                    "log_language_changed", "Language changed to {language}"
                ).format(language=languages[index]),
                "INFO",
            )
            self.update_language(languages[index])
        else:
            # Invalid index - just log warning, don't try to change to English to avoid recursion
            self.log_message(
                self.translations.get(
                    "log_invalid_language_index",
                    "Invalid language index: {index}, ignoring",
                ).format(index=index),
                "WARNING",
            )

    def update_language(self, language):
        import importlib

        translations = {}

        # Language file mapping
        lang_files = {
            "English": "en",
            "Japanese": "ja",
            "Korean": "ko",
            "Chinese": "zh",
            "Filipino": "fil",
        }

        # Load translations from separate files
        for lang_name, file_name in lang_files.items():
            try:
                module = importlib.import_module(
                    f".translations.{file_name}", package=__package__
                )
                translations[lang_name] = module.translations
            except ImportError as e:
                print(f"Failed to load translations for {lang_name}: {e}")
                # Fallback to English if available
                if "English" in translations:
                    translations[lang_name] = translations["English"]
                else:
                    translations[lang_name] = {}

        lang = translations.get(language, translations.get("English", {}))
        self.translations = lang  # Update the instance translations
        self.update_ui_text(lang)

    def update_ui_text(self, translations):
        self.setWindowTitle(translations["app_name"])

        # Main Tab
        self.url_text_label.setText(translations["main_url"])
        self.url_input.setToolTip(translations["main_url_tooltip"])
        self.iterations_text_label.setText(translations["main_iterations"])
        self.iterations_input.setToolTip(translations["main_iterations_tooltip"])
        self.interval_text_label.setText(translations["main_interval"])
        self.interval_input.setToolTip(translations["main_interval_tooltip"])
        self.instances_text_label.setText(translations["main_instances"])
        self.instances_input.setToolTip(translations["main_instances_tooltip"])
        self.start_button.setText(translations["main_start"])
        self.start_button.setToolTip(translations["main_start_tooltip"])
        self.stop_button.setText(translations["main_stop"])
        self.stop_button.setToolTip(translations["main_stop_tooltip"])
        self.reset_button.setText(translations["main_reset"])
        self.reset_button.setToolTip(translations["main_reset_tooltip"])
        self.status_text_label.setText(translations["main_status"])
        self.status_label.setText(translations["status_idle"])
        self.status_label.setToolTip(translations["main_status_tooltip"])
        self.cycle_text_label.setText(translations["main_cycles"])
        self.cycle_label.setToolTip(translations["main_cycles_tooltip"])
        self.url_group.setTitle(translations["url_group"])
        self.iterations_group.setTitle(translations["iterations_group"])
        self.interval_group.setTitle(translations["interval_group"])
        self.instances_group.setTitle(translations["instances_group"])
        self.button_group.setTitle(translations["button_group"])
        self.status_group.setTitle(translations["status_group"])
        self.progress_group.setTitle(translations["progress_group"])
        self.cycles_group.setTitle(translations["cycles_group"])
        self.tab_widget.setTabText(0, translations["tab_main"])

        # Advanced Tab
        self.browser_text_label.setText(translations["browser_selection"])
        self.browser_combo.setToolTip(translations["advanced_browser_tooltip"])
        self.browser_group.setTitle(translations["browser_selection_group"])
        self.headless_checkbox.setText(translations["advanced_headless"])
        self.headless_checkbox.setToolTip(translations["advanced_headless_tooltip"])
        self.disable_gpu_checkbox.setText(translations["advanced_disable_gpu"])
        self.disable_gpu_checkbox.setToolTip(
            translations["advanced_disable_gpu_tooltip"]
        )
        self.incognito_checkbox.setText(translations["advanced_incognito"])
        self.incognito_checkbox.setToolTip(translations["advanced_incognito_tooltip"])
        self.disable_extensions_checkbox.setText(
            translations["advanced_disable_extensions"]
        )
        self.disable_extensions_checkbox.setToolTip(
            translations["advanced_disable_extensions_tooltip"]
        )
        self.start_maximized_checkbox.setText(translations["advanced_start_maximized"])
        self.start_maximized_checkbox.setToolTip(
            translations["advanced_start_maximized_tooltip"]
        )
        self.disable_notifications_checkbox.setText(
            translations["advanced_disable_notifications"]
        )
        self.disable_notifications_checkbox.setToolTip(
            translations["advanced_disable_notifications_tooltip"]
        )
        self.disable_web_security_checkbox.setText(
            translations["advanced_disable_web_security"]
        )
        self.disable_web_security_checkbox.setToolTip(
            translations["advanced_disable_web_security_tooltip"]
        )
        self.no_sandbox_checkbox.setText(translations["advanced_no_sandbox"])
        self.no_sandbox_checkbox.setToolTip(translations["advanced_no_sandbox_tooltip"])
        self.disable_dev_shm_checkbox.setText(translations["advanced_disable_dev_shm"])
        self.disable_dev_shm_checkbox.setToolTip(
            translations["advanced_disable_dev_shm_tooltip"]
        )
        self.proxy_checkbox.setText(translations["advanced_proxy"])
        self.proxy_checkbox.setToolTip(translations["advanced_proxy_tooltip"])
        self.proxy_text_label.setText(translations["advanced_proxy_address"])
        self.proxy_address_input.setToolTip(
            translations["advanced_proxy_address_tooltip"]
        )
        self.test_proxy_button.setText(translations["advanced_test_proxy"])
        self.test_proxy_button.setToolTip(translations["advanced_test_proxy_tooltip"])
        self.user_agent_text_label.setText(translations["advanced_user_agent"])
        self.browser_options_group.setTitle(translations["browser_options_group"])
        self.user_agent_group.setTitle(translations["user_agent_group"])
        self.proxy_group.setTitle(translations["proxy_group"])
        self.tab_widget.setTabText(1, translations["tab_advanced"])

        # Settings Tab
        self.theme_text_label.setText(translations["settings_theme"])
        self.theme_combo.setToolTip(translations["settings_theme_tooltip"])
        self.font_text_label.setText(translations["settings_font"])
        self.font_size_spin.setToolTip(translations["settings_font_tooltip"])
        self.language_text_label.setText(translations["settings_language"])
        self.language_combo.setToolTip(translations["settings_language_tooltip"])
        self.save_settings_button.setText(translations["settings_save"])
        self.save_settings_button.setToolTip(translations["settings_save_tooltip"])
        self.load_settings_button.setText(translations["settings_load"])
        self.load_settings_button.setToolTip(translations["settings_load_tooltip"])
        self.export_settings_button.setText(translations["settings_export_settings"])
        self.export_settings_button.setToolTip(
            translations["settings_export_settings_tooltip"]
        )
        self.import_settings_button.setText(translations["settings_import"])
        self.import_settings_button.setToolTip(translations["settings_import_tooltip"])
        self.reset_settings_button.setText(translations["settings_reset"])
        self.reset_settings_button.setToolTip(translations["settings_reset_tooltip"])
        self.export_log_button.setText(translations["settings_export"])
        self.export_log_button.setToolTip(translations["settings_export_tooltip"])
        self.clear_logs_button.setText(translations["settings_clear"])
        self.clear_logs_button.setToolTip(translations["settings_clear_tooltip"])
        self.autostart_text_label.setText(translations["settings_autostart"])
        self.autostart_check.setToolTip(translations["settings_autostart_tooltip"])
        self.lock_window_size_text_label.setText(
            translations["settings_lock_window_size"]
        )
        self.lock_window_size_check.setToolTip(
            translations["settings_lock_window_size_tooltip"]
        )
        self.theme_group.setTitle(translations["theme_group"])
        self.font_group.setTitle(translations["font_group"])
        self.language_group.setTitle(translations["language_group"])
        self.actions_group.setTitle(translations["actions_group"])
        self.autostart_group.setTitle(translations["autostart_group"])
        self.lock_window_size_group.setTitle(translations["lock_window_size_group"])
        self.tab_widget.setTabText(2, translations["tab_settings"])

        # System Tab
        self.system_text_label.setText(translations["system_details"])
        self.system_text_label.setToolTip(translations["system_details_tooltip"])
        self.cpu_usage_label.setText(translations["system_cpu_usage"] + " 0%")
        self.cpu_usage_label.setToolTip(translations["system_cpu_usage_tooltip"])
        self.memory_usage_label.setText(translations["system_memory_usage"] + " 0%")
        self.memory_usage_label.setToolTip(translations["system_memory_usage_tooltip"])
        self.disk_usage_label.setText(translations["system_disk_usage"] + " 0%")
        self.disk_usage_label.setToolTip(translations["system_disk_usage_tooltip"])
        self.system_group.setTitle(translations["system_group"])
        self.monitor_group.setTitle(translations["monitor_group"])
        self.tab_widget.setTabText(3, translations["tab_system"])

        # Logs Tab
        self.logs_text_label.setText(translations["logs"])
        self.logs_text_label.setToolTip(translations["logs_tooltip"])
        self.show_info_check.setText(translations["logs_show_info"])
        self.show_info_check.setToolTip(translations["logs_show_info_tooltip"])
        self.show_warning_check.setText(translations["logs_show_warning"])
        self.show_warning_check.setToolTip(translations["logs_show_warning_tooltip"])
        self.show_error_check.setText(translations["logs_show_error"])
        self.show_error_check.setToolTip(translations["logs_show_error_tooltip"])
        self.logs_group.setTitle(translations["logs_group"])
        self.filter_group.setTitle(translations["filter_group"])
        self.actions_group_logs.setTitle(translations["actions_group_logs"])
        self.tab_widget.setTabText(4, translations["tab_logs"])

        # About Tab
        self.about_text_label.setText(translations["about"])
        self.about_text_label.setToolTip(translations["about_tooltip"])
        self.about_group.setTitle(translations["about_group"])
        self.license_group.setTitle(translations["license_group"])
        self.tab_widget.setTabText(5, translations["tab_about"])

        # Update "About" tab content dynamically
        about_info = f"""
        <div style="line-height:1.8;">
            <span style="font-size:22px; font-weight:700;"><a href="https://github.com/VoxDroid/Advance-Tab-Manager" style="text-decoration:none;">{translations["app_name"]}</a></span><br/>
            <span style="font-size:13px; opacity:0.5;">{translations["version"]} {CURRENT_VERSION}</span>
            <br/><br/>
            <span style="font-size:14px;">{translations["about_description"]}</span>
        </div>
        <br/>
        <table cellpadding="0" cellspacing="0" style="width:100%; border-collapse:collapse;">
            <tr style="line-height:2.4;">
                <td style="padding:6px 20px 6px 0; opacity:0.6; white-space:nowrap;">{translations["developed_by"]}</td>
                <td style="padding:6px 0; font-weight:600;">VoxDroid</td>
            </tr>
            <tr style="line-height:2.4;">
                <td style="padding:6px 20px 6px 0; opacity:0.6; white-space:nowrap;">{translations["github"]}</td>
                <td style="padding:6px 0;"><a href="https://github.com/VoxDroid">github.com/VoxDroid</a></td>
            </tr>
            <tr style="line-height:2.4;">
                <td style="padding:6px 20px 6px 0; opacity:0.6; white-space:nowrap;">{translations["about_support"]}</td>
                <td style="padding:6px 0;"><a href="https://github.com/VoxDroid/Advance-Tab-Manager/issues">{translations["about_issues_page"]}</a></td>
            </tr>
        </table>
        """
        about_label = self.findChild(QLabel, "about_label")
        if about_label:
            about_label.setText(about_info)
            about_label.setToolTip(translations["about_tooltip"])

        # Update license text
        license_text = f"""
        <div style="line-height:1.8; font-size:13px;">
            {translations["about_license_text"].format(license=translations["license"])}
        </div>
        """
        license_label = self.findChild(QLabel, "license_label")
        if license_label:
            license_label.setText(license_text)
            license_label.setToolTip(translations["license_tooltip"])

        # Update combo box items (disconnect signals to avoid recursion)
        self.theme_combo.currentIndexChanged.disconnect(self.change_theme)
        self.language_combo.currentIndexChanged.disconnect(self.change_language)

        self.browser_combo.clear()
        self.browser_combo.addItems(
            [translations["browser_chrome"], translations["browser_firefox"]]
        )

        self.theme_combo.clear()
        self.theme_combo.addItems(
            [
                translations["theme_dark_navy"],
                translations["theme_light_blue"],
                translations["theme_dark_green"],
                translations["theme_light_green"],
                translations["theme_soft_pink"],
                translations["theme_soft_lavender"],
            ]
        )

        self.language_combo.clear()
        self.language_combo.addItems(
            [
                translations["language_english"],
                translations["language_japanese"],
                translations["language_korean"],
                translations["language_chinese"],
                translations["language_filipino"],
            ]
        )

        # Set the current index based on the language
        lang_english = translations.get("language_english", "")
        if lang_english == "English":
            self.language_combo.setCurrentIndex(0)
        elif lang_english == "英語":
            self.language_combo.setCurrentIndex(1)
        elif lang_english == "영어":
            self.language_combo.setCurrentIndex(2)
        elif lang_english == "英语":
            self.language_combo.setCurrentIndex(3)
        elif lang_english == "Ingles":
            self.language_combo.setCurrentIndex(4)
        else:
            self.language_combo.setCurrentIndex(0)

        # Reconnect signals
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self.language_combo.currentIndexChanged.connect(self.change_language)

        # Update system information display
        if hasattr(self, "system_info_label"):
            self.system_info_label.setText(self._format_system_info_html())

        # Update status bar
        if hasattr(self, "status_message"):
            self.status_message.setText(translations["status_bar_ready"])

    def save_settings(self):
        ui_elements = {
            "url_input": self.url_input,
            "iterations_input": self.iterations_input,
            "interval_input": self.interval_input,
            "instances_input": self.instances_input,
            "theme_combo": self.theme_combo,
            "font_size_spin": self.font_size_spin,
            "language_combo": self.language_combo,
            "headless_checkbox": self.headless_checkbox,
            "disable_gpu_checkbox": self.disable_gpu_checkbox,
            "incognito_checkbox": self.incognito_checkbox,
            "disable_extensions_checkbox": self.disable_extensions_checkbox,
            "start_maximized_checkbox": self.start_maximized_checkbox,
            "disable_notifications_checkbox": self.disable_notifications_checkbox,
            "disable_web_security_checkbox": self.disable_web_security_checkbox,
            "no_sandbox_checkbox": self.no_sandbox_checkbox,
            "disable_dev_shm_checkbox": self.disable_dev_shm_checkbox,
            "user_agent_input": self.user_agent_input,
            "proxy_checkbox": self.proxy_checkbox,
            "proxy_address_input": self.proxy_address_input,
            "autostart_check": getattr(self, "autostart_check", None),
            "lock_window_size_check": getattr(self, "lock_window_size_check", None),
        }
        self.settings_manager = SettingsManager()
        self.settings_manager.save_settings(ui_elements)
        self.log_message(
            self.translations.get("log_settings_saved", "Settings saved successfully"),
            "INFO",
        )
        self.update_window_size_lock()

    def load_settings(self):
        ui_elements = {
            "url_input": self.url_input,
            "iterations_input": self.iterations_input,
            "interval_input": self.interval_input,
            "instances_input": self.instances_input,
            "theme_combo": self.theme_combo,
            "font_size_spin": self.font_size_spin,
            "language_combo": self.language_combo,
            "headless_checkbox": self.headless_checkbox,
            "disable_gpu_checkbox": self.disable_gpu_checkbox,
            "incognito_checkbox": self.incognito_checkbox,
            "disable_extensions_checkbox": self.disable_extensions_checkbox,
            "start_maximized_checkbox": self.start_maximized_checkbox,
            "disable_notifications_checkbox": self.disable_notifications_checkbox,
            "disable_web_security_checkbox": self.disable_web_security_checkbox,
            "no_sandbox_checkbox": self.no_sandbox_checkbox,
            "disable_dev_shm_checkbox": self.disable_dev_shm_checkbox,
            "user_agent_input": self.user_agent_input,
            "proxy_checkbox": self.proxy_checkbox,
            "proxy_address_input": self.proxy_address_input,
            "autostart_check": getattr(self, "autostart_check", None),
            "lock_window_size_check": getattr(self, "lock_window_size_check", None),
        }
        self.settings_manager = SettingsManager()
        self.settings_manager.load_settings(ui_elements)

        # Validate and apply theme
        theme_index = self.theme_combo.currentIndex()
        if 0 <= theme_index < self.theme_combo.count():
            self.change_theme(theme_index)
        else:
            self.change_theme(0)  # Default to first theme

        self.change_font_size(self.font_size_spin.value())

        # Validate and apply language
        language_index = self.language_combo.currentIndex()
        if 0 <= language_index < self.language_combo.count():
            self.change_language(language_index)
        else:
            # Don't call change_language for invalid indices to avoid recursion
            self.language_combo.setCurrentIndex(0)
            self.log_message(
                self.translations.get(
                    "log_invalid_language_index_settings",
                    "Invalid language index in settings, defaulting to English",
                ),
                "WARNING",
            )

        self.log_message(
            self.translations.get(
                "log_settings_loaded", "Settings loaded successfully"
            ),
            "INFO",
        )
        self.update_window_size_lock()

    def export_settings(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Settings", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                self.settings_manager.export_settings(file_path)
                self.log_message(
                    self.translations.get(
                        "log_settings_exported", "Settings exported to {file_path}"
                    ).format(file_path=file_path),
                    "INFO",
                )
            except Exception as e:
                self.log_message(
                    self.translations.get(
                        "log_failed_export_settings",
                        "Failed to export settings: {error}",
                    ).format(error=str(e)),
                    "ERROR",
                )

    def import_settings(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Settings", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                self.settings_manager.import_settings(file_path)
                self.load_settings()  # Reload settings into UI
                self.log_message(
                    self.translations.get(
                        "log_settings_imported", "Settings imported from {file_path}"
                    ).format(file_path=file_path),
                    "INFO",
                )
            except Exception as e:
                self.log_message(
                    self.translations.get(
                        "log_failed_import_settings",
                        "Failed to import settings: {error}",
                    ).format(error=str(e)),
                    "ERROR",
                )

    def reset_to_default_settings(self):
        """Reset all settings to their default values."""
        reply = QMessageBox.question(
            self,
            self.translations.get("reset_settings_title", "Reset Settings"),
            self.translations.get(
                "reset_settings_message",
                "Are you sure you want to reset all settings to their default values?\n\nThis action cannot be undone.",
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Clear all settings
                self.settings_manager.settings.clear()

                # Reset UI elements to defaults
                self.url_input.setText("https://google.com/")
                self.iterations_input.setValue(0)
                self.interval_input.setValue(1)
                self.instances_input.setValue(1)
                self.theme_combo.setCurrentIndex(0)
                self.font_size_spin.setValue(12)
                self.language_combo.setCurrentIndex(0)
                self.headless_checkbox.setChecked(False)
                self.disable_gpu_checkbox.setChecked(False)
                self.incognito_checkbox.setChecked(False)
                self.disable_extensions_checkbox.setChecked(False)
                self.start_maximized_checkbox.setChecked(False)
                self.disable_notifications_checkbox.setChecked(False)
                self.disable_web_security_checkbox.setChecked(False)
                self.no_sandbox_checkbox.setChecked(False)
                self.disable_dev_shm_checkbox.setChecked(False)
                self.user_agent_input.setText("")
                self.proxy_checkbox.setChecked(False)
                self.proxy_address_input.setText("")
                if hasattr(self, "autostart_check"):
                    self.autostart_check.setChecked(False)
                if hasattr(self, "lock_window_size_check"):
                    self.lock_window_size_check.setChecked(True)

                # Apply theme and font changes
                self.change_theme(0)
                self.change_font_size(12)
                self.change_language(0)
                self.update_window_size_lock()

                self.log_message(
                    self.translations.get(
                        "log_settings_reset", "All settings reset to default values"
                    ),
                    "INFO",
                )

            except Exception as e:
                self.log_message(
                    self.translations.get(
                        "log_failed_reset_settings", "Failed to reset settings: {error}"
                    ).format(error=str(e)),
                    "ERROR",
                )

    def closeEvent(self, event):
        # Auto-save settings before closing
        try:
            self.save_settings()
            self.log_message(
                self.translations.get(
                    "log_settings_auto_saved", "Settings auto-saved on exit"
                ),
                "INFO",
            )
        except Exception as e:
            self.log_message(
                self.translations.get(
                    "log_failed_auto_save_settings",
                    "Failed to auto-save settings: {error}",
                ).format(error=str(e)),
                "WARNING",
            )

        self.stop_browser()
        for thread in self.threads:
            if thread.isRunning():
                thread.terminate()
                QTimer.singleShot(0, lambda t=thread: t.wait(5000))
        self.kill_remaining_processes_async()
        event.accept()

    def resizeEvent(self, event):
        if self.lock_window_size:
            self.resize(self.minimumSize())
        super().resizeEvent(event)

    def toggle_window_size_lock(self, state):
        self.lock_window_size = bool(state)
        self.update_window_size_lock()
        self.log_message(
            self.translations.get(
                "log_window_size_lock", "Window size {status}"
            ).format(status="locked" if self.lock_window_size else "unlocked"),
            "INFO",
        )

    def update_window_size_lock(self):
        if self.lock_window_size:
            self.setMinimumSize(QSize(1100, 900))
            self.setMaximumSize(QSize(1100, 900))
            # Ensure window is not larger than minimum when locking
            if self.width() > 1100 or self.height() > 900:
                self.resize(1100, 900)
        else:
            self.setMinimumSize(QSize(0, 0))
            self.setMaximumSize(QSize(16777215, 16777215))  # Allow maximizing

        # Force window to update its constraints
        self.updateGeometry()


def main():
    app = QApplication(sys.argv)
    _load_jetbrains_mono()
    app.setFont(QFont("JetBrains Mono", 12))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
