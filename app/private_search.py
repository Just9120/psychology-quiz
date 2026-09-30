"""Operator-only, rebuildable retrieval over reviewed private source extracts.

There is deliberately no HTTP or Telegram entrypoint. Source text and indexes
live in a separate PostgreSQL schema; public learning tables are read-only to
this tool. The caller supplies a private manifest and an explicit actor role.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from time import monotonic, process_time

import psycopg

from app.postgres_config import validate_delivery_target
from app.source_inventory import (InventoryError, combine_registries,
                                  unresolved_related_conflicts, valid_review_timestamp)
from app.private_rag import RagError


MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MODEL_REPOSITORY = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
MODEL_REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
MODEL_FILES = ("config.json", "model_optimized.onnx", "special_tokens_map.json",
               "tokenizer.json", "tokenizer_config.json")
FASTEMBED_VERSION = "0.8.0"
MODEL_IDENTITY = f"{MODEL}@{MODEL_REVISION}:fastembed-{FASTEMBED_VERSION}:mean-pooling"
INDEX_VERSION = "private-search-v2"
DIMENSIONS = 384
PRIVATE_ROOT = Path("/data/search-input")
CORPUS = Path(__file__).resolve().parents[1] / "content/source-corpus.json"
# This model's default tokenizer window is short. Keep Cyrillic chunks well
# below that window so the referenced tail is not routinely absent from the
# semantic vector; exact token coverage is still checked in retrieval QA.
MAX_CHARS = 160
OVERLAP = 32
MAX_QUERY = 500
MAX_RESULTS = 20
MAX_QA_CASES = 20
READ_STATEMENT_TIMEOUT_SECONDS = 30
REBUILD_STATEMENT_TIMEOUT_SECONDS = 600
MAX_REBUILD_STATEMENT_TIMEOUT_SECONDS = 3600
SOURCE_ID = re.compile(r"^[A-Za-z0-9_-]{20,}$")
NOTE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SearchError(ValueError):
    pass


def statement_timeout_seconds(action: str, requested: int | None) -> int:
    """Keep reads short while allowing a bounded operator rebuild window."""
    if action != "rebuild":
        if requested is not None:
            raise SearchError("rebuild_timeout_only")
        return READ_STATEMENT_TIMEOUT_SECONDS
    if requested is None:
        return REBUILD_STATEMENT_TIMEOUT_SECONDS
    if (type(requested) is not int
            or not READ_STATEMENT_TIMEOUT_SECONDS <= requested <= MAX_REBUILD_STATEMENT_TIMEOUT_SECONDS):
        raise SearchError("invalid_rebuild_timeout")
    return requested


def private_file(path: Path, root: Path) -> bytes:
    root = root.resolve(strict=True)
    if path.is_absolute() or ".." in path.parts or (root / path).is_symlink():
        raise SearchError("private_path_required")
    candidate = (root / path).resolve(strict=True)
    if not candidate.is_relative_to(root):
        raise SearchError("private_path_required")
    info = candidate.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > 20_000_000 or info.st_size == 0:
        raise SearchError("private_regular_file_required")
    return candidate.read_bytes()


def chunks(text: str):
    """Bound context by characters because the configured model truncates input."""
    start = 0
    while start < len(text):
        end = min(start + MAX_CHARS, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + MAX_CHARS // 2, end)
            if boundary > start:
                end = boundary
        segment = text[start:end]
        piece = segment.strip()
        if piece:
            left = len(segment) - len(segment.lstrip())
            right = len(segment) - len(segment.rstrip())
            yield start + left, end - right, piece
        if end == len(text):
            break
        start = max(start + 1, end - OVERLAP)


def reviewed_chunks(manifest: dict, corpus: dict, root: Path, reviews: dict | None = None):
    if (manifest.get("schema_version") != 1 or not isinstance(manifest.get("sources"), list)
            or not isinstance(manifest.get("notes", []), list)):
        raise SearchError("invalid_private_manifest")
    reviewed = {item["id"]: item for item in corpus["sources"]
                if item.get("kind") == "learning_material" and item.get("readable") is True}
    if manifest["sources"] and not isinstance(reviews, dict):
        raise SearchError("private_source_review_required")
    if reviews is not None:
        try:
            held_sources = unresolved_related_conflicts(reviews)
        except InventoryError as error:
            raise SearchError("invalid_private_source_reviews") from error
    else:
        held_sources = set()
    seen = set()
    result = []
    for item in manifest["sources"]:
        if not isinstance(item, dict):
            raise SearchError("invalid_private_manifest")
        source_id = item.get("source_id")
        if (not isinstance(source_id, str) or not SOURCE_ID.fullmatch(source_id)
                or source_id in seen or source_id not in reviewed):
            raise SearchError("unreviewed_or_duplicate_source")
        if source_id in held_sources:
            raise SearchError("unresolved_related_source_conflict")
        seen.add(source_id)
        source = reviewed[source_id]
        review = reviews.get(source_id)
        if (not isinstance(review, dict)
                or review.get("review_state") != "processed"
                or review.get("source_kind", source["kind"]) != source["kind"]
                or not isinstance(review.get("revision"), list)
                or len(review["revision"]) != 3
                or review["revision"][0] != source.get("modified_time")
                or review["revision"][1] != source.get("title")
                or not isinstance(review["revision"][2], str)
                or not review["revision"][2].strip()
                or review.get("snapshot_sha256") != source.get("snapshot_sha256")
                or review.get("snapshot_kind") != "extracted_text"
                or not all(isinstance(review.get(field), str) and review[field].strip()
                           for field in ("reviewer", "review_note"))
                or not valid_review_timestamp(review.get("reviewed_at"))):
            raise SearchError("private_source_review_incomplete")
        if (source.get("snapshot_kind") != "extracted_text"
                or item.get("modified_time") != source.get("modified_time")
                or item.get("snapshot_sha256") != source.get("snapshot_sha256")
                or not isinstance(item.get("text_path"), str)):
            raise SearchError("source_revision_not_reviewed")
        raw = private_file(Path(item["text_path"]), root)
        if hashlib.sha256(raw).hexdigest() != source["snapshot_sha256"]:
            raise SearchError("private_extract_fingerprint_changed")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as error:
            raise SearchError("invalid_source_text") from error
        ranges = review.get("search_ranges")
        if (not isinstance(ranges, list) or not ranges or len(ranges) > 100
                or not isinstance(review.get("search_review_note"), str)
                or not review["search_review_note"].strip()
                or not isinstance(review.get("search_reviewer"), str)
                or not review["search_reviewer"].strip()
                or not valid_review_timestamp(review.get("search_reviewed_at"))):
            raise SearchError("private_search_passages_not_reviewed")
        previous_end = 0
        for bounds in ranges:
            if (not isinstance(bounds, list) or len(bounds) != 2
                    or any(type(value) is not int for value in bounds)
                    or not 0 <= bounds[0] < bounds[1] <= len(text)
                    or bounds[0] < previous_end or not text[bounds[0]:bounds[1]].strip()):
                raise SearchError("invalid_private_search_ranges")
            previous_end = bounds[1]
            result.extend((source_id, source["modified_time"], source["snapshot_sha256"],
                           f"characters:{bounds[0] + start}:{bounds[0] + end}", piece)
                          for start, end, piece in chunks(text[bounds[0]:bounds[1]]))
    for item in manifest.get("notes", []):
        if not isinstance(item, dict):
            raise SearchError("invalid_private_note")
        note_id = item.get("note_id")
        digest = item.get("snapshot_sha256")
        modified = item.get("modified_time")
        if (not isinstance(note_id, str) or not NOTE_ID.fullmatch(note_id)
                or f"note:{note_id}" in seen or not isinstance(digest, str)
                or not SHA256.fullmatch(digest) or not isinstance(modified, str)
                or not modified.strip() or len(modified) > 64
                or not isinstance(item.get("text_path"), str)):
            raise SearchError("invalid_private_note")
        seen.add(f"note:{note_id}")
        raw = private_file(Path(item["text_path"]), root)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise SearchError("private_note_fingerprint_changed")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as error:
            raise SearchError("invalid_private_note_text") from error
        result.extend((f"note:{note_id}", modified, digest,
                       f"characters:{start}:{end}", piece)
                      for start, end, piece in chunks(text))
    if not result:
        raise SearchError("no_reviewed_search_text")
    return result


def load_private_chunks(manifest_path: Path):
    try:
        relative = manifest_path.resolve(strict=True).relative_to(PRIVATE_ROOT.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise SearchError("private_manifest_required") from error
    manifest = json.loads(private_file(relative, PRIVATE_ROOT))
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    if isinstance(manifest, dict) and manifest.get("private_registry_path") is not None:
        private_path = manifest["private_registry_path"]
        if not isinstance(private_path, str) or not private_path:
            raise SearchError("private_registry_path_required")
        try:
            private_registry = json.loads(private_file(Path(private_path), PRIVATE_ROOT))
            corpus = combine_registries(corpus, private_registry)
        except (InventoryError, json.JSONDecodeError, UnicodeError) as error:
            raise SearchError("invalid_private_source_registry") from error
    reviews = None
    if isinstance(manifest, dict) and manifest.get("sources"):
        review_path = manifest.get("processing_path")
        if not isinstance(review_path, str) or not review_path:
            raise SearchError("private_source_review_required")
        reviews = json.loads(private_file(Path(review_path), PRIVATE_ROOT))
    return reviewed_chunks(manifest, corpus, PRIVATE_ROOT, reviews)


def capacity_estimate(source_chunks):
    """Lower bounds only: no HNSW, text-index, model-cache or backup overhead."""
    return {"sources": len({item[0] for item in source_chunks}),
            "chunks": len(source_chunks),
            "text_utf8_bytes": sum(len(item[4].encode("utf-8")) for item in source_chunks),
            "raw_vector_bytes": len(source_chunks) * DIMENSIONS * 4}


def verify_private_schema(conn, *, owner="psychology_app"):
    row = conn.execute("""SELECT e.extversion,n.nspname FROM pg_extension e
        JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'""").fetchone()
    if row is None or row[0] != "0.8.6" or row[1] != "private_search":
        raise SearchError("private_pgvector_extension_required")
    row = conn.execute("""SELECT pg_get_userbyid(nspowner) FROM pg_namespace
        WHERE nspname='private_search'""").fetchone()
    if row is None or row[0] != owner:
        raise SearchError("private_search_schema_owner_required")


