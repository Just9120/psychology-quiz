"""Create an ignored manual-handoff package without reading a transcript."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.practice_packages import load_case_package


def export(case_id: str, output: Path) -> dict:
    data = ROOT / "data"
    if data.is_symlink():
        raise ValueError("private_output_required")
    data.mkdir(exist_ok=True)
    if (output.is_symlink() or output.exists()
            or output.resolve(strict=False).parent != data.resolve(strict=True)):
        raise ValueError("new_private_output_required")
    package = load_case_package(case_id)
    output.mkdir(mode=0o700)
    documents = {"session.json": package, "client-role.json": package["client_role"],
                 "transcript-analysis.json": package["transcript_analysis"]}
    for name, value in documents.items():
        descriptor = os.open(output / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.write("\n")
    brief = package["student_brief"]
    descriptor = os.open(output / "student-brief.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(package["notice"] + "\n\n" + brief["situation"] + "\n\n" + brief["task"]
                   + "\n\n" + "\n".join(brief["constraints"]) + "\n")
    return {"files": 4, "case_fingerprint": package["case_fingerprint"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Export reviewed case for manual external-model practice")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = export(args.case_id, args.output)
    except (OSError, ValueError, TypeError, KeyError):
        print("PRACTICE_EXPORT_STOP: check case approval and unused private output; preserve partial output", file=sys.stderr)
        return 1
    print("PRACTICE_PACKAGE_READY " + json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
