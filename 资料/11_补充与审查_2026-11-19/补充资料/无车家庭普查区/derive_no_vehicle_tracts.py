"""Derive Maricopa tract counts and MOEs from an archived Census Reporter response.

No new download or model modification is performed. Requires only Python stdlib.
Usage: python derive_no_vehicle_tracts.py [--input RAW_JSON] [--out DIRECTORY]
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json


def main():
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parent
    parser.add_argument("--input", type=Path, default=root / "censusreporter_acs2024_B08201_tract_04013_raw.json")
    parser.add_argument("--out", type=Path, default=root)
    parser.add_argument("--county", type=Path, default=root / "censusreporter_acs2024_B08201_county_04013_raw.json")
    args = parser.parse_args()
    source = json.loads(args.input.read_text(encoding="utf-8"))
    assert source["release"]["id"] == "acs2024_5yr"
    assert source["release"]["years"] == "2020-2024"
    table = source["tables"]["B08201"]
    assert table["universe"] == "Households"
    assert table["columns"]["B08201002"]["name"] == "No vehicle available"
    rows = []
    sentinel_fields = 0
    for geoid, entry in sorted(source["data"].items()):
        if not geoid.startswith("14000US04013"):
            continue
        b = entry["B08201"]
        total, total_moe = b["estimate"]["B08201001"], b["error"]["B08201001"]
        zero, zero_moe = b["estimate"]["B08201002"], b["error"]["B08201002"]
        values = [total, total_moe, zero, zero_moe]
        sentinel_fields += sum(x is not None and x < 0 for x in values)
        cleaned = [x if x is not None and x >= 0 else None for x in values]
        total, total_moe, zero, zero_moe = cleaned
        if total is not None and zero is not None:
            assert 0 <= zero <= total, (geoid, total, zero)
        rows.append({"GEOID": geoid.removeprefix("14000US"),
                     "census_reporter_geoid": geoid,
                     "NAME": source["geography"][geoid]["name"],
                     "state": "04", "county": "013", "tract": geoid[-6:],
                     "B08201_001E_households": total,
                     "B08201_001M_households_moe90": total_moe,
                     "B08201_002E_no_vehicle_households": zero,
                     "B08201_002M_no_vehicle_households_moe90": zero_moe,
                     "pct_no_vehicle_fraction": zero / total if total and zero is not None else None,
                     "ratio_moe": "NOT_DERIVED",
                     "source_provider": "CENSUS_REPORTER_MIRROR_OF_CENSUS_ACS",
                     "release": "acs2024_5yr", "acs_period": "2020-2024"})
    assert rows and len({x["GEOID"] for x in rows}) == len(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    csv_path = args.out / "maricopa_tract_no_vehicle_acs2024_5yr.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    county_source = json.loads(args.county.read_text(encoding="utf-8"))
    assert county_source["release"]["id"] == "acs2024_5yr"
    county = county_source["data"]["05000US04013"]["B08201"]["estimate"]
    assert sum(x["B08201_001E_households"] or 0 for x in rows) == county["B08201001"]
    assert sum(x["B08201_002E_no_vehicle_households"] or 0 for x in rows) == county["B08201002"]
    validation = {
        "raw_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "county_raw_sha256": hashlib.sha256(args.county.read_bytes()).hexdigest(),
        "release_checked": source["release"],
        "raw_geography_count": len(source["data"]),
        "selected_tract_count": len(rows),
        "non_tract_parent_rows_excluded": len(source["data"]) - len(rows),
        "tract_ids_unique": True,
        "all_tracts_in_state04_county013": True,
        "nonnegative_estimate_numerators_within_denominators": True,
        "negative_sentinel_fields_converted_to_empty_csv_cells": sentinel_fields,
        "missing_total_estimates": sum(x["B08201_001E_households"] is None for x in rows),
        "missing_no_vehicle_estimates": sum(x["B08201_002E_no_vehicle_households"] is None for x in rows),
        "zero_household_tracts": sum(x["B08201_001E_households"] == 0 for x in rows),
        "tract_households_sum": sum(x["B08201_001E_households"] or 0 for x in rows),
        "tract_no_vehicle_households_sum": sum(x["B08201_002E_no_vehicle_households"] or 0 for x in rows),
        "published_county_households": county.get("B08201001"),
        "published_county_no_vehicle_households": county.get("B08201002"),
        "tract_count_sums_exactly_match_separate_county_response": True,
        "MOEs_not_added_and_ratio_MOE_not_claimed": True,
        "not_mapped_to_villages_or_contest_districts": True,
        "model_inputs_changed": False,
    }
    (args.out / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=True))


if __name__ == "__main__":
    main()
