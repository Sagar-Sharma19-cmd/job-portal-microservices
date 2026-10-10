"""Register service instances and maintain registry heartbeats."""

import logging
import os
import threading
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

HEARTBEAT_INTERVAL_SECONDS = float(
    os.getenv("HEARTBEAT_INTERVAL_SECONDS", "10")
)

HTTP_TIMEOUT_SECONDS = float(
    os.getenv("HTTP_TIMEOUT_SECONDS", "2")
)

# Tracks registration sessions by instance ID.
_sessions = {}
_sessions_lock = threading.Lock()


def _registry_request(method: str, path: str, **kwargs):
    """Send a request to the registry with a bounded timeout."""
    return requests.request(
        method,
        f"{REGISTRY_URL}{path}",
        timeout=HTTP_TIMEOUT_SECONDS,
        **kwargs,
    )


def register_service(
    service_name: str,
    host: str,
    port: int,
) -> str:
    """
    Register a service instance and start its heartbeat thread.

    Returns the instance ID even if the registry is temporarily
    unavailable, allowing the service to keep running and retry.
    """
    instance_id = f"{service_name}-{port}"

    payload = {
        "service_name": service_name,
        "instance_id": instance_id,
        "host": host,
        "port": port,
    }

    with _sessions_lock:
        existing = _sessions.get(instance_id)

        if existing:
            existing["stop_event"].set()

        stop_event = threading.Event()

        session = {
            "service_name": service_name,
            "host": host,
            "port": port,
            "stop_event": stop_event,
            "thread": None,
        }

        _sessions[instance_id] = session

    def register_once() -> bool:
        try:
            response = _registry_request(
                "POST",
                "/registry/register",
                json=payload,
            )
            response.raise_for_status()

            logger.info(
                "[REGISTRATION] registered %s at %s:%s",
                instance_id,
                host,
                port,
            )
            return True

        except requests.RequestException as exc:
            logger.warning(
                "[REGISTRATION] registry unavailable for %s: %s",
                instance_id,
                exc,
            )
            return False

    def heartbeat_loop():
        registered = register_once()

        while not stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
            if not registered:
                registered = register_once()
                continue

            try:
                response = _registry_request(
                    "PUT",
                    f"/registry/heartbeat/{instance_id}",
                )

                if response.status_code == 404:
                    logger.warning(
                        "[REGISTRATION] %s missing; registering again",
                        instance_id,
                    )
                    registered = register_once()
                    continue

                response.raise_for_status()

            except requests.RequestException as exc:
                logger.warning(
                    "[REGISTRATION] heartbeat failed for %s: %s",
                    instance_id,
                    exc,
                )

                # Retry registration on the next heartbeat cycle.
                registered = False

    thread = threading.Thread(
        target=heartbeat_loop,
        name=f"heartbeat-{instance_id}",
        daemon=True,
    )

    with _sessions_lock:
        current_session = _sessions.get(instance_id)

        if current_session and current_session["stop_event"] is stop_event:
            current_session["thread"] = thread

    thread.start()

    return instance_id


def deregister_service(instance_id: str) -> None:
    """Stop heartbeats and request removal from the registry."""
    with _sessions_lock:
        session = _sessions.pop(instance_id, None)

    if session is None:
        return

    stop_event = session["stop_event"]
    stop_event.set()

    thread = session["thread"]

    if thread and thread.is_alive():
        thread.join(timeout=HTTP_TIMEOUT_SECONDS + 1)

    try:
        response = _registry_request(
            "DELETE",
            f"/registry/instances/{instance_id}",
        )

        if response.status_code not in (200, 204, 404):
            response.raise_for_status()

        logger.info(
            "[REGISTRATION] deregistered %s",
            instance_id,
        )

    except requests.RequestException as exc:
        logger.warning(
            "[REGISTRATION] deregistration failed for %s: %s",
            instance_id,
            exc,
        )