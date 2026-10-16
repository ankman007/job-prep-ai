"""Start the stack with docker compose on host ports that are actually free.

Usage: python start.py          # pick free ports, build, start
       python start.py --down   # stop the stack
"""
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
PORTS = {
    "FRONTEND_PORT": 3000,
    "BACKEND_PORT": 8000,
    "POSTGRES_PORT": 5432,
}
SCAN_LIMIT = 200


def compose(*args):
    return subprocess.run(["docker", "compose", *args], cwd=ROOT).returncode


def read_env():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def write_env(env):
    ENV_FILE.write_text("".join(f"{k}={v}\n" for k, v in env.items()))


def is_free(port):
    for host in ("0.0.0.0", "127.0.0.1"):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((host, port))
            except OSError:
                return False
    return True


def pick_port(preferred, taken):
    for port in preferred:
        if port and port not in taken and is_free(port):
            return port
    start = preferred[-1]
    for port in range(start + 1, start + SCAN_LIMIT):
        if port not in taken and is_free(port):
            return port
    sys.exit(f"No free port found in {start}-{start + SCAN_LIMIT}")


def main():
    if "--down" in sys.argv:
        sys.exit(compose("down"))

    if not (ROOT / "backend" / ".env").exists():
        sys.exit("backend/.env is missing. Copy backend/.env.example and fill it in.")

    # Release this stack's own ports so they count as free.
    compose("down")

    env = read_env()
    taken = set()
    for key, default in PORTS.items():
        saved = int(env[key]) if env.get(key, "").isdigit() else None
        port = pick_port([saved, default], taken)
        taken.add(port)
        env[key] = str(port)
    write_env(env)

    for key in PORTS:
        print(f"{key}={env[key]}")

    code = compose("up", "-d", "--build")
    if code:
        sys.exit(code)

    print(f"\nFrontend: http://localhost:{env['FRONTEND_PORT']}")
    print(f"API:      http://localhost:{env['BACKEND_PORT']}  (docs: /docs)")
    print(f"Postgres: localhost:{env['POSTGRES_PORT']}  (jobprep / jobprep)")


if __name__ == "__main__":
    main()
