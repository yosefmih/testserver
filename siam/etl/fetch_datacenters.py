#!/usr/bin/env python3
"""Generate data center / hyperscale hub GeoJSON from curated public data."""

import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUTPUT_FILE = OUTPUT_DIR / "datacenters.geojson"

DATACENTERS = [
    {"name": "AWS us-east-1", "provider": "AWS", "region_id": "us-east-1", "type": "hyperscale", "lat": 39.0438, "lon": -77.4875},
    {"name": "AWS us-east-2", "provider": "AWS", "region_id": "us-east-2", "type": "hyperscale", "lat": 39.9612, "lon": -82.9988},
    {"name": "AWS us-west-1", "provider": "AWS", "region_id": "us-west-1", "type": "hyperscale", "lat": 37.3382, "lon": -121.8863},
    {"name": "AWS us-west-2", "provider": "AWS", "region_id": "us-west-2", "type": "hyperscale", "lat": 45.8399, "lon": -119.7050},
    {"name": "GCP us-central1", "provider": "GCP", "region_id": "us-central1", "type": "hyperscale", "lat": 41.2619, "lon": -95.8608},
    {"name": "GCP us-east1", "provider": "GCP", "region_id": "us-east1", "type": "hyperscale", "lat": 33.1960, "lon": -80.0131},
    {"name": "GCP us-east4", "provider": "GCP", "region_id": "us-east4", "type": "hyperscale", "lat": 39.0438, "lon": -77.4740},
    {"name": "GCP us-west1", "provider": "GCP", "region_id": "us-west1", "type": "hyperscale", "lat": 45.5946, "lon": -121.1787},
    {"name": "Azure East US", "provider": "Azure", "region_id": "eastus", "type": "hyperscale", "lat": 36.6677, "lon": -78.3750},
    {"name": "Azure West US", "provider": "Azure", "region_id": "westus", "type": "hyperscale", "lat": 47.2343, "lon": -119.8526},
    {"name": "Azure Central US", "provider": "Azure", "region_id": "centralus", "type": "hyperscale", "lat": 41.6006, "lon": -93.6091},
    {"name": "Azure South Central US", "provider": "Azure", "region_id": "southcentralus", "type": "hyperscale", "lat": 29.4241, "lon": -98.4936},
    {"name": "Equinix Ashburn DC1-DC15", "provider": "Equinix", "region_id": "DC", "type": "ix", "lat": 39.0458, "lon": -77.4875},
    {"name": "Equinix San Jose SV1-SV5", "provider": "Equinix", "region_id": "SV", "type": "ix", "lat": 37.3352, "lon": -121.8893},
    {"name": "Equinix Chicago CH1-CH4", "provider": "Equinix", "region_id": "CH", "type": "ix", "lat": 41.8781, "lon": -87.6298},
    {"name": "Equinix Dallas DA1-DA3", "provider": "Equinix", "region_id": "DA", "type": "ix", "lat": 32.8140, "lon": -96.8167},
    {"name": "Equinix Los Angeles LA1-LA4", "provider": "Equinix", "region_id": "LA", "type": "ix", "lat": 34.0522, "lon": -118.2437},
    {"name": "Equinix Miami MI1-MI3", "provider": "Equinix", "region_id": "MI", "type": "ix", "lat": 25.7617, "lon": -80.1918},
    {"name": "CoreSite Denver DE1", "provider": "CoreSite", "region_id": "DE1", "type": "colo", "lat": 39.7392, "lon": -104.9903},
    {"name": "CoreSite Silicon Valley SV7", "provider": "CoreSite", "region_id": "SV7", "type": "colo", "lat": 37.3861, "lon": -122.0839},
    {"name": "Digital Realty Dallas DFW", "provider": "Digital Realty", "region_id": "DFW", "type": "colo", "lat": 32.7767, "lon": -96.8297},
    {"name": "Digital Realty Ashburn", "provider": "Digital Realty", "region_id": "IAD", "type": "colo", "lat": 39.0300, "lon": -77.4710},
    {"name": "QTS Chicago", "provider": "QTS", "region_id": "ORD", "type": "colo", "lat": 41.8500, "lon": -87.6500},
    {"name": "CyrusOne Houston", "provider": "CyrusOne", "region_id": "IAH", "type": "colo", "lat": 29.9841, "lon": -95.3414},
]


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    features = []
    for dc in DATACENTERS:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [dc["lon"], dc["lat"]],
            },
            "properties": {
                "name": dc["name"],
                "provider": dc["provider"],
                "region_id": dc["region_id"],
                "dc_type": dc["type"],
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    OUTPUT_FILE.write_text(json.dumps(geojson, indent=2))
    print(f"Wrote {len(features)} data center locations to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
