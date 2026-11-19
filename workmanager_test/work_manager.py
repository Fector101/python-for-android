"""Small Python API for p4a's WorkManager workers.

The p4a fork must be built with at least one worker, e.g.::

    --worker=script:./workers/heartbeat.py

That generates ``<package>.ScriptWorker``. A single generated worker can run
any bundled script because the script path is part of the WorkRequest input
data; ``PYTHON_SERVICE_ARGUMENT`` carries a JSON string with user arguments.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

_SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_MAX_SCRIPT_LENGTH = 120  # start.c ENTRYPOINT_MAXLEN is 128.
# androidx.work.Data.MAX_DATA_BYTES, and a reserve for the other entries the
# generated worker puts in the same Data (script, package and service class).
_MAX_DATA_BYTES = 10 * 1024
_DATA_OVERHEAD_BYTES = 512
_MAX_ARGUMENT_BYTES = _MAX_DATA_BYTES - _DATA_OVERHEAD_BYTES
_TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "CANCELLED"})


@dataclass(frozen=True)
class WorkInfo:
    """Read-only snapshot of one WorkManager work-info row."""

    id: str = ""
    state: str = "UNKNOWN"
    run_attempt_count: int = 0
    generation: int = 0
    tags: tuple = ()
    output: Dict[str, Any] = field(default_factory=dict)
    progress: Dict[str, Any] = field(default_factory=dict)
    initial_delay_ms: int = 0
    next_schedule_time_ms: int = 0
    stop_reason: int = 0
    stop_reason_name: str = "NOT_STOPPED"


@dataclass(frozen=True)
class WorkInfos:
    """All work-info rows returned for a unique work name."""

    found: bool = False
    infos: tuple = ()
    error: Optional[str] = None


def _autoclass(name: str):
    """Import jnius only when actually running on Android."""
    try:
        from jnius import autoclass
    except Exception as exc:  # pragma: no cover - desktop fallback
        raise RuntimeError(
            "Work requires a p4a Android build with jnius available"
        ) from exc
    return autoclass(name)


def _context():
    """Return the application context, preferring p4a's activity reference."""
    try:
        from android import mActivity  # type: ignore

        if mActivity is not None:
            return mActivity.getApplicationContext()
    except Exception:
        pass

    PythonActivity = _autoclass("org.kivy.android.PythonActivity")
    return PythonActivity.mActivity.getApplicationContext()


def _worker_class(worker_name: str = "script"):
    package = str(_context().getPackageName())
    class_name = "{}.{}Worker".format(package, worker_name.capitalize())
    return _autoclass(class_name)


def _validate_worker_name(worker_name: str) -> str:
    if not isinstance(worker_name, str) or not worker_name:
        raise ValueError("worker_name must be a non-empty string")
    if not worker_name.replace("_", "").isalnum() or worker_name[0].isdigit():
        raise ValueError(
            "worker_name must be a Java identifier (letters, digits and "
            "underscores, not starting with a digit)"
        )
    return worker_name


def _validate_script(script: str) -> str:
    if not isinstance(script, str) or not script:
        raise ValueError("script must be a non-empty relative path")
    script = script.replace("\\", "/")
    if posixpath.isabs(script) or re.match(r"^[A-Za-z]:", script):
        raise ValueError("script must be relative to the p4a files/app root")
    parts = [part for part in script.split("/") if part not in ("", ".")]
    if not parts or ".." in parts:
        raise ValueError("script must not contain '..' path segments")
    if not script.lower().endswith((".py", ".pyc")):
        raise ValueError("script must end with .py or .pyc")
    normalized = "/".join(parts)
    if len(normalized) > _MAX_SCRIPT_LENGTH:
        raise ValueError(
            "script path is too long (max {} characters)".format(_MAX_SCRIPT_LENGTH)
        )
    return normalized


