"""WorkManager script that promotes itself to a foreground service."""

import json
import logging
import os
import sys
import time

from android_notify import Notification, logger as android_notify_logger
from android_notify.config import get_python_worker, on_android_platform
from android_notify.internal.java_classes import BuildVersion, autoclass
from work_result import set_output, set_progress

android_notify_logger.setLevel(logging.WARNING)

# Same shape as the regular p4a service pattern, but for the active worker.
service = get_python_worker() if on_android_platform() else None

# WorkManager's manifest declares dataSync (added for expedited work), so use
# that type rather than the wallpaper service's specialUse type.
foreground_type = (
    autoclass("android.content.pm.ServiceInfo").FOREGROUND_SERVICE_TYPE_DATA_SYNC
    if service and BuildVersion.SDK_INT >= 34
    else 0
)

Notification.createChannel(
    id="worker_foreground_channel",
    name="Worker foreground",
    importance="low",
)


def main() -> int:
    raw = os.environ.get("PYTHON_SERVICE_ARGUMENT", "")
    try:
        payload = json.loads(raw) if raw else {}
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    title = str(payload.get("title", "Foreground worker"))
    text = str(payload.get("text", "Working in the background"))
    try:
        seconds = max(1, min(120, int(payload.get("sleep_seconds", 25))))
    except (TypeError, ValueError):
        seconds = 25

    notification = Notification(
        title=title,
        message=text,
        name="from worker",
        channel_id="worker_foreground_channel",
    )
    # WorkManager marshals ForegroundInfo across binder, so use the
    # marshallable builder (no PendingIntent / bitmap icon) while keeping the
    # same get_worker -> fill_args -> startForeground pattern as wallpaper.py.
    builder = notification.fill_args(persistent=True, marshallable=True)

    if service is not None:
        service.startForeground(notification.id, builder.build(), foreground_type)

    print("FOREGROUND_MARKER title={!r} seconds={}".format(
        title, seconds), flush=True)

    elapsed = 0
    while elapsed < seconds:
        step = min(5, seconds - elapsed)
        time.sleep(step)
        elapsed += step
        set_progress({"elapsed": elapsed, "total": seconds})

    set_output({"title": title, "completed": True})
    return 0


if __name__ == "__main__":
    sys.exit(main())
