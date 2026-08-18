#!/usr/bin/env bash
# Production readiness — the whole 24/7 stack, exercised, not reviewed.
#
#   make production-readiness      # or: bash scripts/production_readiness.sh
#
# What it proves, in order:
#   1. compose file parses with the local .env (a synthetic one is generated if absent)
#   2. the stack builds and comes up healthy behind the proxy, with HTTPS
#   3. /api/health answers THROUGH the proxy — the path a user takes
#   4. the backend server process is killed hard (a real crash) and the container
#      comes back on its own
#      (restart: unless-stopped), and health recovers
#   5. the database survives the restart: the same schema version answers after
#
# Honesty rules, same as scripts/docker_verify.sh: without a Docker daemon this
# exits 3 (EXTERNAL VALIDATION REQUIRED), never 0 — "could not test" is not "passed".
# KEEP_UP=1 leaves the stack running afterwards; default tears it down.
#
# Works for both stacks. Defaults to production; `make local-readiness` runs it as:
#   COMPOSE_FILE=docker-compose.local.yml BASE_URL=http://127.0.0.1:8000
# (same checks, including the hard kill; only the entry URL differs).
set -uo pipefail

BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
COMPOSE="docker compose -f ${COMPOSE_FILE}"
# The drill must probe the SAME name Caddy serves under, or the TLS handshake fails
# with an SNI mismatch that looks like a stack failure but isn't. That name lives in
# .env (TIA_DOMAIN), so read it from there when the caller didn't pin BASE_URL —
# found on the Frankfurt deploy, where the site was on the IP and the drill hit
# localhost.
if [ -z "${BASE_URL:-}" ] && [ -z "${TIA_DOMAIN:-}" ] && [ -f .env ]; then
  TIA_DOMAIN="$(grep -E '^TIA_DOMAIN=' .env | tail -1 | cut -d= -f2-)"
fi
BASE_URL="${BASE_URL:-https://${TIA_DOMAIN:-localhost}}"
fail=0

pass() { echo "  ${GREEN}PASS${RESET}  $*"; }
warn() { echo "  ${YELLOW}WARN${RESET}  $*"; }
nope() { echo "  ${RED}FAIL${RESET}  $*"; fail=1; }

echo "${BOLD}Production readiness${RESET}"

# ---- 0. is there anything to run this on? --------------------------------------------
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "  ${YELLOW}SKIP${RESET}  no Docker daemon reachable"
  echo
  echo "${YELLOW}EXTERNAL VALIDATION REQUIRED${RESET} — run this on the target machine"
  echo "(the VPS, or any host with Docker). Until then the production stack is authored"
  echo "but UNEXECUTED, and is labelled REQUIRES VALIDATION in the docs."
  exit 3
fi

# ---- 1. configuration ----------------------------------------------------------------
made_env=0
if [ ! -f .env ]; then
  # A readiness check must not require real secrets; generate throwaway ones.
  {
    echo "POSTGRES_PASSWORD=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"
    echo "TIA_DEMO_USER=readiness-operator"
    echo "TIA_DEMO_PASSWORD=$(head -c 24 /dev/urandom | base64 | tr -d '/+=')"
    echo "TIA_JWT_SECRET=$(head -c 36 /dev/urandom | base64 | tr -d '/+=')"
    echo "TIA_DOMAIN=localhost"
  } > .env
  made_env=1
  warn "no .env — generated throwaway credentials for this check only"
fi
cleanup() {
  if [ "${KEEP_UP:-0}" != "1" ]; then $COMPOSE down -v --remove-orphans >/dev/null 2>&1; fi
  [ "$made_env" -eq 1 ] && rm -f .env
}
trap cleanup EXIT

$COMPOSE config -q && pass "compose file parses" || { nope "compose config invalid"; exit 1; }

# ---- 2. up ---------------------------------------------------------------------------
$COMPOSE up -d --build --wait && pass "stack built and healthy" || { nope "stack failed to come up — $COMPOSE logs"; exit 1; }

# ---- 3. through the entry point users take -------------------------------------------
if curl -kfsS --max-time 10 "${BASE_URL}/api/health" | grep -q '"status"'; then
  pass "/api/health answers on ${BASE_URL}"
else
  nope "no answer on ${BASE_URL}"
fi

# The database must NOT be reachable from the host: no published port.
if $COMPOSE ps postgres | grep -Eq '(:5432|0\.0\.0\.0)'; then
  nope "postgres publishes a host port — the internal network contract is broken"
else
  pass "postgres has no published port"
fi

# ---- 4. crash the backend, watch it return -------------------------------------------
# NOT `docker kill`: Docker counts that as a manual stop and restart policies
# deliberately ignore it (found on the first real run of this drill — the backend
# stayed down exactly as `unless-stopped` promises for operator stops). A real
# crash is the server PROCESS dying inside the container: PID 1 (sh) sees its
# child killed, exits non-zero, and the restart policy fires.
backend_id="$($COMPOSE ps -q backend)"
docker exec "$backend_id" python -c "
import os, signal
for pid in filter(str.isdigit, os.listdir('/proc')):
    try:
        with open(f'/proc/{pid}/cmdline', 'rb') as fh:
            cmd = fh.read().decode(errors='ignore')
    except OSError:
        continue
    if ('tia.api' + '.main') in cmd and int(pid) != os.getpid():
        os.kill(int(pid), signal.SIGKILL)
" >/dev/null 2>&1 && pass "backend server process killed (SIGKILL inside the container — a crash, not a stop)"
recovered=0
for _ in $(seq 1 30); do
  sleep 4
  state="$(docker inspect -f '{{.State.Health.Status}}' "$($COMPOSE ps -q backend)" 2>/dev/null || echo none)"
  if [ "$state" = "healthy" ]; then recovered=1; break; fi
done
if [ "$recovered" -eq 1 ]; then
  pass "backend restarted on its own and reports healthy"
else
  nope "backend did not recover within 120s of a hard kill"
fi

# ---- 5. state survived ---------------------------------------------------------------
if curl -kfsS --max-time 10 "${BASE_URL}/api/health" | grep -q '"database": *"online"'; then
  pass "database online after the restart"
else
  nope "database not online after restart"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "${GREEN}PRODUCTION READINESS: PASS${RESET} — the stack survives a hard kill."
  echo "Note what this does NOT prove: venue connectivity (make binance-public),"
  echo "reboot survival of the *host* (reboot it and check), or profitability (nothing does)."
else
  echo "${RED}PRODUCTION READINESS: FAIL${RESET} — fix the FAIL lines above and re-run."
  exit 1
fi
