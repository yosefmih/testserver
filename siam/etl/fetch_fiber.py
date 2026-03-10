#!/usr/bin/env python3
"""Generate fiber backbone routes along major US interstate highways."""

import json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "public" / "data"
OUTPUT_FILE = OUTPUT_DIR / "fiber_backbone.geojson"

BACKBONE_ROUTES = {
    "I-95 (Lumen/Level3)": {
        "operator": "Lumen",
        "type": "long_haul",
        "coordinates": [
            [-71.0589, 42.3601],   # Boston
            [-71.4128, 41.8240],   # Providence
            [-72.9279, 41.3083],   # New Haven
            [-73.9857, 40.7484],   # New York
            [-74.1724, 40.7357],   # Newark
            [-75.1652, 39.9526],   # Philadelphia
            [-75.5277, 39.1582],   # Wilmington DE
            [-76.6122, 39.2904],   # Baltimore
            [-77.0369, 38.9072],   # Washington DC
            [-77.4360, 37.5407],   # Richmond
            [-78.6382, 35.7796],   # Raleigh
            [-79.9311, 32.7765],   # Charleston
            [-81.0998, 32.0809],   # Savannah
            [-81.6557, 30.3322],   # Jacksonville
            [-80.1918, 25.7617],   # Miami
        ],
    },
    "I-5 (Zayo)": {
        "operator": "Zayo",
        "type": "long_haul",
        "coordinates": [
            [-122.3321, 47.6062],  # Seattle
            [-122.6765, 45.5152],  # Portland
            [-123.0868, 44.0521],  # Eugene
            [-122.7141, 42.3265],  # Medford
            [-122.3942, 40.5865],  # Redding
            [-121.4944, 38.5816],  # Sacramento
            [-121.8863, 37.3382],  # San Jose
            [-119.7871, 36.7378],  # Fresno
            [-118.7798, 34.4208],  # Santa Barbara
            [-118.2437, 34.0522],  # Los Angeles
            [-117.1611, 32.7157],  # San Diego
        ],
    },
    "I-80 (AT&T)": {
        "operator": "AT&T",
        "type": "long_haul",
        "coordinates": [
            [-122.4194, 37.7749],  # San Francisco
            [-121.4944, 38.5816],  # Sacramento
            [-120.0324, 39.0968],  # Reno area
            [-112.0154, 40.7338],  # Salt Lake City
            [-109.5498, 41.5868],  # Rock Springs WY
            [-106.3131, 41.1400],  # Laramie
            [-104.8214, 41.1400],  # Cheyenne
            [-102.8788, 40.8258],  # North Platte area
            [-100.7543, 40.6942],  # Kearney NE
            [-96.7898, 40.8136],  # Lincoln
            [-95.9345, 41.2565],  # Omaha
            [-93.6091, 41.6006],  # Des Moines
            [-90.5885, 41.5236],  # Davenport/Quad Cities
            [-87.6298, 41.8781],  # Chicago
            [-84.3880, 41.6528],  # Toledo
            [-81.6944, 41.4993],  # Cleveland
            [-80.0431, 40.4406],  # Pittsburgh area
            [-77.8600, 40.7934],  # State College area
            [-75.1652, 39.9526],  # Philadelphia area
            [-74.0060, 40.7128],  # New York
        ],
    },
    "I-10 (Lumen/Level3)": {
        "operator": "Lumen",
        "type": "long_haul",
        "coordinates": [
            [-118.2437, 34.0522],  # Los Angeles
            [-116.5453, 33.8303],  # Palm Springs
            [-114.6183, 32.6927],  # Yuma
            [-112.0740, 33.4484],  # Phoenix
            [-111.9431, 32.2226],  # Tucson
            [-106.6504, 32.3199],  # Las Cruces
            [-106.4424, 31.7619],  # El Paso
            [-102.0779, 31.9974],  # Pecos area
            [-100.4370, 31.4638],  # junction area
            [-98.4936, 29.4241],  # San Antonio
            [-97.7431, 30.2672],  # Austin
            [-95.3698, 29.7604],  # Houston
            [-93.2210, 30.2241],  # Beaumont
            [-92.0198, 30.2266],  # Lake Charles
            [-91.1871, 30.4515],  # Baton Rouge
            [-90.0715, 29.9511],  # New Orleans
            [-88.0399, 30.6954],  # Mobile
            [-87.2169, 30.4383],  # Pensacola
            [-84.2807, 30.4383],  # Tallahassee
            [-81.6557, 30.3322],  # Jacksonville
        ],
    },
    "I-70 (Zayo)": {
        "operator": "Zayo",
        "type": "long_haul",
        "coordinates": [
            [-104.9903, 39.7392],  # Denver
            [-100.5199, 39.0639],  # Hays KS area
            [-97.3375, 39.0473],  # Topeka area
            [-94.5786, 39.0997],  # Kansas City
            [-92.3341, 38.9517],  # Columbia MO
            [-90.1994, 38.6270],  # St. Louis
            [-89.6501, 38.5200],  # E. St. Louis area
            [-87.5321, 39.1653],  # Terre Haute
            [-86.1581, 39.7684],  # Indianapolis
            [-84.5120, 39.1031],  # Cincinnati area
            [-82.9988, 39.9612],  # Columbus
            [-80.6665, 40.0584],  # Wheeling WV area
            [-79.9959, 40.4406],  # Pittsburgh
            [-77.0146, 39.6395],  # Frederick MD
            [-76.6122, 39.2904],  # Baltimore
        ],
    },
    "I-40 (AT&T)": {
        "operator": "AT&T",
        "type": "long_haul",
        "coordinates": [
            [-117.0173, 34.9592],  # Barstow CA
            [-116.1668, 34.8958],  # Needles area
            [-114.5695, 35.1917],  # Kingman AZ
            [-111.6513, 35.1983],  # Flagstaff
            [-110.5249, 35.0857],  # Winslow AZ
            [-109.0452, 35.1395],  # Gallup NM
            [-106.6504, 35.0844],  # Albuquerque
            [-104.6674, 34.8375],  # Santa Rosa NM
            [-103.2148, 35.1814],  # Amarillo area
            [-97.5164, 35.4676],  # Oklahoma City
            [-95.9928, 36.1540],  # Tulsa area
            [-94.1633, 36.3729],  # Joplin area
            [-93.0933, 35.3859],  # Ft Smith area
            [-92.2896, 35.0845],  # Little Rock
            [-90.0490, 35.1495],  # Memphis
            [-86.7816, 36.1627],  # Nashville
            [-83.9207, 35.9606],  # Knoxville
            [-82.5515, 35.5951],  # Asheville
            [-80.2442, 36.0999],  # Winston-Salem
            [-79.7910, 36.0726],  # Greensboro
            [-78.6382, 35.7796],  # Raleigh
            [-77.8868, 34.2257],  # Wilmington NC
        ],
    },
    "I-35 (Lumen/Level3)": {
        "operator": "Lumen",
        "type": "long_haul",
        "coordinates": [
            [-92.1005, 46.7867],  # Duluth
            [-93.2650, 44.9778],  # Minneapolis
            [-93.6091, 41.6006],  # Des Moines
            [-94.5786, 39.0997],  # Kansas City
            [-97.3301, 37.6872],  # Wichita
            [-97.5164, 35.4676],  # Oklahoma City
            [-97.1375, 33.2148],  # Gainesville TX
            [-96.7970, 32.7767],  # Dallas/Ft Worth
            [-97.1431, 31.5493],  # Waco
            [-97.7431, 30.2672],  # Austin
            [-98.4936, 29.4241],  # San Antonio
            [-99.5075, 27.5064],  # Laredo
        ],
    },
    "I-75 (AT&T)": {
        "operator": "AT&T",
        "type": "long_haul",
        "coordinates": [
            [-84.3471, 46.4953],  # Sault Ste Marie
            [-84.7477, 44.7631],  # Grayling MI
            [-83.7483, 43.4195],  # Saginaw
            [-83.3554, 42.3314],  # Detroit area
            [-83.7510, 41.6528],  # Toledo
            [-84.1916, 39.7589],  # Dayton
            [-84.5120, 39.1031],  # Cincinnati
            [-84.3880, 38.0406],  # Lexington
            [-84.2700, 37.6939],  # Corbin KY area
            [-83.9207, 35.9606],  # Knoxville
            [-84.3880, 33.7490],  # Atlanta
            [-83.6324, 32.8407],  # Macon
            [-82.3417, 31.5886],  # Valdosta area
            [-82.3248, 30.3322],  # Jacksonville area
            [-82.4572, 27.9506],  # Tampa
            [-81.3789, 28.5384],  # Orlando
            [-80.6081, 28.0836],  # Melbourne
            [-80.3517, 27.2038],  # Fort Pierce area
            [-80.1373, 26.1224],  # Ft Lauderdale
            [-80.1918, 25.7617],  # Miami
        ],
    },
    "I-90 (Zayo)": {
        "operator": "Zayo",
        "type": "long_haul",
        "coordinates": [
            [-122.3321, 47.6062],  # Seattle
            [-117.4260, 47.6588],  # Spokane
            [-113.9940, 46.8721],  # Missoula
            [-111.0429, 45.6770],  # Bozeman
            [-106.6340, 45.7833],  # Billings
            [-105.5127, 44.7983],  # Sheridan WY area
            [-104.7143, 44.0805],  # Gillette area
            [-103.2310, 44.0805],  # Rapid City
            [-100.3510, 43.7252],  # Pierre SD area
            [-97.3500, 43.5500],  # Mitchell SD
            [-96.7321, 43.5460],  # Sioux Falls
            [-93.2650, 44.9778],  # Minneapolis
            [-91.2396, 43.8014],  # La Crosse WI
            [-89.4012, 43.0731],  # Madison
            [-88.0131, 42.3314],  # Milwaukee area
            [-87.6298, 41.8781],  # Chicago
            [-84.3880, 41.6528],  # Toledo
            [-81.6944, 41.4993],  # Cleveland
            [-79.0060, 42.1292],  # Erie
            [-78.8784, 42.8864],  # Buffalo
            [-76.1474, 43.0481],  # Syracuse
            [-73.7562, 42.6526],  # Albany
            [-72.5734, 42.1015],  # Springfield MA
            [-71.0589, 42.3601],  # Boston
        ],
    },
    "I-20 (AT&T)": {
        "operator": "AT&T",
        "type": "long_haul",
        "coordinates": [
            [-101.8313, 32.4487],  # Midland TX
            [-100.4370, 32.4487],  # Abilene area
            [-96.7970, 32.7767],  # Dallas/Ft Worth
            [-94.7977, 32.5007],  # Longview TX
            [-92.1193, 32.5251],  # Ruston LA area
            [-91.1403, 32.5093],  # Vicksburg
            [-90.1848, 32.2988],  # Jackson MS
            [-88.7034, 32.3547],  # Meridian MS
            [-87.5692, 33.2098],  # Tuscaloosa
            [-86.8024, 33.5207],  # Birmingham
            [-85.0024, 33.4045],  # Anniston AL
            [-84.3880, 33.7490],  # Atlanta
            [-83.2321, 33.4735],  # Madison GA area
            [-82.0070, 33.4710],  # Augusta
            [-81.0348, 34.0007],  # Columbia SC
            [-79.7910, 34.1954],  # Florence SC
        ],
    },
}


def run():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    features = []
    for route_name, route_data in BACKBONE_ROUTES.items():
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": route_data["coordinates"],
            },
            "properties": {
                "route_name": route_name,
                "type": route_data["type"],
                "operator": route_data["operator"],
            },
        })

    geojson = {"type": "FeatureCollection", "features": features}
    OUTPUT_FILE.write_text(json.dumps(geojson, indent=2))
    print(f"Wrote {len(features)} fiber backbone routes to {OUTPUT_FILE}")


if __name__ == "__main__":
    run()
