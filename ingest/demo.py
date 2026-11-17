"""Offline demo mode.

`DemoClient` answers the same URLs as the live APIs with synthetic payloads in
the real response formats (FMI WFS XML, SWPC JSON, Open-Meteo JSON). The data is
fake, but it flows through the real parsers, loaders and dbt models, which is
what CI tests. Values are deterministic per (station, hour) so overlapping
requests return identical numbers, like the real API.

The scenario: a cold, clear night in Lapland, a front over the south coast and
a geomagnetic storm peaking near Kp 4 tonight: overhead in Lapland,
low on the horizon in central Finland, marginal on the south coast.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from urllib.parse import urlparse

from . import config

# Real FMI station names and approximate coordinates. fmisids are illustrative.
DEMO_STATIONS = [
    (100971, "Helsinki Kaisaniemi", "Helsinki", 60.1752, 24.9446),
    (101004, "Helsinki Kumpula", "Helsinki", 60.2031, 24.9613),
    (100968, "Vantaa Helsinki-Vantaan lentoasema", "Vantaa", 60.3267, 24.9565),
    (100932, "Hanko Tulliniemi", "Hanko", 59.8100, 22.9100),
    (101065, "Turku Artukainen", "Turku", 60.5141, 22.2623),
    (100907, "Maarianhamina lentoasema", "Maarianhamina", 60.1225, 19.9026),
    (101030, "Kotka Rankki", "Kotka", 60.3758, 26.9619),
    (101237, "Lappeenranta lentoasema", "Lappeenranta", 61.0442, 28.1440),
    (101152, "Lahti Laune", "Lahti", 60.9763, 25.6195),
    (101124, "Tampere Härmälä", "Tampere", 61.4656, 23.7472),
    (101044, "Pori lentoasema", "Pori", 61.4617, 21.7999),
    (101339, "Jyväskylä lentoasema", "Jyväskylä", 62.3995, 25.6784),
    (101398, "Mikkeli lentoasema", "Mikkeli", 61.6880, 27.2010),
    (101436, "Savonlinna lentoasema", "Savonlinna", 61.9440, 28.9450),
    (101580, "Kuopio Savilahti", "Kuopio", 62.8920, 27.6339),
    (101608, "Joensuu Linnunlahti", "Joensuu", 62.6029, 29.7246),
    (101464, "Vaasa lentoasema", "Vaasa", 63.0507, 21.7622),
    (101485, "Seinäjoki Pelmaa", "Seinäjoki", 62.9467, 22.4854),
    (101662, "Kokkola Hollihaka", "Kokkola", 63.8382, 23.1167),
    (101786, "Oulu lentoasema", "Oulu", 64.9300, 25.3544),
    (101588, "Nurmes Valtimontie", "Nurmes", 63.5440, 29.1300),
    (101725, "Kajaani lentoasema", "Kajaani", 64.2853, 27.6922),
    (101846, "Kemi Ajos", "Kemi", 65.6700, 24.5200),
    (101887, "Kuusamo lentoasema", "Kuusamo", 65.9876, 29.2328),
    (101920, "Rovaniemi lentoasema", "Rovaniemi", 66.5640, 25.8303),
    (101966, "Salla kirkonkylä", "Salla", 66.8327, 28.6638),
    (101932, "Sodankylä Tähtelä", "Sodankylä", 67.3672, 26.6290),
    (101986, "Kittilä lentoasema", "Kittilä", 67.7006, 24.8467),
    (102033, "Enontekiö lentoasema", "Enontekiö", 68.3623, 23.4221),
    (102016, "Kilpisjärvi kyläkeskus", "Enontekiö", 69.0434, 20.7865),
    (102047, "Inari Ivalo lentoasema", "Inari", 68.6075, 27.4054),
    (102035, "Utsjoki Kevo", "Utsjoki", 69.7559, 27.0105),
]
NO_SNOW_SENSOR = {101030, 100932}  # coastal stations without a snow sensor, like the real network
BAD_SENSOR = 101152  # emits one physically impossible reading, filtered by dbt


def _u(*keys) -> float:
    """Deterministic uniform [0, 1) noise."""
    h = hashlib.sha256("|".join(map(str, keys)).encode()).hexdigest()
    return int(h[:12], 16) / 16**12


def _hour_index(ts: datetime) -> float:
    return (ts - datetime(2026, 1, 1)).total_seconds() / 3600.0


def storm_peak(now: datetime) -> datetime:
    """The coming 21:00 UTC (23:00 Helsinki time): the storm peaks 'tonight'."""
    peak = now.replace(hour=21, minute=0, second=0, microsecond=0)
    return peak if now - peak < timedelta(hours=3) else peak + timedelta(days=1)


def demo_kp(ts: datetime, now: datetime) -> float:
    dt = (ts - storm_peak(now)).total_seconds() / 3600.0
    return round(min(9.0, 1.33 + 2.67 * math.exp(-((dt / 7.0) ** 2)) + 0.3 * _u("kp", ts)), 2)


def station_value(st, param: str, ts: datetime) -> float | None:
    fmisid, _, _, lat, lon = st
    h = _hour_index(ts)
    hour = ts.hour
    noise = _u(fmisid, param, ts) - 0.5
    if param == "t2m":
        base = 3.0 - (lat - 60.0) * 1.35
        diurnal = 1.8 * math.cos((hour - 13) / 24 * 2 * math.pi)
        synoptic = 3.5 * math.sin(h / 80.0 * 2 * math.pi + lon / 6.0)
        night = hour >= 18 or hour <= 6
        cold_pocket = -11.5 if (lat > 67.0 and lon > 23.0 and night) else 0.0  # clear-sky inversion in Lapland
        if fmisid == BAD_SENSOR and int(h) % 11 == 5:
            return 99.9  # sensor glitch
        return round(base + diurnal + synoptic + cold_pocket + 1.2 * noise, 1)
    if param in ("ws_10min", "wg_10min"):
        coast = 2.5 if lat < 61.0 or lon < 22.5 else 0.0
        front = (
            17.0 * math.exp(-((((h % 48) - 30) / 4.0) ** 2)) if (lat < 61.0 and lon < 25.5) else 0.0
        )  # gale on the southwest coast
        mean = max(0.3, 2.5 + coast + front + 2.0 * noise)
        return round(mean if param == "ws_10min" else mean * 1.6 + abs(noise) * 3, 1)
    if param == "r_1h":
        wet = math.sin(h / 80.0 * 2 * math.pi + lon / 6.0) > 0.35 and lat < 64.0
        if fmisid == 101065 and int(h) % 48 == 31:
            return 11.8  # a downpour in Turku
        return round(max(0.0, (1.4 + 1.5 * noise) if wet else 0.0), 1)
    if param == "snow_aws":
        if fmisid in NO_SNOW_SENSOR:
            return None
        depth = max(0.0, (lat - 62.5) * 9.0)
        storm_snow = 12.0 if (lat > 66 and (h % 96) > 50) else 0.0
        return round(depth + storm_snow + abs(noise), 0) if depth > 0 else 0.0
    if param == "n_man":
        if fmisid % 3:  # manual cloud observations exist only at some stations
            return None
        return float(round(min(8, max(0, 8 * (1 / (1 + math.exp((lat - 62.5) * 1.4))) + 2 * noise))))
    if param == "rh":
        return round(min(100.0, 85 + 12 * noise), 0)
    if param == "p_sea":
        return round(1005 + 12 * math.sin(h / 80.0 * 2 * math.pi) + 2 * noise, 1)
    return None


def cloud_cover(lat: float, lon: float, ts: datetime) -> tuple[float, float]:
    h = _hour_index(ts)
    front_edge = 62.0 + 0.8 * math.sin(h / 30.0) + (lon - 25.0) * 0.08  # cloud south of this latitude
    total = 100.0 / (1.0 + math.exp((lat - front_edge) * 1.8))
    total += 18.0 * (_u("cc", round(lat, 1), round(lon, 1), ts) - 0.5)
    if 64.0 < lat < 66.0 and 27.0 < lon < 30.0:
        total += 35.0  # a cloud patch over Kuusamo, so the map is not one clean gradient
    total = max(0.0, min(100.0, total))
    return round(total), round(total * 0.6)


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", ""))


class DemoClient:
    def __init__(self, now: datetime) -> None:
        self.now = now
        self.calls: list[str] = []

    def get(self, url: str, params: dict | None = None) -> bytes:
        params = params or {}
        self.calls.append(url)
        path = urlparse(url).path
        if url.startswith(config.FMI_WFS_URL):
            if params.get("storedquery_id") == config.FMI_STATIONS_QUERY:
                return self._stations_xml()
            return self._observations_xml(_ts(params["starttime"]), _ts(params["endtime"]), params["parameters"].split(","))
        if path.endswith("noaa-planetary-k-index.json"):
            return self._kp_observed()
        if path.endswith("noaa-planetary-k-index-forecast.json"):
            return self._kp_forecast()
        if path.endswith("rtsw_mag_1m.json"):
            return self._solar_wind("mag")
        if path.endswith("rtsw_wind_1m.json"):
            return self._solar_wind("plasma")
        if url.startswith(config.OPENMETEO_URL):
            return self._openmeteo(params)
        raise ValueError(f"DemoClient has no fixture for {url}")

    # --- FMI -------------------------------------------------------------
    def _stations_xml(self) -> bytes:
        parts = []
        for fmisid, name, muni, lat, lon in DEMO_STATIONS:
            parts.append(
                f"""<wfs:member><ef:EnvironmentalMonitoringFacility gml:id="wfs1-{fmisid}">
