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

export type Outcome = "approved" | "refused" | "withdrawn" | "deferred" | "pending" | "unknown";

/** One Committee of Adjustment application near the lot, from Toronto Open Data. */
export type Precedent = {
  sys_id: string;
  reference_file: string | null;
  application_type: "MV" | "CO" | null;
  work_type: string | null;
  sub_type: string | null;
  description: string | null;
  zoning_designation: string | null;
  address: string | null;
  planning_district: string | null;
  in_date: string | null;
  hearing_date: string | null;
  decision: string;
  decision_raw: string | null;
  appeal: string | null;
  appeal_body: string | null;
  outcome: Outcome;
  status: string | null;
  distance_m: number;
  lat: number;
  lon: number;
};

export type PrecedentSummary = {
  total: number;
  approved: number;
  refused: number;
  withdrawn: number;
  deferred: number;
  pending: number;
  unknown: number;
  approval_rate: number | null;
  appealed: number;
  by_work_type: Record<string, number>;
  oldest_hearing: string | null;
  newest_hearing: string | null;
};

export type CardPrecedents = {
  work_types: string[];
  keywords: string[];
  summary: PrecedentSummary;
  examples: Precedent[];
};

export type PrecedentSearch = {
  lat: number;
  lon: number;
  radius_m: number;
  work_type: string | null;
  query: string | null;
  summary: PrecedentSummary;
  items: Precedent[];
  truncated: boolean;
  source_url: string;
  note: string;
};

export const OUTCOME_LABELS: Record<Outcome, string> = {
  approved: "Approved",
  refused: "Refused",
  withdrawn: "Withdrawn",
  deferred: "Deferred",
  pending: "Pending",
  unknown: "No decision on file",
};

export const APPLICATION_TYPE_LABELS: Record<string, string> = {
  MV: "Minor variance",
  CO: "Consent",
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
  precedents: CardPrecedents | null;
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
  precedents: PrecedentSummary | null;
  precedent_radius_m: number | null;
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

/** A paragraph of the written answer and the ids it rests on (card:, clause:, gap:, file:). */
export type AnswerParagraph = { text: string; citations: string[] };
export type AnswerSection = { heading: string; paragraphs: AnswerParagraph[] };

export type Answer = {
  headline: string;
  sections: AnswerSection[];
  questions: string[];
  unknowns: string[];
  dropped: string[];
  model: string;
  prompt_version: number;
};

export type AskRequest = {
  mode: Mode;
  text?: string | null;
  details?: Intent | null;
};

export type AskResponse = {
  intent: Intent;
  understood: string[];
  unclear: string[];
  analysis: PathwayAnalysis;
  answer: Answer | null;
  answer_note: string | null;
  cached: boolean;
};
