"""Streamlit weather dashboard — reads from data/weather.db (DuckDB, read-only).

Sections:
  0. Weather Map              — PyDeck; colour=temp, opacity=population (no overlap)
  1. Current Conditions       — per-city cards (temp, humidity, wind, clouds)
  2. Regional Snapshot        — aggregate KPIs with hour-over-hour deltas
  3. Temperature Tracking     — temp + feels-like dual lines, up to 3 cities + City Advisor
  4. Conditions Distribution  — horizontal bar of condition_main counts
  5. City Comparison          — box plot of temp range per city
  6. Hourly Detail            — expandable raw table

Sidebar: state + city multi-select, 24h time slider (ET), ▶ Play / ⏹ Stop, Refresh.
Run locally:  streamlit run app/dashboard.py
"""

from __future__ import annotations

import datetime
import math
import os
import subprocess
import sys
import time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_PATH = Path(os.getenv("DUCKDB_PATH", "data/weather.db"))
S3_SYNC_SCRIPT = Path(os.getenv("S3_SYNC_SCRIPT", "scripts/s3_to_duckdb.py"))
_ET = ZoneInfo("America/New_York")
_ENV = os.getenv("ENVIRONMENT", "local")
_S3_PROCESSED = os.getenv("S3_PROCESSED_BUCKET", "weatherdata-processed-local")
_AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# Absolute temperature colour anchors  [temp_f, [R, G, B]]  (alpha set per-city)
_TEMP_ANCHORS = [
    (10,  [0,   0,   180]),
    (30,  [30,  100, 255]),
    (50,  [100, 220, 200]),
    (70,  [255, 220,  50]),
    (90,  [200,  30,   0]),
]

# 2020 census populations for the 19 tri-state cities
CITY_POPULATIONS = {
    "New York City": 8_336_817,
    "Buffalo":         278_349,
    "Rochester":       211_328,
    "Yonkers":         211_569,
    "Syracuse":        148_620,
    "Albany":           99_224,
    "White Plains":     58_109,
    "Newark":          311_549,
    "Jersey City":     292_449,
    "Paterson":        159_732,
    "Elizabeth":       137_298,
    "Edison":          107_588,
    "Trenton":          90_871,
    "Bridgeport":      148_654,
    "New Haven":       130_250,
    "Stamford":        135_470,
    "Hartford":        121_054,
    "Waterbury":       114_403,
    "Norwalk":          91_184,
}
_LOG_POP_MIN = math.log10(58_109)      # White Plains
_LOG_POP_MAX = math.log10(8_336_817)   # NYC
_RADIUS_BASE  = 3_500   # metres — base for all cities
_RADIUS_BOOST = 2_000   # additional metres at max population

CONDITION_ICONS = {
    "Clear": "☀️", "Clouds": "☁️", "Rain": "🌧️", "Drizzle": "🌦️",
    "Thunderstorm": "⛈️", "Snow": "❄️", "Mist": "🌫️", "Fog": "🌫️", "Haze": "🌫️",
}

# ---------------------------------------------------------------------------
# Page config — must be first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Tri-State Weather Dashboard",
    page_icon="🌤️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_et(ts):
    return ts.tz_localize("UTC").tz_convert(_ET)


def _temp_rgb(temp_f: float) -> list[int]:
    """Return [R, G, B] using absolute anchor interpolation."""
    anchors = _TEMP_ANCHORS
    if temp_f <= anchors[0][0]:
        return anchors[0][1]
    if temp_f >= anchors[-1][0]:
        return anchors[-1][1]
    for i in range(len(anchors) - 1):
        t0, c0 = anchors[i]
        t1, c1 = anchors[i + 1]
        if t0 <= temp_f <= t1:
            frac = (temp_f - t0) / (t1 - t0)
            return [int(c0[j] + frac * (c1[j] - c0[j])) for j in range(3)]
    return anchors[-1][1]


def _pop_t(city_name: str) -> float:
    pop = CITY_POPULATIONS.get(city_name, 100_000)
    t = (math.log10(pop) - _LOG_POP_MIN) / (_LOG_POP_MAX - _LOG_POP_MIN)
    return max(0.0, min(1.0, t))


def _pop_radius(city_name: str) -> int:
    return int(_RADIUS_BASE + _pop_t(city_name) * _RADIUS_BOOST)   # 3500–5500 m


def _pop_alpha(city_name: str) -> int:
    return int(140 + _pop_t(city_name) * 100)   # 140–240


