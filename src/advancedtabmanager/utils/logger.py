import logging
import os
import sys

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    else:
        # Get the parent directory of utils (which is advancedtabmanager)
        base_dir = os.path.dirname(os.path.dirname(__file__))
        return os.path.join(base_dir, relative_path)

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('advanced_tab_manager.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("TabManager")

class Logger:
    def __init__(self):
        self.logger = setup_logging()

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def debug(self, message):
        self.logger.debug(message)