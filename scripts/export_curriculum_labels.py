"""Export source-free navigation labels after validating the current private source graph."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.curriculum import merge_public_labels
from app.source_inventory import combine_registries, reviewed_graph
from scripts.source_inventory_report import (
    _snapshot, combine_private_topics, private_registry_input, private_topics_input,
)


def project_labels(curriculum, private, registry, snapshot):
    combined = combine_private_topics(curriculum, private, registry)
    graph = reviewed_graph(snapshot, registry, combined)
    if (graph["source_metadata"].get("current", 0) != graph["tracked_sources"]
            or graph["lesson_metadata"].get("current", 0) != len(combined["topics"])):
        raise ValueError("Current source graph required for curriculum labels")
    modules = {}
    by_id = {source["id"]: source for source in registry["sources"]}
    for topic in combined["topics"].values():
        path = by_id[topic["source"]["source_id"]]["corpus_path"]
        match = re.match(r"Модуль ([1-6])(?:[. /]|$)", path)
        if match:
            modules.setdefault(topic["discipline_id"], set()).add("module" + match[1])
    labels = {"schema_version": 1, "disciplines": {}, "topics": {}}
    for key, value in combined["disciplines"].items():
        candidates = modules.get(key, set())
        ordered = sorted(candidates)
        labels["disciplines"][key] = {"title": value["title"],
            "module": ordered[0] if len(ordered) == 1 else None, "modules": ordered}
    for key, value in private["topics"].items():
        labels["topics"][key] = {field: value[field] for field in ("title", "discipline_id")}
    encoded = json.dumps(labels, ensure_ascii=False)
    if any(source_id in encoded for source_id in by_id if len(source_id) >= 20):
        raise ValueError("Private source identifier in curriculum labels")
    merge_public_labels(curriculum, labels)
    return labels


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--private-registry", type=Path, required=True)
    parser.add_argument("--private-topics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    private_registry = private_registry_input(args.private_registry, ROOT)
    registry = combine_registries(read(ROOT / "content/source-corpus.json"), private_registry)
    labels = project_labels(read(ROOT / "content/curriculum.json"),
        private_topics_input(args.private_topics, ROOT), registry, _snapshot(read(args.current)))
    args.output.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"CURRICULUM_LABELS_OK disciplines={len(labels['disciplines'])} topics={len(labels['topics'])}")


if __name__ == "__main__":
    main()
