# Zoning pathways (phase 1)

`backend/app/zoning` answers 2 questions for 1 Toronto parcel and 1 proposal:

1. Which zoning standards is the proposal short on, and by how much?
2. Which legal pathways address each shortfall, and what are their risks?

Phase 1 is deterministic. No language model is called. The design, with the later
phases, is in the "Zoning Pathways Design v2" document.

## Pipeline

```
intent (form) ─┐
               ├─> gaps.py ──> gap rows ──┐
lot analysis ──┤                          ├─> facts.py ──> fact bundle ──> cards.match ──> candidates
               └─> standards.py ──> required values (clause ids)
```

| Module | Does | Reads |
|---|---|---|
| `intent.py` | The proposal as a fixed set of fields. A field the user does not give stays `None`. | request body |
| `standards.py` | Required value of each standard for the zone, with the clause ids it rests on. | lot analysis, city height overlay |
| `gaps.py` | Required vs proposed vs existing for 12 standards. Status `complies`, `short`, `unknown` or `not_applicable`. | intent, lot analysis |
| `facts.py` | Flattens everything into dotted paths. `FACT_PATHS` is the list a card trigger may read. | gap rows |
| `predicate.py` | Evaluates a card trigger. Three-valued: a missing fact gives `unknown` and is named. | fact bundle |
| `cards.py` | Loads `playbook/*.yaml`, validates each card, matches and ranks. | fact bundle |
| `service.py` | Orchestration and the response. | all of the above |

### Standards

`lot_frontage`, `lot_area`, `lot_coverage`, `height`, `storeys`, `building_depth`,
`building_length`, `fsi`, `front_setback`, `side_setback`, `rear_setback`, `units`.

Numbers and clause ids come from the city's office consolidation of Zoning By-law
569-2013, Chapter 10 (sections 10.5, 10.10, 10.20, 10.40, 10.60, 10.80), read on
2026-10-24. Zones outside R, RD, RS, RT and RM return every standard as `unknown`.
A site-specific exception flags every row; its text is not read.

### Existing building envelope

`app/lot/analysis.py` now returns `envelope`: the main building's front, side and
rear setbacks, length, depth (rear wall from the required 6.0 m front setback),
width and LiDAR height. The gap analysis uses these as the proposed values when
the intent keeps the walls, and as the "existing" column always. `existing_status`
on a gap row is what decides whether a legal non-conforming pathway exists.

### Playbook cards

A card is 1 YAML file in `backend/app/zoning/playbook/`. Fields:

| Field | Meaning |
|---|---|
| `id`, `name`, `category` | `legal_non_conforming`, `as_of_right`, `minor_variance`, `consent`, `rezoning`, `appeal`, `constraint` |
| `trigger` | A predicate over `FACT_PATHS`. Leaves are `path op literal`; nodes are `all`, `any`, `not`. |
| `covers` | Standards the pathway can remove a gap on |
| `legal_basis` | Clause ids with 1 sentence each and a URL |
| `mechanics` | The steps |
| `risks` | Mandatory. Shown every time the card applies |
| `buyer_questions` | Buyer mode output: questions for the lawyer, agent or builder |
| `professional_notes` | Professional mode output: what to check next |
| `cost_band`, `time_band` | `none … very_high`, `weeks … year_plus` |
| `precedent_work_types` | Committee of Adjustment `WORK_TYPE` values to pull as precedents (phase 1b) |

Loading fails when a trigger reads a fact that is not in `FACT_PATHS`, when a
card has no risk or no legal basis, or when two cards share an id. A planner
reviews every pull request that changes a card.

Ranking: 10 points per short standard the card covers, 5 if the trigger is fully
true, minus a cost penalty. Constraint cards get 8 extra so they sit near the top.

## API

```
POST /api/listings/{id}/zoning/pathways   body: Intent  -> PathwayAnalysis
POST /api/zoning/pathways?lat=&lon=        body: Intent  -> PathwayAnalysis   (not cached)
GET  /api/zoning/playbook                                -> every card
```

