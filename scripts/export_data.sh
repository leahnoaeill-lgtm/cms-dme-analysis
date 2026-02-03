#!/bin/bash
# Export database data for migration to AWS
# Usage: ./scripts/export_data.sh

set -e

EXPORT_DIR="./data_export"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
EXPORT_FILE="${EXPORT_DIR}/cms_analysis_${TIMESTAMP}.sql"

echo "Creating export directory..."
mkdir -p ${EXPORT_DIR}

echo "Exporting database..."
pg_dump -U postgres -d cms_analysis \
    --no-owner \
    --no-privileges \
    --clean \
    --if-exists \
    > ${EXPORT_FILE}

echo "Compressing export..."
gzip ${EXPORT_FILE}

echo "Export complete: ${EXPORT_FILE}.gz"
echo "File size: $(ls -lh ${EXPORT_FILE}.gz | awk '{print $5}')"
