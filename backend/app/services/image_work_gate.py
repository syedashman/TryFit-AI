"""Limit how many jobs run CPU/memory-heavy image analysis at the same time.

Jobs in a batch should wait on Vertex in parallel, but on small hosts (e.g. a
0.1-CPU / 512 MB Render instance) running candidate scoring and result
post-processing for several jobs at once only splits the CPU and multiplies
peak memory until the process is killed. Serialising just that part keeps
memory flat and lets results finish one after another instead of all late.
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

from app.core.config import get_settings

_lock = threading.Lock()
_gate: threading.BoundedSemaphore | None = None


def _get_gate() -> threading.BoundedSemaphore:
    global _gate
    with _lock:
        if _gate is None:
            _gate = threading.BoundedSemaphore(
                max(1, get_settings().max_concurrent_image_processing)
            )
        return _gate


@contextmanager
def heavy_image_work() -> Iterator[None]:
    gate = _get_gate()
    gate.acquire()
    try:
        yield
    finally:
        gate.release()
