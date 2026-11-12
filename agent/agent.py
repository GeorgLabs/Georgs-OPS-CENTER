"""The Ops Center agent: measures THIS computer and reports to your Ops Center.

    python agent/agent.py --url http://127.0.0.1:8000 --key ops_xxxxxxxx

Needs only psutil (setup installs it; copy this file to any other machine and `pip install psutil`).
Press Ctrl+C to stop.
The API key identifies the host; it is sent in the X-API-Key header, never in the URL.
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import psutil
except ImportError:  # started with the wrong Python (not the project's .venv)? Use the right one.
    root = Path(__file__).resolve().parent.parent
    venv_python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if venv_python.exists() and Path(sys.executable).resolve() != venv_python.resolve():
        sys.exit(subprocess.run([str(venv_python), *sys.argv], check=False).returncode)
    sys.exit("psutil is missing: run  pip install psutil  and try again.")


def disk_path() -> str:
    return psutil.disk_partitions()[0].mountpoint if sys.platform == "win32" else "/"


def measure() -> dict:
    return {
        "cpu_percent": psutil.cpu_percent(interval=1),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage(disk_path()).percent,
    }


def send(url: str, key: str, data: dict) -> str:
    request = urllib.request.Request(
        url.rstrip("/") + "/api/ingest",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json", "X-API-Key": key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        return f"HTTP {exc.code} {detail}"
    except urllib.error.URLError as exc:
        return f"cannot reach server ({exc.reason})"


def main() -> None:
    parser = argparse.ArgumentParser(description="Report this machine's load to Ops Center")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--key", required=True, help="the host's API key (ops_...)")
    parser.add_argument("--every", type=float, default=5, help="seconds between reports")
    args = parser.parse_args()

    print(f"Reporting to {args.url} every {args.every:g}s - Ctrl+C to stop")
    try:
        while True:
            data = measure()
            status = send(args.url, args.key, data)
            print(f"{time.strftime('%H:%M:%S')}  cpu {data['cpu_percent']:5.1f}%  mem {data['memory_percent']:5.1f}%  "
                  f"disk {data['disk_percent']:5.1f}%  -> {status}")
            time.sleep(max(0.0, args.every - 1))
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