Example body:

```json
{"mode": "buyer", "keep_existing_walls": true, "proposed_rear_setback_m": 8.0, "proposed_storeys": 2}
```

The response has the gap rows, the short and unknown standards, the ranked
candidates (`applies` or `may_apply` with the missing facts named), the caveats
and a disclaimer. In buyer mode each candidate carries `questions` to ask a
professional. In professional mode it carries notes on what to check next.

## Tests

```
./start.sh test tests/test_zoning_predicate.py tests/test_zoning_standards.py tests/test_zoning_pathways.py
```

The end-to-end tests build a synthetic RD block and check the 2-walls case: a
house 0.6 m from the side line with a 1.2 m requirement, walls kept, rear wall
pushed out. The alteration card ranks first and covers the side and rear gaps.

## Precedent corpus (phase 1b)

Toronto Open Data publishes "Committee of Adjustment Applications" daily
(package `committee-of-adjustment-applications`): an active file, a closed file
since 2017, and 1 closed file per year back to 2001. Each record has the street
address, the zone label, `WORK_TYPE`, `SUB_TYPE`, `DESCRIPTION`, `HEARING_DATE`,
`C_OF_A_DESCISION`, `OMB_DESCISION` and `STATUSDESC`. It has no variance table
and no coordinates.

What is not available in bulk: the variance table (required vs proposed per
standard). The hearing agenda PDFs on the 4 district schedule pages are item
lists only (file number, address, ward), in every district and in both the 2025
and 2026 layouts. The per-file public hearing notice has the table, but the
Application Information Centre keeps it for about 90 days and older notices
need the paid Research Request Portal. So a precedent here is "what the file
asked for, in the city's words, and what was decided", not a variance-by-
variance comparison.

### Load

`./start.sh city-data` runs 2 steps:

