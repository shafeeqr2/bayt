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

// REALTOR.ca lists parking as comma-joined features, e.g. "Attached Garage, Garage" or
// "Underground, No Garage". "Garage" / "No Garage" are redundant flags once a specific kind is given.
const PARKING_KINDS: Record<string, string> = {
  Underground: "underground",
  "Attached Garage": "attached garage",
  "Detached Garage": "detached garage",
  Carport: "carport",
  Street: "street parking",
  "Visitor Parking": "visitor parking",
  Tandem: "tandem",
  Shared: "shared",
  Covered: "covered",
  "Inside Entry": "inside entry",
};

/** "2 spaces, underground" or "1 space, no garage". Null when the listing says nothing about parking. */
export function formatParking(spaces: number | null, type: string | null): string | null {
  const features = (type ?? "")
    .split(",")
    .map((feature) => feature.trim())
    .filter(Boolean);
  const kinds = features.map((feature) => PARKING_KINDS[feature]).filter(Boolean);
  if (kinds.length === 0) {
    if (features.includes("Garage")) kinds.push("garage");
    else if (features.includes("No Garage") || features.includes("None")) kinds.push("no garage");
  }
  // "0 spaces, underground" is common for condos: the building has a garage but no space comes with the unit.
  const count = spaces == null ? null : spaces === 0 ? "None included" : spaces === 1 ? "1 space" : `${n(spaces)} spaces`;
  const parts = [count, kinds.length ? kinds.join(", ") : null].filter(Boolean);
  return parts.length ? parts.join(", ") : null;
}

export function formatDate(iso: string | null): string | null {
  return iso
    ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-CA", { year: "numeric", month: "short", day: "numeric" })
    : null;
}
