"""Pull section titles (and order, where it applies) from the Comedy Database sheet.

Reads the Sections columns of the 'Sections & Tags' tab, published as CSV.
Each site takes only its own section_keys; other rows are skipped.

    python3 sync_sections.py <directory|guide> <csv-url-or-local-file>
    (or set SECTIONS_CSV_URL and pass only the site name)

On a bad read or bad rows, the existing sections file is kept and the script
exits non-zero so the scheduled run fails visibly.
"""
import csv, io, json, os, pathlib, re, sys, urllib.request

ROOT = pathlib.Path.cwd()  # the repo the script is run from
SITES = {
    "directory": {"keys": {"venue", "show", "openmic", "classes", "podcast", "festival", "performer", "resource"},
                  "order_editable": True},
    "guide": {"keys": {"thisweek", "nextweek", "furtherout", "unconfirmed"},
              "order_editable": False},  # Guide order follows the calendar
}
ALL_KEYS = set().union(*(s["keys"] for s in SITES.values()))


def fetch(source):
    if source.startswith("http"):
        with urllib.request.urlopen(source, timeout=30) as r:
            return r.read().decode("utf-8")
    return pathlib.Path(source).read_text(encoding="utf-8")


def parse(text, site):
    cfg = SITES[site]
    rows = list(csv.DictReader(io.StringIO(text)))
    sections, seen = [], set()
    for n, row in enumerate(rows, 2):  # row 1 is the header
        key = re.sub(r"\s+", "", (row.get("section_key") or "").lower())  # "this week" -> "thisweek"
        if not key:
            continue  # blank rows below the table are fine
        if key not in ALL_KEYS:
            raise ValueError(f"row {n}: unknown section_key '{key}'. section_key is an internal ID "
                             "and must not be renamed. Change the title instead.")
        if key not in cfg["keys"]:
            continue  # belongs to the other site
        if key in seen:
            raise ValueError(f"row {n}: duplicate section_key '{key}'")
        seen.add(key)
        title = (row.get("title") or "").strip()
        if not title:
            raise ValueError(f"row {n}: title is empty")
        try:
            order = int((row.get("display_order") or "").strip())
        except ValueError:
            raise ValueError(f"row {n}: display_order must be a whole number")
        active = (row.get("active") or "Y").strip().upper() != "N"
        sections.append({"key": key, "order": order, "title": title, "active": active})
    if not sections:
        raise ValueError(f"no {site} sections found in the sheet")
    if not any(s["active"] for s in sections):
        raise ValueError("no active sections")
    return sorted(sections, key=lambda s: s["order"])


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in SITES:
        sys.exit("Usage: sync_sections.py <directory|guide> [csv-url-or-file]")
    site = sys.argv[1]
    source = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("SECTIONS_CSV_URL", "")
    if not source:
        sys.exit("No source: pass a CSV URL/path or set SECTIONS_CSV_URL.")
    try:
        sections = parse(fetch(source), site)
    except Exception as exc:
        sys.exit(f"Sections sync failed; sections.json left as-is. {exc}")
    out = ROOT / "sections.json"
    out.write_text(json.dumps(sections, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(sections)} {site} sections to {out.name}")


if __name__ == "__main__":
    main()
