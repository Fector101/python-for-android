"""Example WorkManager script: logs a marker and succeeds."""

import json
import os
import sys
import time
from datetime import datetime, timezone

print("ran")


def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {"raw": raw}
    if not isinstance(payload, dict):
        payload = {"message": payload}

    message = payload.get("message", "hello")
    try:
        sleep_seconds = max(0, int(payload.get("sleep_seconds", 0)))
    except (TypeError, ValueError):
        sleep_seconds = 0

    stamp = datetime.now(timezone.utc).isoformat()
    print(
        "WORKER_MARKER heartbeat pid={} time={} message={!r} sleep={}".format(
            os.getpid(), stamp, message, sleep_seconds
        ),
        flush=True,
    )
    try:
        from android_notify import Notification
        Notification(title=message).send()
    except Exception as e:
        print(f'the worker file: {e}')

    # Stay alive in short steps so cancellation is observable in WorkInfo.
    slept = 0
    while slept < sleep_seconds:
        step = min(5, sleep_seconds - slept)
        time.sleep(step)
        slept += step
        print("WORKER_MARKER heartbeat alive slept={}/{}".format(
            slept, sleep_seconds), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
