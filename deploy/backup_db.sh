#!/usr/bin/env bash
#
# Daily off-server backup of the romeralQRAccess PostgreSQL database.
#
# The VPS plan carries no provider-side backups, so this script is the
# only copy of the database that survives the VPS itself being lost.
# It runs from cron (see deploy/crontab.txt): pg_dump to a timestamped
# file in a temp directory, rclone copy that file to a Google Drive
# remote, then always delete the local temp file.
#
# Assumptions, since there is no real VPS or Google Drive remote to
# test this against yet (documented here rather than guessed at
# silently):
#   - App checkout at /srv/romeral/app, backend/.env at
#     /srv/romeral/app/backend/.env with DATABASE_URL set, matching
#     deploy/setup_vps.sh.
#   - rclone is installed and already has a *remote* configured (via
#     `rclone config`, run once by hand) pointing at the Google Drive
#     folder. That remote should use a Google service account
#     (service_account_file = /path/to/sa.json in rclone's config, a
#     file never committed to this repo) rather than an interactive
#     OAuth token, since a cron job has no terminal to re-authenticate
#     from when a token expires. Only the *name* of that remote is an
#     input to this script, via RCLONE_REMOTE_NAME - the remote's own
#     credentials live entirely in rclone's config, outside the repo.
#   - GDRIVE_BACKUP_FOLDER is a path inside that remote (e.g.
#     "romeral-backups"), also provided by environment variable so
#     nothing Drive-specific is hardcoded here.
#   - Both variables are expected to be exported in the environment
#     the cron job runs with (for example via a small /etc/sysconfig
#     file or a wrapper sourced before this script, consistent with
#     how backend/.env is the single source of truth for the database
#     credentials rather than anything this script invents).
#
# Required environment variables:
#   RCLONE_REMOTE_NAME    - name of the pre-configured rclone remote
#                            (e.g. "gdrive-backup").
#   GDRIVE_BACKUP_FOLDER  - destination path inside that remote
#                            (e.g. "romeral-backups").
#
# Optional environment variables:
#   APP_ROOT   - defaults to /srv/romeral/app.
#   ENV_FILE   - defaults to ${APP_ROOT}/backend/.env.
#   LOG_FILE   - defaults to ${APP_ROOT}/backend/logs/backup_db.log.
#
# Usage (as set up by deploy/crontab.txt):
#   RCLONE_REMOTE_NAME=gdrive-backup GDRIVE_BACKUP_FOLDER=romeral-backups \
#       ./deploy/backup_db.sh

set -euo pipefail

APP_ROOT="${APP_ROOT:-/srv/romeral/app}"
BACKEND_DIR="${APP_ROOT}/backend"
ENV_FILE="${ENV_FILE:-${BACKEND_DIR}/.env}"
LOG_FILE="${LOG_FILE:-${BACKEND_DIR}/logs/backup_db.log}"

log() {
    # Timestamped line appended to LOG_FILE so an operator can check
    # success/failure without digging through cron's own mail.
    printf '%s %s\n' "$(date -Iseconds)" "$1" >>"${LOG_FILE}"
}

fail() {
    log "FAILURE: $1"
    exit 1
}

mkdir -p "$(dirname "${LOG_FILE}")"

: "${RCLONE_REMOTE_NAME:?RCLONE_REMOTE_NAME must be set (name of the configured rclone remote)}"
: "${GDRIVE_BACKUP_FOLDER:?GDRIVE_BACKUP_FOLDER must be set (destination path inside that remote)}"

if [[ ! -f "${ENV_FILE}" ]]; then
    fail "Expected ${ENV_FILE} to exist with DATABASE_URL set."
fi

# backend/.env is the single source of truth for the database
# credentials, same as deploy/setup_vps.sh - this script never
# invents or hardcodes a password.
database_url="$(grep -E '^DATABASE_URL=' "${ENV_FILE}" | tail -n1 | cut -d'=' -f2-)"
if [[ -z "${database_url}" ]]; then
    fail "DATABASE_URL not found in ${ENV_FILE}."
fi

# postgres://user:password@host:port/dbname
rest="${database_url#postgres://}"
DB_USER="${rest%%:*}"
rest="${rest#*:}"
DB_PASSWORD="${rest%%@*}"
rest="${rest#*@}"
DB_HOSTPORT="${rest%%/*}"
DB_HOST="${DB_HOSTPORT%%:*}"
DB_PORT="${DB_HOSTPORT##*:}"
DB_NAME="${rest##*/}"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
TMP_DIR="$(mktemp -d)"
DUMP_FILE="${TMP_DIR}/romeral_${TIMESTAMP}.dump"

# Always clean up the local temp file and directory, whether the
# script succeeds, fails partway through, or is interrupted - a dump
# left behind on disk is not itself the backup (the Drive copy is),
# and should never accumulate silently on the VPS.
cleanup() {
    rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

export PGPASSWORD="${DB_PASSWORD}"

if ! pg_dump -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
    -F c -f "${DUMP_FILE}"; then
    unset PGPASSWORD
    fail "pg_dump failed for database '${DB_NAME}'; no backup was uploaded."
fi
unset PGPASSWORD

if [[ ! -s "${DUMP_FILE}" ]]; then
    fail "pg_dump produced an empty dump file; no backup was uploaded."
fi

if ! rclone copy "${DUMP_FILE}" "${RCLONE_REMOTE_NAME}:${GDRIVE_BACKUP_FOLDER}"; then
    fail "rclone copy to '${RCLONE_REMOTE_NAME}:${GDRIVE_BACKUP_FOLDER}' failed; dump was not uploaded."
fi

log "SUCCESS: uploaded $(basename "${DUMP_FILE}") ($(du -h "${DUMP_FILE}" | cut -f1)) to ${RCLONE_REMOTE_NAME}:${GDRIVE_BACKUP_FOLDER}"
