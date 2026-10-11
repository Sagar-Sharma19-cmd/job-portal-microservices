import requests

from common import discovery_client as discovery


def setup_function():
    discovery._cache.clear()
    discovery._round_robin_positions.clear()


def test_registry_returns_instances(monkeypatch):
    expected = [
        {"instance_id": "job-service-8002", "host": "127.0.0.1", "port": 8002}
    ]

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"service_name": "job-service", "instances": expected}

    monkeypatch.setattr(
        discovery.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    assert discovery.get_instances("job-service") == expected


def test_registry_404_returns_empty_list(monkeypatch):
    class FakeResponse:
        status_code = 404

    monkeypatch.setattr(
        discovery.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )

    assert discovery.get_instances("unknown-service") == []


def test_registry_down_uses_environment_fallback(monkeypatch):
    monkeypatch.setattr(
        discovery.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            requests.ConnectionError("Registry unavailable")
        ),
    )
    monkeypatch.setenv("JOB_PORT", "8002")
    monkeypatch.setenv("JOB_PORT_2", "8012")

    instances = discovery.get_instances("job-service")

    assert len(instances) == 2
    assert instances[0]["port"] == 8002
    assert instances[1]["port"] == 8012


def test_round_robin_selects_instances(monkeypatch):
    instances = [
        {"instance_id": "job-service-8002", "host": "127.0.0.1", "port": 8002},
        {"instance_id": "job-service-8012", "host": "127.0.0.1", "port": 8012},
    ]

    monkeypatch.setattr(
        discovery,
        "get_instances",
        lambda service_name: instances,
    )

    first = discovery.choose_instance("job-service")
    second = discovery.choose_instance("job-service")
    third = discovery.choose_instance("job-service")

    assert first["port"] == 8002
    assert second["port"] == 8012
    assert third["port"] == 8002


def test_unknown_service_without_fallback_returns_empty(monkeypatch):
    monkeypatch.setattr(
        discovery.requests,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            requests.ConnectionError("Registry unavailable")
        ),
    )

    assert discovery.get_instances("unknown-service") == []