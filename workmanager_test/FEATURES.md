# WorkManager test app — feature status

Companion app for the p4a WorkManager worker patch. Features are added one at a
time; this file tracks what is covered and what is still missing.

Branch: `feat/workmanager-worker-support` (`Fector101/python-for-android`).

Legend: **Done** = implemented and verified on a device. **Missing** = not
implemented. Every "Partial" row was closed out by the A→B→C→D→E cleanup.

## Done

| Feature | Commit | Coverage / verification |
|---|---|---|
| Core scheduling + lifecycle | `58a10d39` | One-time work with initial delay, periodic work, unique work names, `cancel`, `cancelAll`, status polling by name. Script path passed in input data so one generated worker runs any bundled script. Device: heartbeat `SUCCEEDED` (exit 0), failing script `FAILED` (exit 3), worker notification visible in `dumpsys notification`. |
| Constraints | `d9d5e4d8` | UI checkboxes for `network_required` / `charging_required`; mapped to `NetworkType.CONNECTED` and `setRequiresCharging(true)`. Device: work stayed `ENQUEUED` with charging off + wifi/data off; ran and finished with code 0 after constraints were restored. |
| Richer WorkInfo | `24599a5a` | `getInfoJson()` in `Worker.tmpl.java` serialises all `WorkInfo` rows to JSON (id, state, attempts, generation, tags, output, progress, initial delay, next-run time, stop reason). Python `get_work_info()` / `get_work_infos()` expose typed dataclasses; legacy `get_info()` still returns just the state. Device: `SUCCEEDED` / `FAILED`, attempt count and tags read back from WorkManager; constrained work observed `ENQUEUED` then `SUCCEEDED`. |
| Periodic repeat | `58a10d39` (user device test) | A 15-minute periodic heartbeat was scheduled with the original commit and produced a notification every 15 minutes. |
| `ExistingWorkPolicy` KEEP vs REPLACE | `b55854f0` | UI policy toggle passes `keep`/`replace` into `Work`. Device: scheduling the same unique name twice with KEEP kept the same work ID; with REPLACE it produced a new ID. |
| `cancel_all()` + cancel while running | `b55854f0` | "Cancel all" and "Schedule slow" buttons. Device: Cancel all moved every tracked work to `CANCELLED`; cancelling a sleeping worker gave `CANCELLED` / `CANCELLED_BY_APP` and the worker process exited. |
| Persistence across process death | verification only (no code change) | Work scheduled with a 90 s delay kept the same ID `715b2235-…` and `ENQUEUED` state across `am force-stop`, then executed with `message='persist test'`. Reboot test skipped by user; WorkManager persists its DB across reboot by design. |
| Input data limit | `47f26388` | `Work.argument_json()` validates UTF-8 byte size against WorkManager's 10 KB `Data` cap with a 512-byte reserve for the other Data entries (9728-byte payload limit). Device: 9728 bytes accepted, 9729 rejected before any Java call, multi-byte UTF-8 counted by bytes. |
| Status polling off the main thread | `35ac91fc` | One daemon `work-status-poll` thread does the JNI `get_work_info()` calls; a `queue.Queue` hands results to the Kivy main thread, drained by a 0.25 s Clock callback. `on_stop()` joins the thread. Device: thread alive/daemon, ~4 updates/sec, `RUNNING` → `SUCCEEDED`, no JNI crash. |
| Output + progress write side | `3e83866f` | `work_result.py` lets a worker write `set_progress()` / `set_output()` small JSON snapshots to a per-script dir. Java `PythonWorker` polls `progress.json` via `setProgressAsync()` and reads `output.json` into `Result.success(Data)`; no native signature change or new Data keys. Python unwraps `PYTHON_WORK_OUTPUT` / `PYTHON_WORK_PROGRESS` into plain dicts in `WorkInfo`. Device: progress observed while `RUNNING` (`step 1` → `step 4`), output `{'message': 'output demo', 'steps': 6}` after `SUCCEEDED`. |
| Retry + backoff | `21fd650e` | `work_result.request_retry()` writes `retry.json`; Java maps it to `Result.retry()` (takes precedence over the exit status). `Work(backoff_policy, backoff_delay_seconds)` maps to `setBackoffCriteria()` with Python validation and Java clamping to WorkManager's 10 s .. 24 h range. `work_result.attempt()` keeps a counter that survives retries. Device: Java logged `Worker requested retry`, work re-enqueued with `nextScheduleTimeMillis` ~10 s later, `run_attempt_count` went 1 → 2. MIUI `proc frequent died!` / `process is bad` then blocked the next worker process launch, so the final attempt was not observed — the known platform throttle, not an app bug. |

