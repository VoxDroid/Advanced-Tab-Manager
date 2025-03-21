import sys
import time
import json
import logging
import platform
import psutil
import subprocess
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QPushButton, QLineEdit, QLabel, QTabWidget, QSpinBox, QProgressBar, 
                            QComboBox, QCheckBox, QFileDialog, QGroupBox, QScrollArea, QTextEdit,
                            QStatusBar, QSizePolicy)
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer, QSize, QEventLoop
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import qtawesome as qta
import urllib3
from urllib3.util.retry import Retry
import socket
import requests
import random
import os

urllib3.disable_warnings(urllib3.exceptions.ConnectionError)

retry_strategy = Retry(total=0, connect=None, read=None, redirect=None, status=None)
http = urllib3.PoolManager(retries=retry_strategy)

class BrowserThread(QThread):
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    update_cycle = pyqtSignal(int)
    log_message = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, url, iterations, interval, chrome_options, instance_id):
        super().__init__()
        self.url = url
        self.iterations = iterations
        self.interval = interval
        self.chrome_options = chrome_options
        self.is_running = True
        self.driver = None
        self.port = random.randint(9515, 9599)
        self.service = Service(ChromeDriverManager().install(), port=self.port)
        self.driver_process = None
        self.chrome_processes = []
        self.instance_id = instance_id  
        self.progress = 0  
        self.cycle = 0  

    def wait_for_service(self, host='127.0.0.1', port=0, timeout=10):
        """Wait for ChromeDriver service to be available on the specified port."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    return True
            except socket.error:
                time.sleep(0.1)
        return False

    def is_port_in_use(self, port, host='127.0.0.1'):
        """Check if a port is in use to avoid conflicts."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((host, port)) == 0

    def find_available_port(self, start_port=9515, end_port=9599):
        """Find an available port within the specified range."""
        while start_port <= end_port:
            if not self.is_port_in_use(start_port):
                return start_port
            start_port += 1
        raise Exception("No available ports in the specified range")

    def run(self):
        try:
            self.log_message.emit(f"Starting browser thread for instance {self.instance_id} on port {self.port}", "INFO")
            
            if self.is_port_in_use(self.port):
                self.port = self.find_available_port()
                self.service.port = self.port
                self.log_message.emit(f"Port {self.port} was in use, switching to new port {self.port}", "WARNING")

            self.service.start()

            if not self.wait_for_service(port=self.service.port):
                raise WebDriverException(f"ChromeDriver service failed to start on port {self.service.port} for instance {self.instance_id}")

            try:
                driver = webdriver.Remote(
                    command_executor=f"http://127.0.0.1:{self.service.port}",
                    options=self.chrome_options
                )
                self.driver = driver
            except WebDriverException as e:
                self.error_occurred.emit(f"Failed to initialize WebDriver for instance {self.instance_id}: {str(e)}")
                self.log_message.emit(f"Failed to initialize WebDriver for instance {self.instance_id}: {str(e)}", "ERROR")
                return

            self.driver_process = psutil.Process(self.service.process.pid)  

            self.chrome_processes = [p for p in psutil.process_iter(['pid', 'name']) 
                                  if 'chrome.exe' in p.name().lower() and 
                                  p.create_time() > time.time() - 10]

            try:
                self.driver.get(self.url)
                first_tab_handle = self.driver.current_window_handle
                self.log_message.emit(f"Opened initial tab with URL: {self.url} for instance {self.instance_id}", "INFO")

                iteration = 0
                while self.is_running and (self.iterations == 0 or iteration < self.iterations):
                    if not self.driver or not hasattr(self.driver, 'window_handles'):
                        self.error_occurred.emit(f"WebDriver is invalid or None for instance {self.instance_id}, cannot proceed with tab operations")
                        self.log_message.emit(f"WebDriver is invalid or None for instance {self.instance_id}, cannot proceed with tab operations", "ERROR")
                        break

                    try:
                        time.sleep(0.05)  
                        self.driver.execute_script(f"window.open('{self.url}', '_blank');")
                        time.sleep(self.interval)
                        
                        if not self.driver or not hasattr(self.driver, 'window_handles'):
                            self.error_occurred.emit(f"WebDriver became invalid during tab operation for instance {self.instance_id}")
                            self.log_message.emit(f"WebDriver became invalid during tab operation for instance {self.instance_id}", "ERROR")
                            break

                        handles = self.driver.window_handles
                        if not handles:
                            self.log_message.emit(f"No window handles found for instance {self.instance_id}, skipping tab operation", "WARNING")
                            continue

                        new_tab_handle = handles[-1]
                        self.driver.switch_to.window(new_tab_handle)
                        
                        if new_tab_handle != first_tab_handle:
                            self.driver.close()
                        
                        self.driver.switch_to.window(first_tab_handle)
                        
                        iteration += 1
                        self.progress = int(iteration / self.iterations * 100) if self.iterations > 0 else 0
                        self.cycle = iteration
                        self.update_status.emit(f"Instance {self.instance_id}: {len(handles)} tabs open!")
                        self.update_progress.emit(self.progress)
                        self.update_cycle.emit(self.cycle)
                        self.log_message.emit(f"Instance {self.instance_id}, Cycle {iteration}: Opened new tab, total tabs: {len(handles)}", "INFO")
                    except WebDriverException as e:
                        self.error_occurred.emit(f"Browser error for instance {self.instance_id}: {str(e)}")
                        self.log_message.emit(f"Browser error occurred for instance {self.instance_id}: {str(e)}", "ERROR")
                        break
                    except Exception as e:
                        self.error_occurred.emit(f"Unexpected error during tab operation for instance {self.instance_id}: {str(e)}")
                        self.log_message.emit(f"Unexpected error during tab operation for instance {self.instance_id}: {str(e)}", "ERROR")
                        break

            except Exception as e:
                self.error_occurred.emit(f"Critical error during tab operations for instance {self.instance_id}: {str(e)}")
                self.log_message.emit(f"Critical error during tab operations for instance {self.instance_id}: {str(e)}", "ERROR")
                return

        except Exception as e:
            self.error_occurred.emit(f"Critical error for instance {self.instance_id}: {str(e)}")
            self.log_message.emit(f"Critical error in thread for instance {self.instance_id}: {str(e)}", "ERROR")
        finally:
            self.cleanup()

    def cleanup(self):
        if self.driver:
            try:
                if hasattr(self.driver, 'session_id') and self.driver.session_id:
                    self.driver.session_id = None 
                    self.driver.close()  
                    self.driver.quit() 
                else:
                    self.log_message.emit(f"Driver session is invalid for instance {self.instance_id}, skipping graceful quit", "WARNING")
            except Exception as e:
                self.log_message.emit(f"Failed to quit driver gracefully for instance {self.instance_id}: {str(e)}", "WARNING")
            finally:
                self.driver = None

        if self.service:
            try:
                self.service.stop()
            except Exception as e:
                self.log_message.emit(f"Failed to stop service for instance {self.instance_id}: {str(e)}", "WARNING")

        if self.driver_process or self.chrome_processes:
            self.terminate_processes_async()

    def terminate_processes_async(self):
        """Asynchronously terminate ChromeDriver and Chrome processes to prevent UI freezing."""
        def terminate_process(proc):
            try:
                if proc and proc.is_running():
                    proc.terminate()
                    proc.wait(timeout=3)  
            except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                try:
                    if proc and proc.is_running():
                        proc.kill()
                except psutil.NoSuchProcess:
                    self.log_message.emit(f"Process {proc.pid if proc else 'unknown'} for instance {self.instance_id} already terminated", "INFO")

        if self.driver_process:
            QTimer.singleShot(0, lambda: terminate_process(self.driver_process))
            self.driver_process = None

        for proc in self.chrome_processes[:]: 
            QTimer.singleShot(0, lambda p=proc: terminate_process(p))

        self.log_message.emit(f"Browser thread processes for instance {self.instance_id} scheduled for termination", "INFO")

    def stop(self):
        self.is_running = False
        self.cleanup()
        self.log_message.emit(f"Stopping browser thread for instance {self.instance_id}", "WARNING")

