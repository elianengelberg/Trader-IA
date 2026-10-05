#!/usr/bin/env bash
# Binance Spot TESTNET validation of the live market-making service, end to end, from the VPS.
#
# One command, every step checked before the next:
#   1. the repo is on the expected branch, fast-forwarded, clean;
#   2. the image is rebuilt from that HEAD (the commit is baked in as TIA_COMMIT);
#   3. the Testnet keys are present in this shell's environment (values are never printed,
#      never written; this script does not read .env) and every host is testnet.binance.vision;
#   4. the latency profile is MEASURED NOW against Spot Testnet public market data from this host,
#      into a directory of its own. The production data volume (trader-ia_tia-data) holds the
#      profile the paper maker measured against Mainnet public data; it is never read or written;
#   5. the profile is loaded through the same code the validator uses, at the validator's path,
#      inside the container, and its source must name Testnet;
#   6. the service validation runs for $MINUTES minutes, Testnet only, no token, no real money;
#   7. the evidence is kept under $OUT, scanned for sensitive keys, and copied unmodified into
#      docs/evidence/ (the earlier service runs' JSONs too, if found) — a FAIL is kept as a FAIL.
#
# Nothing here provokes a fill, relaxes a rail, touches .env, docker-compose or the running service.
#
# Usage, as the shell that holds the Testnet keys (exported, never pasted):
#   bash scripts/run_mm_service_testnet_validation.sh
# Knobs (environment): MINUTES=3 PROFILE_MINUTES=5 CAP_USD=200 OUT=/home/tia/tia-testnet
#   RECOVERY_DRILL=1   after the window the service dies with quotes resting and a second one
#                      starts on the same account (items R1-R7: sweep, clean reconciliation, own ids)
#   FILL_PROBE=1800    then the block validator rests a post-only bid AT the best bid and an ask AT
#                      the best ask for that many seconds, re-pegged to the best every 30 s, and
#                      checks a real fill if the market comes (never forced; NOT TESTED otherwise)
#   S8_EXPERIMENT=1    EXPERIMENTAL: the service validation runs with the three harness overrides
#                      (--fee-scenario testnet_zero --quote-ttl-ms 30000 --requote-threshold-bps 5)
#                      so the engine's own quotes can rest long enough to be filled on Testnet.
#                      Quoting parameters only, recorded in the evidence; not a strategy, not a
#                      Mainnet fee assumption; the stale-data threshold and every rail unchanged.

set -euo pipefail

REPO="${REPO:-/home/tia/Trader-IA}"
BRANCH="${BRANCH:-claude/algo-trading-simulation-platform-ngf7xo}"
IMAGE="${IMAGE:-trader-ia:prod}"
OUT="${OUT:-/home/tia/tia-testnet}"
RUNTIME="${RUNTIME:-$OUT/runtime}"
PROFILE_IN_CONTAINER=/app/data/runtime/mm/latency_profile.json
MINUTES="${MINUTES:-3}"
PROFILE_MINUTES="${PROFILE_MINUTES:-5}"
CAP_USD="${CAP_USD:-200}"
RECOVERY_DRILL="${RECOVERY_DRILL:-0}"
FILL_PROBE="${FILL_PROBE:-0}"
S8_EXPERIMENT="${S8_EXPERIMENT:-0}"
REST_URL=https://testnet.binance.vision
STREAM_URL=wss://stream.testnet.binance.vision/stream
WS_URL=wss://ws-api.testnet.binance.vision/ws-api/v3
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN_AS="$(id -u):$(id -g)"

say() { printf '\n== %s\n' "$*"; }
die() { printf '\nSTOP: %s\n' "$*" >&2; exit 1; }
# Sensitive JSON keys. Item names such as "no_activation_token" are not keys named token.
SENSITIVE_KEYS='"(apiKey|api_key|apiSecret|api_secret|secret|signature|authorization|password|listenKey|token)"[[:space:]]*:'

say "1. repo state (fast-forward only)"
cd "$REPO"
git fetch origin "$BRANCH"
git checkout -q "$BRANCH"
git pull --ff-only origin "$BRANCH"
HEAD=$(git rev-parse --short HEAD)
[ -z "$(git status --short)" ] || die "the working tree is not clean; resolve by hand, no reset"
echo "HEAD $HEAD on $(git branch --show-current)"

