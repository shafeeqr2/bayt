"use client";

import { useState, type FormEvent } from "react";

import { formatDate } from "@/lib/format";
import {
  APPLICATION_TYPE_LABELS,
  CATEGORY_LABELS,
  COST_LABELS,
  FACT_LABELS,
  TIME_LABELS,
  type Answer,
  type AskRequest,
  type AskResponse,
  type CardPrecedents,
  type Candidate,
  type Gap,
  type Intent,
  type Mode,
  type PathwayAnalysis,
  type Project,
} from "@/lib/zoning";
import { OutcomeLabel, SummaryChips } from "./precedents-ui";

const PROJECTS: [Project, string][] = [
  ["unknown", "Not sure yet"],
  ["addition", "Add to the house (back, side or up)"],
  ["new_build", "Tear down and rebuild"],
  ["convert", "More units inside the existing house"],
  ["garden_suite", "Garden suite in the back yard"],
  ["laneway_suite", "Laneway suite"],
  ["sever", "Split the lot in 2"],
];

type Walls = "" | "yes" | "no";

type Numbers = {
  proposed_units: string;
  proposed_storeys: string;
  proposed_height_m: string;
  proposed_gfa_m2: string;
  proposed_footprint_m2: string;
  proposed_side_setback_m: string;
  proposed_rear_setback_m: string;
  proposed_front_setback_m: string;
};

const NUMBER_FIELDS: [keyof Numbers, string, string][] = [
  ["proposed_units", "Units after the work", "e.g. 2"],
  ["proposed_storeys", "Storeys", "e.g. 3"],
  ["proposed_height_m", "Height (m)", "e.g. 9.5"],
  ["proposed_gfa_m2", "Floor area (m²)", "all floors, as the by-law counts"],
  ["proposed_footprint_m2", "Footprint (m²)", "ground area of all buildings"],
  ["proposed_side_setback_m", "Smallest side yard (m)", "blank = keep the wall where it is"],
  ["proposed_rear_setback_m", "Rear yard (m)", "rear wall to the rear lot line"],
  ["proposed_front_setback_m", "Front yard (m)", "blank = keep the wall where it is"],
];

/**
 * "What could you build here?" The plan in the person's own words, with the detail fields behind a
 * toggle. The backend reads the text into the intent, runs the deterministic analysis, and writes a
 * cited answer when a model key is configured. See docs/zoning-pathways.md.
 */