def ensure_index(conn, *, owner="psychology_app", create=False):
    verify_private_schema(conn, owner=owner)
    relations = conn.execute("""SELECT c.relname,c.relkind,pg_get_userbyid(c.relowner)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='private_search' AND c.relkind IN ('r','p','i')""").fetchall()
    if relations:
        expected = {"chunks", "chunks_pkey", "private_search_terms",
                    "private_search_vectors", "index_meta", "index_meta_pkey"}
        if {row[0] for row in relations} != expected or any(row[2] != owner for row in relations):
            raise SearchError("private_search_relation_drift")
        marker = conn.execute("""SELECT version,model_name,dimensions FROM private_search.index_meta
            WHERE singleton=true""").fetchone()
        if marker != (INDEX_VERSION, MODEL_IDENTITY, DIMENSIONS):
            raise SearchError("private_search_index_drift")
        return
    if not create:
        raise SearchError("private_search_index_missing")
    conn.execute("""CREATE TABLE private_search.chunks (
        source_id text NOT NULL, modified_time text NOT NULL,
        snapshot_sha256 text NOT NULL, locator text NOT NULL,
        content text NOT NULL, embedding private_search.vector(384) NOT NULL,
        search_text tsvector GENERATED ALWAYS AS (to_tsvector('russian',content)) STORED,
        PRIMARY KEY(source_id,snapshot_sha256,locator)
    )""")
    conn.execute("""CREATE INDEX private_search_terms
        ON private_search.chunks USING gin(search_text)""")
    conn.execute("""CREATE INDEX private_search_vectors
        ON private_search.chunks USING hnsw(embedding private_search.vector_cosine_ops)""")
    conn.execute("""CREATE TABLE private_search.index_meta (
        singleton boolean PRIMARY KEY CHECK(singleton=true),
        version text NOT NULL, model_name text NOT NULL, dimensions integer NOT NULL,
        source_count integer NOT NULL, chunk_count integer NOT NULL
    )""")
    conn.execute("INSERT INTO private_search.index_meta VALUES(true,%s,%s,%s,0,0)",
                 (INDEX_VERSION, MODEL_IDENTITY, DIMENSIONS))


