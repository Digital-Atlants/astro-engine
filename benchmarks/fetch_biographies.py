"""Work item 3.1: assemble biography excerpts, with the birth time removed.

Pulls the plain-text extract of each corpus case's public Wikipedia article and
writes it to `benchmarks/fixtures/biographies/`. Before writing, any clock time
is redacted, so the extraction context cannot contain the birth time. The
Rodden rating, the corpus fixture and every prior benchmark output are simply
never read here.

Redaction is logged per case so a reader can see what was removed rather than
taking it on trust.

    python benchmarks/fetch_biographies.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from benchmarks.harness import corpus  # noqa: E402

OUT_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "biographies"
API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "astro-engine-benchmark/1.0 (research; contact via repository)"

# Anything that could carry a time of day, plus the words for one.
TIME_PATTERNS = [
    re.compile(r"\b\d{1,2}\s*[:.]\s*\d{2}\s*(?::\s*\d{2})?\s*(?:[ap]\.?m\.?)?", re.I),
    re.compile(r"\b\d{1,2}\s*(?:o'clock|am|pm|a\.m\.|p\.m\.)", re.I),
    re.compile(r"\b(?:midnight|noon|midday)\b", re.I),
    re.compile(r"\bborn at\b[^.]{0,60}", re.I),
]


def fetch_extract(title: str, attempts: int = 5) -> str:
    """Wikipedia rate-limits bursts with 429; back off rather than lose cases."""
    for attempt in range(attempts):
        try:
            text = _fetch_once(title)
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == attempts - 1:
                raise
            text = ""
        if text:
            return text
        time.sleep(2.0 * (attempt + 1))
    return ""


def _fetch_once(title: str) -> str:
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "format": "json",
        "titles": title,
    }
    req = urllib.request.Request(
        f"{API}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    pages = data["query"]["pages"]
    page = next(iter(pages.values()))
    return page.get("extract", "") or ""


def redact(text: str) -> tuple[str, list[str]]:
    removed: list[str] = []

    def sub(m):
        removed.append(m.group(0).strip())
        return "[TIME REDACTED]"

    for pattern in TIME_PATTERNS:
        text = pattern.sub(sub, text)
    return text, removed


def title_from_url(url: str) -> str:
    return urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index = []
    for case in corpus.load_corpus():
        url = case.get("events_source_url") or ""
        title = title_from_url(url)
        existing = OUT_DIR / f"{case['case_id']}.txt"
        cached = existing.exists() and existing.stat().st_size > 2000
        try:
            raw = (
                existing.read_text(encoding="utf-8")
                if cached
                else fetch_extract(title)
            )
        except Exception as exc:  # noqa: BLE001
            print(f"  !! {case['case_id']}: {exc}", flush=True)
            raw = ""
        text, removed = redact(raw)
        if not cached:
            time.sleep(1.0)  # be a polite API client
        path = OUT_DIR / f"{case['case_id']}.txt"
        path.write_text(text, encoding="utf-8")
        index.append(
            {
                "case_id": case["case_id"],
                "title": title,
                "source_url": url,
                "chars": len(text),
                "redactions": removed,
                "n_redactions": len(removed),
            }
        )
        print(
            f"  {case['case_id']:24} {len(text):>7} chars, "
            f"{len(removed)} redaction(s)",
            flush=True,
        )

    (OUT_DIR / "index.json").write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    total = sum(r["n_redactions"] for r in index)
    empty = [r["case_id"] for r in index if r["chars"] == 0]
    print(f"\n{len(index)} biographies, {total} redactions, {len(empty)} empty {empty}")


if __name__ == "__main__":
    main()
