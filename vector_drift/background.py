"""Slow drawing jobs on a worker thread, so the frame loop does not stall on them.

The game scene uses it for field-arrow layers of the zoomed-out view: each
takes ~100 ms on a large screen, which drawn in a frame shows as a hitch.
Jobs are keyed; the worker builds each requested key once, in request
order, and the frame loop picks finished results up with take_done().
pygame draws on separate software surfaces safely from another thread.
"""

import logging
import threading

log = logging.getLogger(__name__)

IDLE_EXIT_S = 2.0       # the worker ends after this long without a job


class BackgroundBuilder:
    """Runs ``build(job)`` for requested keys on one daemon worker thread.

    ``request(key, job)`` queues a key unless it is queued, building or built
    already (until forget()). ``take_done()`` returns {key: result} finished
    since the last call; a build that raises gives None. The thread starts
    with the first request; ``stop()`` ends it.
    """

    def __init__(self, build):
        self._build = build
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._jobs = []                 # [(key, job)] waiting, oldest first
        self._asked = set()             # keys waiting, building or built
        self._done = {}
        self._stopped = False
        self.thread = None

    def request(self, key, job):
        with self._lock:
            if self._stopped or key in self._asked:
                return
            self._asked.add(key)
            self._jobs.append((key, job))
            if self.thread is None:
                self.thread = threading.Thread(target=self._run, name="background-builder",
                                               daemon=True)
                self.thread.start()
        self._wake.set()

    def take_done(self):
        with self._lock:
            done, self._done = self._done, {}
        return done

    def forget(self, drop):
        """Drop every key ``drop(key)`` is true for: not built if still waiting,
        result discarded if building, and requestable again."""
        with self._lock:
            self._jobs = [(k, j) for k, j in self._jobs if not drop(k)]
            self._done = {k: v for k, v in self._done.items() if not drop(k)}
            self._asked = {k for k in self._asked if not drop(k)}

    def stop(self):
        with self._lock:
            self._stopped = True
            self._jobs = []
        self._wake.set()

    def _run(self):
        while True:
            with self._lock:
                if self._stopped:
                    self.thread = None
                    return
                key, job = self._jobs.pop(0) if self._jobs else (None, None)
                if key is None:
                    self._wake.clear()
            if key is None:
                if not self._wake.wait(IDLE_EXIT_S):
                    with self._lock:
                        if not self._jobs:          # idle: end; the next request restarts it
                            self.thread = None
                            return
                continue
            try:
                result = self._build(job)
            except Exception:  # noqa: BLE001 - a bad job must not kill the worker
                log.warning("background job %r failed", key, exc_info=True)
                result = None
            with self._lock:
                if key in self._asked and not self._stopped:
                    self._done[key] = result
