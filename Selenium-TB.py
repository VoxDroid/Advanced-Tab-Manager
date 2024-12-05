import time
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Set up Chrome options
options = Options()
options.add_argument("--start-maximized")  # Start browser maximized
options.add_argument("--disable-extensions")

# Automatically download the correct ChromeDriver version
service = Service(ChromeDriverManager().install())

# Create the main driver instance
driver = webdriver.Chrome(service=service, options=options)

# Open the first tab with the desired URL
driver.get("https://google.com/")

# Store the first window handle to ensure it remains open
first_tab_handle = driver.current_window_handle

# Loop to open and close tabs
try:
    while True:
        # Open a new tab
        driver.execute_script("window.open('https://google.com/', '_blank');")
        
        # Wait for 1 second
        time.sleep(.5)
        
        # Get the list of window handles (tabs)
        handles = driver.window_handles

        # Switch to the latest opened tab
        new_tab_handle = handles[-1]
        driver.switch_to.window(new_tab_handle)

        # Close the current tab (not the first one)
        if new_tab_handle != first_tab_handle:
            driver.close()  # Close the newly opened tab
        else:
            print("Trying to close the first tab, skipping.")

        # Ensure that the first tab remains open
        driver.switch_to.window(first_tab_handle)

        # Print how many tabs are open
        handles = driver.window_handles
        print(f"{len(handles)} tabs open!")

        # Optional: Add a condition to stop after a set amount of time or iterations

except KeyboardInterrupt:
    # Allow graceful exit with Ctrl+C
    print("Exiting...")
    driver.quit()  # Close all tabs and the browser
