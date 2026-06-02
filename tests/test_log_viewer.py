import time

from advancedtabmanager.ui.log_viewer import LogViewer


def test_append_log_adds_entry(qt_app, monkeypatch):
    monkeypatch.setattr(time, "strftime", lambda _fmt: "12:34:56")

    viewer = LogViewer()
    viewer.append_log("Hello", "INFO")

    html = viewer.toHtml()
    assert "[12:34:56] [INFO] Hello" in html
    assert "#4ade80" in html
