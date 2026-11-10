"""Data objects produced by the Procedural Level Validator."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ValidationCheck:
    name: str
    passed: bool
    severity: str        # "error" | "warning" | "info"
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    level_id: int
    seed: int | None
    generator: str
    checks: list
    metrics: dict = field(default_factory=dict)
    solver_confirmed: bool | None = None
    solver_result: object | None = None
    route: tuple | None = None
    segments: tuple | None = None

    @property
    def ok(self):
        return not any(c.severity == "error" and not c.passed
                       for c in self.checks)

    @property
    def errors(self):
        return [c for c in self.checks if c.severity == "error" and not c.passed]

    @property
    def warnings(self):
        return [c for c in self.checks if c.severity == "warning" and not c.passed]

    @property
    def infos(self):
        return [c for c in self.checks if c.severity == "info"]

    def summary(self):
        errors = len(self.errors)
        warnings = len(self.warnings)
        if errors:
            status = "REJECTED"
        elif self.solver_confirmed is True:
            status = "OK (solver confirmed)"
        elif self.solver_confirmed is None:
            status = "OK (geometry only)"
        else:
            status = "OK (solver probe found nothing in budget)"
        failed = ", ".join(c.name for c in self.errors) or "-"
        return (f"level {self.level_id} [{self.generator}] seed={self.seed}: "
                f"{status}; {len(self.checks)} checks, "
                f"{errors} error(s) [{failed}], {warnings} warning(s)")

    def to_dict(self):
        return {
            "level_id": self.level_id,
            "seed": self.seed,
            "generator": self.generator,
            "ok": self.ok,
            "solver_confirmed": self.solver_confirmed,
            "metrics": dict(self.metrics),
            "checks": [
                {"name": c.name, "passed": c.passed, "severity": c.severity,
                 "message": c.message, "details": dict(c.details)}
                for c in self.checks
            ],
        }


def _check(checks, name, passed, severity, message, **details):
    checks.append(ValidationCheck(name=name, passed=bool(passed),
                                  severity=severity, message=message,
                                  details=details))


__all__ = ["ValidationCheck", "ValidationReport", "_check"]
