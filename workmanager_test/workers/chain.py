"""WorkManager chain demo: logs a timed step marker, then succeeds."""

import json
import os
import sys
import time
from datetime import datetime, timezone

from work_result import parent_output, set_output


def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    step = payload.get("step", "?")
    message = payload.get("message", "chain step")
    try:
        sleep_seconds = max(0, int(payload.get("sleep_seconds", 8)))
    except (TypeError, ValueError):
        sleep_seconds = 8

    previous = parent_output()
    stamp = datetime.now(timezone.utc).isoformat()
    print("CHAIN_MARKER step={} time={} pid={}".format(
        step, stamp, os.getpid()), flush=True)
    print("PARENT_OUTPUT_MARKER step={} parent={!r}".format(
        step, previous), flush=True)

    # Stay alive long enough that MIUI does not flag the worker process as
    # "frequent died" between steps.
    slept = 0
    while slept < sleep_seconds:
        part = min(5, sleep_seconds - slept)
        time.sleep(part)
        slept += part

    result = {"step": step, "message": message, "time": stamp}
    if "step" in previous:
        result["parent_step"] = previous["step"]
    set_output(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
