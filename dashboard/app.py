"""Finland Weather & Aurora Grid: Streamlit dashboard.

Reads the Parquet files that the scheduled pipeline publishes to the repo's
`data` branch. If those can't be fetched (first deploy, offline), it falls back
to the bundled demo snapshot and says so at the top of the page.
"""

from __future__ import annotations

import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import requests
import streamlit as st

TZ = "Europe/Helsinki"
DEMO_DIR = Path(__file__).parent / "demo_data"
DEFAULT_DATA_URL = "https://raw.githubusercontent.com/munyingi/finland-weather-aurora/data"
TABLES = [
    "aurora_cells",
    "aurora_tonight",
    "aurora_spots_hourly",
    "space_weather_hourly",
    "weather_cells",
    "region_daily",
    "weather_events",
    "stations",
    "pipeline_health",
]

st.set_page_config(page_title="Finland Weather & Aurora Grid", page_icon="🌌", layout="wide")


def _data_url() -> str:
    try:
        return st.secrets.get("DATA_URL", os.getenv("DATA_URL", DEFAULT_DATA_URL))
    except Exception:  # no secrets file locally
        return os.getenv("DATA_URL", DEFAULT_DATA_URL)


@st.cache_data(ttl=900, show_spinner="Loading the latest pipeline output...")
def load_data() -> tuple[dict[str, pd.DataFrame], dict, str]:
    base = _data_url().rstrip("/")
    try:
        manifest = requests.get(f"{base}/manifest.json", timeout=15).json()
        frames = {}
        for name in TABLES:
            resp = requests.get(f"{base}/{name}.parquet", timeout=30)
            resp.raise_for_status()
            frames[name] = pd.read_parquet(io.BytesIO(resp.content))
        return frames, manifest, "live"
    except Exception:
        manifest = json.loads((DEMO_DIR / "manifest.json").read_text())
        frames = {name: pd.read_parquet(DEMO_DIR / f"{name}.parquet") for name in TABLES}
        return frames, manifest, "bundled demo"


def to_local(series: pd.Series) -> pd.Series:
    s = pd.to_datetime(series)
    if s.dt.tz is None:
        s = s.dt.tz_localize("UTC")
    return s.dt.tz_convert(TZ)


def ramp(value: float, stops: list[tuple[float, tuple[int, int, int, int]]]) -> list[int]:
    """Piecewise-linear colour ramp."""
    if pd.isna(value):
        return [80, 80, 80, 40]
    if value <= stops[0][0]:
        return list(stops[0][1])
    for (v0, c0), (v1, c1) in zip(stops, stops[1:], strict=False):
        if value <= v1:
            t = (value - v0) / (v1 - v0)
            return [round(a + (b - a) * t) for a, b in zip(c0, c1, strict=True)]
    return list(stops[-1][1])


AURORA_STOPS = [
    (0, (15, 25, 55, 25)),
    (15, (30, 90, 130, 120)),
    (35, (20, 170, 140, 170)),
    (60, (60, 235, 120, 210)),
    (100, (190, 255, 120, 235)),
]
MEASURES = {
    "air_temperature_c": (
        "Temperature",
        "°C",
        [
            (-30, (49, 54, 149, 200)),
            (-10, (116, 173, 209, 200)),
            (0, (240, 240, 240, 200)),
            (10, (244, 109, 67, 200)),
            (25, (165, 0, 38, 210)),
        ],
    ),
    "wind_gust_ms": (
        "Wind gust",
        "m/s",
        [(0, (240, 249, 232, 150)), (10, (123, 204, 196, 190)), (20, (43, 140, 190, 210)), (30, (8, 64, 129, 230))],
    ),
    "wind_speed_ms": (
        "Wind speed",
        "m/s",
        [(0, (240, 249, 232, 150)), (6, (123, 204, 196, 190)), (14, (43, 140, 190, 210)), (21, (8, 64, 129, 230))],
    ),
    "precipitation_mm": (
        "Precipitation (1 h)",
        "mm",
        [(0, (250, 250, 250, 40)), (0.5, (158, 202, 225, 170)), (3, (49, 130, 189, 210)), (10, (8, 48, 107, 235))],
    ),
    "snow_depth_cm": (
        "Snow depth",
        "cm",
        [(0, (120, 100, 80, 60)), (5, (210, 225, 240, 170)), (40, (150, 180, 230, 200)), (100, (70, 90, 200, 230))],
    ),
    "pressure_hpa": (
        "Pressure (sea level)",
        "hPa",
        [(975, (118, 42, 131, 200)), (1000, (240, 240, 240, 180)), (1030, (27, 120, 55, 200))],
    ),
}
VIEW = pdk.ViewState(latitude=64.8, longitude=25.8, zoom=4.1, pitch=0)


