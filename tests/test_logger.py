import os
from pathlib import Path

from advancedtabmanager.utils import logger as logger_module


def test_resource_path_with_meipass(monkeypatch, tmp_path):
    monkeypatch.setattr(logger_module.sys, "_MEIPASS", str(tmp_path), raising=False)

    result = logger_module.resource_path("asset.txt")

    assert result == os.path.join(str(tmp_path), "asset.txt")

    monkeypatch.delattr(logger_module.sys, "_MEIPASS", raising=False)


def test_resource_path_without_meipass(monkeypatch):
    monkeypatch.delattr(logger_module.sys, "_MEIPASS", raising=False)
    base_dir = Path(logger_module.__file__).resolve().parents[1]

    result = logger_module.resource_path("assets/icon.ico")

    expected = os.path.join(str(base_dir), "assets", "icon.ico")
    assert os.path.normpath(result) == os.path.normpath(expected)


def test_setup_logging_creates_log_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    logger = logger_module.setup_logging()
    logger.info("hello")

    assert logger.name == "TabManager"
    assert (tmp_path / "advanced_tab_manager.log").exists()


def test_logger_wrapper_methods(monkeypatch):
    calls = []

    class DummyLogger:
        def info(self, message):
            calls.append(("info", message))

        def warning(self, message):
            calls.append(("warning", message))

        def error(self, message):
            calls.append(("error", message))

        def debug(self, message):
            calls.append(("debug", message))

    monkeypatch.setattr(logger_module, "setup_logging", lambda: DummyLogger())

    wrapper = logger_module.Logger()
    wrapper.info("a")
    wrapper.warning("b")
    wrapper.error("c")
    wrapper.debug("d")

    assert calls == [
        ("info", "a"),
        ("warning", "b"),
        ("error", "c"),
        ("debug", "d"),
    ]
