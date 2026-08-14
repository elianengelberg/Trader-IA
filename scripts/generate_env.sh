#!/usr/bin/env bash
# Write a production .env with cryptographically generated secrets. Never prints them.
#
#   bash scripts/generate_env.sh              # refuses if .env already exists
#   FORCE=1 bash scripts/generate_env.sh      # overwrite (the old file is backed up)
#
# Generates: POSTGRES_PASSWORD, TIA_DEMO_PASSWORD, TIA_JWT_SECRET.
# Asks for nothing and prints no secret — the only output is what was written where.
# TIA_DEMO_USER defaults to "operator" (change it in the file if you want another name).
# Optional values (domain, webhook, API keys) are left empty for you to fill in.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ] && [ "${FORCE:-0}" != "1" ]; then
  echo "REFUSED: .env already exists. FORCE=1 to overwrite (a timestamped backup is kept)."
  exit 1
fi
[ -f .env ] && cp .env ".env.backup.$(date -u +%Y%m%d-%H%M%S)" && chmod 600 .env.backup.*

gen() { python3 -c "import secrets; print(secrets.token_urlsafe($1))"; }

POSTGRES_PASSWORD="$(gen 32)"
TIA_DEMO_PASSWORD="$(gen 24)"
TIA_JWT_SECRET="$(gen 48)"

umask 177  # the file is born 600, not chmod'ed after
cat > .env <<EOF
# Trader-IA production environment — generated $(date -u +%Y-%m-%dT%H:%M:%SZ) by
# scripts/generate_env.sh. Secrets are machine-generated; nothing here was ever
# displayed or transmitted. This file is gitignored. Keep it mode 600.

# ---- required ----
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
TIA_DEMO_USER=operator
TIA_DEMO_PASSWORD=${TIA_DEMO_PASSWORD}
TIA_JWT_SECRET=${TIA_JWT_SECRET}

# ---- recommended (fill in) ----
# Domain with DNS pointing at this machine -> automatic Let's Encrypt HTTPS.
TIA_DOMAIN=localhost
# Any JSON-POST endpoint (Discord/Slack webhook, ntfy, ...). Empty = alerts stay
# in the database and the dashboard only.
TIA_ALERT_WEBHOOK_URL=
BACKUP_KEEP=14

# ---- optional ----
TIA_ANTHROPIC_API_KEY=
# Venue credentials: NOT needed for the 24/7 paper session. When the time comes,
# paste them HERE on this machine (never into a chat), key restricted to:
# reading + spot trading only, withdrawals disabled, IP-locked to this server.
TIA_BINANCE_API_KEY=
TIA_BINANCE_API_SECRET=
EOF

echo "PASS  .env written (mode 600). Your dashboard login: operator / <see the file>."
echo "      Read the password with:  grep TIA_DEMO_PASSWORD .env"
echo "      Nothing was printed here on purpose — terminals get logged."
