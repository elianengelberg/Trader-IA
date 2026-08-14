# Deployment — running Trader-IA 24/7 without your PC

This document takes the platform from a git clone to a hardened, self-restarting
deployment on a small server. Follow it in order; every section states what it proves
and what it merely prepares.

**Honesty header, before anything else.** The Docker files, the compose stack, the CI
workflow and every command in this document were authored in an environment with **no
Docker daemon and no route to Binance**, so none of them has been executed end-to-end
here. They are labelled REQUIRES VALIDATION until `make production-readiness` (§14) has
run green **on your machine**. The application code behind them — the runtime, the
watchdogs, the restart semantics — *is* covered by the test suite (see
`SYSTEM_STATUS.md`).

---

## 1. What you are deploying

Five containers, one published:

```
                    internet
                       │
                 ┌─────▼─────┐
                 │   proxy   │  Caddy, ports 80/443 — the ONLY published service
                 └─────┬─────┘  automatic HTTPS
                       │ internal network
                 ┌─────▼─────┐
                 │  backend  │  FastAPI + the trading runtime, one process
                 └──┬─────┬──┘  applies migrations, then serves
                    │     │
          ┌─────────▼─┐ ┌─▼────────┐
          │ postgres  │ │  backup  │  daily pg_dump to its own volume
          └───────────┘ └──────────┘
```

* Everything restarts `unless-stopped`. Restart *safety* is the application's job:
  a restarted paper session is a **new run over the same evidence store** — closed
  trades, the edge estimator and the track record reload from the database, and the
  runtime reconciles before it trades. Nothing re-places an order it cannot account for.
* Redis appears in the demo compose file's `full` profile but is **not part of the
  production stack**: the event bus is in-process by design (one runtime process), and a
  container that ships unused is attack surface with a version number.
* The demo `docker-compose.yml` is untouched by any of this; production lives in
  `docker-compose.prod.yml`.

## 2. Choosing infrastructure

This is an MVP that polls 1-minute bars — **not HFT**. Latency to the venue is charged
as a cost by the cost model, but tens of milliseconds are irrelevant at this timeframe.
What matters: a machine that stays up, a disk that persists, a bill you don't notice.

| Option | Fit | Notes |
|---|---|---|
| **Hetzner Cloud (CX-line)** | **Recommended** | Small instances (2 vCPU / 4 GB class) have historically been in the €5–10/month range; excellent price/performance. EU/US regions. |
| DigitalOcean droplet | Good | Same shape, typically a few dollars more; nicer UI, good docs. |
| AWS Lightsail / EC2 | Works | Lightsail is the sane entry point; raw EC2 + EBS + egress pricing is overkill and easy to misestimate. |
| Fly.io / Railway / Render | Possible | PaaS comfort, but persistent volumes, always-on containers and outbound-connection pricing need checking; the compose file maps least directly onto them. |
| Your own hardware | Fine | A Raspberry-class box in a closet meets the load; you own uptime and backups. |

**Recommendation: a small Hetzner or DigitalOcean VPS, 2 vCPU / 4 GB / 40 GB.** The
whole stack idles well under 2 GB. Prices above are indicative from training data —
**verify current pricing before committing**; this repository cannot browse.

One thing no provider gives you: a reason to deploy to more than one machine. One
operator, one process, one database — resist the urge.

## 3. Prerequisites

