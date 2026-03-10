#!/usr/bin/env python3
"""Master ETL runner — executes all data fetch scripts in sequence."""

import importlib
import sys
import time
from pathlib import Path

SCRIPTS = [
    "fetch_datacenters",
    "fetch_fiber",
    "fetch_energy_rates",
    "fetch_lmop",
    "fetch_eia860",
    "fetch_viirs",
]


def run():
    print("=" * 60)
    print("SIAM Data Pipeline — Starting ETL")
    print("=" * 60)

    results = {}
    total_start = time.time()

    for script_name in SCRIPTS:
        print(f"\n{'─' * 40}")
        print(f"Running {script_name}...")
        start = time.time()

        try:
            module = importlib.import_module(script_name)
            module.run()
            elapsed = time.time() - start
            results[script_name] = f"OK ({elapsed:.1f}s)"
            print(f"{script_name} completed in {elapsed:.1f}s")
        except Exception as e:
            elapsed = time.time() - start
            results[script_name] = f"FAILED ({e})"
            print(f"{script_name} FAILED: {e}")

    total_elapsed = time.time() - total_start
    print(f"\n{'=' * 60}")
    print("ETL Summary")
    print(f"{'=' * 60}")
    for script, status in results.items():
        print(f"  {script:.<30} {status}")
    print(f"\nTotal time: {total_elapsed:.1f}s")

    output_dir = Path(__file__).parent.parent / "public" / "data"
    if output_dir.exists():
        files = list(output_dir.glob("*"))
        print(f"\nGenerated {len(files)} files in {output_dir}:")
        for f in sorted(files):
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:.<30} {size_kb:.1f} KB")


if __name__ == "__main__":
    run()
