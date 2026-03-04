import time
from PyQt6.QtWidgets import QTextEdit

class LogViewer(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            background-color: #19191f;
            color: #d1d5db;
            border: 1px solid #2a2a35;
            border-radius: 6px;
            font-family: 'JetBrains Mono', 'Courier New', monospace;
            font-size: 13px;
            padding: 12px;
        """)

    def append_log(self, message, level):
        colors = {"INFO": "#4ade80", "WARNING": "#facc15", "ERROR": "#f87171", "DEBUG": "#67e8f9"}
        timestamp = time.strftime("%H:%M:%S")
        self.append(f'<span style="color: {colors.get(level, "#d1d5db")}">[{timestamp}] [{level}] {message}</span>')
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())