def hex_map(df: pd.DataFrame, tooltip_html: str, dark: bool) -> pdk.Deck:
    layer = pdk.Layer(
        "H3HexagonLayer",
        df,
        get_hexagon="cell_id",
        get_fill_color="color",
        get_line_color=[255, 255, 255, 25],
        line_width_min_pixels=0.3,
        pickable=True,
        stroked=True,
        filled=True,
        extruded=False,
    )
    return pdk.Deck(
        layers=[layer],
        initial_view_state=VIEW,
        map_style=pdk.map_styles.CARTO_DARK if dark else pdk.map_styles.CARTO_LIGHT,
        tooltip={"html": tooltip_html, "style": {"fontSize": "12px"}},
    )


frames, manifest, source = load_data()
generated = pd.Timestamp(manifest["generated_at_utc"]).tz_localize("UTC").tz_convert(TZ)

st.title("Finland Weather & Aurora Grid")
st.caption(
    "Hourly FMI station weather interpolated onto an H3 hexagon grid, plus an aurora visibility score "
    "from NOAA space weather, solar position and cloud forecasts. "
    f"Data generated **{generated:%a %d %b %H:%M}** Helsinki time."
)
if source != "live" or manifest.get("mode") == "demo":
    st.warning(
        "Showing the bundled **demo snapshot** (synthetic data in the real API formats). "
        "The live feed appears once the scheduled pipeline has published to the `data` branch.",
        icon="🧪",
    )

tab_aurora, tab_weather, tab_regions, tab_events, tab_health, tab_about = st.tabs(
    ["🌌 Aurora", "🌡️ Weather", "📊 Regions", "⚠️ Extreme weather", "🩺 Pipeline health", "ℹ️ About"]
)

