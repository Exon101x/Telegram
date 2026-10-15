#!/usr/bin/env bash
# Convenience launcher for Linux/macOS: activates a local .venv if present,
# then runs the bot. Pass a different script name to run that instead:
#   ./run.sh generate_session.py --lib telethon
set -euo pipefail
cd "$(dirname "$0")"

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

SCRIPT="${1:-telegram_session_bot.py}"
shift || true
python3 "$SCRIPT" "$@"