export function PathwaysPanel({ id }: { id: string }) {
  const [mode, setMode] = useState<Mode>("buyer");
  const [text, setText] = useState("");
  const [showDetails, setShowDetails] = useState(false);
  const [project, setProject] = useState<Project>("unknown");
  const [walls, setWalls] = useState<Walls>("");
  const [numbers, setNumbers] = useState<Numbers>({
    proposed_units: "",
    proposed_storeys: "",
    proposed_height_m: "",
    proposed_gfa_m2: "",
    proposed_footprint_m2: "",
    proposed_side_setback_m: "",
    proposed_rear_setback_m: "",
    proposed_front_setback_m: "",
  });
  const [result, setResult] = useState<AskResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const plan = text.trim();
    const details: Intent = { mode, project };
    if (walls) details.keep_existing_walls = walls === "yes";
    if (project === "sever") details.sever_lot = true;
    let anyDetail = project !== "unknown" || walls !== "";
    for (const [key] of NUMBER_FIELDS) {
      const raw = numbers[key].trim();
      if (raw === "") continue;
      const value = Number(raw);
      if (!Number.isFinite(value) || value <= 0) {
        setError(`"${raw}" is not a valid number.`);
        return;
      }
      details[key] = key === "proposed_units" || key === "proposed_storeys" ? Math.round(value) : value;
      anyDetail = true;
    }
    if (!plan && !anyDetail) {
      setError("Write what you have in mind, or open the details and fill a field.");
      return;
    }
    setBusy(true);
    setError(null);
    const body: AskRequest = { mode, text: plan || null, details: anyDetail ? details : null };
    try {
      const res = await fetch(`/api/listings/${encodeURIComponent(id)}/zoning/ask`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.status === 404) {
        setError("No parcel data for this listing; the analysis covers Toronto lots only.");
        setResult(null);
      } else if (!res.ok) {
        setError(`The analysis failed (${res.status}). Try again in a moment.`);
      } else {
        setResult((await res.json()) as AskResponse);
      }
    } catch {
      setError("Could not reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">What could you build here?</h2>
        <p className="text-sm text-muted">
          Describe the plan. The analysis compares it with Zoning By-law 569-2013 for this lot and lists the public
          routes that address each shortfall, with their risks. No prediction and no legal advice.
        </p>
      </div>

      <form onSubmit={submit} className="space-y-4 rounded-xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <Field label="I am">
            <Segmented
              value={mode}
              onChange={(v) => setMode(v as Mode)}
              options={[
                ["buyer", "buying"],
                ["professional", "a professional"],
              ]}
            />
          </Field>
          <button
            type="button"
            onClick={() => setShowDetails((v) => !v)}
            aria-expanded={showDetails}
            className="rounded-lg border border-border px-3 py-1.5 text-sm text-muted hover:text-foreground"
          >
            {showDetails ? "Hide the details" : "Give the details"}
          </button>
        </div>
        <label className="block space-y-1 text-sm">
          <span className="text-muted">What do you have in mind?</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            maxLength={2000}
            placeholder="e.g. Keep the house and add a third storey, about 10.5 m high, and push the back wall out so the rear yard is 6.5 m."
            className={`${control} resize-y leading-relaxed`}
          />
        </label>
        {showDetails && (
        <div className="space-y-4 border-t border-border pt-4">
        <div className="flex flex-wrap items-end gap-4">
          <Field label="The plan">
            <select value={project} onChange={(e) => setProject(e.target.value as Project)} className={control}>
              {PROJECTS.map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Keep the existing main walls?">
            <select value={walls} onChange={(e) => setWalls(e.target.value as Walls)} className={control}>
              <option value="">Not sure</option>
              <option value="yes">Yes, it is an alteration</option>
              <option value="no">No, it is a new building</option>
            </select>
          </Field>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {NUMBER_FIELDS.map(([key, label, hint]) => (
            <Field key={key} label={label} hint={hint}>
              <input
                type="number"
                inputMode="decimal"
                step="any"
                min="0"
                value={numbers[key]}
                onChange={(e) => setNumbers({ ...numbers, [key]: e.target.value })}
                className={control}
              />
            </Field>
          ))}
        </div>
        <p className="text-xs text-muted">A detail you type here wins over what the text says.</p>
        </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-foreground disabled:opacity-60"
          >
            {busy ? "Checking the by-law…" : "Check the zoning"}
          </button>
          <p className="text-xs text-muted">Say what you know. The answer says what it still needs.</p>
        </div>
        {error && <p className="text-sm text-accent">{error}</p>}
      </form>

      {result && (
        <>
          <Understood result={result} />
          {result.answer ? <WrittenAnswer answer={result.answer} /> : result.answer_note && (
            <p className="rounded-lg bg-background p-3 text-xs leading-relaxed text-muted">{result.answer_note}</p>
          )}
          <Results result={result.analysis} />
        </>
      )}
    </section>
  );
}

/** What the model read from the text, so the person can correct it in the details. */
function Understood({ result }: { result: AskResponse }) {
  if (result.understood.length === 0 && result.unclear.length === 0) return null;
  return (
    <div className="space-y-1 text-sm">
      {result.understood.length > 0 && (
        <p>
          <span className="text-muted">Understood: </span>
          {result.understood.join(" · ")}
        </p>
      )}
      {result.unclear.length > 0 && (
        <p className="text-muted">Not used: {result.unclear.join(" · ")}</p>
      )}
    </div>
  );
}

const CITATION_LABELS: Record<string, string> = { card: "route", clause: "by-law", gap: "standard", file: "file" };

function Citation({ id }: { id: string }) {
  const [kind, ...rest] = id.split(":");
  const value = rest.join(":");
  const label = CITATION_LABELS[kind] ?? kind;
  return (
    <span className="mr-1 inline-block rounded bg-border px-1.5 py-0.5 font-mono text-[10px] text-muted" title={id}>
      {label} {value.replace(/-/g, " ")}
    </span>
  );
}

/** The model's written answer. Every paragraph passed the citation check on the server. */
function WrittenAnswer({ answer }: { answer: Answer }) {
  return (
    <div className="space-y-4 rounded-xl border border-border bg-surface p-5">
      <p className="text-base font-medium leading-snug">{answer.headline}</p>
      {answer.sections.map((section) => (
        <div key={section.heading} className="space-y-2">
          <h3 className="text-sm font-semibold">{section.heading}</h3>
          {section.paragraphs.map((p, i) => (
            <div key={i} className="space-y-1">
              <p className="text-sm leading-relaxed text-foreground/90">{p.text}</p>
              <p className="leading-5">
                {p.citations.map((c) => (
                  <Citation key={c} id={c} />
                ))}
              </p>
            </div>
          ))}
        </div>
      ))}
      {answer.unknowns.length > 0 && <List title="Still unknown" items={answer.unknowns} />}
      {answer.questions.length > 0 && <List title="Ask next" items={answer.questions} />}
      <p className="text-xs text-muted">
        Written by {answer.model} from the analysis below. Every paragraph cites a route, a by-law clause, a standard or a
        nearby file; paragraphs that cited nothing in the analysis were removed
        {answer.dropped.length > 0 && ` (${answer.dropped.length} removed)`}.
      </p>
    </div>
  );
}

const control =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm tabular-nums focus:border-accent focus:outline-none";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block min-w-40 flex-1 space-y-1 text-sm">
      <span className="text-muted">{label}</span>
      {children}
      {hint && <span className="block text-xs text-muted/80">{hint}</span>}
    </label>
  );
}

function Segmented({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (value: string) => void;
  options: [string, string][];
}) {
  return (
    <div className="inline-flex rounded-lg border border-border bg-background p-0.5" role="radiogroup">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          role="radio"
          aria-checked={value === v}
          onClick={() => onChange(v)}
          className={`rounded-md px-3 py-1.5 text-sm ${value === v ? "bg-surface font-medium shadow-sm" : "text-muted"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// -- results -----------------------------------------------------------------

function Results({ result }: { result: PathwayAnalysis }) {
  const shown = result.gaps.filter((g) => g.status !== "not_applicable" || g.existing_status === "short");
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-semibold">
            Zoning check
            {result.zone_label && <span className="ml-2 font-mono text-xs font-normal text-muted">{result.zone_label}</span>}
          </h3>
          <p className="text-sm text-muted">
            {result.short_standards.length === 0
              ? "Nothing short of the by-law in what you gave."
              : `Short on ${result.short_standards.length} ${result.short_standards.length === 1 ? "standard" : "standards"}.`}
            {result.unknown_standards.length > 0 && ` ${result.unknown_standards.length} could not be judged.`}
          </p>
        </div>
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full text-sm">
            <thead className="text-left text-muted">
              <tr className="border-b border-border">
                <th className="px-4 py-2 font-medium">Standard</th>
                <th className="px-4 py-2 font-medium">By-law</th>
                <th className="px-4 py-2 font-medium">Your plan</th>
                <th className="px-4 py-2 font-medium">Today</th>
                <th className="px-4 py-2 font-medium">Result</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((g) => (
                <GapRow key={g.standard} gap={g} />
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="font-semibold">
            {result.mode === "buyer" ? "Routes and the questions to ask" : "Pathways to explore"}
          </h3>
          {result.precedents && result.precedent_radius_m && (
            <p className="text-sm text-muted">
              {result.precedents.total} Committee of Adjustment files within {result.precedent_radius_m} m since 2001
              {result.precedents.approval_rate != null && `, ${Math.round(result.precedents.approval_rate * 100)}% of decided files approved`}
              .
            </p>
          )}
        </div>
        {result.candidates.length === 0 ? (
          <p className="text-sm text-muted">No pathway in the playbook matches what you gave. Fill in more of the plan.</p>
        ) : (
          <ol className="space-y-3">
            {result.candidates.map((c) => (
              <CandidateCard key={c.card_id} c={c} mode={result.mode} />
            ))}
          </ol>
        )}
      </div>

      {result.caveats.length > 0 && (
        <ul className="space-y-1 rounded-lg bg-background p-3 text-xs leading-relaxed text-muted">
          {result.caveats.map((caveat) => (
            <li key={caveat}>{caveat}</li>
          ))}
        </ul>
      )}
      <p className="text-xs leading-relaxed text-muted">{result.disclaimer}</p>
    </div>
  );
}

const STATUS: Record<Gap["status"], [string, string]> = {
  complies: ["Complies", "bg-emerald-600/15 text-emerald-700 dark:text-emerald-300"],
  short: ["Short", "bg-accent/15 text-accent"],
  unknown: ["Unknown", "bg-border text-muted"],
  not_applicable: ["No limit", "bg-border text-muted"],
};

function num(value: number | null, unit: string): string {
  if (value == null) return "—";
  const text = Number.isInteger(value) ? String(value) : value.toFixed(unit === "x lot area" ? 2 : 1);
  if (unit === "%") return `${text}%`;
  if (unit === "x lot area") return `${text} FSI`;
  if (unit === "m2") return `${text} m²`;
  if (unit === "units" || unit === "storeys") return text;
  return `${text} ${unit}`;
}

function GapRow({ gap }: { gap: Gap }) {
  const [label, tone] = STATUS[gap.status];
  const source =
    gap.proposed_source === "existing" ? " (as today)" : gap.proposed_source === "derived" ? " (calculated)" : "";
  return (
    <tr className="border-b border-border align-top last:border-0">
      <td className="px-4 py-2">
        <div>{gap.label}</div>
        {gap.clause_ids.length > 0 && (
          <div className="font-mono text-[11px] text-muted">
            {gap.source_url ? (
              <a href={gap.source_url} target="_blank" rel="noreferrer" className="hover:underline">
                {gap.clause_ids.join(", ")}
              </a>
            ) : (
              gap.clause_ids.join(", ")
            )}
          </div>
        )}
        {gap.note && <div className="text-xs text-muted">{gap.note}</div>}
      </td>
      <td className="px-4 py-2 tabular-nums">
        {gap.required_status === "not_applicable" ? "No limit" : num(gap.required, gap.unit)}
        {gap.required != null && <span className="text-muted"> {gap.kind === "min" ? "min" : "max"}</span>}
      </td>
      <td className="px-4 py-2 tabular-nums">
        {num(gap.proposed, gap.unit)}
        <span className="text-muted">{source}</span>
      </td>
      <td className="px-4 py-2 tabular-nums">
        {num(gap.existing, gap.unit)}
        {gap.existing_status === "short" && <span className="ml-1 text-xs text-accent">short today</span>}
      </td>
      <td className="px-4 py-2">
        <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{label}</span>
        {gap.status === "short" && gap.delta != null && (
          <span className="ml-1 text-xs text-muted">by {num(gap.delta, gap.unit)}</span>
        )}
      </td>
    </tr>
  );
}

function CandidateCard({ c, mode }: { c: Candidate; mode: Mode }) {
  const constraint = c.category === "constraint";
  const needs = c.missing_facts.map((f) => FACT_LABELS[f] ?? f.replace(/^gap\./, "").replace(/[._]/g, " "));
  return (
    <li className={`rounded-xl border bg-surface p-5 ${constraint ? "border-accent/60" : "border-border"}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="rounded-full bg-border px-2 py-0.5 font-medium">{CATEGORY_LABELS[c.category] ?? c.category}</span>
            <span className={c.result === "applies" ? "text-emerald-700 dark:text-emerald-300" : "text-muted"}>
              {c.result === "applies" ? "Applies to this plan" : `May apply, needs ${needs.join(", ")}`}
            </span>
          </div>
          <h4 className="font-medium leading-snug">{c.name}</h4>
        </div>
        <div className="text-right text-xs text-muted">
          <div>{c.decision_body}</div>
          {!constraint && (
            <div>
              {COST_LABELS[c.cost_band] ?? c.cost_band} · {TIME_LABELS[c.time_band] ?? c.time_band}
            </div>
          )}
        </div>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-foreground/90">{c.summary}</p>
      {c.covers_gaps.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          Addresses: {c.covers_gaps.map((s) => s.replace(/_/g, " ")).join(", ")}
        </p>
      )}
      <div className="mt-3 grid gap-4 md:grid-cols-2">
        <List title="Risks" items={c.risks} tone="risk" />
        <List title={mode === "buyer" ? "Ask your lawyer, agent or builder" : "Check next"} items={c.questions} />
      </div>
      {c.precedents && <Comparable p={c.precedents} />}
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer text-muted hover:text-foreground">Steps and legal basis</summary>
        <div className="mt-2 grid gap-4 md:grid-cols-2">
          <List title="Steps" items={c.mechanics} ordered />
          <div>
            <p className="text-xs font-medium text-muted">Legal basis</p>
            <ul className="mt-1 space-y-1 text-xs leading-relaxed">
              {c.legal_basis.map((b) => (
                <li key={b.clause}>
                  {b.url ? (
                    <a href={b.url} target="_blank" rel="noreferrer" className="font-mono hover:underline">
                      {b.clause}
                    </a>
                  ) : (
                    <span className="font-mono">{b.clause}</span>
                  )}{" "}
                  <span className="text-muted">{b.says}</span>
                </li>
              ))}
            </ul>
            {c.why.length > 0 && (
              <p className="mt-2 font-mono text-[11px] text-muted">matched: {c.why.join(" · ")}</p>
            )}
          </div>
        </div>
      </details>
    </li>
  );
}

/** What the committee did with comparable files near this lot: counts, then the most recent decided ones. */
function Comparable({ p }: { p: CardPrecedents }) {
  const what = [...p.work_types, ...p.keywords.map((k) => `"${k}"`)].join(", ");
  if (p.summary.total === 0) {
    return <p className="mt-3 text-xs text-muted">No comparable file nearby ({what}).</p>;
  }
  return (
    <div className="mt-3 space-y-2 rounded-lg bg-background p-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-xs font-medium text-muted">
          Nearby decisions on comparable files <span className="font-normal">({what})</span>
        </p>
        <SummaryChips summary={p.summary} compact />
      </div>
      {p.examples.length > 0 && (
        <ul className="space-y-1.5 text-xs leading-snug">
          {p.examples.map((e) => (
            <li key={e.sys_id} className="grid gap-x-3 sm:grid-cols-[minmax(0,1fr)_auto]">
              <span>
                <span className="font-medium">{e.address ?? "Address withheld"}</span>
                <span className="text-muted">
                  {" "}
                  · {Math.round(e.distance_m)} m
                  {e.hearing_date && ` · ${formatDate(e.hearing_date)}`}
                  {e.application_type && ` · ${APPLICATION_TYPE_LABELS[e.application_type] ?? e.application_type}`}
                </span>
                {e.description && <span className="block text-muted line-clamp-2">{e.description}</span>}
              </span>
              <OutcomeLabel p={e} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function List({ title, items, ordered, tone }: { title: string; items: string[]; ordered?: boolean; tone?: "risk" }) {
  if (items.length === 0) return null;
  const Tag = ordered ? "ol" : "ul";
  return (
    <div>
      <p className={`text-xs font-medium ${tone === "risk" ? "text-accent" : "text-muted"}`}>{title}</p>
      <Tag className={`mt-1 space-y-1 text-sm leading-relaxed ${ordered ? "list-decimal" : "list-disc"} pl-4`}>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </Tag>
    </div>
  );
}
