"""Follow-up robot (scheduled RPA)."""
from __future__ import annotations

import argparse
import csv
import html
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clearpath import config, db, nlp, routing, service  # noqa: E402


def report_by_agency(con) -> tuple[Path, Path]:
    config.ensure_dirs()
    today = db.now().date().isoformat()
    rows = [dict(r) for r in con.execute(
        "SELECT protocol, created_at, category, priority, status, deadline, agency, address FROM reports "
        "WHERE status != 'resolved' ORDER BY agency, CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 "
        "WHEN 'medium' THEN 2 ELSE 3 END, deadline")]
    now = db.iso()
    for r in rows:
        r["overdue"] = "yes" if r["deadline"] < now and r["status"] in ("forwarded", "in_progress", "escalated") else "no"
        r["category"] = nlp.CATEGORIES[r["category"]]

    csv_file = config.REPORTS_DIR / f"pending_{today}.csv"
    with csv_file.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["protocol"])
        w.writeheader()
        w.writerows(rows)

    by_agency = defaultdict(list)
    for r in rows:
        by_agency[r["agency"]].append(r)
    parts = [f"<h1>ClearPath: pending reports on {today}</h1><p>{len(rows)} open reports.</p>"]
    for agency, items in by_agency.items():
        overdue = sum(1 for i in items if i["overdue"] == "yes")
        parts.append(f"<h2>{html.escape(agency)}: {len(items)} pending, {overdue} overdue</h2><table border=1 cellpadding=4>"
                     "<tr><th>Protocol</th><th>Category</th><th>Priority</th><th>Status</th><th>Deadline</th><th>Address</th></tr>")
        for i in items:
            parts.append(f"<tr><td>{i['protocol']}</td><td>{html.escape(i['category'])}</td><td>{i['priority']}</td>"
                         f"<td>{i['status']}</td><td>{i['deadline'][:10]}</td><td>{html.escape(i['address'] or '-')}</td></tr>")
        parts.append("</table>")
    html_file = config.REPORTS_DIR / f"pending_{today}.html"
    html_file.write_text("<meta charset='utf-8'>" + "".join(parts), encoding="utf-8")
    return csv_file, html_file


def run_once(con) -> dict:
    escalated = routing.escalate_overdue(con)
    photos_deleted = service.apply_retention(con)
    csv_file, html_file = report_by_agency(con)
    return {"escalated": escalated, "photos_deleted": photos_deleted, "csv": str(csv_file), "html": str(html_file)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--loop", type=int, default=0, help="interval in seconds (0 = run once)")
    args = p.parse_args()
    con = db.connect()
    while True:
        res = run_once(con)
        print(f"[{db.iso()}] escalated: {len(res['escalated'])} | photos deleted (retention): "
              f"{len(res['photos_deleted'])} | report: {res['html']}")
        if not args.loop:
            break
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
