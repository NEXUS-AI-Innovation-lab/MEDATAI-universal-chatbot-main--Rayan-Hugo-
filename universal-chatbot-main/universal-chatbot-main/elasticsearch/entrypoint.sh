#!/bin/bash
set -e

# Start Elasticsearch in the background
/usr/local/bin/docker-entrypoint.sh elasticsearch &

# Wait for Elasticsearch to start
echo "[RESTORE] Waiting for Elasticsearch to start..."
until curl -s http://localhost:9200 >/dev/null; do
    sleep 2
done
echo "[RESTORE] Elasticsearch is up."

# Register the snapshot repository (REQUIRED)
echo "[RESTORE] Registering snapshot repository..."
curl -s -X PUT "http://localhost:9200/_snapshot/my_repo" \
  -H "Content-Type: application/json" \
  -d "{
        \"type\": \"fs\",
        \"settings\": { \"location\": \"/usr/share/elasticsearch/backups\" }
      }" > /dev/null

# Check if there are zero indices
INDEX_COUNT=$(curl -s http://localhost:9200/_cat/indices?h=index | wc -l)

if [ "$INDEX_COUNT" -eq 0 ]; then
    echo "[RESTORE] No indices found. Restoring snapshot..."
    curl -s -X POST \
        "http://localhost:9200/_snapshot/my_repo/snap1/_restore?wait_for_completion=true"
    echo "[RESTORE] Snapshot restore finished."
else
    echo "[RESTORE] Indices already present — skipping restore."
fi

# Keep process open
wait
