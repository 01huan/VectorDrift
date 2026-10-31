import queue
from unittest.mock import patch

from vector_drift.account.auth_manager import AccountManager
from vector_drift.account.errors import AccountError


def test_auth_manager_initial_state():
    am = AccountManager()
    assert am.status == "guest"
    assert am.current_user is None
    assert am.profile is None
    assert am.is_busy is False
    assert am.last_error is None


def test_is_configured_delegates(monkeypatch):
    am = AccountManager()
    monkeypatch.setattr("vector_drift.account.auth_manager.is_configured", lambda: False)
    assert am.is_configured() is False
    monkeypatch.setattr("vector_drift.account.auth_manager.is_configured", lambda: True)
    assert am.is_configured() is True


def test_is_authenticated():
    am = AccountManager()
    assert am.is_authenticated() is False
    am.status = "authenticated"
    # still no current_user
    assert am.is_authenticated() is False


def test_reset_to_guest():
    am = AccountManager()
    am.current_user = "u"
    am.profile = "p"
    am.status = "authenticated"
    am.last_error = "err"
    am.reset_to_guest()
    assert am.current_user is None
    assert am.profile is None
    assert am.status == "guest"
    assert am.last_error is None


def test_run_async_unconfigured_calls_on_error(monkeypatch):
    am = AccountManager()
    monkeypatch.setattr(am, "is_configured", lambda: False)
    errors = []
    am._run_async("k", lambda: 1, on_error=errors.append)
    assert len(errors) == 1
    assert isinstance(errors[0], AccountError)
    assert am.is_busy is False


def test_run_async_busy_calls_on_error(monkeypatch):
    am = AccountManager()
    monkeypatch.setattr(am, "is_configured", lambda: True)
    am.is_busy = True
    errors = []
    am._run_async("k", lambda: 1, on_error=errors.append)
    assert len(errors) == 1
    assert isinstance(errors[0], AccountError)
    assert "in progress" in str(errors[0])


def test_poll_empty_queue():
    am = AccountManager()
    am.poll()  # should not raise
    assert am.is_busy is False


def test_poll_processes_success(monkeypatch):
    am = AccountManager()
    am.is_busy = True
    successes = []
    task = am._queue  # placeholder

    # manually enqueue a completed task by reusing _Task via module
    from vector_drift.account.auth_manager import _Task

    t = _Task(kind="k", fn=lambda: 5, on_success=successes.append)
    am._queue.put((t, 5, None))
    am.poll()
    assert successes == [5]
    assert am.is_busy is False
    assert am.last_error is None


def test_poll_processes_error():
    am = AccountManager()
    am.is_busy = True
    errors = []

    from vector_drift.account.auth_manager import _Task

    t = _Task(kind="k", fn=lambda: None, on_error=errors.append)
    am._queue.put((t, None, ValueError("boom")))
    am.poll()
    assert len(errors) == 1
    assert am.last_error == "boom"
    assert am.is_busy is False
