"""Start Hipstraw: the desk API (FastAPI) and the web app (Next.js), then open the reviewer desk.

    python scripts/start_hipstraw.py              # build the web app if needed, start both, open the desk
    python scripts/start_hipstraw.py --dev        # the web app in dev mode (hot reload)
    python scripts/start_hipstraw.py --fresh      # start from an empty desk (the sample requests are seeded again)
    python scripts/start_hipstraw.py --no-open    # do not open a browser

The desk API serves http://127.0.0.1:8000 (`hipstraw-mm desk serve`); the web app http://127.0.0.1:3000 and
passes /api to the desk. On first start the desk opens one sample request per thesis in input/demand/theses.
Ctrl+C stops both. No model, no API key: the playbook's rules pick the Lines.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
DB = ROOT / ".runs" / "desk.db"
CLI = "from hipstraw_mm.cli import main; raise SystemExit(main())"


def up(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait(port: int, proc: subprocess.Popen[bytes], what: str, seconds: int = 90) -> None:
    for _ in range(seconds * 5):
        if up(port):
            return
        if proc.poll() is not None:
            raise SystemExit(f"{what} stopped before it was ready (exit {proc.returncode})")
        time.sleep(0.2)
    raise SystemExit(f"{what} did not answer on port {port}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dev", action="store_true", help="run the web app with hot reload")
    parser.add_argument("--fresh", action="store_true", help="start from an empty desk")
    parser.add_argument("--no-open", action="store_true", help="do not open a browser")
    args = parser.parse_args()
    node, npm = shutil.which("node"), shutil.which("npm")
    if not node or not npm:
        raise SystemExit("Node.js is needed for the web app: https://nodejs.org")
    for port in (8000, 3000):
        if up(port):
            raise SystemExit(f"port {port} is in use: stop what runs there first")
    if args.fresh and DB.exists():
        DB.unlink()
    if not (WEB / "node_modules").exists():
        print("Installing the web app's packages (first start)...", flush=True)
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=WEB, check=True)
    next_bin = str(WEB / "node_modules" / "next" / "dist" / "bin" / "next")
    if not args.dev and not (WEB / ".next" / "BUILD_ID").exists():
        print("Building the web app (first start)...", flush=True)
        subprocess.run([node, next_bin, "build"], cwd=WEB, check=True)

    api = subprocess.Popen([sys.executable, "-c", CLI, "desk", "serve", "--port", "8000", "--db", str(DB)], cwd=ROOT)
    web = subprocess.Popen([node, next_bin, "dev" if args.dev else "start", "-p", "3000"], cwd=WEB)
    try:
        wait(8000, api, "the desk API")
        wait(3000, web, "the web app")
        url = "http://127.0.0.1:3000/desk"
        print(f"\nHipstraw is running:\n  reviewer desk       {url}\n  customer workspace  http://127.0.0.1:3000/workspace"
              f"\n  desk API            http://127.0.0.1:8000/docs\nCtrl+C stops both.", flush=True)
        if not args.no_open:
            webbrowser.open(url)
        while api.poll() is None and web.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for proc in (web, api):
            if proc.poll() is None:
                proc.terminate()


if __name__ == "__main__":
    main()
