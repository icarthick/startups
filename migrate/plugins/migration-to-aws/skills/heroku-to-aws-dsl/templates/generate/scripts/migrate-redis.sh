#!/usr/bin/env bash
set -euo pipefail
###############################################################################
# Redis Migration — Heroku Redis -> AWS ElastiCache Redis
# Prereqs: redis-cli (with TLS support); network access to both instances.
# Usage: fill connection params, then: chmod +x && ./migrate-redis.sh
# Placeholders ({{...}}) are filled by YOU from heroku credentials + terraform output.
###############################################################################

# --- Source (Heroku Redis) — heroku redis:credentials -a <app> ---
SOURCE_REDIS_HOST="{{SOURCE_REDIS_HOST}}"
SOURCE_REDIS_PORT="{{SOURCE_REDIS_PORT}}"
SOURCE_REDIS_PASSWORD="{{SOURCE_REDIS_PASSWORD}}"
SOURCE_REDIS_TLS="true"

# --- Target (AWS ElastiCache) — terraform output ---
TARGET_REDIS_HOST="{{TARGET_REDIS_HOST}}"
TARGET_REDIS_PORT="{{TARGET_REDIS_PORT}}"
TARGET_REDIS_PASSWORD="{{TARGET_REDIS_PASSWORD}}"
TARGET_REDIS_TLS="true"

LOG_FILE="redis_migration_$(date +%Y%m%d_%H%M%S).log"
BATCH_SIZE=100
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

source_cli() {
  local tls=""; [ "$SOURCE_REDIS_TLS" == "true" ] && tls="--tls"
  redis-cli -h "$SOURCE_REDIS_HOST" -p "$SOURCE_REDIS_PORT" -a "$SOURCE_REDIS_PASSWORD" $tls "$@"
}
target_cli() {
  local tls=""; [ "$TARGET_REDIS_TLS" == "true" ] && tls="--tls"
  redis-cli -h "$TARGET_REDIS_HOST" -p "$TARGET_REDIS_PORT" -a "$TARGET_REDIS_PASSWORD" $tls "$@"
}

check_prerequisites() {
  command -v redis-cli >/dev/null 2>&1 || { log "ERROR: redis-cli not found"; exit 1; }
  log "Prerequisites OK"
}
test_connections() {
  source_cli PING >/dev/null 2>&1 || { log "ERROR: cannot connect to source Redis"; exit 1; }
  target_cli PING >/dev/null 2>&1 || { log "ERROR: cannot connect to target Redis"; exit 1; }
  log "Connections OK"
}
migrate_keys() {
  local total migrated=0 failed=0
  total=$(source_cli DBSIZE | awk '{print $NF}')
  log "Migrating $total keys..."
  source_cli --scan --pattern '*' | while IFS= read -r key; do
    local ttl dump; ttl=$(source_cli TTL "$key"); [ "$ttl" -lt 0 ] && ttl=0
    dump=$(source_cli DUMP "$key")
    if [ -n "$dump" ]; then
      if target_cli RESTORE "$key" "$((ttl * 1000))" "$dump" REPLACE >/dev/null 2>&1; then
        migrated=$((migrated + 1))
      else
        failed=$((failed + 1)); log "WARN: failed to restore $key"
      fi
    fi
    if [ $(( (migrated + failed) % BATCH_SIZE )) -eq 0 ]; then
      log "Progress: $((migrated + failed))/$total (migrated=$migrated failed=$failed)"
    fi
  done
  log "Migration complete: migrated=$migrated failed=$failed"
}
verify() {
  local s t; s=$(source_cli DBSIZE | awk '{print $NF}'); t=$(target_cli DBSIZE | awk '{print $NF}')
  log "Source keys: $s | Target keys: $t"
  [ "$s" == "$t" ] && log "OK key counts match" || log "WARN key count mismatch (expired keys or failed restores)"
}

main() {
  log "=== Redis Migration Started ==="
  check_prerequisites
  test_connections
  migrate_keys
  verify
  log "=== Redis Migration Complete ==="
}
main "$@"