# --------------------------------------------------------------------------- aurora
with tab_aurora:
    aur = frames["aurora_cells"].copy()
    aur["local"] = to_local(aur["valid_at"])
    tonight = frames["aurora_tonight"].sort_values("spot_rank")

    now_local = pd.Timestamp(datetime.now(UTC)).tz_convert(TZ).floor("h")
    hours = sorted(aur["local"].unique())
    future = [h for h in hours if h >= now_local] or hours
    # Default to the darkest, most promising hour in the next 18 hours
    window = aur[aur["local"].isin(future[:18])]
    best_hour = window.groupby("local")["aurora_score"].mean().idxmax() if not window.empty else hours[-1]

    left, right = st.columns([3, 2], gap="large")
    with left:
        hour = st.select_slider(
            "Hour (Helsinki time)",
            options=hours,
            value=best_hour,
            format_func=lambda t: pd.Timestamp(t).strftime("%a %H:%M"),
        )
        snap = aur[aur["local"] == hour].copy()
        snap["color"] = snap["aurora_score"].apply(lambda v: ramp(v, AURORA_STOPS))
        snap["kp_txt"] = snap["kp"].round(1).astype(str)
        st.pydeck_chart(
            hex_map(
                snap,
                "<b>{region_name}</b><br/>Aurora score <b>{aurora_score}</b> ({aurora_category})"
                "<br/>Kp {kp_txt} · cloud {cloud_cover_pct}%<br/>Sun altitude {sun_altitude_deg}°",
                dark=True,
            ),
            height=620,
        )
        st.caption("Brighter green = better odds. Score = geomagnetic chance × darkness × clear sky (0 to 100).")

    with right:
        k = snap.iloc[0] if not snap.empty else None
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Kp at this hour",
            f"{k['kp']:.1f}" if k is not None and pd.notna(k["kp"]) else "n/a",
            help="Planetary K-index, 0 (quiet) to 9 (extreme storm)",
        )
        c2.metric("Best spot tonight", tonight.iloc[0]["spot_name"] if not tonight.empty else "n/a")
        c3.metric("Cells 'good' or better", int((snap["aurora_score"] >= 35).sum()))

        st.subheader("Where to go tonight")
        show = tonight[
            [
                "spot_rank",
                "spot_name",
                "region_name",
                "best_score",
                "best_hour_local",
                "kp_at_best",
                "cloud_cover_at_best_pct",
                "outlook",
            ]
        ].copy()
        show["best_hour_local"] = pd.to_datetime(show["best_hour_local"]).dt.strftime("%a %H:%M")
        st.dataframe(
            show.rename(
                columns={
                    "spot_rank": "#",
                    "spot_name": "Spot",
                    "region_name": "Region",
                    "best_score": "Score",
                    "best_hour_local": "Best hour",
                    "kp_at_best": "Kp",
                    "cloud_cover_at_best_pct": "Cloud %",
                    "outlook": "Outlook",
                }
            ),
            hide_index=True,
            height=430,
            column_config={"Score": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d")},
        )

    sw = frames["space_weather_hourly"].copy()
    sw["local"] = to_local(sw["hour_at"])
    sw = sw[sw["local"] >= now_local - pd.Timedelta(days=2)]
    kp_chart = (
        alt.Chart(sw)
        .mark_bar()
        .encode(
            x=alt.X("local:T", title=None),
            y=alt.Y("kp:Q", title="Kp", scale=alt.Scale(domain=[0, 9])),
            color=alt.Color(
                "kp_status:N",
                title="Kp source",
                scale=alt.Scale(domain=["observed", "estimated", "predicted"], range=["#4c78a8", "#72b7b2", "#c7c7c7"]),
            ),
            tooltip=[
                alt.Tooltip("local:T", format="%a %H:%M"),
                "kp:Q",
                "kp_status:N",
                alt.Tooltip("bz_mean_nt:Q", title="Bz (nT)", format=".1f"),
            ],
        )
        .properties(height=180, title="Geomagnetic activity: last 2 days and NOAA 3-day forecast")
    )
    rule = alt.Chart(pd.DataFrame({"t": [now_local]})).mark_rule(color="orange").encode(x="t:T")
    st.altair_chart(kp_chart + rule, width="stretch")

    spots = frames["aurora_spots_hourly"].copy()
    spots["local"] = to_local(spots["valid_at"])
    pick = st.multiselect(
        "Compare spots",
        tonight["spot_name"].tolist(),
        default=tonight["spot_name"].head(1).tolist() + tonight["spot_name"].tail(1).tolist(),
    )
    if pick:
        st.altair_chart(
            alt.Chart(spots[spots["spot_name"].isin(pick)])
            .mark_line(point=True)
            .encode(
                x=alt.X("local:T", title=None),
                y=alt.Y("aurora_score:Q", title="Score", scale=alt.Scale(domain=[0, 100])),
                color="spot_name:N",
                tooltip=["spot_name", alt.Tooltip("local:T", format="%a %H:%M"), "aurora_score", "cloud_cover_pct", "kp"],
            )
            .properties(height=240),
            width="stretch",
        )
    with st.expander("How the aurora score works"):
        st.markdown(
            """
- **Geomagnetic chance**: the southern edge of the auroral oval moves south as Kp rises.
  Each hexagon's *geomagnetic* latitude (dipole model) is compared with that edge, minus a
  couple of degrees because aurora is visible low on the northern horizon. Southward
  solar-wind Bz and fast wind nudge the effective Kp up.
- **Darkness**: zero while the sun is above -6° (civil twilight), full from -12° (nautical).
- **Clear sky**: 1 minus Open-Meteo cloud cover.

It is a transparent rule of thumb built for this portfolio project, not an official forecast.
For the real thing, see FMI's Revontulet ja avaruussää service.
"""
        )

# --------------------------------------------------------------------------- weather
with tab_weather:
    wx = frames["weather_cells"].copy()
    wx["local"] = to_local(wx["observed_at"])
    c1, c2 = st.columns([1, 3])
    with c1:
        measure = st.radio("Measure", list(MEASURES), format_func=lambda m: MEASURES[m][0])
        whours = sorted(wx["local"].unique())
        wh = st.select_slider(
            "Hour", options=whours, value=whours[-1], format_func=lambda t: pd.Timestamp(t).strftime("%a %H:%M"), key="wx_hour"
        )
        snap = wx[wx["local"] == wh].copy()
        label, unit, stops = MEASURES[measure]
        vals = snap[measure].dropna()
        if not vals.empty:
            st.metric(f"Min {label.lower()}", f"{vals.min():.1f} {unit}")
            st.metric(f"Max {label.lower()}", f"{vals.max():.1f} {unit}")
        st.caption(
            f"{len(frames['stations'])} stations → {snap['cell_id'].nunique()} hexagons (~250 km² each), inverse-distance weighted."
        )
    with c2:
        snap["color"] = snap[measure].apply(lambda v: ramp(v, stops))
        snap["val"] = snap[measure].round(1).astype(str)
        st.pydeck_chart(
            hex_map(
                snap,
                f"<b>{{region_name}}</b><br/>{label}: <b>{{val}} {unit}</b><br/>Nearest station {{nearest_station_km}} km",
                dark=False,
            ),
            height=640,
        )

# --------------------------------------------------------------------------- regions
with tab_regions:
    rd = frames["region_daily"].copy()
    rd["local_date"] = pd.to_datetime(rd["local_date"])
    metric = st.selectbox(
        "Metric",
        [
            "air_temperature_mean_c",
            "air_temperature_min_c",
            "air_temperature_max_c",
            "wind_gust_max_ms",
            "precipitation_mean_mm",
            "snow_depth_mean_cm",
        ],
    )
    st.altair_chart(
        alt.Chart(rd)
        .mark_line(point=True)
        .encode(
            x=alt.X("local_date:T", title=None),
            y=alt.Y(f"{metric}:Q", title=metric.replace("_", " ")),
            color=alt.Color("region_name:N", legend=alt.Legend(columns=2)),
            tooltip=["region_name", "local_date:T", metric],
        )
        .properties(height=380),
        width="stretch",
    )
    latest = rd[rd["local_date"] == rd["local_date"].max()].sort_values("air_temperature_mean_c")
    st.dataframe(latest.drop(columns=["region_code"]), hide_index=True, width="stretch")

# --------------------------------------------------------------------------- events
with tab_events:
    ev = frames["weather_events"].copy()
    if ev.empty:
        st.info("No extreme weather in the last 30 days.")
    else:
        counts = ev.groupby(["event_type", "severity"]).size().reset_index(name="station_days")
        st.altair_chart(
            alt.Chart(counts)
            .mark_bar()
            .encode(
                x=alt.X("station_days:Q", title="Station-days"),
                y=alt.Y("event_type:N", sort="-x", title=None),
                color=alt.Color(
                    "severity:N", scale=alt.Scale(domain=["low", "medium", "high"], range=["#9ecae1", "#fd8d3c", "#d62728"])
                ),
            )
            .properties(height=220),
            width="stretch",
        )
        ev["color"] = ev["severity"].map({"low": [158, 202, 225, 180], "medium": [253, 141, 60, 200], "high": [214, 39, 40, 220]})
        kind = st.multiselect("Event types", sorted(ev["event_type"].unique()), default=sorted(ev["event_type"].unique()))
        sel = ev[ev["event_type"].isin(kind)]
        st.pydeck_chart(
            pdk.Deck(
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        sel,
                        get_position=["lon", "lat"],
                        get_fill_color="color",
                        get_radius=9000,
                        pickable=True,
                    )
                ],
                initial_view_state=VIEW,
                map_style=pdk.map_styles.CARTO_LIGHT,
                tooltip={"html": "<b>{station_name}</b><br/>{local_date}: {event_type}<br/>{metric} = {metric_value}"},
            ),
            height=480,
        )
        st.dataframe(sel.drop(columns=["color", "event_id", "station_key", "lat", "lon"]), hide_index=True, width="stretch")

