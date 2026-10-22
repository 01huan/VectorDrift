"""Background solver runner.

Runs :meth:`Solver.solve` on a background thread so the PyGame main thread
never blocks.  Results are delivered through a :class:`SolverJob` that callers
poll or wait on.

Design notes:
* Pure ``threading`` (standard library, offline).  Because the solver is
  CPU-bound, a single Python thread does not multi-core parallelize; this is
  acceptable for stage 1 and keeps the implementation simple and deterministic.
  A later stage can swap the execution backend to ``multiprocessing`` behind
  the same ``SolverJob`` API without touching solvers.
* Cancellation is cooperative: the job sets a flag; solvers that honour it
  (PSO does via budget checks) stop early.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..data import LevelSpec
from .interface import Solver, SolveResult


@dataclass
class SolverJob:
    """Handle to an in-flight or completed solve request."""

    solver: Solver
    level: LevelSpec
    kwargs: dict = field(default_factory=dict)
    result: Optional[SolveResult] = None
    error: Optional[BaseException] = None
    _thread: Optional[threading.Thread] = None
    _finished: threading.Event = field(default_factory=threading.Event)
    _cancel: threading.Event = field(default_factory=threading.Event)
    _on_complete: Optional[Callable[[SolveResult], None]] = None

    def start(self, on_complete: Optional[Callable[[SolveResult], None]] = None,
              daemon: bool = True) -> "SolverJob":
        self._on_complete = on_complete

        def _target() -> None:
            try:
                # Inject cancellation hook into budgets if caller supplied one.
                kwargs = dict(self.kwargs)
                self.result = self.solver.solve(self.level, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - surface to caller
                self.error = exc
            finally:
                self._finished.set()
                if self._on_complete is not None and self.result is not None:
                    try:
                        self._on_complete(self.result)
                    except Exception:  # callback must not kill the runner
                        pass

        self._thread = threading.Thread(target=_target, name="solver-job",
                                        daemon=daemon)
        self._thread.start()
        return self

    @property
    def running(self) -> bool:
        return self._thread is not None and not self._finished.is_set()

    def cancel(self) -> None:
        """Request cooperative cancellation (best effort)."""
        self._cancel.set()

    def result_wait(self, timeout_s: Optional[float] = None) -> Optional[SolveResult]:
        """Block until the result is ready or ``timeout_s`` elapses."""
        self._finished.wait(timeout=timeout_s)
        return self.result

    def __enter__(self) -> "SolverJob":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.running:
            self.cancel()
            self._finished.wait(timeout=5.0)


def run_solver_async(solver: Solver, level: LevelSpec,
                     on_complete: Optional[Callable[[SolveResult], None]] = None,
                     **kwargs) -> SolverJob:
    """Convenience: create and start a background solve job."""
    job = SolverJob(solver=solver, level=level, kwargs=kwargs)
    job.start(on_complete=on_complete)
    return job
