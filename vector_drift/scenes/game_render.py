"""GameRenderMixin: composes the world, section and panel renderers."""
from .game_render_world import GameWorldRenderMixin
from .game_render_section import GameSectionRenderMixin
from .game_render_hud import GameHudRenderMixin


class GameRenderMixin(GameWorldRenderMixin, GameSectionRenderMixin, GameHudRenderMixin):
    """Drawing for GameScene.

    The world (plot, arrows, trails), the sections (start/target/props) and
    the left panel (level row, ship, clock, telemetry) each live in their own
    module; this class only assembles them.
    """

    def _ship_state(self):
        """Return (x, y, vx, vy, fx, fy) for the ship right now.

        Diverged force reads as (nan, nan) so callers can distinguish
        "no valid force" from (0, 0); draw/telemetry paths sanitize it to
        zeros / "—" for display.
        """
        if self.flight is not None:
            f = self.flight
            fx, fy = f.force
            return f.x, f.y, f.vx, f.vy, fx, fy
        x, y = self.launch_pos
        try:
            fx, fy = self.field.at(x, y)
        except (ArithmeticError, ValueError, TypeError, OverflowError,
                RecursionError, MemoryError):
            fx = fy = float("nan")
        return x, y, 0.0, 0.0, fx, fy
