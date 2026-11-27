"""Golden checks from check_set.csv. Deterministic tool outputs only — no API key."""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent import claims, tools

CHECKS = ROOT / "checks" / "check_set.csv"

TOOL_MAP = {
    "scheme_quarter": lambda a: tools.scheme_quarter(a["period"]),
    "scheme_summary": lambda a: tools.scheme_summary(),
    "window_summary": lambda a: claims.window_summary(),
    "check_claim": lambda a: claims.check_claim(a["batch_no"], a["claim_date"], a["claim_type"]),
    "assess_requests": lambda a: tools.assess_requests(a.get("requests", []), a.get("period")),
}


def get_path(obj: dict, dotted: str):
    for part in dotted.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj


def coerce(expected: str, actual):
    if actual is None:
        return False
    if expected.lower() in ("true", "false"):
        return actual == (expected.lower() == "true")
    try:
        if isinstance(actual, float) and "." in expected:
            return round(actual, 2) == round(float(expected), 2)
        if isinstance(actual, (int, float)) and "." not in expected:
            return actual == int(expected) if "." not in str(expected) else actual == float(expected)
    except ValueError:
        pass
    return str(actual) == expected


def main() -> int:
    failed = 0
    with open(CHECKS, newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        tool = row["tool"]
        args = json.loads(row["args_json"]) if row["args_json"].strip() else {}
        field = row["assert_field"]
        expected = row["assert_value"]
        fn = TOOL_MAP.get(tool)
        if fn is None:
            print(f"FAIL {row['check_id']}: unknown tool {tool!r}")
            failed += 1
            continue
        result = fn(args)
        actual = get_path(result, field) if "." in field else result.get(field)
        if not coerce(expected, actual):
            print(f"FAIL {row['check_id']} ({row.get('notes', '')}): {field}={actual!r}, want {expected!r}")
            failed += 1
        else:
            print(f"ok   {row['check_id']}: {field}={actual!r}")
    print(f"\n{len(rows) - failed}/{len(rows)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())