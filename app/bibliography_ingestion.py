"""Private, revision-bound bibliography candidates from any extracted source.

Discovery locates mentions, never approves a work identity or publication. Source
texts, offsets and Drive identifiers stay in the private operator queue. Existing
catalogue and personal reading rows are not modified by ingestion.
"""
from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from itertools import chain

from app.source_inventory import InventoryError, _revision

# A PDF line break may precede a title or occur inside it. Keep the raw
# spelling for source coordinates and limit the cue-to-title break to one line.
READING_QUOTE = re.compile(
    r'(?:книг[а-я]*|учебник[а-я]*|пособи[а-я]*|монографи[а-я]*|прочита[а-я]*|литератур[а-я]*)'
    r'[^\n«»“”"]{0,120}?(?:\r?\n[ \t]*)?[«“"](?P<title>[^«»“”"]{3,200})[»”"]', re.IGNORECASE)


# Genre cues have a tighter grammar than explicit reading instructions: do not
# cross a sentence into dialogue after a mention of somebody's romantic affair.
NOVEL_QUOTE = re.compile(
    r'(?<!\w)(?i:роман(?:а|е|ом|у|ы|ов|ах|ами)?|повест(?:ь|и|ью|ей|ям|ями|ях))'
    r'[ \t]+(?:(?:[А-ЯЁ][а-яё-]+[ \t]+){1,3})?'
    r'(?:под названием[ \t]+)?(?:\r?\n[ \t]*)?'
    r'[«“"](?P<title>[^«»“”"]{3,200})[»”"]')

# Lectures may name a textbook as an author's main scholarly work. Keep the
# qualifier and immediate title grammar, rather than matching any use of "труд".
ACADEMIC_WORK_QUOTE = re.compile(
    r'(?<!\w)(?i:(?:основн[а-я]+|научн[а-я]+|фундаментальн[а-я]+)'
    r'[ \t]+труд(?:а|е|ом|у|ы|ов|ах|ами)?)(?:[ \t]+|[ \t]*\r?\n[ \t]*)'
    r'(?:это[ \t]+)?(?:\r?\n[ \t]*)?'
    r'[«“"](?P<title>[^«»“”"]{3,200})[»”"]')

QUOTED_TITLE = re.compile(r'[«“"](?P<title>[^»”"]{3,200})[»”"]')
TITLE_SEPARATOR = re.compile(r'[\s,;]*(?:(?:и|или|а также)[\s,;]+)?', re.IGNORECASE)


def _book_quotes(text: str):
    """Keep adjacent titles in a book list, without interpreting later dialogue."""
    for first in chain(READING_QUOTE.finditer(text), NOVEL_QUOTE.finditer(text),
                       ACADEMIC_WORK_QUOTE.finditer(text)):
        cue = text[first.start():first.start("title")]
        if re.search(r"литератур[а-я]*\s+к\s+блок[а-я]*\s*[«“\"]$", cue, re.IGNORECASE):
            # The quoted name labels the course block, not a recommended book.
            continue
        yield first.span("title"), first.group("title")
        end = first.end()
        while True:
            separator = TITLE_SEPARATOR.match(text, end)
            # Only a bounded list separator may connect another quoted title.
            if separator.end() - end > 80:
                break
            following = QUOTED_TITLE.match(text, separator.end())
            if following is None:
                break
            yield following.span("title"), following.group("title")
            end = following.end()


# Transcripts can omit title quotes: e.g. "романе Льва Толстого Война и мир,".
# There is no reliable boundary between a two-/three-part author name and a
# capitalized title. Preserve the complete citation as a private review task,
# rather than guessing an author, edition or work identity.
UNQUOTED_BOOK_CITATION = re.compile(
    r"(?<!\w)(?i:роман(?:а|е|ом|у|ы|ов|ах|ами)?|повест(?:ь|и|ью|ей|ям|ями|ях))"
    r"[ \t]+(?P<citation>(?:[А-ЯЁ][а-яё-]+[ \t]+){2}"
    r"[А-ЯЁ][^\n,.;:!?«»“”\"]{1,200})(?=[,.;:!?]|$)")


def _unparsed_book_citations(text: str):
    for match in UNQUOTED_BOOK_CITATION.finditer(text):
        start, end = match.span("citation")
        while end > start and text[end - 1].isspace():
            end -= 1
        yield (start, end), text[start:end]


def _title_pattern(title: str):
    # Keep offsets in the exact captured text; do not normalize the source.
    parts = re.split(r"\s+", title.strip())
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(part) for part in parts)
                      + r"(?!\w)", re.IGNORECASE)


