#!/usr/bin/env bash
#
# Everything, with a per-area verdict.
#
# Runs to the end rather than stopping at the first failure: a report that says "lint
# failed" and nothing else hides whether the rest works. Each area prints PASS, FAIL or
# WARN, and the exit code is non-zero if anything actually failed.
set -uo pipefail
cd "$(dirname "$0")/.."

export PYTHONPATH="packages/tia/src"
PY=".venv/bin/python"; [ -x "$PY" ] || PY="python3"
RUFF=".venv/bin/ruff"; [ -x "$RUFF" ] || RUFF="ruff"

BOLD=$'\033[1m'; RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'
declare -a NAMES RESULTS DETAILS
failures=0

# R22: every area's id, exit code, timestamps and command go to the run directory, and
# pytest areas leave their junit XML there too. `tia.live.verify_evidence finish` turns
# that into the marker the activation gate reads — bound to the artifact that was tested.
EVIDENCE_DIR="data/runtime/verify_run"
MARKER="data/runtime/verify_passed.json"
stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
record() {
  local id="$1" required="$2" status="$3" started="$4" finished="$5"; shift 5
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$id" "$required" "$status" "$started" "$finished" "$*" \
    >> "$EVIDENCE_DIR/suites.tsv"
}

run() {
  local id="$1" name="$2"; shift 2
  printf "\n%s▸ %s%s\n" "$BOLD" "$name" "$RESET"
  local output started
  started=$(stamp)
  output=$("$@" 2>&1)
  local status=$?
  record "$id" 1 "$status" "$started" "$(stamp)" "$@"
  echo "$output" | tail -6
  NAMES+=("$name")
  if [ $status -eq 0 ]; then
    RESULTS+=("PASS"); DETAILS+=("$(echo "$output" | grep -oE '[0-9]+ passed' | tail -1)")
  else
    RESULTS+=("FAIL"); DETAILS+=("exit $status"); failures=$((failures+1))
  fi
}

soft() {
  local id="$1" name="$2"; shift 2
  printf "\n%s▸ %s%s\n" "$BOLD" "$name" "$RESET"
  local output started
  started=$(stamp)
  output=$("$@" 2>&1); local status=$?
  record "$id" 0 "$status" "$started" "$(stamp)" "$@"
  echo "$output" | tail -6
  NAMES+=("$name")
  if [ $status -eq 0 ]; then RESULTS+=("PASS"); DETAILS+=("")
  else RESULTS+=("WARN"); DETAILS+=("optional — exit $status"); fi
}

printf "%sTrader-IA — full verification%s\n" "$BOLD" "$RESET"
printf "Simulation only. No real money, no broker, no custody.\n"

# Discards any previous marker (an interrupted run leaves no evidence) and records the
# identity of what is about to be tested: commit, tree, file contents, config, deps.
mkdir -p data/runtime
if ! $PY -m tia.live.verify_evidence begin --run-dir "$EVIDENCE_DIR" --marker "$MARKER"; then
  failures=$((failures+1))
fi
mkdir -p "$EVIDENCE_DIR"

J="--junitxml=$EVIDENCE_DIR"
run  lint        "Lint (ruff)"            $RUFF check packages tests scripts
run  unit        "Unit tests"             $PY -m pytest tests/unit -q "$J/unit.xml"
run  integration "Integration tests"      $PY -m pytest tests/integration -q "$J/integration.xml"
run  property    "Property tests"         $PY -m pytest tests/property -q "$J/property.xml"
run  failure     "Failure injection"      $PY -m pytest tests/failure -q "$J/failure.xml"
run  adversarial "Adversarial (synthetic)" $PY -m pytest tests/adversarial -q "$J/adversarial.xml"
run  e2e         "End-to-end pipeline"    $PY -m pytest tests/e2e -q "$J/e2e.xml"
soft frontend-typecheck "Frontend type check" bash -c 'cd frontend && npm run typecheck --silent'
soft frontend-build     "Frontend build"      bash -c 'cd frontend && npm run build --silent'
run  smoke       "Smoke test"             ./scripts/smoke.sh

printf "\n%s%s%s\n" "$BOLD" "$(printf '─%.0s' {1..66})" "$RESET"
printf "%sVERIFICATION SUMMARY%s\n\n" "$BOLD" "$RESET"
for i in "${!NAMES[@]}"; do
  case "${RESULTS[$i]}" in
    PASS) colour="$GREEN" ;;
    WARN) colour="$YELLOW" ;;
    *)    colour="$RED" ;;
  esac
  printf "  %s%-4s%s  %-26s %s\n" "$colour" "${RESULTS[$i]}" "$RESET" "${NAMES[$i]}" "${DETAILS[$i]}"
done

# Record the outcome where the live activation gate can read it. A file rather than
# in-process state on purpose: the gate's `tests_pass` check must be satisfiable only by a
# run that actually happened, in a separate process — a check the API could satisfy from
# its own memory is a check the API could satisfy by being wrong. Since R22 the file is
# schema v2: it names the artifact that was tested (and is refused for any other), every
# area's exit code and junit counts, provenance and timestamps, sealed with a digest.
# The writer re-identifies the artifact now; if anything changed during the run, the
# marker records a run that does not pass.
if ! $PY -m tia.live.verify_evidence finish --run-dir "$EVIDENCE_DIR" --marker "$MARKER" \
    --entrypoint scripts/verify.sh; then
  if [ "$failures" -eq 0 ]; then
    failures=1
    printf "%sthe evidence could not be bound to the tested artifact — the gate will refuse it%s\n" "$RED" "$RESET"
  fi
fi

printf "\n"
if [ "$failures" -eq 0 ]; then
  printf "%sALL CHECKS PASSED%s\n" "$GREEN" "$RESET"
  printf "Nothing here is a claim about profitability. See docs/ARCHITECTURE.md §12.5.\n"
  exit 0
fi
printf "%s%d AREA(S) FAILED%s\n" "$RED" "$failures" "$RESET"
exit 1
