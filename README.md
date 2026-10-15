# Vector Drift

Steer a spaceship by designing a linear force field

    F(x, y) = (ax + by + c,  dx + ey + f)   [N]

The ship starts at rest at (-7, 0) and must reach the planet at (7, 0). Each launch has 10 seconds.
Every miss costs one of 5 lives:

- **Time up**: the next launch starts (at rest) where the ship stopped.
- **Abort / Out of bounds / Diverged**: the next launch starts back at (-7, 0).

## Run

    pip install -r requirements.txt
    python main.py

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

Each box takes a linear expression `px + qy + r`; any term may be omitted and terms may be in any order.
`2x`, `2*x`, `-x`, `x/2`, `1/2x`, `-0.5y + 3` are all valid; an empty box means 0.
Products, powers, parentheses, functions and repeated terms are rejected with a reason.

## Tests

    python -m pytest tests

## Layout

    main.py                 entry point
    vector_drift/
      config.py             layout, colors, physics constants
      data.py               ships and levels (add new ones here)
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