def embedder():
    try:
        from importlib.metadata import version
        from fastembed import TextEmbedding
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise SearchError("local_embedding_dependency_required") from error
    if version("fastembed") != FASTEMBED_VERSION:
        raise SearchError("embedding_runtime_version_changed")
    cache = os.environ.get("SEARCH_MODEL_CACHE", "/data/search-model-cache")
    try:
        # FastEmbed's named model otherwise follows the latest Hub revision.
        # Pin both the ONNX/tokenizer bytes and pooling implementation used by
        # stored vectors; a later change requires a deliberate index rebuild.
        try:
            path = snapshot_download(repo_id=MODEL_REPOSITORY, revision=MODEL_REVISION,
                                     allow_patterns=MODEL_FILES, cache_dir=cache,
                                     local_files_only=True)
        except Exception:
            path = snapshot_download(repo_id=MODEL_REPOSITORY, revision=MODEL_REVISION,
                                     allow_patterns=MODEL_FILES, cache_dir=cache)
    except Exception as error:
        raise SearchError("pinned_embedding_unavailable") from error
    if any(not (Path(path) / filename).is_file() for filename in MODEL_FILES):
        raise SearchError("pinned_embedding_incomplete")
    return TextEmbedding(model_name=MODEL, cache_dir=cache,
                         specific_model_path=path, local_files_only=True)


