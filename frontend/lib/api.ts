import "server-only";

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

export type ListingSummary = {
  id: string;
  mls_number: string | null;
  price: number;
  building_type: string | null;
  ownership_type: string | null;
  bedrooms_text: string | null;
  bedrooms_total: number | null;
  bathrooms: number | null;
  sqft_min: number | null;
  sqft_max: number | null;
  address: string | null;
  city: string | null;
  community: string | null;
  cover_photo: string | null;
};

export type ListingDetail = ListingSummary & {
  url: string | null;
  property_type: string | null;
  bedrooms_above: number | null;
  bedrooms_below: number | null;
  stories: string | null;
  lot_size: string | null;
  parking_spaces: number | null;
  postal_code: string | null;
  cross_streets: string | null;
  latitude: number | null;
  longitude: number | null;
  tax_annual: number | null;
  maintenance_fee_monthly: number | null;
  description: string | null;
  photos: { high: string; medium: string; low: string }[];
  rooms: { type: string | null; level: string | null; dimension: string | null }[];
};

export type ListingPage = {
  items: ListingSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type Facets = { cities: string[]; building_types: string[] };

async function get<T>(path: string): Promise<T | null> {
  const res = await fetch(`${BACKEND_URL}${path}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json();
}

export async function getListings(params: URLSearchParams): Promise<ListingPage> {
  return (await get<ListingPage>(`/api/listings?${params}`))!;
}

export async function getFacets(): Promise<Facets> {
  return (await get<Facets>("/api/listings/facets"))!;
}

export async function getListing(id: string): Promise<ListingDetail | null> {
  return get<ListingDetail>(`/api/listings/${encodeURIComponent(id)}`);
}
