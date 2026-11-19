# p4a WorkManager worker API (PR #2613 port)

Status 2026-11-19: implementation complete in the local p4a fork and the
`workmanager_test/` app. Final APK verified on device `H6YPAAWSYLP7CAIN`
(`heartbeat_once SUCCEEDED`, `failing_once FAILED`). `android_notify` was
patched to work from the worker and the notification call is restored in
`workers/heartbeat.py`; device verification showed an active `NotificationRecord`
with title `auto from device test` from the `:worker_script` process.

## Goal

Run arbitrary bundled Python scripts from WorkManager without adding a p4a
`services = ...` entry and without starting a p4a `Service` from Python.
Based on closed upstream p4a PR #2613, but adapted to the current 2026 checkout
(SDL3, Gradle 8.11/AGP 8.11, `.pyc` packaging, `service_data` manifests).

## Local p4a patch (uncommitted)

`/home/fabian/Documents/widget/python-for-android`:

- `common/build/src/main/java/org/kivy/android/PythonWorker.java`
  - `RemoteListenableWorker`; runs the script on a Java thread.
  - `PYTHON_WORK_SCRIPT` overrides the build-time entrypoint, so one generated
    worker can run any bundled script.
  - `PYTHON_SERVICE_ARGUMENT` carries a JSON string with script args.
  - `nativeStart()` returns `int`; 0 -> `Result.success()`, else `Result.failure()`.
- `common/build/jni/application/src/start.c`
  - `run_python(argc, argv, call_exit)` shared by app/service/worker.
  - `main()` and `Java_org_kivy_android_PythonService_nativeStart` use
    `call_exit=true`; `Java_org_kivy_android_PythonWorker_nativeStart` uses
    `call_exit=false`.
  - Worker scripts are run with `runpy.run_path(..., run_name="__main__")`,
    which catches `SystemExit(code)` and stores it in
    `sys.p4a_worker_exit_code`. This is necessary because `PyRun_SimpleFile()`
    itself honours `SystemExit` and would kill the remote process before Java
    can complete the WorkManager future. `runpy` also supports p4a's `.pyc`
    entrypoints. The resolved path is passed through
    `sys.p4a_worker_entrypoint`; `os.environ` is a snapshot from interpreter
    startup, so a C `setenv()` after `Py_Initialize()` is invisible to Python.
- `PythonService.java`: `nativeStart` declaration changed `void` -> `int`.
- `common/build/build.py`: `--worker=NAME:PATH_TO_PY`; generates
  `NAMEWorker.java` + `NAMEWorkerService.java`; passes `worker_names` to the
  manifest and `work_manager_version` to Gradle; forces AndroidX when workers
  are declared.
- Templates: `Worker.tmpl.java`, `WorkerService.tmpl.java`,
  `build.tmpl.gradle` (work-runtime + work-multiprocess 2.9.0 for API >= 31),
  and worker-service declarations in `_sdl_common`, `service_library`,
  `service_only`, `webview`, `qt` manifests.
- Generated worker service runs in `:worker_<name>`, is `exported=false`,
  `stopWithTask=true`, and calls `System.exit(0)` in `onDestroy()` because p4a
  cannot initialise CPython twice in one process.

## Test app

`/home/fabian/Documents/python-android/workmanager_test/`:

- `buildozer.spec` uses the patched p4a via `p4a.source_dir`, `p4a.bootstrap =
  sdl3`, local Kivy source, and
  `p4a.extra_args = --skip-prebuilt --worker=script:./workers/heartbeat.py`.
- `work_manager.py` exposes `Work(name, script, args=..., delay_seconds=...,
  interval_minutes=..., policy=...).schedule()` plus `cancel()`, `cancel_all()`,
  `get_info()`. It calls static helpers on the generated `<name|capitalize>Worker`
  class, so jnius never needs a Java class literal.
- `workers/heartbeat.py` logs `WORKER_MARKER ...` and sends an
  `android_notify` notification in a `try/except` that prints
  `the worker file: ...` on failure; `workers/failing.py` returns exit code 3
  to verify `FAILED`.
- The local `android_notify/` package under `workmanager_test/` is copied to
  `files/app/` and shadows the recipe-installed copy in site-packages (app root
  is first on `PYTHONPATH`). It was added after the first final APK, so builds
  before that did not contain it.
- `python -m pytest workmanager_test/tests -q` passes 15 tests on desktop with
  monkeypatched `_context()`/`_autoclass()`; no module-level jnius import.

Build command (from `workmanager_test/`):

```bash
VIRTUAL_ENV=/home/fabian/Documents/python-android/venv \
PATH="/home/fabian/Documents/python-android/venv/bin:$PATH" \
/home/fabian/Documents/python-android/venv/bin/buildozer android debug
```

## Gotchas

- This is **not** a p4a app `Service`; `RemoteWorkerService` is AndroidX
  WorkManager multiprocess plumbing. It is acceptable under the user's
  "no service" constraint.
- WorkManager periodic minimum is 15 minutes; `Work` validates that.
- `--worker` only names the generated Java worker; the script itself is bundled
  because it lives under `source.dir`. The path at runtime is relative to
  `files/app`.
- Newer p4a compiles `.py` to `.pyc`; `run_python()` prefers `.pyc` and falls
  back to `.py`. `runpy.run_path()` must be given the **resolved** path:
  passing the requested `.py` name fails on device because only `.pyc` is
  bundled. The resolved path is handed to Python through
  `sys.p4a_worker_entrypoint`; `os.environ` is a snapshot from interpreter
  startup, so a C `setenv()` after `Py_Initialize()` is invisible to Python.
