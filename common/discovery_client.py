"""Service discovery client with caching and development fallbacks."""

import logging
import os
import threading
import time

from pathlib import Path

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")

logger = logging.getLogger(__name__)

REGISTRY_URL = os.getenv(
    "REGISTRY_URL",
    "http://127.0.0.1:8761",
).rstrip("/")

CACHE_SECONDS = 5

FALLBACK_PORTS = {
    "candidate-service": "CANDIDATE_PORT",
    "job-service": "JOB_PORT",
    "application-service": "APPLICATION_PORT",
    "recruitment-service": "RECRUITMENT_PORT",
    "notification-service": "NOTIFICATION_PORT",
}

_cache = {}
_cache_lock = threading.Lock()
_round_robin_positions = {}
_round_robin_lock = threading.Lock()


def _fallback_instances(service_name: str) -> list[dict]:
    """Return a development fallback instance for a known service."""
    port_variable = FALLBACK_PORTS.get(service_name)

    if not port_variable:
        return []

    port_value = os.getenv(port_variable)

    if not port_value:
        return []

    instances = [{
        "instance_id": f"{service_name}-{port_value}",
        "host": "127.0.0.1",
        "port": int(port_value),
    }]

    # Support the optional second local job-service instance.
    if service_name == "job-service":
        second_port = os.getenv("JOB_PORT_2")

        if second_port:
            instances.append({
                "instance_id": f"{service_name}-{second_port}",
                "host": "127.0.0.1",
                "port": int(second_port),
            })

    return instances


def get_instances(service_name: str) -> list[dict]:
    """
    Return available instances for a service.

    Results are cached for five seconds. If the registry is unavailable,
    use the last known instances or development fallback configuration.
    A registry 404 means the service is not registered.
    """
    now = time.monotonic()

    with _cache_lock:
        cached = _cache.get(service_name)

        if cached and now - cached["timestamp"] < CACHE_SECONDS:
            return list(cached["instances"])

        last_known = list(cached["instances"]) if cached else []

    try:
        response = requests.get(
            f"{REGISTRY_URL}/registry/services/{service_name}",
            timeout=1,
        )

        if response.status_code == 404:
            with _cache_lock:
                _cache[service_name] = {
                    "timestamp": now,
                    "instances": [],
                }
            return []

        response.raise_for_status()
        data = response.json()
        instances = data.get("instances", [])

        with _cache_lock:
            _cache[service_name] = {
                "timestamp": time.monotonic(),
                "instances": list(instances),
            }

        return list(instances)

    except requests.RequestException:
        logger.warning(
            "[DISCOVERY] registry down, using dev fallback"
        )

        if last_known:
            return last_known

        return _fallback_instances(service_name)


def choose_instance(service_name: str) -> dict | None:
    """Choose instances in round-robin order."""
    instances = get_instances(service_name)

    if not instances:
        return None

    with _round_robin_lock:
        position = _round_robin_positions.get(service_name, 0)
        instance = instances[position % len(instances)]

        _round_robin_positions[service_name] = (
            position + 1
        ) % len(instances)

        return instance