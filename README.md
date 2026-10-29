# Vector Drift

Steer a spaceship by designing a mathematical force field.

```
F(x, y) = (Fx(x, y), Fy(x, y))   [N]
```

The force components can be defined using mathematical expressions, including supported functions, parentheses, and combinations of operations.

The ship starts at rest at (-7, 0) and must reach the planet at (7, 0). Each launch has 10 seconds. Every miss costs one of 5 lives:

* ??*Time up**?? the next launch starts (at rest) where the ship stopped.
* ??*Abort / Out of bounds / Diverged**?? the next launch starts back at (-7, 0).
* ??*Invalid mathematical result**?? if evaluating a force expression produces an invalid numerical result during flight, such as `log(-1)`, the launch fails and costs one life.
* ??*Infinite force**?? if the ship passes through a point where the force is infinite, such as `tan(x)` at x = 簣?/2, `1/x^2` or `log(abs(x))` at x = 0, it is flung straight off the field, which counts as out of bounds. Points where the force stays finite (`sin(x)/x` at x = 0) are passed through.

## Run

Requires **Python 3.11 or newer** (the level hints are read with the standard
library's `tomllib`, added in 3.11).

```
pip install -r requirements.txt
python main.py
```

The game opens fullscreen at the screen's real resolution (sharp on high-DPI
screens such as Windows scaling 200%). The 16:9 layout is scaled to fit; on other
aspect ratios the leftover strip is filled with the background color.
Quit with **Quit** on the main menu or Alt+F4.

- `VECTOR_DRIFT_WINDOWED=1` runs in a window instead.
- `VECTOR_DRIFT_SCALE` forces a scale (e.g. `1`, `1.5`, `2`).

The formula editor bypasses the system input method (e.g. Bopomofo), so typing
works even when a CJK IME is in Chinese mode.

## Screens

Main menu -> **Start** -> level select -> level. In a level, the round button next to
"LV1" goes back to level select, which has the way back to the main menu.

## Ships

Six ship skins, `ship01` to `ship06`, look different but fly the same (1 kg).
On level N you can fly `ship01` to `shipN`, and the level starts on `shipN`.
The arrows beside the ship also show the later ones, in grey with "LvN+",
but those cannot launch until their level. Random levels allow every ship.

## Controls

| Input | Action |
|---|---|
| Enter, or the play button on the Vector_field panel | Launch (when both formulas are valid) |
| Esc, or the stop button (during flight) | Abort the flight (costs a life) |
| Tab, Up/Down | Switch between the Fx and Fy lines |
| Mouse drag, double-click, Shift+arrows/Home/End | Select text in a line |
| Ctrl+A / Ctrl+C / Ctrl+X / Ctrl+V | Select line / copy / cut / paste |
| Ctrl+M | Mute / unmute |

## Formula format

Each box takes a mathematical expression in terms of `x` and `y`. Unlike a purely linear expression, formulas can include supported mathematical functions, parentheses, and combinations of operations.

For example, depending on the supported functions and operators:

* `2x + y`
* `sin(y) + x^2`
* `-(x + y) / 2`
* `sin(x) * cos(y)`
* `log(x)`

An empty box means 0.

The parser accepts only supported mathematical syntax. Unsupported functions or invalid expressions are rejected with a reason.

## Invalid Mathematical Results

A formula may be syntactically valid but produce an invalid or undefined numerical result at certain coordinates. For example, `log(-1)` is undefined over the real numbers.

If evaluating a force expression produces an invalid numerical result during flight, the launch fails and costs one life.

Consider the valid input domain of your expressions when designing a force field. An expression that works at one position may become invalid elsewhere along the ship's trajectory.


## Adding a fixed level

A fixed level (one written out in `vector_drift/data.py`) must also get a hint
in `vector_drift/hints.toml`: a `[level.N]` table with `steps`, `answer_note`
and at least one answer (`fx`, `fy`, optional `label`). `tests/test_hints.py`
fails for any fixed level without a hint, and flies every answer from the
level start to check that it reaches the planet. Random levels (7, 8) use the
AI Solver and need no hint.

## Tests

```
python -m pytest tests
```

## Layout

```
main.py                 entry point
vector_drift/
  config.py             layout, colors, physics constants
  data.py               ships and levels (add new ones here)
  hints.py, hints.toml  step-by-step hints for the fixed levels
  expr_parser.py        formula parser
  physics.py            fixed-step semi-implicit Euler flight
  coords.py             world <-> screen mapping
  render.py             grid, arrow field, color legend
  sprites.py            ship, planet, trail, vectors (all code-drawn)
  ui.py                 fonts, Button, TextBox
  audio.py              optional CC0 sound slots
  scenes/               menu, game, win, fail
assets/                 optional sounds, music, fonts (see assets/README.md)
tests/                  parser and physics tests
```

