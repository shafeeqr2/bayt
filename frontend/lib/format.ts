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
