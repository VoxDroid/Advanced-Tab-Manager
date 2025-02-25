# Advanced Tab Manager

## Overview

Advanced Tab Manager is a Python-based desktop application built with PyQt6 and Selenium. It provides a user-friendly interface to automate browser tab management, allowing users to open and close Chrome tabs programmatically with extensive customization options. This tool is ideal for testing, simulation, or repetitive browser automation tasks.

## Features

- **Graphical User Interface**: Manage tabs through an intuitive UI with three tabs: Main, Advanced, and Settings.
- **Customizable Tab Automation**:
  - Specify a URL to open.
  - Set the number of iterations (0 for infinite).
  - Define the interval between tab openings.
  - Run multiple browser instances simultaneously (up to 10).
- **Advanced Chrome Options**:
  - Headless mode, GPU disabling, incognito mode, and extension disabling.
  - Custom user agent and proxy settings.
  - Additional Chrome command-line arguments.
- **Theming**: Choose from four color themes (Dark Navy, Light Blue, Dark Green, Light Green).
- **Settings Persistence**: Save and load configurations for reuse.
- **Real-Time Feedback**: Displays status, progress bar, and cycle count during operation.
- **Automatic WebDriver Setup**: Uses Webdriver Manager to handle ChromeDriver installation.

## Prerequisites

1. **Python**: Python 3.x installed.
2. **Dependencies**: Install required libraries (see Installation).
3. **Google Chrome**: A compatible version of Chrome must be installed.

## Installation

1. Clone or download this repository:
   ```bash
   git clone https://github.com/VoxDroid/Advance-Tab-Manager.git
   cd Advanced-Tab-Manager
   ```
2. Install dependencies using `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python app.py
   ```

### Requirements.txt
```
PyQt6
qtawesome
selenium
webdriver-manager
```

## Usage

1. **Launch the Application**:
   - Run `python app.py` to open the GUI.
2. **Main Tab**:
   - Enter a URL (e.g., `https://google.com`).
   - Set iterations (0 for infinite), interval (in seconds), and number of instances.
   - Click "Start" to begin automation; "Stop" to halt it.
3. **Advanced Tab**:
   - Configure Chrome options (e.g., headless, incognito).
   - Set a custom user agent or proxy.
   - Add extra Chrome arguments (one per line).
4. **Settings Tab**:
   - Choose a theme and font size.
   - Save or load settings for future use.
5. **Monitoring**:
   - Watch the status, progress bar, and cycle count update in real-time.

## Script Breakdown

### 1. **Main Components**
- **BrowserThread**: A QThread subclass that handles tab opening/closing in the background, keeping the initial tab active.
- **MainWindow**: The core GUI class with tabs for main controls, advanced options, and settings.

### 2. **Tab Management**
- Opens new tabs with `window.open` via Selenium’s `execute_script`.
- Closes new tabs while preserving the first tab.
- Supports multiple instances for parallel execution.

### 3. **Customization**
- Chrome options are configurable via checkboxes and text inputs.
- Themes and font sizes enhance user experience.

### 4. **Persistence**
- Uses `QSettings` to save and load user preferences.

## Code Structure

```python
# Main application setup
app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())

# Browser thread for tab management
class BrowserThread(QThread):
    def run(self):
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(self.url)
        while self.is_running:
            driver.execute_script(f"window.open('{self.url}', '_blank');")
            time.sleep(self.interval)
            # Switch and close new tabs, keep first tab
            ...

# GUI with PyQt6
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Tab Manager")
        self.create_main_tab()
        self.create_advanced_tab()
        self.create_settings_tab()
    ...

```

## Use Cases

1. **Website Testing**: Simulate multiple tab openings for load testing.
2. **Automation Tasks**: Perform repetitive browser actions with custom settings.
3. **UI Customization**: Experiment with different themes and configurations.

## Notes

- Ensure an active internet connection for Webdriver Manager to download ChromeDriver.
- Modify the default URL in the Main tab to target different websites.
- Adjust intervals and iterations based on system performance.

## Screenshots

*N/A*

## Licensing

This project is distributed under the MIT License. Feel free to modify and use it in your projects.

---
