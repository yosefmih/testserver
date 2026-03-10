#!/usr/bin/env python3
"""Fetch or generate state-level industrial electricity rates."""

import json
from pathlib import Path

import requests

OUTPUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUTPUT_FILE = OUTPUT_DIR / "energy_rates.json"

FALLBACK_RATES = {
    "AL": 0.072, "AK": 0.185, "AZ": 0.078, "AR": 0.068, "CA": 0.165,
    "CO": 0.084, "CT": 0.155, "DE": 0.098, "FL": 0.089, "GA": 0.073,
    "HI": 0.275, "ID": 0.068, "IL": 0.082, "IN": 0.079, "IA": 0.075,
    "KS": 0.081, "KY": 0.065, "LA": 0.063, "ME": 0.118, "MD": 0.099,
    "MA": 0.168, "MI": 0.092, "MN": 0.088, "MS": 0.071, "MO": 0.078,
    "MT": 0.072, "NE": 0.079, "NV": 0.075, "NH": 0.148, "NJ": 0.125,
    "NM": 0.078, "NY": 0.145, "NC": 0.076, "ND": 0.075, "OH": 0.078,
    "OK": 0.065, "OR": 0.069, "PA": 0.088, "RI": 0.162, "SC": 0.071,
    "SD": 0.082, "TN": 0.078, "TX": 0.072, "UT": 0.071, "VT": 0.128,
    "VA": 0.078, "WA": 0.055, "WV": 0.072, "WI": 0.088, "WY": 0.072,
    "DC": 0.095,
}


def try_eia_api():
    api_key = "YOUR_EIA_API_KEY"
    if api_key.startswith("YOUR_"):
        return None

    url = f"https://api.eia.gov/v2/electricity/retail-sales/data/?api_key={api_key}"
    params = {
        "frequency": "annual",
        "data[0]": "price",
        "facets[sectorid][]": "IND",
        "sort[0][column]": "period",
        "sort[0][direction]": "desc",
        "length": 100,
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        rates = {}
        for record in data.get("response", {}).get("data", []):
            state = record.get("stateid", "")
            price = record.get("price")
            if state and price and state not in rates and len(state) == 2:
                rates[state] = round(float(price) / 100, 4)
        return rates if len(rates) > 10 else None
    except Exception:
        return None


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rates = try_eia_api()
    if rates:
        print(f"Fetched {len(rates)} state rates from EIA API")
    else:
        print("Using curated industrial electricity rates")
        rates = FALLBACK_RATES

    OUTPUT_FILE.write_text(json.dumps(rates, indent=2))
    print(f"Wrote energy rates for {len(rates)} states to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
