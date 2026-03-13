#!/bin/bash
# ──────────────────────────────────────────────────────────────
# PostgreSQL Multi-Database Init Script
# ──────────────────────────────────────────────────────────────
# This script runs ONCE during the first startup of the Postgres
# container. It creates additional databases and users beyond
# the default POSTGRES_DB / POSTGRES_USER.
#
# Used by: Hive Metastore (primary), Apache Superset
# ──────────────────────────────────────────────────────────────
set -e

echo ">>> Creating Superset database and user..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create superset user
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'superset') THEN
            CREATE ROLE superset WITH LOGIN PASSWORD 'superset123';
        END IF;
    END
    \$\$;

    -- Create superset database
    SELECT 'CREATE DATABASE superset OWNER superset'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'superset')\gexec

    -- Grant privileges
    GRANT ALL PRIVILEGES ON DATABASE superset TO superset;
EOSQL

echo ">>> Multi-database initialization complete."
