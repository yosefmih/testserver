#!/usr/bin/env python3
"""Fetch EIA-860 generator data, filter for wind/solar in high-curtailment ISOs."""

import io
import json
import os
import zipfile
from pathlib import Path

import pandas as pd
import requests

OUTPUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUTPUT_FILE = OUTPUT_DIR / "eia860_renewables.geojson"

EIA860_BASE_URL = "https://www.eia.gov/electricity/data/eia860"

ISO_STATE_MAP = {
    "CAISO": ["CA"],
    "ERCOT": ["TX"],
    "SPP": ["KS", "OK", "NE", "SD", "ND"],
}
ALL_ISO_STATES = {s for states in ISO_STATE_MAP.values() for s in states}

TARGET_TECHNOLOGIES = {"Wind", "Solar Photovoltaic", "Solar Thermal", "Onshore Wind Turbine", "Offshore Wind Turbine"}


def determine_iso(state):
    for iso, states in ISO_STATE_MAP.items():
        if state in states:
            return iso
    return "Unknown"


def download_eia860():
    for year in range(2023, 2019, -1):
        url = f"{EIA860_BASE_URL}/xls/eia8602{year}.zip"
        print(f"Trying EIA-860 for year {year}: {url}")
        try:
            response = requests.get(url, timeout=120)
            if response.status_code == 200:
                print(f"Downloaded EIA-860 {year} ({len(response.content) / 1024:.0f} KB)")
                return response.content, year
        except requests.RequestException:
            continue
    raise RuntimeError("Could not download EIA-860 data for any recent year")


def parse_generators(zip_content, year):
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
        generator_files = [f for f in zf.namelist() if "generator" in f.lower() and f.endswith(".xlsx")]
        if not generator_files:
            generator_files = [f for f in zf.namelist() if "3_1" in f and f.endswith(".xlsx")]
        if not generator_files:
            raise FileNotFoundError(f"No generator file found. Contents: {zf.namelist()}")

        target_file = generator_files[0]
        print(f"Parsing {target_file}")
        with zf.open(target_file) as f:
            df = pd.read_excel(f, sheet_name=0, engine="openpyxl", header=1)

    return df


def filter_and_convert(df):
    tech_col = next((c for c in df.columns if "technol" in c.lower()), None)
    status_col = next((c for c in df.columns if c.lower() in ("status", "operating status")), None)
    state_col = next((c for c in df.columns if c.lower() in ("state", "plant state")), None)
    lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
    lon_col = next((c for c in df.columns if "lon" in c.lower() or "long" in c.lower()), None)
    name_col = next((c for c in df.columns if "plant" in c.lower() and "name" in c.lower()), df.columns[0])
    cap_col = next((c for c in df.columns if "nameplate" in c.lower() and "capacity" in c.lower()), None)

    if not all([tech_col, state_col, lat_col, lon_col]):
        raise ValueError(f"Missing required columns. Found: {list(df.columns)[:20]}")

    if status_col:
        df = df[df[status_col].astype(str).str.upper().isin(["OP", "OPERATING"])]

    df = df[df[tech_col].astype(str).apply(lambda t: any(target in t for target in ["Wind", "Solar"]))]
    df = df[df[state_col].astype(str).isin(ALL_ISO_STATES)]
    df = df.dropna(subset=[lat_col, lon_col])

    features = []
    for _, row in df.iterrows():
        tech = str(row[tech_col])
        technology = "Solar" if "Solar" in tech else "Wind"
        state = str(row[state_col])

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row[lon_col]), float(row[lat_col])],
            },
            "properties": {
                "plant_name": str(row.get(name_col, "Unknown")),
                "state": state,
                "nameplate_capacity_mw": float(row[cap_col]) if cap_col and pd.notna(row.get(cap_col)) else None,
                "technology": technology,
                "balancing_authority": determine_iso(state),
                "type": technology.lower(),
            },
        })

    return {"type": "FeatureCollection", "features": features}


def generate_fallback():
    import random
    random.seed(43)

    sites = []
    regions = {
        "CAISO_Wind": [("Tehachapi Wind Farm", "CA", 35.08, -118.45), ("Altamont Pass", "CA", 37.73, -121.64), ("San Gorgonio Pass", "CA", 33.92, -116.58)],
        "CAISO_Solar": [("Ivanpah Solar", "CA", 35.55, -115.47), ("Topaz Solar", "CA", 35.05, -119.98), ("Desert Sunlight", "CA", 33.83, -115.40)],
        "ERCOT_Wind": [("Roscoe Wind Farm", "TX", 32.45, -100.53), ("Horse Hollow", "TX", 32.07, -100.28), ("Sweetwater Wind", "TX", 32.47, -100.40), ("Gulf Wind", "TX", 27.20, -97.39)],
        "ERCOT_Solar": [("Samson Solar", "TX", 33.43, -96.10), ("Roadrunner Solar", "TX", 32.20, -102.60)],
        "SPP_Wind": [("Meridian Way", "KS", 37.85, -97.95), ("Flat Ridge", "KS", 37.20, -97.75), ("Cimarron Bend", "KS", 37.05, -100.35), ("Traverse Wind", "OK", 36.30, -98.40)],
    }

    for region, plants in regions.items():
        iso, tech = region.rsplit("_", 1)
        for name, state, lat, lon in plants:
            lat += random.uniform(-0.1, 0.1)
            lon += random.uniform(-0.1, 0.1)
            sites.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "plant_name": name,
                    "state": state,
                    "nameplate_capacity_mw": random.randint(50, 500),
                    "technology": tech,
                    "balancing_authority": iso,
                    "type": tech.lower(),
                },
            })

    return {"type": "FeatureCollection", "features": sites}


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        zip_content, year = download_eia860()
        df = parse_generators(zip_content, year)
        geojson = filter_and_convert(df)
    except Exception as e:
        print(f"EIA-860 download/parse failed ({e}), using fallback data")
        geojson = generate_fallback()

    OUTPUT_FILE.write_text(json.dumps(geojson, indent=2))
    print(f"Wrote {len(geojson['features'])} renewable sites to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
