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
| `ui.start_marker` | `ui/start_marker.png` | Launch pad / start marker ring |
| `background.space` | `background/space.png` | Tiled full-screen backdrop (optional) |

## Sizing

Each slot declares a default logical-pixel display size in
`vector_drift/image_assets.py` (`AssetSpec.display_w` / `display_h`).  The
image is scaled once with `config.UI_SCALE` and cached; it is never re-scaled
per frame.

Callers may override the size at draw time (e.g. `draw_ship` passes the
per-frame `size`), which takes precedence over the spec.

## Collision

Collision radii remain authoritative in game data
(`ShipSpec.hull_radius`, `ObstacleSpec.radius`, `PickupSpec.radius`) and are
**not** derived from image dimensions or alpha pixels.  Adding a PNG does not
change physics.

## Where to get assets

- Kenney: https://kenney.nl/assets (all packs are CC0, attribution optional)
- OpenGameArt: https://opengameart.org (filter by license, pick CC0)
