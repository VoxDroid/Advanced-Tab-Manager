import time
import random
import socket
import os
import shutil
import stat
import subprocess
import psutil
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class BrowserThread(QThread):
    update_status = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    update_cycle = pyqtSignal(int)
    log_message = pyqtSignal(str, str)
    error_occurred = pyqtSignal(str)

    def __init__(self, url, iterations, interval, browser_options, instance_id, browser_type='chrome', translations=None):
        super().__init__()
        self.url = url
        self.iterations = iterations
        self.interval = interval
        self.browser_options = browser_options
        self.browser_type = browser_type.lower()
        self.is_running = True
        self.driver = None
        self.port = random.randint(9515, 9599)
        self.service = None  # Initialize later in run() to avoid blocking UI
        self.driver_process = None
        self.browser_processes = []  # Will contain only specific processes we create
        self.instance_id = instance_id
        self.translations = translations or {}
        self.progress = 0
        self.cycle = 0
        self.stop_requested = False  # Flag to prevent error emissions during stop

        # Priority will be set in run() method after thread starts

    def is_driver_valid(self):
        """Check if the WebDriver is in a valid state for operations."""
        return (self.driver is not None and
                hasattr(self.driver, 'execute_script') and
                hasattr(self.driver, 'window_handles') and
                hasattr(self.driver, 'switch_to') and
                hasattr(self.driver, 'close'))

    def _verify_executable(self, path):
        """Verify a downloaded driver is an executable and runnable.
        Returns True if the binary looks valid, False for known Exec-format errors.
        """
        try:
            if not os.path.isfile(path):
                return False

            # Ensure executable bit is set where possible
            try:
                if not os.access(path, os.X_OK):
                    os.chmod(path, 0o755)
            except Exception:
                pass

            # Run `--version` to detect architecture/format issues quickly
            subprocess.run([path, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=True)
            return True
        except subprocess.CalledProcessError:
            # Binary ran but returned non-zero; treat as valid for our purposes
            return True
        except OSError as e:
            # Errno 8 == Exec format error on POSIX systems
            if getattr(e, 'errno', None) == 8 or 'exec format' in str(e).lower():
                return False
            raise
        except Exception:
            return False

    def _install_driver(self, browser_type: str):
        """Install driver via webdriver-manager and sanity-check the binary.
        Falls back to a driver found in PATH if the downloaded binary appears invalid.
        Raises OSError on unrecoverable failures.
        """
        if browser_type == 'chrome':
            path = ChromeDriverManager().install()
        elif browser_type == 'firefox':
            path = GeckoDriverManager().install()
        else:
            raise ValueError(f"Unsupported browser type: {browser_type}")

        # Verify downloaded binary; attempt alternate-arch binaries in the same release folder,
        # then fallback to PATH if mismatch (common on mac M1/x86 mismatch).
        if not self._verify_executable(path):
            # 1) Try to find alternate architecture binaries in the same release directory
            try:
                release_dir = os.path.dirname(os.path.dirname(path))
                if os.path.isdir(release_dir):
                    for entry in os.listdir(release_dir):
                        candidate_dir = os.path.join(release_dir, entry)
                        candidate_path = os.path.join(candidate_dir, os.path.basename(path))
                        if candidate_path == path:
                            continue
                        if os.path.isfile(candidate_path) and self._verify_executable(candidate_path):
                            self.log_message.emit(self.translations.get("log_found_alternative_driver", "Found usable driver binary for alternative architecture: {path}").format(path=candidate_path), "WARNING")
                            return candidate_path
            except Exception:
                pass

            # 2) Fallback to driver in PATH
            fallback = shutil.which('chromedriver' if browser_type == 'chrome' else 'geckodriver')
            if fallback and self._verify_executable(fallback):
                self.log_message.emit(self.translations.get("log_driver_fallback_path", "Downloaded driver binary appears incompatible; falling back to driver found in PATH: {path}").format(path=fallback), "WARNING")
                return fallback

            # 3) Nothing usable found — surface a clear OSError so caller can report it
            raise OSError(f"Downloaded driver binary appears unusable (possible architecture mismatch): {path}")

        return path

    def _try_reinitialize_driver(self):
        """Attempt to reinitialize the WebDriver if it became invalid."""
        # Don't reinitialize if stop was requested
        if not self.is_running:
            return False

        try:
            self.log_message.emit(self.translations.get("log_reinitialize_attempt", "Attempting to reinitialize WebDriver for instance {instance_id}").format(instance_id=self.instance_id), "WARNING")

            # Clean up existing driver if any
            if self.driver:
                try:
                    self.driver.quit()
                except:
                    pass
                self.driver = None

            # Clean up service if needed
            if self.service:
                try:
                    self.service.stop()
                except:
                    pass

            # Reinitialize service
            if self.browser_type == 'chrome':
                driver_path = self._install_driver('chrome')
                self.service = ChromeService(driver_path, port=self.port)
            elif self.browser_type == 'firefox':
                driver_path = self._install_driver('firefox')
                self.service = FirefoxService(driver_path, port=self.port)

            # Start service (handle Exec format / architecture mismatches cleanly)
            try:
                self.service.start()
            except OSError as e:
                if getattr(e, 'errno', None) == 8 or 'exec format' in str(e).lower():
                    # Known cause: wrong architecture binary (e.g. arm64 vs x86_64 on macOS)
                    self.log_message.emit(self.translations.get("log_exec_format_error", "Exec format error starting driver — binary architecture mismatch or invalid executable."), "ERROR")
                    return False
                raise

            if not self.wait_for_service(port=self.service.port, timeout=15):  # Longer timeout for reinitialization
                return False

            # Create new driver
            if self.browser_type == 'chrome':
                driver = webdriver.Remote(
                    command_executor=f"http://127.0.0.1:{self.service.port}",
                    options=self.browser_options
                )
            elif self.browser_type == 'firefox':
                driver = webdriver.Remote(
                    command_executor=f"http://127.0.0.1:{self.service.port}",
                    options=self.browser_options
                )

            self.driver = driver
            self.driver.get(self.url)  # Reopen initial tab

            self.log_message.emit(self.translations.get("log_reinitialize_success", "Successfully reinitialized WebDriver for instance {instance_id}").format(instance_id=self.instance_id), "INFO")
            return True

        except Exception as e:
            self.log_message.emit(self.translations.get("log_reinitialize_failed", "Failed to reinitialize WebDriver for instance {instance_id}: {error}").format(instance_id=self.instance_id, error=str(e)), "ERROR")
            return False

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
            # Set thread priority after thread has started
            self.setPriority(QThread.Priority.NormalPriority)

            # Add startup delay to prevent all instances from starting simultaneously
            startup_delay = self.instance_id * 0.5  # 0.5 seconds between each instance
            if startup_delay > 0:
                time.sleep(startup_delay)

            self.log_message.emit(self.translations.get("log_browser_thread_start", "Starting browser thread for instance {instance_id} on port {port}").format(instance_id=self.instance_id, port=self.port), "INFO")

            # Create service in background thread to avoid blocking UI
            if self.browser_type == 'chrome':
                driver_path = self._install_driver('chrome')
                self.service = ChromeService(driver_path, port=self.port)
            elif self.browser_type == 'firefox':
                driver_path = self._install_driver('firefox')
                self.service = FirefoxService(driver_path, port=self.port)
            else:
                raise ValueError(f"Unsupported browser type: {self.browser_type}")

            if self.is_port_in_use(self.port):
                self.port = self.find_available_port()
                self.service.port = self.port
                self.log_message.emit(self.translations.get("log_port_in_use", "Port {old_port} was in use, switching to new port {new_port}").format(old_port=self.port, new_port=self.port), "WARNING")

            try:
                self.service.start()
            except OSError as e:
                if getattr(e, 'errno', None) == 8 or 'exec format' in str(e).lower():
                    self.error_occurred.emit(f"Exec format error when starting driver for instance {self.instance_id}: {str(e)}")
                    self.log_message.emit(self.translations.get("log_exec_format_error", "Exec format error starting driver — binary architecture mismatch or invalid executable."), "ERROR")
                    return
                raise

            if not self.wait_for_service(port=self.service.port):
                raise WebDriverException(f"{self.browser_type.capitalize()}Driver service failed to start on port {self.service.port} for instance {self.instance_id}")

            try:
                # Add connection stability options for Linux
                import platform
                connection_timeout = 30  # seconds
                if platform.system() == 'Linux':
                    connection_timeout = 60  # Longer timeout on Linux for stability
                
                if self.browser_type == 'chrome':
                    driver = webdriver.Remote(
                        command_executor=f"http://127.0.0.1:{self.service.port}",
                        options=self.browser_options,
                        keep_alive=True  # Keep connection alive
                    )
                elif self.browser_type == 'firefox':
                    driver = webdriver.Remote(
                        command_executor=f"http://127.0.0.1:{self.service.port}",
                        options=self.browser_options,
                        keep_alive=True  # Keep connection alive
                    )
                
                # Set implicit wait for better stability
                driver.implicitly_wait(10)
                
                self.driver = driver
            except WebDriverException as e:
                error_msg = str(e).lower()
                # Provide more specific error messages for common issues
                if "chrome instance exited" in error_msg:
                    self.log_message.emit(self.translations.get("log_browser_exited_immediately", "Chrome browser instance exited immediately. This usually indicates:"), "ERROR")
                    self.log_message.emit(self.translations.get("log_chrome_binary_not_found_error", "  - Chrome binary not found at: {binary}").format(binary=getattr(self.browser_options, 'binary_location', 'Not set')), "ERROR")
                    self.log_message.emit(self.translations.get("log_chrome_version_incompatible", "  - Chrome version incompatible with ChromeDriver"), "ERROR")
                    self.log_message.emit(self.translations.get("log_conflicting_arguments", "  - Conflicting Chrome command line arguments"), "ERROR")
                    self.log_message.emit(self.translations.get("log_conflicting_profile", "  - Chrome already running with conflicting profile"), "ERROR")
                elif "session not created" in error_msg:
                    self.log_message.emit(self.translations.get("log_session_creation_failed", "WebDriver session creation failed. Check browser version compatibility."), "ERROR")
                elif "executable needs to be in path" in error_msg:
                    self.log_message.emit(self.translations.get("log_executable_not_found", "Browser executable not found in PATH or specified location."), "ERROR")
                else:
                    self.log_message.emit(self.translations.get("log_webdriver_init_error", "WebDriver initialization error: {error}").format(error=str(e)), "ERROR")
                
                self.error_occurred.emit(f"Failed to initialize WebDriver for instance {self.instance_id}: {str(e)}")
                self.log_message.emit(self.translations.get("log_failed_init_webdriver", "Failed to initialize WebDriver for instance {instance_id}: {error}").format(instance_id=self.instance_id, error=str(e)), "ERROR")
                return

            try:
                if hasattr(self.service, 'process') and getattr(self.service, 'process') is not None and getattr(self.service.process, 'pid', None):
                    self.driver_process = psutil.Process(self.service.process.pid)
                else:
                    self.driver_process = None
                    self.log_message.emit(self.translations.get("log_no_service_process", "No Service.process attribute available; skipping process tracking for instance {instance_id}").format(instance_id=self.instance_id), "WARNING")
            except Exception as e:
                self.driver_process = None
                self.log_message.emit(self.translations.get("log_cannot_track_process", "Could not track browser process for instance {instance_id}: {error}").format(instance_id=self.instance_id, error=str(e)), "WARNING")

            # Track only the specific browser process we created, not all browser processes
            try:
                # Get the browser process associated with this WebDriver session
                browser_pid = None
                if self.browser_type == 'chrome':
                    # Use psutil to find child processes more reliably
                    try:
                        children = self.driver_process.children(recursive=True)
                        # Find the main chrome process (usually the one with --type=renderer or similar)
                        for child in children:
                            if 'chrome' in child.name().lower():
                                browser_pid = child.pid
                                break
                        # If no specific renderer found, use the first child
                        if not browser_pid and children:
                            browser_pid = children[0].pid
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                elif self.browser_type == 'firefox':
                    # Firefox usually runs as a single process. Guard access to service.process.
                    browser_pid = None
                    if hasattr(self.service, 'process') and getattr(self.service, 'process') is not None:
                        try:
                            browser_pid = self.service.process.pid
                        except Exception:
                            browser_pid = None

                if browser_pid:
                    self.browser_processes = [psutil.Process(browser_pid)]
                else:
                    self.browser_processes = []
            except Exception as e:
                self.log_message.emit(self.translations.get("log_cannot_track_process", "Could not track browser process for instance {instance_id}: {error}").format(instance_id=self.instance_id, error=str(e)), "WARNING")
                self.browser_processes = []

            try:
                self.driver.get(self.url)
                first_tab_handle = self.driver.current_window_handle
                self.log_message.emit(self.translations.get("log_opened_initial_tab", "Opened initial tab with URL: {url} for instance {instance_id}").format(url=self.url, instance_id=self.instance_id), "INFO")

                iteration = 0
                consecutive_errors = 0  # Track consecutive errors for performance optimization
                while self.is_running and (self.iterations == 0 or iteration < self.iterations):
                    # Emergency check: if stop was called, exit immediately
                    if not self.is_running or self.driver is None:
                        break

                    if not self.is_driver_valid():
                        self.error_occurred.emit(f"WebDriver is invalid or None for instance {self.instance_id}, cannot proceed with tab operations")
                        self.log_message.emit(self.translations.get("log_webdriver_invalid", "WebDriver is invalid or None for instance {instance_id}, cannot proceed with tab operations").format(instance_id=self.instance_id), "ERROR")
                        break

                    try:
                        # Interruptible sleep for faster stop response
                        total_sleep = max(0.05, self.interval)
                        sleep_step = 0.05  # Check every 50ms for very fast response
                        slept = 0.0
                        while slept < total_sleep and self.is_running and self.driver is not None:
                            time.sleep(min(sleep_step, total_sleep - slept))
                            slept += sleep_step

                        # Double-check driver is still valid before executing script
                        if not self.is_driver_valid():
                            if not self.stop_requested:
                                self.error_occurred.emit(f"WebDriver became invalid before script execution for instance {self.instance_id}")
                                self.log_message.emit(self.translations.get("log_webdriver_invalid_before_script", "WebDriver became invalid before script execution for instance {instance_id}").format(instance_id=self.instance_id), "ERROR")
                            # Try to reinitialize driver
                            if self._try_reinitialize_driver():
                                continue  # Skip this iteration and try again
                            else:
                                break  # Give up if reinitialization fails

                        # Execute script with retry logic for connection issues
                        max_script_retries = 3
                        script_retry_count = 0
                        script_success = False
                        
                        while script_retry_count < max_script_retries and not script_success:
                            try:
                                self.driver.execute_script(f"window.open('{self.url}', '_blank');")
                                script_success = True
                            except Exception as script_e:
                                script_retry_count += 1
                                error_str = str(script_e).lower()
                                
                                # Check if this is a connection-related error that we should retry
                                connection_errors = ['connection aborted', 'remote end closed', 'connection reset', 'broken pipe', 'connection refused']
                                is_connection_error = any(err in error_str for err in connection_errors)
                                
                                if is_connection_error and script_retry_count < max_script_retries:
                                    self.log_message.emit(f"Connection error during script execution for instance {self.instance_id}, retrying ({script_retry_count}/{max_script_retries}): {str(script_e)}", "WARNING")
                                    time.sleep(1)  # Brief pause before retry
                                    continue
                                else:
                                    # Re-raise the exception if it's not a connection error or we've exhausted retries
                                    raise script_e

                        # Check driver validity after script execution
                        if not self.is_driver_valid():
                            if not self.stop_requested:
                                self.error_occurred.emit(f"WebDriver became invalid after script execution for instance {self.instance_id}")
                                self.log_message.emit(self.translations.get("log_webdriver_invalid_after_script", "WebDriver became invalid after script execution for instance {instance_id}").format(instance_id=self.instance_id), "ERROR")
                            # Try to reinitialize driver
                            if self._try_reinitialize_driver():
                                continue  # Skip this iteration and try again
                            else:
                                break  # Give up if reinitialization fails

                        handles = self.driver.window_handles
                        if not handles:
                            self.log_message.emit(self.translations.get("log_no_window_handles", "No window handles found for instance {instance_id}, skipping tab operation").format(instance_id=self.instance_id), "WARNING")
                            continue

                        new_tab_handle = handles[-1]
                        self.driver.switch_to.window(new_tab_handle)

                        # Wait for the page to fully load
                        try:
                            WebDriverWait(self.driver, 10).until(
                                lambda driver: driver.execute_script("return document.readyState") == "complete"
                            )
                        except Exception as e:
                            error_msg = str(e).lower()
                            # Suppress warnings for discarded browsing contexts and invalid sessions (tab/browser closed manually)
                            suppress_keywords = ['browsing context has been discarded', 'session does not exist', 'invalid session', 'marionette', 'no such window']
                            should_suppress = any(keyword in error_msg for keyword in suppress_keywords)
                            if not should_suppress and not self.stop_requested:
                                self.log_message.emit(self.translations.get("log_timeout_waiting_page_load", "Timeout waiting for page to load in instance {instance_id}: {error}").format(instance_id=self.instance_id, error=str(e)), "WARNING")

                        if new_tab_handle != first_tab_handle:
                            # Double-check driver is still valid before closing tab
                            if self.is_driver_valid():
                                self.driver.close()
                            else:
                                self.log_message.emit(f"Driver became invalid before closing tab for instance {self.instance_id}", "WARNING")
                                break

                        # Double-check driver is still valid before switching back
                        if self.is_driver_valid():
                            self.driver.switch_to.window(first_tab_handle)
                        else:
                            self.log_message.emit(f"Driver became invalid before switching window for instance {self.instance_id}", "WARNING")
                            break

                        iteration += 1
                        consecutive_errors = 0  # Reset error counter on success

                        # Update cycle and progress accurately
                        self.cycle = iteration
                        if self.iterations > 0:
                            self.progress = (iteration / self.iterations) * 100
                        else:
                            self.progress = iteration % 100  # Cycle 0-99 for infinite iterations

                        # Emit signals every iteration for accurate monitoring
                        self.update_status.emit(f"Instance {self.instance_id}: {len(handles)} tabs open!")
                        self.update_progress.emit(self.progress)
                        self.update_cycle.emit(self.cycle)
                        self.log_message.emit(f"Instance {self.instance_id}, Cycle {iteration}: Opened new tab, total tabs: {len(handles)}", "INFO")
                    except WebDriverException as e:
                        consecutive_errors += 1
                        # Suppress marionette errors (Firefox connection lost), connection errors, and errors during shutdown
                        error_msg = str(e).lower()
                        should_suppress = (self.stop_requested or 'marionette' in error_msg or 'connection' in error_msg or 
                                         'remote end closed' in error_msg or 'connection aborted' in error_msg or
                                         'connection reset' in error_msg or 'broken pipe' in error_msg)
                        
                        is_connection_error = ('connection aborted' in error_msg or 'remote end closed' in error_msg or 
                                             'connection reset' in error_msg or 'broken pipe' in error_msg)
                        
                        if not should_suppress:
                            self.error_occurred.emit(f"Browser error for instance {self.instance_id}: {str(e)}")
                            self.log_message.emit(f"Browser error occurred for instance {self.instance_id}: {str(e)}", "ERROR")

                        # Try to recover from connection errors
                        if is_connection_error and not self.stop_requested:
                            if self._try_reinitialize_driver():
                                self.log_message.emit(f"Driver recovered from WebDriver connection error for instance {self.instance_id}, continuing", "INFO")
                                continue  # Continue the while loop with the new driver
                            else:
                                self.log_message.emit(f"Failed to recover from WebDriver connection error for instance {self.instance_id}: {str(e)}", "ERROR")
                                return

                        # Performance optimization: if too many consecutive errors, add delay
                        if consecutive_errors > 3:
                            time.sleep(1.0)  # Prevent rapid error loops
                        break
                    except Exception as e:
                        consecutive_errors += 1
                        error_msg = str(e).lower()
                        is_connection_error = ('connection aborted' in error_msg or 'remote end closed' in error_msg or 
                                             'connection reset' in error_msg or 'broken pipe' in error_msg)
                        
                        if not self.stop_requested:
                            if is_connection_error:
                                self.log_message.emit(f"Connection error during tab operation for instance {self.instance_id}, attempting recovery: {str(e)}", "WARNING")
                                # Try to reinitialize the driver for connection errors
                                if self._try_reinitialize_driver():
                                    self.log_message.emit(f"Driver recovered from connection error for instance {self.instance_id}, continuing", "INFO")
                                    continue  # Continue the while loop with the new driver
                                else:
                                    self.error_occurred.emit(f"Failed to recover from connection error for instance {self.instance_id}: {str(e)}")
                                    self.log_message.emit(f"Failed to recover from connection error for instance {self.instance_id}: {str(e)}", "ERROR")
                                    return
                            else:
                                self.error_occurred.emit(f"Unexpected error during tab operation for instance {self.instance_id}: {str(e)}")
                                self.log_message.emit(f"Unexpected error during tab operation for instance {self.instance_id}: {str(e)}", "ERROR")

                        # Performance optimization: if too many consecutive errors, add delay
                        if consecutive_errors > 3:
                            time.sleep(1.0)  # Prevent rapid error loops
                        break

            except Exception as e:
                if not self.stop_requested:
                    self.error_occurred.emit(f"Critical error during tab operations for instance {self.instance_id}: {str(e)}")
                    self.log_message.emit(f"Critical error during tab operations for instance {self.instance_id}: {str(e)}", "ERROR")
                return

        except Exception as e:
            if not self.stop_requested:
                self.error_occurred.emit(f"Critical error for instance {self.instance_id}: {str(e)}")
                self.log_message.emit(f"Critical error in thread for instance {self.instance_id}: {str(e)}", "ERROR")
        finally:
            self.cleanup()
            # Memory optimization: force garbage collection
            import gc
            gc.collect()

    def cleanup(self):
        """Synchronous cleanup to prevent timer threading issues."""
        def cleanup_driver():
            try:
                if self.driver:
                    try:
                        # Check if driver has required attributes before accessing them
                        if hasattr(self.driver, 'session_id') and self.driver.session_id is not None:
                            self.driver.session_id = None
                            if hasattr(self.driver, 'close'):
                                self.driver.close()
                            if hasattr(self.driver, 'quit'):
                                self.driver.quit()
                        else:
                            self.log_message.emit(f"Driver session is invalid for instance {self.instance_id}, skipping graceful quit", "WARNING")
                    except Exception as e:
                        # Suppress cleanup errors during shutdown or for expected failures
                        if not self.stop_requested and 'NoneType' not in str(e):
                            self.log_message.emit(f"Failed to quit driver gracefully for instance {self.instance_id}: {str(e)}", "WARNING")
                    finally:
                        self.driver = None
            except Exception as e:
                # Catch any unexpected errors in cleanup_driver
                self.log_message.emit(f"Critical error in driver cleanup for instance {self.instance_id}: {str(e)}", "ERROR")
                self.driver = None

        def cleanup_service():
            try:
                if self.service:
                    # Some Service instances never populated `.process` if start() failed — avoid calling
                    # stop() in that case because selenium's stop() implementation may expect `.process` to exist.
                    if hasattr(self.service, 'process') and getattr(self.service, 'process'):
                        try:
                            self.service.stop()
                        except Exception as e:
                            self.log_message.emit(f"Failed to stop service for instance {self.instance_id}: {str(e)}", "WARNING")
                    else:
                        # Nothing to stop; avoid invoking stop() which may access `.process` internally.
                        self.log_message.emit(self.translations.get("log_service_no_process", "Service has no running process for instance {instance_id}, skipping stop").format(instance_id=self.instance_id), "INFO")
            except Exception as e:
                self.log_message.emit(f"Failed to stop service for instance {self.instance_id}: {str(e)}", "WARNING")

        # Call cleanup functions synchronously to avoid timer threading issues
        cleanup_driver()
        cleanup_service()
        # Call process termination synchronously
        self._terminate_processes_sync()

    def _terminate_processes_sync(self):
        """Synchronously terminate ChromeDriver and Chrome processes."""
        def terminate_process(proc):
            if proc is None:
                return
            try:
                if proc.is_running():
                    proc.terminate()
                    # Reduce timeout for faster cleanup
                    proc.wait(timeout=2)
            except (psutil.TimeoutExpired, psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    if proc and proc.is_running():
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        try:
            # Terminate processes more efficiently
            if self.driver_process:
                # Also terminate all children of the driver process
                try:
                    children = self.driver_process.children(recursive=True)
                    for child in children:
                        terminate_process(child)
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    pass
                terminate_process(self.driver_process)
                self.driver_process = None

            # Only terminate the specific browser processes we tracked
            for proc in self.browser_processes[:]:  # Copy list to avoid modification issues
                terminate_process(proc)

            self.browser_processes.clear()  # Clear list to prevent re-termination
        except Exception as e:
            self.log_message.emit(f"Error in terminate_processes_sync for instance {self.instance_id}: {str(e)}", "ERROR")
        """Asynchronously terminate ChromeDriver and Chrome processes to prevent UI freezing."""
        def terminate_process(proc):
            if proc is None:
                return
            try:
                if proc.is_running():
                    proc.terminate()
                    # Reduce timeout for faster cleanup
                    proc.wait(timeout=2)
            except (psutil.TimeoutExpired, psutil.NoSuchProcess, psutil.AccessDenied):
                try:
                    if proc and proc.is_running():
                        proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass  # Process already terminated or access denied

        try:
            # Terminate processes more efficiently
            if self.driver_process:
                # Also terminate all children of the driver process
                try:
                    children = self.driver_process.children(recursive=True)
                    for child in children:
                        QTimer.singleShot(0, lambda p=child: terminate_process(p))
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    pass
                QTimer.singleShot(0, lambda: terminate_process(self.driver_process))
                self.driver_process = None

            # Only terminate the specific browser processes we tracked
            for proc in self.browser_processes[:]:  # Copy list to avoid modification issues
                QTimer.singleShot(0, lambda p=proc: terminate_process(p))

            self.browser_processes.clear()  # Clear list to prevent re-termination
        except Exception as e:
            self.log_message.emit(f"Error in terminate_processes_async for instance {self.instance_id}: {str(e)}", "ERROR")

    def stop(self):
        """Immediate and robust stop of all browser operations."""
        self.is_running = False
        self.stop_requested = True  # Prevent error emissions during shutdown
        # Kill switch: immediately invalidate the driver to prevent any further operations
        self.driver = None
        self.log_message.emit(f"Emergency stop activated for instance {self.instance_id}", "WARNING")

        # Immediate process termination for faster cleanup
        self._immediate_process_kill()

        # Force thread exit immediately
        if self.isRunning():
            self.exit(0)
            # Schedule terminate as backup after a short delay
            QTimer.singleShot(10, lambda: self.terminate() if self.isRunning() else None)

        # Schedule cleanup asynchronously for any remaining tasks
        QTimer.singleShot(0, self.cleanup)

    def _immediate_process_kill(self):
        """Kill processes immediately without waiting."""
        def kill_process(proc):
            if proc is None:
                return
            try:
                if proc.is_running():
                    proc.kill()  # Immediate kill instead of terminate
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        try:
            # Kill driver process immediately
            if self.driver_process:
                kill_process(self.driver_process)
                # Kill all children immediately
                try:
                    children = self.driver_process.children(recursive=True)
                    for child in children:
                        kill_process(child)
                except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                    pass

            # Kill tracked browser processes
            for proc in self.browser_processes[:]:
                kill_process(proc)

            self.browser_processes.clear()
        except Exception as e:
            self.log_message.emit(f"Error in immediate process kill for instance {self.instance_id}: {str(e)}", "ERROR")