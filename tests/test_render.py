
"""Tests for vector_drift.plot_layers."""

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import math
from types import SimpleNamespace

import numpy as np
import pygame
import pytest

from vector_drift import render as pl


@pytest.fixture(scope="session", autouse=True)
def pygame_setup():
    """Initialize pygame for headless Surface-based tests."""
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


@pytest.fixture
def viewport():
    """A small, predictable viewport for rendering tests."""
    return SimpleNamespace(
        width=160,
        height=120,
        left=-4.0,
        top=3.0,
        scale=20.0,
        cx=80.0,
        cy=60.0,
        half_w=4.0,
        half_h=3.0,
    )


class ConstantField:
    def __init__(self, fx, fy):
        self.fx = fx
        self.fy = fy

    def at(self, x, y):
        return self.fx, self.fy


class SelectiveErrorField:
    """Raises an exception at selected sample points."""

    def at(self, x, y):
        if x == -0.5:
            raise ValueError("invalid field value")
        if y == -0.5:
            raise ZeroDivisionError("division by zero")
        return 1.0, 2.0


# ---------------------------------------------------------------------------
# Basic helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "c0, c1, t, expected",
    [
        ((0, 10, 20), (10, 20, 30), 0.0, (0, 10, 20)),
        ((0, 10, 20), (10, 20, 30), 1.0, (10, 20, 30)),
        ((0, 0, 0), (10, 10, 10), 0.5, (5, 5, 5)),
        ((10, 20), (0, 0), 0.25, (8, 15)),
    ],
)
def test_lerp(c0, c1, t, expected):
    assert pl._lerp(c0, c1, t) == expected


# ---------------------------------------------------------------------------
# Arrow geometry
# ---------------------------------------------------------------------------

def test_arrow_polygon_returns_seven_vertices():
    points = pl.arrow_polygon((0, 0), (10, 0), width=2, head=4)

    assert points is not None
    assert len(points) == 7


def test_arrow_polygon_tip_matches_endpoint():
    endpoint = (15.0, 8.0)

    points = pl.arrow_polygon(
        (0.0, 0.0),
        endpoint,
        width=2,
        head=5,
    )

    assert points[3] == endpoint


def test_arrow_polygon_is_perpendicular_to_horizontal_arrow():
    points = pl.arrow_polygon((0, 0), (10, 0), width=2, head=4)

    # The shaft is centered on y=0 and has half-width 1.
    assert points[0][1] == pytest.approx(1)
    assert points[6][1] == pytest.approx(-1)


def test_arrow_polygon_is_perpendicular_to_vertical_arrow():
    points = pl.arrow_polygon((0, 0), (0, 10), width=2, head=4)

    assert points[0][0] == pytest.approx(-1)
    assert points[6][0] == pytest.approx(1)


@pytest.mark.parametrize(
    "start, end",
    [
        ((0, 0), (0, 0)),
        ((1, 2), (1 + 1e-8, 2)),
    ],
)
def test_arrow_polygon_returns_none_for_degenerate_arrow(start, end):
    assert pl.arrow_polygon(start, end, width=2, head=5) is None


def test_arrow_polygon_caps_head_length():
    points = pl.arrow_polygon((0, 0), (10, 0), width=2, head=100)

    # The head length is capped at 70% of the total arrow length.
    assert points[1][0] == pytest.approx(3)


def test_arrow_polygon_supports_custom_head_width():
    points = pl.arrow_polygon(
        (0, 0),
        (10, 0),
        width=2,
        head=4,
        head_width=6,
    )

    assert len(points) == 7
    assert all(math.isfinite(v) for point in points for v in point)


def test_draw_arrow_handles_degenerate_arrow():
    surface = pygame.Surface((40, 40), pygame.SRCALPHA)

    # A zero-length arrow should not attempt to draw a polygon.
    pl.draw_arrow(surface, (10, 10), (10, 10), (255, 0, 0))

    assert surface.get_size() == (40, 40)


def test_draw_arrow_draws_non_degenerate_arrow():
    surface = pygame.Surface((40, 40), pygame.SRCALPHA)

    pl.draw_arrow(
        surface,
        (5, 20),
        (35, 20),
        (255, 0, 0),
    )

    assert pygame.surfarray.array_alpha(surface).max() > 0


def test_draw_smooth_arrow_draws_on_surface():
    surface = pygame.Surface((100, 100), pygame.SRCALPHA)

    pl.draw_smooth_arrow(
        surface,
        (10, 50),
        (90, 50),
        (255, 255, 255),
        outline=(0, 0, 0),
        k=2,
    )

    assert pygame.surfarray.array_alpha(surface).max() > 0


def test_draw_smooth_arrow_handles_degenerate_arrow():
    surface = pygame.Surface((40, 40), pygame.SRCALPHA)

    pl.draw_smooth_arrow(
        surface,
        (20, 20),
        (20, 20),
        (255, 255, 255),
        k=2,
    )

    assert surface.get_size() == (40, 40)


