"""Reads live numbers from the machine the server runs on (psutil). Works on Windows and Linux."""

import platform
import socket
import time
from pathlib import Path

import psutil

_CPUS = psutil.cpu_count(logical=True) or 1
_DISK_ROOT = Path.cwd().anchor or "/"


def system_info() -> dict:
    return {
        "hostname": socket.gethostname(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu_count": _CPUS,
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage(_DISK_ROOT).percent,
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }


def list_processes() -> list[dict]:
    """All running processes, unsorted. cpu_percent is 0-100 of the whole machine."""
    procs = []
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            proc.cpu_percent(None)  # the first call only starts the measurement
            procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(0.2)

    result = []
    for proc in procs:
        try:
            if proc.pid == 0:  # Windows "System Idle Process" - not a real process
                continue
            result.append(
                {
                    "pid": proc.pid,
                    "name": proc.info.get("name") or "?",
                    "cpu_percent": round(min(100.0, proc.cpu_percent(None) / _CPUS), 1),
                    "memory_percent": round(proc.memory_percent(), 1),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return result
