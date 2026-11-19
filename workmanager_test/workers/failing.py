"""Example WorkManager script: always fails so WorkManager reports FAILED."""

import json
import os
import sys


def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {"raw": raw}
    print(
        "WORKER_MARKER failing pid={} args={!r}".format(os.getpid(), payload),
        flush=True,
    )
    return 3


if __name__ == "__main__":
    sys.exit(main())
