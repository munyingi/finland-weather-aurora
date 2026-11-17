"""H3 hexagon grid covering Finland, with each cell tagged to its region (maakunta).

Geometry work stays in Python (h3 + shapely), so the warehouse needs no spatial
extension and the dbt models are plain SQL that run on any DuckDB build.
"""

from __future__ import annotations

import json
from collections import Counter

import h3
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

from . import config


def load_regions() -> list[dict]:
    with open(config.REGIONS_GEOJSON, encoding="utf-8") as fh:
        fc = json.load(fh)
    regions: dict[str, dict] = {}
    for feat in fc["features"]:
        p = feat["properties"]
        geom = shape(feat["geometry"])
        if p["region_code"] in regions:  # Åland ships as several municipality polygons
            regions[p["region_code"]]["geometry"] = regions[p["region_code"]]["geometry"].union(geom)
        else:
            regions[p["region_code"]] = {**p, "geometry": geom}
    return list(regions.values())


def build_cells(
    res_weather: int = config.H3_RES_WEATHER, res_aurora: int = config.H3_RES_AURORA
) -> tuple[list[dict], list[dict]]:
    """Return (weather cells, aurora cells). Weather cells are children of aurora cells."""
    regions = load_regions()
    assigned: dict[str, dict] = {}
    # Fill the whole country first: simplified region polygons leave slivers along
    # shared borders, and cells whose centre falls in a sliver would be lost.
    country = unary_union([r["geometry"] for r in regions]).buffer(0.02)
    for cell in h3.geo_to_cells(mapping(country), res_weather):
        lat, lon = h3.cell_to_latlng(cell)
        pt = Point(lon, lat)
        region = next((r for r in regions if r["geometry"].contains(pt)), None)
        assigned[cell] = region or min(regions, key=lambda r: r["geometry"].distance(pt))
    for region in regions:
        cells = set(h3.geo_to_cells(mapping(region["geometry"]), res_weather))
        if len(cells) < 10:
            # Archipelagos like Åland are mostly water at this resolution, so a
            # centroid-in-polygon test drops most islands. Use overlap instead.
            shape_ = h3.geo_to_h3shape(mapping(region["geometry"]))
            cells = set(h3.h3shape_to_cells_experimental(shape_, res_weather, contain="overlap"))
        for cell in cells:
            assigned.setdefault(cell, region)

    weather = []
    for cell, region in sorted(assigned.items()):
        lat, lon = h3.cell_to_latlng(cell)
        weather.append(
            {
                "cell_id": cell,
                "h3_res": res_weather,
                "parent_cell_id": h3.cell_to_parent(cell, res_aurora),
                "lat": lat,
                "lon": lon,
                "region_code": region["region_code"],
                "region_name": region["region_name"],
                "region_name_fi": region["region_name_fi"],
            }
        )

    by_parent: dict[str, list[dict]] = {}
    for w in weather:
        by_parent.setdefault(w["parent_cell_id"], []).append(w)
    region_lookup = {r["region_code"]: r for r in regions}
    aurora = []
    for parent, children in sorted(by_parent.items()):
        code = Counter(c["region_code"] for c in children).most_common(1)[0][0]
        lat, lon = h3.cell_to_latlng(parent)
        aurora.append(
            {
                "cell_id": parent,
                "h3_res": res_aurora,
                "parent_cell_id": None,
                "lat": lat,
                "lon": lon,
                "region_code": code,
                "region_name": region_lookup[code]["region_name"],
                "region_name_fi": region_lookup[code]["region_name_fi"],
            }
        )
    return weather, aurora


def region_for_point(lat: float, lon: float, regions: list[dict] | None = None) -> str | None:
    regions = regions or load_regions()
    pt = Point(lon, lat)
    for r in regions:
        if r["geometry"].contains(pt):
            return r["region_code"]
    return None