* A VPS (§2) running a current Debian or Ubuntu LTS, reachable over SSH.
* Docker Engine + the compose plugin ([docs.docker.com/engine/install](https://docs.docker.com/engine/install/)).
* Optional but recommended: a domain (any registrar, ~$10/year) with an A record
  pointing at the VPS — this is what turns self-signed HTTPS into real HTTPS (§8).
* No Binance account is needed for anything in this document. The 24/7 **paper** session
  uses public market data only.

## 4. Server preparation

As root, once:

```bash
apt-get update && apt-get upgrade -y
adduser tia && usermod -aG docker,sudo tia      # never run the stack as root
rkhunter --version >/dev/null 2>&1 || true       # your hardening taste here
# SSH: keys only
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh
# unattended security updates
apt-get install -y unattended-upgrades && dpkg-reconfigure -plow unattended-upgrades
```

Log in as `tia` from here on.

## 5. Getting the code and configuring secrets

```bash
git clone https://github.com/elianengelberg/Trader-IA.git && cd Trader-IA
cp .env.production.example .env
chmod 600 .env
$EDITOR .env
```

Rules for `.env`, which is the **only** place secrets live:

* Generate, don't invent: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
  for `TIA_JWT_SECRET`; 32+ characters for `POSTGRES_PASSWORD` and the dashboard password.
* Nothing sensitive goes in the compose file, the repository, a shell argument (history!)
  or a chat window. The compose file refuses to start if the required three are missing.
* Venue credentials stay **empty** for paper. When the day comes (§15): create the key
  with withdrawals disabled and an IP restriction to this server, export it into `.env`,
  and know that a key alone arms nothing — the activation gate still stands.
* If you prefer a real secret manager (Vault, SOPS, your provider's), inject the same
  variables into the environment and delete `.env`; nothing in the stack reads the file
  itself, only the variables.

## 6. First deployment

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps          # all healthy?
docker compose -f docker-compose.prod.yml logs backend | tail -20
curl -k https://localhost/api/health                  # -k while on self-signed TLS
```

The backend runs `alembic upgrade head` before serving — a schema mismatch is a visible
startup failure, not a 3 a.m. surprise. First boot prints the generated dashboard
credentials **only** if you left `TIA_DEMO_USER`/`TIA_DEMO_PASSWORD` unset, which the
prod compose file does not allow — so login is whatever you set in `.env`.

## 7. Firewall

The compose file publishes only 80/443; Postgres and the backend have **no host ports at
all** — there is nothing to expose by accident. Add the host firewall anyway (defence in
depth, and it covers whatever you run next on this box):

```bash
sudo apt-get install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh          # do this FIRST or the next line locks you out
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

Never `ufw allow 5432` or 6379. If you ever need to inspect the database, tunnel:
`ssh -L 5432:localhost:5432 tia@vps` and then
`docker compose -f docker-compose.prod.yml exec postgres psql -U tia`.

## 8. HTTPS

* **With a domain**: set `TIA_DOMAIN=trader.example.com` in `.env`, point the DNS A
  record at the VPS, `docker compose -f docker-compose.prod.yml up -d`. Caddy obtains
  and renews Let's Encrypt certificates on its own; there is no step two.
* **Without a domain**: `TIA_DOMAIN=localhost` serves Caddy's local-CA certificate.
  Encrypted, but browsers warn and `curl` needs `-k`. Fine for a smoke test; get the
  domain — HSTS, cookies marked Secure, and your own trust in the padlock all work
  better with one.

## 9. The 24/7 paper session

Log in to the dashboard (or use `curl` with the session cookie) and start it:

```
POST /api/live/paper-start
```

What is now running, and what guards it:

| Concern | Mechanism |
|---|---|
| "HTTP answers" ≠ "engine alive" | the loop advances `last_heartbeat` each cycle; `/api/health` reports `trading_engine: degraded` when it stalls >120 s, even while HTTP still returns 200 |
| Stale market data | no new bar for 300 s → the market-data watchdog **halts new entries**; recovery is earned through a clean reconciliation, never assumed |
| Feed outages | transient provider failures halt entries; ten consecutive escalate to SAFE_MODE — sticky until an operator acts |
| Claude outage | the advisory layer degrades to no effect; the deterministic pipeline continues (its modifier could only ever be ≤ 0) |
| Restart / redeploy / reboot | an interrupted session **resumes on boot** as a new run over the same evidence store; an operator **stop** (`POST /api/live/stop`) or an engaged **kill switch** stays down across restarts — sticky means sticky |
| Duplicate orders on restart | recovery reloads persisted evidence and reconciles before trading; order idempotency is by client order id |

Verify the restart story on day one: `docker compose -f docker-compose.prod.yml restart
backend`, wait 30 s, `GET /api/live` — the session should be back by itself. Then
`sudo reboot` and check again (§14).

This paper session is also the clock on the **paper track record** the activation gate
requires (minimum days *and* trades). It only accrues while the session runs — which is
the point of putting it on a VPS instead of your PC.

## 10. Backups and restore

The `backup` container writes a nightly `pg_dump` to the `tia-backups` volume and keeps
the newest `BACKUP_KEEP` (default 14). On demand: `make backup`.

Copy them **off the machine** — a backup on the disk it protects is a wish:

```bash
# from your laptop, e.g. in a weekly cron
rsync -az tia@vps:/var/lib/docker/volumes/trader-ia_tia-backups/_data/ ./tia-backups/
```

Restore drill (do this once *before* you need it):

```bash
docker compose -f docker-compose.prod.yml stop backend
gunzip -c tia-YYYYMMDD-HHMMSS.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T postgres psql -U tia -d tia
docker compose -f docker-compose.prod.yml start backend
```

## 11. Monitoring, alerts, and the daily report

* `/api/health` — unauthenticated, per-component; this is what uptime monitors should
  poll. Point any free external monitor (e.g. an uptime-checker pinging
  `https://your-domain/api/health`) at it so you learn about downtime from your phone,
  not from the equity curve.
* `/api/metrics` — Prometheus format, authenticated.
* **Alerts**: set `TIA_ALERT_WEBHOOK_URL` in `.env` to any JSON-POST endpoint — a
  Discord/Slack webhook works as-is. Safe-mode entries, kill switches, capital halts,
  watchdog trips and failed session resumes are pushed the moment they persist. Email /
  Telegram / anything else is one adapter away: they are all consumers of the same
  webhook seam.
* **Daily report**: `make daily-report` prints yesterday's decisions, orders, fills,
  closed round trips, incidents and error counts from the journal. Cron it into the
  webhook if you want it delivered:

```cron
5 0 * * * cd /home/tia/Trader-IA && make daily-report 2>&1 | tail -30
```

## 12. Updating, CI, and rollback

CI (`.github/workflows/ci.yml`) runs lint, the full Python suite and the frontend build
on every push. Deploys are deliberately **not** CI's job — a trading system should not
redeploy itself because a branch moved. On the VPS:

```bash
git pull && bash scripts/deploy.sh
```

`deploy.sh` is the rollback story: it backs up the database **before** touching
anything, tags the running image as `trader-ia:previous`, builds, swaps with
`up -d --wait`, verifies health through the proxy, and — if the new version fails to
come up healthy — retags the previous image and brings it back.

## 13. Emergency procedures

All of these are authenticated, operator-role-only, and audited with the actor's name.
None of them is reachable by the model layer — there is no code path from an LLM to any
of these endpoints.

| Situation | Action |
|---|---|
| Stop new entries, keep managing exits | `POST /api/live/kill-switch` (goes to SAFE_MODE, cancels resting orders) |
| Close everything now | `POST /api/live/flatten` — cancel, close, verify, record |
| Stop the session | `POST /api/live/stop` — stamped; stays stopped across restarts |
| Kill the machine's role entirely | `docker compose -f docker-compose.prod.yml down` — nothing trades from this box until you bring it back |

The kill switch is independent of Claude, of the strategy layer, and of the venue being
responsive (it cancels what it can and lands in SAFE_MODE regardless). Because the
dashboard is HTTPS on a public domain, **your phone is a remote kill switch** — log in,
one button, named in the audit trail.

## 14. Proving readiness (do not skip)

On the VPS, once the stack is configured:

```bash
make production-readiness
```

This parses the compose file, builds and starts the stack, checks health **through the
proxy over HTTPS**, verifies Postgres publishes no host port, SIGKILLs the backend and
requires it to come back healthy on its own, and confirms the database answers after.
Exit 0 is the readiness claim; exit 3 means it could not run (no Docker) and readiness
is **unproven** — the script will not pretend otherwise.

Then the one test no script can wrap: `sudo reboot`, wait two minutes, open the
dashboard. The stack (`restart: unless-stopped` + Docker's boot integration) and the
session (§9 resume semantics) should both be back. If they are, you have a deployment;
until then you have files.

## 15. The road from here to live trading

Nothing in this document arms live trading, and nothing on this server will trade real
money by itself. The system stays **DISARMED** until every one of these happens, in
order, by a human:

1. `make binance-public` — from any machine with venue egress: validates endpoint
   shapes, kline layout, filters. Writes the fingerprinted validation record.
2. Testnet keys → `make binance-testnet` — signing, permissions, fees, listenKey, one
   resting order placed/duplicated/cancelled on **testnet**.
3. Real keys (withdrawals disabled, IP-locked) → `make binance-account` — the record is
   bound to that key's fingerprint; validating one key and trading another is refused.
4. The paper track record accrues to the configured minimums (days AND trades) on this
   very server (§9).
5. `make verify` green on the deployed commit; `make readiness` green.
6. `POST /api/live/arm` with the exact confirmation phrase, as an operator, with all
   27 gate checks passing — and the ceiling is `TIA_LIVE__MAX_LIVE_CAPITAL`, which
   fails closed at 0.

Every step leaves an audit row. None can be performed by this repository's author, by
CI, or by the model — which is exactly the design.
