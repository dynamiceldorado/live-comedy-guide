"""Turn the Comedy Database 'Events' tab (CSV pushed by the sheet's robot) into data/events.json.

    python3 sheet_to_events.py data/sheet/events.csv

Only public columns are kept. Rows that are rejected, cancelled or past are left out.
On a bad read or bad rows, events.json is left as-is and the script exits non-zero.
"""
import csv, json, pathlib, re, sys

ROOT = pathlib.Path.cwd()
KEYS = ["id", "status", "view", "cheap_date", "type", "genre", "tier", "title", "start_date", "end_date",
        "date_text", "time", "sort_time", "venue", "area", "price_text", "link", "link_label",
        "description", "image_url", "ded_pick", "pick_note"]
STATUSES = {"verified", "unconfirmed", "cancelled", "past", "rejected"}
VIEWS = {"Public", "Comics", "Performers", "Both"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: sheet_to_events.py <events.csv>")
    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
    out, seen = [], set()
    for n, r in enumerate(rows, 2):
        r = {(k or "").strip(): (v or "").strip() for k, v in r.items()}
        if not r.get("id"):
            continue
        if r["id"] in seen:
            sys.exit(f"Events sync failed; events.json left as-is. row {n}: duplicate id {r['id']}")
        seen.add(r["id"])
        st = r.get("status", "").lower()
        if st not in STATUSES:
            sys.exit(f"Events sync failed; events.json left as-is. row {n} ({r['id']}): unknown status '{r.get('status')}'")
        if st not in ("verified", "unconfirmed"):
            continue
        if r.get("view") not in VIEWS:
            sys.exit(f"Events sync failed; events.json left as-is. row {n} ({r['id']}): unknown view '{r.get('view')}'")
        for k in ("start_date", "end_date"):
            if r.get(k) and not DATE.match(r[k]):
                sys.exit(f"Events sync failed; events.json left as-is. row {n} ({r['id']}): {k} must look like 2026-11-20")
        if not r.get("start_date"):
            sys.exit(f"Events sync failed; events.json left as-is. row {n} ({r['id']}): start_date is empty")
        e = {k: r.get(k, "") for k in KEYS}
        e["status"] = st
        out.append(e)
    if not out:
        sys.exit("Events sync failed; events.json left as-is. No publishable rows found.")
    (ROOT / "data" / "events.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Wrote {len(out)} events to data/events.json")


if __name__ == "__main__":
    main()
