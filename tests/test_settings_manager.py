import json

from advancedtabmanager.config import settings_manager as settings_module
from advancedtabmanager.config.settings_manager import SettingsManager


class FakeSettings:
    def __init__(self):
        self._store = {}

    def setValue(self, key, value):
        self._store[key] = value

    def value(self, key, default=None, type=None):
        value = self._store.get(key, default)
        if type is not None:
            try:
                return type(value)
            except Exception:
                return value
        return value

    def allKeys(self):
        return list(self._store.keys())

    def clear(self):
        self._store.clear()


class DummyText:
    def __init__(self, value=""):
        self._value = value

    def text(self):
        return self._value

    def setText(self, value):
        self._value = value


class DummySpin:
    def __init__(self, value=0):
        self._value = value

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value


class DummyCombo:
    def __init__(self, index=0):
        self._index = index

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, index):
        self._index = index


class DummyCheck:
    def __init__(self, checked=False):
        self._checked = checked

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = bool(checked)


def _build_ui(url="https://example.com", iterations=7, interval=5, instances=2):
    return {
        "url_input": DummyText(url),
        "iterations_input": DummySpin(iterations),
        "interval_input": DummySpin(interval),
        "instances_input": DummySpin(instances),
        "theme_combo": DummyCombo(3),
        "font_size_spin": DummySpin(14),
        "language_combo": DummyCombo(2),
        "headless_checkbox": DummyCheck(True),
        "disable_gpu_checkbox": DummyCheck(True),
        "incognito_checkbox": DummyCheck(True),
        "disable_extensions_checkbox": DummyCheck(True),
        "start_maximized_checkbox": DummyCheck(True),
        "disable_notifications_checkbox": DummyCheck(True),
        "disable_web_security_checkbox": DummyCheck(True),
        "no_sandbox_checkbox": DummyCheck(True),
        "disable_dev_shm_checkbox": DummyCheck(True),
        "user_agent_input": DummyText("agent"),
        "proxy_checkbox": DummyCheck(True),
        "proxy_address_input": DummyText("127.0.0.1:8080"),
        "autostart_check": DummyCheck(True),
        "lock_window_size_check": DummyCheck(False),
    }


def test_save_and_load_settings(monkeypatch):
    fake_settings = FakeSettings()
    monkeypatch.setattr(settings_module, "QSettings", lambda _org, _app: fake_settings)

    manager = SettingsManager()
    ui_elements = _build_ui()
    manager.save_settings(ui_elements)

    assert fake_settings.value("url") == "https://example.com"
    assert fake_settings.value("iterations") == 7
    assert fake_settings.value("interval") == 5
    assert fake_settings.value("instances") == 2
    assert fake_settings.value("language") == 2
    assert fake_settings.value("headless") is True

    new_ui = _build_ui(url="", iterations=0, interval=0, instances=0)
    manager.load_settings(new_ui)

    assert new_ui["url_input"].text() == "https://example.com"
    assert new_ui["iterations_input"].value() == 7
    assert new_ui["interval_input"].value() == 5
    assert new_ui["instances_input"].value() == 2
    assert new_ui["language_combo"].currentIndex() == 2
    assert new_ui["headless_checkbox"].isChecked() is True


def test_export_and_import_settings(monkeypatch, tmp_path):
    fake_settings = FakeSettings()
    monkeypatch.setattr(settings_module, "QSettings", lambda _org, _app: fake_settings)

    manager = SettingsManager()
    fake_settings.setValue("theme", 2)
    fake_settings.setValue("url", "https://example.com")

    export_path = tmp_path / "settings.json"
    manager.export_settings(str(export_path))

    exported = json.loads(export_path.read_text())
    assert exported["theme"] == 2
    assert exported["url"] == "https://example.com"

    import_path = tmp_path / "import.json"
    import_path.write_text(json.dumps({"url": "https://imported.com", "iterations": 3}))

    manager.import_settings(str(import_path))
    assert fake_settings.value("url") == "https://imported.com"
    assert fake_settings.value("iterations") == 3


def test_get_and_set_setting(monkeypatch):
    fake_settings = FakeSettings()
    monkeypatch.setattr(settings_module, "QSettings", lambda _org, _app: fake_settings)

    manager = SettingsManager()
    manager.set_setting("mode", "fast")

    assert manager.get_setting("mode") == "fast"