## Missing

| Feature | State | Notes |
|---|---|---|
| Chaining (`beginWith().then()`) | Missing | No API to build dependent work chains. |
| Custom tags / query by tag | Missing | WorkManager's auto-generated tag is visible in `WorkInfo.tags`, but there is no way to add tags or query `getWorkInfosByTag`. |
| Non-unique work (`enqueue`) | Missing | Every schedule call uses `enqueueUniqueWork` / `enqueueUniquePeriodicWork`. |
| More existing-work policies | Missing | `APPEND`, `APPEND_OR_REPLACE`, `UPDATE` (periodic) are not exposed. |
| Network types beyond CONNECTED | Missing | `UNMETERED`, `NOT_ROAMING`, `NOT_REQUIRED` are not exposed. |
| Battery / storage / idle constraints | Missing | `requiresBatteryNotLow`, `requiresStorageNotLow`, `requiresDeviceIdle` are not exposed. |
| Expedited work / foreground long-running | Missing | No `setExpedited()` or foreground service type support. |
| Multiple distinct worker classes | Missing | Only the `script` worker is generated; `--worker` can be repeated but the Python API defaults to one class name. |
| Stop reason for constrained work | Missing from verification | The field is read correctly, but WorkManager 2.9.0 reported `NOT_STOPPED` for `ENQUEUED` constrained rows; a real stop-reason case has not been observed. |

## Known test-app caveats

- The p4a branch copy of `workmanager_test/android_notify/` contains only
  `config.py` (no `__init__.py`), so it is a namespace package and the installed
  `android_notify` from the venv wins on import. Running the full test suite
  there yields 3 pre-existing failures in `test_android_notify_config.py`;
  `test_work_manager.py` alone passes.
- p4a renders Java from a template and caches sources inside the existing build
  dist. When `Worker.tmpl.java` or `PythonWorker.java` changes, refresh
  `.buildozer/android/platform/build-arm64-v8a/dists/workmanagertest/{templates/Worker.tmpl.java,src/main/java/org/kivy/android/PythonWorker.java}`
  and `build/bootstrap_builds/sdl3/src/main/java/org/kivy/android/PythonWorker.java`,
  otherwise the APK keeps the stale Java.
- `start.c` resolves a requested `.py` worker entrypoint to `.pyc` (it prefers
  the compiled file) and passes that resolved path as `ANDROID_ENTRYPOINT`.
  `work_result.py` strips `.pyc` so its per-script result dir matches the Java
  side's `PYTHON_WORK_SCRIPT` name. Any future file-based exchange must
  normalise the extension on both sides.
- MIUI can flag `<package>:worker_script` as "process is bad" after repeated
  short worker runs (`ProcessStarter: proc frequent died!`). This is platform
  throttling, not an app bug; a reinstall or a cooldown clears it. During retry
  verification it blocked the second rescheduled worker launch even with an
  8-second worker lifetime and 10-second backoff, so only the first retry
  (`run_attempt_count` 1 → 2) could be observed; raising the delay or rebooting
  the device clears the flag.
- MIUI also requires a manual tap in the install confirmation dialog; plain
  `adb install` fails with `INSTALL_FAILED_USER_RESTRICTED` until approved.

## Suggested order for the next features

1. Chaining (`beginWith().then()`).
2. Custom tags / query by tag, non-unique `enqueue`, extra existing-work
   policies, extra network types and battery/storage/idle constraints.
3. Expedited work / foreground long-running work.
