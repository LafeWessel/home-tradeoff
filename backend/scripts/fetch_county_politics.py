#!/usr/bin/env python3
"""Generate county_politics.json from MIT Election Lab 2024 presidential returns.

Harvard Dataverse requires a one-time guestbook sign-in to download the raw file.
Two ways to run this script:

  Option A — provide a pre-downloaded file:
    cd backend && python -m scripts.fetch_county_politics /path/to/countypres_2000-2024.tab

  Option B — automated download (works if the dataset has no guestbook gate):
    cd backend && python -m scripts.fetch_county_politics

  To download the file manually:
    1. Open https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/VOQCHQ
    2. Click "Access Dataset" → fill in the guestbook (name / email / affiliation)
    3. Download countypres_2000-2024.tab
    4. Run:  python -m scripts.fetch_county_politics /path/to/countypres_2000-2024.tab

Output:
    app/sources/static/county_politics.json
    Keys: 5-digit county FIPS (e.g. "48453" = Travis County TX)
    Values: signed ppt margin — positive = Republican, negative = Democratic
"""

import csv
import io
import json
import sys
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent.parent / "app" / "sources" / "static"
OUT_FILE = STATIC_DIR / "county_politics.json"

DATAVERSE_DOI = "doi:10.7910/DVN/VOQCHQ"
DATAVERSE_META = (
    "https://dataverse.harvard.edu/api/datasets/:persistentId/"
    f"?persistentId={DATAVERSE_DOI}"
)
ELECTION_YEAR = 2024


def _read_local(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".tab":
        return "\t" + text
    return text


def _download() -> str:
    try:
        import requests
    except ImportError:
        sys.exit("Install requests: pip install requests")

    print("Fetching dataset metadata from Harvard Dataverse...", file=sys.stderr)
    r = requests.get(DATAVERSE_META, timeout=30)
    r.raise_for_status()
    files = r.json()["data"]["latestVersion"]["files"]

    csv_entry = next(
        (
            f
            for f in files
            if "county" in f["dataFile"]["filename"].lower()
            and f["dataFile"]["filename"].split(".")[-1] in ("csv", "tab")
        ),
        None,
    )
    if csv_entry is None:
        names = [f["dataFile"]["filename"] for f in files]
        sys.exit(f"Could not find county data file. Available files: {names}")

    file_id = csv_entry["dataFile"]["id"]
    filename = csv_entry["dataFile"]["filename"]
    dl_url = f"https://dataverse.harvard.edu/api/access/datafile/{file_id}?format=original"
    print(f"Downloading {filename} (id={file_id})...", file=sys.stderr)
    r = requests.get(dl_url, timeout=300, stream=True)

    if r.status_code == 400 and "Guestbook" in r.text:
        print(
            "\nERROR: This dataset requires a one-time guestbook sign-in.\n"
            "Please download the file manually:\n"
            "  1. Open: https://dataverse.harvard.edu/dataset.xhtml"
            "?persistentId=doi:10.7910/DVN/VOQCHQ\n"
            "  2. Click 'Access Dataset' and fill in the short guestbook form.\n"
            "  3. Download countypres_2000-2024.tab\n"
            "  4. Re-run: python -m scripts.fetch_county_politics "
            "/path/to/countypres_2000-2024.tab\n",
            file=sys.stderr,
        )
        sys.exit(1)

    r.raise_for_status()
    chunks = []
    for chunk in r.iter_content(chunk_size=1 << 20):
        chunks.append(chunk)
    text = b"".join(chunks).decode("utf-8", errors="replace")
    if filename.endswith(".tab"):
        return "\t" + text
    return text


def _compute_margins(raw: str, year: int) -> dict[str, float]:
    """Return {5-digit-fips: signed_margin_ppts} for presidential race in `year`."""
    delimiter = "\t" if raw.startswith("\t") else ","
    text = raw[1:] if delimiter == "\t" else raw
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    # Two-pass: collect all rows, then prefer TOTAL mode to avoid double-counting
    # subtotals (EARLY VOTING, ELECTION DAY, etc.) that are included in TOTAL.
    rows_by_county: dict[str, list[dict]] = {}
    for row in reader:
        try:
            row_year = int(row.get("year", 0))
        except ValueError:
            continue
        if row_year != year:
            continue
        office = row.get("office", "").upper()
        if office not in ("US PRESIDENT", "PRESIDENT"):
            continue
        fips_raw = row.get("county_fips", "")
        try:
            fips = str(int(fips_raw)).zfill(5)
        except (ValueError, TypeError):
            continue
        if fips.endswith("000"):  # state-total pseudo-rows
            continue
        rows_by_county.setdefault(fips, []).append(row)

    county: dict[str, dict[str, int]] = {}
    for fips, rows in rows_by_county.items():
        total_rows = [r for r in rows if r.get("mode", "").upper() == "TOTAL"]
        use = total_rows if total_rows else rows
        cc = county.setdefault(fips, {"R": 0, "D": 0, "TOTAL": 0})
        for row in use:
            party = row.get("party", "").upper()
            try:
                votes = int(row.get("candidatevotes") or 0)
            except ValueError:
                votes = 0
            try:
                total = int(row.get("totalvotes") or 0)
            except ValueError:
                total = 0
            if party == "REPUBLICAN":
                cc["R"] += votes
            elif party in ("DEMOCRAT", "DEMOCRATIC"):
                cc["D"] += votes
            cc["TOTAL"] = max(cc["TOTAL"], total)

    margins: dict[str, float] = {}
    for fips, v in county.items():
        total = v["TOTAL"] or (v["R"] + v["D"])
        if total == 0:
            continue
        margins[fips] = round((v["R"] - v["D"]) / total * 100, 1)
    return margins


def main() -> None:
    if len(sys.argv) >= 2:
        raw = _read_local(Path(sys.argv[1]))
    else:
        raw = _download()

    margins = _compute_margins(raw, ELECTION_YEAR)
    if not margins:
        sys.exit(
            f"No {ELECTION_YEAR} presidential data found. "
            "The dataset may not include that year yet."
        )

    out = {
        "_meta": {
            "source": "MIT Election Lab — County Presidential Election Returns",
            "source_year": ELECTION_YEAR,
            "notes": (
                "Signed two-party margin in percentage points: "
                "positive = Republican win, negative = Democratic win."
            ),
        },
        "data": dict(sorted(margins.items())),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Wrote {len(margins)} counties → {OUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
