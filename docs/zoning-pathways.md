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

## Precedent corpus (phase 1b, not built yet)

Toronto Open Data publishes "Committee of Adjustment Applications" daily
(package `committee-of-adjustment-applications`): active files, closed files
since 2017, and 1 file per year back to 2001. Each record has the address, the
zone label, `WORK_TYPE`, `SUB_TYPE`, `DESCRIPTION`, `HEARING_DATE`,
`C_OF_A_DESCISION`, `OMB_DESCISION` and `STATUSDESC`. It has no variance table
and no coordinates. The variance tables (required vs proposed per standard) are
in the hearing agenda PDFs on each district's schedule page, which go back about
1 year. Decision notices after the appeal period need the paid Research Request
Portal. "Local Appeals Body Appeals" is a separate monthly dataset.

Plan: load the open data, geocode by address against `city.address_points`, join
to parcels, and extract variance tables from the agenda PDFs for the last year.
