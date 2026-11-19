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
        def scheduleChain(*args):
            calls["scheduleChain"] = args

        @staticmethod
        def cancel(*args):
            calls["cancel"] = args

        @staticmethod
        def cancelAll(*args):
            calls["cancelAll"] = args

        @staticmethod
        def cancelByTag(*args):
            calls["cancelByTag"] = args

        @staticmethod
        def getStatus(*args):
            calls["getStatus"] = args
            return "SUCCEEDED"

        @staticmethod
        def getInfoJson(*args):
            calls["getInfoJson"] = args
            return calls.get("info_json", '{"found":false,"infos":[]}')

        @staticmethod
        def getInfoJsonByTag(*args):
            calls["getInfoJsonByTag"] = args
            return calls.get("tag_info_json", '{"found":false,"infos":[]}')

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
    (context, name, script, data, periodic, delay, interval,
     network, charging, policy, backoff_policy, backoff_delay,
     tags_json, unique, network_type) = calls["schedule"]
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
    assert backoff_policy == "exponential"
    assert backoff_delay == 30
    assert tags_json == "[]"
    assert unique is True
    assert network_type == "connected"
    assert calls["autoclass"] == [
        "io.github.fector101.workmanagertest.ScriptWorker",
    ]


def test_explicit_keep_policy_reaches_java(java):
    _, calls = java
    work_manager.Work(
        name="keep_once",
        script="workers/heartbeat.py",
        policy="keep",
    ).schedule()

    assert calls["schedule"][9] == "keep"


@pytest.mark.parametrize("policy", [
    "keep", "replace", "append", "append_or_replace",
    "APPEND", "APPEND_OR_REPLACE",
])
def test_one_time_policies_reach_java(java, policy):
    _, calls = java
    work_manager.Work(
        name="policy_once",
        script="workers/heartbeat.py",
        policy=policy,
    ).schedule()

    assert calls["schedule"][9] == policy.lower()


@pytest.mark.parametrize("policy", ["keep", "replace", "update", "UPDATE"])
def test_periodic_policies_reach_java(java, policy):
    _, calls = java
    work_manager.Work(
        name="policy_periodic",
        script="workers/heartbeat.py",
        interval_minutes=15,
        policy=policy,
    ).schedule()

    assert calls["schedule"][4] is True
    assert calls["schedule"][9] == policy.lower()


@pytest.mark.parametrize("policy", ["update", "bogus", "", 42])
def test_invalid_one_time_policy(policy):
    with pytest.raises(ValueError, match="policy"):
        work_manager.Work(
            name="bad_policy",
            script="workers/heartbeat.py",
            policy=policy,
        )


@pytest.mark.parametrize("policy", ["append", "append_or_replace", "bogus", 42])
def test_invalid_periodic_policy(policy):
    with pytest.raises(ValueError, match="policy"):
        work_manager.Work(
            name="bad_policy",
            script="workers/heartbeat.py",
            interval_minutes=15,
            policy=policy,
        )


def test_explicit_backoff_reaches_java(java):
    _, calls = java
    work_manager.Work(
        name="backoff_once",
        script="workers/retry.py",
        backoff_policy="LINEAR",
        backoff_delay_seconds=10,
    ).schedule()

    assert calls["schedule"][10] == "linear"
    assert calls["schedule"][11] == 10


@pytest.mark.parametrize("policy", ["fast", "LINEAR!", ""])
def test_invalid_backoff_policy(policy):
    with pytest.raises(ValueError, match="backoff_policy"):
        work_manager.Work(
            name="bad_backoff",
            script="workers/retry.py",
            backoff_policy=policy,
        )


@pytest.mark.parametrize("delay", [0, -1, 86401, "abc"])
def test_invalid_backoff_delay(delay):
    with pytest.raises(ValueError, match="backoff_delay_seconds"):
        work_manager.Work(
            name="bad_backoff",
            script="workers/retry.py",
            backoff_delay_seconds=delay,
        )


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


