# Advanced Tab Manager Pro

![GitHub release (latest by date)](https://img.shields.io/github/v/release/VoxDroid/Advanced-Tab-Manager?label=Latest%20Release&style=flat-square)
![GitHub license](https://img.shields.io/github/license/VoxDroid/Advanced-Tab-Manager?style=flat-square)
![GitHub issues](https://img.shields.io/github/issues/VoxDroid/Advanced-Tab-Manager?style=flat-square)
![GitHub stars](https://img.shields.io/github/stars/VoxDroid/Advanced-Tab-Manager?style=flat-square)
![GitHub forks](https://img.shields.io/github/forks/VoxDroid/Advanced-Tab-Manager?style=flat-square)
![Python Version](https://img.shields.io/badge/Python-3.8%2B-blue?style=flat-square)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-green?style=flat-square)

---

## 📖 Overview

**Advanced Tab Manager Pro** is a sophisticated desktop application designed to automate browser tab management using Python, PyQt6, and Selenium. This tool enables users to open and close Chrome tabs programmatically with extensive customization options, including multiple browser instances, proxy settings, and real-time system monitoring. Featuring a modern GUI with multilingual support and customizable themes, it’s perfect for developers, testers, and automation enthusiasts looking to streamline repetitive browser tasks.

---

## ✨ Features

- **Multi-Instance Tab Management**: Run multiple Chrome instances simultaneously.
- **Customizable Browser Options**: Headless mode, incognito, proxy support, and more.
- **Multilingual Interface**: Supports English, Japanese, Korean, Chinese, and Filipino.
- **Theme Variety**: Six distinct themes (Dark Navy, Light Blue, Dark Green, Light Green, Soft Pink, Soft Lavender).
- **Real-Time Monitoring**: Track CPU, memory, and disk usage.
- **Detailed Logging**: Color-coded logs with filtering and export capabilities.
- **Advanced Settings**: Configure user agents, proxy servers, and additional Chrome arguments.
- **System Tray Integration**: Minimize to tray (planned feature).
- **Cross-Platform**: Works on Windows, Linux, and macOS with minor adjustments.

---

## 🚀 Installation

### Prerequisites

- **Python 3.8+**: Ensure Python is installed.
- **Pip**: Python package manager (typically included with Python).
- **Chrome Browser**: Required for Selenium WebDriver.

### Steps

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/VoxDroid/Advanced-Tab-Manager.git
   cd Advanced-Tab-Manager
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   *Note*: If `requirements.txt` isn’t present, manually install:
   ```bash
   pip install PyQt6 selenium psutil qtawesome webdriver-manager requests
   ```

3. **Run the Application**:
   ```bash
   python app.py
   ```
   - This launches the GUI and automatically installs the ChromeDriver via `webdriver-manager`.

---

## 📋 Usage

### Main Interface

| Tab          | Description                                      |
|--------------|--------------------------------------------------|
| **Main**     | Configure URL, instances, and start/stop tasks.  |
| **Advanced** | Customize Chrome options and proxy settings.    |
| **Settings** | Adjust theme, language, and font size.          |
| **System**   | View real-time system stats.                    |
| **Logs**     | Monitor detailed logs with filters.             |
| **About**    | Application details and license info.           |

### Starting a Tab Task

1. **Main Tab**:
   - Enter a URL (e.g., `https://google.com`).
   - Set iterations (0 for infinite), interval (seconds), and number of instances.
   - Click "Start" to begin.

2. **Advanced Tab** (Optional):
   - Enable headless mode, incognito, or proxy settings.

3. **Monitor Progress**:
   - Check status, cycles, and logs in real-time.

---

## 🎨 Customization

### Themes

Select from six visually appealing themes:
- **Dark Navy** (Default)
- **Light Blue**
- **Dark Green**
- **Light Green**
- **Soft Pink**
- **Soft Lavender**

Adjust in the **Settings Tab** under "Theme".

### Languages

Supported languages:
- English
- Japanese (日本語)
- Korean (한국어)
- Chinese (中文)
- Filipino (Tagalog)

Set in the **Settings Tab** under "Language".

---

## 🛠️ Technical Details

### Dependencies

| Package            | Purpose                     |
|--------------------|-----------------------------|
| PyQt6             | GUI framework              |
| Selenium          | Browser automation         |
| psutil            | System monitoring          |
| qtawesome         | Icon library               |
| webdriver-manager | ChromeDriver management    |
| requests          | HTTP requests (unused)     |

### File Structure

```
Advanced-Tab-Manager/
├── app.py                # Main application script
└── README.md              # Documentation
```

*Note*: Additional files (e.g., font files) may be added in future updates.

---

## 🌟 Contributing

Contributions are encouraged! Here’s how to contribute:

1. **Fork the Repository**: Click "Fork" on GitHub.
2. **Clone Your Fork**:
   ```bash
   git clone https://github.com/VoxDroid/Advanced-Tab-Manager.git
   ```
3. **Create a Branch**:
   ```bash
   git checkout -b feature/your-feature
   ```
4. **Make Changes**: Add features or fix bugs.
5. **Commit and Push**:
   ```bash
   git add .
   git commit -m "Describe your changes"
   git push origin feature/your-feature
   ```
6. **Submit a Pull Request**: Open a PR on GitHub.

### Guidelines

- Adhere to PEP 8 for Python code.
- Test locally before submitting.
- Update this README if new features are added.

---

## 🐛 Issues and Support

Encountered a problem? Need help?

- **Open an Issue**: Visit [Issues](https://github.com/VoxDroid/Advanced-Tab-Manager/issues).
- **Contact**: Use GitHub Discussions or reach out directly (if contact info is provided).

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](https://github.com/VoxDroid/Advanced-Tab-Manager?tab=MIT-1-ov-file) file for details.

---

## 🙌 Acknowledgments

- **PyQt6 Team**: For a robust GUI framework.
- **Selenium Project**: For powerful browser automation.
- **qtawesome**: For FontAwesome icon integration.
- **webdriver-manager**: For seamless ChromeDriver management.

---

## 📈 Roadmap

- [ ] Add drag-and-drop URL support.
- [ ] Implement system tray functionality.
- [ ] Enhance proxy settings with authentication.
- [ ] Add more language translations.
- [ ] Support additional browsers (e.g., Firefox).

---

## 📊 Stats

![GitHub commit activity](https://img.shields.io/github/commit-activity/m/VoxDroid/Advanced-Tab-Manager?style=flat-square)
![GitHub last commit](https://img.shields.io/github/last-commit/VoxDroid/Advanced-Tab-Manager?style=flat-square)
![Contributors](https://img.shields.io/github/contributors/VoxDroid/Advanced-Tab-Manager?style=flat-square)

---

## 💡 Tips and Tricks

- **Infinite Loops**: Set "Iterations" to 0 for continuous tab cycling.
- **Resource Management**: Use fewer instances on low-spec systems.
- **Headless Mode**: Enable for faster, UI-free operation.
- **Log Filtering**: Toggle log levels in the Logs tab for focused debugging.

---

## 📸 Screenshots

### Main Tab
![Main Tab](assets/screenshots/atm_MAIN.png)

### Advanced Tab
![Advanced tab](assets/screenshots/atm_ADVANCED.png)

### Settings Tab
![Settings Tab](assets/screenshots/atm_SETTINGS.png)

### System Tab
![System Tab](assets/screenshots/atm_SYSTEM.png)

### Logs Tab
![Logs Tab](assets/screenshots/atm_LOGS.png)

---

## 🔗 Links

- **Repository**: [github.com/VoxDroid/Advanced-Tab-Manager](https://github.com/VoxDroid/Advanced-Tab-Manager)
- **Issues**: [github.com/VoxDroid/Advanced-Tab-Manager/issues](https://github.com/VoxDroid/Advanced-Tab-Manager/issues)
- **Author**: [VoxDroid](https://github.com/VoxDroid)

---

## 🎉 Final Words

Thank you for exploring **Advanced Tab Manager Pro**! This tool aims to make browser automation accessible and efficient. If it helps your workflow, please star the repository and share your feedback. Happy automating! 🚀

---