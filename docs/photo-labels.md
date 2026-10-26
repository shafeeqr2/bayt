# Photo labels

Each listing photo gets a title, one sentence about the house, and a set of facts
a floor plan can use. A vision model reads the photos; the results live in the
`listing_photos` table and show under the gallery on the listing page.

## What the model returns

One structured call per photo (`app/photos/reader.py`, `PhotoFacts`):

| Field | Meaning |
|---|---|
| `kind` | `exterior_front`, `exterior_back`, `exterior_side`, `street`, `aerial`, `interior`, `floor_plan`, `other` |
| `title` | 2 to 5 words: "Kitchen", "Front of the house" |
| `caption` | 1 sentence, at most 25 words, about the house. Not the furniture. |
| `level` | `basement`, `main`, `second`, `third`, `unknown`; null for exterior photos |
| `room` | The listed room the photo most likely shows, copied from the listing |
| `windows`, `window_wall` | Count, and the wall they are on from the camera: `left`, `right`, `far`, `several` |
| `exterior_doors` | Doors to outside in the photo |
| `stairs` | `none`, `up`, `down`, `both` |
| `open_to` | Other rooms visible through an opening with no door |
| `storeys` | Storeys above ground; exterior photos only |
| `garage` | `left`, `right`, `centre`, `none` as seen from the street; front photos only |

The model sees the listing facts (type, storeys, bedrooms, bathrooms, parking) and
the listed rooms with levels and sizes, so `room` names a listed room and `level`
tells 2 rooms with the same name apart.

`clean()` keeps the facts honest after the call: `room` must name a listed room,
exterior facts stay only on exterior photos, `open_to` drops "none", and a window
count with `window_wall = none` becomes `unknown`.

## Furniture

The buyer wants the room, not the staging. The prompt says what stays with the
house (floors, counters, cabinets, tile, fireplaces, tubs, sinks, closets) and
what leaves (furniture, curtains, blinds, lamps, decor). Major appliances count
as part of the house: a Toronto listing usually includes the fridge, stove,
dishwasher, microwave, washer and dryer, so a kitchen or laundry caption names
them. The model still names furniture in about 1 caption in 5. A caption that
matches the `FURNITURE` word list is asked for once more, with the words to
leave out named. The second answer wins when it names fewer of them.

## Model and format

| Provider | Default vision model |
|---|---|
| OpenRouter (`sk-or-`) | `nvidia/nemotron-3.5-super-vl` |
| NVIDIA NIM (`nvapi-`) | `nvidia/nemotron-3.5-super-vl` |
| Anthropic (`sk-ant-`) | `claude-opus-5-5` |

`PHOTO_MODEL` in `.env` overrides it. The zoning text model does not read images.

The OpenAI-style backend calls the vision model in plain JSON mode
(`response_format: {"type": "json_object"}`, schema in the system prompt), not
the grammar-constrained `json_schema` mode the zoning calls use. On the Nemotron
vision model the constrained mode stalls on enum fields: it emits whitespace until
the token budget is gone, and 20 of 50 photos failed that way in the first trial.
Plain JSON mode read all 50 at about 1 s per photo, and pydantic still rejects a
wrong shape.

Rejected: `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`. It labelled a
bathroom and a basement as floor plans and listed every room as "open to".

## Cost and speed, measured 2026-10-25

| | |
|---|---|
| 1 photo at the 1600 px size | 1 to 2 s, about $0.0004 |
| 50 photos, 6 in parallel | 8.4 s, about $0.02 |

## API

```bash
# The stored labels. Never calls the model.
curl http://localhost:8000/api/listings/30401713/photos

# Read the photos that have no current label (all of them with ?force=true).
curl -X POST "http://localhost:8000/api/listings/30401713/photos/read"
```

Reading is explicit. Opening a listing page shows the stored labels and never
calls the model. Nothing reads all listings in bulk yet.

## What comes next

The facts are the input for the floor plan rework: the front photo fixes the
garage side and the storeys, `window_wall` and `open_to` constrain where rooms
sit, `stairs` fixes the stair position, and a `floor_plan` photo replaces the
generated plan.
