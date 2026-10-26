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

## The second pass

One photo at a time gets the floor wrong about 1 time in 10: a main-floor
bedroom with hardwood becomes "the basement family room", the basement kitchen
becomes the main floor. After the photos are read, `review_labels()` sends every
label of the listing and a contact sheet of all the photos (`sheet.py`: numbered
thumbnails, 8 per row, 1 JPEG) to the vision model in 1 call. It sees the
finishes side by side, the order of the photos, the listed rooms per level, and
the stairs, and returns only the photos whose kind, level or room changes
(`Fix`).

Why a sheet: the vision model takes at most a few dozen images per call (50
image parts are refused), and the text model cannot compare finishes it does not
see. On the trial listing the text model missed the 3 basement photos labelled
main floor, or "fixed" the foyer into the basement; with the sheet the vision
model found exactly the 3, in 2 to 3 s, on 2 runs out of 2.

The reviewer is not stable: the same labels get different fixes from call to
call, and one host moved the whole basement to the main floor. So the pass
runs 5 times in parallel and a fix counts only when 3 runs propose the same
photo, kind and level (`consensus()`). A level change then faces a pixel check
(`neighbours_agree()`): a colour histogram of the lower 60% of each thumbnail
(`sheet.finish_histogram`) finds the 5 photos that look most like this one,
among the interior photos not being moved in the same pass. When most of them
sit on another floor, the change is dropped. On the trial listing the 3
hardwood bedrooms are each other's nearest neighbours and then the other
main-floor photos, and the basement kitchen photos sit next to each other, so
a run that moved the bedrooms to the basement is blocked and a run that moved
the basement kitchen out of the main floor goes through.

The pass runs 2 rounds after a read. On the trial listing the first round fixed
2 of the 3 basement photos labelled main floor; the second round, which sees
those 2 already in the basement, fixed the third.

Guards on the model's answer:

- Each fix repeats the label as given (`kind_was`, `level_was`, `room_was`). A fix that does not match the stored label is a misread and is skipped. The first version without these fields wrote "corrected to main" in its reason and "basement" in the field.
- A photo with stairs going down is not the basement: the camera stands above them.
- `room` must be listed on the photo's level. A "Dining room" listed only on the main floor is dropped from a basement photo.
- The level words in the title and the caption are swapped ("Main-floor kitchen" becomes "Basement kitchen"); the rest of the sentence stays.

The change and the model's reason go in the row's `note`, so the API shows what
the second pass did. `POST /api/listings/{id}/photos/review` runs the pass alone.
It takes about 4 s: 1 s to fetch the thumbnails and build the sheet, 3 s for
the 5 calls in parallel.

## The bytes, not the URL

The reader fetches each photo itself and sends it as a JPEG data URL, at most
1280 px on the long side. With the CDN URL alone, the host fetches the image
and may serve a stale copy from its cache: on 308 Morrish Road the first photo
had been a survey drawing before the listing changed its photos, and the model
kept describing "two proposed lots, Part 1 and Part 2" for an aerial photo that
every other client downloaded. The bytes also feed the drawing check below.

## A false floor plan

A `floor_plan` label will later replace the generated plan, so it must be
right. On 308 Morrish Road the model called an aerial drone photo "a survey
drawing with proposed lot areas". A drawing is a light page with little colour,
so `sheet.light_share()` measures the share of light, near-grey pixels in the
thumbnail. A `floor_plan` label on an image below 0.6 is asked for again with
the note that this is a photograph; a second `floor_plan` becomes `other`.

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
