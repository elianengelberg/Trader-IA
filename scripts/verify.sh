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

run() {
  local name="$1"; shift
  printf "\n%s▸ %s%s\n" "$BOLD" "$name" "$RESET"
  local output
  output=$("$@" 2>&1)
  local status=$?
  echo "$output" | tail -6
  NAMES+=("$name")
  if [ $status -eq 0 ]; then
    RESULTS+=("PASS"); DETAILS+=("$(echo "$output" | grep -oE '[0-9]+ passed' | tail -1)")
  else
    RESULTS+=("FAIL"); DETAILS+=("exit $status"); failures=$((failures+1))
  fi
}

soft() {
  local name="$1"; shift
  printf "\n%s▸ %s%s\n" "$BOLD" "$name" "$RESET"
  local output
  output=$("$@" 2>&1); local status=$?
  echo "$output" | tail -6
  NAMES+=("$name")
  if [ $status -eq 0 ]; then RESULTS+=("PASS"); DETAILS+=("")
  else RESULTS+=("WARN"); DETAILS+=("optional — exit $status"); fi
}

printf "%sTrader-IA — full verification%s\n" "$BOLD" "$RESET"
printf "Simulation only. No real money, no broker, no custody.\n"

run  "Lint (ruff)"            $RUFF check packages tests scripts
run  "Unit tests"             $PY -m pytest tests/unit -q
run  "Integration tests"      $PY -m pytest tests/integration -q
run  "Property tests"         $PY -m pytest tests/property -q
run  "Failure injection"      $PY -m pytest tests/failure -q
run  "End-to-end pipeline"    $PY -m pytest tests/e2e -q
soft "Frontend type check"    bash -c 'cd frontend && npm run typecheck --silent'
soft "Frontend build"         bash -c 'cd frontend && npm run build --silent'
run  "Smoke test"             ./scripts/smoke.sh

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
# run that actually happened, in a separate process, against this commit — a check the API
# could satisfy from its own memory is a check the API could satisfy by being wrong.
mkdir -p data/runtime
cat > data/runtime/verify_passed.json <<JSON
{
  "passed": $([ "$failures" -eq 0 ] && echo true || echo false),
  "failed": $failures,
  "at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "commit": "$(git rev-parse HEAD 2>/dev/null || echo unknown)",
  "dirty": $(test -n "$(git status --porcelain 2>/dev/null)" && echo true || echo false)
}
JSON

printf "\n"
if [ "$failures" -eq 0 ]; then
  printf "%sALL CHECKS PASSED%s\n" "$GREEN" "$RESET"
  printf "Nothing here is a claim about profitability. See docs/ARCHITECTURE.md §12.5.\n"
  exit 0
fi
printf "%s%d AREA(S) FAILED%s\n" "$RED" "$failures" "$RESET"
exit 1