<gml:identifier codeSpace="http://xml.fmi.fi/namespace/stationcode/fmisid">{fmisid}</gml:identifier>
<gml:name codeSpace="http://xml.fmi.fi/namespace/locationcode/name">{name}</gml:name>
<gml:name codeSpace="http://xml.fmi.fi/namespace/location/region">{muni}</gml:name>
<ef:representativePoint><gml:Point gml:id="p-{fmisid}" srsName="http://www.opengis.net/def/crs/EPSG/0/4258"><gml:pos>{lat:.4f} {lon:.4f}</gml:pos></gml:Point></ef:representativePoint>
<ef:operationalActivityPeriod><ef:OperationalActivityPeriod><ef:activityTime><gml:TimePeriod gml:id="t-{fmisid}"><gml:beginPosition>1990-01-01T00:00:00Z</gml:beginPosition><gml:endPosition indeterminatePosition="now"/></gml:TimePeriod></ef:activityTime></ef:OperationalActivityPeriod></ef:operationalActivityPeriod>
<ef:belongsTo xlink:title="Automaattinen sääasema" xlink:href="http://xml.fmi.fi/namespace/networkcode/121"/>
</ef:EnvironmentalMonitoringFacility></wfs:member>"""
            )
        return self._wfs(parts)

    def _observations_xml(self, start: datetime, end: datetime, params: list[str]) -> bytes:
        parts = []
        ts = start.replace(minute=0, second=0)
        if ts < start:
            ts += timedelta(hours=1)
        last_hour = min(end, self.now)
        i = 0
        while ts <= last_hour:
            for st in DEMO_STATIONS:
                for p in params:
                    v = station_value(st, p, ts)
                    if v is None and p != "n_man":  # FMI sends NaN for missing manual obs
                        continue
                    i += 1
                    val = "NaN" if v is None else f"{v}"
                    parts.append(
                        f"""<wfs:member><BsWfs:BsWfsElement gml:id="BsWfsElement.1.{i}">
