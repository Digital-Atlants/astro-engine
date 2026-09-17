"""Which commit is actually running.

The web client refuses to serve its professional flow against an engine it
was not built for, so it has to be able to ask. `/health` answers with the
commit SHA and the field names present on `InterviewAnswer`, which together
pin the request contract: a client that finds a field it does not know about,
or a SHA it has not been tested against, can decline rather than send
answers the engine will silently reinterpret.

Resolution order, first hit wins:

1. `GIT_SHA` - set explicitly at build or deploy time.
2. `RAILWAY_GIT_COMMIT_SHA` - injected by the platform this service runs on.
3. `.git/HEAD` in the source tree, followed one ref deep. Present in a
   checkout, absent from a slim container image.

`"unknown"` when none of them resolve. That is a real state and is reported
as such rather than papered over with the package version.
"""

from __future__ import annotations

import os
import pathlib

UNKNOWN = "unknown"

_ENV_KEYS = ("GIT_SHA", "RAILWAY_GIT_COMMIT_SHA")


def _from_git_dir(root: pathlib.Path) -> str | None:
    head = root / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not text.startswith("ref:"):
        return text or None
    ref = text.split(":", 1)[1].strip()
    try:
        return (root / ".git" / ref).read_text(encoding="utf-8").strip() or None
    except OSError:
        pass
    packed = root / ".git" / "packed-refs"
    try:
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.endswith(" " + ref):
                return line.split(" ", 1)[0]
    except OSError:
        return None
    return None


def git_sha() -> str:
    for key in _ENV_KEYS:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    root = pathlib.Path(__file__).resolve().parent.parent
    return _from_git_dir(root) or UNKNOWN


def interview_answer_fields() -> list[str]:
    from .schemas import InterviewAnswer

    return sorted(InterviewAnswer.model_fields)
