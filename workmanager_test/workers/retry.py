"""WorkManager script that retries a bounded number of times, then succeeds."""

import json
import os
import sys
import time

from work_result import attempt, request_retry, set_output, set_progress


def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    try:
        max_attempts = max(1, min(10, int(payload.get("max_attempts", 3))))
    except (TypeError, ValueError):
        max_attempts = 3
    message = payload.get("message", "retry demo")

    current = attempt()
    set_progress({
        "attempt": current,
        "max_attempts": max_attempts,
        "message": message,
    })
    print("RETRY_MARKER attempt={}/{} pid={}".format(
        current, max_attempts, os.getpid()), flush=True)

    if current < max_attempts:
        request_retry("attempt {} of {}".format(current, max_attempts))
        # Stay alive long enough that MIUI does not flag the worker process as
        # "frequent died" between retries.
        time.sleep(8)
        return 0

    set_output({"message": message, "attempts": current})
    return 0


if __name__ == "__main__":
    sys.exit(main())
