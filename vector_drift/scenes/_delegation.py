"""Lazy delegation to the game scene, avoiding import cycles.

The game scene (``vector_drift.scenes.game``) imports the mixin modules
below; they in turn delegate public names back to the game scene through
this indirection, so importing a mixin never needs the real module.
"""

import sys


def _gm():
    """The ``vector_drift.scenes.game`` module (lazily resolved)."""
    return sys.modules["vector_drift.scenes.game"]
