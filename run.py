import os
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
SUPPORTED = {(3, 11), (3, 12), (3, 13)}


def is_supported(version_info):
    return (version_info.major, version_info.minor) in SUPPORTED


def venv_python():
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def find_supported_python():
    candidates = []
    if os.name == "nt":
        launcher = shutil.which("py")
        if launcher:
            for minor in (13, 12, 11):
                try:
                    result = subprocess.run(
                        [launcher, f"-3.{minor}", "-c", "import sys; print(sys.executable)"],
                        cwd=ROOT, check=True, capture_output=True, text=True,
                    )
                    path = result.stdout.strip().splitlines()[-1].strip()
                    if path:
                        candidates.append(Path(path))
                except (OSError, subprocess.CalledProcessError):
                    continue
    else:
        for name in ("python3.13", "python3.12", "python3.11", "python3"):
            path = shutil.which(name)
            if path:
                candidates.append(Path(path))

    for candidate in candidates:
        try:
            result = subprocess.run(
                [str(candidate), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            major, minor = map(int, result.stdout.strip().split(".")[:2])
            if (major, minor) in SUPPORTED:
                return candidate
        except (OSError, subprocess.CalledProcessError, ValueError):
            continue
    return None


def ensure_venv(base_python):
    py = venv_python()
    if py.exists():
        try:
            result = subprocess.run([str(py), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True, check=True)
            version_text = result.stdout.strip().strip("()")
            major, minor = (int(x.strip()) for x in version_text.split(",")[:2])
            if (major, minor) not in SUPPORTED:
                raise RuntimeError("unsupported venv")
        except Exception:
            print("Existing .venv uses an unsupported/interrupted Python installation; recreating it.")
            shutil.rmtree(VENV, ignore_errors=True)

    if not py.exists():
        print(f"Creating isolated virtual environment with {base_python} …")
        subprocess.check_call([str(base_python), "-m", "venv", str(VENV)], cwd=ROOT)
    return py


def run(py, *args):
    command = [str(py), *map(str, args)]
    print("\n> " + " ".join(command))
    subprocess.check_call(command, cwd=ROOT)


def main():
    version_file = ROOT / "VERSION.txt"
    try:
        app_version = version_file.read_text(encoding="utf-8").strip() or "0.0.0-dev"
    except OSError:
        app_version = "0.0.0-dev"
    print("=" * 72)
    print(f"VARDHA VOICE CONNECT — AI VOICE CALLING AGENT v{app_version}")
    print("Supported Python: 3.11 / 3.12 / 3.13")
    print("=" * 72)

    current = sys.version_info
    base_python = Path(sys.executable) if is_supported(current) else None
    if base_python is None:
        base_python = find_supported_python()
        if base_python is None:
            raise SystemExit("Python 3.11, 3.12 or 3.13 is required. Install one of these versions and run again.")
        if Path(sys.executable).resolve() != base_python.resolve():
            print(f"Current interpreter is unsupported ({current.major}.{current.minor}); switching to {base_python} …")
            os.execv(str(base_python), [str(base_python), str(Path(__file__))])

    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created .env from .env.example. Add provider credentials before placing a real call.")

    py = ensure_venv(base_python)
    run(py, "-m", "pip", "install", "--upgrade", "pip")
    run(py, "-m", "pip", "install", "-r", "requirements.txt")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "media").mkdir(exist_ok=True)
    run(py, "manage.py", "check")
    run(py, "manage.py", "migrate")
    run(py, "manage.py", "collectstatic", "--noinput")

    host = os.getenv("HOST", "127.0.0.1")
    port = os.getenv("PORT", "8000")
    base_url = f"http://{host}:{port}"
    print(f"\nStarting local ASGI server on {base_url}")
    server = subprocess.Popen(
        [str(py), "-m", "daphne", "-b", host, "-p", port, "config.asgi:application"],
        cwd=ROOT,
    )
    try:
        import requests
        deadline = time.time() + 15
        last_error = None
        smoke_paths = [
            "/", "/call", "/knowledge", "/history",
            "/api/health", "/api/dashboard", "/service-worker.js",
            f"/static/voice_agent/styles.css?v={app_version}",
            f"/static/voice_agent/app.js?v={app_version}",
        ]
        while time.time() < deadline:
            try:
                response = requests.get(base_url + "/api/health", timeout=2)
                if response.status_code == 200:
                    break
            except Exception as exc:
                last_error = exc
            if server.poll() is not None:
                raise SystemExit(
                    f"Daphne exited before readiness check completed (code {server.returncode})."
                )
            time.sleep(0.25)
        else:
            raise SystemExit(
                f"Local server smoke test timed out: {last_error or 'health endpoint not ready'}"
            )

        for path in smoke_paths:
            response = requests.get(base_url + path, timeout=5)
            if response.status_code != 200:
                raise SystemExit(
                    f"Smoke test failed: {path} returned HTTP {response.status_code}"
                )
            content_type = response.headers.get("Content-Type", "")
            body = response.text
            if not body.strip():
                raise SystemExit(f"Smoke test failed: {path} returned an empty body")
            if path.endswith(".css") and "text/css" not in content_type:
                raise SystemExit(
                    f"Smoke test failed: CSS returned Content-Type {content_type!r}"
                )
            if path.endswith(".js") and "javascript" not in content_type:
                raise SystemExit(
                    f"Smoke test failed: JavaScript returned Content-Type {content_type!r}"
                )
            if path.startswith("/api/") and "json" not in content_type:
                raise SystemExit(
                    f"Smoke test failed: API returned Content-Type {content_type!r}"
                )
        print(f"Local smoke test passed for {len(smoke_paths)} endpoints/assets.")
        print(f"Open: {base_url}")
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    main()
