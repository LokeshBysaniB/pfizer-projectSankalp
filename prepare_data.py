"""Run once, ahead of time. Turns the raw sales file into two small tables the app reads.

    python prepare_data.py                  # reads data/primary_sales.csv
    python prepare_data.py path/to/file.csv

Writes data/scheme_by_quarter.csv and data/scheme_by_tier.csv.
The chat app never reads the raw file. Run this again only when new sales data arrives.

Cleaning done here:
  - exact duplicate rows are dropped
  - dates come in three formats (01-04-2024, 2024-04-01, 01-Apr-2024); all are read
  - each invoice is placed in its fiscal quarter (April to March, so Q3 FY25 = Oct to Dec 2024)
  - sales  = invoiced_qty x pts_inr   (billed packs, free packs excluded)
  - free   = free_qty x pts_inr       (free packs valued at PTS, as policy section 4.4 says)
"""
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y")


def parse_date(text: str) -> datetime:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Unreadable invoice date: {text!r}")


def fiscal_quarter(d: datetime) -> str:
    fy = d.year + 1 if d.month >= 4 else d.year
    q = ((d.month - 4) % 12) // 3 + 1
    return f"Q{q} FY{fy % 100:02d}"


def quarter_sort_key(label: str) -> tuple:
    q, fy = label.split()
    return int(fy[2:]), int(q[1])


def build(src: Path):
    seen, sales, free_by_tier = set(), defaultdict(float), defaultdict(float)
    kept = dropped = 0
    with open(src, newline="") as f:
        for row in csv.DictReader(f):
            key = tuple(row.values())
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            kept += 1
            quarter = fiscal_quarter(parse_date(row["invoice_date"]))
            pts = float(row["pts_inr"])
            sales[quarter] += float(row["invoiced_qty"]) * pts
            free_qty = float(row["free_qty"])
            if free_qty > 0:
                tier = (row.get("scheme_code") or "").strip()[-1:]
                if tier not in ("A", "B"):
                    raise ValueError(f"Free goods without a Tier A or B scheme code: {row['invoice_no']}")
                free_by_tier[(quarter, tier)] += free_qty * pts
    return sales, free_by_tier, kept, dropped


def main(src: Path) -> None:
    sales, free_by_tier, kept, dropped = build(src)
    quarters = sorted(sales, key=quarter_sort_key)
    with open(DATA / "scheme_by_quarter.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["quarter", "sales_inr", "free_inr"])
        for q in quarters:
            free = sum(v for (qq, _), v in free_by_tier.items() if qq == q)
            w.writerow([q, round(sales[q], 2), round(free, 2)])
    with open(DATA / "scheme_by_tier.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["quarter", "tier", "free_inr"])
        for (q, tier), v in sorted(free_by_tier.items(), key=lambda kv: (quarter_sort_key(kv[0][0]), kv[0][1])):
            w.writerow([q, tier, round(v, 2)])
    print(f"Read {kept + dropped} rows, dropped {dropped} exact duplicates, kept {kept}.")
    print(f"Wrote {len(quarters)} quarters to data/scheme_by_quarter.csv and data/scheme_by_tier.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "primary_sales.csv")