# --------------------------------------------------------------------------- health
with tab_health:
    h = frames["pipeline_health"].copy()
    status_icon = {"healthy": "🟢", "degraded": "🟠", "stale": "🔴", "never_loaded": "⚪"}
    h.insert(0, "", h["status"].map(status_icon))
    cols = st.columns(len(h))
    for col, (_, row) in zip(cols, h.iterrows(), strict=True):
        col.metric(row["source"], row["status"], help=f"Rows in warehouse: {row['total_rows']:,}")
    st.dataframe(h, hide_index=True, width="stretch")
    st.json(manifest)
    st.caption(f"Data source: {source} ({_data_url() if source == 'live' else 'dashboard/demo_data'})")

# --------------------------------------------------------------------------- about
with tab_about:
    left, right = st.columns([3, 2], gap="large")
    with left:
        st.header("About this project")
        st.markdown(
            """
A geospatial data engineering portfolio project covering **all of Finland**, from Hanko to Utsjoki and Åland.

**What it answers**
- What is the weather right now, everywhere in Finland, not only where a station stands?
- Which regions had frost, storms, heavy rain or snow in the last 30 days?
- **Where should I go tonight to see the northern lights**, and at what time?

**How it works**
1. **Ingest (Python).** Every 3 hours GitHub Actions pulls hourly observations from about 190 FMI weather
   stations, the NOAA Kp index and real-time solar wind, and an Open-Meteo cloud forecast for every aurora cell.
   Loads are idempotent and incremental, and one failing source never stops the others.
2. **Model (dbt on DuckDB).** Stations are interpolated onto ~1,770 H3 hexagons with inverse distance
   weighting, rolled up to the 19 regions, and checked against extreme-weather rules. Station metadata
   is kept as SCD Type 2 history.
3. **Score the aurora.** Each hexagon gets a 0 to 100 score per hour:
   geomagnetic chance (Kp, solar wind, geomagnetic latitude) × darkness (sun position) × clear sky (cloud cover).
4. **Serve.** Small Parquet files are published to a `data` branch and read by this Streamlit app.

**Quality built in:** 47 dbt data tests, 2 dbt unit tests, source freshness checks, 17 pytest tests,
an offline demo mode that runs the full pipeline in CI, and the Pipeline health tab.
"""
        )
    with right:
        st.subheader("Stack")
        st.markdown(
            """
| Layer | Tools |
|---|---|
| Ingestion | Python, requests, H3, Shapely |
| Warehouse | DuckDB |
| Transformation | dbt (incremental, snapshots, unit tests) |
| Orchestration | GitHub Actions (every 3 h) |
| Serving | Parquet, Streamlit, pydeck, Altair |
"""
        )
        st.subheader("Data sources")
        st.markdown(
            """
- [Finnish Meteorological Institute open data](https://en.ilmatieteenlaitos.fi/open-data) (CC BY 4.0)
- [NOAA Space Weather Prediction Center](https://www.swpc.noaa.gov/)
- [Open-Meteo](https://open-meteo.com/) (CC BY 4.0)
- [Natural Earth](https://www.naturalearthdata.com/) region boundaries
"""
        )
        st.subheader("Author")
        st.markdown(
            """
**Samwel Munyingi**, Helsinki, Finland.

[GitHub](https://github.com/munyingi) · [LinkedIn](https://linkedin.com/in/samwel-munyingi-352a88161) ·
[Source code](https://github.com/munyingi/finland-weather-aurora)
"""
        )
        st.info(
            "The aurora score is a transparent rule of thumb for this project, not an official forecast. "
            "For alerts, use FMI's Revontulet ja avaruussää service.",
            icon="ℹ️",
        )

st.divider()
st.caption(
    "Data: Finnish Meteorological Institute open data (CC BY 4.0) · NOAA SWPC · Open-Meteo (CC BY 4.0) · "
    "Natural Earth (public domain) · H3 by Uber. Built by Samwel Munyingi · "
    "[GitHub](https://github.com/munyingi/finland-weather-aurora)"
)
