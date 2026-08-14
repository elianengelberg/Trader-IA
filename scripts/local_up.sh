#!/usr/bin/env bash
# One command from a clone to the autonomous local stack:
#
#   bash scripts/local_up.sh
#
# What it does: checks Docker, generates .env if missing (secrets never printed),
# builds and starts docker-compose.local.yml, waits for health, and prints where the
# dashboard is and what to do about reboots. Idempotent — re-running updates in place.
#
# Exit 0 = stack healthy on http://127.0.0.1:8000. Exit 3 = no Docker here (honest).
set -uo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.local.yml"

say()  { echo "  $*"; }
fail() { echo "  FAIL  $*" >&2; exit 1; }

echo "Trader-IA — local stack"

# ---- docker ---------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  say "SKIP  no docker CLI."
  say "      Windows/macOS: install Docker Desktop  -> docs.docker.com/desktop"
  say "      Linux:         install Docker Engine   -> docs.docker.com/engine/install"
  exit 3
fi
if ! docker info >/dev/null 2>&1; then
  say "SKIP  Docker is installed but not running. Start Docker Desktop (or:"
  say "      sudo systemctl start docker) and re-run this script."
  exit 3
fi
say "PASS  Docker daemon reachable"

# ---- .env -----------------------------------------------------------------------------
if [ ! -f .env ]; then
  bash scripts/generate_env.sh || fail ".env generation failed"
else
  say "PASS  .env already present (kept as-is)"
fi

# ---- up -------------------------------------------------------------------------------
$COMPOSE config -q || fail "compose file does not parse with this .env"
$COMPOSE up -d --build --wait || {
  echo
  $COMPOSE ps
  fail "stack did not reach healthy — logs: $COMPOSE logs backend | tail -30"
}
say "PASS  stack up and healthy"

# ---- health, like a user would --------------------------------------------------------
if curl -fsS --max-time 10 "http://127.0.0.1:8000/api/health" | grep -q '"status"'; then
  say "PASS  /api/health answers on http://127.0.0.1:8000"
else
  fail "the backend container is healthy but 127.0.0.1:8000 does not answer"
fi

echo
echo "  Dashboard:  http://127.0.0.1:8000   (this machine only — nothing is on your LAN)"
echo "  Login:      operator / the password inside .env  (grep TIA_DEMO_PASSWORD .env)"
echo "  Start the 24/7 paper session from the LIVE tab — it will resume by itself"
echo "  after a crash or reboot; a manual stop or kill switch stays stopped."
echo
echo "  So it survives reboots WITHOUT you: Docker itself must start at boot —"
echo "    Windows/macOS: Docker Desktop -> Settings -> General -> 'Start when you log in'"
echo "    Linux:         sudo systemctl enable docker"
echo "  Then prove it:  restart your PC and run  bash scripts/post_reboot_check.sh"
echo "  (with COMPOSE_FILE=docker-compose.local.yml BASE_URL=http://127.0.0.1:8000)"
echo "  or simply:      make local-restart-check"