1. The importer (`importer/import_city_data.py`, `coa_csv`) downloads the 18
   datastore dumps, renames the columns to one lower-snake-case header
   (`REFERENCE_FILE#` and `REFERENCE_FILE` become `reference_file`; the yearly
   files' `WARD` and the newer `WARD_NAME` + `WARD_NUMBER` both survive), adds a
   `source` column (`active` or `closed`), and loads the merged CSV as
   `city.coa_raw` with every column as text. The dumps carry no
   `last_modified`, so the package's `last_refreshed` versions the cache.
2. `python -m app.city.coa` builds `city.coa_applications`: 1 row per `SYS_ID`
   (a decided row beats an undecided one), dates parsed (3 formats; typo years
   such as 0227 and 3008 become null), the decision and the appeal normalized,
   and a point from `city.address_points`. The backend entrypoint runs it with
   `--if-needed` on start.

Normalized vocabulary (`app/city/coa.py`):

| Column | Values |
|---|---|
| `decision` | approved, approved_with_conditions, approved_in_part, refused, withdrawn, deferred, pending, unknown. From 40+ raw spellings ("Approved wih Conditions", "conditional approval", "Not Granted"); the status column fills in a blank decision. |
| `appeal` | approved or refused (the board decided the file), dismissed (the committee's decision stands), pending, unknown, or null. `appeal_body` is OMB or TLAB when the text or status says. |
| `outcome` | approved, refused, withdrawn, deferred, pending, unknown. The board's result wins over the committee's. |

Geocoding joins on the normalized street name (same rule as the listing
matcher, `app.city.address.normalize_name`), the exact street number first and a
`lo_num`..`hi_num` range second, with the street type and direction required to
agree when both sides have one. There is no pin to break ties, so a candidate on
a different street is never taken. On 2026-10-24: 94,527 applications, 88,816
placed (94%). The unplaced rows are mostly placeholder addresses such as "99
IBMS CONVERT SCARBOROUGH" and "0 MIDLAND AVE".

### Query

`app/zoning/precedents.py`. `nearby()` is the only database call: every file
within a radius (default 500 m, max 2,000 m, up to 1,500 rows), nearest first,
with optional `work_type` and description filters. `summarize()` counts
outcomes and the approval rate (approved / decided). `for_card()` picks the
files a strategy card calls comparable: `precedent_work_types` (exact
`WORK_TYPE` values: R Addition, New R Building, Sever Lot, ...) or
`precedent_keywords` in the description (garden suite, laneway suite,
fourplex, ...). Garden and laneway suites are not a `WORK_TYPE`, so those cards
use keywords only.

The pathway analysis takes the nearby files as data (`analyze_pathways(...,
precedents=...)`), so it stays pure. It adds 4 facts (`precedents.total`,
`.approved`, `.refused`, `.approval_rate`) that a card trigger may read, a
summary on the answer, and on each candidate the comparable files with up to 5
decided examples (keyword matches first, then most recent).

```
GET /api/listings/{id}/zoning/precedents?radius_m=500&work_type=&q=  -> PrecedentSearch
GET /api/zoning/precedents?lat=&lon=&radius_m=                       -> PrecedentSearch
```

404 when the table is not loaded. The listing page shows "Committee of
Adjustment decisions nearby" under the lot section and the comparable files on
each pathway card.

### Caveats

An approved file nearby is not an approval of this plan: the variance asked for
is unknown, the zone label may differ, and the by-law changed in 2013 and again
with the multiplex permissions in 2023. The answer says so in its caveats. A
later phase can enrich recent files with the hearing notice from the
Application Information Centre while it is still online.

## Phase 2: free text in, a cited answer out

`app/zoning/answer.py` makes 2 structured-output calls to Claude through the
official SDK (`anthropic`, `client.messages.parse`). The model is
`ZONING_MODEL` (default `claude-opus-5-5`); the key is `LLM_API_KEY`.
Without a key both calls raise `ModelUnavailable` and the endpoint returns the
deterministic analysis with a note. Nothing else changes.

1. `parse_intent`: the person's words -> `ParsedIntent`, the same fields as
   `Intent` plus `understood` (one line per fact read) and `unclear` (what no
   field holds). The model fills a field only when the text says it. A number
   that fails `Intent`'s bounds (a negative height) is dropped. Effort `low`.
2. `merge_intent`: detail fields from the form win; the model fills the blanks.
3. The deterministic pipeline runs on the merged intent, exactly as in phase 1.
4. `write_answer`: `_compact_analysis` gives the model the gaps, the ranked cards
   with their legal basis, risks and questions, and the nearby files, each with
   an id (`gap:<standard>`, `card:<id>`, `clause:<clause>`, `file:<reference>`).
   The model returns a `Draft`: headline, sections of paragraphs with citations,
   questions, unknowns. Effort `medium`.
5. `check_citations` keeps a paragraph only when every citation resolves to an
   id in the analysis. A paragraph with no citation, a made-up clause or an
   unknown file is dropped and listed in `Answer.dropped`. An answer with no
   paragraph left is reported as unavailable. The model never adds a rule, a
   number or a file; it can only word what the analysis holds.

```
POST /api/listings/{id}/zoning/ask   body: AskRequest {mode, text?, details?: Intent}
                                     -> AskResponse {intent, understood, unclear, analysis, answer?, answer_note, cached}
```

Answers are cached in `zoning_answers` by listing and `request_hash` (intent
fields without the text, playbook version, `PROMPT_VERSION`, model). The text
itself is not part of the key, so 2 wordings of the same plan cost 1 model call.
Bump `PROMPT_VERSION` when a prompt or an output schema changes.

The form on the listing page takes the text first. "Give the details" opens the
structured fields; a detail typed there wins over the text. The written answer
sits above the gap table, each paragraph with its citation chips, and says how
many paragraphs the check removed.

Tests use a fake client (`tests/test_zoning_answer.py`); no test calls the API.
