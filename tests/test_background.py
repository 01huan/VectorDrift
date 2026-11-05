"""BackgroundBuilder: slow drawing jobs run on a worker thread, results picked up later."""

import threading
import time

from vector_drift.background import BackgroundBuilder


def _wait(builder, keys, timeout=5.0):
    got = {}
    end = time.monotonic() + timeout
    while time.monotonic() < end and not keys <= set(got):
        got.update(builder.take_done())
        time.sleep(0.005)
    return got


def test_jobs_run_on_another_thread_and_come_back_by_key():
    threads = []
    builder = BackgroundBuilder(lambda job: threads.append(threading.current_thread()) or job * 2)
    builder.request("a", 1)
    builder.request("b", 5)
    got = _wait(builder, {"a", "b"})
    builder.stop()
    assert got == {"a": 2, "b": 10}
    assert threading.main_thread() not in threads


def test_a_key_is_built_once_until_forgotten():
    calls = []
    builder = BackgroundBuilder(lambda job: calls.append(job) or job)
    builder.request("a", 1)
    builder.request("a", 1)
    _wait(builder, {"a"})
    builder.request("a", 1)                 # already built: not again
    time.sleep(0.05)
    assert calls == [1]
    builder.forget(lambda key: key == "a")
    builder.request("a", 1)
    _wait(builder, {"a"})
    builder.stop()
    assert calls == [1, 1]


def test_forgotten_jobs_are_dropped_before_they_run():
    gate = threading.Event()
    calls = []

    def build(job):
        gate.wait(2.0)
        calls.append(job)
        return job

    builder = BackgroundBuilder(build)
    builder.request("first", 1)             # the worker blocks on this one
    time.sleep(0.05)
    builder.request("stale", 2)
    builder.forget(lambda key: key == "stale")
    gate.set()
    got = _wait(builder, {"first"})
    time.sleep(0.05)
    got.update(builder.take_done())
    builder.stop()
    assert got == {"first": 1} and calls == [1]


def test_a_failing_job_gives_none():
    builder = BackgroundBuilder(lambda job: 1 / job)
    builder.request("zero", 0)
    got = _wait(builder, {"zero"})
    builder.stop()
    assert got == {"zero": None}


def test_no_thread_until_the_first_request():
    builder = BackgroundBuilder(lambda job: job)
    assert builder.thread is None
    builder.stop()


def test_an_idle_worker_ends_and_restarts_on_the_next_request(monkeypatch):
    from vector_drift import background
    monkeypatch.setattr(background, "IDLE_EXIT_S", 0.05)
    builder = BackgroundBuilder(lambda job: job)
    builder.request("a", 1)
    _wait(builder, {"a"})
    end = time.monotonic() + 2.0
    while builder.thread is not None and time.monotonic() < end:
        time.sleep(0.01)
    assert builder.thread is None
    builder.request("b", 2)
    assert _wait(builder, {"b"}) == {"b": 2}
    builder.stop()
