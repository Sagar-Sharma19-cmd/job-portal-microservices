# Common Library

Shared utilities for communication between Job Portal microservices.

## Components

### 1. Circuit Breaker

File: `circuit_breaker.py`

Provides a thread-safe circuit breaker with three states:

- `CLOSED`: Requests are allowed.
- `OPEN`: Requests are blocked temporarily.
- `HALF_OPEN`: One trial request is permitted after the recovery interval.

Configuration:
- `CB_FAILURE_THRESHOLD`: Number of failures before opening the circuit.
- `CB_OPEN_SECONDS`: Time before allowing a recovery trial.

### 2. Service Discovery Client

File: `discovery_client.py`

Provides:
- Service instance lookup from the Service Registry.
- Five-second instance caching.
- Development fallback ports when the registry is unavailable.
- Round-robin instance selection.

Configuration:
- `REGISTRY_URL`
- `CANDIDATE_PORT`
- `JOB_PORT`
- `JOB_PORT_2`
- `APPLICATION_PORT`
- `RECRUITMENT_PORT`
- `NOTIFICATION_PORT`

### 3. Service Client

File: `service_client.py`

Provides:
- HTTP communication between microservices.
- Internal authentication and request ID headers.
- Configurable request timeouts.
- Circuit breaker integration.
- Standardized service-unavailable errors.

The `call_service()` function returns HTTP responses below status 500,
including 4xx responses. Network failures, timeouts, and HTTP 5xx
responses are treated as service failures.

Configuration:
- `INTERNAL_TOKEN`
- `HTTP_TIMEOUT_SECONDS`

### 4. Service Registration

File: `registration.py`

Provides:
- Service instance registration.
- Periodic registry heartbeats.
- Re-registration after an unknown-instance response.
- Service deregistration.
- Logging and retries when the registry is unavailable.

Configuration:
- `REGISTRY_URL`
- `HEARTBEAT_INTERVAL_SECONDS`
- `HTTP_TIMEOUT_SECONDS`

## Usage

Import shared utilities from the common package:

```python
from common import (
    CircuitBreaker,
    call_service,
    choose_instance,
    get_instances,
    get_circuit_states,
    register_service,
    deregister_service,
)