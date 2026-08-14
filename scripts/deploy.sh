#!/usr/bin/env bash
# Deploy (or update) the production stack on the machine this runs on, with rollback.
#
#   bash scripts/deploy.sh            # deploy HEAD of the current branch
#
# The sequence, and why it is ordered this way:
#   1. preflight   — daemon reachable, .env present, compose file parses
#   2. backup      — the database, BEFORE anything changes
#   3. build       — the new image, while the old stack still serves
#   4. swap        — up -d --wait; compose replaces containers and waits for health
#   5. verify      — /api/health answers through the proxy
#   6. rollback    — if 4 or 5 fails: retag the previous image and up -d again
#
# Exit codes: 0 deployed, 1 failed (rolled back or nothing changed), 3 no Docker here.
set -uo pipefail

COMPOSE="docker compose -f docker-compose.prod.yml"
IMAGE="trader-ia:prod"
PREVIOUS="trader-ia:previous"

say()  { echo "$(date -u +%H:%M:%S)  $*"; }
fail() { say "FAIL  $*" >&2; exit 1; }

# ---- 1. preflight --------------------------------------------------------------------
command -v docker >/dev/null 2>&1 || { say "no docker CLI — run this on the VPS"; exit 3; }
docker info >/dev/null 2>&1       || { say "no Docker daemon reachable"; exit 3; }
[ -f .env ] || fail ".env missing — cp .env.production.example .env and fill it in"
$COMPOSE config -q || fail "compose file does not parse with this .env"

# ---- 2. backup -----------------------------------------------------------------------
if $COMPOSE ps --status running postgres 2>/dev/null | grep -q postgres; then
  bash scripts/backup.sh || fail "backup failed — refusing to deploy over an unbacked database"
else
  say "SKIP  stack not running yet; nothing to back up"
fi

# ---- 3. build ------------------------------------------------------------------------
# Keep the currently deployed image reachable under :previous for rollback.
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  docker tag "$IMAGE" "$PREVIOUS"
fi
$COMPOSE build --quiet backend || fail "image build failed — nothing was touched"

# ---- 4 + 5. swap and verify ----------------------------------------------------------
rollback() {
  say "ROLLBACK  restoring previous image"
  if docker image inspect "$PREVIOUS" >/dev/null 2>&1; then
    docker tag "$PREVIOUS" "$IMAGE"
    $COMPOSE up -d --wait || say "ROLLBACK FAILED — intervene by hand: $COMPOSE logs backend"
  else
    say "no previous image to roll back to"
  fi
  exit 1
}

$COMPOSE up -d --wait --remove-orphans || rollback

# Through the proxy, like a user. -k because a localhost domain serves a local CA cert.
for _ in 1 2 3 4 5 6; do
  if curl -kfsS --max-time 5 "https://${TIA_DOMAIN:-localhost}/api/health" >/dev/null 2>&1; then
    say "PASS  deployed and healthy"
    exit 0
  fi
  sleep 5
done
say "health endpoint never answered after deploy"
rollback