def discover_bibliography(snapshot: dict, captures: list[dict], catalogue: list[dict],
                          catalogue_aliases: list[dict] | None = None) -> dict:
    """Return review candidates and explicit unread coverage, never a clean bill."""
    by_title = defaultdict(set)
    for entry in catalogue:
        if not isinstance(entry, dict) or not all(isinstance(entry.get(k), str) and entry[k].strip()
                                                 for k in ("title", "id", "work_id")):
            raise InventoryError("invalid_bibliography_catalogue")
        by_title[entry["title"]].add(entry["work_id"])
    # Operator-supplied title variants identify candidates only. They never
    # merge works or grant publication approval, and stay outside public JSON.
    work_ids = {entry["work_id"] for entry in catalogue}
    if catalogue_aliases is not None and not isinstance(catalogue_aliases, list):
        raise InventoryError("invalid_bibliography_aliases")
    for alias in catalogue_aliases or []:
        if (not isinstance(alias, dict)
                or not isinstance(alias.get("title"), str) or not alias["title"].strip()
                or not isinstance(alias.get("work_id"), str)
                or alias["work_id"] not in work_ids):
            raise InventoryError("invalid_bibliography_alias")
        by_title[alias["title"]].add(alias["work_id"])
    author_cues = defaultdict(set)
    for entry in catalogue:
        authors = entry.get("authors", [])
        if not isinstance(authors, list):
            continue
        for author in authors:
            # Conventional surname-first bibliography names. Do not infer a
            # surname from arbitrary full names or expand unidentified authors.
            if isinstance(author, str) and re.fullmatch(
                    r"[A-Za-zА-Яа-яЁё-]{3,}(?:\s+[A-ZА-ЯЁ]\.){1,3}", author):
                author_cues[entry["work_id"]].add(author.split()[0])
    known = [(_title_pattern(title), sorted(ids), len(title.split()) == 1,
              [re.compile(r"(?<!\w)" + re.escape(surname)
                          + r"(?:[ \t]*[A-ZА-ЯЁ]\.){0,3}[ \t]*(?:[:.,—–-][ \t]*)?$",
                          re.IGNORECASE)
               for work_id in ids for surname in author_cues[work_id]])
             for title, ids in by_title.items()]
    seen, mentions = set(), []
    evidence_counts = defaultdict(int)
    for capture in captures:
        if not isinstance(capture, dict):
            raise InventoryError("invalid_bibliography_capture")
        source_id = capture.get("source_id")
        source = snapshot["files"].get(source_id)
        raw = capture.get("content")
        if (source is None or source_id in seen or not isinstance(raw, bytes)
                or tuple(capture.get("revision", ())) != _revision(source)
                or hashlib.sha256(raw).hexdigest() != capture.get("snapshot_sha256")):
            raise InventoryError("stale_or_invalid_bibliography_capture")
        try:
            text = raw.decode("utf-8")
        except UnicodeError as error:
            raise InventoryError("bibliography_extracted_utf8_required") from error
        if not text.lstrip("\ufeff").strip():
            raise InventoryError("bibliography_empty_capture_not_read")
        seen.add(source_id)
        found = {}
        evidence_kinds = {}
        book_quotes = list(_book_quotes(text))
        explicit_titles = {bounds for bounds, _ in book_quotes}
        for pattern, work_ids, single_word, author_patterns in known:
            for match in pattern.finditer(text):
                if any(start <= match.start() and match.end() <= end
                       and match.span() != (start, end)
                       for start, end in explicit_titles):
                    # A shorter catalogue title inside an explicit longer title
                    # is not a second work. Keep the full title's review task.
                    continue
                if (single_word and match.span() not in explicit_titles
                        and not any(author.search(text[max(0, match.start() - 80):match.start()])
                                    for author in author_patterns)):
                    # A common word such as "психология" is not a citation of
                    # the same-named textbook, including inside another title.
                    continue
                found[match.span()] = (match.group(), work_ids)
                # A title match alone is a broad search hit, not a citation.
                # Retain it so discovery does not silently lose possible books.
                evidence_kinds[match.span()] = (
                    "explicit_book_title" if any(
                        start <= match.start() and match.end() <= end
                        for start, end in explicit_titles)
                    else "author_title_citation" if any(
                        author.search(text[max(0, match.start() - 80):match.start()])
                        for author in author_patterns)
                    else "catalogue_title_match")
        for bounds, title in book_quotes:
            if not any(start <= bounds[0] and bounds[1] <= end for start, end in found):
                found[bounds] = (title, [])
                evidence_kinds[bounds] = "explicit_book_title"
        unparsed = {}
        for bounds, citation in _unparsed_book_citations(text):
            if any(bounds[0] <= start and end <= bounds[1] and work_ids
                   for (start, end), (_, work_ids) in found.items()):
                # A known title inside this citation already has a review task.
                continue
            found[bounds] = (citation, [])
            unparsed[bounds] = True
            evidence_kinds[bounds] = "unparsed_author_title"
        for (start, end), (title, work_ids) in sorted(found.items()):
            evidence_kind = evidence_kinds[(start, end)]
            evidence_counts[evidence_kind] += 1
            mentions.append({
                "source_id": source_id, "revision": list(_revision(source)),
                "snapshot_sha256": capture["snapshot_sha256"],
                "paths": snapshot["paths"][source_id],
                "locator": f"characters:{start}:{end}", "title_candidate": title,
                "excerpt": text[max(0, start - 150):min(len(text), end + 150)],
                "candidate_work_ids": work_ids, "decision": "pending_review",
                "evidence_kind": evidence_kind,
            })
            if (start, end) in unparsed:
                mentions[-1]["candidate_kind"] = "unparsed_author_title"
                mentions[-1]["review_note"] = (
                    "Unquoted author/title citation: identify the title manually; "
                    "the full citation is not an approved title or work identity.")
    return {"schema_version": 1, "captured_sources": len(seen),
            "unread_source_ids": sorted(set(snapshot["files"]) - seen),
            "mentions": mentions, "evidence_counts": dict(sorted(evidence_counts.items())),
            "publication_approval": False}
