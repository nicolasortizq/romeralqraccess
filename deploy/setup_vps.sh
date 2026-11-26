#!/usr/bin/env bash
#
# One-time (and safely repeatable) setup for the romeralQRAccess VPS.
#
# Target: Hostgator VPS Snappy 2000 - NVMe 4, AlmaLinux 9, no cPanel.
# Domain: acceso.vallederomeral.cl
#
# This script is idempotent: running it again on an already-configured
# server should not error out or duplicate anything. It is NOT a full
# app deployment (code checkout, migrations, collectstatic) - that is a
# separate, more frequent step documented in docs/. This script only
# gets a bare AlmaLinux 9 box to the point where that deploy step can
# run: system packages, the database, the service user, and the Nginx /
# Gunicorn / certbot wiring.
#
# Assumptions, since the VPS is not contracted yet and this cannot be
# run against a real server (documented here rather than guessed at
# silently):
#   - Run as root (or via sudo) on AlmaLinux 9.
#   - The app checkout lives at /srv/romeral/app (backend/ inside it),
#     already cloned with its Python virtualenv built at
#     /srv/romeral/app/backend/.venv and backend/.env in place before
#     this script's "start services" step - this script does not create
#     the venv or clone the repo, only the OS-level pieces around it.
#   - backend/.env already exists with a DATABASE_URL in the form
#     postgres://user:password@localhost:5432/dbname - this script
#     parses it to create the matching PostgreSQL role and database
#     instead of inventing or hardcoding credentials anywhere.
#   - CERTBOT_EMAIL is provided (env var) for Let's Encrypt renewal
#     notices; the DOMAIN is fixed to acceso.vallederomeral.cl.
#
# Usage:
#   CERTBOT_EMAIL=admin@vallederomeral.cl ./deploy/setup_vps.sh

set -euo pipefail

DOMAIN="acceso.vallederomeral.cl"
APP_ROOT="/srv/romeral/app"
BACKEND_DIR="${APP_ROOT}/backend"
ENV_FILE="${BACKEND_DIR}/.env"
SERVICE_USER="romeral"
SERVICE_GROUP="romeral"
NGINX_GROUP="nginx"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

log() {
    printf '==> %s\n' "$1"
}

require_root() {
    if [[ "$(id -u)" -ne 0 ]]; then
        echo "This script must be run as root (use sudo)." >&2
        exit 1
    fi
}

install_packages() {
    log "Installing system packages (dnf is idempotent: already-installed packages are skipped)"

    # Django 6.1 requires PostgreSQL 15 or later. AlmaLinux 9's own
    # AppStream module only ships PostgreSQL 13, so pull a current
    # version from the official PostgreSQL (PGDG) repository instead.
    if ! rpm -q pgdg-redhat-repo >/dev/null 2>&1; then
        dnf install -y https://download.postgresql.org/pub/repos/yum/reporpms/EL-9-x86_64/pgdg-redhat-repo-latest.noarch.rpm
    fi
    # The AppStream "postgresql" module must be disabled, or dnf resolves
    # the PGDG packages against AppStream's older module metadata.
    dnf -qy module disable postgresql || true

    dnf install -y \
        python3.12 \
        python3.12-pip \
        postgresql16-server \
        postgresql16-contrib \
        nginx \
        certbot \
        python3-certbot-nginx \
        firewalld

    # initdb only initializes the data directory once; running it again
    # on an already-initialized cluster is a no-op (and exits non-zero,
    # hence the guard) rather than wiping existing data.
    if [[ ! -f /var/lib/pgsql/16/data/PG_VERSION ]]; then
        log "Initializing PostgreSQL 16 data directory"
        /usr/pgsql-16/bin/postgresql-16-setup initdb
    else
        log "PostgreSQL 16 data directory already initialized, skipping initdb"
    fi
}

create_service_user() {
    if id "${SERVICE_USER}" >/dev/null 2>&1; then
        log "System user '${SERVICE_USER}' already exists, skipping"
    else
        log "Creating system user '${SERVICE_USER}'"
        useradd --system --home-dir "${APP_ROOT}" --shell /sbin/nologin --create-home "${SERVICE_USER}"
    fi

    # Gunicorn's socket is group-owned by "nginx" (see gunicorn.service)
    # so the Nginx worker can reach it without the socket being world
    # writable. usermod -aG is idempotent: adding an existing membership
    # again is a no-op.
    usermod -aG "${NGINX_GROUP}" "${SERVICE_USER}"

    mkdir -p "${BACKEND_DIR}/logs"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_ROOT}" 2>/dev/null || true
}

