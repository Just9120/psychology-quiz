"""Preflight ordinary personal Markdown links before replacing managed notes.

This does not rewrite personal files or republish withdrawn claims. If a file or
an existing heading/block link would disappear, the owner must migrate it first.
Plugin-specific links and application settings are left untouched.
"""
from __future__ import annotations

import posixpath
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


def _links(text: str):
    # Examples in code are not navigation. Reference-style Markdown links are
    # resolved through their local definition, independently of their label.
    text = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1\s*$", "", text)
    text = re.sub(r"`[^`\n]+`", "", text)
    for target in re.findall(r"!?\[\[([^\]\n]+)\]\]", text):
        yield target.split('|', 1)[0], True
    for target in re.findall(r"!?\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^\s)]+)", text):
        yield target.strip('<>'), False
    for target in re.findall(r"(?m)^\s{0,3}\[[^\]\n]+\]:\s*(<[^>\n]+>|[^\s]+)", text):
        yield target.strip('<>'), False


def _heading(value: str) -> str:
    value = re.sub(r'<[^>]*>', '', value)
    value = re.sub(r'!?\[([^\]]+)\]\([^)]*\)', r'\1', value)
    return re.sub(r'\s+', ' ', value.strip().strip('#').strip(' *_`~')).casefold()


def _has_anchor(body: bytes, fragment: str, wiki: bool) -> bool:
    if not fragment:
        return True
    text = body.decode('utf-8')
    if fragment.startswith('^'):
        return fragment[1:] in re.findall(r'(?m)(?:^|\s)\^([A-Za-z0-9-]+)\s*$', text)
    # Preserve nested heading paths as well as simple headings. Markdown links
    # may use a URL-encoded heading or a conventional hyphenated heading slug.
    wanted = [_heading(part) for part in fragment.split('#') if part]
    stack: list[tuple[int, str]] = []
    for match in re.finditer(r'(?m)^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$', text):
        level, title = len(match[1]), _heading(match[2])
        stack = [item for item in stack if item[0] < level] + [(level, title)]
        values = [item[1] for item in stack]
        if wanted and values[-len(wanted):] == wanted:
            return True
        if not wiki and len(wanted) == 1:
            slug = re.sub(r'[^\w\s-]', '', title).replace(' ', '-')
            if wanted[0] == slug:
                return True
    if len(wanted) == 1:
        for title in re.findall(r'(?m)^([^\n]+)\n\s{0,3}(?:={3,}|-{3,})\s*$', text):
            normalized = _heading(title)
            if wanted[0] == normalized or (not wiki and wanted[0] ==
                    re.sub(r'[^\w\s-]', '', normalized).replace(' ', '-')):
                return True
    return False


def _targets(target: str, origin: str, universe: set[str], wiki: bool) -> set[str]:
    if not target:
        return {origin} & universe
    target = target.replace('\\', '/')
    if target.startswith('/'):
        paths = {posixpath.normpath(target.lstrip('/'))}
    else:
        paths = {posixpath.normpath(posixpath.join(posixpath.dirname(origin), target))}
        if wiki:
            paths.add(posixpath.normpath(target))
    paths |= {path + '.md' for path in paths if not path.lower().endswith('.md')}
    folded = {path.casefold(): path for path in universe}
    found = {folded[path.casefold()] for path in paths if path.casefold() in folded}
    if wiki and not found and '/' not in target:
        name = target if target.lower().endswith('.md') else target + '.md'
        found = {path for path in universe if path.rsplit('/', 1)[-1].casefold() == name.casefold()}
    return found


def personal_link_breaks(vault: Path, previous: dict[str, bytes],
                         current: dict[str, bytes]) -> bool:
    """Return whether this update introduces an unresolved managed link.

    Pre-existing broken anchors are not newly introduced failures. Removal of
    their target file still requires explicit migration. Root notes and folders
    other than personal/ receive the same protection.
    """
    personal: dict[str, bytes] = {}
    total = 0
    for path in vault.rglob('*'):
        relative = path.relative_to(vault)
        if relative.parts[0] in {'generated', '.vault-generated-backup'}:
            continue
        if path.is_symlink():
            # Do not follow an owner's link outside the Vault during inspection.
            return True
        if path.is_file() and path.suffix.lower() == '.md':
            size = path.stat().st_size
            total += size
            if size > 8 * 1024 * 1024 or total > 64 * 1024 * 1024:
                return True
            personal[relative.as_posix()] = path.read_bytes()
    old = {**personal, **{'generated/' + name: body for name, body in previous.items()}}
    new = {**personal, **{'generated/' + name: body for name, body in current.items()}}
    for origin, body in personal.items():
        for raw, wiki in _links(body.decode('utf-8')):
            # Decode after scheme detection: encoded local names remain local.
            if urlsplit(raw).scheme or raw.startswith('//'):
                continue
            target, _, fragment = unquote(raw).partition('#')
            old_targets = _targets(target, origin, set(old), wiki)
            old_managed = {name for name in old_targets if name.startswith('generated/')}
            if not old_managed:
                continue
            new_targets = _targets(target, origin, set(new), wiki)
            if not old_managed <= new_targets:
                return True
            if any(_has_anchor(old[name], fragment, wiki)
                   and not _has_anchor(new[name], fragment, wiki) for name in old_managed):
                return True
    return False
