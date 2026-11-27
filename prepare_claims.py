"""Run once, ahead of time. Applies the 90-day window rule to every credited and pending claim.

    python prepare_claims.py                  # reads data/expiry_claims.csv
    python prepare_claims.py path/to/file.csv

Writes data/claims_window_check.csv (one row per credited or pending claim).
The chat app never reads the raw claims file. Run this again only when a new claims register arrives.

Cleaning and choices made here:
  - exact duplicate rows are dropped (23 in the pack)
  - dates come in three formats; all are read
  - expiry comes from the batch master. If the batch is not in the master (policy archives batches
    from before October 2023) the register's own expiry is used only to flag the claim as
    'cannot_verify'. Those claims are escalated, never rejected.
  - breakage and short-supply claims are marked 'not_checked': the window rule does not apply to them
  - rejected claims are left out: nothing to recover or hold
  - value = credit value for credited claims, claimed value for pending claims (blank if the register has none)
"""
import csv
import sys
from pathlib import Path

from agent import rules

DATA = Path(__file__).resolve().parent / "data"
FIELDS = ["claim_no", "status", "stockist_code", "cnf_code", "batch_no", "claim_type", "claim_date",
          "expiry_date", "expiry_source", "days_from_expiry", "outcome", "code", "group", "value_inr", "reason"]


def money(text) -> float | None:
    """Rupees as a number. Blank stays blank: 8 pending claims have no claimed value and we do not invent one."""
    t = str(text or "").replace(",", "").strip()
    return float(t) if t else None


def build(claims_path: Path, batch_path: Path):
    with open(batch_path, newline="") as f:
        master = {r["batch_no"].strip().upper(): rules.parse_date(r["expiry_date"]) for r in csv.DictReader(f)}
    seen, out = set(), []
    read = dropped = 0
    with open(claims_path, newline="") as f:
        for row in csv.DictReader(f):
            read += 1
            key = tuple(row.values())
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
            if row["status"] not in ("Credited", "Pending"):
                continue
            claim_date = rules.parse_date(row["claim_date"])
            ctype = rules.normalise_claim_type(row["claim_type"])
            if claim_date is None:
                raise ValueError(f"Unreadable claim date: {row['claim_no']} {row['claim_date']!r}")
            batch = row["batch_no"].strip().upper()
            expiry, source = master.get(batch), "batch_master"
            if expiry is None:
                expiry, source = rules.parse_date(row["expiry_date_as_claimed"]), "register"
            res = rules.window_check(ctype, claim_date, expiry)
            if res["code"] == "NOT_COVERED":
                group = "not_checked"  # breakage and short supply: the window rule does not apply
            elif source == "register":
                group = "ok" if res["outcome"] == "pass" else "cannot_verify"
            else:
                group = "ok" if res["outcome"] == "pass" else rules.window_group(res["code"])
            value = money(row["credit_value_inr"]) if row["status"] == "Credited" else money(row["claim_value_inr"])
            out.append({
                "claim_no": row["claim_no"], "status": row["status"], "stockist_code": row["stockist_code"],
                "cnf_code": row["cnf_code"], "batch_no": batch, "claim_type": row["claim_type"],
                "claim_date": claim_date.isoformat(), "expiry_date": expiry.isoformat(), "expiry_source": source,
                "days_from_expiry": res["days_from_expiry"], "outcome": res["outcome"], "code": res["code"],
                "group": group, "value_inr": "" if value is None else round(value, 2), "reason": res["reason"],
            })
    return out, read, dropped


def main(src: Path) -> None:
    rows, read, dropped = build(src, DATA / "batch_master.csv")
    with open(DATA / "claims_window_check.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"Read {read} rows, dropped {dropped} exact duplicates, kept {len(rows)} credited or pending claims.")
    for g in ("firm", "confirm", "cannot_verify"):
        sel = [r for r in rows if r["group"] == g and r["status"] == "Credited"]
        print(f"  credited, {g}: {len(sel)} claims, INR {sum(r['value_inr'] or 0 for r in sel) / 1e5:.1f} lakh")
    hold = [r for r in rows if r["group"] not in ("ok", "not_checked") and r["status"] == "Pending"]
    print(f"  pending, to hold: {len(hold)} claims, INR {sum(r['value_inr'] or 0 for r in hold) / 1e5:.1f} lakh")
    print("Wrote data/claims_window_check.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA / "expiry_claims.csv")
