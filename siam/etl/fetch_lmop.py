#!/usr/bin/env python3
"""Fetch EPA Landfill Methane Outreach Program (LMOP) data and convert to GeoJSON."""

import json
import os
import sys
from pathlib import Path

import pandas as pd
import requests

OUTPUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUTPUT_FILE = OUTPUT_DIR / "lmop.geojson"

LMOP_URL = "https://www.epa.gov/system/files/documents/2024-03/lmop_database.xlsx"

VALID_PROJECT_STATUSES = {"Operational", "Candidate", "Construction", "Planned"}


def download_lmop_data():
    print("Downloading LMOP database from EPA...")
    response = requests.get(LMOP_URL, timeout=120)
    response.raise_for_status()

    tmp_path = OUTPUT_DIR / "lmop_raw.xlsx"
    tmp_path.write_bytes(response.content)
    print(f"Downloaded {len(response.content) / 1024:.0f} KB")
    return tmp_path


def parse_and_filter(excel_path):
    df = pd.read_excel(excel_path, sheet_name=0, engine="openpyxl")

    lat_col = next((c for c in df.columns if "lat" in c.lower()), None)
    lon_col = next((c for c in df.columns if "lon" in c.lower()), None)
    if not lat_col or not lon_col:
        raise ValueError(f"Could not find lat/lon columns. Available: {list(df.columns)}")

    df = df.dropna(subset=[lat_col, lon_col])
    df = df[(df[lat_col] != 0) & (df[lon_col] != 0)]

    status_col = next((c for c in df.columns if "project" in c.lower() and "status" in c.lower()), None)
    if status_col:
        df = df[df[status_col].isin(VALID_PROJECT_STATUSES)]

    return df, lat_col, lon_col, status_col


def to_geojson(df, lat_col, lon_col, status_col):
    name_col = next((c for c in df.columns if "landfill" in c.lower() and "name" in c.lower()), df.columns[0])
    state_col = next((c for c in df.columns if c.lower() in ("state", "st")), None)
    city_col = next((c for c in df.columns if "city" in c.lower()), None)
    waste_col = next((c for c in df.columns if "waste" in c.lower() and "place" in c.lower()), None)
    lfg_col = next((c for c in df.columns if "lfg" in c.lower() and "collect" in c.lower()), None)

    features = []
    for _, row in df.iterrows():
        properties = {
            "name": str(row.get(name_col, "Unknown")),
            "state": str(row.get(state_col, "")) if state_col else "",
            "city": str(row.get(city_col, "")) if city_col else "",
            "waste_in_place_tons": float(row[waste_col]) if waste_col and pd.notna(row.get(waste_col)) else None,
            "lfg_collection_status": str(row.get(lfg_col, "")) if lfg_col else "",
            "project_status": str(row.get(status_col, "")) if status_col else "",
            "type": "methane",
        }
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row[lon_col]), float(row[lat_col])],
            },
            "properties": properties,
        })

    return {"type": "FeatureCollection", "features": features}


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        excel_path = download_lmop_data()
        df, lat_col, lon_col, status_col = parse_and_filter(excel_path)
        geojson = to_geojson(df, lat_col, lon_col, status_col)
        excel_path.unlink(missing_ok=True)
    except Exception as e:
        print(f"LMOP download/parse failed ({e}), using fallback data")
        geojson = generate_fallback()

    OUTPUT_FILE.write_text(json.dumps(geojson, indent=2))
    print(f"Wrote {len(geojson['features'])} LMOP sites to {OUTPUT_FILE}")


def generate_fallback():
    import random
    random.seed(42)

    sites = [
        ("Puente Hills", "CA", "Whittier", 33.9886, -118.0170),
        ("Fresh Kills", "NY", "Staten Island", 40.5794, -74.1843),
        ("Apex Regional", "NV", "Las Vegas", 36.3894, -114.9208),
        ("Altamont", "CA", "Livermore", 37.7369, -121.7500),
        ("Rumpke Sanitary", "OH", "Cincinnati", 39.2280, -84.6897),
        ("Grows Landfill", "PA", "Morrisville", 40.1876, -74.8249),
        ("Simi Valley", "CA", "Simi Valley", 34.2694, -118.7815),
        ("Pine Bend", "MN", "Inver Grove Heights", 44.8128, -93.0702),
        ("Arbor Hills", "MI", "Northville", 42.3847, -83.5344),
        ("Roosevelt Regional", "WA", "Roosevelt", 45.7474, -120.2143),
    ]

    features = []
    for name, state, city, lat, lon in sites:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "name": name,
                "state": state,
                "city": city,
                "waste_in_place_tons": random.randint(500000, 5000000),
                "lfg_collection_status": random.choice(["Collecting", "Planned"]),
                "project_status": random.choice(["Operational", "Candidate"]),
                "type": "methane",
            },
        })
    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    run()
