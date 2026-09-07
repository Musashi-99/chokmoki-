#!/bin/sh
set -e

DB_PATH="/data/dbip-city-lite.mmdb"
DB_URL="https://cdn.jsdelivr.net/npm/dbip-city-lite/dbip-city-lite.mmdb.gz"

if [ ! -f "$DB_PATH" ]; then
    echo "Downloading GeoIP database..."
    mkdir -p /data
    wget -qO- "$DB_URL" | gunzip -c > "$DB_PATH"
    echo "Database ready."
fi

exec /app/geoip-server -db "$DB_PATH" "$@"
