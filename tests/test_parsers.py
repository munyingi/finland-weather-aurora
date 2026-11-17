import json
from datetime import datetime, timedelta

import pytest

from ingest import config, fmi, openmeteo, swpc


def test_fmi_observations_parse_and_drop_nan(demo_client, now):
    start = now.replace(minute=0) - timedelta(hours=2)
    rows = fmi.fetch_observations(demo_client, start, start + timedelta(hours=2), chunk_hours=1)
    assert rows, "expected observations"
    assert {r["parameter"] for r in rows} <= set(config.FMI_PARAMETERS)
    assert all(r["value"] == r["value"] for r in rows)  # no NaN
    # n_man is reported as NaN by most stations in the fixture and must be dropped
    n_man = [r for r in rows if r["parameter"] == "n_man"]
    t2m = [r for r in rows if r["parameter"] == "t2m"]
    assert 0 < len(n_man) < len(t2m)
    assert all(isinstance(r["observed_at"], datetime) and r["observed_at"].tzinfo is None for r in rows)


def test_fmi_parser_survives_namespace_version_change():
    xml = b"""<?xml version="1.0"?>
    <wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/3.0" xmlns:gml="http://www.opengis.net/gml/3.3"
        xmlns:BsWfs="http://xml.fmi.fi/schema/wfs/3.0">
      <wfs:member><BsWfs:BsWfsElement>
        <BsWfs:Location><gml:Point><gml:pos>60.17523 24.94459 </gml:pos></gml:Point></BsWfs:Location>
        <BsWfs:Time>2026-11-17T18:00:00Z</BsWfs:Time>
        <BsWfs:ParameterName>t2m</BsWfs:ParameterName><BsWfs:ParameterValue>-2.3</BsWfs:ParameterValue>
      </BsWfs:BsWfsElement></wfs:member>
    </wfs:FeatureCollection>"""
    rows = fmi.parse_observations(xml)
    assert rows == [
        {
            "position_key": "60.1752,24.9446",
            "station_lat": 60.17523,
            "station_lon": 24.94459,
            "observed_at": datetime(2026, 11, 17, 18, 0),
            "parameter": "t2m",
            "value": -2.3,
        }
    ]


def test_fmi_stations_match_observation_positions(demo_client, now):
    stations = fmi.fetch_stations(demo_client)
    obs = fmi.fetch_observations(demo_client, now.replace(minute=0) - timedelta(hours=1), now.replace(minute=0))
    assert {s["position_key"] for s in stations} >= {o["position_key"] for o in obs}
    kumpula = next(s for s in stations if s["fmisid"] == 101004)
    assert kumpula["station_name"] == "Helsinki Kumpula" and kumpula["municipality"] == "Helsinki"
    assert kumpula["active_to"] is None


def test_time_windows_cover_span_without_gaps():
    start = datetime(2026, 11, 1)
    wins = fmi.time_windows(start, start + timedelta(hours=7), 3)
    assert [w[1] - w[0] for w in wins] == [timedelta(hours=3), timedelta(hours=3), timedelta(hours=1)]
    assert all(a[1] == b[0] for a, b in zip(wins, wins[1:], strict=False))
    assert fmi.time_windows(start, start, 3) == []


@pytest.mark.parametrize(
    "payload",
    [
        [["time_tag", "kp", "observed", "noaa_scale"], ["2026-11-17 18:00:00", "4.33", "predicted", "G1"]],
        [{"time_tag": "2026-11-17T18:00:00", "kp": 4.33, "observed": "predicted", "noaa_scale": "G1"}],
    ],
    ids=["header-row", "list-of-objects"],
)
def test_swpc_kp_accepts_both_shapes(payload):
    rows = swpc.parse_kp(json.dumps(payload).encode(), "forecast")
    assert rows == [
        {"block_start": datetime(2026, 11, 17, 18), "product": "forecast", "kp": 4.33, "status": "predicted", "noaa_scale": "G1"}
    ]


def test_swpc_rtsw_keeps_only_the_active_spacecraft():
    mag = json.dumps(
        [
            {"time_tag": "2026-11-17T18:01:00", "active": True, "source": "DSCOVR", "bz_gsm": -7.5, "bt": 9.0},
            {"time_tag": "2026-11-17T18:01:00", "active": False, "source": "ACE", "bz_gsm": 3.0, "bt": 4.0},
        ]
    ).encode()
    plasma = json.dumps(
        [{"time_tag": "2026-11-17T18:01:00", "active": True, "source": "DSCOVR", "proton_speed": 612.3, "proton_density": 5.1}]
    ).encode()
    assert swpc.parse_solar_wind(mag, plasma) == [
        {"observed_at": datetime(2026, 11, 17, 18, 1), "bz_gsm_nt": -7.5, "bt_nt": 9.0, "speed_kms": 612.3, "density_cm3": 5.1}
    ]


def test_swpc_solar_wind_merges_mag_and_plasma():
    mag = json.dumps([["time_tag", "bz_gsm", "bt"], ["2026-11-17 18:01:00.000", "-7.5", "9.0"]]).encode()
    plasma = json.dumps(
        [["time_tag", "density", "speed"], ["2026-11-17 18:01:00.000", "5.1", "612.3"], ["2026-11-17 18:02:00.000", "5.0", None]]
    ).encode()
    rows = swpc.parse_solar_wind(mag, plasma)
    assert rows[0] == {
        "observed_at": datetime(2026, 11, 17, 18, 1),
        "bz_gsm_nt": -7.5,
        "bt_nt": 9.0,
        "speed_kms": 612.3,
        "density_cm3": 5.1,
    }
    assert rows[1]["bz_gsm_nt"] is None and rows[1]["speed_kms"] is None


def test_openmeteo_maps_rows_back_to_cells_by_order(demo_client):
    cells = [{"cell_id": "a", "lat": 69.0, "lon": 21.0}, {"cell_id": "b", "lat": 60.2, "lon": 24.9}]
    rows = openmeteo.fetch_cloud(demo_client, cells)
    hours = config.OPENMETEO_PAST_HOURS + config.OPENMETEO_FORECAST_HOURS
    assert len(rows) == 2 * hours
    lapland = [r["cloud_cover_pct"] for r in rows if r["cell_id"] == "a"]
    south = [r["cloud_cover_pct"] for r in rows if r["cell_id"] == "b"]
    assert sum(lapland) < sum(south)  # demo scenario: clear north, cloudy south


def test_openmeteo_rejects_location_count_mismatch():
    payload = json.dumps([{"hourly": {"time": ["2026-11-17T18:00"], "cloud_cover": [10]}}]).encode()
    with pytest.raises(ValueError, match="returned 1 locations for 2"):
        openmeteo.parse_cloud(payload, ["a", "b"])
