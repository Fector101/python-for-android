# WorkManager worker test app

This app exercises the local python-for-android patch based on upstream PR
#2613. It uses WorkManager's multiprocess path (`RemoteListenableWorker` +
`RemoteWorkerService`), not a p4a `Service` started from Python.

## Build

The spec uses the patched p4a checkout and declares two generated workers:

```ini
p4a.source_dir = /home/fabian/Documents/widget/python-for-android
p4a.extra_args = --skip-prebuilt --worker=script:./workers/heartbeat.py --worker=audit:./workers/audit.py
```

Each `--worker=NAME:PATH` spec generates its own `NAMEWorker` /
`NAMEWorkerService` Java pair in a `:worker_NAME` process. `NAME` is the
generated class name; `PATH` is the build-time default entrypoint, which the
runtime `PYTHON_WORK_SCRIPT` input-data entry overrides.

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
- a one-time `workers/audit.py` job on the second generated worker class (10 s);
- a 2-step `workers/chain.py` chain where step 2 receives step 1's output;
- cancellation and status polling by work name.

Watch for these logcat markers:

```bash
adb logcat -s python PythonWorker ScriptWorker AuditWorker
```

Expected markers:

```text
WORKER_MARKER heartbeat pid=... time=... message='hello from WorkManager'
Finished remote python work: 0
WORKER_MARKER failing pid=... args={'message': 'expected failure'}
Finished remote python work: 3
AUDIT_MARKER worker=audit pid=... time=... script=workers/audit.pyc message='audit worker'
CHAIN_MARKER step=1 time=... pid=...
PARENT_OUTPUT_MARKER step=1 parent={}
CHAIN_MARKER step=2 time=... pid=...
PARENT_OUTPUT_MARKER step=2 parent={'step': 1, 'message': 'chain step 1', ...}
```

The UI's status label should eventually show `SUCCEEDED` for the heartbeat and
audit worker, and `FAILED` for the failing script. The `AuditWorker` tag in
logcat confirms the second generated class ran the job.

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

To run on another generated class, pass `worker_name`:

```python
Work(
    name="audit_once",
    script="workers/audit.py",
    worker_name="audit",
    args={"message": "audit worker"},
).schedule()
```

`worker_name` defaults to `"script"` and is also accepted by `WorkChain` and by
`cancel`, `cancel_all`, `get_info`, `get_work_infos` and
`get_work_infos_by_tag`. It resolves to `<package>.<Name>Worker`, so it must
match a `--worker=NAME:...` entry in `buildozer.spec`.

### Chained Data propagation

WorkManager passes a successful step's output `Data` into the next step's
input. The generated worker writes that `PYTHON_WORK_OUTPUT` value to
`work_data/<script>/parent_output.json` before Python starts, so a chain step
can read the previous step's `set_output()` payload:

```python
from work_result import parent_output, set_output

previous = parent_output()  # {} for the first step or a failed predecessor
set_output({
    "step": 2,
    "parent_step": previous.get("step"),
})
```

`workers/chain.py` uses this to log `PARENT_OUTPUT_MARKER` and include
`parent_step` in its own output. Only successful predecessors propagate data;
a failed step blocks the chain. The per-script directory is shared by steps
using the same script, which is safe because chains run sequentially.
WorkManager's 10 KB `Data` cap still applies to the parent output.
