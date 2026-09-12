from __future__ import annotations

from typing import Any


def get_system_stats() -> dict[str, Any]:
    try:
        import psutil
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {"cpu": psutil.cpu_percent(interval=None), "memory": memory.percent, "disk": disk.percent, "load": getattr(psutil, "getloadavg", lambda: (0, 0, 0))()[0]}
    except Exception:
        return {"cpu": 0, "memory": 0, "disk": 0, "load": 0}