def process_peak_rss_bytes():
    """Process-lifetime high-water mark; unavailable platforms return unknown."""
    try:
        import resource
    except ImportError:
        return None
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes. Do not guess other OS units.
    if sys.platform.startswith("linux"):
        return int(usage * 1024)
    if sys.platform == "darwin":
        return int(usage)
    return None


def model_probe():
    """Measure local embedding startup without reading sources or connecting to DB."""
    started = monotonic()
    cpu_started = process_time()
    vector = list(embedder().embed(["проверка поиска по учебному материалу"]))
    if len(vector) != 1:
        raise SearchError("incomplete_probe_embedding")
    vector_text(vector[0])
    cache = Path(os.environ.get("SEARCH_MODEL_CACHE", "/data/search-model-cache"))
    cache_bytes = sum(path.stat().st_size for path in cache.rglob("*")
                      if path.is_file() and not path.is_symlink()) if cache.is_dir() else 0
    return {"model": MODEL_IDENTITY, "dimensions": DIMENSIONS,
            "elapsed_ms": round((monotonic() - started) * 1000), "cache_bytes": cache_bytes,
            "process_cpu_ms": round((process_time() - cpu_started) * 1000),
            "process_peak_rss_bytes": process_peak_rss_bytes()}


def vector_text(value):
    numbers = [float(number) for number in value]
    if len(numbers) != DIMENSIONS or any(not -1e6 < number < 1e6 for number in numbers):
        raise SearchError("invalid_embedding_dimensions")
    if not any(numbers):
        # Cosine distance is undefined for a zero vector; otherwise a broken
        # model could make arbitrary passages look like search results.
        raise SearchError("zero_embedding_not_searchable")
    return "[" + ",".join(format(number, ".9g") for number in numbers) + "]"


def rebuild(conn, source_chunks, model, *, owner="psychology_app"):
    """Atomically replace only the derivative; never touch source/user tables."""
    verify_private_schema(conn, owner=owner)
    with conn.transaction():
        # Serialize operator rebuilds. Without this, two concurrent DELETE / INSERT
        # cycles can interleave and leave an index assembled from both inputs.
        lock_key = int.from_bytes(hashlib.sha256(b"psychology:private_search_rebuild").digest()[:8],
                                  signed=True)
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
        ensure_index(conn, owner=owner, create=True)
        conn.execute("DELETE FROM private_search.chunks")
        with conn.cursor() as cursor:
            for offset in range(0, len(source_chunks), 32):
                batch = source_chunks[offset:offset + 32]
                vectors = list(model.embed([item[4] for item in batch]))
                if len(vectors) != len(batch):
                    raise SearchError("incomplete_embeddings")
                prepared = [(*item, vector_text(vector)) for item, vector in zip(batch, vectors)]
                cursor.executemany("""INSERT INTO private_search.chunks
                    (source_id,modified_time,snapshot_sha256,locator,content,embedding)
                    VALUES(%s,%s,%s,%s,%s,%s::private_search.vector)""", prepared)
        count = conn.execute("SELECT count(*) FROM private_search.chunks").fetchone()[0]
        if count != len(source_chunks):
            raise SearchError("incomplete_private_rebuild")
        conn.execute("""UPDATE private_search.index_meta SET source_count=%s,chunk_count=%s
            WHERE singleton=true""", (len({item[0] for item in source_chunks}), count))
    return count