<BsWfs:Location><gml:Point gml:id="BsWfsElementP.1.{i}" srsDimension="2" srsName="http://www.opengis.net/def/crs/EPSG/0/4258"><gml:pos>{st[3]:.5f} {st[4]:.5f} </gml:pos></gml:Point></BsWfs:Location>
<BsWfs:Time>{ts:%Y-%m-%dT%H:%M:%S}Z</BsWfs:Time><BsWfs:ParameterName>{p}</BsWfs:ParameterName><BsWfs:ParameterValue>{val}</BsWfs:ParameterValue>
</BsWfs:BsWfsElement></wfs:member>"""
                    )
            ts += timedelta(hours=1)
        return self._wfs(parts)

    @staticmethod
    def _wfs(members: list[str]) -> bytes:
        head = (
            '<?xml version="1.0" encoding="UTF-8"?>\n<wfs:FeatureCollection '
            'xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2" '
            'xmlns:BsWfs="http://xml.fmi.fi/schema/wfs/2.0" xmlns:xlink="http://www.w3.org/1999/xlink" '
            'xmlns:ef="http://inspire.ec.europa.eu/schemas/ef/4.0" '
            f'numberMatched="{len(members)}" numberReturned="{len(members)}">'
        )
        return (head + "\n".join(members) + "</wfs:FeatureCollection>").encode("utf-8")

    # --- SWPC ------------------------------------------------------------
    def _blocks(self, start: datetime, end: datetime):
        ts = start.replace(hour=start.hour - start.hour % 3, minute=0, second=0, microsecond=0)
        while ts < end:
            yield ts
            ts += timedelta(hours=3)

    def _kp_observed(self) -> bytes:
        # list-of-objects shape
        rows = [
            {"time_tag": f"{b:%Y-%m-%dT%H:%M:%S}", "Kp": demo_kp(b, self.now), "a_running": 7, "station_count": 8}
            for b in self._blocks(self.now - timedelta(days=7), self.now - timedelta(hours=3))
        ]
        return json.dumps(rows).encode()

    def _kp_forecast(self) -> bytes:
        # header-row shape
        today = self.now.replace(hour=0, minute=0, second=0, microsecond=0)
        rows = [["time_tag", "kp", "observed", "noaa_scale"]]
        for b in self._blocks(today - timedelta(days=7), today + timedelta(days=3)):
            status = "observed" if b + timedelta(hours=3) <= today else ("estimated" if b <= self.now else "predicted")
            kp = demo_kp(b, self.now)
            scale = "G2" if kp >= 6 else ("G1" if kp >= 5 else None)
            rows.append([f"{b:%Y-%m-%d %H:%M:%S}", f"{kp:.2f}", status, scale])
        return json.dumps(rows).encode()

    def _solar_wind(self, kind: str) -> bytes:
        # RTSW key-value format: one row per spacecraft per minute, numeric values,
        # with the backup spacecraft flagged inactive.
        start = self.now - timedelta(hours=24)
        peak = storm_peak(self.now)
        rows = []
        ts = start.replace(second=0, microsecond=0)
        while ts <= self.now:
            hrs_to_peak = (peak - ts).total_seconds() / 3600.0
            arriving = math.exp(-(((hrs_to_peak - 2) / 4.0) ** 2))
            for source, active in (("DSCOVR", True), ("ACE", False)):
                tag = f"{ts:%Y-%m-%dT%H:%M:%S}"
                if kind == "mag":
                    bz = round(1.5 - 8.0 * arriving + 2 * (_u("bz", ts) - 0.5), 2) if active else 99.0
                    rows.append(
                        {
                            "time_tag": tag,
                            "active": active,
                            "source": source,
                            "bx_gsm": 1.1,
                            "by_gsm": -2.0,
                            "bz_gsm": bz,
                            "bt": round(abs(bz) + 3, 2),
                            "phi_gsm": 120.0,
                            "theta_gsm": -30.0,
                        }
                    )
                else:
                    speed = round(410 + 150 * arriving + 15 * (_u("v", ts) - 0.5), 1) if active else 9999.0
                    rows.append(
                        {
                            "time_tag": tag,
                            "active": active,
                            "source": source,
                            "proton_speed": speed,
                            "proton_density": 6.1,
                            "proton_temperature": 150000.0,
                        }
                    )
            ts += timedelta(minutes=1)
        return json.dumps(rows).encode()

    # --- Open-Meteo ------------------------------------------------------
    def _openmeteo(self, params: dict) -> bytes:
        lats = [float(x) for x in params["latitude"].split(",")]
        lons = [float(x) for x in params["longitude"].split(",")]
        first = self.now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=int(params["past_hours"]))
        hours = [first + timedelta(hours=i) for i in range(int(params["past_hours"]) + int(params["forecast_hours"]))]
        out = []
        for idx, (lat, lon) in enumerate(zip(lats, lons, strict=True)):
            cc = [cloud_cover(lat, lon, t) for t in hours]
            out.append(
                {
                    "latitude": round(lat, 2),  # the real API snaps to its model grid
                    "longitude": round(lon, 2),
                    "location_id": idx,
                    "generationtime_ms": 0.5,
                    "utc_offset_seconds": 0,
                    "timezone": "GMT",
                    "hourly_units": {"time": "iso8601", "cloud_cover": "%", "cloud_cover_low": "%"},
                    "hourly": {
                        "time": [f"{t:%Y-%m-%dT%H:%M}" for t in hours],
                        "cloud_cover": [c[0] for c in cc],
                        "cloud_cover_low": [c[1] for c in cc],
                    },
                }
            )
        return json.dumps(out if len(out) > 1 else out[0]).encode()
