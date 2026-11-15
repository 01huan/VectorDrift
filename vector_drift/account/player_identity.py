"""A stable id for the player, used by the community level statistics.

The public level page counts how often a level was played, how often it was
cleared and how many *different* players cleared it.  The last number needs
an identity, so every player gets one:

* a signed-in player is identified by the account id, so the same player
  counts once per account on every device;
* a guest gets a random id that is stored in the local profile, so the guest
  counts once per installation.

The id is sent to the clear-recording function, which stores only a hash
combined with the level id, so the public level row cannot be used to read
or link player ids.
"""

from __future__ import annotations

import uuid
from typing import Any

__all__ = ["new_player_key", "player_key"]


def new_player_key() -> str:
    """A fresh random id for this installation."""
    return uuid.uuid4().hex


def player_key(session: Any, account: Any = None) -> str:
    """The key that identifies the player in the community statistics.

    The account id wins when the player is signed in; otherwise the local
    player id of the session is used (and created when it is still missing).
    """
    user = getattr(account, "current_user", None)
    user_id = getattr(user, "id", None)
    if user_id:
        return str(user_id)
    key = getattr(session, "player_key", None)
    if not key:
        key = new_player_key()
        try:
            session.player_key = key
        except Exception:  # pragma: no cover - a session without attributes
            pass
    return key
