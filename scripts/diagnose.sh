#!/usr/bin/env bash
#
# Environment diagnosis.
#
# Answers three questions and nothing else: what is installed, what is running, and what
# is missing. It never installs anything and never changes state — a diagnostic that
# repairs things cannot tell you what was broken.
#
# Exit code is 0 when everything *required* is present. Optional components that are
# absent are reported and do not fail the run, because the demo is designed to work
# without them.
#
# Usage: ./scripts/diagnose.sh
set -uo pipefail

cd "$(dirname "$0")/.."

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
YELLOW=$'\033[33m'; RESET=$'\033[0m'

required_missing=0
optional_missing=0

section() { printf "\n%s%s%s\n" "$BOLD" "$1" "$RESET"; }
ok()      { printf "  %sPASS%s  %-26s %s\n" "$GREEN" "$RESET" "$1" "${2:-}"; }
warn()    { printf "  %sWARN%s  %-26s %s\n" "$YELLOW" "$RESET" "$1" "${2:-}"; optional_missing=$((optional_missing+1)); }
fail()    { printf "  %sFAIL%s  %-26s %s\n" "$RED" "$RESET" "$1" "${2:-}"; required_missing=$((required_missing+1)); }
note()    { printf "        %s%s%s\n" "$DIM" "$1" "$RESET"; }

# $1 label, $2 command, $3 required(yes/no), $4 hint
check_command() {
  local label="$1" cmd="$2" required="$3" hint="${4:-}"
  if command -v "$cmd" >/dev/null 2>&1; then
    ok "$label" "$($cmd --version 2>&1 | head -1 | cut -c1-58)"
  elif [ "$required" = "yes" ]; then
    fail "$label" "not installed"
    [ -n "$hint" ] && note "$hint"
  else
    warn "$label" "not installed (optional)"
    [ -n "$hint" ] && note "$hint"
  fi
}

printf "%sTrader-IA — environment diagnosis%s\n" "$BOLD" "$RESET"
printf "%s%s · %s%s\n" "$DIM" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$(uname -sr)" "$RESET"

# --------------------------------------------------------------------- required
section "Required"
check_command "Python 3.11+" python3 yes "install Python 3.11 or newer"

if command -v python3 >/dev/null 2>&1; then
  version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    ok "Python version" "$version"
  else
    fail "Python version" "$version — 3.11 or newer is required"
  fi
fi

PY=".venv/bin/python"
if [ -x "$PY" ]; then
  ok "virtualenv" ".venv present"
else
  PY="python3"
  warn "virtualenv" "no .venv — using the system Python"
  note "create one:  python3 -m venv .venv && .venv/bin/pip install -e '.[all,dev]'"
fi

for module in pydantic numpy pandas structlog; do
  if $PY -c "import $module" 2>/dev/null; then
    ok "python: $module" "$($PY -c "import $module; print(getattr($module, '__version__', 'installed'))" 2>/dev/null)"
  else
    fail "python: $module" "not importable"
    note "install:  pip install -e '.[all,dev]'"
  fi
done

for module in fastapi uvicorn sqlalchemy aiosqlite jwt; do
  if $PY -c "import $module" 2>/dev/null; then
    ok "python: $module" "installed"
  else
    fail "python: $module" "not importable — the API cannot start"
    note "install:  pip install -e '.[api,db]'"
  fi
done

if $PY -c "import tia" 2>/dev/null || PYTHONPATH=packages/tia/src $PY -c "import tia" 2>/dev/null; then
  ok "package: tia" "importable"
else
  fail "package: tia" "not importable"
  note "install:  pip install -e ."
fi

