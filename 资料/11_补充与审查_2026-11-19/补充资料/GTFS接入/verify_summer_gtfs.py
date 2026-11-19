"""Inspect archived GTFS schedules without modifying model inputs (stdlib only).

python verify_summer_gtfs.py --repo REPO --out OUT --date 2026-07-20
Counts active trip records, not frequency-expanded vehicle departures.
"""
from pathlib import Path
import argparse
import csv
import datetime as dt
import hashlib
import io
import json
import zipfile

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
EXPECTED = ["mdb-147-202606160033", "mdb-147-202607280152"]
REFERENCE = "https://gtfs.org/documentation/schedule/reference/"


def rows(z, name):
    if name not in z.namelist():
        return
    with z.open(name) as raw:
        with io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
            yield from csv.DictReader(stream)


def seconds(value):
    if not value:
        return None
    h, m, s = map(int, value.split(":"))
    if h < 0 or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError(f"Invalid GTFS time: {value}")
    return h * 3600 + m * 60 + s


def active_services(calendar, exceptions, date):
    compact = date.strftime("%Y%m%d")
    active = {r["service_id"] for r in calendar
              if r["start_date"] <= compact <= r["end_date"]
              and r[WEEKDAYS[date.weekday()]] == "1"}
    day_exceptions = [r for r in exceptions if r["date"] == compact]
    for r in day_exceptions:
        if r["exception_type"] == "1":
            active.add(r["service_id"])
        elif r["exception_type"] == "2":
            active.discard(r["service_id"])
        else:
            raise ValueError("Unknown calendar exception type")
    return active, day_exceptions