class LogViewer(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            background-color: #172a45;
            color: #e6f1ff;
            border: 2px solid #303C55;
            border-radius: 10px;
            font-family: 'Courier New';
        """)

    def append_log(self, message, level):
        colors = {"INFO": "#00ff00", "WARNING": "#ffff00", "ERROR": "#ff0000", "DEBUG": "#00ffff"}
        timestamp = time.strftime("%H:%M:%S")
        self.append(f'<span style="color: {colors.get(level, "#e6f1ff")}">[{timestamp}] [{level}] {message}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        return os.path.join(os.path.dirname(__file__), relative_path)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowIcon(QIcon(resource_path("ATM.ico")))
        self.setWindowTitle("Advanced Tab Manager Pro")
        self.setGeometry(100, 100, 1100, 900)
        self.setMinimumSize(QSize(1100, 900))
        self.setStyleSheet(self.get_dark_navy_style())
        self.lock_window_size = True

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.tab_widget = QTabWidget()
        self.layout.addWidget(self.tab_widget)

        self.create_main_tab()
        self.create_advanced_tab()
        self.create_settings_tab()
        self.create_system_tab()
        self.create_logs_tab()
        self.create_about_tab()

        self.setup_status_bar()
        self.threads = []
        self.load_settings()

        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("TabManager")

        self.error_timer = QTimer()
        self.error_timer.timeout.connect(self.check_errors)
        self.error_timer.start(1000)

        self.update_window_size_lock()

    def get_dark_navy_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #0a192f;
                color: #e6f1ff;
                border-radius: 12px;
            }
            QTabBar::tab {
                background-color: #172a45;
                color: #e6f1ff;
                padding: 14px;
                margin: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #0a192f;
                border-bottom: 3px solid #1a237e;
            }
            QPushButton {
                background-color: #172a45;
                color: #e6f1ff;
                border: 2px solid #303C55;
                padding: 12px 24px;
                border-radius: 12px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #303C55;
                border-color: #4a5d78;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #172a45;
                color: #e6f1ff;
                border: 2px solid #303C55;
                padding: 10px;
                border-radius: 12px;
                font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #4a5d78;
                background-color: #1a2d4f;
            }
            QLabel {
                color: #e6f1ff;
                font-size: 16px;
                padding: 4px;
            }
            QProgressBar {
                border: 2px solid #303C55;
                border-radius: 12px;
                background-color: #172a45;
                color: #e6f1ff;
                text-align: center;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #303C55;
                border-radius: 10px;
            }
            QCheckBox {
                color: #e6f1ff;
                font-size: 16px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                border: 2px solid #303C55;
                border-radius: 6px;
                background-color: #172a45;
            }
            QCheckBox::indicator:checked {
                background-color: #1a237e;
                border-color: #4a5d78;
            }
            QGroupBox {
                background-color: #172a45;
                border: 2px solid #303C55;
                border-radius: 12px;
                margin-top: 20px;
                padding: 12px;
                font-size: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 18px;
                padding: 0 6px 0 6px;
                color: #e6f1ff;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
                border-radius: 12px;
            }
            QScrollArea QWidget {
                background-color: transparent;
            }
            QStatusBar {
                background-color: #172a45;
                color: #e6f1ff;
                font-size: 14px;
                border-top: 2px solid #303C55;
                border-radius: 0 0 12px 12px;
            }
        """

    def get_light_blue_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #e8f5ff;
                color: #0d47a1;
                border-radius: 12px;
            }
            QTabBar::tab {
                background-color: #bbdefb;
                color: #0d47a1;
                padding: 14px;
                margin: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #e8f5ff;
                border-bottom: 3px solid #1976d2;
            }
            QPushButton {
                background-color: #2196f3;
                color: #ffffff;
                border: 2px solid #bbdefb;
                padding: 12px 24px;
                border-radius: 12px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #1976d2;
                border-color: #1565c0;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #ffffff;
                color: #0d47a1;
                border: 2px solid #bbdefb;
                padding: 10px;
                border-radius: 12px;
                font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #1565c0;
                background-color: #f5faff;
            }
            QLabel {
                color: #0d47a1;
                font-size: 16px;
                padding: 4px;
            }
            QProgressBar {
                border: 2px solid #bbdefb;
                border-radius: 12px;
                background-color: #ffffff;
                color: #0d47a1;
                text-align: center;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #2196f3;
                border-radius: 10px;
            }
            QCheckBox {
                color: #0d47a1;
                font-size: 16px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                border: 2px solid #bbdefb;
                border-radius: 6px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #1976d2;
                border-color: #1565c0;
            }
            QGroupBox {
                background-color: #bbdefb;
                border: 2px solid #bbdefb;
                border-radius: 12px;
                margin-top: 20px;
                padding: 12px;
                font-size: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 18px;
                padding: 0 6px 0 6px;
                color: #0d47a1;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
                border-radius: 12px;
            }
            QScrollArea QWidget {
                background-color: transparent;
            }
            QStatusBar {
                background-color: #e8f5ff;
                color: #0d47a1;
                font-size: 14px;
                border-top: 2px solid #bbdefb;
                border-radius: 0 0 12px 12px;
            }
        """

    def get_dark_green_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #1b5e20;
                color: #e8f5e9;
                border-radius: 12px;
            }
            QTabBar::tab {
                background-color: #2e7d32;
                color: #e8f5e9;
                padding: 14px;
                margin: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #1b5e20;
                border-bottom: 3px solid #43a047;
            }
            QPushButton {
                background-color: #388e3c;
                color: #e8f5e9;
                border: 2px solid #43a047;
                padding: 12px 24px;
                border-radius: 12px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #43a047;
                border-color: #2e7d32;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #2e7d32;
                color: #e8f5e9;
                border: 2px solid #43a047;
                padding: 10px;
                border-radius: 12px;
                font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #2e7d32;
                background-color: #3a8341;
            }
            QLabel {
                color: #e8f5e9;
                font-size: 16px;
                padding: 4px;
            }
            QProgressBar {
                border: 2px solid #43a047;
                border-radius: 12px;
                background-color: #2e7d32;
                color: #e8f5e9;
                text-align: center;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 10px;
            }
            QCheckBox {
                color: #e8f5e9;
                font-size: 16px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                border: 2px solid #43a047;
                border-radius: 6px;
                background-color: #2e7d32;
            }
            QCheckBox::indicator:checked {
                background-color: #43a047;
                border-color: #2e7d32;
            }
            QGroupBox {
                background-color: #2e7d32;
                border: 2px solid #43a047;
                border-radius: 12px;
                margin-top: 20px;
                padding: 12px;
                font-size: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 18px;
                padding: 0 6px 0 6px;
                color: #e8f5e9;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
                border-radius: 12px;
            }
            QScrollArea QWidget {
                background-color: transparent;
            }
            QStatusBar {
                background-color: #1b5e20;
                color: #e8f5e9;
                font-size: 14px;
                border-top: 2px solid #43a047;
                border-radius: 0 0 12px 12px;
            }
        """

    def get_light_green_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #f0f7f0;
                color: #1b5e20;
                border-radius: 12px;
            }
            QTabBar::tab {
                background-color: #c8e6c9;
                color: #1b5e20;
                padding: 14px;
                margin: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #f0f7f0;
                border-bottom: 3px solid #43a047;
            }
            QPushButton {
                background-color: #4caf50;
                color: #ffffff;
                border: 2px solid #a5d6a7;
                padding: 12px 24px;
                border-radius: 12px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #43a047;
                border-color: #388e3c;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #ffffff;
                color: #1b5e20;
                border: 2px solid #a5d6a7;
                padding: 10px;
                border-radius: 12px;
                font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #388e3c;
                background-color: #f5faf5;
            }
            QLabel {
                color: #1b5e20;
                font-size: 16px;
                padding: 4px;
            }
            QProgressBar {
                border: 2px solid #a5d6a7;
                border-radius: 12px;
                background-color: #ffffff;
                color: #1b5e20;
                text-align: center;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #4caf50;
                border-radius: 10px;
            }
            QCheckBox {
                color: #1b5e20;
                font-size: 16px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                border: 2px solid #a5d6a7;
                border-radius: 6px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #43a047;
                border-color: #388e3c;
            }
            QGroupBox {
                background-color: #c8e6c9;
                border: 2px solid #a5d6a7;
                border-radius: 12px;
                margin-top: 20px;
                padding: 12px;
                font-size: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 18px;
                padding: 0 6px 0 6px;
                color: #1b5e20;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
                border-radius: 12px;
            }
            QScrollArea QWidget {
                background-color: transparent;
            }
            QStatusBar {
                background-color: #f0f7f0;
                color: #1b5e20;
                font-size: 14px;
                border-top: 2px solid #a5d6a7;
                border-radius: 0 0 12px 12px;
            }
        """

    def get_soft_pink_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #fff5f7;
                color: #d81b60;
                border-radius: 12px;
            }
            QTabBar::tab {
                background-color: #ffccd5;
                color: #d81b60;
                padding: 14px;
                margin: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #fff5f7;
                border-bottom: 3px solid #f48fb1;
            }
            QPushButton {
                background-color: #f48fb1;
                color: #ffffff;
                border: 2px solid #ff80ab;
                padding: 12px 24px;
                border-radius: 12px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #ec407a;
                border-color: #e91e63;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #ffffff;
                color: #d81b60;
                border: 2px solid #ff80ab;
                padding: 10px;
                border-radius: 12px;
                font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #e91e63;
                background-color: #fff1f5;
            }
            QLabel {
                color: #d81b60;
                font-size: 16px;
                padding: 4px;
            }
            QProgressBar {
                border: 2px solid #ff80ab;
                border-radius: 12px;
                background-color: #ffffff;
                color: #d81b60;
                text-align: center;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #f48fb1;
                border-radius: 10px;
            }
            QCheckBox {
                color: #d81b60;
                font-size: 16px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                border: 2px solid #ff80ab;
                border-radius: 6px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #ec407a;
                border-color: #e91e63;
            }
            QGroupBox {
                background-color: #ffccd5;
                border: 2px solid #ff80ab;
                border-radius: 12px;
                margin-top: 20px;
                padding: 12px;
                font-size: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 18px;
                padding: 0 6px 0 6px;
                color: #d81b60;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
                border-radius: 12px;
            }
            QScrollArea QWidget {
                background-color: transparent;
            }
            QStatusBar {
                background-color: #fff5f7;
                color: #d81b60;
                font-size: 14px;
                border-top: 2px solid #ff80ab;
                border-radius: 0 0 12px 12px;
            }
        """

    def get_soft_lavender_style(self):
        return """
            QMainWindow, QTabWidget::pane, QGroupBox {
                background-color: #f8f1ff;
                color: #4a148c;
                border-radius: 12px;
            }
            QTabBar::tab {
                background-color: #e1bee7;
                color: #4a148c;
                padding: 14px;
                margin: 2px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background-color: #f8f1ff;
                border-bottom: 3px solid #ab47bc;
            }
            QPushButton {
                background-color: #ab47bc;
                color: #ffffff;
                border: 2px solid #ce93d8;
                padding: 12px 24px;
                border-radius: 12px;
                min-width: 140px;
            }
            QPushButton:hover {
                background-color: #8e24aa;
                border-color: #6a1b9a;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit {
                background-color: #ffffff;
                color: #4a148c;
                border: 2px solid #ce93d8;
                padding: 10px;
                border-radius: 12px;
                font-size: 16px;
            }
            QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QTextEdit:focus {
                border-color: #6a1b9a;
                background-color: #f5e7ff;
            }
            QLabel {
                color: #4a148c;
                font-size: 16px;
                padding: 4px;
            }
            QProgressBar {
                border: 2px solid #ce93d8;
                border-radius: 12px;
                background-color: #ffffff;
                color: #4a148c;
                text-align: center;
                font-size: 14px;
            }
            QProgressBar::chunk {
                background-color: #ab47bc;
                border-radius: 10px;
            }
            QCheckBox {
                color: #4a148c;
                font-size: 16px;
                spacing: 10px;
            }
            QCheckBox::indicator {
                border: 2px solid #ce93d8;
                border-radius: 6px;
                background-color: #ffffff;
            }
            QCheckBox::indicator:checked {
                background-color: #8e24aa;
                border-color: #6a1b9a;
            }
            QGroupBox {
                background-color: #e1bee7;
                border: 2px solid #ce93d8;
                border-radius: 12px;
                margin-top: 20px;
                padding: 12px;
                font-size: 18px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 18px;
                padding: 0 6px 0 6px;
                color: #4a148c;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
                border-radius: 12px;
            }
            QScrollArea QWidget {
                background-color: transparent;
            }
            QStatusBar {
                background-color: #f8f1ff;
                color: #4a148c;
                font-size: 14px;
                border-top: 2px solid #ce93d8;
                border-radius: 0 0 12px 12px;
            }
        """

    def create_main_tab(self):
        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)

        # URL Section
        self.url_group = QGroupBox("URL Configuration")
        url_layout = QHBoxLayout()
        url_icon_label = QLabel()
        url_icon_label.setPixmap(qta.icon('fa5s.link', color='#e6f1ff').pixmap(16, 16))
        url_icon_label.setStyleSheet("padding-right: 10px;")
        self.url_text_label = QLabel("URL:")
        self.url_input = QLineEdit("https://google.com/")
        self.url_input.setToolTip("Enter the URL to open in tabs")
        url_layout.addWidget(url_icon_label)
        url_layout.addWidget(self.url_text_label)
        url_layout.addWidget(self.url_input)
        self.url_group.setLayout(url_layout)
        scroll_content_layout.addWidget(self.url_group)

        # Iterations Section
        self.iterations_group = QGroupBox("Iterations")
        iterations_layout = QHBoxLayout()
        iterations_icon_label = QLabel()
        iterations_icon_label.setPixmap(qta.icon('fa5s.redo', color='#e6f1ff').pixmap(16, 16))
        iterations_icon_label.setStyleSheet("padding-right: 10px;")
        self.iterations_text_label = QLabel("Iterations (0 for infinite):")
        self.iterations_input = QSpinBox()
        self.iterations_input.setRange(0, 1000000)
        self.iterations_input.setToolTip("Set to 0 for infinite iterations")
        iterations_layout.addWidget(iterations_icon_label)
        iterations_layout.addWidget(self.iterations_text_label)
        iterations_layout.addWidget(self.iterations_input)
        self.iterations_group.setLayout(iterations_layout)
        scroll_content_layout.addWidget(self.iterations_group)

        # Interval Section
        self.interval_group = QGroupBox("Interval")
        interval_layout = QHBoxLayout()
        interval_icon_label = QLabel()
        interval_icon_label.setPixmap(qta.icon('fa5s.clock', color='#e6f1ff').pixmap(16, 16))
        interval_icon_label.setStyleSheet("padding-right: 10px;")
        self.interval_text_label = QLabel("Interval (seconds):")
        self.interval_input = QSpinBox()
        self.interval_input.setRange(1, 3600)
        self.interval_input.setValue(1)
        self.interval_input.setToolTip("Set the delay between tab openings in seconds")
        interval_layout.addWidget(interval_icon_label)
        interval_layout.addWidget(self.interval_text_label)
        interval_layout.addWidget(self.interval_input)
        self.interval_group.setLayout(interval_layout)
        scroll_content_layout.addWidget(self.interval_group)

        # Instances Section
        self.instances_group = QGroupBox("Instances")
        instances_layout = QHBoxLayout()
        instances_icon_label = QLabel()
        instances_icon_label.setPixmap(qta.icon('fa5s.clone', color='#e6f1ff').pixmap(16, 16))
        instances_icon_label.setStyleSheet("padding-right: 10px;")
        self.instances_text_label = QLabel("Number of instances:")
        self.instances_input = QSpinBox()
        self.instances_input.setRange(1, 10)
        self.instances_input.setValue(1)
        self.instances_input.setToolTip("Set the number of browser instances to run simultaneously")
        instances_layout.addWidget(instances_icon_label)
        instances_layout.addWidget(self.instances_text_label)
        instances_layout.addWidget(self.instances_input)
        self.instances_group.setLayout(instances_layout)
        scroll_content_layout.addWidget(self.instances_group)

        # Actions Section
        self.button_group = QGroupBox("Actions")
        button_layout = QHBoxLayout()
        self.start_button = QPushButton()
        self.start_button.setText("Start")
        self.start_button.setIcon(qta.icon('fa5s.play', color='#e6f1ff'))
        self.start_button.clicked.connect(self.start_browser)
        self.start_button.setToolTip("Start opening tabs")
        self.stop_button = QPushButton()
        self.stop_button.setText("Stop")
        self.stop_button.setIcon(qta.icon('fa5s.stop', color='#e6f1ff'))
        self.stop_button.clicked.connect(self.stop_browser)
        self.stop_button.setToolTip("Stop all tab operations")
        self.reset_button = QPushButton()
        self.reset_button.setText("Reset")
        self.reset_button.setIcon(qta.icon('fa5s.sync', color='#e6f1ff'))
        self.reset_button.clicked.connect(self.reset_fields)
        self.reset_button.setToolTip("Reset all fields to default values")
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.reset_button)
        self.button_group.setLayout(button_layout)
        scroll_content_layout.addWidget(self.button_group)

        # Status Section
        self.status_group = QGroupBox("Status")
        status_layout = QHBoxLayout()
        status_icon_label = QLabel()
        status_icon_label.setPixmap(qta.icon('fa5s.info-circle', color='#e6f1ff').pixmap(16, 16))
        status_icon_label.setStyleSheet("padding-right: 10px;")
        self.status_text_label = QLabel("Status:")
        self.status_label = QLabel("Idle")
        self.status_label.setToolTip("Current status of the tab manager")
        status_layout.addWidget(status_icon_label)
        status_layout.addWidget(self.status_text_label)
        status_layout.addWidget(self.status_label)
        self.status_group.setLayout(status_layout)
        scroll_content_layout.addWidget(self.status_group)

        # Progress Section
        self.progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar)
        self.progress_group.setLayout(progress_layout)
        scroll_content_layout.addWidget(self.progress_group)

        # Cycles Section
        self.cycles_group = QGroupBox("Cycles")
        cycles_layout = QHBoxLayout()
        cycles_icon_label = QLabel()
        cycles_icon_label.setPixmap(qta.icon('fa5s.redo-alt', color='#e6f1ff').pixmap(16, 16))
        cycles_icon_label.setStyleSheet("padding-right: 10px;")
        self.cycle_text_label = QLabel("Cycles:")
        self.cycle_label = QLabel("0")
        self.cycle_label.setToolTip("Number of tab cycles completed")
        cycles_layout.addWidget(cycles_icon_label)
        cycles_layout.addWidget(self.cycle_text_label)
        cycles_layout.addWidget(self.cycle_label)
        self.cycles_group.setLayout(cycles_layout)
        scroll_content_layout.addWidget(self.cycles_group)

        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        self.tab_widget.addTab(main_tab, "Main")

    def create_advanced_tab(self):
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # Chrome Options
        self.chrome_options_group = QGroupBox("Chrome Options")
        chrome_options_layout = QVBoxLayout()
        self.headless_checkbox = QCheckBox()
        self.headless_checkbox.setText("Headless mode")
        self.headless_checkbox.setIcon(qta.icon('fa5s.eye-slash', color='#e6f1ff'))
        self.headless_checkbox.setToolTip("Run Chrome in headless mode (no UI)")
        self.disable_gpu_checkbox = QCheckBox()
        self.disable_gpu_checkbox.setText("Disable GPU")
        self.disable_gpu_checkbox.setIcon(qta.icon('fa5s.desktop', color='#e6f1ff'))
        self.disable_gpu_checkbox.setToolTip("Disable GPU hardware acceleration")
        self.incognito_checkbox = QCheckBox()
        self.incognito_checkbox.setText("Incognito mode")
        self.incognito_checkbox.setIcon(qta.icon('fa5s.user-secret', color='#e6f1ff'))
        self.incognito_checkbox.setToolTip("Run Chrome in incognito mode")
        self.disable_extensions_checkbox = QCheckBox()
        self.disable_extensions_checkbox.setText("Disable extensions")
        self.disable_extensions_checkbox.setIcon(qta.icon('fa5s.plug', color='#e6f1ff'))
        self.disable_extensions_checkbox.setToolTip("Disable all Chrome extensions")
        self.start_maximized_checkbox = QCheckBox()
        self.start_maximized_checkbox.setText("Start maximized")
        self.start_maximized_checkbox.setIcon(qta.icon('fa5s.expand', color='#e6f1ff'))
        self.start_maximized_checkbox.setToolTip("Start Chrome maximized")
        chrome_options_layout.addWidget(self.headless_checkbox)
        chrome_options_layout.addWidget(self.disable_gpu_checkbox)
        chrome_options_layout.addWidget(self.incognito_checkbox)
        chrome_options_layout.addWidget(self.disable_extensions_checkbox)
        chrome_options_layout.addWidget(self.start_maximized_checkbox)
        self.chrome_options_group.setLayout(chrome_options_layout)
        scroll_layout.addWidget(self.chrome_options_group)

        # User Agent
        self.user_agent_group = QGroupBox("User Agent")
        user_agent_layout = QHBoxLayout()
        user_agent_icon_label = QLabel()
        user_agent_icon_label.setPixmap(qta.icon('fa5s.user', color='#e6f1ff').pixmap(16, 16))
        user_agent_icon_label.setStyleSheet("padding-right: 10px;")
        self.user_agent_text_label = QLabel("Enter custom user agent (optional):")
        self.user_agent_input = QLineEdit()
        self.user_agent_input.setToolTip("Enter a custom user agent for the browser (optional)")
        user_agent_layout.addWidget(user_agent_icon_label)
        user_agent_layout.addWidget(self.user_agent_text_label)
        user_agent_layout.addWidget(self.user_agent_input)
        self.user_agent_group.setLayout(user_agent_layout)
        scroll_layout.addWidget(self.user_agent_group)

        # Proxy Settings
        self.proxy_group = QGroupBox("Proxy Settings")
        proxy_layout = QVBoxLayout()
        self.proxy_checkbox = QCheckBox()
        self.proxy_checkbox.setText("Use proxy")
        self.proxy_checkbox.setIcon(qta.icon('fa5s.server', color='#e6f1ff'))
        self.proxy_checkbox.setToolTip("Enable use of a proxy server")
        proxy_input_layout = QHBoxLayout()
        proxy_icon_label = QLabel()
        proxy_icon_label.setPixmap(qta.icon('fa5s.network-wired', color='#e6f1ff').pixmap(16, 16))
        proxy_icon_label.setStyleSheet("padding-right: 10px;")
        self.proxy_text_label = QLabel("Proxy address (e.g., 127.0.0.1:8080):")
        self.proxy_address_input = QLineEdit()
        self.proxy_address_input.setToolTip("Enter proxy address in the format IP:PORT (e.g., 127.0.0.1:8080)")
        proxy_input_layout.addWidget(proxy_icon_label)
        proxy_input_layout.addWidget(self.proxy_text_label)
        proxy_input_layout.addWidget(self.proxy_address_input)
        proxy_layout.addWidget(self.proxy_checkbox)
        proxy_layout.addLayout(proxy_input_layout)
        self.proxy_group.setLayout(proxy_layout)
        scroll_layout.addWidget(self.proxy_group)

        # Additional Arguments
        self.args_group = QGroupBox("Additional Arguments")
        args_layout = QHBoxLayout()
        args_icon_label = QLabel()
        args_icon_label.setPixmap(qta.icon('fa5s.cogs', color='#e6f1ff').pixmap(16, 16))
        args_icon_label.setStyleSheet("padding-right: 10px;")
        self.args_text_label = QLabel("Enter additional Chrome arguments (one per line):")
        self.additional_args_input = QTextEdit()
        self.additional_args_input.setPlaceholderText("Enter additional Chrome arguments (one per line)")
        self.additional_args_input.setToolTip("Add Chrome command-line arguments, one per line (e.g., --disable-notifications)")
        args_layout.addWidget(args_icon_label)
        args_layout.addWidget(self.args_text_label)
        args_layout.addWidget(self.additional_args_input)
        self.args_group.setLayout(args_layout)
        scroll_layout.addWidget(self.args_group)

        scroll_area.setWidget(scroll_content)
        advanced_layout.addWidget(scroll_area)

        self.tab_widget.addTab(advanced_tab, "Advanced")

    def create_settings_tab(self):
        settings_tab = QWidget()
        settings_layout = QVBoxLayout(settings_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)

        # Theme Section
        self.theme_group = QGroupBox("Theme Selection")
        theme_layout = QHBoxLayout()
        theme_icon_label = QLabel()
        theme_icon_label.setPixmap(qta.icon('fa5s.palette', color='#e6f1ff').pixmap(16, 16))
        theme_icon_label.setStyleSheet("padding-right: 10px;")
        self.theme_text_label = QLabel("Theme:")
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark Navy", "Light Blue", "Dark Green", "Light Green", "Soft Pink", "Soft Lavender"])
        self.theme_combo.currentIndexChanged.connect(self.change_theme)
        self.theme_combo.setToolTip("Select the visual theme for the application")
        theme_layout.addWidget(theme_icon_label)
        theme_layout.addWidget(self.theme_text_label)
        theme_layout.addWidget(self.theme_combo)
        self.theme_group.setLayout(theme_layout)
        scroll_content_layout.addWidget(self.theme_group)

        # Font Size Section
        self.font_group = QGroupBox("Font Size")
        font_layout = QHBoxLayout()
        font_icon_label = QLabel()
        font_icon_label.setPixmap(qta.icon('fa5s.font', color='#e6f1ff').pixmap(16, 16))
        font_icon_label.setStyleSheet("padding-right: 10px;")
        self.font_text_label = QLabel("Font Size:")
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setValue(12)
        self.font_size_spin.valueChanged.connect(self.change_font_size)
        self.font_size_spin.setToolTip("Adjust the font size for the application (8–24 pt)")
        font_layout.addWidget(font_icon_label)
        font_layout.addWidget(self.font_text_label)
        font_layout.addWidget(self.font_size_spin)
        self.font_group.setLayout(font_layout)
        scroll_content_layout.addWidget(self.font_group)

        # Language Section
        self.language_group = QGroupBox("Language")
        language_layout = QHBoxLayout()
        language_icon_label = QLabel()
        language_icon_label.setPixmap(qta.icon('fa5s.language', color='#e6f1ff').pixmap(16, 16))
        language_icon_label.setStyleSheet("padding-right: 10px;")
        self.language_text_label = QLabel("Language:")
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "Japanese", "Korean", "Chinese", "Filipino"])
        self.language_combo.currentIndexChanged.connect(self.change_language)
        self.language_combo.setToolTip("Select the language for the application interface")
        language_layout.addWidget(language_icon_label)
        language_layout.addWidget(self.language_text_label)
        language_layout.addWidget(self.language_combo)
        self.language_group.setLayout(language_layout)
        scroll_content_layout.addWidget(self.language_group)

        # Actions Section
        self.actions_group = QGroupBox("Actions")
        actions_layout = QHBoxLayout()
        self.save_settings_button = QPushButton()
        self.save_settings_button.setText("Save Settings")
        self.save_settings_button.setIcon(qta.icon('fa5s.save', color='#e6f1ff'))
        self.save_settings_button.clicked.connect(self.save_settings)
        self.save_settings_button.setToolTip("Save current application settings")
        self.load_settings_button = QPushButton()
        self.load_settings_button.setText("Load Settings")
        self.load_settings_button.setIcon(qta.icon('fa5s.upload', color='#e6f1ff'))
        self.load_settings_button.clicked.connect(self.load_settings)
        self.load_settings_button.setToolTip("Load previously saved settings")
        self.export_log_button = QPushButton()
        self.export_log_button.setText("Export Logs")
        self.export_log_button.setIcon(qta.icon('fa5s.download', color='#e6f1ff'))
        self.export_log_button.clicked.connect(self.export_logs)
        self.export_log_button.setToolTip("Export application logs to a text file")
        actions_layout.addWidget(self.save_settings_button)
        actions_layout.addWidget(self.load_settings_button)
        actions_layout.addWidget(self.export_log_button)
        self.actions_group.setLayout(actions_layout)
        scroll_content_layout.addWidget(self.actions_group)

        # Auto-Start Section
        self.autostart_group = QGroupBox("Auto-Start Options")
        autostart_layout = QHBoxLayout()
        autostart_icon_label = QLabel()
        autostart_icon_label.setPixmap(qta.icon('fa5s.play-circle', color='#e6f1ff').pixmap(16, 16))
        autostart_icon_label.setStyleSheet("padding-right: 10px;")
        self.autostart_text_label = QLabel("Auto-Start on Launch:")
        self.autostart_check = QCheckBox()
        self.autostart_check.setToolTip("Automatically start the browser on application launch")
        autostart_layout.addWidget(autostart_icon_label)
        autostart_layout.addWidget(self.autostart_text_label)
        autostart_layout.addWidget(self.autostart_check)
        self.autostart_group.setLayout(autostart_layout)
        scroll_content_layout.addWidget(self.autostart_group)

        # Lock Window Size Section
        self.lock_window_size_group = QGroupBox("Window Size Lock")
        lock_window_size_layout = QHBoxLayout()
        lock_window_size_icon_label = QLabel()
        lock_window_size_icon_label.setPixmap(qta.icon('fa5s.lock', color='#e6f1ff').pixmap(16, 16))
        lock_window_size_icon_label.setStyleSheet("padding-right: 10px;")
        self.lock_window_size_text_label = QLabel("Lock Window Size:")
        self.lock_window_size_check = QCheckBox()
        self.lock_window_size_check.setToolTip("Prevent resizing the window with the mouse")
        self.lock_window_size_check.stateChanged.connect(self.toggle_window_size_lock)
        lock_window_size_layout.addWidget(lock_window_size_icon_label)
        lock_window_size_layout.addWidget(self.lock_window_size_text_label)
        lock_window_size_layout.addWidget(self.lock_window_size_check)
        self.lock_window_size_group.setLayout(lock_window_size_layout)
        scroll_content_layout.addWidget(self.lock_window_size_group)

        scroll_area.setWidget(scroll_content)
        settings_layout.addWidget(scroll_area)

        self.tab_widget.addTab(settings_tab, "Settings")

    def create_system_tab(self):
        system_tab = QWidget()
        system_layout = QVBoxLayout(system_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)

        self.system_group = QGroupBox("System Information")
        system_layout_inner = QHBoxLayout()
        system_icon_label = QLabel()
        system_icon_label.setPixmap(qta.icon('fa5s.info-circle', color='#e6f1ff').pixmap(16, 16))
        system_icon_label.setStyleSheet("padding-right: 10px;")
        self.system_text_label = QLabel("System Details:")
        self.system_text_label.setStyleSheet("font-weight: bold;")

        system_info = f"""
        OS: {platform.system()} {platform.release()}
        Python Version: {platform.python_version()}
        CPU: {platform.processor()}
        CPU Cores: {psutil.cpu_count(logical=True)} (Physical: {psutil.cpu_count(logical=False)})
        Memory: {psutil.virtual_memory().total / (1024**3):.2f} GB
        Disk Space: {psutil.disk_usage('/').total / (1024**3):.2f} GB total
        CPU Usage: {psutil.cpu_percent()}%
        Memory Usage: {psutil.virtual_memory().percent}%
        """
        system_label = QLabel(system_info)
        system_label.setWordWrap(True)
        system_label.setToolTip("View detailed information about the system")
        system_layout_inner.addWidget(system_icon_label)
        system_layout_inner.addWidget(self.system_text_label)
        system_layout_inner.addWidget(system_label)
        self.system_group.setLayout(system_layout_inner)
        scroll_content_layout.addWidget(self.system_group)

        # Real-time System Monitor
        self.monitor_group = QGroupBox("Real-time System Monitor")
        monitor_layout = QVBoxLayout()
        self.cpu_usage_label = QLabel("CPU Usage: 0%")
        self.cpu_usage_label.setToolTip("View real-time CPU usage percentage")
        self.memory_usage_label = QLabel("Memory Usage: 0%")
        self.memory_usage_label.setToolTip("View real-time memory usage percentage")
        self.disk_usage_label = QLabel("Disk Usage: 0%")
        self.disk_usage_label.setToolTip("View real-time disk usage percentage")
        monitor_layout.addWidget(self.cpu_usage_label)
        monitor_layout.addWidget(self.memory_usage_label)
        monitor_layout.addWidget(self.disk_usage_label)
        self.monitor_group.setLayout(monitor_layout)
        scroll_content_layout.addWidget(self.monitor_group)

        scroll_area.setWidget(scroll_content)
        system_layout.addWidget(scroll_area)

        self.tab_widget.addTab(system_tab, "System")

        # Start real-time monitoring
        self.system_monitor_timer = QTimer()
        self.system_monitor_timer.timeout.connect(self.update_system_monitor)
        self.system_monitor_timer.start(1000) 

    def create_logs_tab(self):
        logs_tab = QWidget()
        logs_layout = QVBoxLayout(logs_tab)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)

        self.logs_group = QGroupBox("Application Logs")
        logs_layout_inner = QVBoxLayout()
        logs_icon_label = QLabel()
        logs_icon_label.setPixmap(qta.icon('fa5s.list-alt', color='#e6f1ff').pixmap(16, 16))
        logs_icon_label.setStyleSheet("padding-right: 10px;")
        self.logs_text_label = QLabel("Logs:")
        self.logs_text_label.setStyleSheet("font-weight: bold;")

        self.log_viewer = LogViewer()
        logs_layout_inner.addWidget(logs_icon_label)
        logs_layout_inner.addWidget(self.logs_text_label)
        logs_layout_inner.addWidget(self.log_viewer)
        self.logs_group.setLayout(logs_layout_inner)
        scroll_content_layout.addWidget(self.logs_group)

        # Log Filters
        self.filter_group = QGroupBox("Log Filters")
        filter_layout = QHBoxLayout()
        self.show_info_check = QCheckBox()
        self.show_info_check.setText("Show Info")
        self.show_info_check.setIcon(qta.icon('fa5s.info-circle', color='#e6f1ff'))
        self.show_info_check.setChecked(True)
        self.show_info_check.setToolTip("Show informational log messages")
        self.show_warning_check = QCheckBox()
        self.show_warning_check.setText("Show Warnings")
        self.show_warning_check.setIcon(qta.icon('fa5s.exclamation-triangle', color='#e6f1ff'))
        self.show_warning_check.setChecked(True)
        self.show_warning_check.setToolTip("Show warning log messages")
        self.show_error_check = QCheckBox()
        self.show_error_check.setText("Show Errors")
        self.show_error_check.setIcon(qta.icon('fa5s.times-circle', color='#e6f1ff'))
        self.show_error_check.setChecked(True)
        self.show_error_check.setToolTip("Show error log messages")
        filter_layout.addWidget(self.show_info_check)
        filter_layout.addWidget(self.show_warning_check)
        filter_layout.addWidget(self.show_error_check)
        self.filter_group.setLayout(filter_layout)
        scroll_content_layout.addWidget(self.filter_group)

        # Log Actions
        self.actions_group_logs = QGroupBox("Log Actions")
        actions_layout = QHBoxLayout()
        self.clear_logs_button = QPushButton()
        self.clear_logs_button.setText("Clear Logs")
        self.clear_logs_button.setIcon(qta.icon('fa5s.eraser', color='#e6f1ff'))
        self.clear_logs_button.clicked.connect(self.clear_logs)
        self.clear_logs_button.setToolTip("Clear all log messages")
        self.export_log_button = QPushButton()
        self.export_log_button.setText("Export Logs")
        self.export_log_button.setIcon(qta.icon('fa5s.download', color='#e6f1ff'))
        self.export_log_button.clicked.connect(self.export_logs)
        self.export_log_button.setToolTip("Export logs to a text file")
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

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_content_layout = QVBoxLayout(scroll_content)

        self.about_group = QGroupBox("About Advanced Tab Manager")
        about_layout_inner = QVBoxLayout()
        about_icon_label = QLabel()
        about_icon_label.setPixmap(qta.icon('fa5s.info', color='#e6f1ff').pixmap(16, 16))
        about_icon_label.setStyleSheet("padding-right: 10px;")
        self.about_text_label = QLabel("About:")
        self.about_text_label.setStyleSheet("font-weight: bold;")

        about_info = """
        <h2>Advanced Tab Manager Pro</h2>
        <p>Version: 1.1.0</p>
        <p>Developed by: VoxDroid</p>
        <p>Github: <a href="https://github.com/VoxDroid">https://github.com/VoxDroid</a></p>
        <p>Support: <a href="https://github.com/VoxDroid/Advance-Tab-Manager/issues">Issues Page</a></p>
        <p>Description: Advanced Tab Manager is a Python-based desktop application built with PyQt6 and Selenium. It provides a user-friendly interface to automate browser tab management, allowing users to open and close Chrome tabs programmatically with extensive customization options. This tool is ideal for testing, simulation, or repetitive browser automation tasks.</p>
        """
        about_label = QLabel(about_info)
        about_label.setObjectName("about_label")
        about_label.setOpenExternalLinks(True)
        about_label.setWordWrap(True)
        about_label.setToolTip("Click links for more information about the developer or license")
        about_layout_inner.addWidget(about_icon_label)
        about_layout_inner.addWidget(self.about_text_label)
        about_layout_inner.addWidget(about_label)
        self.about_group.setLayout(about_layout_inner)
        scroll_content_layout.addWidget(self.about_group)

        # License Information
        self.license_group = QGroupBox("License")
        license_layout = QVBoxLayout()
        license_text = """
        <p>This software is licensed under the MIT License. See <a href="https://github.com/VoxDroid/Advance-Tab-Manager?tab=MIT-1-ov-file">MIT License</a> for details.</p>
        """
        license_label = QLabel(license_text)
        license_label.setObjectName("license_label")
        license_label.setOpenExternalLinks(True)
        license_label.setWordWrap(True)
        license_label.setToolTip("Click to view the MIT License details online")
        license_layout.addWidget(license_label)
        self.license_group.setLayout(license_layout)
        scroll_content_layout.addWidget(self.license_group)

        scroll_area.setWidget(scroll_content)
        about_layout.addWidget(scroll_area)

        self.tab_widget.addTab(about_tab, "About")

    def setup_status_bar(self):
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        self.status_message = QLabel("Ready")
        self.status_message.setStyleSheet("color: #e6f1ff; font-size: 14px;")
        status_bar.addWidget(self.status_message)
        dev_info = QLabel("Developed by: VoxDroid | GitHub: github.com/VoxDroid | Version: 1.1.0")
        dev_info.setStyleSheet("color: #e6f1ff; font-size: 14px;")
        status_bar.addPermanentWidget(dev_info)

    def start_browser(self):
        if not self.url_input.text().strip():
            self.log_message("Please enter a valid URL!", "ERROR")
            return

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

        for instance_id in range(instances):
            thread = BrowserThread(url, iterations, interval, chrome_options, instance_id)
            thread.update_status.connect(self.update_status)
            thread.update_progress.connect(self.update_progress)
            thread.update_cycle.connect(self.update_cycle)
            thread.log_message.connect(self.log_message)
            thread.error_occurred.connect(self.handle_error)
            thread.start()
            self.threads.append(thread)
            time.sleep(0.1) 
        self.status_message.setText("Running...")

    def stop_browser(self):
        for thread in self.threads[:]:
            thread.stop()
            if thread.isRunning():
                QTimer.singleShot(0, lambda t=thread: t.wait(5000)) 
        self.threads.clear()
        self.kill_remaining_processes()
        self.status_message.setText("Stopped")
        self.status_label.setText("Idle")
        self.log_message("All browser threads and processes stopped", "INFO")

    def kill_remaining_processes(self):
        def terminate_process(proc):
            try:
                if proc and proc.is_running():
                    proc.terminate()
                    proc.wait(timeout=3)
            except (psutil.TimeoutExpired, psutil.NoSuchProcess):
                try:
                    if proc and proc.is_running():
                        proc.kill()
                except psutil.NoSuchProcess:
                    self.log_message(f"Process {proc.pid if proc else 'unknown'} already terminated", "INFO")

        for proc in psutil.process_iter(['pid', 'name']):
            if 'chromedriver.exe' in proc.name().lower() or 'chrome.exe' in proc.name().lower():
                QTimer.singleShot(0, lambda p=proc: terminate_process(p))
                self.log_message(f"Forcefully terminating process {proc.pid} ({proc.name()})", "WARNING")

    def reset_fields(self):
        self.url_input.setText("https://google.com/")
        self.iterations_input.setValue(0)
        self.interval_input.setValue(1)
        self.instances_input.setValue(1)
        self.progress_bar.setValue(0)
        self.cycle_label.setText("0")
        self.status_label.setText("Idle")
        self.log_message("Fields reset to default", "INFO")

    def update_status(self, status):
        self.status_label.setText(status)
        self.status_message.setText(status)

    def update_progress(self, value):
        if self.threads:
            total_progress = sum(thread.progress for thread in self.threads if hasattr(thread, 'progress')) // len(self.threads)
            self.progress_bar.setValue(total_progress if total_progress > 0 else value)
        else:
            self.progress_bar.setValue(value)

    def update_cycle(self, cycle):
        max_cycle = max((thread.cycle for thread in self.threads if hasattr(thread, 'cycle')), default=cycle)
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
                self.handle_error(f"Browser thread for instance {thread.instance_id} terminated unexpectedly")
                self.stop_browser()
                break

    def update_system_monitor(self):
        self.cpu_usage_label.setText(f"CPU Usage: {psutil.cpu_percent()}%")
        self.memory_usage_label.setText(f"Memory Usage: {psutil.virtual_memory().percent}%")
        self.disk_usage_label.setText(f"Disk Usage: {psutil.disk_usage('/').percent}%")

    def update_log_filters(self):
        filters = {
            "INFO": self.show_info_check.isChecked(),
            "WARNING": self.show_warning_check.isChecked(),
            "ERROR": self.show_error_check.isChecked()
        }
        current_text = self.log_viewer.toHtml()
        self.log_viewer.clear()
        for line in current_text.split('<br>'):
            if not line.strip():
                continue
            for level, show in filters.items():
                if f"[{level}]" in line and show:
                    self.log_viewer.append(line)
                    break

    def export_logs(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Logs", "", "Text Files (*.txt)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_viewer.toPlainText())
                self.log_message(f"Logs exported to {file_path}", "INFO")
            except Exception as e:
                self.log_message(f"Failed to export logs: {str(e)}", "ERROR")

    def clear_logs(self):
        self.log_viewer.clear()
        self.log_message("Logs cleared", "INFO")

    def change_theme(self, index):
        themes = {
            0: self.get_dark_navy_style(),
            1: self.get_light_blue_style(),
            2: self.get_dark_green_style(),
            3: self.get_light_green_style(),
            4: self.get_soft_pink_style(),
            5: self.get_soft_lavender_style()
        }
        self.setStyleSheet(themes[index])
        self.log_message(f"Theme changed to {self.theme_combo.currentText()}", "INFO")

    def change_font_size(self, size):
        font = QFont("Poppins", size)
        QApplication.setFont(font)
        self.log_message(f"Font size changed to {size}pt", "INFO")

    def change_language(self, index):
        languages = {
            0: "English",
            1: "Japanese",
            2: "Korean",
            3: "Chinese",
            4: "Filipino"
        }
        self.log_message(f"Language changed to {languages[index]}", "INFO")
        self.update_language(languages[index])

    def update_language(self, language):
        translations = {
            "English": {
                "app_name": "Advanced Tab Manager Pro",
                "main_url": "URL:",
                "main_iterations": "Iterations (0 for infinite):",
                "main_interval": "Interval (seconds):",
                "main_instances": "Number of instances:",
                "main_start": "Start",
                "main_stop": "Stop",
                "main_reset": "Reset",
                "main_status": "Status:",
                "main_cycles": "Cycles:",
                "main_url_tooltip": "Enter the URL to open in tabs",
                "main_iterations_tooltip": "Set to 0 for infinite iterations",
                "main_interval_tooltip": "Set the delay between tab openings in seconds",
                "main_instances_tooltip": "Set the number of browser instances to run simultaneously",
                "main_start_tooltip": "Start opening tabs",
                "main_stop_tooltip": "Stop all tab operations",
                "main_reset_tooltip": "Reset all fields to default values",
                "main_status_tooltip": "Current status of the tab manager",
                "main_cycles_tooltip": "Number of tab cycles completed",
                "url_group": "URL Configuration",
                "iterations_group": "Iterations",
                "interval_group": "Interval",
                "instances_group": "Instances",
                "button_group": "Actions",
                "status_group": "Status",
                "progress_group": "Progress",
                "cycles_group": "Cycles",
                "advanced_headless": "Headless mode",
                "advanced_disable_gpu": "Disable GPU",
                "advanced_incognito": "Incognito mode",
                "advanced_disable_extensions": "Disable extensions",
                "advanced_start_maximized": "Start maximized",
                "advanced_user_agent": "Enter custom user agent (optional):",
                "advanced_proxy": "Use proxy",
                "advanced_proxy_address": "Proxy address (e.g., 127.0.0.1:8080):",
                "advanced_args": "Enter additional Chrome arguments (one per line):",
                "advanced_headless_tooltip": "Run Chrome in headless mode (no UI)",
                "advanced_disable_gpu_tooltip": "Disable GPU hardware acceleration",
                "advanced_incognito_tooltip": "Run Chrome in incognito mode",
                "advanced_disable_extensions_tooltip": "Disable all Chrome extensions",
                "advanced_start_maximized_tooltip": "Start Chrome maximized",
                "advanced_user_agent_tooltip": "Enter a custom user agent for the browser (optional)",
                "advanced_proxy_tooltip": "Enable use of a proxy server",
                "advanced_proxy_address_tooltip": "Enter proxy address in the format IP:PORT (e.g., 127.0.0.1:8080)",
                "advanced_args_tooltip": "Add Chrome command-line arguments, one per line (e.g., --disable-notifications)",
                "chrome_options_group": "Chrome Options",
                "user_agent_group": "User Agent",
                "proxy_group": "Proxy Settings",
                "args_group": "Additional Arguments",
                "settings_theme": "Theme:",
                "settings_font": "Font Size:",
                "settings_language": "Language:",
                "settings_save": "Save Settings",
                "settings_load": "Load Settings",
                "settings_export": "Export Logs",
                "settings_clear": "Clear Logs",
                "settings_autostart": "Auto-Start on Launch:",
                "settings_lock_window_size": "Lock Window Size:",
                "settings_theme_tooltip": "Select the visual theme for the application",
                "settings_font_tooltip": "Adjust the font size for the application (8–24 pt)",
                "settings_language_tooltip": "Select the language for the application interface",
                "settings_save_tooltip": "Save current application settings",
                                "settings_load_tooltip": "Load previously saved settings",
                "settings_export_tooltip": "Export application logs to a text file",
                "settings_clear_tooltip": "Clear all log messages",
                "settings_autostart_tooltip": "Automatically start the browser on application launch",
                "settings_lock_window_size_tooltip": "Prevent resizing the window with the mouse",
                "theme_group": "Theme Selection",
                "font_group": "Font Size",
                "language_group": "Language",
                "actions_group": "Actions",
                "autostart_group": "Auto-Start Options",
                "lock_window_size_group": "Window Size Lock",
                "system_details": "System Details:",
                "system_cpu_usage": "CPU Usage:",
                "system_memory_usage": "Memory Usage:",
                "system_disk_usage": "Disk Usage:",
                "system_details_tooltip": "View detailed information about the system",
                "system_cpu_usage_tooltip": "View real-time CPU usage percentage",
                "system_memory_usage_tooltip": "View real-time memory usage percentage",
                "system_disk_usage_tooltip": "View real-time disk usage percentage",
                "system_group": "System Information",
                "monitor_group": "Real-time System Monitor",
                "logs": "Logs:",
                "logs_show_info": "Show Info",
                "logs_show_warning": "Show Warnings",
                "logs_show_error": "Show Errors",
                "logs_tooltip": "View application log messages",
                "logs_show_info_tooltip": "Show informational log messages",
                "logs_show_warning_tooltip": "Show warning log messages",
                "logs_show_error_tooltip": "Show error log messages",
                "logs_group": "Application Logs",
                "filter_group": "Log Filters",
                "actions_group_logs": "Log Actions",
                "about": "About:",
                "about_tooltip": "View information about the application",
                "license": "License",
                "license_tooltip": "View the software license details",
                "about_group": "About Advanced Tab Manager",
                "license_group": "License",
                "tab_main": "Main",
                "tab_advanced": "Advanced",
                "tab_settings": "Settings",
                "tab_system": "System",
                "tab_logs": "Logs",
                "tab_about": "About",
                "status_ready": "Ready",
                "status_running": "Running...",
                "status_stopped": "Stopped",
                "status_idle": "Idle",
                "error": "Error",
                "please_enter_valid_url": "Please enter a valid URL!",
                "developed_by": "Developed by: ",
                "github": "GitHub: ",
                "version": "Version: ",
                "description": "Description: "
            },
            "Japanese": {
                "app_name": "高度なタブマネージャープロ",
                "main_url": "URL：",
                "main_iterations": "イテレーション (0で無限):",
                "main_interval": "インターバル (秒):",
                "main_instances": "インスタンス数:",
                "main_start": "開始",
                "main_stop": "停止",
                "main_reset": "リセット",
                "main_status": "ステータス：",
                "main_cycles": "サイクル:",
                "main_url_tooltip": "タブで開くURLを入力してください",
                "main_iterations_tooltip": "無限のイテレーションのために0に設定します",
                "main_interval_tooltip": "タブの開き間の遅延を秒単位で設定します",
                "main_instances_tooltip": "同時に実行するブラウザインスタンスの数を設定します",
                "main_start_tooltip": "タブの開きを開始します",
                "main_stop_tooltip": "すべてのタブ操作を停止します",
                "main_reset_tooltip": "すべてのフィールドをデフォルト値にリセットします",
                "main_status_tooltip": "タブマネージャーの現在のステータス",
                "main_cycles_tooltip": "完了したタブサイクルの数",
                "url_group": "URL構成",
                "iterations_group": "イテレーション",
                "interval_group": "インターバル",
                "instances_group": "インスタンス",
                "button_group": "操作",
                "status_group": "ステータス",
                "progress_group": "進捗",
                "cycles_group": "サイクル",
                "advanced_headless": "ヘッドレスモード",
                "advanced_disable_gpu": "GPUを無効化",
                "advanced_incognito": "インコグニトモード",
                "advanced_disable_extensions": "拡張機能を無効化",
                "advanced_start_maximized": "最大化して開始",
                "advanced_user_agent": "カスタムユーザーエージェントを入力 (オプション):",
                "advanced_proxy": "プロキシを使用",
                "advanced_proxy_address": "プロキシアドレス (例: 127.0.0.1:8080):",
                "advanced_args": "追加のChrome引数を入力 (1行ごとに):",
                "advanced_headless_tooltip": "Chromeをヘッドレスモードで実行 (UIなし)",
                "advanced_disable_gpu_tooltip": "GPUハードウェアアクセラレーションを無効化",
                "advanced_incognito_tooltip": "Chromeをインコグニトモードで実行",
                "advanced_disable_extensions_tooltip": "すべてのChrome拡張機能を無効化",
                "advanced_start_maximized_tooltip": "Chromeを最大化して開始",
                "advanced_user_agent_tooltip": "ブラウザ用のカスタムユーザーエージェントを入力 (オプション)",
                "advanced_proxy_tooltip": "プロキシサーバーの使用を有効化",
                "advanced_proxy_address_tooltip": "プロキシアドレスをIP:PORT形式で入力 (例: 127.0.0.1:8080)",
                "advanced_args_tooltip": "Chromeコマンドライン引数を1行ごとに追加 (例: --disable-notifications)",
                "chrome_options_group": "Chromeオプション",
                "user_agent_group": "ユーザーエージェント",
                "proxy_group": "プロキシ設定",
                "args_group": "追加引数",
                "settings_theme": "テーマ：",
                "settings_font": "フォントサイズ：",
                "settings_language": "言語：",
                "settings_save": "設定を保存",
                "settings_load": "設定を読み込む",
                "settings_export": "ログをエクスポート",
                "settings_clear": "ログをクリア",
                "settings_autostart": "起動時の自動開始：",
                "settings_lock_window_size": "ウィンドウサイズをロック：",
                "settings_theme_tooltip": "アプリケーションの視覚的なテーマを選択します",
                "settings_font_tooltip": "アプリケーションのフォントサイズを調整 (8–24 pt)",
                "settings_language_tooltip": "アプリケーションインターフェイスの言語を選択します",
                "settings_save_tooltip": "現在のアプリケーション設定を保存します",
                "settings_load_tooltip": "以前に保存された設定を読み込みます",
                "settings_export_tooltip": "アプリケーションのログをテキストファイルにエクスポートします",
                "settings_clear_tooltip": "すべてのログメッセージをクリアします",
                "settings_autostart_tooltip": "アプリケーション起動時にブラウザを自動的に開始します",
                "settings_lock_window_size_tooltip": "マウスでのウィンドウサイズ変更を防止します",
                "theme_group": "テーマ選択",
                "font_group": "フォントサイズ",
                "language_group": "言語",
                "actions_group": "操作",
                "autostart_group": "自動開始オプション",
                "lock_window_size_group": "ウィンドウサイズロック",
                "system_details": "システム詳細：",
                "system_cpu_usage": "CPU使用率：",
                "system_memory_usage": "メモリ使用率：",
                "system_disk_usage": "ディスク使用率：",
                "system_details_tooltip": "システムに関する詳細情報を表示します",
                "system_cpu_usage_tooltip": "リアルタイムCPU使用率を表示します",
                "system_memory_usage_tooltip": "リアルタイムメモリ使用率を表示します",
                "system_disk_usage_tooltip": "リアルタイムディスク使用率を表示します",
                "system_group": "システム情報",
                "monitor_group": "リアルタイムシステムモニター",
                "logs": "ログ：",
                "logs_show_info": "情報を表示",
                "logs_show_warning": "警告を表示",
                "logs_show_error": "エラーを表示",
                "logs_tooltip": "アプリケーションのログメッセージを表示します",
                "logs_show_info_tooltip": "情報ログメッセージを表示します",
                "logs_show_warning_tooltip": "警告ログメッセージを表示します",
                "logs_show_error_tooltip": "エラーログメッセージを表示します",
                "logs_group": "アプリケーションログ",
                "filter_group": "ログフィルター",
                "actions_group_logs": "ログ操作",
                "about": "概要：",
                "about_tooltip": "アプリケーションに関する情報を表示します",
                "license": "ライセンス",
                "license_tooltip": "ソフトウェアのライセンスの詳細を表示します",
                "about_group": "高度なタブマネージャーについて",
                "license_group": "ライセンス",
                "tab_main": "メイン",
                "tab_advanced": "高度",
                "tab_settings": "設定",
                "tab_system": "システム",
                "tab_logs": "ログ",
                "tab_about": "概要",
                "status_ready": "準備完了",
                "status_running": "実行中...",
                "status_stopped": "停止済み",
                "status_idle": "待機中",
                "error": "エラー",
                "please_enter_valid_url": "有効なURLを入力してください！",
                "developed_by": "開発者：",
                "github": "GitHub：",
                "version": "バージョン：",
                "description": "説明："
            },
            "Korean": {
                "app_name": "고급 탭 관리자 프로",
                "main_url": "URL:",
                "main_iterations": "반복 (0은 무한):",
                "main_interval": "간격 (초):",
                "main_instances": "인스턴스 수:",
                "main_start": "시작",
                "main_stop": "중지",
                "main_reset": "초기화",
                "main_status": "상태:",
                "main_cycles": "사이클:",
                "main_url_tooltip": "탭에서 열 URL을 입력하세요",
                "main_iterations_tooltip": "무한 반복을 위해 0으로 설정하세요",
                "main_interval_tooltip": "탭 열기 간의 지연을 초 단위로 설정하세요",
                "main_instances_tooltip": "동시에 실행할 브라우저 인스턴스 수를 설정하세요",
                "main_start_tooltip": "탭 열기를 시작하세요",
                "main_stop_tooltip": "모든 탭 작업을 중지하세요",
                "main_reset_tooltip": "모든 필드를 기본값으로 초기화하세요",
                "main_status_tooltip": "탭 관리자의 현재 상태",
                "main_cycles_tooltip": "완료된 탭 사이클 수",
                "url_group": "URL 구성",
                "iterations_group": "반복",
                "interval_group": "간격",
                "instances_group": "인스턴스",
                "button_group": "작업",
                "status_group": "상태",
                "progress_group": "진행 상황",
                "cycles_group": "사이클",
                "advanced_headless": "헤드리스 모드",
                "advanced_disable_gpu": "GPU 비활성화",
                "advanced_incognito": "시크릿 모드",
                "advanced_disable_extensions": "확장 프로그램 비활성화",
                "advanced_start_maximized": "최대화하여 시작",
                "advanced_user_agent": "사용자 정의 사용자 에이전트 입력 (옵션):",
                "advanced_proxy": "프록시 사용",
                "advanced_proxy_address": "프록시 주소 (예: 127.0.0.1:8080):",
                "advanced_args": "추가 Chrome 인수 입력 (줄마다 하나씩):",
                "advanced_headless_tooltip": "Chrome을 헤드리스 모드에서 실행 (UI 없음)",
                "advanced_disable_gpu_tooltip": "GPU 하드웨어 가속 비활성화",
                "advanced_incognito_tooltip": "Chrome을 시크릿 모드에서 실행",
                "advanced_disable_extensions_tooltip": "모든 Chrome 확장 프로그램 비활성화",
                "advanced_start_maximized_tooltip": "Chrome을 최대화하여 시작",
                "advanced_user_agent_tooltip": "브라우저용 사용자 정의 사용자 에이전트를 입력 (옵션)",
                "advanced_proxy_tooltip": "프록시 서버 사용 활성화",
                "advanced_proxy_address_tooltip": "프록시 주소를 IP:PORT 형식으로 입력 (예: 127.0.0.1:8080)",
                "advanced_args_tooltip": "Chrome 명령줄 인수를 줄마다 하나씩 추가 (예: --disable-notifications)",
                "chrome_options_group": "Chrome 옵션",
                "user_agent_group": "사용자 에이전트",
                "proxy_group": "프록시 설정",
                "args_group": "추가 인수",
                "settings_theme": "테마：",
                "settings_font": "글꼴 크기：",
                "settings_language": "언어：",
                "settings_save": "설정 저장",
                "settings_load": "설정 불러오기",
                "settings_export": "로그 내보내기",
                "settings_clear": "로그 지우기",
                "settings_autostart": "시작 시 자동 시작：",
                "settings_lock_window_size": "창 크기 잠금：",
                "settings_theme_tooltip": "애플리케이션의 시각적 테마를 선택하세요",
                "settings_font_tooltip": "애플리케이션의 글꼴 크기를 조정하세요 (8–24 pt)",
                "settings_language_tooltip": "애플리케이션 인터페이스의 언어를 선택하세요",
                "settings_save_tooltip": "현재 애플리케이션 설정을 저장하세요",
                "settings_load_tooltip": "이전에 저장된 설정을 불러오세요",
                "settings_export_tooltip": "애플리케이션 로그를 텍스트 파일로 내보내세요",
                "settings_clear_tooltip": "모든 로그 메시지를 지우세요",
                "settings_autostart_tooltip": "애플리케이션 시작 시 브라우저를 자동으로 시작하세요",
                "settings_lock_window_size_tooltip": "마우스로 창 크기를 조정하지 못하도록 합니다",
                "theme_group": "테마 선택",
                "font_group": "글꼴 크기",
                "language_group": "언어",
                "actions_group": "작업",
                "autostart_group": "자동 시작 옵션",
                "lock_window_size_group": "창 크기 잠금",
                "system_details": "시스템 세부사항：",
                "system_cpu_usage": "CPU 사용률：",
                "system_memory_usage": "메모리 사용률：",
                "system_disk_usage": "디스크 사용률：",
                "system_details_tooltip": "시스템에 대한 상세 정보를 보세요",
                "system_cpu_usage_tooltip": "실시간 CPU 사용률을 확인하세요",
                "system_memory_usage_tooltip": "실시간 메모리 사용률을 확인하세요",
                "system_disk_usage_tooltip": "실시간 디스크 사용률을 확인하세요",
                "system_group": "시스템 정보",
                "monitor_group": "실시간 시스템 모니터",
                "logs": "로그：",
                "logs_show_info": "정보 표시",
                "logs_show_warning": "경고 표시",
                "logs_show_error": "오류 표시",
                "logs_tooltip": "애플리케이션 로그 메시지를 보세요",
                "logs_show_info_tooltip": "정보 로그 메시지를 표시합니다",
                "logs_show_warning_tooltip": "경고 로그 메시지를 표시합니다",
                "logs_show_error_tooltip": "오류 로그 메시지를 표시합니다",
                "logs_group": "애플리케이션 로그",
                "filter_group": "로그 필터",
                "actions_group_logs": "로그 작업",
                "about": "정보：",
                "about_tooltip": "애플리케이션에 대한 정보를 보세요",
                "license": "라이선스",
                "license_tooltip": "소프트웨어 라이선스 세부사항을 보세요",
                "about_group": "고급 탭 관리자 정보",
                "license_group": "라이선스",
                "tab_main": "메인",
                "tab_advanced": "고급",
                "tab_settings": "설정",
                "tab_system": "시스템",
                "tab_logs": "로그",
                "tab_about": "정보",
                "status_ready": "준비 완료",
                "status_running": "실행 중...",
                "status_stopped": "중지됨",
                "status_idle": "유휴",
                "error": "오류",
                "please_enter_valid_url": "유효한 URL을 입력하세요!",
                "developed_by": "개발자：",
                "github": "GitHub：",
                "version": "버전：",
                "description": "설명："
            },
            "Chinese": {
                "app_name": "高级标签管理器专业版",
                "main_url": "URL：",
                "main_iterations": "迭代次数（0为无限）：",
                "main_interval": "间隔（秒）：",
                "main_instances": "实例数量：",
                "main_start": "开始",
                "main_stop": "停止",
                "main_reset": "重置",
                "main_status": "状态：",
                "main_cycles": "循环：",
                "main_url_tooltip": "输入要在标签页中打开的URL",
                "main_iterations_tooltip": "设置为0以进行无限迭代",
                "main_interval_tooltip": "设置标签页打开之间的延迟（以秒为单位）",
                "main_instances_tooltip": "设置同时运行的浏览器实例数量",
                "main_start_tooltip": "开始打开标签页",
                "main_stop_tooltip": "停止所有标签页操作",
                "main_reset_tooltip": "将所有字段重置为默认值",
                "main_status_tooltip": "标签管理器的当前状态",
                "main_cycles_tooltip": "已完成的标签页循环次数",
                "url_group": "URL配置",
                "iterations_group": "迭代",
                "interval_group": "间隔",
                "instances_group": "实例",
                "button_group": "操作",
                "status_group": "状态",
                "progress_group": "进度",
                "cycles_group": "循环",
                "advanced_headless": "无头模式",
                "advanced_disable_gpu": "禁用GPU",
                "advanced_incognito": "隐身模式",
                "advanced_disable_extensions": "禁用扩展",
                "advanced_start_maximized": "最大化启动",
                "advanced_user_agent": "输入自定义用户代理（可选）：",
                "advanced_proxy": "使用代理",
                "advanced_proxy_address": "代理地址（例如：127.0.0.1:8080）：",
                "advanced_args": "输入附加的Chrome参数（每行一个）：",
                "advanced_headless_tooltip": "以无头模式运行Chrome（无UI）",
                "advanced_disable_gpu_tooltip": "禁用GPU硬件加速",
                "advanced_incognito_tooltip": "以隐身模式运行Chrome",
                "advanced_disable_extensions_tooltip": "禁用所有Chrome扩展",
                "advanced_start_maximized_tooltip": "最大化启动Chrome",
                "advanced_user_agent_tooltip": "为浏览器输入自定义用户代理（可选）",
                "advanced_proxy_tooltip": "启用代理服务器使用",
                "advanced_proxy_address_tooltip": "以IP:PORT格式输入代理地址（例如：127.0.0.1:8080）",
                "advanced_args_tooltip": "添加Chrome命令行参数，每行一个（例如：--disable-notifications）",
                "chrome_options_group": "Chrome选项",
                "user_agent_group": "用户代理",
                "proxy_group": "代理设置",
                "args_group": "附加参数",
                "settings_theme": "主题：",
                "settings_font": "字体大小：",
                "settings_language": "语言：",
                "settings_save": "保存设置",
                "settings_load": "加载设置",
                "settings_export": "导出日志",
                "settings_clear": "清除日志",
                "settings_autostart": "启动时自动启动：",
                "settings_lock_window_size": "锁定窗口大小：",
                "settings_theme_tooltip": "选择应用程序的视觉主题",
                "settings_font_tooltip": "调整应用程序的字体大小（8–24 pt）",
                "settings_language_tooltip": "选择应用程序界面的语言",
                "settings_save_tooltip": "保存当前应用程序设置",
                "settings_load_tooltip": "加载之前保存的设置",
                "settings_export_tooltip": "将应用程序日志导出到文本文件",
                "settings_clear_tooltip": "清除所有日志消息",
                "settings_autostart_tooltip": "在应用程序启动时自动启动浏览器",
                "settings_lock_window_size_tooltip": "防止用鼠标调整窗口大小",
                "theme_group": "主题选择",
                "font_group": "字体大小",
                "language_group": "语言",
                "actions_group": "操作",
                "autostart_group": "自动启动选项",
                "lock_window_size_group": "窗口大小锁定",
                "system_details": "系统详情：",
                "system_cpu_usage": "CPU使用率：",
                "system_memory_usage": "内存使用率：",
                "system_disk_usage": "磁盘使用率：",
                "system_details_tooltip": "查看系统的详细信息",
                "system_cpu_usage_tooltip": "查看实时CPU使用率百分比",
                "system_memory_usage_tooltip": "查看实时内存使用率百分比",
                "system_disk_usage_tooltip": "查看实时磁盘使用率百分比",
                "system_group": "系统信息",
                "monitor_group": "实时系统监控",
                "logs": "日志：",
                "logs_show_info": "显示信息",
                "logs_show_warning": "显示警告",
                "logs_show_error": "显示错误",
                "logs_tooltip": "查看应用程序日志消息",
                "logs_show_info_tooltip": "显示信息日志消息",
                "logs_show_warning_tooltip": "显示警告日志消息",
                "logs_show_error_tooltip": "显示错误日志消息",
                "logs_group": "应用程序日志",
                "filter_group": "日志过滤器",
                "actions_group_logs": "日志操作",
                "about": "关于：",
                "about_tooltip": "查看应用程序信息",
                "license": "许可",
                "license_tooltip": "查看软件许可详情",
                "about_group": "关于高级标签管理器",
                "license_group": "许可",
                "tab_main": "主页",
                "tab_advanced": "高级",
                "tab_settings": "设置",
                "tab_system": "系统",
                "tab_logs": "日志",
                "tab_about": "关于",
                "status_ready": "就绪",
                "status_running": "运行中...",
                "status_stopped": "已停止",
                "status_idle": "空闲",
                "error": "错误",
                "please_enter_valid_url": "请输入有效的URL！",
                "developed_by": "开发者：",
                "github": "GitHub：",
                "version": "版本：",
                "description": "描述："
            },
            "Filipino": {
                "app_name": "Advanced Tab Manager Pro",
                "main_url": "URL:",
                "main_iterations": "Mga Iterasyon (0 para sa walang hanggan):",
                "main_interval": "Agwat (segundo):",
                "main_instances": "Bilang ng mga instansya:",
                "main_start": "Simula",
                "main_stop": "Hinto",
                "main_reset": "I-reset",
                "main_status": "Katayuan:",
                "main_cycles": "Mga Siklo:",
                "main_url_tooltip": "Ipasok ang URL na bubuksan sa mga tab",
                "main_iterations_tooltip": "Itakda sa 0 para sa walang hanggang mga iterasyon",
                "main_interval_tooltip": "Itakda ang pagkaantala sa pagbukas ng mga tab sa segundo",
                "main_instances_tooltip": "Itakda ang bilang ng mga instansya ng browser na tatakbo nang sabay-sabay",
                "main_start_tooltip": "Simulan ang pagbukas ng mga tab",
                "main_stop_tooltip": "Huwag patuloy ang lahat ng operasyon ng tab",
                "main_reset_tooltip": "Ibalik ang lahat ng mga patlang sa mga default na halaga",
                "main_status_tooltip": "Kasalukuyang katayuan ng tagapamahala ng tab",
                "main_cycles_tooltip": "Bilang ng mga siklo ng tab na natapos",
                "url_group": "Konpigurasyon ng URL",
                "iterations_group": "Mga Iterasyon",
                "interval_group": "Agwat",
                "instances_group": "Mga Instansya",
                "button_group": "Mga Aksyon",
                "status_group": "Katayuan",
                "progress_group": "Pag-unlad",
                "cycles_group": "Mga Siklo",
                "advanced_headless": "Headless mode",
                "advanced_disable_gpu": "Huwag paganahin ang GPU",
                "advanced_incognito": "Incognito mode",
                "advanced_disable_extensions": "Huwag paganahin ang mga extension",
                "advanced_start_maximized": "Simulan nang pinakamalaki",
                "advanced_user_agent": "Magpasok ng custom user agent (opsyonal):",
                "advanced_proxy": "Gumamit ng proxy",
                "advanced_proxy_address": "Address ng proxy (hal. 127.0.0.1:8080):",
                "advanced_args": "Magpasok ng karagdagang Chrome na argumento (isa bawat linya):",
                "advanced_headless_tooltip": "Patakbuhin ang Chrome sa headless mode (walang UI)",
                "advanced_disable_gpu_tooltip": "Huwag paganahin ang hardware acceleration ng GPU",
                "advanced_incognito_tooltip": "Patakbuhin ang Chrome sa incognito mode",
                "advanced_disable_extensions_tooltip": "Huwag paganahin ang lahat ng Chrome extensions",
                "advanced_start_maximized_tooltip": "Simulan ang Chrome nang pinakamalaki",
                "advanced_user_agent_tooltip": "Magpasok ng custom user agent para sa browser (opsyonal)",
                "advanced_proxy_tooltip": "Paganahin ang paggamit ng proxy server",
                "advanced_proxy_address_tooltip": "Magpasok ng address ng proxy sa format ng IP:PORT (hal. 127.0.0.1:8080)",
                "advanced_args_tooltip": "Magdagdag ng Chrome command-line arguments, isa bawat linya (hal. --disable-notifications)",
                "chrome_options_group": "Mga Opsyon ng Chrome",
                "user_agent_group": "User Agent",
                "proxy_group": "Mga Setting ng Proxy",
                "args_group": "Karagdagang Mga Argumento",
                "settings_theme": "Tema:",
                "settings_font": "Laki ng Font:",
                "settings_language": "Wika:",
                "settings_save": "I-save ang Mga Setting",
                "settings_load": "Mag-load ng Mga Setting",
                "settings_export": "I-export ang Mga Log",
                "settings_clear": "Burahin ang Mga Log",
                "settings_autostart": "Auto-Start kapag Naglunsad:",
                "settings_lock_window_size": "I-lock ang Laki ng Window:",
                "settings_theme_tooltip": "Pumili ng biswal na tema para sa aplikasyon",
                "settings_font_tooltip": "Ayusin ang laki ng font para sa aplikasyon (8–24 pt)",
                "settings_language_tooltip": "Pumili ng wika para sa interface ng aplikasyon",
                "settings_save_tooltip": "I-save ang kasalukuyang mga setting ng aplikasyon",
                "settings_load_tooltip": "Mag-load ng mga na-save nang naunang mga setting",
                "settings_export_tooltip": "I-export ang mga log ng aplikasyon sa isang text file",
                "settings_clear_tooltip": "Burahin ang lahat ng mga mensahe ng log",
                "settings_autostart_tooltip": "Awtomatikong simulan ang browser kapag naglunsad ang aplikasyon",
                "settings_lock_window_size_tooltip": "Pigilan ang pag-aayos ng laki ng window gamit ang mouse",
                "theme_group": "Pagpili ng Tema",
                "font_group": "Laki ng Font",
                "language_group": "Wika",
                "actions_group": "Mga Aksyon",
                "autostart_group": "Mga Opsyon ng Auto-Start",
                "lock_window_size_group": "Pagsasara ng Laki ng Window",
                "system_details": "Detalye ng System:",
                "system_cpu_usage": "Paggamit ng CPU:",
                "system_memory_usage": "Paggamit ng Memorya:",
                "system_disk_usage": "Paggamit ng Disk:",
                "system_details_tooltip": "Tingnan ang detalyadong impormasyon tungkol sa system",
                "system_cpu_usage_tooltip": "Tingnan ang real-time na porsyento ng paggamit ng CPU",
                "system_memory_usage_tooltip": "Tingnan ang real-time na porsyento ng paggamit ng memorya",
                "system_disk_usage_tooltip": "Tingnan ang real-time na porsyento ng paggamit ng disk",
                "system_group": "Impormasyon ng System",
                "monitor_group": "Real-time System Monitor",
                "logs": "Mga Log:",
                "logs_show_info": "Ipakita ang Info",
                "logs_show_warning": "Ipakita ang Mga Babala",
                "logs_show_error": "Ipakita ang Mga Error",
                "logs_tooltip": "Tingnan ang mga mensahe ng log ng aplikasyon",
                "logs_show_info_tooltip": "Ipakita ang mga mensahe ng log na impormasyon",
                "logs_show_warning_tooltip": "Ipakita ang mga mensahe ng log na babala",
                "logs_show_error_tooltip": "Ipakita ang mga mensahe ng log na error",
                "logs_group": "Mga Log ng Aplikasyon",
                "filter_group": "Mga Filter ng Log",
                "actions_group_logs": "Mga Aksyon ng Log",
                "about": "Tungkol sa:",
                "about_tooltip": "Tingnan ang impormasyon tungkol sa aplikasyon",
                "license": "Lisensya",
                "license_tooltip": "Tingnan ang mga detalye ng lisensya ng software",
                "about_group": "Tungkol sa Advanced Tab Manager",
                "license_group": "Lisensya",
                "tab_main": "Pangunahin",
                "tab_advanced": "Advanced",
                "tab_settings": "Mga Setting",
                "tab_system": "System",
                "tab_logs": "Mga Log",
                "tab_about": "Tungkol sa",
                "status_ready": "Handa",
                "status_running": "Nagrarun...",
                "status_stopped": "Huminto",
                "status_idle": "Walang Ginagawa",
                "error": "Error",
                "please_enter_valid_url": "Mangyaring magpasok ng wastong URL!",
                "developed_by": "Binuo ni: ",
                "github": "GitHub: ",
                "version": "Bersyon: ",
                "description": "Paglalarawan: "
            }
        }
        lang = translations.get(language, translations["English"])
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
        self.headless_checkbox.setText(translations["advanced_headless"])
        self.headless_checkbox.setToolTip(translations["advanced_headless_tooltip"])
        self.disable_gpu_checkbox.setText(translations["advanced_disable_gpu"])
        self.disable_gpu_checkbox.setToolTip(translations["advanced_disable_gpu_tooltip"])
        self.incognito_checkbox.setText(translations["advanced_incognito"])
        self.incognito_checkbox.setToolTip(translations["advanced_incognito_tooltip"])
        self.disable_extensions_checkbox.setText(translations["advanced_disable_extensions"])
        self.disable_extensions_checkbox.setToolTip(translations["advanced_disable_extensions_tooltip"])
        self.start_maximized_checkbox.setText(translations["advanced_start_maximized"])
        self.start_maximized_checkbox.setToolTip(translations["advanced_start_maximized_tooltip"])
        self.user_agent_text_label.setText(translations["advanced_user_agent"])
        self.user_agent_input.setToolTip(translations["advanced_user_agent_tooltip"])
        self.proxy_checkbox.setText(translations["advanced_proxy"])
        self.proxy_checkbox.setToolTip(translations["advanced_proxy_tooltip"])
        self.proxy_text_label.setText(translations["advanced_proxy_address"])
        self.proxy_address_input.setToolTip(translations["advanced_proxy_address_tooltip"])
        self.args_text_label.setText(translations["advanced_args"])
        self.additional_args_input.setToolTip(translations["advanced_args_tooltip"])
        self.chrome_options_group.setTitle(translations["chrome_options_group"])
        self.user_agent_group.setTitle(translations["user_agent_group"])
        self.proxy_group.setTitle(translations["proxy_group"])
        self.args_group.setTitle(translations["args_group"])
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
        self.export_log_button.setText(translations["settings_export"])
        self.export_log_button.setToolTip(translations["settings_export_tooltip"])
        self.clear_logs_button.setText(translations["settings_clear"])
        self.clear_logs_button.setToolTip(translations["settings_clear_tooltip"])
        self.autostart_text_label.setText(translations["settings_autostart"])
        self.autostart_check.setToolTip(translations["settings_autostart_tooltip"])
        self.lock_window_size_text_label.setText(translations["settings_lock_window_size"])
        self.lock_window_size_check.setToolTip(translations["settings_lock_window_size_tooltip"])
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
        <h2><a href="https://github.com/VoxDroid/Advance-Tab-Manager">{translations["app_name"]}</a></h2>
        <p>{translations["version"]} 1.1.0</p>
        <p>{translations["developed_by"]} VoxDroid</p>
        <p>{translations["github"]}<a href="https://github.com/VoxDroid">https://github.com/VoxDroid</a></p>
        <p>Support: <a href="https://github.com/VoxDroid/Advance-Tab-Manager/issues">Issues Page</a></p>
        <p>{translations["description"]} Advanced Tab Manager is a Python-based desktop application built with PyQt6 and Selenium. It provides a user-friendly interface to automate browser tab management, allowing users to open and close Chrome tabs programmatically with extensive customization options. This tool is ideal for testing, simulation, or repetitive browser automation tasks.</p>
        """
        about_label = self.findChild(QLabel, "about_label")
        if about_label:
            about_label.setText(about_info)
            about_label.setToolTip(translations["about_tooltip"])

        # Update license text
        license_text = f"""
        <p>This software is licensed under the {translations["license"]}. See <a href="https://github.com/VoxDroid/Advance-Tab-Manager?tab=MIT-1-ov-file">{translations["license"]} </a> for details.</p>
        """
        license_label = self.findChild(QLabel, "license_label")
        if license_label:
            license_label.setText(license_text)
            license_label.setToolTip(translations["license_tooltip"])

    def save_settings(self):
        settings = QSettings("AdvancedTabManager", "Settings")
        settings.setValue("url", self.url_input.text())
        settings.setValue("iterations", self.iterations_input.value())
        settings.setValue("interval", self.interval_input.value())
        settings.setValue("instances", self.instances_input.value())
        settings.setValue("theme", self.theme_combo.currentIndex())
        settings.setValue("font_size", self.font_size_spin.value())
        settings.setValue("language", self.language_combo.currentIndex())
        settings.setValue("headless", self.headless_checkbox.isChecked())
        settings.setValue("disable_gpu", self.disable_gpu_checkbox.isChecked())
        settings.setValue("incognito", self.incognito_checkbox.isChecked())
        settings.setValue("disable_extensions", self.disable_extensions_checkbox.isChecked())
        settings.setValue("start_maximized", self.start_maximized_checkbox.isChecked())
        settings.setValue("user_agent", self.user_agent_input.text())
        settings.setValue("use_proxy", self.proxy_checkbox.isChecked())
        settings.setValue("proxy_address", self.proxy_address_input.text())
        settings.setValue("additional_args", self.additional_args_input.toPlainText())
        settings.setValue("autostart", self.autostart_check.isChecked())
        settings.setValue("lock_window_size", self.lock_window_size_check.isChecked())
        self.log_message("Settings saved successfully", "INFO")
        self.update_window_size_lock()

    def load_settings(self):
        settings = QSettings("AdvancedTabManager", "Settings")
        self.url_input.setText(settings.value("url", "https://google.com/"))
        self.iterations_input.setValue(int(settings.value("iterations", 0)))
        self.interval_input.setValue(int(settings.value("interval", 1)))
        self.instances_input.setValue(int(settings.value("instances", 1)))
        self.theme_combo.setCurrentIndex(int(settings.value("theme", 0)))
        self.font_size_spin.setValue(int(settings.value("font_size", 12)))
        self.language_combo.setCurrentIndex(int(settings.value("language", 0)))
        self.headless_checkbox.setChecked(settings.value("headless", False, type=bool))
        self.disable_gpu_checkbox.setChecked(settings.value("disable_gpu", False, type=bool))
        self.incognito_checkbox.setChecked(settings.value("incognito", False, type=bool))
        self.disable_extensions_checkbox.setChecked(settings.value("disable_extensions", False, type=bool))
        self.start_maximized_checkbox.setChecked(settings.value("start_maximized", False, type=bool))
        self.user_agent_input.setText(settings.value("user_agent", ""))
        self.proxy_checkbox.setChecked(settings.value("use_proxy", False, type=bool))
        self.proxy_address_input.setText(settings.value("proxy_address", ""))
        self.additional_args_input.setPlainText(settings.value("additional_args", ""))
        if hasattr(self, 'autostart_check'):
            self.autostart_check.setChecked(settings.value("autostart", False, type=bool))
        if hasattr(self, 'lock_window_size_check'):
            self.lock_window_size_check.setChecked(settings.value("lock_window_size", True, type=bool))

        self.change_theme(self.theme_combo.currentIndex())
        self.change_font_size(self.font_size_spin.value())
        self.change_language(self.language_combo.currentIndex())
        self.log_message("Settings loaded successfully", "INFO")
        self.update_window_size_lock()

    def closeEvent(self, event):
        self.stop_browser()
        for thread in self.threads:
            if thread.isRunning():
                thread.terminate()
                QTimer.singleShot(0, lambda t=thread: t.wait(5000))
        self.kill_remaining_processes()
        event.accept()

    def resizeEvent(self, event):
        if self.lock_window_size:
            self.resize(self.minimumSize())
        super().resizeEvent(event)

    def toggle_window_size_lock(self, state):
        self.lock_window_size = bool(state)
        self.update_window_size_lock()
        self.log_message(f"Window size {'locked' if self.lock_window_size else 'unlocked'}", "INFO")

    def update_window_size_lock(self):
        if self.lock_window_size:
            self.setMinimumSize(QSize(1100, 900))  
            self.setMaximumSize(QSize(1100, 900)) 
        else:
            self.setMinimumSize(QSize(0, 0))
            self.setMaximumSize(QSize(16777215, 16777215))  

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Poppins", 12))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())