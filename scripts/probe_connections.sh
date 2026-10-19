#!/usr/bin/env bash
# Checks that every service in .env is reachable and the credentials work.
# Prints only pass/fail plus non-secret facts (plan, limits). Never prints key values.
# Usage: bash scripts/probe_connections.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/logs/probe.log"
PSQL="$(command -v psql || echo /opt/homebrew/opt/libpq/bin/psql)"

# Read one KEY=value from .env without echoing it.
env_get() { grep -E "^$1=" "$ROOT/.env" | head -1 | cut -d= -f2-; }

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

# --- Blitz API ---
BLITZ_KEY="$(env_get Blitz_APIKEY)"
if [ -z "$BLITZ_KEY" ]; then
  log "BLITZ      FAIL  Blitz_APIKEY missing from .env"
else
  body="$(curl -s -m 10 -w '\n%{http_code}' https://api.blitz-api.ai/v2/account/key-info -H "x-api-key: $BLITZ_KEY")"
  code="$(tail -1 <<<"$body")"
  if [ "$code" = "200" ]; then
    facts="$(sed '$d' <<<"$body" | jq -r '"valid=\(.valid) plan=\(.active_plans|map(.name)|join(",")) records_remaining=\(.records_remaining) rps_per_endpoint=\(.max_requests_per_seconds) resets=\(.next_reset_at)"')"
    log "BLITZ      OK    $facts"
  else
    log "BLITZ      FAIL  HTTP $code"
  fi
fi

# --- Supabase project URL (reachability only; no anon key in .env) ---
SB_URL="$(env_get SUPABASE_URL)"
if [ -z "$SB_URL" ]; then
  log "SUPABASE   FAIL  SUPABASE_URL missing from .env"
else
  code="$(curl -s -m 10 -o /dev/null -w '%{http_code}' "$SB_URL/auth/v1/health")"
  case "$code" in
    200|401) log "SUPABASE   OK    project URL reachable (HTTP $code)" ;;
    *)       log "SUPABASE   FAIL  project URL returned HTTP $code" ;;
  esac
fi

# --- Supabase Postgres (direct + pooler) ---
for var in SUPABASE_DB_URL_DIRECT SUPABASE_DB_URL_POOLER; do
  url="$(env_get $var)"
  if [ -z "$url" ]; then
    log "$(printf '%-10s' ${var#SUPABASE_DB_URL_}) FAIL  $var missing from .env"
    continue
  fi
  out="$(PGCONNECT_TIMEOUT=10 "$PSQL" "$url" -tA -c "select current_database() || ' | ' || split_part(version(), ' ', 2)" 2>&1)"
  if [ $? -eq 0 ]; then
    log "$(printf '%-10s' ${var#SUPABASE_DB_URL_}) OK    db=$out"
  else
    # psql errors name host/user but not the password; keep only the last line.
    log "$(printf '%-10s' ${var#SUPABASE_DB_URL_}) FAIL  $(tail -1 <<<"$out")"
  fi
done
