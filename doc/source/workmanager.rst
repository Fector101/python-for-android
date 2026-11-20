WorkManager workers
===================

python-for-android can generate AndroidX WorkManager workers that run bundled
Python scripts. Use this when you need deferrable, guaranteed background work:
constraints (network, charging, battery, storage, idle), retries with backoff,
periodic execution, or chains of dependent steps.

This is a different mechanism from :doc:`services`. A WorkManager worker is
declared at build time with ``--worker``, is hosted by a generated
``RemoteWorkerService``, and runs in its own ``:worker_<name>`` process. You do
not add a p4a ``services = ...`` entry, and you do not call ``startService()``
from Python.

.. note::

    The Python helpers shown below (``work_manager.py`` and
    ``work_result.py``) are reference implementations shipped in
    ``workmanager_test/``. python-for-android generates the Java API but does
    not install a Python package; copy those two files into your app, or write
    equivalent wrappers around the generated Java classes.

Build configuration
-------------------

Declare at least one worker when building. Pass ``--worker=NAME:PATH`` to
``p4a apk``, or add it to ``p4a.extra_args`` in ``buildozer.spec``::

    [app]
    p4a.extra_args = --worker=script:./workers/heartbeat.py

``NAME`` must be a Java identifier (letters, digits and underscores, not
starting with a digit). ``PATH`` is relative to your app source directory and
points at the script to run. Keep the path short (under 120 characters),
because it is passed to the native entrypoint.

The build generates two Java classes for each spec:

* ``<package>.<Name>Worker`` — extends ``PythonWorker`` (a
  ``RemoteListenableWorker``). This is the class you schedule against.
* ``<package>.<Name>WorkerService`` — the ``RemoteWorkerService`` host that
  keeps WorkManager's multiprocess IPC in its own process.

The manifest service, the ``androidx.work:work-runtime`` and
``work-multiprocess`` dependencies, and the foreground service declaration are
added automatically. The WorkManager version is selected from the target API
(2.9.0 for API 31+, otherwise 2.6.0).

Multiple worker classes
~~~~~~~~~~~~~~~~~~~~~~~

Repeat ``--worker`` to generate distinct classes and processes::

    p4a.extra_args = --worker=script:./workers/heartbeat.py --worker=audit:./workers/audit.py

This produces ``ScriptWorker`` in ``:worker_script`` and ``AuditWorker`` in
``:worker_audit``. Select a class from Python with ``worker_name="audit"``
(the default is ``"script"``). Any generated class can run any bundled script:
the script path is part of each work request, so ``worker_name`` chooses the
worker process/class, not the script.

Writing the worker script
-------------------------

The script is executed with ``runpy.run_path()`` as ``__main__``. Its argument
is available as the ``PYTHON_SERVICE_ARGUMENT`` environment variable, a JSON
string. Decode it with the ``json`` module::

    # workers/heartbeat.py
    import json
    import os

    from work_result import set_output

    payload = json.loads(os.environ.get("PYTHON_SERVICE_ARGUMENT", "") or "{}")
    message = payload.get("message", "hello")

    print("heartbeat: {}".format(message), flush=True)
    set_output({"message": message})

A clean exit (falling off the end, ``return`` from ``main()``, or
``sys.exit(0)``) makes WorkManager mark the work ``SUCCEEDED``. A non-zero
``SystemExit`` code or an uncaught exception marks it ``FAILED``. Do not call
``os._exit()`` or kill the process yourself: Java needs to complete the
WorkManager future.

.. note::

    ``PythonActivity.mActivity`` is ``null`` in the worker process. Libraries
    that need an Android ``Context`` can use
    ``autoclass('org.kivy.android.PythonWorker').getWorkerContext()``.

Scheduling from Python
----------------------

The reference helper in ``workmanager_test/work_manager.py`` wraps the
generated Java methods with jnius. Copy it into your app and import it::

    from work_manager import Work

    Work(
        name="heartbeat_once",
        script="workers/heartbeat.py",
        args={"message": "hello"},
        delay_seconds=10,
    ).schedule()