say "2. image $IMAGE from $HEAD"
docker build -t "$IMAGE" --build-arg GIT_COMMIT="$HEAD" .
docker run --rm "$IMAGE" python -c 'import os; print("TIA_COMMIT baked into the image:", os.environ.get("TIA_COMMIT"))'

say "3. credentials present? (values never printed) and Testnet-only hosts"
[ -n "${TIA_LIVE__BINANCE_API_KEY:-}" ] && echo "API_KEY present: YES" || die "TIA_LIVE__BINANCE_API_KEY is not in this shell's environment; export it in the shell, paste it nowhere"
[ -n "${TIA_LIVE__BINANCE_API_SECRET:-}" ] && echo "API_SECRET present: YES" || die "TIA_LIVE__BINANCE_API_SECRET is not in this shell's environment"
export TIA_LIVE__BINANCE_API_KEY TIA_LIVE__BINANCE_API_SECRET
for url in "$REST_URL" "$STREAM_URL" "$WS_URL"; do
  case "$url" in *testnet.binance.vision*) ;; *) die "not a Testnet host: $url";; esac
done
echo "REST   $REST_URL"; echo "STREAM $STREAM_URL"; echo "WS-API $WS_URL"

say "4. latency profile: measured now, on this host, against Spot Testnet ($PROFILE_MINUTES min, public data, no keys)"
mkdir -p "$RUNTIME/mm" "$OUT"
if [ -e "$RUNTIME/mm/latency_profile.json" ]; then
  mv "$RUNTIME/mm/latency_profile.json" "$RUNTIME/mm/latency_profile_${STAMP}_previous.json"
  echo "a previous Testnet profile was set aside as latency_profile_${STAMP}_previous.json"
fi
pstatus=0
docker run --rm --name tia-mm-latency-testnet --user "$RUN_AS" \
  -e TIA_COMMIT="$HEAD" \
  -v "$RUNTIME:/app/data/runtime" \
  "$IMAGE" python scripts/mm_market_data_check.py --symbol BTC-USD --minutes "$PROFILE_MINUTES" --no-record \
    --rest-url "$REST_URL" --stream-url "$STREAM_URL" \
    --write-latency-profile "$PROFILE_IN_CONTAINER" --json \
  2>&1 | tee "$OUT/mm_latency_profile_testnet_${HEAD}_$STAMP.log" || pstatus=$?
echo "market data check exit status: $pstatus (0 = the six hard Phase 2 criteria held; the profile is judged on its own below)"
[ -s "$RUNTIME/mm/latency_profile.json" ] || die "no profile was written; the report above says which component had no samples (nothing is invented)"

say "5. the profile, loaded by the validator's own code at the validator's path inside the container"
find /home/tia /root -type f -name 'latency_profile*.json' 2>/dev/null || true
docker run --rm --user "$RUN_AS" -v "$RUNTIME:/app/data/runtime:ro" "$IMAGE" python - <<'PY'
from tia.mm.latency_model import LatencyProfile
p = LatencyProfile.load("/app/data/runtime/mm/latency_profile.json")
print("profile_id", p.profile_id, "commit", p.commit, "measured_at_utc", p.measured_at_utc, "duration_s", p.duration_s, "symbol", p.symbol)
print("source", p.source)
for name, s in p.measured.items():
    print(f"  {name}: count {s.count} p50 {s.p50} p95 {s.p95} p99 {s.p99} max {s.max}")
assert "testnet.binance.vision" in p.source, "this profile was not measured against Spot Testnet"
assert all(s.count > 0 for s in p.measured.values()), "a measured component has no samples"
PY

