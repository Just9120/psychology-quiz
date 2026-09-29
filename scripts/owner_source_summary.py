"""Create source-free owner aggregates from a complete private inventory."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.source_inventory import InventoryError
from scripts.source_inventory_report import _read, _snapshot, report, private_json_target


def build(current, processed, observed_at):
    observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed.tzinfo is None or observed > datetime.now(timezone.utc):
        raise ValueError("invalid_observation_time")
    value = report(current, processed=processed)
    files = _snapshot(current)["files"]
    records = {key: record for key, record in processed.items() if key in files}
    return {"schema_version": 1, "state": "PARTIAL",
            "captured_at": observed_at, "generated_at": datetime.now(timezone.utc).isoformat(),
            "files": value["files"], "folders": value["folders"],
            "processing": value["processing"], "processing_records": len(records),
            "known_holds": sum(record.get("review_state") == "conflict" or bool(record.get("conflict_hold"))
                               for record in records.values())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        target = private_json_target(args.output, ROOT)
        value = build(_read(args.current), _read(args.processed), args.observed_at)
        with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
    except (InventoryError, OSError, ValueError, TypeError) as error:
        print("OWNER_SUMMARY_STOP: " + (str(error) if isinstance(error, InventoryError) else type(error).__name__))
        return 1
    print("OWNER_SOURCE_SUMMARY_CREATED; counts only, supplied review snapshot remains partial")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
