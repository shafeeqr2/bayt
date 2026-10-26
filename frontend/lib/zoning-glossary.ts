/**
 * Plain words for each zoning standard, for people who do not know the terms.
 * Keyed by the standard id the backend uses (app/zoning/standards.py).
 */
export type Term = {
  /** Short name for a chip or a line label. */
  name: string;
  /** What it is, in 1 or 2 plain sentences. */
  what: string;
  /** Why the by-law has it, in 1 sentence. */
  why: string;
  /** How it is measured, so the person can check a drawing. */
  how: string;
};

export const GLOSSARY: Record<string, Term> = {
  lot_frontage: {
    name: "Lot frontage",
    what: "The width of the lot where it meets the street.",
    why: "A minimum keeps new lots as wide as the lots around them.",
    how: "Measured along the front lot line, or at the front yard line on a lot that narrows.",
  },
  lot_area: {
    name: "Lot area",
    what: "The size of the whole lot.",
    why: "A minimum stops lots from being split into pieces too small for the street.",
    how: "The area inside the lot lines, in square metres.",
  },
  lot_coverage: {
    name: "Lot coverage",
    what: "The share of the lot that buildings cover, seen from above. Includes a garage or a shed.",
    why: "The rest of the lot stays open for yards, trees and rain water.",
    how: "Footprint of all buildings divided by the lot area, as a percent.",
  },
  height: {
    name: "Height",
    what: "How tall the building is, from the ground to the top of the roof.",
    why: "A limit keeps new houses in scale with the street and protects light to the neighbours.",
    how: "Measured from established grade, the ground level at the street. A sloped lot can change the result.",
  },
  storeys: {
    name: "Storeys",
    what: "The number of floors above ground.",
    why: "Some streets have a storey limit as well as a height limit.",
    how: "A basement does not count when most of it is below ground.",
  },
  building_depth: {
    name: "Building depth",
    what: "How far back the rear wall reaches, measured from the front yard line the by-law requires.",
    why: "It keeps rear walls in line along the street, so one house does not loom over the yards next door.",
    how: "From the required front yard setback to the rear main wall, not from your own front wall.",
  },
  building_length: {
    name: "Building length",
    what: "The length of the house from the front main wall to the rear main wall.",
    why: "A limit stops very long houses that shadow the yards next door.",
    how: "Front main wall to rear main wall. Porches and small bays do not count.",
  },
  fsi: {
    name: "Floor space index",
    what: "All floors added together, divided by the lot area. 0.45 means the floors can total 45% of the lot size.",
    why: "It limits the size of the house as a whole, not only its footprint.",
    how: "Gross floor area as the by-law counts it, divided by lot area. Some basement and garage area is left out.",
  },
  front_setback: {
    name: "Front yard",
    what: "The distance from the front lot line to the front wall of the house.",
    why: "It keeps the houses on a street in a line.",
    how: "On many streets the required value is the average of the 2 neighbours, not a fixed number.",
  },
  side_setback: {
    name: "Side yard",
    what: "The distance from a side lot line to the nearest side wall.",
    why: "It leaves room for access, light and fire safety between houses.",
    how: "The by-law tests each side. The smaller side is the one that matters here.",
  },
  rear_setback: {
    name: "Rear yard",
    what: "The distance from the rear wall of the house to the rear lot line. Your back yard depth.",
    why: "It keeps a band of open yards along the middle of the block.",
    how: "Measured from the rear main wall. The by-law asks for 7.5 m or 25% of the lot depth, whichever is more.",
  },
  units: {
    name: "Units",
    what: "How many homes the building holds.",
    why: "Toronto allows up to 4 units in a house without a hearing, and 6 on some streets.",
    how: "Each self-contained home with its own kitchen counts as 1 unit.",
  },
};