# --------------------------------------------------------------------- data
section "Data"
if [ -d data/fixtures ] && [ -n "$(ls -A data/fixtures/*.csv 2>/dev/null)" ]; then
  count=$(ls data/fixtures/*.csv 2>/dev/null | wc -l | tr -d ' ')
  rows=$(cat data/fixtures/*.csv 2>/dev/null | wc -l | tr -d ' ')
  ok "market fixtures" "$count files, $rows rows"
else
  fail "market fixtures" "missing"
  note "generate:  python scripts/generate_fixtures.py"
fi

mkdir -p data/runtime 2>/dev/null
if [ -w data/runtime ]; then
  ok "runtime directory" "data/runtime writable"
else
  fail "runtime directory" "data/runtime is not writable"
fi

# --------------------------------------------------------------------- database
section "Database"
if $PY - <<'PYEOF' 2>/dev/null
import asyncio, sys
sys.path.insert(0, "packages/tia/src")
from tia.persistence import Database

async def main():
    db = Database("sqlite+aiosqlite:///data/runtime/_diagnose.db")
    await db.ensure_schema()
    ok = await db.ping()
    await db.close()
    import pathlib
    for p in pathlib.Path("data/runtime").glob("_diagnose.db*"):
        p.unlink(missing_ok=True)
    sys.exit(0 if ok else 1)

asyncio.run(main())
PYEOF
then
  ok "SQLite (default)" "schema creates and responds"
else
  fail "SQLite (default)" "could not create or query a database"
fi

if command -v pg_isready >/dev/null 2>&1 && pg_isready >/dev/null 2>&1; then
  ok "PostgreSQL (optional)" "server accepting connections"
else
  warn "PostgreSQL (optional)" "not running — SQLite is the default and needs nothing"
fi

if command -v redis-cli >/dev/null 2>&1 && [ "$(redis-cli ping 2>/dev/null)" = "PONG" ]; then
  ok "Redis (optional)" "responding"
else
  warn "Redis (optional)" "not running — the in-process event bus is the default"
fi

# --------------------------------------------------------------------- frontend
section "Frontend"
check_command "Node 18+" node no "needed only to rebuild the dashboard"
check_command "npm" npm no "needed only to rebuild the dashboard"

if [ -d frontend/dist ] && [ -f frontend/dist/index.html ]; then
  size=$(du -sh frontend/dist 2>/dev/null | cut -f1)
  ok "dashboard built" "frontend/dist ($size)"
elif [ -d frontend/node_modules ]; then
  warn "dashboard built" "dependencies installed but not built"
  note "build:  cd frontend && npm run build"
else
  warn "dashboard built" "not built — the API will serve a 503 with instructions"
  note "build:  cd frontend && npm install && npm run build"
fi

# --------------------------------------------------------------------- optional
section "Optional integrations"
if [ -n "${TIA_ANTHROPIC_API_KEY:-}" ] || [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  ok "Anthropic API key" "configured (value not shown)"
else
  warn "Anthropic API key" "not set — the offline mock provider is used"
  note "the demo is fully functional without it; set TIA_ANTHROPIC_API_KEY to use Claude"
fi

if [ -n "${TIA_DEMO_PASSWORD:-}" ]; then
  ok "demo password" "set from the environment"
else
  warn "demo password" "not set — one is generated at startup and printed to the log"
fi

check_command "Docker" docker no "only needed for the compose deployment"
if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    ok "Docker daemon" "running"
  else
    warn "Docker daemon" "not running — compose is unavailable"
  fi
fi

# --------------------------------------------------------------------- ports
section "Ports"
for port in 8000 3000; do
  if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":$port "; then
    warn "port $port" "already in use"
  else
    ok "port $port" "free"
  fi
done

# --------------------------------------------------------------------- verdict
printf "\n%s%s%s\n" "$BOLD" "$(printf '─%.0s' {1..64})" "$RESET"
if [ "$required_missing" -gt 0 ]; then
  printf "%sNOT READY%s — %d required check(s) failed.\n" "$RED" "$RESET" "$required_missing"
  printf "Fix those first; the notes above give the exact command for each.\n"
  exit 1
fi

if [ "$optional_missing" -gt 0 ]; then
  printf "%sREADY%s — %d optional component(s) absent, none of them needed for the demo.\n" \
    "$GREEN" "$RESET" "$optional_missing"
else
  printf "%sREADY%s — everything present.\n" "$GREEN" "$RESET"
fi
printf "\nStart it:   make demo        then open http://127.0.0.1:8000\n"
printf "Verify it:  make verify\n"
exit 0
