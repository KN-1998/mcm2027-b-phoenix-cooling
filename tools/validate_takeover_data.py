"""Offline checks of real source reconstruction, not service-outcome validation.

Usage: python tools/validate_takeover_data.py --out results/takeover_data_validation
The dated availability audit compares each posted weekday cell with the previous
weekday-envelope rule. Unknown cells are excluded from numerical error scoring.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.mch.realnet import MAG_CSV, calendar_for_date

EXTRA = ROOT / "资料" / "11_补充与审查_2026-11-19" / "补充资料"
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def independent_clock(raw):
    value = str(raw or "").strip().upper()
    for fmt in ("%I:%M %p", "%I %p", "%I:%M%p", "%I%p"):
        try:
            parsed = dt.datetime.strptime(value, fmt)
            return parsed.hour + parsed.minute / 60
        except ValueError:
            pass
    return None


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "takeover_data_validation")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    rows = read_csv(MAG_CSV)
    raw_path = EXTRA / "MAG日历" / "原始响应" / "query_all_fields.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8-sig"))
    raw_phoenix = {str(f["attributes"]["OBJECTID"]): f["attributes"] for f in raw["features"]
                   if str(f["attributes"].get("Year")) == "2026"
                   and str(f["attributes"].get("City")).strip().lower() == "phoenix"}
    assert len(rows) == len(raw_phoenix) == 50
    assert {r["OBJECTID"] for r in rows} == set(raw_phoenix)
    source_mismatches = []
    for row in rows:
        for day in DAYS:
            for key in (day + "Open", day + "Close"):
                if (row.get(key) or "") != (raw_phoenix[row["OBJECTID"]].get(key) or ""):
                    source_mismatches.append([row["OBJECTID"], key])
    assert not source_mismatches

    audit, legacy_errors, corrected_errors = [], [], []
    status_counts = {}
    for row in rows:
        opens = [independent_clock(row.get(d + "Open")) for d in DAYS[:5]]
        closes = [independent_clock(row.get(d + "Close")) for d in DAYS[:5]]
        baseline_open = min((v for v in opens if v is not None), default=9.0)
        baseline_close = max((v for v in closes if v is not None), default=17.0)
        if baseline_close <= baseline_open:
            baseline_close = min(24, baseline_open + 8)
        for offset, day in enumerate(DAYS):
            date = dt.date(2026, 7, 20) + dt.timedelta(days=offset)
            rule = calendar_for_date(row, date)
            status_counts[rule["status"]] = status_counts.get(rule["status"], 0) + 1
            op, cl = independent_clock(row.get(day + "Open")), independent_clock(row.get(day + "Close"))
            known = (op is not None and cl is not None and op != cl
                     and rule["status"] != "outside_posted_source_date_range")
            old_error = new_error = None
            if known:
                old_error = (abs(baseline_open - op) + abs(baseline_close - cl)) / 2
                if not rule["status"].startswith("open_"):
                    raise AssertionError("known weekday pair lost during calendar resolution")
                new_error = (abs(rule["open_hour"] - op) + abs(rule["close_hour"] - cl)) / 2
                legacy_errors.append(old_error)
                corrected_errors.append(new_error)
            audit.append({"objectid": row["OBJECTID"], "name": row["Location"],
                "kind": row["HeatRelief_Type"], "date": date.isoformat(), "weekday": day,
                "source_open_raw": row.get(day + "Open"), "source_close_raw": row.get(day + "Close"),
                "source_status": rule["status"], "numeric_scoring_included": known,
                "legacy_envelope_open": baseline_open, "legacy_envelope_close": baseline_close,
                "revised_open": rule.get("open_hour"), "revised_close": rule.get("close_hour"),
                "legacy_mean_endpoint_error_hours": old_error,
                "revised_mean_endpoint_error_hours": new_error})
    with (args.out / "calendar_source_reconstruction.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)

    village_path = EXTRA / "官方村界与人口" / "village_demographics_acs2018_2022.csv"
    district_path = EXTRA / "官方村界与人口" / "district_demographics_candidate_12.csv"
    villages, districts = read_csv(village_path), read_csv(district_path)
    population_total = sum(int(r["population"]) for r in villages)
    household_total = sum(int(r["households"]) for r in villages)
    assert len(villages) == len({r["village"] for r in villages}) == 15
    assert len(districts) == len({r["district_id"] for r in districts}) == 12
    assert population_total == 1620649 and household_total == 595336
    allocation_errors = []
    for row in districts:
        constituents = [v for v in villages if v["district_id"] == row["district_id"]]
        for field in ("population", "households", "age65plus_count"):
            error = int(row[field]) - sum(int(v[field]) for v in constituents)
            allocation_errors.append(error)
            assert error == 0
    assert all(not r["pct_no_vehicle"] for r in districts)
    summary = {
        "evidence_class": "real_source_reconstruction_and_input_quality_control",
        "not_service_outcome_empirical_validation": True,
        "source_scope": "MAG public-view snapshot 2026-11-18, posted 2026 season; HSD2024 report ACS2018-2022",
        "calendar": {"sites": len(rows), "site_weekday_cells": len(audit),
            "dates": ["2026-07-20", "2026-07-26"], "status_counts": status_counts,
            "numeric_known_clock_pairs": len(legacy_errors),
            "scoring_rule": "mean absolute open/close endpoint error; unknown hours excluded",
            "legacy_weekday_envelope_mae_hours": statistics.mean(legacy_errors),
            "revised_day_lookup_mae_hours": statistics.mean(corrected_errors),
            "raw_csv_weekday_cell_mismatches": len(source_mismatches),
            "independence_limit": "Both exports describe the same MAG response, not independent observations of actual opening."},
        "population": {"villages": len(villages), "contest_aggregated_districts": len(districts),
            "population": population_total, "households": household_total,
            "max_aggregation_count_error": max(abs(v) for v in allocation_errors),
            "no_vehicle_values_imputed": 0,
            "independence_limit": "Counts are report-derived input checks, not held-out prediction targets."},
        "service_outcome_validation": {"status": "NOT_AVAILABLE",
            "missing": ["district-day requested visits including turned-away demand", "actual site-day capacity and open hours", "matched observed travel itineraries"],
            "decision": "Restrict model outputs to conditional scenario comparisons; no measured coverage or deployment guarantee."},
        "input_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (MAG_CSV, raw_path, village_path, district_path)}
    }
    dump(args.out / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