def test_one_time_schedule_passes_constraints(java):
    _, calls = java
    work_manager.Work(
        name="constrained_once",
        script="workers/heartbeat.py",
        delay_seconds=10,
        network_required=True,
        charging_required=True,
    ).schedule()

    (context, name, script, data, periodic, delay, interval,
     network, charging, policy, backoff_policy, backoff_delay,
     tags_json, unique, network_type) = calls["schedule"]
    assert name == "constrained_once"
    assert periodic is False
    assert delay == 10
    assert network is True
    assert charging is True
    assert unique is True
    assert network_type == "connected"


@pytest.mark.parametrize("network_type", [
    "connected", "unmetered", "not_roaming", "not_required",
    "UNMETERED", "Not_Roaming",
])
def test_network_type_reaches_java(java, network_type):
    _, calls = java
    work = work_manager.Work(
        name="network_type_once",
        script="workers/heartbeat.py",
        network_required=True,
        network_type=network_type,
    )
    assert work.network_type == network_type.lower()
    work.schedule()
    assert calls["schedule"][14] == network_type.lower()


def test_network_type_defaults_to_connected(java):
    _, calls = java
    work_manager.Work(
        name="default_network", script="workers/heartbeat.py",
    ).schedule()
    assert calls["schedule"][14] == "connected"


@pytest.mark.parametrize("network_type", [
    "bogus", "", "wifi", "connected ", 42, None,
])
def test_invalid_network_type(network_type):
    with pytest.raises(ValueError, match="network_type"):
        work_manager.Work(
            name="bad_network", script="workers/heartbeat.py",
            network_type=network_type,
        )


def test_network_type_reaches_chain_step_json(java):
    _, calls = java
    work_manager.Work(
        name="chain_net", script="workers/chain.py",
        network_required=True, network_type="not_roaming",
    ).then(work_manager.Work(
        name="step2", script="workers/chain.py", network_type="UNMETERED",
    )).schedule()

    steps = json.loads(calls["scheduleChain"][3])
    assert steps[0]["network_type"] == "not_roaming"
    assert steps[0]["network_required"] is True
    assert steps[1]["network_type"] == "unmetered"
    assert steps[1]["network_required"] is False


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


def test_argument_json_accepts_exactly_max_size():
    wrapper = len('{"blob":""}')
    work = work_manager.Work(
        name="big_ok",
        script="workers/heartbeat.py",
        args={"blob": "x" * (work_manager._MAX_ARGUMENT_BYTES - wrapper)},
    )

    assert len(work.argument_json()) == work_manager._MAX_ARGUMENT_BYTES


def test_argument_json_rejects_payload_over_limit():
    wrapper = len('{"blob":""}')
    work = work_manager.Work(
        name="big_bad",
        script="workers/heartbeat.py",
        args={"blob": "x" * (work_manager._MAX_ARGUMENT_BYTES - wrapper + 1)},
    )

    with pytest.raises(ValueError, match="too large for WorkManager Data"):
        work.argument_json()


