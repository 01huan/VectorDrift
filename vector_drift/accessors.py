"""Small shared helpers for resolving loose session attributes.

Centralising these keeps backward-compatible attribute fallbacks in one place
instead of duplicating them across ``shop`` and ``data``.
"""

from __future__ import annotations


def owned_ship_ids(session=None) -> set:
    """Resolve the set of owned ship ids from a session (or the default)."""
    if session is None:
        return {"ship01"}

    for attr in ("owned_ships", "unlocked_ships", "purchased_ships", "owned_ship_ids"):
        value = getattr(session, attr, None)
        if value is not None:
            if isinstance(value, set):
                return value
            try:
                return set(value)
            except TypeError:
                pass

    owned = {"ship01"}
    try:
        setattr(session, "owned_ships", owned)
    except Exception:
        pass
    return owned


__all__ = ["owned_ship_ids"]
