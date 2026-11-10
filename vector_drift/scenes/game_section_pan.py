"""Camera pan helper used while transitioning between sections."""

from .. import config

from .game_layout import ease_in_out


class SectionPan:
    """The camera pan from a reached checkpoint to the next section.

    ``shift`` is section_shift (m): where the new section's origin sits in
    the old section's coordinates. ``level`` / ``pickups`` / ``holes`` are
    the old section as it was left; ``arrival`` is where the ship touched
    the checkpoint (old section coordinates); ``t`` is seconds elapsed.
    """

    def __init__(self, shift, level, pickups, holes, arrival):
        self.shift = shift
        self.level = level
        self.pickups = pickups
        self.holes = holes
        self.arrival = arrival
        self.t = 0.0

    @property
    def progress(self):
        """Eased 0 -> 1 over config.CHECKPOINT_PAN_DURATION."""
        duration = config.CHECKPOINT_PAN_DURATION
        return ease_in_out(self.t / duration if duration > 0 else 1.0)
