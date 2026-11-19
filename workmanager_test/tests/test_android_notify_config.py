import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from android_notify import config  # noqa: E402


@pytest.fixture(autouse=True)
def reset_config_cache(monkeypatch):
    monkeypatch.setattr(config, '_activity_context', None)
    monkeypatch.setattr(config, '_worker_context', None, raising=False)
    monkeypatch.delattr(sys, 'p4a_worker_entrypoint', raising=False)
    monkeypatch.delenv('PYTHON_SERVICE_ARGUMENT', raising=False)
    # Exercise the Android branches while keeping jnius out of the way.
    monkeypatch.setattr(config, 'on_android_platform', lambda: True)


def test_worker_marker_is_independent_of_service_argument(monkeypatch):
    monkeypatch.setenv('PYTHON_SERVICE_ARGUMENT', 'payload')
    assert config.from_service_file() is True
    assert config.from_worker_file() is False

    monkeypatch.setattr(sys, 'p4a_worker_entrypoint', 'workers/heartbeat.py', raising=False)
    assert config.from_worker_file() is True
    # Workers intentionally keep the service path for permission/listener
    # handling; only the Context lookup differs.
    assert config.from_service_file() is True


def test_worker_context_wins_over_service_context(monkeypatch):
    monkeypatch.setenv('PYTHON_SERVICE_ARGUMENT', 'payload')
    monkeypatch.setattr(sys, 'p4a_worker_entrypoint', 'workers/heartbeat.py', raising=False)

    class FakePythonWorker:
        @staticmethod
        def getWorkerContext():
            return 'WORKER_CONTEXT'

    def fake_autoclass(name):
        assert name == 'org.kivy.android.PythonWorker'
        return FakePythonWorker

    monkeypatch.setattr(config, '_get_jnius', lambda: (lambda x, y: x, fake_autoclass))

    def no_service():
        raise AssertionError('services must not be used from a worker')

    monkeypatch.setattr(config, 'get_python_service', no_service)

    assert config.get_python_activity_context() == 'WORKER_CONTEXT'
    # Cached on subsequent calls, so the Java lookup happens only once.
    assert config.get_python_activity_context() == 'WORKER_CONTEXT'


def test_worker_context_missing_raises_clear_error(monkeypatch):
    monkeypatch.setattr(sys, 'p4a_worker_entrypoint', 'workers/heartbeat.py', raising=False)

    class FakePythonWorker:
        @staticmethod
        def getWorkerContext():
            return None

    monkeypatch.setattr(
        config,
        '_get_jnius',
        lambda: (lambda x, y: x, lambda name: FakePythonWorker),
    )

    with pytest.raises(RuntimeError, match='PythonWorker'):
        config.get_python_activity_context()
