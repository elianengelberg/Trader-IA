#!/usr/bin/env bash
#
# Smoke test: start the whole system, drive it through a browser, stop it.
#
# The server is started here rather than assumed to be running, so this works from a cold
# checkout and so a failure cannot be "you forgot to start it". The server is stopped on
# any exit path, including a failure, because leaving a process on port 8000 makes the
# next run fail for the wrong reason.
set -uo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
export PYTHONPATH="packages/tia/src"
export TIA_DEMO_USER="${TIA_DEMO_USER:-operator}"
export TIA_DEMO_PASSWORD="${TIA_DEMO_PASSWORD:-smoke-test-password}"

PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"

if [ ! -f frontend/dist/index.html ]; then
  echo "FAIL  the dashboard is not built — run: cd frontend && npm install && npm run build"
  exit 1
fi

mkdir -p data/runtime
SMOKE_DB="data/runtime/smoke.db"
rm -f "$SMOKE_DB" "$SMOKE_DB"-* 2>/dev/null
export TIA_DATABASE_URL="sqlite+aiosqlite:///./$SMOKE_DB"

echo "Starting the server on http://$HOST:$PORT"
$PY -m uvicorn tia.api.main:app --host "$HOST" --port "$PORT" --log-level warning > /tmp/tia-smoke.log 2>&1 &
SERVER_PID=$!
cleanup() {
  kill "$SERVER_PID" 2>/dev/null
  wait "$SERVER_PID" 2>/dev/null
  rm -f "$SMOKE_DB" "$SMOKE_DB"-* 2>/dev/null
}
trap cleanup EXIT

for _ in $(seq 1 40); do
  if curl -sf -m 2 "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done

if ! curl -sf -m 3 "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
  echo "FAIL  the server did not become healthy"
  tail -20 /tmp/tia-smoke.log
  exit 1
fi
echo "PASS  server is healthy"

if $PY -c "import playwright" 2>/dev/null; then
  $PY scripts/browser_smoke.py --url "http://$HOST:$PORT"
  exit $?
fi

echo "WARN  playwright is not installed; running the API-only smoke path"
echo "      install it with:  pip install playwright"
JAR=$(mktemp)
fail=0
step() {
  local name="$1" expected="$2" got="$3"
  if [ "$got" = "$expected" ]; then printf "PASS  %-46s %s\n" "$name" "$got"
  else printf "FAIL  %-46s got %s, wanted %s\n" "$name" "$got" "$expected"; fail=1; fi
}
code() { curl -s -o /dev/null -w "%{http_code}" -m 10 "$@"; }

step "unauthenticated request is refused" 401 "$(code "http://$HOST:$PORT/api/runtime")"
step "login" 200 "$(code -c "$JAR" -X POST "http://$HOST:$PORT/api/auth/login" -H 'content-type: application/json' -d "{\"username\":\"$TIA_DEMO_USER\",\"password\":\"$TIA_DEMO_PASSWORD\"}")"
step "dashboard is served" 200 "$(code "http://$HOST:$PORT/")"
step "start a run" 200 "$(code -b "$JAR" -X POST "http://$HOST:$PORT/api/runtime/start" -H 'content-type: application/json' -d '{"scenario":"trend_up","initial_capital":10000,"bar_interval_seconds":0.02}')"
sleep 12
step "portfolio responds" 200 "$(code -b "$JAR" "http://$HOST:$PORT/api/portfolio")"
step "decisions responds" 200 "$(code -b "$JAR" "http://$HOST:$PORT/api/decisions")"
bars=$(curl -s -b "$JAR" "http://$HOST:$PORT/api/runtime" | $PY -c 'import json,sys; print(json.load(sys.stdin).get("counters",{}).get("bars",0))')
if [ "${bars:-0}" -gt 0 ]; then printf "PASS  %-46s %s bars\n" "market data is being processed" "$bars"
else printf "FAIL  %-46s no bars processed\n" "market data is being processed"; fail=1; fi
step "stop the run" 200 "$(code -b "$JAR" -X POST "http://$HOST:$PORT/api/runtime/stop")"
rm -f "$JAR"

[ "$fail" -eq 0 ] && { echo "RESULT: PASS"; exit 0; } || { echo "RESULT: FAIL"; exit 1; }
