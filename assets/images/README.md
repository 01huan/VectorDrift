# Vector Drift image assets

Place CC0 (public domain) PNG files here.  Every slot is looked up by a
resource key; when the file is missing the game silently falls back to the
existing pygame code-drawn art, so the game is fully playable without any PNG.

## Resource key -> file name

| Resource key | File (relative to this folder) | Used for |
|--------------|-------------------------------|----------|
| `ship.ship01` … `ship.ship06` | `ships/ship01.png` … `ships/ship06.png` | Player ship skins, 512 x 512 (panel preview, lives icon, in-flight sprite) |
| `target.planet` | `targets/planet.png` | Destination / target planet, 512 x 512 |
| `obstacle.rock01`, `obstacle.rock02` | `obstacles/rock01.png`, `obstacles/rock02.png` | Bumper rocks, 512 x 512: each bumper shows one of them, picked at random and turned by a random angle (fixed per bumper) |
| `pickup.shockwave` | `pickups/shockwave.png` | Shockwave pickup icon, 256 x 256 |
| `pickup.extratime` | `pickups/extratime.png` | Extratime pickup icon (stopwatch), 256 x 256 |
| `pickup.shield` | `pickups/shield.png` | Shield pickup icon, 256 x 256 |
| `ui.start_marker` | `ui/start_marker.png` | Launch pad / start marker ring |
| `background.space` | `background/space.png` | Tiled full-screen backdrop (optional) |

Round props (the planet and the rocks) fill about 98% of their canvas: the
whole canvas is drawn at the collision size, so the picture's circle is the
circle the ship bounces off or reaches. Their glow stays code-drawn. The
planet and the rocks are stored with a 256-colour palette to keep files
small (about 40-60 KB each); at game size this looks the same as the
full-colour original.

Pickups are small on screen (a 0.45-0.5 m radius, under 150 px even at
4K), so their icons are 256 x 256, fitted to 95% of the canvas and stored
the same way (about 10-15 KB each).

## Sizing

Each slot declares a default logical-pixel display size in
`vector_drift/image_assets.py` (`AssetSpec.display_w` / `display_h`), turned
into real pixels with `config.UI_SCALE`.

Callers may ask for another real-pixel size at draw time, which takes
precedence over the spec: the same ship image is drawn at one size in the
panel preview, another for the lives icons and another in flight.

The PNG is read from disk once per key.  Each distinct size is scaled once
and cached under `(key, width, height)`, so it is never re-scaled per frame.
A missing or unreadable file is remembered as missing (not retried every
frame) and the code-drawn art is used instead.

## Ship orientation

Draw ship images with the nose pointing right.  The game rotates the image
to the direction of flight, and the lives counter turns it 90 degrees so the
nose points up.  A used life shows the same image in grey, dimmed to about
the brightness of the code-drawn grey rocket.

## Collision

Collision radii remain authoritative in game data
(`ShipSpec.hull_radius`, `ObstacleSpec.radius`, `PickupSpec.radius`) and are
**not** derived from image dimensions or alpha pixels.  Adding a PNG does not
change physics.

## Where to get assets

- Kenney: https://kenney.nl/assets (all packs are CC0, attribution optional)
- OpenGameArt: https://opengameart.org (filter by license, pick CC0)
