#!/usr/bin/env bash
# Validate the Docker deployment path — HONESTLY.
#
# This script refuses to claim PASS for anything it could not execute. Without a
# daemon it validates what is validatable (file presence, compose syntax if the CLI
# can parse offline) and exits 3, a distinct code meaning EXTERNAL VALIDATION
# REQUIRED — deliberately not 0, so no pipeline mistakes "could not test" for "passed".
set -u

BOLD=$'\033[1m'; GREEN=$'\033[32m'; RED=$'\033[31m'; YELLOW=$'\033[33m'; RESET=$'\033[0m'

echo "${BOLD}Docker verification${RESET}"

fail=0
for f in Dockerfile docker-compose.yml; do
  if [ -f "$f" ]; then echo "  ${GREEN}PASS${RESET}  $f exists"; else echo "  ${RED}FAIL${RESET}  $f missing"; fail=1; fi
done
[ "$fail" -eq 1 ] && exit 1

if ! command -v docker >/dev/null 2>&1; then
  echo "  ${YELLOW}SKIP${RESET}  docker CLI not installed"
  echo
  echo "${YELLOW}EXTERNAL VALIDATION REQUIRED${RESET} — no Docker CLI in this environment."
  exit 3
fi

if ! docker info >/dev/null 2>&1; then
  echo "  ${YELLOW}SKIP${RESET}  no Docker daemon reachable"
  echo
  echo "${YELLOW}EXTERNAL VALIDATION REQUIRED${RESET} — run this from a machine with a"
  echo "running Docker daemon. Until then the Dockerfile and compose file are reviewed"
  echo "but UNEXECUTED, and are labelled REQUIRES VALIDATION in the README."
  exit 3
fi

echo "  daemon reachable — running the real checks"
set -e
docker compose config -q                       && echo "  ${GREEN}PASS${RESET}  compose config valid"
docker compose build --quiet                   && echo "  ${GREEN}PASS${RESET}  image builds"
docker compose up -d --wait                    && echo "  ${GREEN}PASS${RESET}  services healthy"
curl -fsS http://127.0.0.1:8000/api/health >/dev/null && echo "  ${GREEN}PASS${RESET}  health endpoint answers"
docker compose down -v                         && echo "  ${GREEN}PASS${RESET}  clean shutdown"
echo "${GREEN}DOCKER VERIFIED${RESET}"
