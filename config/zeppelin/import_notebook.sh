#!/bin/bash
# Zeppelin başlayana kadar bekle, sonra notebook'u import et
echo "[NDR] Waiting for Zeppelin to start..."
for i in $(seq 1 60); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/version)
    if [ "$STATUS" = "200" ]; then
        echo "[NDR] Zeppelin is up. Importing NDR notebook..."
        # Mevcut notebook'u kontrol et
        EXISTING=$(curl -s http://localhost:8080/api/notebook | grep -c "NDR_Streaming_KMeans")
        if [ "$EXISTING" -eq "0" ]; then
            RESULT=$(curl -s -X POST \
                -H "Content-Type: application/json" \
                -d @/opt/zeppelin/notebook_import/NDR_Streaming_KMeans.zpln \
                http://localhost:8080/api/notebook/import)
            echo "[NDR] Import result: $RESULT"
        else
            echo "[NDR] NDR notebook already exists, skipping import."
        fi
        exit 0
    fi
    sleep 3
done
echo "[NDR] Zeppelin did not start in time, skipping import."
