#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

printf '\n%s\n' '======================================================================'
printf '%s\n' 'VARDHA VOICE CONNECT 1.4.0 - Django + Exotel + Gemini Live'
printf '%s\n' 'Python 3.11 / 3.12 / 3.13 isolated environment runner'
printf '%s\n\n' '======================================================================'

find_python() {
  local candidate
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      if "$candidate" -c 'import sys; raise SystemExit(0 if (sys.version_info.major, sys.version_info.minor) in {(3,11),(3,12),(3,13)} else 1)' >/dev/null 2>&1; then
        command -v "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

BASE_PY="$(find_python || true)"
if [[ -z "$BASE_PY" ]]; then
  echo "ERROR: Python 3.11, 3.12 or 3.13 was not found."
  echo "Install one supported Python version and run this script again."
  exit 1
fi

"$BASE_PY" --version
echo "The Python runner will create or repair .venv as required."
echo
exec "$BASE_PY" run.py
