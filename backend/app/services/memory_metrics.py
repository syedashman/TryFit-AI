from __future__ import annotations

import os
import threading

if os.name == "nt":
    from ctypes import POINTER, Structure, byref, c_size_t, sizeof, windll
    from ctypes.wintypes import BOOL, DWORD, HANDLE
else:
    import resource


_peak_rss_bytes = 0
_peak_lock = threading.Lock()


if os.name == "nt":
    class _ProcessMemoryCounters(Structure):
        _fields_ = [
            ("cb", DWORD),
            ("PageFaultCount", DWORD),
            ("PeakWorkingSetSize", c_size_t),
            ("WorkingSetSize", c_size_t),
        ]


def rss_bytes() -> int:
    """Return current process RSS using the host platform's lightweight API."""
    if os.name == "nt":
        counters = _ProcessMemoryCounters()
        counters.cb = sizeof(counters)
        get_process_memory_info = windll.psapi.GetProcessMemoryInfo
        get_process_memory_info.argtypes = [HANDLE, POINTER(_ProcessMemoryCounters), DWORD]
        get_process_memory_info.restype = BOOL
        if get_process_memory_info(
            windll.kernel32.GetCurrentProcess(),
            byref(counters),
            counters.cb,
        ):
            return int(counters.WorkingSetSize)
        return 0

    usage = resource.getrusage(resource.RUSAGE_SELF)
    return int(usage.ru_maxrss * (1024 if os.uname().sysname == "Linux" else 1))


def memory_snapshot() -> tuple[float, float]:
    """Return current and process-peak RSS in megabytes."""
    current = rss_bytes()
    global _peak_rss_bytes
    with _peak_lock:
        _peak_rss_bytes = max(_peak_rss_bytes, current)
        peak = _peak_rss_bytes
    return current / 1048576, peak / 1048576


def log_memory(label: str) -> tuple[float, float]:
    try:
        current, peak = memory_snapshot()
    except Exception as exc:  # noqa: BLE001
        print(f"[MEM] {label} unavailable={type(exc).__name__}")
        return 0.0, 0.0
    print(f"[MEM] {label} rss_mb={current:.1f} peak_rss_mb={peak:.1f}")
    return current, peak