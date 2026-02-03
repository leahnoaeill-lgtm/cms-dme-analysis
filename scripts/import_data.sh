#!/bin/bash
# Import database data on AWS
# Usage: ./scripts/import_data.sh <export_file.sql.gz>

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <export_file.sql.gz>"
    exit 1
fi

IMPORT_FILE=$1

# Check if running in Docker or standalone
if [ -n "$DB_HOST" ]; then
    # Docker environment
    PGHOST=${DB_HOST}
    PGPORT=${DB_PORT:-5432}
    PGUSER=${DB_USER:-postgres}
    PGPASSWORD=${DB_PASSWORD}
    PGDATABASE=${DB_NAME:-cms_analysis}
else
    # Local environment
    PGHOST=localhost
    PGPORT=5432
    PGUSER=postgres
    PGDATABASE=cms_analysis
fi

echo "Importing data from ${IMPORT_FILE}..."
echo "Target: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"

if [[ ${IMPORT_FILE} == *.gz ]]; then
    echo "Decompressing and importing..."
    gunzip -c ${IMPORT_FILE} | PGPASSWORD=${PGPASSWORD} psql -h ${PGHOST} -p ${PGPORT} -U ${PGUSER} -d ${PGDATABASE}
else
    echo "Importing..."
    PGPASSWORD=${PGPASSWORD} psql -h ${PGHOST} -p ${PGPORT} -U ${PGUSER} -d ${PGDATABASE} < ${IMPORT_FILE}
fi

echo "Import complete!"
