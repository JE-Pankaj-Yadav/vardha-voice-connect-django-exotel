import os
import platform
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".venv"
PY = ENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
PIP = ENV / ("Scripts/pip.exe" if os.name == "nt" else "bin/pip")


def run(*args):
    print("\n>", " ".join(map(str, args)))
    subprocess.check_call([str(x) for x in args], cwd=ROOT)


def main():
    print("=" * 72)
    print("VARDHA VOICE CONNECT — AI VOICE CALLING AGENT v1.0")
    print("Local Windows runner — Python 3.11 / 3.12 / 3.13")
    print("=" * 72)
    if sys.version_info < (3, 11) or sys.version_info >= (3, 14):
        raise SystemExit("Python 3.11, 3.12 or 3.13 is required. Please install one of these versions.")

    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        print("\nCreated .env from .env.example.")
        print("Add your Exotel and OpenAI values, then restart the runner.\n")

    if not PY.exists():
        print("Creating isolated virtual environment: .venv")
        venv.EnvBuilder(with_pip=True, clear=False).create(ENV)

    run(PY, "-m", "pip", "install", "--upgrade", "pip")
    run(PIP, "install", "-r", "requirements.txt")
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "media").mkdir(exist_ok=True)
    run(PY, "manage.py", "check")
    run(PY, "manage.py", "migrate")
    run(PY, "manage.py", "collectstatic", "--noinput")
    print("\nStarting local ASGI server on http://127.0.0.1:8000")
    run(PY, "-m", "daphne", "-b", "127.0.0.1", "-p", "8000", "config.asgi:application")


if __name__ == "__main__":
    main()
