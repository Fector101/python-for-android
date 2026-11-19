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
| Chaining (`beginUniqueWork().then()`) | `3f4d6907` | `Work(...).then(Work(...))` builds a `WorkChain` (2..10 one-time steps, same worker class, no periodic steps). Java `scheduleChain()` takes a JSON array of per-step settings and applies `beginUniqueWork(name, policy, first).then(rest).enqueue()`, so name/policy/cancel/status apply to the whole chain. Device: step 2 stayed `BLOCKED` while step 1 ran (`CHAIN_MARKER step=1` at 20:59:55Z), then ran and both rows finished `SUCCEEDED` (step 2 output at 21:00:04Z); per-step outputs readable in `get_work_infos()`. |
| Custom tags / query by tag | `e11a229c` | `Work(tags=[...])` adds custom tags to one-time, periodic and chain-step requests (JSON array string to Java `addTag()`); 1..10 tags of ≤100 chars, validated in Python. `get_work_infos_by_tag()` wraps `getWorkInfosByTag()` in the existing `WorkInfos` dataclasses, and `cancel_by_tag()` wraps `cancelAllWorkByTag()`. Device: two works sharing `tag_demo` were both returned by the tag query with `tags=['io.github.fector101.workmanagertest.ScriptWorker', 'tag_demo']` (WorkManager's auto class tag is additive), both finished `SUCCEEDED`; `cancel_by_tag('tag_cancel')` moved a third work to `CANCELLED`. |
| More existing-work policies | `064ee7a6` | One-time `policy` now accepts `keep`, `replace`, `append` and `append_or_replace`; periodic accepts `keep`, `replace` and `update` (WorkManager 2.9.0). Java `parseOneTimePolicy()` / `parsePeriodicPolicy()` map the strings and fall back to KEEP; `scheduleChain()` uses the one-time parser too. `WorkChain.policy` accepts the four one-time values. Values are case-insensitive; invalid one-time/periodic pairings are rejected in Python. UI policy button cycles all five values (an invalid pairing is reported in the log area). Device: `append` under one name produced two distinct IDs, one `BLOCKED` while the other ran, then both `SUCCEEDED`; `update` on a periodic request kept the same ID with one row; `append_or_replace` accepted a re-schedule after the original finished. |
| Non-unique work (`enqueue`) | `575e2216` | `Work(unique=False)` calls Java `manager.enqueue()` for both one-time and periodic requests; 14-arg `schedule()` overload adds the `unique` flag (older overloads delegate with `true`). The name is auto-added as a tag, so `get_work_infos(name, unique=False)` / `get_info()` / `get_work_info()` / `cancel()` dispatch to the existing tag-based Java methods, and `policy` is ignored for non-unique work. UI adds a "Non-unique" checkbox wired into status polling. Device: two one-time works with distinct IDs ran `RUNNING` concurrently (no `BLOCKED`, unlike APPEND), two non-unique periodic rows existed, tags contained `['io.github.fector101.workmanagertest.ScriptWorker', 'nonunique_once']`, and `cancel(name, unique=False)` moved both rows to `CANCELLED`. |
| Network types beyond CONNECTED | `6afe4992` | `Work(network_type=...)` accepts `connected` (default), `unmetered`, `not_roaming`, `not_required` (case-insensitive, validated in Python). `network_required` stays the master switch. Java `parseNetworkType()` maps the strings to `NetworkType.*` and falls back to `CONNECTED`; a 15-arg `schedule()` overload carries the extra value (older overloads delegate with `"connected"`), and chain steps read `network_type` from their JSON. UI adds a "Network type:" button cycling the four values. Device: on wifi all four types were accepted and finished `SUCCEEDED`; with airplane mode + wifi disabled (no active default network), `connected` stayed `ENQUEUED` while `not_required` ran `RUNNING` → `SUCCEEDED`, proving the constraint actually gates execution. The post-restore `connected` attempt hit MIUI's `proc frequent died!` / `process is bad` throttle (worker process never launched); the same APK ran all workers fine before that, so it is the known platform throttle, not a feature bug. |
| Battery / storage / idle constraints | `d84700ce` | `Work(battery_not_low=..., storage_not_low=..., device_idle=...)` maps to `setRequiresBatteryNotLow` / `setRequiresStorageNotLow` / `setRequiresDeviceIdle`. An 18-arg `schedule()` overload carries the three flags (older overloads delegate with `false,false,false`), chain steps read the three keys, and the UI gains battery/storage/idle checkboxes. Java skips `setBackoffCriteria()` for `device_idle` work — WorkManager throws `IllegalArgumentException: Cannot set backoff criteria on an idle mode job` otherwise. Device baseline (battery 97, storage 34 GB free, `mState=ACTIVE`): battery/storage/free all `SUCCEEDED` while idle stayed `ENQUEUED`. With `dumpsys battery unplug` + `set level 5` (`Battery not low: false`): battery work stayed `ENQUEUED` while storage/free ran and finished `SUCCEEDED`. Storage has no safe low-storage mock, so it has baseline evidence only. `dumpsys deviceidle force-idle` was attempted but the run hit the MIUI process-bad throttle, so the idle→running direction was not directly observed; the ACTIVE-device `ENQUEUED` result proves the gate. All device settings restored. |

## Missing

| Feature | State | Notes |
|---|---|---|
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
  dist. When `Worker.tmpl.java` or `PythonWorker.java` changes, refresh all
  cached copies under `.buildozer/android/platform/build-arm64-v8a/`:
  `dists/workmanagertest/templates/Worker.tmpl.java`,
  `dists/workmanagertest/src/main/java/org/kivy/android/PythonWorker.java`,
  `build/bootstrap_builds/sdl3/templates/Worker.tmpl.java` and
  `build/bootstrap_builds/sdl3/src/main/java/org/kivy/android/PythonWorker.java`,
  otherwise the APK keeps the stale Java. The two template copies are easy to
  miss — only refreshing the `dists` one is not enough.
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
- `append` on a unique name whose last work is already in a terminal state
  throws `IllegalStateException` from WorkManager; use `append_or_replace` for
  re-scheduling after a chain finishes. The UI shows the failure in its log
  area rather than crashing.
- Non-unique work uses the work `name` as an auto-added tag for lookup and
  cancellation, on top of custom tags. WorkManager allows 10 tags per request,
  so Python caps custom tags at 9 when `unique=False`. `policy` is ignored for
  non-unique work because `enqueue()` has no policy argument.
- On this MIUI device, `cmd connectivity airplane-mode enable` does **not** drop
  wifi — an active default network remains, so a `CONNECTED` work still runs.
  To simulate "no network" for constraint tests, disable both:
  `cmd connectivity airplane-mode enable` **and** `svc wifi disable`; confirm
  with `dumpsys connectivity | grep 'Active default network'`. Restore with
  `cmd connectivity airplane-mode disable` + `svc wifi enable`.
- WorkManager rejects `setBackoffCriteria()` on jobs with
  `setRequiresDeviceIdle(true)` (`IllegalArgumentException: Cannot set backoff
  criteria on an idle mode job`). The generated Java now skips backoff for idle
  work in both `schedule()` and `scheduleChain()`; retry/backoff settings are
  silently ignored for those requests.
- `dumpsys battery unplug` + `dumpsys battery set level 5` makes
  `dumpsys jobscheduler` report `Battery not low: false` and held the
  battery-constrained work. Restore with `dumpsys battery reset`. There is no
  safe low-storage mock, so `storage_not_low` has baseline evidence only.

## Suggested order for the next features

1. Expedited work / foreground long-running work.
3. Data propagation between chained steps (parent output into child input).
