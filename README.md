# Selenium Tab Management Script

## Overview

This script is a Python-based automation tool utilizing the Selenium library. It repeatedly opens and closes browser tabs while keeping a specific tab open at all times. It serves as a practical example of managing browser tabs programmatically.

## Features

- Automatically sets up the Chrome WebDriver with the correct version.
- Opens a specified URL in the browser.
- Continuously opens and closes new tabs, maintaining the initial tab open.
- Graceful shutdown with a keyboard interrupt (Ctrl+C).

## Prerequisites

1. **Python**: Ensure Python 3.x is installed.
2. **Selenium**: Install Selenium using `pip install selenium`.
3. **Webdriver Manager**: Install the Webdriver Manager library using `pip install webdriver-manager`.
4. **Google Chrome**: A compatible version of Google Chrome should be installed.

## Installation

To use this script:

1. Clone or download the repository.
2. Install the required Python dependencies:
   ```bash
   pip install selenium webdriver-manager
   ```

## Script Breakdown

### 1. **Chrome Options and Setup**

The script sets up the Chrome browser with specific options:

- ``: Starts the browser in maximized mode.
- ``: Disables browser extensions for a cleaner environment.

The WebDriver is initialized using WebDriver Manager to automatically download and configure the appropriate ChromeDriver version.

### 2. **Opening the Browser**

The script:

- Opens the browser with the URL `https://link.com`.
- Stores the initial tab's handle to ensure it remains open.

### 3. **Loop for Tab Management**

Inside a loop:

- A new tab is opened with the specified URL.
- The script switches to the new tab and immediately closes it if it’s not the initial tab.
- It ensures the first tab remains active throughout.

### 4. **Graceful Exit**

The loop can be interrupted using `Ctrl+C`, which triggers a graceful shutdown by closing all tabs and quitting the browser.

## Code Structure

Here is a brief summary of the code:

```python
# Set up Chrome options
options = Options()
options.add_argument("--start-maximized")
options.add_argument("--disable-extensions")

# Configure WebDriver service
service = Service(ChromeDriverManager().install())

# Initialize WebDriver
driver = webdriver.Chrome(service=service, options=options)

# Open the initial tab
driver.get("https://link.com")
first_tab_handle = driver.current_window_handle

# Tab management loop
try:
    while True:
        driver.execute_script("window.open('https://link.com', '_blank');")
        time.sleep(.5)
        handles = driver.window_handles
        driver.switch_to.window(handles[-1])
        if handles[-1] != first_tab_handle:
            driver.close()
        driver.switch_to.window(first_tab_handle)
except KeyboardInterrupt:
    print("Exiting...")
    driver.quit()
```

## Use Cases

1. **Tab Management Simulation**: Simulate tab opening and closing for testing or demonstration purposes.
2. **Load Testing**: Test how a website handles rapid tab opening and closing.

## Notes

- Ensure you have an active internet connection for the WebDriver Manager to download the necessary files.
- Modify the `driver.get` URL to automate other websites.
- Adjust the `time.sleep` duration for different speeds.

## Licensing

This script is distributed under the MIT License. Feel free to modify and use it in your projects.

---

### You can make `requirements.txt`:

```
selenium
webdriver-manager
```

