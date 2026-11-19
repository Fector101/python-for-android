"""WorkManager script that reports progress and returns a final output."""

import json
import os
import sys
import time

from work_result import set_output, set_progress


def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    steps = max(1, min(10, int(payload.get("steps", 3))))
    message = payload.get("message", "done")

    for step in range(1, steps + 1):
        set_progress({
            "step": step,
            "total": steps,
            "percent": 100 * step // steps,
        })
        time.sleep(1)

    set_output({"message": message, "steps": steps})
    return 0


if __name__ == "__main__":
    sys.exit(main())
