/** Shapes shared by the zoning pathways form (browser) and the API route. No server-only imports. */

export type Mode = "buyer" | "professional";
export type Project = "addition" | "new_build" | "convert" | "garden_suite" | "laneway_suite" | "sever" | "unknown";

/** What the user wants to build. A field left out means "not given", never zero. */
export type Intent = {
  mode: Mode;
  project: Project;
  text?: string | null;
  keep_existing_walls?: boolean | null;
  sever_lot?: boolean | null;
  proposed_units?: number | null;
  proposed_storeys?: number | null;
  proposed_height_m?: number | null;
  proposed_gfa_m2?: number | null;
  proposed_footprint_m2?: number | null;
  proposed_building_depth_m?: number | null;
  proposed_building_length_m?: number | null;
  proposed_front_setback_m?: number | null;
  proposed_side_setback_m?: number | null;
  proposed_rear_setback_m?: number | null;
};

export type GapStatus = "complies" | "short" | "unknown" | "not_applicable";

export type Gap = {
  standard: string;
  label: string;
  kind: "min" | "max";
  unit: string;
  required: number | null;
  required_status: "known" | "unknown" | "not_applicable";
  proposed: number | null;
  proposed_source: "intent" | "existing" | "derived" | null;
  existing: number | null;
  status: GapStatus;
  existing_status: GapStatus;
  delta: number | null;
  relief_pct: number | null;
  clause_ids: string[];
  source_url: string | null;
  note: string | null;
};

export type Candidate = {
  card_id: string;
  name: string;
  category: string;
  result: "applies" | "may_apply";
  summary: string;
  decision_body: string;
  covers_gaps: string[];
  missing_facts: string[];
  why: string[];
  legal_basis: { clause: string; says: string; url: string | null }[];
  mechanics: string[];
  risks: string[];
  questions: string[];
  cost_band: string;
  time_band: string;
  score: number;
};

export type PathwayAnalysis = {
  mode: Mode;
  intent: Intent;
  zone_label: string | null;
  zone: string | null;
  gaps: Gap[];
  short_standards: string[];
  unknown_standards: string[];
  candidates: Candidate[];
  missing_facts: string[];
  caveats: string[];
  playbook_version: string;
  disclaimer: string;
  computed_at: string;
};

export const CATEGORY_LABELS: Record<string, string> = {
  legal_non_conforming: "Existing rights",
  as_of_right: "No hearing needed",
  minor_variance: "Minor variance",
  consent: "Consent",
  rezoning: "Rezoning",
  appeal: "Appeal",
  constraint: "Constraint",
};

export const COST_LABELS: Record<string, string> = {
  none: "No extra cost",
  low: "Low cost",
  medium: "Medium cost",
  high: "High cost",
  very_high: "Very high cost",
};

export const TIME_LABELS: Record<string, string> = {
  weeks: "Weeks",
  months: "Months",
  half_year: "Around half a year",
  year_plus: "A year or more",
};

/** Human names for the fact paths a card may say it needs. */
export const FACT_LABELS: Record<string, string> = {
  "intent.keep_existing_walls": "whether the existing main walls stay",
  "intent.proposed_units": "the number of units",
  "intent.proposed_storeys": "the number of storeys",
  "intent.proposed_height_m": "the proposed height",
  "intent.proposed_gfa_m2": "the proposed floor area",
  "heritage.listed": "the heritage register status",
};
