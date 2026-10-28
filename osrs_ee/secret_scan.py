"""SEC-03 — repository/data-dir secret scan (metadata-only findings).

Purpose: a one-command check the owner can run before a commit or a bundle:
``osrs-ee secret-scan [PATH]``. It walks text files under PATH, applies
secret-shape patterns (the shapes the Telegram ``Redactor`` refuses at the sink
plus well-known credential prefixes) and reports **where** something matched —
``path``, ``line``, ``pattern`` name, match ``length`` — but **never the matched
text**. A finding is a reason to look, not proof of a leak (docs legitimately
contain shapes such as ``token = ref:env:X``; ``ref:`` values are excluded).

Idea re-implemented after reviewing Engine-Docs ``security/secret_scan.py``
(metadata-only output, prefix catalogue); no code copied (no LICENSE there).
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

# Name -> pattern. Shapes only; a hit is metadata, the value is never emitted.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github_pat_classic", re.compile(r"\bghp_[A-Za-z0-9]{20,}")),
    ("github_oauth", re.compile(r"\bgh[osur]_[A-Za-z0-9]{20,}")),
    ("github_pat_fine", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}")),
    ("telegram_bot_token", re.compile(r"\b[0-9]{5,10}:[A-Za-z0-9_-]{30,}\b")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}")),
    ("genspark_style_key", re.compile(r"\bgsk_[A-Za-z0-9_-]{20,}")),
    ("google_api_key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack_token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("literal_assignment", re.compile(
        r"(?i)\b(password|passwd|pin|api[_-]?key|bot[_-]?token|secret)\s*[:=]\s*['\"]?(?!ref:)(?!\$\{?[A-Z_]+)([^\s'\"]{8,})")),
)

DEFAULT_EXCLUDE_DIRS = frozenset({".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache",
                                  "osrs_ee.egg-info", "build", "dist", "References"})
TEXT_SUFFIXES = frozenset({".py", ".md", ".toml", ".txt", ".json", ".sql", ".yaml", ".yml", ".ini", ".cfg",
                           ".env", ".example", ".sh", ".ps1", ".bat", ".csv", ".jsonl", ".log", ""})
MAX_FILE_BYTES = 2_000_000
ALLOW_MARKER = "secret-scan: allow"   # explicit, visible opt-out for documented fixtures


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    pattern: str
    length: int        # length of the matched span — never its content

    def to_dict(self) -> dict:
        return asdict(self)


def _is_text_candidate(p: Path) -> bool:
    if p.suffix.lower() not in TEXT_SUFFIXES and not p.name.startswith(".env"):
        return False
    try:
        if p.stat().st_size > MAX_FILE_BYTES:
            return False
        with open(p, "rb") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return b"\x00" not in head


def iter_files(root: Path, *, exclude_dirs: Iterable[str] = DEFAULT_EXCLUDE_DIRS) -> Iterator[Path]:
    excl = set(exclude_dirs)
    if root.is_file():
        yield root
        return
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in excl)
        for name in sorted(filenames):
            p = Path(dirpath) / name
            if _is_text_candidate(p):
                yield p


def scan_text(text: str, path: str) -> list[Finding]:
    out: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        for name, pat in PATTERNS:
            m = pat.search(line)
            if m:
                span = m.group(2) if name == "literal_assignment" else m.group(0)
                out.append(Finding(path, lineno, name, len(span)))
    return out


def scan_path(root: str | Path, *, exclude_dirs: Optional[Iterable[str]] = None) -> tuple[list[Finding], int]:
    """Return (findings, files_scanned). Findings carry no secret content."""
    rootp = Path(root)
    findings: list[Finding] = []
    n = 0
    for p in iter_files(rootp, exclude_dirs=exclude_dirs if exclude_dirs is not None else DEFAULT_EXCLUDE_DIRS):
        n += 1
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(p.relative_to(rootp)) if rootp.is_dir() else p.name
        findings.extend(scan_text(text, rel))
    return findings, n


def check_private_permissions(paths: Iterable[Path]) -> list[dict]:
    """POSIX: report files/dirs readable by group/others. Metadata only. Empty on non-POSIX."""
    if os.name != "posix":
        return []
    out = []
    for p in paths:
        try:
            mode = p.stat().st_mode & 0o777
        except OSError:
            continue
        if mode & 0o077:
            out.append({"path": str(p), "mode": oct(mode), "issue": "readable by group/others"})
    return out