- Worker Python logs use the logcat tag set by `PYTHON_NAME` (here `script`),
  not `python`. Filtering logcat on `python:I` hides all worker prints and
  tracebacks. Use `*:S` with both tags, or capture the full log.
- Two one-time jobs scheduled at once both call `nativeStart()` in the same
  `:worker_script` process. `PythonWorker.java` now serializes calls with a
  static lock because p4a cannot initialise CPython in two threads at once.
- When overriding `files/app/main.py` on device, delete `files/app/main.pyc`
  too; p4a executes the cached bytecode and ignores the overridden `.py`.
- Do not add a module-level `__getattr__` to Python helper modules; use lazy
  functions/autoclass calls (existing p4a startup footgun).
- WorkManager 2.9.0 is used for API >= 31; 2.6.0 is kept for older APIs.
- `PythonWorker.java` must explicitly import `androidx.work.WorkerParameters`;
  extending `RemoteListenableWorker` does not put it in scope. Without it the
  Gradle compile fails with `cannot find symbol WorkerParameters` at the
  constructor.
- p4a native build access tree for SDL3:
  `buildozer android debug` -> `p4a create` -> `Context.prepare_bootstrap()` ->
  `bootstrap.py:prepare_build_dir()`/`copy_files()` copies patched bootstrap
  files into `build/bootstrap_builds/sdl3`; `build_recipes()` ->
  `recipes/sdl3/__init__.py:LibSDL3Recipe.should_build()` runs `ndk-build` only
  if any of five SDL libs is missing; `bootstrap.py:assemble_distribution()`
  copies the whole bootstrap build into `dists/workmanagertest`; `p4a apk` runs
  Gradle on that dist and packages `dists/.../libs/arm64-v8a/libmain.so`.
- Deleting only `dists/<dist_name>` is enough after changing Java/templates,
  but **not** after changing `start.c`: `prepare_build_dir()` refreshes the C
  source while `LibSDL3Recipe.should_build()` still sees all five
  `build/bootstrap_builds/sdl3/libs/arm64-v8a/*.so` and skips `ndk-build`, so
  the old `start.o`/`libmain.so` get copied into the new dist. For native
  changes, also delete `bootstrap_builds/sdl3/libs/arm64-v8a/libmain.so`,
  `bootstrap_builds/sdl3/obj/local/arm64-v8a/libmain.so`, and
  `bootstrap_builds/sdl3/obj/local/arm64-v8a/objs-debug/main/start.o`.
- Confirm native changes with `strings ... | grep p4a_worker_entrypoint` on
  `start.o`, `obj/local/arm64-v8a/libmain.so`,
  `libs/arm64-v8a/libmain.so`, and the APK's `lib/arm64-v8a/libmain.so`
  (`unzip -p APK ... | strings`). Timestamps alone lie because `cp -r` into
  the dist refreshes mtimes for stale artifacts.
- Keep the isolated `workmanager_test/buildozer.spec`; do not repurpose the root
  `buildozer.spec` (it currently targets `/Melo/app_src` / `kivyuritest`). If
  cache reuse is wanted later, add `build_dir = ../.buildozer` to the test spec
  instead, while keeping one arch so the p4a `build-arm64-v8a` tree stays
  separate from the root app's `build-arm64-v8a_armeabi-v7a`.
- `android-notify` is pure Python and only needs to be in `requirements`; no
  custom recipe/config is required. A build started before the requirement was
  added generated `p4a create --requirements=python3,kivy==master` and the
  worker failed with `No module named 'android_notify'`. Once added, p4a sends
  it to the pip stage and stores it in `dist_info.json`'s `recipes` list (which
  also holds pure-Python modules). The current test spec no longer lists
  `android-notify` because the patched local package is bundled directly from
  `source.dir`; an existing dist may still carry the older recipe copy in
  site-packages, but `files/app` wins on `sys.path`.
- `android_notify` worker fix: `start.c:619` sets `PYTHON_SERVICE_ARGUMENT` for
  workers too, so `config.from_service_file()` misclassified the worker as a
  p4a service and `get_python_activity_context()` read
  `PythonService.mService` (null in `:worker_script`) ->
  `'NoneType' object has no attribute 'getApplication'`. `PythonActivity.mActivity`
  is also null there, so flipping `from_service_file()` alone is not enough.
  The patched package keeps the service classification (it correctly skips
  permission prompts and intent-listener binding) and adds
  `from_worker_file()` based on `sys.p4a_worker_entrypoint`. That branch uses
  the new `PythonWorker.getWorkerContext()` static context exposed by the p4a
  `PythonWorker.java` constructor. `get_python_activity_context()` checks
  worker first, then service, then activity. `PythonWorker.java` changes need
  `rm -rf dists/workmanagertest` before rebuilding, otherwise the stale Java
  source in the dist is compiled.
- The test app declares `android.permissions = POST_NOTIFICATIONS` in its spec.
  Without it Android 13+ blocks every `notify()` regardless of the worker fix
  (`dumpsys notification` shows `numBlocked` increasing and
  `numPostedByApp=0`). On this MIUI device the appop is named
  `POST_NOTIFICATION` (singular) and also has to be set to `allow`; `pm grant`
  alone did not unblock it.