# ---------------------------------------------------------------------------
# Star sprites and space background
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "radius, sparkle",
    [
        (0.8, False),
        (1.3, False),
        (1.6, True),
    ],
)
def test_star_sprite_has_valid_size(radius, sparkle):
    sprite = pl._star_sprite(radius, sparkle)

    assert isinstance(sprite, pygame.Surface)
    assert sprite.get_width() > 0
    assert sprite.get_height() > 0
    assert sprite.get_flags() & pygame.SRCALPHA


def test_star_sprite_is_cached():
    radius = 2.37
    first = pl._star_sprite(radius, False)
    second = pl._star_sprite(radius, False)

    assert first is second


def test_star_sprite_cache_distinguishes_sparkle():
    radius = 2.41

    plain = pl._star_sprite(radius, False)
    sparkle = pl._star_sprite(radius, True)

    assert plain is not sparkle


def test_soft_glow_has_expected_dimensions():
    radius = 5

    surface = pl.soft_glow(radius, (255, 100, 50))

    assert surface.get_size() == (20, 20)
    assert surface.get_flags() & pygame.SRCALPHA


def test_soft_glow_alpha_is_stronger_near_center():
    surface = pl.soft_glow(
        radius=10,
        color=(255, 255, 255),
        max_alpha=200,
        extent=2,
    )
    alpha = pygame.surfarray.array_alpha(surface)

    center_alpha = alpha[alpha.shape[0] // 2, alpha.shape[1] // 2]
    corner_alpha = alpha[0, 0]

    assert center_alpha > corner_alpha
    assert alpha.max() <= 200


def test_soft_glow_has_transparent_outer_corners():
    surface = pl.soft_glow(
        radius=5,
        color=(255, 255, 255),
        extent=2,
    )
    alpha = pygame.surfarray.array_alpha(surface)

    assert alpha[0, 0] == 0
    assert alpha[-1, -1] == 0


def test_make_space_background_has_requested_size():
    surface = pl.make_space_background((80, 60), seed=7, star_count=10)

    assert surface.get_size() == (80, 60)


def test_make_space_background_is_deterministic():
    first = pl.make_space_background((80, 60), seed=123, star_count=20)
    second = pl.make_space_background((80, 60), seed=123, star_count=20)

    np.testing.assert_array_equal(
        pygame.surfarray.array3d(first),
        pygame.surfarray.array3d(second),
    )


def test_make_space_background_changes_with_seed():
    first = pl.make_space_background((80, 60), seed=1, star_count=20)
    second = pl.make_space_background((80, 60), seed=2, star_count=20)

    assert not np.array_equal(
        pygame.surfarray.array3d(first),
        pygame.surfarray.array3d(second),
    )


def test_make_space_background_supports_zero_stars():
    surface = pl.make_space_background((40, 30), seed=7, star_count=0)

    assert surface.get_size() == (40, 30)


def test_make_space_background_supports_small_dimensions():
    surface = pl.make_space_background((1, 1), seed=7, star_count=0)

    assert surface.get_size() == (1, 1)


# ---------------------------------------------------------------------------
# Plot background and labels
# ---------------------------------------------------------------------------

def test_make_plot_background_has_viewport_size(viewport):
    surface = pl.make_plot_background(viewport)

    assert surface.get_size() == (viewport.width, viewport.height)


def test_make_plot_background_returns_surface(viewport):
    surface = pl.make_plot_background(viewport)

    assert isinstance(surface, pygame.Surface)


def test_make_plot_labels_has_viewport_size(viewport):
    surface = pl.make_plot_labels(viewport)

    assert surface.get_size() == (viewport.width, viewport.height)


def test_make_plot_labels_returns_transparent_surface(viewport):
    surface = pl.make_plot_labels(viewport)

    assert surface.get_flags() & pygame.SRCALPHA


def test_make_plot_labels_draws_content(viewport):
    surface = pl.make_plot_labels(viewport)

    assert pygame.surfarray.array_alpha(surface).max() > 0


# ---------------------------------------------------------------------------
# Field sampling
# ---------------------------------------------------------------------------

def test_field_samples_returns_expected_grid(viewport):
    field = ConstantField(2.0, 3.0)

    samples = pl.field_samples(viewport, field)

    # half_w=4 and half_h=3, with 1 m spacing:
    # x has 8 samples and y has 6 samples.
    assert len(samples) == 8 * 6


def test_field_samples_uses_cell_centers(viewport):
    samples = pl.field_samples(viewport, ConstantField(1.0, 2.0))

    xs = sorted({sample[0] for sample in samples})
    ys = sorted({sample[1] for sample in samples})

    assert xs == pytest.approx(
        [-3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5]
    )
    assert ys == pytest.approx(
        [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5]
    )


def test_field_samples_preserves_force_components(viewport):
    samples = pl.field_samples(viewport, ConstantField(3.0, -4.0))

    assert samples
    assert all(sample[2:] == (3.0, -4.0) for sample in samples)


def test_field_samples_skips_arithmetic_errors(viewport):
    class ArithmeticErrorField:
        def at(self, x, y):
            raise ArithmeticError("invalid arithmetic")

    assert pl.field_samples(viewport, ArithmeticErrorField()) == []


def test_field_samples_skips_value_errors(viewport):
    class ValueErrorField:
        def at(self, x, y):
            raise ValueError("invalid value")

    assert pl.field_samples(viewport, ValueErrorField()) == []


def test_field_samples_skips_type_errors(viewport):
    class TypeErrorField:
        def at(self, x, y):
            raise TypeError("invalid type")

    assert pl.field_samples(viewport, TypeErrorField()) == []


def test_field_samples_skips_overflow_errors(viewport):
    class OverflowField:
        def at(self, x, y):
            raise OverflowError("too large")

    assert pl.field_samples(viewport, OverflowField()) == []


def test_field_samples_skips_only_invalid_points(viewport):
    samples = pl.field_samples(viewport, SelectiveErrorField())

    assert samples
    assert all(x != -0.5 for x, _, _, _ in samples)
    assert all(y != -0.5 for _, y, _, _ in samples)


def test_field_samples_empty_when_viewport_has_no_cells():
    tiny_viewport = SimpleNamespace(
        half_w=0.4,
        half_h=0.4,
    )

    samples = pl.field_samples(tiny_viewport, ConstantField(1, 1))

    assert samples == []


# ---------------------------------------------------------------------------
# Field arrow sizing and rendering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "length_px",
    [0.0, 1.0, 10.0, 100.0, 1000.0],
)
def test_field_arrow_shape_returns_positive_dimensions(length_px):
    width, head, head_width = pl.field_arrow_shape(length_px)

    assert width > 0
    assert head > 0
    assert head_width > 0