def test_argument_json_counts_utf8_bytes_not_characters():
    work = work_manager.Work(
        name="unicode_bad",
        script="workers/heartbeat.py",
        args={"blob": "\u00e9" * (work_manager._MAX_ARGUMENT_BYTES // 2 + 1)},
    )

    with pytest.raises(ValueError, match="too large for WorkManager Data"):
        work.argument_json()


def test_schedule_rejects_oversized_args_before_java(java):
    _, calls = java
    wrapper = len('{"blob":""}')
    work = work_manager.Work(
        name="no_java_call",
        script="workers/heartbeat.py",
        args={"blob": "x" * (work_manager._MAX_ARGUMENT_BYTES - wrapper + 1)},
    )

    with pytest.raises(ValueError, match="too large for WorkManager Data"):
        work.schedule()

    assert "schedule" not in calls


def test_get_work_info_parses_all_fields(java):
    _, calls = java
    calls["info_json"] = json.dumps({
        "found": True,
        "infos": [{
            "id": "uuid-1",
            "state": "RUNNING",
            "runAttemptCount": 2,
            "generation": 3,
            "tags": ["ScriptWorker", "heartbeat_once"],
            "output": {"message": "done", "count": 4},
            "progress": {"percent": 50},
            "initialDelayMillis": 10000,
            "nextScheduleTimeMillis": 1763560000000,
            "stopReason": 0,
            "stopReasonName": "NOT_STOPPED",
        }],
    })

    info = work_manager.get_work_info("heartbeat_once")

    assert info is not None
    assert info.id == "uuid-1"
    assert info.state == "RUNNING"
    assert info.run_attempt_count == 2
    assert info.generation == 3
    assert "heartbeat_once" in info.tags
    assert info.output == {"message": "done", "count": 4}
    assert info.progress == {"percent": 50}
    assert info.initial_delay_ms == 10000
    assert info.next_schedule_time_ms == 1763560000000
    assert info.stop_reason_name == "NOT_STOPPED"
    assert calls["getInfoJson"] == (calls["getInfoJson"][0], "heartbeat_once")


def test_get_work_info_prefers_active_row(java):
    _, calls = java
    calls["info_json"] = json.dumps({
        "found": True,
        "infos": [
            {"state": "SUCCEEDED", "runAttemptCount": 1},
            {"state": "ENQUEUED", "runAttemptCount": 1,
             "stopReasonName": "CONSTRAINT_CHARGING"},
            {"state": "FAILED", "runAttemptCount": 1},
        ],
    })

    info = work_manager.get_work_info("multi")

    assert info.state == "ENQUEUED"
    assert info.stop_reason_name == "CONSTRAINT_CHARGING"


def test_get_work_info_when_not_found(java):
    _, calls = java
    calls["info_json"] = '{"found":false,"infos":[]}'

    details = work_manager.get_work_infos("missing")

    assert details.found is False
    assert details.infos == ()
    assert details.error is None
    assert work_manager.get_work_info("missing") is None


def test_get_work_info_reports_java_error(java):
    _, calls = java
    calls["info_json"] = '{"found":false,"error":"timeout"}'

    details = work_manager.get_work_infos("slow")

    assert details.error == "timeout"
    assert work_manager.get_work_info("slow") is None


def test_get_work_info_rejects_invalid_json(java):
    _, calls = java
    calls["info_json"] = "not json"

    with pytest.raises(ValueError, match="not JSON"):
        work_manager.get_work_infos("bad")


def test_get_work_info_unwraps_worker_result_data(java):
    _, calls = java
    calls["info_json"] = json.dumps({
        "found": True,
        "infos": [{
            "state": "SUCCEEDED",
            "output": {"PYTHON_WORK_OUTPUT": '{"message":"done","steps":3}'},
            "progress": {"PYTHON_WORK_PROGRESS": '{"step":3,"total":3}'},
        }],
    })

    info = work_manager.get_work_info("result_once")

    assert info.output == {"message": "done", "steps": 3}
    assert info.progress == {"step": 3, "total": 3}


def test_get_work_info_keeps_plain_result_data(java):
    _, calls = java
    calls["info_json"] = json.dumps({
        "found": True,
        "infos": [{
            "state": "SUCCEEDED",
            "output": {"message": "plain"},
            "progress": {"PYTHON_WORK_PROGRESS": "not json"},
        }],
    })

    info = work_manager.get_work_info("plain")

    assert info.output == {"message": "plain"}
    assert info.progress == {"PYTHON_WORK_PROGRESS": "not json"}


def test_work_result_dir_matches_java_for_pyc_entrypoint(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_PRIVATE", str(tmp_path))
    monkeypatch.setenv("ANDROID_ENTRYPOINT", "workers/result.pyc")
    from work_result import work_dir

    # start.c resolves workers/result.py -> workers/result.pyc, while Java
    # keeps the .py name; both must map to workers_result.py on disk.
    assert work_dir() == str(tmp_path / "work_data" / "workers_result.py")


def test_work_result_writes_output_and_progress(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_PRIVATE", str(tmp_path))
    monkeypatch.setenv("ANDROID_ENTRYPOINT", "workers/result.py")
    from work_result import set_output, set_progress

    set_progress({"step": 1, "total": 2})
    set_output({"message": "done"})

    base = tmp_path / "work_data" / "workers_result.py"
    assert json.loads((base / "progress.json").read_text()) == {
        "step": 1, "total": 2}
    assert json.loads((base / "output.json").read_text()) == {
        "message": "done"}


def test_work_result_writes_retry_file(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_PRIVATE", str(tmp_path))
    monkeypatch.setenv("ANDROID_ENTRYPOINT", "workers/retry.py")
    from work_result import request_retry

    request_retry("transient failure")

    base = tmp_path / "work_data" / "workers_retry.py"
    assert json.loads((base / "retry.json").read_text()) == {
        "reason": "transient failure"}
    # attempt.txt is Java's signal to preserve the retry counter.
    assert not (base / "attempt.txt").exists()


def test_work_result_attempt_increments_across_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("ANDROID_PRIVATE", str(tmp_path))
    monkeypatch.setenv("ANDROID_ENTRYPOINT", "workers/retry.py")
    from work_result import attempt

    assert [attempt(), attempt(), attempt()] == [1, 2, 3]
    base = tmp_path / "work_data" / "workers_retry.py"
    assert (base / "attempt.txt").read_text() == "3"


def test_fluent_chain_schedules_java_chain(java):
    _, calls = java
    first = work_manager.Work(
        name="chain_once",
        script="workers/chain.py",
        args={"step": 1},
        policy="replace",
    )
    chain = first.then(work_manager.Work(
        name="chain_step_2",
        script="workers/chain.py",
        args={"step": 2},
    ))

    assert isinstance(chain, work_manager.WorkChain)
    assert chain.name == "chain_once"
    assert chain.policy == "replace"
    assert chain.worker_name == "script"
    assert len(chain.steps) == 2

    assert chain.schedule() is chain
    context, name, policy, steps_json = calls["scheduleChain"]
    assert isinstance(context, FakeContext)
    assert name == "chain_once"
    assert policy == "replace"
    steps = json.loads(steps_json)
    assert [step["script"] for step in steps] == [
        "workers/chain.py", "workers/chain.py"]
    assert [json.loads(step["argument"])["step"] for step in steps] == [1, 2]
    assert calls["autoclass"] == [
        "io.github.fector101.workmanagertest.ScriptWorker",
    ]


def test_chain_steps_json_carries_per_step_options(java):
    _, calls = java
    work_manager.Work(
        name="chain_opts",
        script="workers/chain.py",
        delay_seconds=3,
        network_required=True,
        backoff_policy="linear",
        backoff_delay_seconds=12,
    ).then(work_manager.Work(
        name="step2",
        script="workers/result.py",
        charging_required=True,
    )).schedule()

    steps = json.loads(calls["scheduleChain"][3])
    assert steps[0] == {
        "script": "workers/chain.py",
        "argument": "{}",
        "delay_seconds": 3,
        "network_required": True,
        "network_type": "connected",
        "charging_required": False,
        "backoff_policy": "linear",
        "backoff_delay_seconds": 12,
        "tags": [],
    }
    assert steps[1]["script"] == "workers/result.py"
    assert steps[1]["charging_required"] is True
    assert steps[1]["network_required"] is False
    assert steps[1]["network_type"] == "connected"


def test_chain_then_appends_third_step(java):
    _, calls = java
    chain = work_manager.Work(
        name="chain3", script="workers/chain.py",
    ).then(work_manager.Work(name="s2", script="workers/chain.py"))

    assert chain.then(work_manager.Work(
        name="s3", script="workers/chain.py")) is chain
    chain.schedule()
    assert len(json.loads(calls["scheduleChain"][3])) == 3


@pytest.mark.parametrize("steps", [
    [],
    [work_manager.Work(name="s1", script="workers/chain.py")],
])
def test_chain_requires_at_least_two_steps(steps):
    with pytest.raises(ValueError, match="at least two"):
        work_manager.WorkChain(name="chain_bad", steps=steps)


def test_chain_rejects_more_than_ten_steps():
    steps = [
        work_manager.Work(name="s{}".format(i), script="workers/chain.py")
        for i in range(11)
    ]
    with pytest.raises(ValueError, match="at most 10"):
        work_manager.WorkChain(name="chain_big", steps=steps)


def test_chain_rejects_periodic_step():
    with pytest.raises(ValueError, match="periodic"):
        work_manager.Work(
            name="chain_bad", script="workers/chain.py",
        ).then(work_manager.Work(
            name="s2", script="workers/chain.py", interval_minutes=15))


def test_chain_rejects_mismatched_worker_name():
    with pytest.raises(ValueError, match="worker_name"):
        work_manager.Work(
            name="chain_bad", script="workers/chain.py",
        ).then(work_manager.Work(
            name="s2", script="workers/chain.py", worker_name="other"))


def test_chain_validates_name_and_policy():
    steps = [
        work_manager.Work(name="s1", script="workers/chain.py"),
        work_manager.Work(name="s2", script="workers/chain.py"),
    ]
    with pytest.raises(ValueError, match="name"):
        work_manager.WorkChain(name="bad name!", steps=steps)
    with pytest.raises(ValueError, match="policy"):
        work_manager.WorkChain(name="chain_bad", steps=steps, policy="bad")


@pytest.mark.parametrize("policy", [
    "keep", "replace", "append", "append_or_replace", "APPEND_OR_REPLACE",
])
def test_chain_policies_reach_java(java, policy):
    _, calls = java
    work_manager.Work(
        name="chain_policy", script="workers/chain.py", policy=policy,
    ).then(work_manager.Work(name="s2", script="workers/chain.py")).schedule()

    assert calls["scheduleChain"][2] == policy.lower()


@pytest.mark.parametrize("policy", ["update", "bogus", 42])
def test_chain_rejects_non_one_time_policy(policy):
    steps = [
        work_manager.Work(name="s1", script="workers/chain.py"),
        work_manager.Work(name="s2", script="workers/chain.py"),
    ]
    with pytest.raises(ValueError, match="policy"):
        work_manager.WorkChain(name="chain_bad", steps=steps, policy=policy)


def test_chain_cancel_and_status_use_chain_name(java):
    _, calls = java
    chain = work_manager.Work(
        name="chain_cancel", script="workers/chain.py",
    ).then(work_manager.Work(name="s2", script="workers/chain.py"))

    chain.cancel()
    assert calls["cancel"][1] == "chain_cancel"
    assert chain.get_info() == "SUCCEEDED"
    assert calls["getStatus"][1] == "chain_cancel"


def test_custom_tags_reach_java(java):
    _, calls = java
    work_manager.Work(
        name="tagged",
        script="workers/heartbeat.py",
        tags=["demo", "release"],
    ).schedule()

    assert json.loads(calls["schedule"][12]) == ["demo", "release"]


@pytest.mark.parametrize("tags", [
    "demo",
    42,
    ["a", ""],
    ["a", 2],
    ["x" * 101],
    ["t"] * 11,
])
def test_invalid_tags(tags):
    with pytest.raises(ValueError, match="tag"):
        work_manager.Work(name="tagged", script="workers/heartbeat.py", tags=tags)


def test_get_work_infos_by_tag(java):
    _, calls = java
    calls["tag_info_json"] = json.dumps({
        "found": True,
        "infos": [{
            "id": "abc",
            "state": "SUCCEEDED",
            "tags": ["demo", "ScriptWorker"],
        }],
    })

    infos = work_manager.get_work_infos_by_tag("demo")

    assert calls["getInfoJsonByTag"] == (calls["getInfoJsonByTag"][0], "demo")
    assert infos.found is True
    assert len(infos.infos) == 1
    assert infos.infos[0].tags == ("demo", "ScriptWorker")


def test_cancel_by_tag(java):
    _, calls = java

    work_manager.cancel_by_tag("demo")

    assert calls["cancelByTag"] == (calls["cancelByTag"][0], "demo")


def test_chain_step_json_includes_tags(java):
    _, calls = java
    work_manager.Work(
        name="chain_tags",
        script="workers/chain.py",
        tags=["pipeline", "step1"],
    ).then(work_manager.Work(
        name="s2",
        script="workers/chain.py",
        tags=["pipeline"],
    )).schedule()

    steps = json.loads(calls["scheduleChain"][3])
    assert steps[0]["tags"] == ["pipeline", "step1"]
    assert steps[1]["tags"] == ["pipeline"]


def test_work_object_exposes_work_info(java):
    _, calls = java
    calls["info_json"] = '{"found":true,"infos":[{"state":"SUCCEEDED"}]}'
    work = work_manager.Work(name="x", script="workers/heartbeat.py")

    assert work.get_work_info().state == "SUCCEEDED"
    assert work.get_work_infos().found is True


def test_non_unique_flag_reaches_java(java):
    _, calls = java
    work_manager.Work(
        name="nonunique_once", script="workers/heartbeat.py", unique=False,
    ).schedule()
    assert calls["schedule"][13] is False
    assert calls["schedule"][9] == "keep"

    work_manager.Work(
        name="nonunique_periodic", script="workers/heartbeat.py",
        interval_minutes=15, unique=False,
    ).schedule()
    assert calls["schedule"][13] is False


@pytest.mark.parametrize("policy", ["append", "update", "bogus", "REPLACE"])
def test_non_unique_ignores_policy(policy):
    work = work_manager.Work(
        name="nonunique_policy", script="workers/heartbeat.py",
        unique=False, policy=policy,
    )
    assert work.policy == policy.lower()


def test_non_unique_tag_limit():
    work_manager.Work(
        name="nonunique_tags", script="workers/heartbeat.py",
        unique=False, tags=["t{}".format(i) for i in range(9)],
    )
    with pytest.raises(ValueError, match="tag"):
        work_manager.Work(
            name="nonunique_tags", script="workers/heartbeat.py",
            unique=False, tags=["t{}".format(i) for i in range(10)],
        )


def _tag_infos(*states):
    return json.dumps({
        "found": True,
        "infos": [
            {"id": "id{}".format(i), "state": state}
            for i, state in enumerate(states)
        ],
    })


def test_non_unique_get_work_infos_uses_tag_query(java):
    _, calls = java
    calls["tag_info_json"] = _tag_infos("SUCCEEDED", "SUCCEEDED")

    infos = work_manager.get_work_infos("nonunique_once", unique=False)

    assert calls["getInfoJsonByTag"] == (
        calls["getInfoJsonByTag"][0], "nonunique_once")
    assert "getInfoJson" not in calls
    assert len(infos.infos) == 2


def test_non_unique_get_work_info_picks_active_row(java):
    _, calls = java
    calls["tag_info_json"] = _tag_infos("SUCCEEDED", "RUNNING")

    info = work_manager.get_work_info("nonunique_once", unique=False)

    assert info.id == "id1"
    assert info.state == "RUNNING"


def test_non_unique_get_info_uses_tag_query(java):
    _, calls = java
    calls["tag_info_json"] = _tag_infos("FAILED")

    assert work_manager.get_info("nonunique_once", unique=False) == "FAILED"
    assert "getStatus" not in calls


def test_non_unique_cancel_uses_tag(java):
    _, calls = java

    work_manager.cancel("nonunique_once", unique=False)

    assert calls["cancelByTag"] == (calls["cancelByTag"][0], "nonunique_once")
    assert "cancel" not in calls


def test_work_object_non_unique_dispatches_to_tag_helpers(java):
    _, calls = java
    calls["tag_info_json"] = _tag_infos("SUCCEEDED")
    work = work_manager.Work(
        name="nonunique_once", script="workers/heartbeat.py", unique=False,
    )

    assert work.get_work_infos().found is True
    assert work.get_info() == "SUCCEEDED"
    work.cancel()

    assert calls["getInfoJsonByTag"][1] == "nonunique_once"
    assert calls["cancelByTag"][1] == "nonunique_once"
    assert "getInfoJson" not in calls
    assert "cancel" not in calls

