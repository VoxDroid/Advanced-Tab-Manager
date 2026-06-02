from advancedtabmanager.utils import version_checker as version_module


class DummyResponse:
    def __init__(self, tag_name, html_url):
        self._tag_name = tag_name
        self._html_url = html_url

    def raise_for_status(self):
        return None

    def json(self):
        return {"tag_name": self._tag_name, "html_url": self._html_url}


def test_run_emits_update(monkeypatch, qt_app):
    captured = []

    def fake_get(_url, timeout):
        return DummyResponse("v9.9.9", "https://example.com")

    monkeypatch.setattr(version_module.requests, "get", fake_get)

    checker = version_module.VersionChecker()
    checker.update_available.connect(
        lambda version, url: captured.append((version, url))
    )

    checker.run()

    assert captured == [("9.9.9", "https://example.com")]


def test_run_emits_connection_error(monkeypatch, qt_app):
    captured = []

    def fake_get(_url, timeout):
        raise version_module.requests.exceptions.ConnectionError()

    monkeypatch.setattr(version_module.requests, "get", fake_get)

    checker = version_module.VersionChecker()
    checker.error_occurred.connect(captured.append)

    checker.run()

    assert captured == ["No internet connection. Update check failed."]


def test_run_emits_request_error(monkeypatch, qt_app):
    captured = []

    def fake_get(_url, timeout):
        raise version_module.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(version_module.requests, "get", fake_get)

    checker = version_module.VersionChecker()
    checker.error_occurred.connect(captured.append)

    checker.run()

    assert captured == ["Failed to check for updates: boom"]


def test_check_for_updates_returns_update(monkeypatch):
    def fake_get(_url, timeout):
        return DummyResponse("v2.0.0", "https://example.com")

    monkeypatch.setattr(version_module.requests, "get", fake_get)

    checker = version_module.VersionChecker()
    version, url = checker.check_for_updates()

    assert version == "2.0.0"
    assert url == "https://example.com"


def test_check_for_updates_returns_none_when_current(monkeypatch):
    def fake_get(_url, timeout):
        return DummyResponse("v1.4.0", "https://example.com")

    monkeypatch.setattr(version_module.requests, "get", fake_get)

    checker = version_module.VersionChecker()
    version, url = checker.check_for_updates()

    assert version is None
    assert url is None


def test_check_for_updates_connection_error(monkeypatch):
    def fake_get(_url, timeout):
        raise version_module.requests.exceptions.ConnectionError()

    monkeypatch.setattr(version_module.requests, "get", fake_get)

    checker = version_module.VersionChecker()
    version, error = checker.check_for_updates()

    assert version is None
    assert error == "No internet connection. Update check failed."


def test_check_for_updates_request_error(monkeypatch):
    def fake_get(_url, timeout):
        raise version_module.requests.exceptions.RequestException("boom")

    monkeypatch.setattr(version_module.requests, "get", fake_get)

    checker = version_module.VersionChecker()
    version, error = checker.check_for_updates()

    assert version is None
    assert error == "Failed to check for updates: boom"