def inspect(path, repo, date, provenance):
    with zipfile.ZipFile(path) as z:
        corrupt = z.testzip()
        if corrupt:
            raise ValueError(f"CRC failure in {corrupt}")
        small = {name: list(rows(z, name)) for name in
                 ["feed_info.txt", "agency.txt", "calendar.txt", "calendar_dates.txt",
                  "trips.txt", "routes.txt", "stops.txt", "frequencies.txt", "transfers.txt"]}
        calendar, exceptions = small["calendar.txt"], small["calendar_dates.txt"]
        if not calendar and not exceptions:
            raise ValueError("Both calendar and calendar_dates missing or empty")
        active, day_exceptions = active_services(calendar, exceptions, date)
        trips = small["trips.txt"]
        selected_trips = [r for r in trips if r["service_id"] in active]
        feed = small["feed_info.txt"]
        sample_date = date
        sample_services = active
        if not selected_trips:
            # Keep requested-date result zero; only the separately labelled example changes date.
            first_date = min([r["date"] for r in exceptions if r["exception_type"] == "1"]
                             + [r["start_date"] for r in calendar])
            sample_date = dt.datetime.strptime(first_date, "%Y%m%d").date()
            sample_services, _ = active_services(calendar, exceptions, sample_date)
        frequency_trip_ids = {r["trip_id"] for r in small["frequencies.txt"]}
        candidates = [r for r in trips if r["service_id"] in sample_services
                      and r["trip_id"] not in frequency_trip_ids]
        sample = sorted(candidates, key=lambda x: x["trip_id"])[0] if candidates else None
        sample_stop_times = []
        count, crossing_rows, active_crossing_rows = 0, 0, 0
        max_seconds = 0
        active_trip_ids = {r["trip_id"] for r in selected_trips}
        for r in rows(z, "stop_times.txt"):
            count += 1
            times = [seconds(r.get(k, "")) for k in ("arrival_time", "departure_time")]
            present = [x for x in times if x is not None]
            if present:
                max_seconds = max(max_seconds, max(present))
                if max(present) >= 86400:
                    crossing_rows += 1
                    active_crossing_rows += r["trip_id"] in active_trip_ids
            if sample and r["trip_id"] == sample["trip_id"]:
                sample_stop_times.append(r)
        record_counts = {}
        for name in z.namelist():
            if not name.endswith(".txt"):
                continue
            if name == "stop_times.txt":
                record_counts[name] = count
            elif name in small:
                record_counts[name] = len(small[name])
            else:
                record_counts[name] = sum(1 for _ in rows(z, name))
        example = None
        if sample and sample_stop_times:
            sample_stop_times.sort(key=lambda x: int(x["stop_sequence"]))
            stops = {r["stop_id"]: r for r in small["stops.txt"]}
            route = next(r for r in small["routes.txt"] if r["route_id"] == sample["route_id"])
            expanded = [{**r, "stop_name": stops[r["stop_id"]]["stop_name"],
                         "stop_lat": stops[r["stop_id"]]["stop_lat"],
                         "stop_lon": stops[r["stop_id"]]["stop_lon"]} for r in sample_stop_times]
            duration = seconds(expanded[-1]["arrival_time"]) - seconds(expanded[0]["departure_time"])
            if duration < 0:
                raise ValueError("Example arrival precedes departure")
            example = {"service_date": sample_date.isoformat(), "trip": sample,
                       "route": route, "is_frequency_template": False,
                       "first_stop": expanded[0], "last_stop": expanded[-1],
                       "scheduled_in_vehicle_minutes": duration / 60,
                       "stop_count": len(expanded), "stops": expanded,
                       "scope": "A published scheduled trip, not an observed journey or a full OD router"}
        relative = path.relative_to(repo).as_posix()
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        old = next((r for r in provenance if r.get("path") == relative), {})
        if old.get("sha256") and old["sha256"] != sha:
            raise ValueError("Archive differs from source manifest")
        service_dates = [r["date"] for r in exceptions]
        return {"archive": relative, "sha256": sha, "bytes": path.stat().st_size,
                "archive_url": old.get("url"), "producer_url": old.get("producer_url"),
                "crc_valid": True, "record_counts": record_counts, "feed_info": feed,
                "agency_timezones": sorted({r["agency_timezone"] for r in small["agency.txt"]}),
                "calendar_txt_present": "calendar.txt" in z.namelist(),
                "calendar_dates_min": min(service_dates) if service_dates else None,
                "calendar_dates_max": max(service_dates) if service_dates else None,
                "requested_date": date.isoformat(),
                "active_service_ids": sorted(active), "active_service_count": len(active),
                "date_exception_additions": sum(r["exception_type"] == "1" for r in day_exceptions),
                "date_exception_removals": sum(r["exception_type"] == "2" for r in day_exceptions),
                "active_trip_record_count": len(selected_trips),
                "active_frequency_trip_record_count": sum(r["trip_id"] in frequency_trip_ids for r in selected_trips),
                "frequency_records_total": len(small["frequencies.txt"]),
                "stop_times_rows_at_or_after_24h": crossing_rows,
                "active_trip_stop_times_rows_at_or_after_24h": active_crossing_rows,
                "maximum_service_day_seconds": max_seconds, "scheduled_trip_example": example}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--date", default="2026-07-20")
    a = ap.parse_args()
    repo = a.repo.resolve()
    root = repo / "资料/02_降温网络/GTFS"
    manifest = json.loads((root / "manifest_gtfs.json").read_text(encoding="utf-8-sig"))
    date = dt.date.fromisoformat(a.date)
    result = {"checked_date": "2026-11-19", "requested_service_date": a.date,
              "official_reference": REFERENCE,
              "model_inputs_modified": False,
              "counts_are_trip_records_not_frequency_expanded_departures": True,
              "archives": [inspect(root / name / (name + ".zip"), repo, date, manifest)
                           for name in EXPECTED]}
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "gtfs_schedule_validation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"archives": len(result["archives"]),
                      "active_trip_records": [r["active_trip_record_count"] for r in result["archives"]],
                      "output": "gtfs_schedule_validation.json"}))


if __name__ == "__main__":
    main()
