#!/usr/bin/env bash
# One-time VPS preparation for Trader-IA. Run ONCE, as root, on a fresh Debian/Ubuntu:
#
#   curl -fsSL https://raw.githubusercontent.com/elianengelberg/Trader-IA/<branch>/scripts/vps_setup.sh | bash
#   # or: scp this file up and  sudo bash vps_setup.sh
#
# What it does, in order — each step prints PASS/SKIP so a re-run is safe:
#   1. system updates + unattended security upgrades
#   2. a non-root user `tia` in the docker group
#   3. Docker Engine + compose plugin (official Docker repository)
#   4. UFW: deny inbound, allow SSH/80/443 — Postgres and Redis ports stay closed
#   5. SSH hardening: keys only, no root password login (ONLY if a key is present,
#      so it can never lock you out)
#
# What it deliberately does NOT do: clone the repo, write .env, or start anything.
# Those are the deploy user's actions (docs/DEPLOYMENT.md §5–§6), not root's.
set -uo pipefail

pass() { echo "  PASS  $*"; }
skip() { echo "  SKIP  $*"; }
fail() { echo "  FAIL  $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run as root (sudo bash scripts/vps_setup.sh)"
command -v apt-get >/dev/null 2>&1 || fail "this script targets Debian/Ubuntu (apt)"

echo "Trader-IA VPS setup"

# ---- 1. updates ----------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq && apt-get upgrade -y -qq && pass "system updated"
apt-get install -y -qq unattended-upgrades ca-certificates curl gnupg ufw git rsync
dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
pass "unattended security upgrades enabled"

# ---- 2. user -------------------------------------------------------------------------
if id tia >/dev/null 2>&1; then
  skip "user tia exists"
else
  adduser --disabled-password --gecos "Trader-IA" tia
  pass "user tia created (no password — SSH keys only; add yours to ~tia/.ssh)"
fi

# ---- 3. docker -----------------------------------------------------------------------
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  skip "docker + compose already installed"
else
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/$(. /etc/os-release && echo "$ID")/gpg \
    -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/$(. /etc/os-release && echo "$ID") \
$(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
  pass "docker engine + compose plugin installed"
fi
usermod -aG docker tia
systemctl enable --now docker >/dev/null 2>&1
pass "docker enabled at boot (the stack's restart:unless-stopped rides on this)"

# ---- 3b. swap on small machines ------------------------------------------------------
# 2 GB droplets/instances run the stack fine but can run out of memory during the
# image build (the dashboard's Node build stage). A swap file is the standard net.
if [ "$(free -m | awk '/^Swap:/{print $2}')" -eq 0 ]; then
  (fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none) \
    && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile \
    && { grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab; } \
    && pass "2G swap file created and persisted (build-time safety on small RAM)" \
    || skip "could not create swap — fine on machines with 4 GB+ RAM"
else
  skip "swap already present"
fi

# ---- 4. firewall ---------------------------------------------------------------------
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow ssh >/dev/null       # FIRST, always, or the enable below cuts you off
ufw allow 80/tcp >/dev/null
ufw allow 443/tcp >/dev/null
ufw --force enable >/dev/null
pass "ufw: inbound deny; ssh/80/443 open; 5432 and 6379 closed (and unpublished anyway)"

# ---- 5. ssh hardening (guarded) ------------------------------------------------------
if [ -s /root/.ssh/authorized_keys ] || [ -s /home/tia/.ssh/authorized_keys ]; then
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
  systemctl reload ssh || systemctl reload sshd || true
  pass "ssh: password auth disabled (a key is present)"
else
  skip "ssh hardening NOT applied — no authorized_keys found; add your key first, re-run"
fi

echo
echo "Done. Next, as the tia user (docs/DEPLOYMENT.md §5):"
echo "  su - tia"
echo "  git clone https://github.com/elianengelberg/Trader-IA.git && cd Trader-IA"
echo "  bash scripts/generate_env.sh          # writes .env with generated secrets"
echo "  docker compose -f docker-compose.prod.yml up -d --build"
echo "  make production-readiness"
