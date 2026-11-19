# WorkManager worker test app

This app exercises the local python-for-android patch based on upstream PR
#2613. It uses WorkManager's multiprocess path (`RemoteListenableWorker` +
`RemoteWorkerService`), not a p4a `Service` started from Python.

## Build

The spec uses the patched p4a checkout and declares one generated worker:

```ini
p4a.source_dir = /home/fabian/Documents/widget/python-for-android
p4a.extra_args = --skip-prebuilt --worker=script:./workers/heartbeat.py
```

Build from this directory:

```bash
VIRTUAL_ENV=$PWD/../venv PATH="$PWD/../venv/bin:$PATH" ../venv/bin/buildozer android debug
```

The APK lands in `bin/workmanagertest-0.1-arm64-v8a-debug.apk`.

## Use

The app can schedule:

- a one-time `workers/heartbeat.py` job 10 seconds from now;
- a periodic heartbeat (WorkManager's 15-minute minimum);
- a one-time `workers/failing.py` job that returns exit code 3;
- cancellation and status polling by work name.

Watch for these logcat markers:

```bash
adb logcat -s python PythonWorker ScriptWorker
```

Expected markers:

```text
WORKER_MARKER heartbeat pid=... time=... message='hello from WorkManager'
Finished remote python work: 0
WORKER_MARKER failing pid=... args={'message': 'expected failure'}
Finished remote python work: 3
```

The UI's status label should eventually show `SUCCEEDED` for the heartbeat and
`FAILED` for the failing script.

## Python API

```python
from work_manager import Work, cancel, get_info

Work(
    name="heartbeat_once",
    script="workers/heartbeat.py",
    args={"message": "hi"},
    delay_seconds=10,
    policy="replace",
).schedule()

get_info("heartbeat_once")
cancel("heartbeat_once")
```

`script` is relative to the unpacked `files/app` directory and must end in
`.py` or `.pyc`. It is passed at runtime as `PYTHON_WORK_SCRIPT`; the script
receives its `args` as JSON in `PYTHON_SERVICE_ARGUMENT`.
