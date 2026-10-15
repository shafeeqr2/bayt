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

export type Permit = {
  permit_num: string;
  revision_num: string | null;
  permit_type: string | null;
  structure_type: string | null;
  work: string | null;
  status: string | null;
  application_date: string | null;
  issued_date: string | null;
  completed_date: string | null;
  description: string | null;
  current_use: string | null;
  proposed_use: string | null;
  dwelling_units_created: number | null;
  dwelling_units_lost: number | null;
  est_construction_cost: number | null;
};

export type CityData = {
  match_method: "address" | "nearest";
  match_distance_m: number | null;
  address_full: string | null;
  former_municipality: string | null;
  ward: string | null;
  parcel_id: number | null;
  lot_area_m2: number | null;
  lot_frontage_m: number | null;
  lot_depth_m: number | null;
  lot_geojson: { type: "MultiPolygon"; coordinates: number[][][][] } | null;
  zone_category: string | null;
  zone_label: string | null;
  zone_rules: { label: string; value: string }[];
  zone_string: string | null;
  zone_exception: string | null;
  zoning_bylaw_section: string | null;
  height_limit_m: number | null;
  height_limit_storeys: number | null;
  lot_coverage_pct: number | null;
  parking_zone: string | null;
  policy_area: string | null;
  rooming_house_area: string | null;
  heritage_status: string | null;
  permits: Permit[];
};

/** City of Toronto lot, zoning and permits; null outside Toronto or before `./start.sh city-data`. */
export async function getCityData(id: string): Promise<CityData | null> {
  return get<CityData>(`/api/listings/${encodeURIComponent(id)}/city`);
}
