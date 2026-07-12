"""Structural guard: this repository is astrology-only.

Greps every tracked text file for forbidden domain terms. The term list is
built from character codes so this file does not trip its own scan.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}
TEXT_SUFFIXES = {".py", ".md", ".toml", ".txt", ".yml", ".yaml", ".json", ".cfg", ".ini", ""}

FORBIDDEN = [
    bytes(c).decode()
    for c in (
        [98, 111, 100, 121, 103, 114, 97, 112, 104],          # b-o-d-y-g-r-a-p-h
        [104, 117, 109, 97, 110, 95, 100, 101, 115, 105, 103, 110],
        [104, 117, 109, 97, 110, 32, 100, 101, 115, 105, 103, 110],
        [103, 97, 116, 101, 95],
        [115, 97, 99, 114, 97, 108],
        [109, 97, 110, 105, 102, 101, 115, 116, 111, 114],
        [114, 97, 118, 101, 32, 109, 97, 110, 100, 97, 108, 97],
        [112, 114, 111, 106, 101, 99, 116, 111, 114],          # HD type
        [114, 101, 102, 108, 101, 99, 116, 111, 114],          # HD type
    )
]

BRAND_FORBIDDEN = [
    bytes(c).decode()
    for c in (
        [115, 111, 118, 105, 121, 97],
        [115, 111, 118, 121, 114, 97],
    )
]


def iter_files():
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def test_no_forbidden_terms():
    offenders = []
    for path in iter_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for term in FORBIDDEN + BRAND_FORBIDDEN:
            if term in text and path != Path(__file__):
                offenders.append((str(path), term))
    assert not offenders, f"forbidden terms found: {offenders}"
