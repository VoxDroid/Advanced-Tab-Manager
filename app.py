import sys
import time
import json
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLineEdit, QLabel, QTabWidget, QSpinBox, QProgressBar, 
                             QComboBox, QCheckBox, QFileDialog, QGroupBox, QScrollArea, QTextEdit)
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

class BrowserThread(QThread):
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    update_cycle = pyqtSignal(int)

    def __init__(self, url, iterations, interval, chrome_options):
        super().__init__()
        self.url = url
        self.iterations = iterations
        self.interval = interval
        self.chrome_options = chrome_options
        self.is_running = True

    def run(self):
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=self.chrome_options)

        driver.get(self.url)
        first_tab_handle = driver.current_window_handle

        iteration = 0
        while self.is_running and (self.iterations == 0 or iteration < self.iterations):
            driver.execute_script(f"window.open('{self.url}', '_blank');")
            time.sleep(self.interval)
            
            handles = driver.window_handles
            new_tab_handle = handles[-1]
            driver.switch_to.window(new_tab_handle)
            
            if new_tab_handle != first_tab_handle:
                driver.close()
            
            driver.switch_to.window(first_tab_handle)
            
            iteration += 1
            self.update_status.emit(f"{len(handles)} tabs open!")
            self.update_progress.emit(int(iteration / self.iterations * 100) if self.iterations > 0 else 0)
            self.update_cycle.emit(iteration)

        driver.quit()

    def stop(self):
        self.is_running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Tab Manager")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet(self.get_dark_navy_style())

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)

        self.create_main_tab()
        self.create_advanced_tab()
        self.create_settings_tab()

        self.threads = []
        self.instance_count = 1
        self.load_settings()

    def get_dark_navy_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #0a192f;
                color: #e6f1ff;
            }
            QTabBar::tab {
                background-color: #172a45;
                color: #e6f1ff;
                padding: 8px;
                margin: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #0a192f;
            }
            QPushButton {
                background-color: #172a45;
                color: #e6f1ff;
                border: none;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #303C55;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #172a45;
                color: #e6f1ff;
                border: 1px solid #303C55;
                padding: 5px;
                border-radius: 3px;
            }
            QLabel {
                color: #e6f1ff;
            }
            QProgressBar {
                border: 1px solid #303C55;
                border-radius: 5px;
                background-color: #172a45;
                color: #e6f1ff;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #303C55;
                border-radius: 5px;
            }
            QCheckBox {
                color: #e6f1ff;
            }
            QGroupBox {
                border: 1px solid #303C55;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """

    def create_main_tab(self):
        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)

        url_layout = QHBoxLayout()
        url_label = QLabel("URL:")
        self.url_input = QLineEdit("https://google.com/")
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        main_layout.addLayout(url_layout)

        iterations_layout = QHBoxLayout()
        iterations_label = QLabel("Iterations (0 for infinite):")
        self.iterations_input = QSpinBox()
        self.iterations_input.setRange(0, 1000000)
        iterations_layout.addWidget(iterations_label)
        iterations_layout.addWidget(self.iterations_input)
        main_layout.addLayout(iterations_layout)

        interval_layout = QHBoxLayout()
        interval_label = QLabel("Interval (seconds):")
        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 3600)
        self.interval_input.setValue(1)
        interval_layout.addWidget(interval_label)
        interval_layout.addWidget(self.interval_input)
        main_layout.addLayout(interval_layout)

        instances_layout = QHBoxLayout()
        instances_label = QLabel("Number of instances:")
        self.instances_input = QSpinBox()
        self.instances_input.setRange(1, 10)
        self.instances_input.setValue(1)
        instances_layout.addWidget(instances_label)
        instances_layout.addWidget(self.instances_input)
        main_layout.addLayout(instances_layout)

        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self.start_browser)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_browser)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)

        self.status_label = QLabel("Status: Idle")
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        main_layout.addWidget(self.progress_bar)

        self.cycle_label = QLabel("Cycles: 0")
        main_layout.addWidget(self.cycle_label)

        self.tab_widget.addTab(main_tab, "Main")

    def create_advanced_tab(self):
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # Chrome Options
        chrome_options_group = QGroupBox("Chrome Options")
        chrome_options_layout = QVBoxLayout()
        self.headless_checkbox = QCheckBox("Headless mode")
        self.disable_gpu_checkbox = QCheckBox("Disable GPU")
        self.incognito_checkbox = QCheckBox("Incognito mode")
        self.disable_extensions_checkbox = QCheckBox("Disable extensions")
        self.start_maximized_checkbox = QCheckBox("Start maximized")
        chrome_options_layout.addWidget(self.headless_checkbox)
        chrome_options_layout.addWidget(self.disable_gpu_checkbox)
        chrome_options_layout.addWidget(self.incognito_checkbox)
        chrome_options_layout.addWidget(self.disable_extensions_checkbox)
        chrome_options_layout.addWidget(self.start_maximized_checkbox)
        chrome_options_group.setLayout(chrome_options_layout)
        scroll_layout.addWidget(chrome_options_group)

        # User Agent
        user_agent_group = QGroupBox("User Agent")
        user_agent_layout = QVBoxLayout()
        self.user_agent_input = QLineEdit()
        self.user_agent_input.setPlaceholderText("Enter custom user agent (optional)")
        user_agent_layout.addWidget(self.user_agent_input)
        user_agent_group.setLayout(user_agent_layout)
        scroll_layout.addWidget(user_agent_group)

        # Proxy Settings
        proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout()
        self.proxy_checkbox = QCheckBox("Use proxy")
        self.proxy_address_input = QLineEdit()
        self.proxy_address_input.setPlaceholderText("Proxy address (e.g., 127.0.0.1:8080)")
        proxy_layout.addWidget(self.proxy_checkbox)
        proxy_layout.addWidget(self.proxy_address_input)
        proxy_group.setLayout(proxy_layout)
        scroll_layout.addWidget(proxy_group)

        # Additional Arguments
        args_group = QGroupBox("Additional Arguments")
        args_layout = QVBoxLayout()
        self.additional_args_input = QTextEdit()
        self.additional_args_input.setPlaceholderText("Enter additional Chrome arguments (one per line)")
        args_layout.addWidget(self.additional_args_input)
        args_group.setLayout(args_layout)
        scroll_layout.addWidget(args_group)

        scroll_area.setWidget(scroll_content)
        advanced_layout.addWidget(scroll_area)

        self.tab_widget.addTab(advanced_tab, "Advanced")

    def create_settings_tab(self):
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)

        theme_layout = QHBoxLayout()
        theme_label = QLabel("Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Navy", "Light Blue", "Dark Green", "Light Green"])
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        theme_layout.addWidget(theme_label)
        theme_layout.addWidget(self.theme_combo)
        settings_layout.addLayout(theme_layout)

        font_layout = QHBoxLayout()
        font_label = QLabel("Font Size:")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        self.font_size_spin.valueChanged.connect(self.change_font_size)
        font_layout.addWidget(font_label)
        font_layout.addWidget(self.font_size_spin)
        settings_layout.addLayout(font_layout)

        save_layout = QHBoxLayout()
        self.save_settings_button = QPushButton("Save Settings")
        self.save_settings_button.clicked.connect(self.save_settings)
        self.load_settings_button = QPushButton("Load Settings")
        self.load_settings_button.clicked.connect(self.load_settings)
        save_layout.addWidget(self.save_settings_button)
        save_layout.addWidget(self.load_settings_button)
        settings_layout.addLayout(save_layout)

        self.tab_widget.addTab(settings_tab, "Settings")

    def start_browser(self):
        url = self.url_input.text()
        iterations = self.iterations_input.value()
        interval = self.interval_input.value()
        instances = self.instances_input.value()

        chrome_options = Options()
        if self.headless_checkbox.isChecked():
            chrome_options.add_argument("--headless")
        if self.disable_gpu_checkbox.isChecked():
            chrome_options.add_argument("--disable-gpu")
        if self.incognito_checkbox.isChecked():
            chrome_options.add_argument("--incognito")
        if self.disable_extensions_checkbox.isChecked():
            chrome_options.add_argument("--disable-extensions")
        if self.start_maximized_checkbox.isChecked():
            chrome_options.add_argument("--start-maximized")

        user_agent = self.user_agent_input.text()
        if user_agent:
            chrome_options.add_argument(f"user-agent={user_agent}")

        if self.proxy_checkbox.isChecked():
            proxy = self.proxy_address_input.text()
            if proxy:
                chrome_options.add_argument(f"--proxy-server={proxy}")

        additional_args = self.additional_args_input.toPlainText().split("\n")
        for arg in additional_args:
            if arg.strip():
                chrome_options.add_argument(arg.strip())

        for _ in range(instances):
            thread = BrowserThread(url, iterations, interval, chrome_options)
            thread.update_status.connect(self.update_status)
            thread.update_progress.connect(self.update_progress)
            thread.update_cycle.connect(self.update_cycle)
            thread.start()
            self.threads.append(thread)

    def stop_browser(self):
        for thread in self.threads:
            thread.stop()
        self.threads.clear()
        self.status_label.setText("Status: Stopped")

    def update_status(self, status):
        self.status_label.setText(f"Status: {status}")

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_cycle(self, cycle):
        self.cycle_label.setText(f"Cycles: {cycle}")

    def change_theme(self, index):
        themes = {
            0: self.get_dark_navy_style(),
            1: self.get_light_blue_style(),
            2: self.get_dark_green_style(),
            3: self.get_light_green_style()
        }
        self.setStyleSheet(themes[index])

    def get_light_blue_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #e3f2fd;
                color: #0d47a1;
            }
            QTabBar::tab {
                background-color: #bbdefb;
                color: #0d47a1;
                padding: 8px;
                margin: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #e3f2fd;
            }
            QPushButton {
                background-color: #2196f3;
                color: #ffffff;
                border: none;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #ffffff;
                color: #0d47a1;
                border: 1px solid #bbdefb;
                padding: 5px;
                border-radius: 3px;
            }
            QLabel {
                color: #0d47a1;
            }
            QProgressBar {
                border: 1px solid #bbdefb;
                border-radius: 5px;
                background-color: #ffffff;
                color: #0d47a1;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #2196f3;
                border-radius: 5px;
            }
            QCheckBox {
                color: #0d47a1;
            }
            QGroupBox {
                border: 1px solid #bbdefb;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """

    def get_dark_green_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #1b5e20;
                color: #e8f5e9;
            }
            QTabBar::tab {
                background-color: #2e7d32;
                color: #e8f5e9;
                padding: 8px;
                margin: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #1b5e20;
            }
            QPushButton {
                background-color: #388e3c;
                color: #e8f5e9;
                border: none;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #43a047;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #2e7d32;
                color: #e8f5e9;
                border: 1px solid #43a047;
                padding: 5px;
                border-radius: 3px;
            }
            QLabel {
                color: #e8f5e9;
            }
            QProgressBar {
                border: 1px solid #43a047;
                border-radius: 5px;
                background-color: #2e7d32;
                color: #e8f5e9;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 5px;
            }
            QCheckBox {
                color: #e8f5e9;
            }
            QGroupBox {
                border: 1px solid #43a047;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """

    def get_light_green_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #e8f5e9;
                color: #1b5e20;
            }
            QTabBar::tab {
                background-color: #c8e6c9;
                color: #1b5e20;
                padding: 8px;
                margin: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
            }
            QTabBar::tab:selected {
                background-color: #e8f5e9;
            }
            QPushButton {
                background-color: #4caf50;
                color: #ffffff;
                border: none;
                padding: 8px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #43a047;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #ffffff;
                color: #1b5e20;
                border: 1px solid #a5d6a7;
                padding: 5px;
                border-radius: 3px;
            }
            QLabel {
                color: #1b5e20;
            }
            QProgressBar {
                border: 1px solid #a5d6a7;
                border-radius: 5px;
                background-color: #ffffff;
                color: #1b5e20;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 5px;
            }
            QCheckBox {
                color: #1b5e20;
            }
            QGroupBox {
                border: 1px solid #a5d6a7;
                border-radius: 5px;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }
        """

    def change_font_size(self, size):
        font = QFont("Poppins", size)
        QApplication.setFont(font)

    def save_settings(self):
        settings = QSettings("AdvancedTabManager", "Settings")
        settings.setValue("url", self.url_input.text())
        settings.setValue("iterations", self.iterations_input.value())
        settings.setValue("interval", self.interval_input.value())
        settings.setValue("instances", self.instances_input.value())
        settings.setValue("theme", self.theme_combo.currentIndex())
        settings.setValue("font_size", self.font_size_spin.value())
        settings.setValue("headless", self.headless_checkbox.isChecked())
        settings.setValue("disable_gpu", self.disable_gpu_checkbox.isChecked())
        settings.setValue("incognito", self.incognito_checkbox.isChecked())
        settings.setValue("disable_extensions", self.disable_extensions_checkbox.isChecked())
        settings.setValue("start_maximized", self.start_maximized_checkbox.isChecked())
        settings.setValue("user_agent", self.user_agent_input.text())
        settings.setValue("use_proxy", self.proxy_checkbox.isChecked())
        settings.setValue("proxy_address", self.proxy_address_input.text())
        settings.setValue("additional_args", self.additional_args_input.toPlainText())

    def load_settings(self):
        settings = QSettings("AdvancedTabManager", "Settings")
        self.url_input.setText(settings.value("url", "https://google.com/"))
        self.iterations_input.setValue(int(settings.value("iterations", 0)))
        self.interval_input.setValue(int(settings.value("interval", 1)))
        self.instances_input.setValue(int(settings.value("instances", 1)))
        self.theme_combo.setCurrentIndex(int(settings.value("theme", 0)))
        self.font_size_spin.setValue(int(settings.value("font_size", 12)))
        self.headless_checkbox.setChecked(settings.value("headless", False, type=bool))
        self.disable_gpu_checkbox.setChecked(settings.value("disable_gpu", False, type=bool))
        self.incognito_checkbox.setChecked(settings.value("incognito", False, type=bool))
        self.disable_extensions_checkbox.setChecked(settings.value("disable_extensions", False, type=bool))
        self.start_maximized_checkbox.setChecked(settings.value("start_maximized", False, type=bool))
        self.user_agent_input.setText(settings.value("user_agent", ""))
        self.proxy_checkbox.setChecked(settings.value("use_proxy", False, type=bool))
        self.proxy_address_input.setText(settings.value("proxy_address", ""))
        self.additional_args_input.setPlainText(settings.value("additional_args", ""))

        self.change_theme(self.theme_combo.currentIndex())
        self.change_font_size(self.font_size_spin.value())

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Poppins", 12))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())