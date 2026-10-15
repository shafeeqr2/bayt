const currency = new Intl.NumberFormat("en-CA", {
  style: "currency",
  currency: "CAD",
  maximumFractionDigits: 0,
});

export function formatPrice(value: number): string {
  return currency.format(value);
}

const n = (value: number) => value.toLocaleString("en-CA");

/** Interior size is published as a range bucket, so show it as one. */
export function formatSqft(min: number | null, max: number | null): string | null {
  if (min && max) return min === max ? `${n(min)} sqft` : `${n(min)}-${n(max)} sqft`;
  if (min) return `${n(min)}+ sqft`;
  if (max) return `Up to ${n(max)} sqft`;
  return null;
}

export function bedsLabel(text: string | null): string | null {
  return text ? `${text.replace(/\s+/g, "")} bd` : null;
}

const FEET_PER_METRE = 3.28084;
const SQFT_PER_M2 = 10.7639;

export function formatMetres(value: number | null): string | null {
  return value == null ? null : `${value.toFixed(1)} m (${Math.round(value * FEET_PER_METRE)} ft)`;
}

export function formatArea(m2: number | null): string | null {
  return m2 == null ? null : `${n(Math.round(m2))} m² (${n(Math.round(m2 * SQFT_PER_M2))} sqft)`;
}

export function formatDate(iso: string | null): string | null {
  return iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-CA", { year: "numeric", month: "short", day: "numeric" })
    : null;
}
