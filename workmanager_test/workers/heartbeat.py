"""Example WorkManager script: logs a marker and succeeds."""

import json
import os
import sys
from datetime import datetime, timezone

print("ran")

def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {"raw": raw}

    message = payload.get("message", "hello") if isinstance(payload, dict) else payload
    stamp = datetime.now(timezone.utc).isoformat()
    print(
        "WORKER_MARKER heartbeat pid={} time={} message={!r}".format(
            os.getpid(), stamp, message
        ),
        flush=True,
    )
    try:
        from android_notify import Notification
        Notification(title=message).send()
    except Exception as e:
        print(f'the worker file: {e}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