@dataclass
class Work:
    """Schedule a bundled Python script with WorkManager.

    Args:
        name: Unique work name used by ``schedule()``/``cancel()``/``get_info()``.
        script: Path relative to the unpacked ``files/app`` directory.
        args: JSON-serialisable value exposed to the script as
            ``PYTHON_SERVICE_ARGUMENT``.
        delay_seconds: Initial delay for one-time work.
        interval_minutes: Interval for periodic work. Omit for one-time work;
            WorkManager enforces a 15-minute minimum.
        network_required: Require a connected network.
        charging_required: Require the device to be charging.
        policy: ``"keep"`` or ``"replace"`` for an existing unique work name.
        backoff_policy: ``"exponential"`` (WorkManager default) or ``"linear"``
            for retries requested by the worker via ``work_result.request_retry``.
        backoff_delay_seconds: Initial retry delay, clamped by WorkManager to
            10 seconds .. 24 hours (1 .. 86400 accepted here).
        worker_name: Name passed to p4a's ``--worker`` build argument. The
            default matches ``--worker=script:...``.
    """

    name: str
    script: str
    args: Optional[Any] = None
    delay_seconds: int = 0
    interval_minutes: Optional[int] = None
    network_required: bool = False
    charging_required: bool = False
    policy: str = "keep"
    backoff_policy: str = "exponential"
    backoff_delay_seconds: int = 30
    worker_name: str = "script"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a non-empty string")
        if not _SAFE_NAME_RE.match(self.name):
            raise ValueError(
                "name may only contain letters, digits, '.', '_' and '-', "
                "and must start with a letter"
            )
        self.script = _validate_script(self.script)
        self.worker_name = _validate_worker_name(self.worker_name)
        self.delay_seconds = int(self.delay_seconds)
        if self.delay_seconds < 0:
            raise ValueError("delay_seconds must be >= 0")
        if self.interval_minutes is not None:
            self.interval_minutes = int(self.interval_minutes)
            if self.interval_minutes < 15:
                raise ValueError(
                    "WorkManager periodic work requires interval_minutes >= 15"
                )
        self.policy = self.policy.lower()
        if self.policy not in ("keep", "replace"):
            raise ValueError("policy must be 'keep' or 'replace'")
        self.backoff_policy = self.backoff_policy.lower()
        if self.backoff_policy not in ("exponential", "linear"):
            raise ValueError(
                "backoff_policy must be 'exponential' or 'linear'"
            )
        try:
            self.backoff_delay_seconds = int(self.backoff_delay_seconds)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "backoff_delay_seconds must be between 1 and 86400"
            ) from exc
        if not 1 <= self.backoff_delay_seconds <= 86400:
            raise ValueError(
                "backoff_delay_seconds must be between 1 and 86400"
            )

    @property
    def is_periodic(self) -> bool:
        return self.interval_minutes is not None

    def argument_json(self) -> str:
        """Return the JSON string placed in PYTHON_SERVICE_ARGUMENT."""
        try:
            payload = json.dumps(
                self.args if self.args is not None else {},
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Work args must be JSON-serialisable") from exc
        size = len(payload.encode("utf-8"))
        if size > _MAX_ARGUMENT_BYTES:
            raise ValueError(
                "Work args are too large for WorkManager Data: {} bytes "
                "(max {} for PYTHON_SERVICE_ARGUMENT, limit {} bytes)".format(
                    size, _MAX_ARGUMENT_BYTES, _MAX_DATA_BYTES
                )
            )
        return payload

    def schedule(self) -> "Work":
        worker = _worker_class(self.worker_name)
        worker.schedule(
            _context(),
            self.name,
            self.script,
            self.argument_json(),
            self.is_periodic,
            self.delay_seconds,
            self.interval_minutes or 0,
            bool(self.network_required),
            bool(self.charging_required),
            self.policy,
            self.backoff_policy,
            self.backoff_delay_seconds,
        )
        return self

    def cancel(self) -> None:
        cancel(self.name, worker_name=self.worker_name)

    def get_info(self) -> str:
        return get_info(self.name, worker_name=self.worker_name)

    def get_work_info(self) -> Optional[WorkInfo]:
        return get_work_info(self.name, worker_name=self.worker_name)

    def get_work_infos(self) -> WorkInfos:
        return get_work_infos(self.name, worker_name=self.worker_name)


def schedule(name: str, script: str, **kwargs: Any) -> Work:
    """Convenience wrapper around ``Work(...).schedule()``."""
    return Work(name=name, script=script, **kwargs).schedule()


def cancel(name: str, worker_name: str = "script") -> None:
    """Cancel a unique work request by name."""
    _worker_class(_validate_worker_name(worker_name)).cancel(_context(), name)


def cancel_all(worker_name: str = "script") -> None:
    """Cancel all WorkManager work for this app."""
    _worker_class(_validate_worker_name(worker_name)).cancelAll(_context())


def get_info(name: str, worker_name: str = "script") -> str:
    """Return the first WorkInfo state for ``name`` as a string."""
    return _worker_class(_validate_worker_name(worker_name)).getStatus(
        _context(), name
    )


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _normalise_result_data(value: Any) -> Dict[str, Any]:
    """Unwrap the JSON string written by a worker's set_output/set_progress.

    WorkManager Data only holds primitives, so the Java side stores the worker's
    JSON object as a string under PYTHON_WORK_OUTPUT / PYTHON_WORK_PROGRESS.
    Plain Data keys are passed through unchanged.
    """
    data = _as_dict(value)
    for key in ("PYTHON_WORK_OUTPUT", "PYTHON_WORK_PROGRESS"):
        raw = data.get(key)
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                return parsed
    return data


def _parse_info_json(raw: str) -> WorkInfos:
    """Parse the JSON produced by ``ScriptWorker.getInfoJson``."""
    try:
        payload = json.loads(raw) if isinstance(raw, str) else {}
    except (TypeError, ValueError) as exc:
        raise ValueError("Work info response was not JSON: {!r}".format(raw)) from exc
    if not isinstance(payload, dict):
        raise ValueError("Work info response was not a JSON object")

    rows = []
    for item in payload.get("infos") or []:
        if not isinstance(item, dict):
            continue
        tags = item.get("tags") or []
        rows.append(WorkInfo(
            id=str(item.get("id", "")),
            state=str(item.get("state", "UNKNOWN")),
            run_attempt_count=_as_int(item.get("runAttemptCount")),
            generation=_as_int(item.get("generation")),
            tags=tuple(str(tag) for tag in tags) if isinstance(tags, list) else (),
            output=_normalise_result_data(item.get("output")),
            progress=_normalise_result_data(item.get("progress")),
            initial_delay_ms=_as_int(item.get("initialDelayMillis")),
            next_schedule_time_ms=_as_int(item.get("nextScheduleTimeMillis")),
            stop_reason=_as_int(item.get("stopReason")),
            stop_reason_name=str(item.get("stopReasonName", "UNKNOWN")),
        ))
    error = payload.get("error")
    return WorkInfos(
        found=bool(payload.get("found")),
        infos=tuple(rows),
        error=str(error) if error else None,
    )


def get_work_infos(name: str, worker_name: str = "script") -> WorkInfos:
    """Return every WorkManager work-info row for ``name``."""
    raw = _worker_class(_validate_worker_name(worker_name)).getInfoJson(
        _context(), name
    )
    return _parse_info_json(raw)


def get_work_info(name: str, worker_name: str = "script") -> Optional[WorkInfo]:
    """Return the active row for ``name``, or the newest row if all finished."""
    infos = get_work_infos(name, worker_name=worker_name).infos
    if not infos:
        return None
    for info in infos:
        if info.state not in _TERMINAL_STATES:
            return info
    return infos[0]