parse_database_url() {
    # backend/.env is the single source of truth for the database
    # credentials; this script never invents or hardcodes a password.
    if [[ ! -f "${ENV_FILE}" ]]; then
        echo "Expected ${ENV_FILE} to exist with DATABASE_URL already set." >&2
        echo "Deploy the app checkout and backend/.env before running this script." >&2
        exit 1
    fi

    local database_url
    database_url="$(grep -E '^DATABASE_URL=' "${ENV_FILE}" | tail -n1 | cut -d'=' -f2-)"
    if [[ -z "${database_url}" ]]; then
        echo "DATABASE_URL not found in ${ENV_FILE}." >&2
        exit 1
    fi

    # postgres://user:password@host:port/dbname
    local rest="${database_url#postgres://}"
    DB_USER="${rest%%:*}"
    rest="${rest#*:}"
    DB_PASSWORD="${rest%%@*}"
    rest="${rest#*@}"
    DB_NAME="${rest##*/}"
}

setup_database() {
    log "Ensuring PostgreSQL 16 is running"
    systemctl enable --now postgresql-16
    local psql=(/usr/pgsql-16/bin/psql)

    parse_database_url

    log "Ensuring PostgreSQL role '${DB_USER}' exists"
    if ! sudo -u postgres "${psql[@]}" -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'" | grep -q 1; then
        sudo -u postgres "${psql[@]}" -c "CREATE ROLE \"${DB_USER}\" WITH LOGIN PASSWORD '${DB_PASSWORD}';"
    else
        # Role exists: keep its password in sync with backend/.env in
        # case it was rotated there, so re-running this script after a
        # credential rotation stays correct instead of silently stale.
        sudo -u postgres "${psql[@]}" -c "ALTER ROLE \"${DB_USER}\" WITH LOGIN PASSWORD '${DB_PASSWORD}';"
    fi

    log "Ensuring database '${DB_NAME}' exists"
    if ! sudo -u postgres "${psql[@]}" -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'" | grep -q 1; then
        sudo -u postgres "${psql[@]}" -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\";"
    else
        log "Database '${DB_NAME}' already exists, skipping"
    fi
}

install_configs() {
    log "Installing Nginx site config"
    install -m 0644 "${DEPLOY_DIR}/nginx.conf" "/etc/nginx/conf.d/${DOMAIN}.conf"

    log "Installing Gunicorn systemd unit"
    install -m 0644 "${DEPLOY_DIR}/gunicorn.service" /etc/systemd/system/gunicorn-romeral.service

    systemctl daemon-reload
}

start_services() {
    log "Enabling firewall ports 80/443"

    # Opening the firewall for the first time can lock out the very SSH
    # session running this script, if sshd listens on a non-default port
    # firewalld's default zone doesn't already allow (Hostgator VPS
    # instances are commonly provisioned with sshd on a custom port).
    # Detect and keep every port sshd actually listens on before the
    # first firewall-cmd --reload, instead of discovering the lockout
    # only after the connection drops.
    local ssh_port
    for ssh_port in $(ss -tlnp 2>/dev/null | awk '/sshd/{print $4}' | sed -E 's/.*:([0-9]+)$/\1/' | sort -u); do
        firewall-cmd --permanent --add-port="${ssh_port}/tcp" >/dev/null
    done

    systemctl enable --now firewalld
    firewall-cmd --permanent --add-service=http >/dev/null
    firewall-cmd --permanent --add-service=https >/dev/null
    firewall-cmd --reload >/dev/null

    log "Starting Gunicorn"
    systemctl enable --now gunicorn-romeral
    systemctl restart gunicorn-romeral

    log "Testing and starting Nginx"
    nginx -t
    systemctl enable --now nginx
    systemctl reload nginx
}

request_certificate() {
    if [[ -z "${CERTBOT_EMAIL}" ]]; then
        echo "CERTBOT_EMAIL is not set; skipping certbot. Re-run with" >&2
        echo "CERTBOT_EMAIL=admin@vallederomeral.cl ./deploy/setup_vps.sh to request the certificate." >&2
        return
    fi

    log "Requesting/renewing the Let's Encrypt certificate for ${DOMAIN}"
    # --keep-until-expiring makes this idempotent: if a valid certificate
    # already exists, certbot leaves it alone instead of erroring or
    # re-issuing. --redirect makes certbot add (or confirm) the 80->443
    # redirect in the Nginx config it edits.
    certbot --nginx \
        --non-interactive \
        --agree-tos \
        --redirect \
        --keep-until-expiring \
        -m "${CERTBOT_EMAIL}" \
        -d "${DOMAIN}"
}

main() {
    require_root
    install_packages
    create_service_user
    setup_database
    install_configs
    start_services
    request_certificate
    log "Done. Check: systemctl status gunicorn-romeral nginx"
}

main "$@"
