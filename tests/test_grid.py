from collections import Counter

import h3

from ingest import grid


def test_grid_covers_every_region():
    weather, aurora = grid.build_cells()
    regions = {r["region_code"] for r in grid.load_regions()}
    assert len(regions) == 19  # 18 mainland regions + Åland
    assert {c["region_code"] for c in weather} == regions
    assert 1500 < len(weather) < 2000
    assert 200 < len(aurora) < 350


def test_cells_are_unique_and_children_point_to_aurora_cells():
    weather, aurora = grid.build_cells()
    assert max(Counter(c["cell_id"] for c in weather).values()) == 1
    aurora_ids = {c["cell_id"] for c in aurora}
    assert all(c["parent_cell_id"] in aurora_ids for c in weather)
    assert all(h3.get_resolution(c["cell_id"]) == 5 for c in weather)


def test_region_lookup_for_known_places():
    regions = grid.load_regions()
    assert grid.region_for_point(60.17, 24.94, regions) == "FI-18"  # Helsinki, Uusimaa
    assert grid.region_for_point(69.05, 20.79, regions) == "FI-10"  # Kilpisjärvi, Lapland
    assert grid.region_for_point(61.50, 23.76, regions) == "FI-11"  # Tampere, Pirkanmaa
    assert grid.region_for_point(59.0, 30.0, regions) is None  # Gulf of Finland, Russia side
