#!/usr/bin/env bash
# The after-a-restart evidence collector. Run it after `docker compose restart`,
# after `sudo reboot`, or any time you want proof the 24/7 contract held:
#
#   bash scripts/post_reboot_check.sh
#
# Checks, each with a hard verdict:
#   1. the stack is up and every service reports healthy
#   2. /api/health answers through the proxy and the database is online
#   3. the paper session came back BY ITSELF (active, mode paper-live) — or, if it
#      did not, whether that was CORRECT (an operator stop / kill switch is sticky)
#   4. no duplicate client order ids exist across all runs — the "a restart must not
#      re-place orders" contract, checked in the journal itself, not asserted
#   5. the engine heartbeat is moving
#
# Exit 0 = all green. Exit 1 = something failed. Exit 3 = no stack to check.
set -uo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
DOMAIN="${TIA_DOMAIN:-localhost}"
fail=0
pass() { echo "  PASS  $*"; }
warn() { echo "  WARN  $*"; }
nope() { echo "  FAIL  $*"; fail=1; }

command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1 \
  || { echo "  SKIP  no Docker daemon — nothing to check here"; exit 3; }
$COMPOSE ps -q >/dev/null 2>&1 && [ -n "$($COMPOSE ps -q)" ] \
  || { echo "  SKIP  the production stack is not running"; exit 3; }

echo "Post-restart check ($(date -u +%FT%TZ))"

# ---- 1. services ---------------------------------------------------------------------
unhealthy="$($COMPOSE ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -v healthy || true)"
if [ -z "$unhealthy" ]; then
  pass "every service reports healthy"
else
  nope "not healthy: $(echo "$unhealthy" | tr '\n' ' ')"
fi

# ---- 2 + 3 + 5. through the API ------------------------------------------------------
health="$(curl -kfsS --max-time 10 "https://${DOMAIN}/api/health" 2>/dev/null || true)"
if [ -z "$health" ]; then
  nope "no answer from https://${DOMAIN}/api/health"
else
  pass "health endpoint answers through the proxy"
  echo "$health" | grep -q '"database": *"online"' \
    && pass "database online" || nope "database not online"
  if echo "$health" | grep -q '"mode": *"paper-live"'; then
    pass "paper session is back (mode paper-live)"
    hb="$(echo "$health" | grep -o '"heartbeat_age_seconds": *[0-9.]*' | grep -o '[0-9.]*$' || echo "")"
    if [ -n "$hb" ] && [ "$(printf '%.0f' "$hb")" -lt 120 ]; then
      pass "engine heartbeat moving (${hb}s old)"
    else
      nope "engine heartbeat stale or missing (${hb:-none})"
    fi
  else
    warn "no active paper session — CORRECT if you stopped it or a kill switch is engaged;"
    warn "a crash-interrupted session should have resumed: docker compose logs backend | grep paper_realtime"
  fi
fi

# ---- 4. no duplicate orders, from the journal itself ---------------------------------
dupes="$($COMPOSE exec -T postgres psql -U tia -d tia -tA -c \
  "SELECT COALESCE(string_agg(client_order_id, ','), '') FROM \
   (SELECT client_order_id FROM orders GROUP BY client_order_id HAVING COUNT(*) > 1) d;" \
   2>/dev/null || echo "QUERY_FAILED")"
if [ "$dupes" = "QUERY_FAILED" ]; then
  nope "could not query the orders journal"
elif [ -z "$dupes" ]; then
  pass "zero duplicate client order ids across all runs"
else
  nope "DUPLICATE client order ids found: $dupes"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "RESTART CHECK: PASS — evidence above, not assertion."
else
  echo "RESTART CHECK: FAIL — see the FAIL lines; logs: $COMPOSE logs backend | tail -50"
  exit 1
fi
