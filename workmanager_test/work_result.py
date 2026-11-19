"""Publish small JSON results from a p4a WorkManager worker script.

The generated Java worker reads ``output.json`` when the script finishes and
polls ``progress.json`` while it runs, then exposes them as WorkInfo output and
progress. Both sides derive the same per-script directory from
``ANDROID_PRIVATE`` (the unpacked files/app root) and ``ANDROID_ENTRYPOINT``.
"""

import json
import os
import re

_SAFE_RE = re.compile(r"[^A-Za-z0-9_.-]")


def work_dir():
    """Return the per-script directory used to exchange result files.

    p4a's start.c resolves a requested ``.py`` entrypoint to ``.pyc`` (it
    prefers the compiled file) and passes that resolved path as
    ``ANDROID_ENTRYPOINT``. The Java worker still reads the original
    ``PYTHON_WORK_SCRIPT`` (``.py``), so strip the extension here to make both
    sides derive the same directory name.
    """
    base = os.environ.get("ANDROID_PRIVATE") or os.getcwd()
    script = os.environ.get("ANDROID_ENTRYPOINT") or "default"
    if script.endswith(".pyc"):
        script = script[:-1]
    return os.path.join(base, "work_data", _SAFE_RE.sub("_", script))


def _write(filename, data):
    try:
        payload = json.dumps(data, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError("result data must be JSON-serialisable") from exc
    directory = work_dir()
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, filename)
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(payload)
    os.replace(temporary, target)


def set_progress(data):
    """Publish a small JSON-serialisable snapshot as WorkInfo.progress."""
    _write("progress.json", data)


def set_output(data):
    """Publish a small JSON-serialisable result as WorkInfo.output."""
    _write("output.json", data)