``script`` is the path relative to the unpacked app root (``files/app``).
``args`` must be JSON-serialisable; WorkManager limits the request ``Data`` to
about 10 KB, so keep arguments small.

Options for ``Work``
~~~~~~~~~~~~~~~~~~~~

* ``name`` — unique work name used for scheduling, querying and cancelling.
* ``script`` — bundled worker script path.
* ``args`` — JSON-serialisable value exposed as ``PYTHON_SERVICE_ARGUMENT``.
* ``delay_seconds`` — initial delay for one-time work.
* ``interval_minutes`` — set for periodic work; WorkManager enforces a
  15-minute minimum.
* ``network_required`` / ``network_type`` — require a network of type
  ``connected`` (default), ``unmetered``, ``not_roaming`` or
  ``not_required``.
* ``charging_required``, ``battery_not_low``, ``storage_not_low``,
  ``device_idle`` — additional constraints.
* ``policy`` — what to do if ``name`` exists: one-time work accepts
  ``keep`` (default), ``replace``, ``append``, ``append_or_replace``;
  periodic work accepts ``keep``, ``replace``, ``update``.
* ``backoff_policy`` / ``backoff_delay_seconds`` — ``exponential`` or
  ``linear``, with a delay clamped by WorkManager to 10 seconds .. 24 hours.
* ``tags`` — up to 10 custom strings, queryable with
  ``get_work_infos_by_tag()``.
* ``unique`` — when false, work is enqueued with ``enqueue()`` and ``name``
  becomes a tag; ``policy`` is ignored.
* ``expedited`` / ``expedited_policy`` — higher-priority one-time work
  (foreground service on Android 12+). Expedited work cannot be periodic,
  delayed, or require charging/battery/idle. The policy is
  ``run_as_non_expedited`` or ``drop`` when the app is out of quota.
* ``worker_name`` — selects the generated worker class (default
  ``"script"``).

Some examples::

    # Periodic work that only runs on an unmetered network while charging.
    Work(
        name="nightly_sync",
        script="workers/sync.py",
        interval_minutes=60,
        network_required=True,
        network_type="unmetered",
        charging_required=True,
        policy="replace",
    ).schedule()

    # Tagged, non-unique work: many runs can exist under the same name.
    Work(
        name="cleanup",
        script="workers/cleanup.py",
        tags=["maintenance"],
        unique=False,
    ).schedule()

    # Use a second generated worker class.
    Work(
        name="audit_once",
        script="workers/audit.py",
        worker_name="audit",
    ).schedule()

Direct jnius usage
~~~~~~~~~~~~~~~~~~

You can skip the helper and call the generated class directly. The full
``schedule()`` signature is long, but the class also has shorter overloads::

    from jnius import autoclass

    Worker = autoclass("org.example.myapp.ScriptWorker")
    activity = autoclass("org.kivy.android.PythonActivity").mActivity
    context = activity.getApplicationContext()

    Worker.schedule(
        context,                 # Context
        "heartbeat_once",        # unique name
        "workers/heartbeat.py",  # script path
        '{"message": "hello"}',  # PYTHON_SERVICE_ARGUMENT as JSON
        False,                   # periodic
        10,                      # delay seconds
        0,                       # interval minutes
        False,                   # network required
        False,                   # charging required
        "keep",                  # ExistingWorkPolicy
    )

The other static methods are ``cancel(context, name)``,
``cancelAll(context)``, ``cancelByTag(context, tag)``,
``getStatus(context, name)``, ``getInfoJson(context, name)``,
``getInfoJsonByTag(context, tag)`` and
``scheduleChain(context, name, policy, stepsJson)``.

Chained work
------------

Chain one-time steps with ``then()``. Each step starts after the previous one
succeeds; a failed or retried step blocks the rest::

    from work_manager import Work

    (
        Work(
            name="pipeline",
            script="workers/fetch.py",
            args={"url": "https://example.com/data"},
        )
        .then(Work(script="workers/parse.py"))
        .then(Work(script="workers/publish.py"))
        .schedule()
    )

The first step supplies the chain's ``name``, ``policy`` and ``worker_name``;
later steps provide their own script, arguments, delays, constraints, backoff
and tags. All steps must use the same generated worker class. A chain needs at
least two and at most ten steps. Periodic and expedited steps are not allowed.

