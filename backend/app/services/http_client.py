from __future__ import annotations

import threading

import httpx

_lock = threading.Lock()
_client: httpx.Client | None = None


def get_http_client() -> httpx.Client:
    """Return the process-wide bounded connection pool for outbound APIs."""
    global _client
    if _client is None or _client.is_closed:
        with _lock:
            if _client is None or _client.is_closed:
                _client = httpx.Client(
                    timeout=httpx.Timeout(
                        connect=10.0,
                        read=30.0,
                        write=30.0,
                        pool=5.0,
                    ),
                    limits=httpx.Limits(
                        max_connections=12,
                        max_keepalive_connections=6,
                        keepalive_expiry=30.0,
                    ),
                )
    return _client


def close_http_client() -> None:
    global _client
    with _lock:
        client = _client
        _client = None
    if client is not None:
        client.close()