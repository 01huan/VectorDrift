# Vector Drift image assets

Place CC0 (public domain) PNG files here.  Every slot is looked up by a
resource key; when the file is missing the game silently falls back to the
existing pygame code-drawn art, so the game is fully playable without any PNG.

## Resource key -> file name

| Resource key | File (relative to this folder) | Used for |
|--------------|-------------------------------|----------|
| `ship.drifter` | `ships/drifter.png` | Player ship (panel preview, lives icon, in-flight sprite) |
| `target.planet` | `targets/planet.png` | Destination / target planet |
| `obstacle.bumper` | `obstacles/bumper.png` | Circular bumper obstacle |
| `pickup.bomb` | `pickups/bomb.png` | Bomb pickup |
| `pickup.add_time` | `pickups/add_time.png` | Add-time pickup |
| `pickup.penetrate` | `pickups/penetrate.png` | Penetrate pickup |
| `ui.start_marker` | `ui/start_marker.png` | Launch pad / start marker ring |
| `background.space` | `background/space.png` | Tiled full-screen backdrop (optional) |

`targets/planet.png` is not included at the moment, so the game draws the
target planet in code.

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