Passing output from one step to the next
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

WorkManager merges a successful step's output ``Data`` into the next step's
input. The worker writes that value (the ``PYTHON_WORK_OUTPUT`` key) to
``work_data/<script>/parent_output.json`` before the Python script starts, and
``work_result.parent_output()`` reads it::

    # workers/parse.py
    from work_result import parent_output, set_output

    previous = parent_output()
    print("previous step: {}".format(previous), flush=True)
    set_output({"step": "parse", "from_fetch": previous.get("url")})

``parent_output()`` returns ``{}`` for the first step, for invalid JSON, or
when the previous step failed. Only successful predecessors propagate data,
and WorkManager's 10 KB ``Data`` cap applies before propagation: oversized
output is dropped.

Output, progress and retry
--------------------------

The ``work_result.py`` helper exchanges small JSON files with Java through a
per-script directory under ``files/app/work_data/``:

* ``set_output(dict)`` — published as ``WorkInfo.output`` when the script
  exits cleanly. Java reads ``output.json`` after the script finishes.
* ``set_progress(dict)`` — published as ``WorkInfo.progress``; Java polls
  ``progress.json`` every 300 ms.
* ``request_retry(reason="")`` — asks WorkManager to retry the work using the
  configured backoff policy. The retry file takes precedence over a clean exit
  status, and must be written on every attempt that wants a retry.
* ``attempt()`` — a 1-based attempt counter that survives retries.
* ``parent_output()`` — the previous chain step's output, as described above.

All result values are JSON strings inside WorkManager ``Data``, so keep each
one below the 10 KB limit. Java drops oversized data rather than failing the
work.

.. warning::

    The exchange directory is keyed by script path, not by worker class or
    chain step. Chained steps using the same script share it; that is safe
    because a chain is sequential and Java overwrites ``parent_output.json``
    at the start of each step. Two independent jobs using the same script at
    the same time can overwrite each other's result files.

Querying and cancelling
-----------------------

The helper returns typed snapshots::

    from work_manager import get_info, get_work_info, get_work_infos, cancel

    print(get_info("heartbeat_once"))          # just the state string
    info = get_work_info("heartbeat_once")
    if info is not None:
        print(info.state, info.run_attempt_count, info.output, info.progress)

    for row in get_work_infos("heartbeat_once").infos:
        print(row.id, row.state, row.tags, row.stop_reason_name)

    cancel("heartbeat_once")

``WorkInfo`` exposes ``id``, ``state``, ``run_attempt_count``, ``generation``,
``tags``, ``output``, ``progress``, ``initial_delay_ms``,
``next_schedule_time_ms``, ``stop_reason`` and ``stop_reason_name``. A work
name can have several rows (for example after ``replace`` or ``append``), so
``get_work_infos()`` returns all of them; ``get_work_info()`` returns the
active row, or the newest finished row. ``get_work_infos_by_tag(tag)`` queries
by tag instead of name.

Cancellation helpers are ``cancel(name)``, ``cancel_all()`` and
``cancel_by_tag(tag)``. ``Work`` and ``WorkChain`` objects also have
``cancel()``, ``get_info()``, ``get_work_info()`` and ``get_work_infos()``
methods that remember the right ``worker_name``.

.. note::

    WorkManager only sets a stop reason when a worker that was actually
    running is stopped. A job that is merely ``ENQUEUED`` while waiting for a
    constraint correctly reports ``NOT_STOPPED``.

Limitations
-----------

* A p4a process can initialise CPython only once, so each generated worker
  service runs in its own process and work requests reuse that process.
* Cancelling a running worker exits its process; there is no way to interrupt
  a Python thread from Java.
* Worker scripts are found relative to the app root; imports from the app root
  work normally (for example ``from workers.helpers import ...``).
* A generated class can only be selected if its ``--worker`` spec was present
  at build time. Changing specs requires a rebuild, not just a Python change.
* The reference app in ``workmanager_test/`` contains a complete, tested
  example with one-time, periodic, constrained, retrying, foreground,
  tagged, multi-worker and chained jobs.
