"""WorkManager script that reports which generated worker class ran it."""

import json
import os
import sys
import time
from datetime import datetime, timezone

from work_result import set_output


def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    message = payload.get("message", "audit worker")
    try:
        sleep_seconds = max(0, int(payload.get("sleep_seconds", 10)))
    except (TypeError, ValueError):
        sleep_seconds = 10

    worker = os.environ.get("PYTHON_NAME", "?")
    resolved = (
        os.environ.get("ANDROID_ENTRYPOINT")
        or getattr(sys, "p4a_worker_entrypoint", "?")
    )
    stamp = datetime.now(timezone.utc).isoformat()

    print(
        "AUDIT_MARKER worker={} pid={} time={} script={} message={!r}".format(
            worker, os.getpid(), stamp, resolved, message
        ),
        flush=True,
    )

    slept = 0
    while slept < sleep_seconds:
        step = min(5, sleep_seconds - slept)
        time.sleep(step)
        slept += step

    set_output({
        "worker": worker,
        "script": resolved,
        "message": message,
        "time": stamp,
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
