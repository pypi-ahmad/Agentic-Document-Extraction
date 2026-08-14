from pathlib import Path

from streamlit.testing.v1 import AppTest

from paperplane import shutdown

WORKSPACE_PATH = Path(__file__).resolve().parents[1] / "workspace_app.py"


def test_schedule_process_exit_uses_successful_daemon_timer(monkeypatch) -> None:
    exits = []
    timers = []

    class FakeTimer:
        def __init__(self, delay, callback, args):
            self.delay = delay
            self.callback = callback
            self.args = args
            self.daemon = False
            self.started = False
            timers.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(shutdown.os, "_exit", exits.append)
    monkeypatch.setattr(shutdown.threading, "Timer", FakeTimer)

    timer = shutdown.schedule_process_exit(1.25)
    timer.callback(*timer.args)

    assert timer.delay == 1.25
    assert timer.daemon is True
    assert timer.started is True
    assert exits == [0]


def test_shutdown_html_notifies_all_tabs_and_blanks_the_frontend() -> None:
    assert 'new BroadcastChannel("paperplane-shutdown")' in shutdown.TAB_LISTENER_HTML
    assert 'channel.postMessage("stop-and-clear")' in shutdown.SHUTDOWN_HTML
    assert 'window.location.replace("about:blank")' in shutdown.TAB_LISTENER_HTML
    assert 'window.location.replace("about:blank")' in shutdown.SHUTDOWN_HTML


def test_workspace_confirms_clears_and_schedules_shutdown(monkeypatch) -> None:
    scheduled = []
    monkeypatch.setattr(
        shutdown,
        "schedule_process_exit",
        lambda delay_seconds=shutdown.SHUTDOWN_DELAY_SECONDS: scheduled.append(delay_seconds),
    )
    app = AppTest.from_file(WORKSPACE_PATH).run(timeout=20)

    next(button for button in app.button if button.label == "Stop and clear").click().run(
        timeout=20
    )
    assert {button.label for button in app.button} >= {"Cancel", "Stop and clear now"}

    app.session_state["shutdown_sentinel"] = True
    next(button for button in app.button if button.label == "Stop and clear now").click().run(
        timeout=20
    )

    assert scheduled == [shutdown.SHUTDOWN_DELAY_SECONDS]
    assert "shutdown_sentinel" not in app.session_state
    assert not app.exception
