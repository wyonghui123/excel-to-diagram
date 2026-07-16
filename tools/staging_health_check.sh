#!/bin/bash
# staging_health_check.sh [V007.49-D 2026-07-13] - staging 健康检查
# 验证 2 个 staging 服务端口正常

echo "=== staging Health Check ==="
endpoints=(
    "http://localhost:19101/api"
    "http://localhost:19101/api/db/health"
    "http://localhost:19101/api/db/can_write"
    "http://localhost:19101/api/disk/check?quick=true"
)
all_ok=1
for url in "${endpoints[@]}"; do
    code=$(curl -o /dev/null -s -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || echo "000")
    if [ "$code" = "200" ] || [ "$code" = "401" ]; then
        echo "  ✓ $url -> $code"
    else
        echo "  ✗ $url -> $code"
        all_ok=0
    fi
done
echo "=== staging processes ==="
ps -ef | grep -E "19101|19200" | grep -v grep | head -5
if [ $all_ok -eq 1 ]; then
    echo "=== STATUS: OK ==="
    exit 0
else
    echo "=== STATUS: FAIL ==="
    exit 1
fi