CITY_ACTIVITIES: dict[str, list[dict]] = {
    "New York City": [
        {"name": "Central Park",               "outdoor": True,  "months": [4,5,6,7,8,9,10],       "tip": "stroll, bike, or picnic"},
        {"name": "Broadway show",              "outdoor": False, "months": list(range(1,13)),        "tip": "world-class theater any night"},
        {"name": "MoMA or The Met",            "outdoor": False, "months": list(range(1,13)),        "tip": "world-class art collections"},
        {"name": "Brooklyn Bridge walk",       "outdoor": True,  "months": [3,4,5,6,7,8,9,10,11],  "tip": "iconic skyline views"},
        {"name": "Staten Island Ferry",        "outdoor": True,  "months": list(range(1,13)),        "tip": "free Statue of Liberty views"},
        {"name": "ice skating at Bryant Park", "outdoor": True,  "months": [12,1,2],                "tip": "free admission rink"},
    ],
    "Buffalo": [
        {"name": "Niagara Falls",              "outdoor": True,  "months": [5,6,7,8,9,10],          "tip": "one of the great natural wonders"},
        {"name": "Canalside waterfront",       "outdoor": True,  "months": [5,6,7,8,9],             "tip": "concerts, kayaking, and food"},
        {"name": "Albright-Knox Art Gallery",  "outdoor": False, "months": list(range(1,13)),        "tip": "world-class modern art"},
        {"name": "Delaware Park",              "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "Olmsted-designed park great for walks"},
        {"name": "Buffalo wing trail",         "outdoor": False, "months": list(range(1,13)),        "tip": "where it all started — Anchor Bar and beyond"},
    ],
    "Rochester": [
        {"name": "George Eastman Museum",      "outdoor": False, "months": list(range(1,13)),        "tip": "photography and cinema history"},
        {"name": "Lilac Festival at Highland Park", "outdoor": True, "months": [5],                 "tip": "world's largest lilac collection blooms in May"},
        {"name": "High Falls gorge",           "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "scenic urban waterfall"},
        {"name": "Strong National Museum of Play", "outdoor": False, "months": list(range(1,13)),   "tip": "fun for all ages"},
    ],
    "Albany": [
        {"name": "New York State Capitol tour","outdoor": False, "months": list(range(1,13)),        "tip": "stunning Romanesque architecture"},
        {"name": "Hudson River cruise",        "outdoor": True,  "months": [5,6,7,8,9,10],          "tip": "scenic river views heading south"},
        {"name": "Washington Park",            "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "tulip festival in May"},
        {"name": "Albany Institute of History & Art", "outdoor": False, "months": list(range(1,13)),"tip": "Hudson River School paintings"},
    ],
    "Yonkers": [
        {"name": "Untermyer Park & Gardens",   "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "stunning Hudson River overlooks and formal gardens"},
        {"name": "Hudson River Museum",        "outdoor": False, "months": list(range(1,13)),        "tip": "art and science on the riverfront"},
        {"name": "Yonkers waterfront",         "outdoor": True,  "months": [4,5,6,7,8,9],           "tip": "revitalized pier with great NYC skyline views"},
    ],
    "Syracuse": [
        {"name": "Erie Canal Museum",          "outdoor": False, "months": list(range(1,13)),        "tip": "history of the canal that built New York"},
        {"name": "Onondaga Lake Park trail",   "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "waterfront walking and biking"},
        {"name": "Destiny USA",                "outdoor": False, "months": list(range(1,13)),        "tip": "one of the largest malls in the US"},
        {"name": "New York State Fair",        "outdoor": True,  "months": [8],                     "tip": "massive annual fair in late August"},
    ],
    "White Plains": [
        {"name": "Kensico Dam Plaza",          "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "concerts, food trucks, and open lawns"},
        {"name": "Westchester County Center",  "outdoor": False, "months": list(range(1,13)),        "tip": "events, shows, and exhibitions year-round"},
        {"name": "The Westchester mall",       "outdoor": False, "months": list(range(1,13)),        "tip": "premium shopping close to the city"},
    ],
    "Newark": [
        {"name": "Newark Museum of Art",       "outdoor": False, "months": list(range(1,13)),        "tip": "NJ's largest museum — free on Sundays"},
        {"name": "Branch Brook Park cherry blossoms", "outdoor": True, "months": [4],               "tip": "more cherry trees than Washington D.C."},
        {"name": "Prudential Center events",   "outdoor": False, "months": list(range(1,13)),        "tip": "Devils hockey, concerts, and shows"},
        {"name": "Ironbound district dining",  "outdoor": False, "months": list(range(1,13)),        "tip": "Portuguese and Spanish restaurants renowned across the region"},
    ],
    "Jersey City": [
        {"name": "Liberty State Park",         "outdoor": True,  "months": list(range(1,13)),        "tip": "best view of the Statue of Liberty and NYC skyline"},
        {"name": "Liberty Science Center",     "outdoor": False, "months": list(range(1,13)),        "tip": "hands-on science museum great for all ages"},
        {"name": "Mana Contemporary",          "outdoor": False, "months": list(range(1,13)),        "tip": "massive contemporary art complex"},
        {"name": "Grove Street food scene",    "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "vibrant outdoor dining and cafes"},
    ],
    "Paterson": [
        {"name": "Great Falls National Historical Park", "outdoor": True, "months": list(range(1,13)), "tip": "one of the largest waterfalls in the US — stunning year-round"},
        {"name": "Paterson Museum",            "outdoor": False, "months": list(range(1,13)),        "tip": "industrial and cultural history of the Silk City"},
        {"name": "Lambert Castle",             "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "historic castle with Passaic Valley views"},
    ],
    "Elizabeth": [
        {"name": "Warinanco Park",             "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "boating, skating, and open green space"},
        {"name": "Staten Island Ferry gateway","outdoor": False, "months": list(range(1,13)),        "tip": "easy access to NYC via ferry"},
        {"name": "Jersey Gardens outlet mall", "outdoor": False, "months": list(range(1,13)),        "tip": "NJ's largest outlet mall — tax-free shopping"},
    ],
    "Trenton": [
        {"name": "New Jersey State Capitol",   "outdoor": False, "months": list(range(1,13)),        "tip": "free tours of the historic capitol building"},
        {"name": "Grounds for Sculpture",      "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "42-acre sculpture park — one of NJ's gems"},
        {"name": "Trenton Battle Monument",    "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "key Revolutionary War site on the Delaware"},
    ],
    "Edison": [
        {"name": "Thomas Edison Center at Menlo Park", "outdoor": False, "months": list(range(1,13)), "tip": "where the phonograph and lightbulb were invented"},
        {"name": "Johnson Park",               "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "riverside park with picnic areas and trails"},
        {"name": "Edison's diverse food scene","outdoor": False, "months": list(range(1,13)),        "tip": "acclaimed Indian and Korean restaurants along Oak Tree Rd"},
    ],
    "Bridgeport": [
        {"name": "Beardsley Zoo",              "outdoor": True,  "months": list(range(1,13)),        "tip": "Connecticut's only zoo — open year-round"},
        {"name": "Seaside Park",               "outdoor": True,  "months": [5,6,7,8,9],             "tip": "Olmsted-designed beach park on Long Island Sound"},
        {"name": "Discovery Museum & Planetarium", "outdoor": False, "months": list(range(1,13)),   "tip": "hands-on science exhibits and stargazing shows"},
    ],
    "New Haven": [
        {"name": "Yale University Art Gallery","outdoor": False, "months": list(range(1,13)),        "tip": "free world-class art museum open to the public"},
        {"name": "Peabody Museum of Natural History", "outdoor": False, "months": list(range(1,13)),"tip": "legendary dinosaur hall and natural history collections"},
        {"name": "Frank Pepe's or Sally's Apizza", "outdoor": False, "months": list(range(1,13)),   "tip": "legendary New Haven coal-fired pizza — a pilgrimage for food lovers"},
        {"name": "East Rock Park",             "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "stunning panoramic views from the traprock ridge"},
        {"name": "Long Island Sound beaches",  "outdoor": True,  "months": [6,7,8],                 "tip": "Lighthouse Point and Savin Rock in summer"},
    ],
    "Stamford": [
        {"name": "Stamford Museum & Nature Center", "outdoor": True, "months": list(range(1,13)),   "tip": "farm animals, trails, and observatory on 118 acres"},
        {"name": "Cove Island Park",           "outdoor": True,  "months": [5,6,7,8,9],             "tip": "beach, kayaking, and bird watching on the Sound"},
        {"name": "Downtown SoNo arts & dining","outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "vibrant restaurant and gallery scene"},
    ],
    "Hartford": [
        {"name": "Mark Twain House & Museum",  "outdoor": False, "months": list(range(1,13)),        "tip": "tour the Victorian home where Twain wrote his greatest works"},
        {"name": "Wadsworth Atheneum",         "outdoor": False, "months": list(range(1,13)),        "tip": "oldest public art museum in the US"},
        {"name": "Bushnell Park",              "outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "America's oldest publicly funded park — free carousel"},
        {"name": "Hartford Yard Goats game",   "outdoor": True,  "months": [4,5,6,7,8,9],           "tip": "Double-A baseball at Dunkin' Donuts Park"},
    ],
    "Waterbury": [
        {"name": "Mattatuck Museum",           "outdoor": False, "months": list(range(1,13)),        "tip": "Connecticut art and history spanning 300 years"},
        {"name": "Lake Quassapaug",            "outdoor": True,  "months": [6,7,8],                 "tip": "swimming, paddleboats, and Quassy Amusement Park"},
        {"name": "Imagine Nation museum",      "outdoor": False, "months": list(range(1,13)),        "tip": "interactive children's museum"},
    ],
    "Norwalk": [
        {"name": "Maritime Aquarium",          "outdoor": False, "months": list(range(1,13)),        "tip": "sharks, seals, and Long Island Sound marine life"},
        {"name": "Stepping Stones Museum",     "outdoor": False, "months": list(range(1,13)),        "tip": "award-winning children's museum"},
        {"name": "SoNo arts & dining district","outdoor": True,  "months": [4,5,6,7,8,9,10],        "tip": "galleries, restaurants, and rooftop bars"},
        {"name": "Oyster Festival",            "outdoor": True,  "months": [9],                     "tip": "huge annual September waterfront festival"},
    ],
}


def _city_advisor(city_name, temp_f, feels_like_f, wind_speed_mph, condition_main, humidity_pct) -> dict:
    """Return dict with keys: dress, travel, activities (list of str), season."""
    month = datetime.date.today().month

    season = {
        12: "winter", 1: "winter", 2: "winter",
        3: "spring",  4: "spring", 5: "spring",
        6: "summer",  7: "summer", 8: "summer",
        9: "fall",   10: "fall",  11: "fall",
    }[month]

    if feels_like_f < 20:
        dress = "Extreme cold — heavy parka, thermals, hat, gloves, and scarf essential."
    elif feels_like_f < 32:
        dress = "Heavy winter coat, warm hat, and gloves required."
    elif feels_like_f < 45:
        dress = "Warm jacket and layers recommended."
    elif feels_like_f < 60:
        dress = "Light-to-medium jacket advised."
    elif feels_like_f < 75:
        dress = "Comfortable light clothing — maybe a layer for the evening."
    else:
        dress = "Light, breathable clothing; stay hydrated in the heat."

    if condition_main == "Thunderstorm":
        travel = "Avoid outdoor travel — dangerous conditions."
    elif condition_main == "Snow":
        travel = "Allow extra travel time; watch for icy roads."
    elif condition_main in ("Rain", "Drizzle"):
        travel = "Bring an umbrella; good day for indoor plans."
    elif wind_speed_mph > 25:
        travel = "Very windy — secure loose items and expect delays."
    elif condition_main == "Clear" and feels_like_f > 60:
        travel = "Great day for outdoor activities or sightseeing."
    elif condition_main == "Clouds":
        travel = "Overcast but manageable — outdoor plans should hold."
    else:
        travel = "Conditions are reasonable — no special precautions needed."

    # 3-level severity: severe → indoor only (no fallback); poor → indoor preferred
    if condition_main in ("Thunderstorm", "Snow"):
        severity = "severe"
    elif (
        condition_main in ("Rain", "Drizzle")
        or wind_speed_mph > 25
        or (humidity_pct > 85 and feels_like_f > 78)
        or feels_like_f < 40
    ):
        severity = "poor"
    else:
        severity = "ok"

    all_acts = CITY_ACTIVITIES.get(city_name, [])
    seasonal = [a for a in all_acts if month in a["months"]]

    if severity == "ok":
        candidates = seasonal
    elif severity == "poor":
        candidates = [a for a in seasonal if not a["outdoor"]]
        if not candidates:
            candidates = seasonal  # fallback: no indoor options for this city
    else:  # severe — indoor only, no fallback
        candidates = [a for a in seasonal if not a["outdoor"]]

    # Context note explaining why indoor activities were chosen
    if severity == "severe":
        context_note = "⛔ Dangerous conditions — indoor only"
    elif severity == "poor":
        if condition_main in ("Rain", "Drizzle"):
            context_note = "🌂 Rainy — indoor options shown"
        elif wind_speed_mph > 25:
            context_note = "💨 Very windy — indoor options shown"
        elif humidity_pct > 85 and feels_like_f > 78:
            context_note = "🥵 Muggy — indoor options shown"
        else:
            context_note = "🧊 Cold — indoor options shown"
    else:
        context_note = None

    picks = candidates[:2] if candidates else []
    activities = [f"{a['name']} ({a['tip']})" for a in picks]

    return {"dress": dress, "travel": travel, "activities": activities,
            "season": season, "context_note": context_note}


# ---------------------------------------------------------------------------
# Data loading (cached)
# ---------------------------------------------------------------------------


def _s3_conn():
    """In-memory DuckDB connection with httpfs for reading S3 directly (prod).

    httpfs is pre-installed in the Docker image (Dockerfile RUN step) so we
    only LOAD it here — no network call needed at runtime.
    Uses boto3 to resolve credentials from the App Runner instance IAM role.
    """
    import duckdb
    import boto3
    conn = duckdb.connect()
    conn.execute("LOAD httpfs;")
    conn.execute(f"SET s3_region='{_AWS_REGION}';")
    session = boto3.Session()
    creds = session.get_credentials().get_frozen_credentials()
    conn.execute(f"SET s3_access_key_id='{creds.access_key}';")
    conn.execute(f"SET s3_secret_access_key='{creds.secret_key}';")
    if creds.token:
        conn.execute(f"SET s3_session_token='{creds.token}';")
    return conn


@st.cache_data(ttl=300)
def load_current():
    import duckdb
    if _ENV == "prod":
        conn = _s3_conn()
        df = conn.execute(f"""
            SELECT city AS city_name, state AS state_code, lat, lon,
                   temp_f, feels_like_f, humidity_pct, wind_speed_mph,
                   condition_main, condition_description, clouds_pct,
                   observed_at::TIMESTAMP AS observed_at
            FROM read_parquet(
                's3://{_S3_PROCESSED}/weather/**/*.parquet',
                hive_partitioning=true
            )
            QUALIFY ROW_NUMBER() OVER (PARTITION BY city ORDER BY observed_at::TIMESTAMP DESC) = 1
            ORDER BY city_name
        """).df()
        conn.close()
        return df
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    df = conn.execute("SELECT * FROM weather_current ORDER BY city_name").df()
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_hourly():
    import duckdb
    if _ENV == "prod":
        conn = _s3_conn()
        df = conn.execute(f"""
            SELECT city AS city_name, state AS state_code,
                   DATE_TRUNC('hour', observed_at::TIMESTAMP) AS observed_hour,
                   MIN(temp_f)        AS min_temp_f,
                   AVG(temp_f)        AS avg_temp_f,
                   MAX(temp_f)        AS max_temp_f,
                   AVG(feels_like_f)  AS avg_feels_like_f,
                   AVG(humidity_pct)  AS avg_humidity_pct,
                   AVG(pressure_hpa)  AS avg_pressure_hpa,
                   AVG(wind_speed_mph) AS avg_wind_speed_mph,
                   MAX(wind_gust_mph)  AS max_wind_gust_mph,
                   AVG(clouds_pct)    AS avg_clouds_pct,
                   MODE(condition_main) AS dominant_condition,
                   COUNT(*)           AS reading_count
            FROM read_parquet(
                's3://{_S3_PROCESSED}/weather/**/*.parquet',
                hive_partitioning=true
            )
            GROUP BY city_name, state_code, observed_hour
            ORDER BY city_name, observed_hour
        """).df()
        conn.close()
        return df
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    df = conn.execute(
        "SELECT * FROM weather_hourly_summary ORDER BY city_name, observed_hour"
    ).df()
    conn.close()
    return df


@st.cache_data(ttl=300)
def load_processed():
    import duckdb
    if _ENV == "prod":
        conn = _s3_conn()
        df = conn.execute(f"""
            SELECT city, state, lat, lon, temp_f, feels_like_f, humidity_pct,
                   wind_speed_mph, condition_main, condition_description,
                   clouds_pct, observed_at::TIMESTAMP AS observed_at
            FROM read_parquet(
                's3://{_S3_PROCESSED}/weather/**/*.parquet',
                hive_partitioning=true
            )
            ORDER BY city, observed_at::TIMESTAMP
        """).df()
        conn.close()
        return df
    conn = duckdb.connect(str(DB_PATH), read_only=True)
    df = conn.execute(
        "SELECT * FROM weather_processed ORDER BY city, observed_at"
    ).df()
    conn.close()
    return df


def db_exists() -> bool:
    if _ENV == "prod":
        return True  # prod reads from S3 directly — no local DB file needed
    return DB_PATH.exists() and DB_PATH.stat().st_size > 0


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------


def render_sidebar(df_current, hours):
    """Return (selected_cities, selected_hour_utc_naive)."""
    if "animating" not in st.session_state:
        st.session_state.animating = False
    if "anim_idx" not in st.session_state:
        st.session_state.anim_idx = 0

    with st.sidebar:
        st.title("Filters")

        state_filter = st.multiselect(
            "State", options=["NY", "NJ", "CT"], default=["NY", "NJ", "CT"]
        )
        candidates = sorted(
            df_current.loc[
                df_current["state_code"].isin(state_filter) if state_filter
                else df_current.index.notna(),
                "city_name",
            ].unique().tolist()
        )
        selected_cities = st.multiselect("Cities", options=candidates, default=candidates)

        st.divider()

        selected_hour = hours[-1] if hours else None
        if len(hours) > 1:
            hours_fmt = {
                _to_et(h).strftime("%b %d, %I:%M %p ET"): h for h in hours
            }
            if st.session_state.animating:
                anim_h = hours[st.session_state.anim_idx % len(hours)]
                anim_label = _to_et(anim_h).strftime("%b %d, %I:%M %p ET")
                st.select_slider(
                    "Map Hour (last 24h)", options=list(hours_fmt.keys()),
                    value=anim_label, disabled=True,
                )
                selected_hour = anim_h
            else:
                selected_label = st.select_slider(
                    "Map Hour (last 24h)", options=list(hours_fmt.keys()),
                    value=list(hours_fmt.keys())[-1],
                )
                selected_hour = hours_fmt[selected_label]

            st.caption("Brighter dot = larger city  |  🔵 cold → 🔴 warm")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("▶ Play", use_container_width=True,
                             disabled=st.session_state.animating):
                    st.session_state.animating = True
                    st.session_state.anim_idx = 0
                    st.rerun()
            with c2:
                if st.button("⏹ Stop", use_container_width=True,
                             disabled=not st.session_state.animating):
                    st.session_state.animating = False
                    st.rerun()

        st.divider()
        if st.button("Refresh Data", use_container_width=True, type="primary"):
            _run_refresh()

    return selected_cities, selected_hour


def _run_refresh() -> None:
    if not S3_SYNC_SCRIPT.exists():
        st.sidebar.error(f"Sync script not found: {S3_SYNC_SCRIPT}")
        return
    with st.sidebar:
        with st.spinner("Syncing data from S3…"):
            result = subprocess.run(
                [sys.executable, str(S3_SYNC_SCRIPT)],
                capture_output=True, text=True, timeout=120,
            )
        if result.returncode == 0:
            st.cache_data.clear()
            st.sidebar.success("Data refreshed.")
            st.rerun()
        else:
            st.sidebar.error(
                "Refresh failed. If running inside Docker, run `make refresh-db` from the host."
            )
            st.sidebar.code(result.stderr[-2000:])


# ---------------------------------------------------------------------------
# Section 0: Weather Map
# ---------------------------------------------------------------------------


def render_weather_map(df, selected_hour) -> None:
    import pydeck as pdk

    hour_label = (
        _to_et(selected_hour).strftime("%b %d, %I:%M %p ET")
        if selected_hour is not None else ""
    )
    st.header(f"Weather Map — {hour_label}")

    if df.empty:
        st.info("No data for the selected cities / hour.")
        return

    map_df = df[[
        "latitude", "longitude", "temp_f", "feels_like_f",
        "wind_speed_mph", "humidity_pct", "condition_description",
        "city_name", "state_code",
    ]].copy()

    # Colour = temp (RGB) + population-based alpha; radius = population-scaled (no overlap)
    map_df["color"] = map_df.apply(
        lambda r: _temp_rgb(r["temp_f"]) + [_pop_alpha(r["city_name"])], axis=1
    )
    map_df["radius"] = map_df["city_name"].apply(_pop_radius)

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=map_df,
        get_position=["longitude", "latitude"],
        get_fill_color="color",
        get_radius="radius",
        pickable=True,
    )

    tooltip = {
        "html": (
            "<b>{city_name}, {state_code}</b><br/>"
            "🌡 {temp_f}°F (feels {feels_like_f}°F)<br/>"
            "💧 {humidity_pct}%  💨 {wind_speed_mph} mph<br/>"
            "{condition_description}"
        )
    }

    st.pydeck_chart(
        pdk.Deck(
            layers=[layer],
            initial_view_state=pdk.ViewState(latitude=40.9, longitude=-73.9, zoom=7, pitch=0),
            tooltip=tooltip,
            map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
        ),
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Section 1: Current Conditions (per-city cards + suggestions)
# ---------------------------------------------------------------------------


def render_current_conditions(df) -> None:
    st.header("Current Conditions")

    if df.empty:
        st.info("No data for the selected cities.")
        return

    cols_per_row = 4
    cities = df.to_dict("records")

    for row_start in range(0, len(cities), cols_per_row):
        cols = st.columns(cols_per_row)
        for col_idx, city in enumerate(cities[row_start : row_start + cols_per_row]):
            icon = CONDITION_ICONS.get(city.get("condition_main", ""), "🌡️")
            condition = (city.get("condition_description") or "—").title()
            with cols[col_idx]:
                st.markdown(f"**{city['city_name']}, {city['state_code']}**")
                st.metric(
                    label=f"{icon} {condition}",
                    value=f"{city['temp_f']:.1f} °F",
                    delta=f"Feels {city['feels_like_f']:.1f} °F",
                    delta_color="off",
                )
                st.caption(
                    f"Humidity {city['humidity_pct']:.0f}%  |  "
                    f"Wind {city['wind_speed_mph']:.1f} mph  |  "
                    f"Clouds {city['clouds_pct']:.0f}%"
                )


# ---------------------------------------------------------------------------
# Section 2: Regional Snapshot (aggregate KPIs)
# ---------------------------------------------------------------------------


def render_regional_kpis(map_df, hourly_filtered, selected_hour) -> None:
    st.header("Regional Snapshot")

    if map_df.empty:
        st.info("No data for the selected cities / hour.")
        return

    max_row = map_df.loc[map_df["temp_f"].idxmax()]
    min_row = map_df.loc[map_df["temp_f"].idxmin()]
    avg_temp = float(map_df["temp_f"].mean())
    avg_wind = float(map_df["wind_speed_mph"].mean())

    prev_delta = None
    if selected_hour is not None and not hourly_filtered.empty:
        hours_sorted = sorted(hourly_filtered["observed_hour"].unique())
        if selected_hour in hours_sorted:
            idx = hours_sorted.index(selected_hour)
            if idx > 0:
                prev_h = hours_sorted[idx - 1]
                prev_rows = hourly_filtered[hourly_filtered["observed_hour"] == prev_h]
                if not prev_rows.empty:
                    prev_delta = round(avg_temp - float(prev_rows["avg_temp_f"].mean()), 1)

    delta_str = f"{prev_delta:+.1f}°F" if prev_delta is not None else None

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🌡 Max Temp", f"{max_row['temp_f']:.1f}°F",
                  f"↑ {max_row['city_name']}", delta_color="off")
    with c2:
        st.metric("🥶 Min Temp", f"{min_row['temp_f']:.1f}°F",
                  f"↓ {min_row['city_name']}", delta_color="off")
    with c3:
        st.metric("📊 Regional Avg", f"{avg_temp:.1f}°F", delta_str,
                  delta_color="normal" if prev_delta is not None else "off")
    with c4:
        st.metric("💨 Avg Wind", f"{avg_wind:.1f} mph")


# ---------------------------------------------------------------------------
# Section 3: Temperature Tracking + City Advisor
# ---------------------------------------------------------------------------


def render_temp_tracking(df_processed, selected_cities, df_current) -> None:
    import plotly.express as px
    import pandas as pd

    st.subheader("Temperature Tracking")

    if df_processed.empty or not selected_cities:
        st.info("No data for the selected cities.")
        return

    cities = st.multiselect(
        "Cities (max 3)",
        options=sorted(selected_cities),
        default=[sorted(selected_cities)[0]],
        max_selections=3,
        key="tracking_city",
    )
    if not cities:
        return

    city_df = (
        df_processed[df_processed["city"].isin(cities)]
        .sort_values("observed_at")
        [["observed_at", "city", "temp_f", "feels_like_f"]]
        .rename(columns={"temp_f": "Temp", "feels_like_f": "Feels Like"})
    )
    if city_df.empty:
        st.info("No processed data for the selected cities.")
        return

    melted = city_df.melt(
        id_vars=["observed_at", "city"],
        value_vars=["Temp", "Feels Like"],
        var_name="Metric", value_name="°F",
    )
    melted["label"] = melted["city"] + " — " + melted["Metric"]

    fig = px.line(
        melted,
        x="observed_at", y="°F",
        color="label",
        line_dash="Metric",
        line_dash_map={"Temp": "solid", "Feels Like": "dot"},
        markers=True,
        title="Temperature & Feels Like Over Time",
        labels={"observed_at": "Time (UTC)", "label": "City — Metric"},
    )
    fig.update_layout(hovermode="x unified", margin=dict(l=0, r=0, t=40, b=0))
    st.plotly_chart(fig, use_container_width=True)

    # City Advisor — city-specific seasonal suggestions based on latest conditions
    st.markdown("**🗺 City Advisor**")
    for c in cities:
        row = df_current[df_current["city_name"] == c]
        if row.empty:
            continue
        r = row.iloc[0]
        advice = _city_advisor(
            c, r.temp_f, r.feels_like_f, r.wind_speed_mph, r.condition_main, r.humidity_pct
        )
        act_str = "  ·  ".join(advice["activities"]) if advice["activities"] else "Check local listings for options."
        st.info(
            f"**{c}**\n\n"
            f"👗 {advice['dress']}\n\n"
            f"🚗 {advice['travel']}\n\n"
            f"🎯 **Things to do:** {act_str}"
        )


# ---------------------------------------------------------------------------
# Section 4: Conditions Distribution
# ---------------------------------------------------------------------------


def render_conditions_distribution(df_processed, selected_cities) -> None:
    import plotly.express as px

    st.subheader("Conditions Distribution")

    df = df_processed[df_processed["city"].isin(selected_cities)]
    if df.empty:
        st.info("No data for the selected cities.")
        return

    counts = (
        df["condition_main"]
        .value_counts()
        .reset_index()
        .rename(columns={"condition_main": "Condition", "count": "Count"})
        .sort_values("Count")
    )

    fig = px.bar(
        counts, x="Count", y="Condition", orientation="h",
        title="Weather Condition Frequency",
        color="Count", color_continuous_scale="Blues",
    )
    fig.update_layout(
        coloraxis_showscale=False,
        margin=dict(l=0, r=0, t=40, b=0),
        yaxis_title=None,
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 5: City Comparison (box plot)
# ---------------------------------------------------------------------------


def render_city_comparison(df_hourly) -> None:
    import plotly.express as px
    import pandas as pd

    st.header("City Comparison — Temperature Range")

    if df_hourly.empty:
        st.info("No data for the selected cities.")
        return

    long = pd.melt(
        df_hourly[["city_name", "min_temp_f", "avg_temp_f", "max_temp_f"]],
        id_vars="city_name",
        value_vars=["min_temp_f", "avg_temp_f", "max_temp_f"],
        value_name="temp_f",
    )
    city_order = (
        df_hourly.groupby("city_name")["avg_temp_f"]
        .mean().sort_values(ascending=False).index.tolist()
    )

    fig = px.box(
        long, x="city_name", y="temp_f", color="city_name",
        category_orders={"city_name": city_order},
        labels={"city_name": "City", "temp_f": "Temperature (°F)"},
        title="Temperature Range by City (min / avg / max across hours)",
        color_discrete_sequence=px.colors.qualitative.Safe,
    )
    fig.update_traces(
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Max: %{upperfence:.1f}°F<br>"
            "Avg: %{median:.1f}°F<br>"
            "Min: %{lowerfence:.1f}°F"
            "<extra></extra>"
        )
    )
    fig.update_layout(
        showlegend=False,
        margin=dict(l=0, r=0, t=40, b=0),
        xaxis_tickangle=-30,
    )
    st.plotly_chart(fig, use_container_width=True)


# ---------------------------------------------------------------------------
# Section 6: Hourly Detail
# ---------------------------------------------------------------------------


def render_hourly_detail(df) -> None:
    st.header("Hourly Detail")

    with st.expander("Show weather_hourly_summary table", expanded=False):
        if df.empty:
            st.info("No data for the selected cities.")
        else:
            st.dataframe(
                df.rename(columns={
                    "city_name": "City", "state_code": "State",
                    "observed_hour": "Hour", "avg_temp_f": "Avg Temp (°F)",
                    "min_temp_f": "Min Temp (°F)", "max_temp_f": "Max Temp (°F)",
                    "avg_feels_like_f": "Feels Like (°F)", "avg_humidity_pct": "Humidity (%)",
                    "avg_pressure_hpa": "Pressure (hPa)", "avg_wind_speed_mph": "Wind (mph)",
                    "max_wind_gust_mph": "Gust (mph)", "avg_clouds_pct": "Clouds (%)",
                    "dominant_condition": "Condition", "reading_count": "Readings",
                }),
                use_container_width=True,
                hide_index=True,
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    import pandas as pd

    st.title("🌤️ Tri-State Weather Dashboard")

    if not db_exists():
        st.error(
            f"DuckDB file not found at `{DB_PATH}`. "
            "Run `make refresh-db` once LocalStack is running and has weather data."
        )
        render_sidebar(pd.DataFrame(columns=["city_name", "state_code"]), [])
        return

    try:
        df_current = load_current()
        df_hourly = load_hourly()
        df_processed = load_processed()
    except Exception as exc:
        st.error(f"Failed to load data: {exc}")
        if _ENV == "prod":
            st.info(
                f"**Prod config** — reading from `s3://{_S3_PROCESSED}/` "
                f"(region: `{_AWS_REGION}`). "
                "Check that the pipeline has run and the bucket contains data."
            )
        return

    if not df_current.empty and "observed_at" in df_current.columns:
        latest = pd.to_datetime(df_current["observed_at"]).max()
        st.caption(f"Data as of: {_to_et(latest).strftime('%b %d, %Y %I:%M %p ET')}")

    # Apply 24-hour window to time-series data
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    cutoff_utc = now_utc - datetime.timedelta(hours=24)
    df_hourly = df_hourly[df_hourly["observed_hour"] >= cutoff_utc]
    df_processed = df_processed[df_processed["observed_at"] >= cutoff_utc]

    hours = sorted(df_hourly["observed_hour"].dropna().unique().tolist())
    if not hours:
        if _ENV == "prod":
            st.warning(
                f"No data found in `s3://{_S3_PROCESSED}/` in the last 24 hours. "
                "The pipeline may not have run yet — check EventBridge + Glue job status."
            )
        else:
            st.warning("No data in the last 24 hours. Run `make refresh-db` to sync.")
        return

    selected_cities, selected_hour = render_sidebar(df_current, hours)

    if not selected_cities:
        st.warning("Select at least one city from the sidebar.")
        return

    # Filter datasets
    cur_filtered = df_current[df_current["city_name"].isin(selected_cities)]
    hourly_filtered = df_hourly[df_hourly["city_name"].isin(selected_cities)]
    processed_filtered = df_processed[df_processed["city"].isin(selected_cities)]

    # Map slice: processed data at selected hour, columns renamed
    if selected_hour is not None:
        processed_slice = processed_filtered[
            processed_filtered["observed_at"].dt.floor("h") == selected_hour
        ]
    else:
        processed_slice = processed_filtered

    map_df = processed_slice.rename(columns={
        "city": "city_name", "state": "state_code",
        "lat": "latitude", "lon": "longitude",
    })

    # ── Sections ──────────────────────────────────────────────────────────────
    render_weather_map(map_df, selected_hour)
    st.divider()
    render_current_conditions(cur_filtered)
    st.divider()
    render_regional_kpis(map_df, hourly_filtered, selected_hour)
    st.divider()

    col1, col2 = st.columns(2)
    with col1:
        render_temp_tracking(processed_filtered, selected_cities, df_current)
    with col2:
        render_conditions_distribution(processed_filtered, selected_cities)

    st.divider()
    render_city_comparison(hourly_filtered)
    st.divider()
    render_hourly_detail(hourly_filtered)

    # ── Animation loop — runs until user clicks Stop ──────────────────────────
    if st.session_state.get("animating") and len(hours) > 1:
        st.session_state.anim_idx = (st.session_state.anim_idx + 1) % len(hours)
        _time.sleep(1.5)
        st.rerun()


if __name__ == "__main__":
    main()