def test_field_arrow_shape_head_is_capped():
    _, head, _ = pl.field_arrow_shape(1000)

    assert head == pytest.approx(6.5 * pl.config.UI_SCALE)


def test_make_field_layer_returns_surface_and_max_magnitude(viewport):
    surface, max_mag = pl.make_field_layer(
        viewport,
        ConstantField(3.0, 4.0),
    )

    assert isinstance(surface, pygame.Surface)
    assert surface.get_size() == (viewport.width, viewport.height)
    assert max_mag == pytest.approx(5.0)


def test_make_field_layer_zero_field(viewport):
    surface, max_mag = pl.make_field_layer(
        viewport,
        ConstantField(0.0, 0.0),
    )

    assert surface.get_size() == (viewport.width, viewport.height)
    assert max_mag == pytest.approx(0.0)


def test_make_field_layer_scales_to_largest_force(viewport):
    class VaryingField:
        def at(self, x, y):
            if x < 0:
                return 3.0, 4.0
            return 0.0, 2.0

    _, max_mag = pl.make_field_layer(viewport, VaryingField())

    assert max_mag == pytest.approx(5.0)


def test_make_field_layer_handles_invalid_field_samples(viewport):
    surface, max_mag = pl.make_field_layer(
        viewport,
        SelectiveErrorField(),
    )

    assert surface.get_size() == (viewport.width, viewport.height)
    assert max_mag == pytest.approx(math.hypot(1.0, 2.0))


def test_make_field_layer_handles_non_finite_force_values(viewport):
    class NonFiniteField:
        def at(self, x, y):
            if x < 0:
                return float("inf"), 0.0
            return 3.0, 4.0

    surface, max_mag = pl.make_field_layer(viewport, NonFiniteField())

    assert surface.get_size() == (viewport.width, viewport.height)
    assert max_mag == pytest.approx(5.0)


def test_draw_smooth_arrow_with_huge_coords_does_not_crash():
    surface = pygame.Surface((200, 200))

    # Must not raise (previously: C-long overflow in Rect / blit TypeError).
    pl.draw_smooth_arrow(surface, (54437464510795.0, 100.0), (100.0, 100.0), (255, 0, 0))
    pl.draw_smooth_arrow(surface, (float("inf"), 0.0), (10.0, 10.0), (255, 0, 0))
    pl.draw_smooth_arrow(surface, (0.0, 0.0), (10.0, 10.0), (255, 0, 0))


# ---------------------------------------------------------------------------
# Force formatting and legend
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, expected",
    [
        (0, "0 N"),
        (1, "1 N"),
        (1.234, "1.23 N"),
        (9.999, "10 N"),
        (10, "10.0 N"),
        (12.34, "12.3 N"),
        (999.9, "999.9 N"),
        (1000, "1,000 N"),
        (12345.6, "12,346 N"),
    ],
)
def test_format_force(value, expected):
    assert pl.format_force(value) == expected


def test_draw_legend_with_positive_force():
    surface = pygame.Surface((400, 80), pygame.SRCALPHA)

    pl.draw_legend(surface, (200, 40), 12.5)

    assert pygame.surfarray.array_alpha(surface).max() > 0


def test_draw_legend_with_zero_force():
    surface = pygame.Surface((400, 80), pygame.SRCALPHA)

    pl.draw_legend(surface, (200, 40), 0)

    assert pygame.surfarray.array_alpha(surface).max() > 0


def test_draw_legend_with_negative_force_does_not_crash():
    surface = pygame.Surface((400, 80), pygame.SRCALPHA)

    # The production function treats non-positive values as "0 N".
    pl.draw_legend(surface, (200, 40), -1)

    assert pygame.surfarray.array_alpha(surface).max() > 0
