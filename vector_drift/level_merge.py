"""Merging generated random levels into one multi-screen random level.

A random level is no longer one screen: it is 1..3 *screens*, each one a
complete level built by the usual single-level flow (see
:func:`vector_drift.level_modules.generate_layout`) from its own theme.  The
screens are chained: every screen but the last ends on a checkpoint, so the
ship flies on to the next screen instead of winning the level.

Generation flow (see :func:`generate_merged_layout`):

1. Pick 1..``preset.max_sections`` distinct themes (the preset's templates).
2. Generate one level per theme with the normal random-level flow.
3. Chain them: the first screens' targets become checkpoints, the last
   screen's target is the planet the player has to reach.

Pure logic (no pygame); everything runs off the seeded ``rng``, so a seed
always reproduces the same merged level.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from .data import LevelSpec, SectionSpec, multi_section_level

# How many screens one merged random level may have (1 = no checkpoint).
MAX_SECTIONS = 3


@dataclass(frozen=True)
class MergedSection:
    """One screen of a merged random level.

    ``layout`` is the generated level (level_modules.GeneratedLayout),
    ``preset`` the theme it was built from and ``seed`` the seed its
    generation ran on.
    """

    layout: object        # level_modules.GeneratedLayout
    preset: object        # level_presets.RandomPreset (the theme)
    seed: int             # the seed this screen was generated with

    @property
    def level(self):
        """The screen as a plain one-screen LevelSpec (what gets validated)."""
        return self.layout.level

    @property
    def module(self):
        """The generation module that built this screen."""
        return self.layout.module


@dataclass(frozen=True)
class MergedLayout:
    """A merged random level: the level to play plus the screens it is made of."""

    level: LevelSpec       # the merged level (one screen => no sections)
    sections: tuple        # tuple[MergedSection, ...]


def _themes(preset):
    """The themes a merged level may use: the preset's templates, or itself."""
    templates = tuple(getattr(preset, "templates", ()) or ())
    return templates or (preset,)


def choose_themes(preset, rng, max_sections=MAX_SECTIONS):
    """Pick 1..max_sections distinct themes for one merged level.

    Distinct themes keep the merged level varied (a maze screen next to a
    wormhole screen); a preset with fewer templates than screens simply
    gets fewer screens.
    """
    themes = _themes(preset)
    count = rng.randint(1, max(1, min(int(max_sections), len(themes))))
    return rng.sample(list(themes), count)


def generate_merged_layout(seed, preset, max_sections=None):
    """Generate the screens of one merged random level and chain them.

    ``max_sections`` defaults to the preset's own ``max_sections`` (see
    level_presets.RandomPreset).  Raises RuntimeError when a screen cannot
    be generated at all (the caller retries with another seed).
    """
    from .level_modules import generate_layout

    if max_sections is None:
        max_sections = int(getattr(preset, "max_sections", MAX_SECTIONS) or 1)
    rng = random.Random(seed)
    sections = []
    for theme in choose_themes(preset, rng, max_sections):
        section_seed = rng.getrandbits(63)
        # The normal single-level flow, with this theme as the only choice.
        layout = generate_layout(section_seed, replace(preset, templates=(theme,)))
        sections.append(MergedSection(layout=layout, preset=theme, seed=section_seed))
    level = _merge_levels(preset, [section.level for section in sections])
    return MergedLayout(level=level, sections=tuple(sections))


def _merge_levels(preset, levels):
    """Chain the screens into one level: the first ones end on a checkpoint.

    The merged level's own screen fields mirror the first screen (like
    every multi-section level); the last screen's target is the planet.
    The lives are shared by the whole run, so the merged level gets the
    most generous screen (the checkpoint gives a life back, capped by it).
    """
    if len(levels) == 1:
        return replace(levels[0], id=preset.level_id, name=preset.name,
                       ship_id=levels[0].ship_id, sections=())
    sections = tuple(SectionSpec(
        start=tuple(level.start),
        target_center=tuple(level.target_center),
        target_radius=level.target_radius,
        time_limit=level.time_limit,
        obstacles=tuple(level.obstacles),
        pickups=tuple(level.pickups),
        holes=tuple(level.holes),
    ) for level in levels)
    return multi_section_level(id=preset.level_id, name=preset.name,
                               ship_id=levels[0].ship_id, sections=sections,
                               lives=max(level.lives for level in levels))


def combine_reports(reports, level_id, seed):
    """One report for a merged level: every screen's checks, in order.

    Each check keeps its own severity and message and remembers the screen
    it belongs to (``details["section"]``, 1-based).  The merged report is
    ok only when every screen is ok, and solver-confirmed only when every
    screen was confirmed.
    """
    from .validation_report import ValidationReport

    checks = []
    metrics = {}
    for index, report in enumerate(reports, start=1):
        for check in report.checks:
            details = dict(check.details)
            details["section"] = index
            checks.append(replace(check, details=details))
        for key, value in report.metrics.items():
            metrics[f"{index}.{key}"] = value
    modules = tuple(report.generator for report in reports)
    metrics["sections"] = len(reports)
    metrics["modules"] = modules

    confirmed = [report.solver_confirmed for report in reports]
    if confirmed and all(value is True for value in confirmed):
        solver_confirmed = True
    elif confirmed and all(value is None for value in confirmed):
        solver_confirmed = None
    else:
        solver_confirmed = False

    return ValidationReport(
        level_id=level_id,
        seed=seed,
        generator=modules[0] if len(modules) == 1 else "merged",
        checks=checks,
        metrics=metrics,
        solver_confirmed=solver_confirmed,
        solver_result=None,
        route=None,
        segments=None,
    )


__all__ = [
    "MAX_SECTIONS", "MergedLayout", "MergedSection", "choose_themes",
    "generate_merged_layout", "combine_reports",
]
