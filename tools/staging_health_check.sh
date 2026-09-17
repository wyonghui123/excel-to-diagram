#!/bin/bash
# staging_health_check.sh [V007.49-D + V079-2026-09-02] - staging 健康检查
# 验证 4 个 staging 服务端口 (18081/13011/19101/19200) 正常
#
# [P0-3 2026-09-02] 从 2 个 endpoint 升级到 4 个, 覆盖全部 staging 服务
# 配合 staging_watchdog.sh 实现应用层守护

echo "=== staging Health Check (4 services) ==="

# Service registry: name | port | description
services=(
    "unified_18081:18081:Frontend SPA + API proxy"
    "meta_backend:13011:arch-data-manage-api"
    "log_service:19101:log/alerts/deploy"
    "core_service:19200:exec/upload/audit"
)

all_ok=1
for entry in "${services[@]}"; do
    IFS=':' read -r name port desc <<< "$entry"
    # Try multiple probe paths: / first, then /api/v1/auth/dev-login (200/401 = UP)
    http_code="000"
    for path in "/" "/api/v1/auth/dev-login?username=admin" "/api/services/status"; do
        code=$(curl -o /dev/null -s -w "%{http_code}" --max-time 3 \
            "http://localhost:${port}${path}" 2>/dev/null || echo "000")
        # 200/401/404 都算 UP (200=OK, 401=需要登录=正常, 404=路由不存在但服务在)
        if [ "$code" = "200" ] || [ "$code" = "401" ] || [ "$code" = "404" ]; then
            http_code=$code
            break
        fi
        # 否则继续试下一个 path
    done

    # Get PID by exact port match
    pid=$(ss -tlnp 2>/dev/null | awk -v p=":${port}" '$4 ~ p {print $0}' | grep -oP 'pid=\K[0-9]+' | head -1)

    if [ "$pid" != "" ] && [ "$http_code" != "000" ]; then
        printf "  [OK]   %-16s port=%-6s pid=%-8s http=%s  %s\n" "$name" "$port" "$pid" "$http_code" "$desc"
    else
        printf "  [DOWN] %-16s port=%-6s pid=%-8s http=%s  %s\n" "$name" "$port" "${pid:--}" "$http_code" "$desc"
        all_ok=0
    fi
done

echo ""
echo "=== staging processes ==="
ps -ef | grep -E "19101|19200|13011|18081" | grep -v grep | head -10

echo ""
echo "=== watchdog status ==="
if [ -f /var/run/staging_watchdog/watchdog.pid ]; then
    watchdog_pid=$(cat /var/run/staging_watchdog/watchdog.pid)
    if kill -0 "$watchdog_pid" 2>/dev/null; then
        echo "  watchdog daemon: RUNNING (pid=$watchdog_pid)"
    else
        echo "  watchdog daemon: STALE (pid=$watchdog_pid not alive)"
        all_ok=0
    fi
else
    echo "  watchdog daemon: NOT RUNNING"
    all_ok=0
fi

echo ""
if [ $all_ok -eq 1 ]; then
    echo "=== STATUS: OK ==="
    exit 0
else
    echo "=== STATUS: FAIL (some service(s) down or watchdog not running) ==="
    exit 1
fi
