#!/usr/bin/env bash
set -euo pipefail
###############################################################################
# PostgreSQL Migration — Heroku Postgres -> AWS RDS/Aurora PostgreSQL
# Prereqs: pg_dump, pg_restore, psql; network access to both DBs.
# Usage: fill the connection params below, then: chmod +x && ./migrate-postgres.sh
# Placeholders ({{...}}) are filled by YOU from heroku credentials + terraform output.
###############################################################################

# --- Source (Heroku Postgres) — heroku pg:credentials:url -a <app> ---
SOURCE_DB_HOST="{{SOURCE_DB_HOST}}"
SOURCE_DB_PORT="{{SOURCE_DB_PORT}}"
SOURCE_DB_USER="{{SOURCE_DB_USER}}"
SOURCE_DB_PASSWORD="{{SOURCE_DB_PASSWORD}}"
SOURCE_DB_NAME="{{SOURCE_DB_NAME}}"

# --- Target (AWS RDS/Aurora) — terraform output ---
TARGET_DB_HOST="{{TARGET_DB_HOST}}"
TARGET_DB_PORT="{{TARGET_DB_PORT}}"
TARGET_DB_USER="{{TARGET_DB_USER}}"
TARGET_DB_PASSWORD="{{TARGET_DB_PASSWORD}}"
TARGET_DB_NAME="{{TARGET_DB_NAME}}"

BACKUP_FILE="heroku_postgres_backup_$(date +%Y%m%d_%H%M%S).dump"
LOG_FILE="postgres_migration_$(date +%Y%m%d_%H%M%S).log"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

check_prerequisites() {
  for bin in pg_dump pg_restore psql; do
    command -v "$bin" >/dev/null 2>&1 || { log "ERROR: $bin not found"; exit 1; }
  done
  log "Prerequisites OK"
}
test_conn() {
  PGPASSWORD="$2" psql -h "$1" -p "$3" -U "$4" -d "$5" -c "SELECT 1;" >/dev/null 2>&1 \
    || { log "ERROR: Cannot connect to $6 database"; exit 1; }
  log "$6 connection OK"
}
export_source() {
  log "Exporting source to $BACKUP_FILE..."
  PGPASSWORD="$SOURCE_DB_PASSWORD" pg_dump -h "$SOURCE_DB_HOST" -p "$SOURCE_DB_PORT" \
    -U "$SOURCE_DB_USER" -d "$SOURCE_DB_NAME" -Fc --no-owner --no-acl --verbose \
    -f "$BACKUP_FILE" 2>>"$LOG_FILE"
  log "Export complete: $(du -h "$BACKUP_FILE" | cut -f1)"
}
import_target() {
  log "Importing to target..."
  PGPASSWORD="$TARGET_DB_PASSWORD" pg_restore -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" \
    -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" --no-owner --no-acl --verbose \
    "$BACKUP_FILE" 2>>"$LOG_FILE"
  log "Import complete"
}
verify() {
  local q="SELECT SUM(n_live_tup) FROM pg_stat_user_tables;"
  local s t
  s=$(PGPASSWORD="$SOURCE_DB_PASSWORD" psql -h "$SOURCE_DB_HOST" -p "$SOURCE_DB_PORT" -U "$SOURCE_DB_USER" -d "$SOURCE_DB_NAME" -t -c "$q" | tr -d ' ')
  t=$(PGPASSWORD="$TARGET_DB_PASSWORD" psql -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" -t -c "$q" | tr -d ' ')
  log "Source rows: $s | Target rows: $t"
  [ "$s" == "$t" ] && log "OK row counts match" || log "WARN row count mismatch (may be expected if writes occurred during migration)"
}

main() {
  log "=== PostgreSQL Migration Started ==="
  check_prerequisites
  test_conn "$SOURCE_DB_HOST" "$SOURCE_DB_PASSWORD" "$SOURCE_DB_PORT" "$SOURCE_DB_USER" "$SOURCE_DB_NAME" "Source"
  test_conn "$TARGET_DB_HOST" "$TARGET_DB_PASSWORD" "$TARGET_DB_PORT" "$TARGET_DB_USER" "$TARGET_DB_NAME" "Target"
  export_source
  import_target
  verify
  log "=== PostgreSQL Migration Complete ==="
}
main "$@"