def search(conn, query: str, model, *, limit: int = 5, owner="psychology_app"):
    ensure_index(conn, owner=owner)
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY:
        raise SearchError("invalid_search_query")
    if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
        raise SearchError("invalid_search_limit")
    query_vectors = list(model.embed([query]))
    if len(query_vectors) != 1:
        raise SearchError("incomplete_query_embedding")
    vector = vector_text(query_vectors[0])
    lexical = conn.execute("""SELECT source_id,modified_time,snapshot_sha256,locator,content,
        ts_rank_cd(search_text,plainto_tsquery('russian',%s)) AS score
        FROM private_search.chunks
        WHERE search_text @@ plainto_tsquery('russian',%s)
        ORDER BY score DESC,source_id,locator LIMIT %s""", (query, query, MAX_RESULTS)).fetchall()
    semantic = conn.execute("""SELECT source_id,modified_time,snapshot_sha256,locator,content,
        1-(embedding OPERATOR(private_search.<=>) %s::private_search.vector) AS score
        FROM private_search.chunks
        ORDER BY embedding OPERATOR(private_search.<=>) %s::private_search.vector,source_id,locator LIMIT %s""",
        (vector, vector, MAX_RESULTS)).fetchall()
    ranks = {}
    for rows in (lexical, semantic):
        for rank, row in enumerate(rows, 1):
            key = (row[0], row[2], row[3])
            current = ranks.setdefault(key, {"source_id": row[0], "modified_time": row[1],
                "snapshot_sha256": row[2], "locator": row[3], "excerpt": row[4], "rank_score": 0.0})
            current["rank_score"] += 1.0 / (60 + rank)
    return sorted(ranks.values(), key=lambda row: (-row["rank_score"], row["source_id"], row["locator"]))[:limit]