DRILL=()
[ "$RECOVERY_DRILL" = "1" ] && DRILL=(--recovery-drill)
EXPERIMENT=()
[ "$S8_EXPERIMENT" = "1" ] && EXPERIMENT=(--fee-scenario testnet_zero --quote-ttl-ms 30000 --requote-threshold-bps 5)
say "6. the service validation: $MINUTES min on Spot Testnet, capital cap $CAP_USD USD, profile measured above${DRILL:+, then the recovery drill}${EXPERIMENT:+; EXPERIMENTAL overrides: ${EXPERIMENT[*]}}"
JSON_NAME="mm_service_testnet_${HEAD}_$STAMP.json"
[ -e "$OUT/$JSON_NAME" ] && die "$OUT/$JSON_NAME already exists; evidence is never overwritten"
status=0
docker run --rm --name tia-mm-service-testnet --user "$RUN_AS" \
  -e TIA_COMMIT="$HEAD" \
  --env TIA_LIVE__BINANCE_API_KEY --env TIA_LIVE__BINANCE_API_SECRET \
  --env TIA_LIVE__USE_TESTNET=true --env TIA_MM__REAL_MONEY=false \
  -v "$RUNTIME:/app/data/runtime:ro" -v "$OUT:/out" \
  "$IMAGE" python scripts/validate_mm_live_service_testnet.py \
    --minutes "$MINUTES" --capital-cap-usd "$CAP_USD" --profile "$PROFILE_IN_CONTAINER" \
    --rest-url "$REST_URL" --ws-url "$WS_URL" --stream-url "$STREAM_URL" \
    --json-out "/out/$JSON_NAME" "${DRILL[@]}" "${EXPERIMENT[@]}" \
  2>&1 | tee "$OUT/${JSON_NAME%.json}.log" || status=$?
echo "validator exit status: $status (0 = no FAIL; anything else is kept as it is)"
[ -s "$OUT/$JSON_NAME" ] || die "the validator wrote no evidence file"

if [ "$FILL_PROBE" != "0" ]; then
  say "6b. fill probe: post-only bid AT the best bid and ask AT the best ask for $FILL_PROBE s, re-pegged every 30 s; a fill is checked if the market comes, never forced"
  PROBE_NAME="mm_testnet_fillprobe_${HEAD}_$STAMP.json"
  pstatus2=0
  docker run --rm --name tia-mm-fill-probe --user "$RUN_AS" \
    -e TIA_COMMIT="$HEAD" \
    --env TIA_LIVE__BINANCE_API_KEY --env TIA_LIVE__BINANCE_API_SECRET \
    --env TIA_LIVE__USE_TESTNET=true --env TIA_MM__REAL_MONEY=false \
    -v "$OUT:/out" \
    "$IMAGE" python scripts/validate_mm_testnet.py --symbol BTC-USD --percent-away 2.0 \
      --rest-url "$REST_URL" --ws-url "$WS_URL" \
      --fill-probe "$FILL_PROBE" --fill-probe-sides both --fill-probe-repeg 30 \
      --json-out "/out/$PROBE_NAME" \
    2>&1 | tee "$OUT/${PROBE_NAME%.json}.log" || pstatus2=$?
  echo "fill probe exit status: $pstatus2 (0 = no FAIL; NOT TESTED items mean the market did not come)"
fi

say "7. evidence: scanned for sensitive keys, copied unmodified (FAIL stays FAIL)"
copy_evidence() {
  local file="$1"
  [ -f "$file" ] || return 0
  if grep -qiE "$SENSITIVE_KEYS" "$file"; then
    echo "NOT COPIED: $file names a sensitive key; inspect it by hand without printing values"
  elif [ -e "docs/evidence/$(basename "$file")" ]; then
    echo "already in docs/evidence/: $(basename "$file")"
  else
    cp "$file" docs/evidence/ && echo "copied: $(basename "$file")"
  fi
}
copy_evidence "$OUT/$JSON_NAME"
[ "$FILL_PROBE" != "0" ] && copy_evidence "$OUT/$PROBE_NAME"
# The two earlier service runs wrote to the $HOME/tia-testnet of the shell that ran them.
for earlier in /root/tia-testnet/mm_service_testnet_*.json "$OUT"/mm_service_testnet_2026*.json; do
  case "$earlier" in *"$JSON_NAME") ;; *) copy_evidence "$earlier";; esac
done
if [ -n "$(git status --short docs/evidence)" ]; then
  git add docs/evidence/*.json
  git commit -q -m "Evidence: Binance Spot Testnet service validation on $HEAD ($STAMP), unmodified" && echo "committed" || echo "nothing committed"
  git push origin "$BRANCH" || echo "push failed; the evidence is committed locally and kept under $OUT"
else
  echo "nothing new under docs/evidence/"
fi

say "done — read the PASS / FAIL / NOT TESTED block above; evidence: $OUT/$JSON_NAME"
