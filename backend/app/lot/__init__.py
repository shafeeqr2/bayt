"""Lot analysis: how much of a lot is built on, and whether it could hold another home.

- `toronto.py` fetches parcels, building footprints, zoning and street centrelines
  from the City of Toronto's public ArcGIS services (same source as Open Data Toronto).
- `analysis.py` is pure geometry + zoning arithmetic with no I/O, so it is unit-testable.
- `service.py` ties them together and caches results per listing.
"""