def load_qa_cases(path: Path):
    """Private expectations for the actual hybrid rank, never CI artifacts."""
    try:
        relative = path.resolve(strict=True).relative_to(PRIVATE_ROOT.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise SearchError("private_qa_file_required") from error
    try:
        document = json.loads(private_file(relative, PRIVATE_ROOT))
    except (json.JSONDecodeError, UnicodeError) as error:
        raise SearchError("invalid_private_qa_cases") from error
    cases = document.get("cases") if isinstance(document, dict) else None
    if (not isinstance(document, dict) or document.get("schema_version") != 1
            or not isinstance(cases, list) or not 1 <= len(cases) <= MAX_QA_CASES):
        raise SearchError("invalid_private_qa_cases")
    for case in cases:
        if (not isinstance(case, dict)
                or set(case) != {"query", "source_id", "snapshot_sha256"}
                or not isinstance(case["query"], str)
                or not case["query"].strip() or len(case["query"]) > MAX_QUERY
                or not isinstance(case["source_id"], str)
                or not (SOURCE_ID.fullmatch(case["source_id"])
                        or (case["source_id"].startswith("note:")
                            and NOTE_ID.fullmatch(case["source_id"][5:])))
                or not isinstance(case["snapshot_sha256"], str)
                or not SHA256.fullmatch(case["snapshot_sha256"])):
            raise SearchError("invalid_private_qa_cases")
    return cases


def verify_retrieval(conn, cases, model):
    for case in cases:
        matches = search(conn, case["query"], model, limit=1)
        if (not matches or matches[0]["source_id"] != case["source_id"]
                or matches[0]["snapshot_sha256"] != case["snapshot_sha256"]):
            raise SearchError("private_retrieval_qa_failed")
    return {"cases_passed": len(cases)}


def benchmark_retrieval(conn, cases, model):
    """Read-only, bounded operator measurement over private reviewed QA cases."""
    if not cases:
        raise SearchError("private_qa_file_required")
    timings = []
    for case in cases:
        started = monotonic()
        matches = search(conn, case["query"], model, limit=1)
        timings.append(round((monotonic() - started) * 1000))
        if (not matches or matches[0]["source_id"] != case["source_id"]
                or matches[0]["snapshot_sha256"] != case["snapshot_sha256"]):
            raise SearchError("private_retrieval_qa_failed")
    timings.sort()
    size = conn.execute("SELECT pg_total_relation_size('private_search.chunks'::regclass)").fetchone()[0]
    return {"cases_passed": len(timings), "max_ms": timings[-1],
            "median_ms": timings[len(timings) // 2], "storage_bytes": size}


def verify_index_content(conn, expected_chunks):
    """Compare the complete derivative with its reviewed input before serving it."""
    ensure_index(conn)
    expected = set(expected_chunks)
    if len(expected) != len(expected_chunks):
        raise SearchError("duplicate_private_reviewed_chunk")
    actual = conn.execute("""SELECT source_id,modified_time,snapshot_sha256,locator,content
        FROM private_search.chunks""").fetchall()
    if len(actual) != len(expected) or set(actual) != expected:
        raise SearchError("private_index_stale_for_review")


def require_current_reviewed_index(conn, manifest_path: Path):
    """Do not serve an index assembled from a different private review snapshot."""
    verify_index_content(conn, load_private_chunks(manifest_path))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Private owner/agent retrieval; no public API")
    parser.add_argument("action", choices=("estimate", "probe", "rebuild", "search", "qa", "benchmark", "rag", "status"))
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--statement-timeout-seconds", type=int,
                        help="operator rebuild only; 30–3600 seconds per SQL statement")
    args = parser.parse_args(argv)
    try:
        timeout = statement_timeout_seconds(args.action, args.statement_timeout_seconds)
        if args.action == "rag" and os.environ.get("PRIVATE_RAG_ENABLED") != "1":
            raise SearchError("private_rag_disabled")
        if args.action in {"search", "qa", "benchmark", "rag"} and args.manifest is None:
            raise SearchError("private_manifest_required")
        if args.action == "estimate":
            if args.manifest is None:
                raise SearchError("private_manifest_required")
            print(json.dumps(capacity_estimate(load_private_chunks(args.manifest))))
            return 0
        if args.action == "probe":
            print(json.dumps(model_probe()))
            return 0
        target = os.environ.get("DATABASE_URL", "")
        try:
            validate_delivery_target(target)
        except ValueError as error:
            raise SearchError("explicit_private_postgres_required")
        with psycopg.connect(target, connect_timeout=5) as conn:
            if args.action in {"search", "qa", "benchmark", "rag", "status"}:
                conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            identity = conn.execute("SELECT current_database(),current_user,current_setting('server_version')").fetchone()
            if identity[:2] != ("psychology_atlas", "psychology_app") or identity[2].split()[0] != "18.6":
                raise SearchError("unexpected_private_postgres_identity")
            conn.execute("SELECT set_config('statement_timeout', %s, true)",
                         (f"{timeout}s",))
            if args.action in {"search", "qa", "benchmark", "rag"}:
                require_current_reviewed_index(conn, args.manifest)
            if args.action == "rebuild":
                if args.manifest is None:
                    raise SearchError("private_manifest_required")
                result = {"chunks": rebuild(conn, load_private_chunks(args.manifest), embedder())}
            elif args.action == "search":
                result = {"results": search(conn, args.query, embedder(), limit=args.limit)}
            elif args.action == "qa":
                if args.cases is None:
                    raise SearchError("private_qa_file_required")
                result = verify_retrieval(conn, load_qa_cases(args.cases), embedder())
            elif args.action == "benchmark":
                if args.cases is None:
                    raise SearchError("private_qa_file_required")
                result = benchmark_retrieval(conn, load_qa_cases(args.cases), embedder())
            elif args.action == "rag":
                result = {"results": search(conn, args.query, embedder(), limit=args.limit)}
            else:
                ensure_index(conn)
                row = conn.execute("""SELECT source_count,chunk_count FROM private_search.index_meta
                    WHERE singleton=true""").fetchone()
                result = {"sources": row[0], "chunks": row[1]}
        if args.action == "rag":
            from app.private_rag import draft_answer
            result = draft_answer(args.query, result["results"])
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as error:
        print("PRIVATE_SEARCH_STOP: " + (str(error) if isinstance(error, (SearchError, RagError))
                                         else type(error).__name__), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
