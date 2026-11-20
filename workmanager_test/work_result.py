"""Publish small JSON results from a p4a WorkManager worker script.

The generated Java worker reads ``output.json`` when the script finishes and
polls ``progress.json`` while it runs, then exposes them as WorkInfo output and
progress. A script can also write ``retry.json`` to request WorkManager retry.
Both sides derive the same per-script directory from ``ANDROID_PRIVATE`` (the
unpacked files/app root) and ``ANDROID_ENTRYPOINT``.
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


def parent_output():
    """Return the previous chain step's ``set_output()`` payload.

    WorkManager passes a successful predecessor's output Data into the child's
    input. The generated Java worker writes that ``PYTHON_WORK_OUTPUT`` value
    to ``parent_output.json`` in this script's work dir before Python starts.
    Returns an empty dict when there is no predecessor output or it is invalid.
    """
    target = os.path.join(work_dir(), "parent_output.json")
    try:
        with open(target, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def request_retry(reason=""):
    """Ask Java to reschedule this work with WorkManager's backoff policy.

    The file takes precedence over the script's exit status. It is deleted at
    the start of every worker attempt, so it must be written on each attempt
    that wants a retry.
    """
    _write("retry.json", {"reason": reason})


def attempt():
    """Return this worker's 1-based attempt count.

    Java clears output/progress/retry at the start of each attempt but leaves
    ``attempt.txt`` in place, so the counter survives retry reschedules.
    """
    directory = work_dir()
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, "attempt.txt")
    try:
        with open(target, encoding="utf-8") as handle:
            count = int(handle.read().strip() or "0")
    except (OSError, ValueError):
        count = 0
    count += 1
    temporary = target + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        handle.write(str(count))
    os.replace(temporary, target)
    return count
