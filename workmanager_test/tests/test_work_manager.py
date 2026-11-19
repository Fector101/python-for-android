import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import work_manager  # noqa: E402


class FakeContext:
    def getPackageName(self):
        return "io.github.fector101.workmanagertest"


@pytest.fixture
def java(monkeypatch):
    calls = {}

    class FakeWorker:
        @staticmethod
        def schedule(*args):
            calls["schedule"] = args

        @staticmethod
        def cancel(*args):
            calls["cancel"] = args

        @staticmethod
        def cancelAll(*args):
            calls["cancelAll"] = args

        @staticmethod
        def getStatus(*args):
            calls["getStatus"] = args
            return "SUCCEEDED"

    def fake_autoclass(name):
        calls.setdefault("autoclass", []).append(name)
        return FakeWorker

    monkeypatch.setattr(work_manager, "_context", lambda: FakeContext())
    monkeypatch.setattr(work_manager, "_autoclass", fake_autoclass)
    return FakeWorker, calls


def test_one_time_schedule_arguments(java):
    _, calls = java
    work = work_manager.Work(
        name="heartbeat_once",
        script="./workers/heartbeat.py",
        args={"message": "hi"},
        delay_seconds=10,
        policy="replace",
    )

    assert work.schedule() is work
    context, name, script, data, periodic, delay, interval, network, charging, policy = \
        calls["schedule"]
    assert isinstance(context, FakeContext)
    assert name == "heartbeat_once"
    assert script == "workers/heartbeat.py"
    assert json.loads(data) == {"message": "hi"}
    assert periodic is False
    assert delay == 10
    assert interval == 0
    assert network is False
    assert charging is False
    assert policy == "replace"
    assert calls["autoclass"] == [
        "io.github.fector101.workmanagertest.ScriptWorker",
    ]


def test_periodic_schedule_arguments(java):
    _, calls = java
    work_manager.Work(
        name="heartbeat_periodic",
        script="workers/heartbeat.py",
        interval_minutes=20,
        network_required=True,
        charging_required=True,
    ).schedule()

    args = calls["schedule"]
    assert args[4] is True
    assert args[6] == 20
    assert args[7] is True
    assert args[8] is True
    assert args[9] == "keep"


def test_custom_worker_name(java):
    _, calls = java
    work_manager.Work(
        name="custom",
        script="workers/heartbeat.py",
        worker_name="foo",
    ).schedule()
    assert calls["autoclass"] == [
        "io.github.fector101.workmanagertest.FooWorker",
    ]


def test_cancel_get_info_and_cancel_all(java):
    _, calls = java
    work = work_manager.Work(name="heartbeat_once", script="workers/heartbeat.py")

    work.cancel()
    assert calls["cancel"] == (calls["cancel"][0], "heartbeat_once")

    assert work.get_info() == "SUCCEEDED"
    assert calls["getStatus"] == (calls["getStatus"][0], "heartbeat_once")

    work_manager.cancel_all()
    assert len(calls["cancelAll"]) == 1
    assert isinstance(calls["cancelAll"][0], FakeContext)


@pytest.mark.parametrize(
    "script",
    [
        "/workers/heartbeat.py",
        "C:/workers/heartbeat.py",
        "../workers/heartbeat.py",
        "workers/../../heartbeat.py",
        "workers/heartbeat.txt",
        "",
    ],
)
def test_invalid_script_paths(script):
    with pytest.raises(ValueError):
        work_manager.Work(name="bad", script=script)


def test_periodic_minimum():
    with pytest.raises(ValueError, match="15"):
        work_manager.Work(
            name="too_fast",
            script="workers/heartbeat.py",
            interval_minutes=14,
        )


def test_args_must_be_json_serialisable():
    with pytest.raises(ValueError, match="JSON"):
        work_manager.Work(
            name="bad_args",
            script="workers/heartbeat.py",
            args={"bad": object()},
        ).argument_json()
