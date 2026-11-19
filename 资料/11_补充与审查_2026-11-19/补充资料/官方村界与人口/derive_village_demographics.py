"""Extract published village counts; aggregate using the repository's explicit mapping.

Usage: python derive_village_demographics.py --source-dir PATH --repo PATH
Requires pypdf. Does not write model inputs. Ratios use their proper denominators.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import re
from pypdf import PdfReader


VILLAGES = ["Ahwatukee Foothills", "Alhambra", "Camelback East", "Central City",
            "Deer Valley", "Desert View", "Encanto", "Estrella", "Laveen", "Maryvale",
            "North Gateway", "North Mountain", "Paradise Valley", "Rio Vista", "South Mountain"]
BINS = [(0, 15000), (15000, 25000), (25000, 35000), (35000, 50000),
        (50000, 75000), (75000, 100000), (100000, None)]
LABELS = ["Less than $15,000", "$15,000 to $24,999", "$25,000 to $34,999",
          "$35,000 to $49,999", "$50,000 to $74,999", "$75,000 to $99,999",
          "$100,000 or more"]


def row(text, label):
    line = next(x for x in text.splitlines() if x.startswith(label + " "))
    values = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", line[len(label):])]
    if len(values) != 17:
        raise ValueError(f"Unexpected table layout for {label}: {len(values)} cells")
    return values


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def median_bin(counts):
    """A bracket and uniform-within-bracket interpolation, NEVER an observed median."""
    halfway, cumulative = sum(counts) / 2, 0
    for (lower, upper), count in zip(BINS, counts):
        if cumulative + count >= halfway:
            approximate = (lower + (upper - lower) * (halfway - cumulative) / count
                           if upper is not None and count else None)
            return lower, upper, approximate
        cumulative += count
    raise ValueError("Income bins have no positive total")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_dir
    pdf = root / "2024_HSD_Community_Assessment_Report_FINAL.pdf"
    reader = PdfReader(pdf)
    age, income = reader.pages[33].extract_text(), reader.pages[36].extract_text()
    populations = row(age, "Total Residents")
    households = row(age, "Total Households")
    older1, older2 = row(age, "65 to 74 years"), row(age, "75 years and over")
    bin_rows = [row(income, label) for label in LABELS]
    mapping_path = args.repo / "data/processed/districts.csv"
    with mapping_path.open(encoding="utf-8-sig", newline="") as stream:
        districts = list(csv.DictReader(stream))
    mapping = {}
    crosswalk = []
    for district in districts:
        for village in district["villages_mapped"].split(";"):
            village = village.strip()
            if village in mapping:
                raise ValueError(f"Village assigned twice: {village}")
            mapping[village] = district["district_id"]
            crosswalk.append({"village": village, "district_id": district["district_id"],
                              "mapping_status": "CONTEST_REPO_CHOICE_NOT_OFFICIAL"})
    assert set(mapping) == set(VILLAGES)
    village_rows = []
    for j, village in enumerate(VILLAGES, start=2):
        bins = [r[j] for r in bin_rows]
        lower, upper, estimate = median_bin(bins)
        village_rows.append({"village": village, "district_id": mapping[village],
                             "population": populations[j], "households": households[j],
                             "age65plus_count": older1[j] + older2[j],
                             "pct_65plus": (older1[j] + older2[j]) / populations[j],
                             **{f"income_bin_{k + 1}_households": v for k, v in enumerate(bins)},
                             "income_bin_sum_minus_published_households": sum(bins)-households[j],
                             "median_income_bracket_lower": lower,
                             "median_income_bracket_upper": upper,
                             "median_income_uniform_bin_proxy_usd": estimate,
                             "pct_no_vehicle": "", "no_vehicle_status": "NOT_IN_THIS_TABLE",
                             "source": "PHOENIX_HSD_2024_REPORT_ACS_2018_2022",
                             "source_pdf_pages": "34;37"})
    district_rows = []
    for district in districts:
        members = [x for x in village_rows if x["district_id"] == district["district_id"]]
        pop = sum(x["population"] for x in members)
        hh = sum(x["households"] for x in members)
        old = sum(x["age65plus_count"] for x in members)
        bins = [sum(x[f"income_bin_{k+1}_households"] for x in members) for k in range(7)]
        lower, upper, estimate = median_bin(bins)
        district_rows.append({"district_id": district["district_id"],
                              "district_name": district["district_name"],
                              "villages_mapped": "; ".join(x["village"] for x in members),
                              "population": pop, "households": hh,
                              "age65plus_count": old, "pct_65plus": old / pop,
                              **{f"income_bin_{k+1}_households": v for k, v in enumerate(bins)},
                              "income_bin_sum_minus_published_households": sum(bins)-hh,
                              "median_income_bracket_lower": lower,
                              "median_income_bracket_upper": upper,
                              "median_income_uniform_bin_proxy_usd": estimate,
                              "pct_no_vehicle": "", "no_vehicle_status": "NOT_IN_THIS_TABLE",
                              "source": "DERIVED_COUNTS_FROM_HSD_2024_ACS_2018_2022",
                              "mapping_status": "CONTEST_REPO_CHOICE_NOT_OFFICIAL"})
    write_csv(root / "village_demographics_acs2018_2022.csv", village_rows)
    write_csv(root / "district_demographics_candidate_12.csv", district_rows)
    write_csv(root / "village_to_contest_district.csv", crosswalk)
    validation = {"source_pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                  "mapping_csv_sha256": hashlib.sha256(mapping_path.read_bytes()).hexdigest(),
                  "source_acs_period": "2018-2022", "source_report_year": 2024,
                  "source_pdf_page_age": 34, "source_pdf_page_income": 37,
                  "village_count": len(village_rows), "district_count": len(district_rows),
                  "mapping_unique_and_exhaustive": True,
                  "village_population_sum": sum(populations[2:]),
                  "report_phoenix_population": populations[1],
                  "village_households_sum": sum(households[2:]),
                  "report_phoenix_households": households[1],
                  "source_totals_need_not_exactly_sum": True,
                  "no_vehicle_missing_not_imputed": True,
                  "income_median_is_interpolation_proxy": True,
                  "model_inputs_changed": False}
    (root / "derived_validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(validation, ensure_ascii=True))


if __name__ == "__main__":
    main()
