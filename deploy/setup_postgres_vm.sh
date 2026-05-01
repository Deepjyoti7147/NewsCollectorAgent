#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# deploy/setup_postgres_vm.sh
# Run once on the DB VM (Ubuntu 22.04 / Debian 12) to install PostgreSQL
# and create the newsdb database + user.
# Usage: sudo bash setup_postgres_vm.sh
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DB_NAME="newsdb"
DB_USER="newsuser"
DB_PASS="${POSTGRES_PASSWORD:-changeme_please}"      # override via env
COLLECTOR_VM_IP="${COLLECTOR_VM_IP:-}"               # e.g. 10.0.0.5

echo "==> Installing PostgreSQL 16"
apt-get update -qq
apt-get install -y --no-install-recommends postgresql-16

echo "==> Starting PostgreSQL"
systemctl enable --now postgresql

echo "==> Creating DB user and database"
sudo -u postgres psql <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${DB_USER}') THEN
    CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}';
  END IF;
END
\$\$;

CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};
GRANT ALL PRIVILEGES ON DATABASE ${DB_NAME} TO ${DB_USER};
SQL

echo "==> Configuring pg_hba for collector VM"
HBA_FILE=$(sudo -u postgres psql -t -c "SHOW hba_file;" | tr -d ' ')
PG_CONF=$(sudo -u postgres psql -t -c "SHOW config_file;" | tr -d ' ')

# Allow password-authenticated connections from collector VM
if [ -n "$COLLECTOR_VM_IP" ]; then
    echo "host  ${DB_NAME}  ${DB_USER}  ${COLLECTOR_VM_IP}/32  scram-sha-256" >> "$HBA_FILE"
fi

# Make PostgreSQL listen on all interfaces (use firewall to restrict)
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$PG_CONF"

# Tune for 1 GB RAM DB VM
cat >> "$PG_CONF" <<PGCONF

# Tuned for 1 GB RAM
shared_buffers = 256MB
effective_cache_size = 512MB
maintenance_work_mem = 64MB
work_mem = 4MB
max_connections = 20
checkpoint_completion_target = 0.9
wal_buffers = 16MB
PGCONF

echo "==> Reloading PostgreSQL"
systemctl reload postgresql

echo ""
echo "PostgreSQL setup complete."
echo "  DB:   $DB_NAME"
echo "  User: $DB_USER"
echo "  Remember to open port 5432 in your cloud firewall ONLY from the collector VM IP."
