# Contributing to Advanced Tab Manager Pro

Thank you for your interest in contributing to **Advanced Tab Manager Pro**! This project thrives on community contributions, whether through code, documentation, translations, or feedback. This document outlines the guidelines for contributing to ensure a smooth and collaborative process.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Setting Up the Development Environment](#setting-up-the-development-environment)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Improving Documentation](#improving-documentation)
- [Style Guidelines](#style-guidelines)

## Code of Conduct

All contributors are expected to adhere to the [Code of Conduct](https://github.com/VoxDroid/Advanced-Tab-Manager/blob/main/CODE_OF_CONDUCT.md). By participating, you agree to foster an inclusive and respectful environment.

## How to Contribute

Contributions can take many forms, including:

- **Code**: Add new features, fix bugs, or improve performance.
- **Documentation**: Enhance the [README](https://github.com/VoxDroid/Advanced-Tab-Manager/blob/main/README.md), add tutorials, or improve in-app help text.
- **Translations**: Add or improve support for additional languages in the multilingual interface.
- **Bug Reports**: Identify and report issues via the [Issues](https://github.com/VoxDroid/Advanced-Tab-Manager/issues) page.
- **Feature Suggestions**: Propose new features or enhancements.
- **Testing**: Test the application on different platforms or configurations.

## Setting Up the Development Environment

To contribute code or test changes, follow these steps to set up the project locally:

1. **Fork the Repository**:
   - Fork the repository at [VoxDroid/Advanced-Tab-Manager](https://github.com/VoxDroid/Advanced-Tab-Manager).
   - Clone your fork:
     ```bash
     git clone https://github.com/<your-username>/Advanced-Tab-Manager.git
     cd Advanced-Tab-Manager
     ```

2. **Install Dependencies**:
   - Ensure **Python 3.8+** is installed.
   - Install required packages:
     ```bash
     pip install -r requirements.txt
     ```
     If `requirements.txt` is unavailable, install manually:
     ```bash
     pip install PyQt6 selenium psutil qtawesome webdriver-manager requests packaging
     ```

3. **Create a Branch**:
   - Create a new branch for your changes:
     ```bash
     git checkout -b feature/your-feature
     ```

4. **Run the Application**:
   - Test your setup by running:
     ```bash
     python src/advancedtabmanager/app.py
     ```

## Submitting a Pull Request

1. **Make Changes**:
   - Implement your changes in your branch.
   - Ensure your code follows the [Style Guidelines](#style-guidelines).

2. **Commit Changes**:
   - Write clear, concise commit messages:
     ```bash
     git add .
     git commit -m "Add feature: describe your changes"
     ```

3. **Push to Your Fork**:
   - Push your branch to your forked repository:
     ```bash
     git push origin feature/your-feature
     ```

4. **Open a Pull Request**:
   - Go to the [GitHub repository](https://github.com/VoxDroid/Advanced-Tab-Manager) and open a Pull Request from your branch.
   - Use the Pull Request template provided in the repository.
   - Describe your changes, reference any related issues, and explain the impact.

5. **Code Review**:
   - Maintainers will review your Pull Request. Be responsive to feedback and make necessary updates.
   - Once approved, your changes will be merged into the main branch.

## Reporting Bugs

To report a bug:

1. Check the [Issues](https://github.com/VoxDroid/Advanced-Tab-Manager/issues) page to avoid duplicates.
2. Use the **Bug Report** template when creating a new issue.
3. Include:
   - A clear description of the bug.
   - Steps to reproduce the issue.
   - System details (OS, Python version, application version).
   - Screenshots or logs from the **Logs Tab** if applicable.

## Suggesting Features

To suggest a feature:

1. Check the [Issues](https://github.com/VoxDroid/Advanced-Tab-Manager/issues) page to see if your idea has been proposed.
2. Use the **Feature Request** template when creating a new issue.
3. Provide:
   - A detailed description of the feature.
   - Use cases or benefits.
   - Any mockups or examples, if applicable.

## Improving Documentation

Documentation contributions are highly valued. To improve documentation:

1. Update files like [README.md](https://github.com/VoxDroid/Advanced-Tab-Manager/blob/main/README.md), [SUPPORT.md](https://github.com/VoxDroid/Advanced-Tab-Manager/blob/main/SUPPORT.md), or in-app help text.
2. Submit changes via a Pull Request, following the [Submitting a Pull Request](#submitting-a-pull-request) process.
3. Ensure clarity, accuracy, and consistency with the project’s tone.

## Style Guidelines

To maintain consistency, follow these guidelines:

- **Python Code**:
  - Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for code style.
  - Use descriptive variable and function names.
  - Include docstrings for functions and classes.
  - Add comments for complex logic.

- **Documentation**:
  - Use clear, concise language.
  - Follow the structure and tone of existing documentation.
  - Use Markdown for formatting, consistent with the [README.md](https://github.com/VoxDroid/Advanced-Tab-Manager/blob/main/README.md).

- **Commits**:
  - Write descriptive commit messages (e.g., “Fix: resolve crash in headless mode”).
  - Keep commits focused on a single change or feature.

Thank you for contributing to **Advanced Tab Manager Pro**! Your efforts help make this project better for everyone.

---

**Developed by [VoxDroid](https://github.com/VoxDroid)**  
[GitHub](https://github.com/VoxDroid) | [Ko-fi](https://ko-fi.com/izeno)