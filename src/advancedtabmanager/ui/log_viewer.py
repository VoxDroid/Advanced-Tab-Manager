import time
from PyQt6.QtWidgets import QTextEdit

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