"""The unified Community page.

The Community is one place with two content categories — **Levels** and
**Functions** — between which the player can switch without leaving the
page (the tab bar is drawn by both browsers, and the per-tab search / sort /
page state is kept on the session while switching).

This module exposes the small factory helpers the menus use; the browsers
live in :mod:`vector_drift.scenes.community_levels` and
:mod:`vector_drift.scenes.community_functions`, on top of the shared base in
:mod:`vector_drift.scenes.community_browser`.
"""

from __future__ import annotations

COMMUNITY_SCENES = ("levels", "functions")


def open_community(manager, category: str = "levels", back_to=None):
    """Switch to the Community page on the given category.

    ``back_to`` is a scene class called with ``(manager)`` when the Back
    button is clicked (defaults to the category's home: the level editor for
    levels, the Function Lab for functions).
    """
    category = category if category in COMMUNITY_SCENES else "levels"
    if category == "functions":
        from .community_functions import CommunityFunctionsScene

        scene = CommunityFunctionsScene(manager, back_to=back_to)
    else:
        from .community_levels import CommunityLevelsScene

        scene = CommunityLevelsScene(manager, back_to=back_to)
    manager.switch(scene)
    return scene


def community_scene(manager, category: str = "levels", back_to=None):
    """A community scene for ``category`` without switching to it."""
    category = category if category in COMMUNITY_SCENES else "levels"
    if category == "functions":
        from .community_functions import CommunityFunctionsScene

        return CommunityFunctionsScene(manager, back_to=back_to)
    from .community_levels import CommunityLevelsScene

    return CommunityLevelsScene(manager, back_to=back_to)
