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
from dataclasses import dataclass
from typing import Any, Dict, Optional

_SAFE_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
_MAX_SCRIPT_LENGTH = 120  # start.c ENTRYPOINT_MAXLEN is 128.


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

    @property
    def is_periodic(self) -> bool:
        return self.interval_minutes is not None

    def argument_json(self) -> str:
        """Return the JSON string placed in PYTHON_SERVICE_ARGUMENT."""
        try:
            return json.dumps(
                self.args if self.args is not None else {},
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Work args must be JSON-serialisable") from exc

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
        )
        return self

    def cancel(self) -> None:
        cancel(self.name, worker_name=self.worker_name)

    def get_info(self) -> str:
        return get_info(self.name, worker_name=self.worker_name)


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
