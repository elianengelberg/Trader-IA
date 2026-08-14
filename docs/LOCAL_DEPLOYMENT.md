# Local deployment — an autonomous system on your own PC

This runs the full paper platform on the machine you are sitting at: Docker stack,
PostgreSQL, daily backups, the dashboard on `http://127.0.0.1:8000`, automatic recovery
after reboots, and every safety control intact. Your PC is the server.

**Honesty header.** Authored without a Docker daemon, so `docker-compose.local.yml` and
the commands below carry the same REQUIRES VALIDATION label as the production stack
until `make local-readiness` has run green on your machine. The application behavior
behind them — session resume, sticky stops, watchdogs — is covered by the test suite.

## 1. What you get, and the one honest limit

```
your PC ──► Docker ──► backend (127.0.0.1:8000) ──► dashboard in your browser
                   ├─► postgres   (internal network only — no port on your machine)
                   └─► backup     (daily pg_dump to its own volume)
```

The limit is in the mission statement itself: **this runs while your PC is on.** Sleep,
hibernation and a closed laptop lid all pause it — Docker freezes with the OS — and the
paper track record only accrues while the machine is awake. That is not a bug to fix
but the trade you chose; when it stops being acceptable, `docs/DEPLOYMENT.md` is the
same system on a VPS. On a desktop that stays on, disable sleep (Windows: Power
settings → never sleep when plugged in; macOS: Energy Saver → prevent automatic
sleeping) and the difference from a VPS shrinks to power cuts.

## 2. Requirements

| OS | What to install | Note |
|---|---|---|
| Windows 10/11 | Docker Desktop ([docs.docker.com/desktop](https://docs.docker.com/desktop/)) | uses WSL2 (the installer sets it up). Run the commands below in the WSL2/Ubuntu terminal or Git Bash |
| macOS | Docker Desktop | Apple Silicon and Intel both fine |
| Linux | Docker Engine + compose plugin ([docs.docker.com/engine/install](https://docs.docker.com/engine/install/)) | add yourself to the `docker` group |

Plus `git`. Nothing else — Python, Node and Postgres all live inside the containers.

## 3. Start it (one command)

```bash
git clone https://github.com/elianengelberg/Trader-IA.git && cd Trader-IA
git checkout claude/algo-trading-simulation-platform-ngf7xo
bash scripts/local_up.sh
```

The script checks Docker, generates `.env` (mode 600, secrets machine-generated and
never printed), builds, starts, waits for health, and prints where everything is.
Login: `operator` / the password inside `.env` (`grep TIA_DEMO_PASSWORD .env`).

The dashboard binds to **127.0.0.1 only** — reachable from this machine, invisible to
your LAN and the internet. That is the local security model: nothing to firewall
because nothing is exposed. (Phone/tablet access is what the VPS deployment is for.)

## 4. Start the 24/7 paper session

Open `http://127.0.0.1:8000` → LIVE tab → **Start 24/7 paper session**. Real Binance
market data (mainnet public endpoints, keyless, read-only), simulated fills, no
credentials anywhere. The status banner shows Environment PAPER, System ONLINE,
the engine heartbeat, and DISARMED.

## 5. Reboot recovery — two layers, then proof

1. **Docker must start at boot** (this is the one thing only you can configure):
   * Windows/macOS: Docker Desktop → Settings → General → **"Start Docker Desktop when
     you sign in"**. Note: containers start at *sign-in*, not before — auto-login or a
     manual login after reboot is part of the deal on a desktop OS.
   * Linux: `sudo systemctl enable docker` — containers return before anyone logs in.
2. **Everything else is automatic.** `restart: unless-stopped` brings the containers
   back; the backend applies migrations, recovers state, reloads the evidence store,
   reconciles, and resumes a crash-interrupted paper session by itself. An operator
   stop or an engaged kill switch stays down across reboots — sticky means sticky.

Prove it, don't assume it:

```bash
# soft: container restart
docker compose -f docker-compose.local.yml restart backend
make local-restart-check

# hard: reboot your PC, log in, then
make local-restart-check
```

The check collects evidence: services healthy, health endpoint answering, the paper
session back by itself (or correctly held down), the heartbeat moving, and **zero
duplicate client order ids** read straight from the orders journal.

## 6. The full drill

```bash
make local-readiness
```

Same hard checks as the production readiness script — build, health, Postgres publishes
no host port, SIGKILL the backend and require self-recovery, database intact after —
pointed at the local stack. Exit 0 is the claim; exit 3 means it could not run.

## 7. Binance validation and testnet

```bash
make binance-public          # no account, no key — validates the data path
```

Then, when you want the execution path validated too: create keys at
[testnet.binance.vision](https://testnet.binance.vision) (fake balances, separate from
any real account), add them to `.env` **on this machine, never in a chat**
(`TIA_BINANCE_API_KEY=…`, `TIA_BINANCE_API_SECRET=…`), and:

```bash
set -a && source .env && set +a
make binance-testnet         # signing, permissions, fees, listenKey, and one order:
                             # place → duplicate rejected → cancel → final state
docker compose -f docker-compose.local.yml up -d   # restart so the backend sees the keys
```

Mainnet stays untouched: the system remains DISARMED, `max_live_capital` is 0, and
arming still requires the 27-check gate plus a typed confirmation phrase — none of
which this document goes near.

## 8. Backups and restore

The `backup` container writes a daily `pg_dump` to the `tia-local-backups` volume,
keeping the newest `BACKUP_KEEP` (default 14). On demand: `make backup` (it detects
whichever stack is running). Copy them off this disk — an external drive or cloud
folder; a backup on the disk it protects is a wish:

```bash
docker run --rm -v trader-ia_tia-local-backups:/b -v "$PWD/backups-copy":/out alpine \
  sh -c "cp /b/*.sql.gz /out/"
```

Restore drill (once, before you need it):

```bash
docker compose -f docker-compose.local.yml stop backend
gunzip -c backups-copy/tia-YYYYMMDD-HHMMSS.sql.gz | \
  docker compose -f docker-compose.local.yml exec -T postgres psql -U tia -d tia
docker compose -f docker-compose.local.yml start backend
```

## 9. Day-to-day

| Want | Command |
|---|---|
| Status + health | `make local-status` |
| Logs | `make local-logs` |
| Yesterday's activity | `make daily-report` |
| Stop the stack (data kept) | `make local-down` |
| Update to a new version | `git pull && bash scripts/local_up.sh` |
| Alerts to Discord/Slack/ntfy | set `TIA_ALERT_WEBHOOK_URL` in `.env`, `make local-up` |

## 10. Moving to a VPS later

The evidence store is portable: take a backup (§8), stand up the VPS stack
(`docs/DEPLOYMENT.md`), restore the dump into its Postgres, and the track record,
edge evidence and journal continue where they left off. Days in which no session ran
count for nothing — on either machine — because the gate reads persisted trades, not
wall-clock time.
