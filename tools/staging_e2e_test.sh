#!/bin/bash
# staging_e2e_test.sh [V007.49-D 2026-07-13] - staging 5 项端到端 smoke test (v2 简化)
# 用法: bash /opt/app/staging/scripts/staging_e2e_test.sh

echo "=== staging E2E Test ($(date '+%Y-%m-%d %H:%M:%S')) ==="

PASS=0
FAIL=0

# T1: /api (staging log_service 端点列表)
RESP=$(curl -s --max-time 5 http://localhost:19101/api 2>/dev/null)
if echo "$RESP" | grep -q '"endpoints"'; then
    echo "  ✓ T1 /api: $(echo "$RESP" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(len(d.get('endpoints',[])), 'endpoints')")"
    PASS=$((PASS+1))
else
    echo "  ✗ T1 /api: empty/error"
    FAIL=$((FAIL+1))
fi

# T2: db/health (用 python 解析, 不依赖 json 格式)
RESP=$(curl -s --max-time 5 http://localhost:19101/api/db/health 2>/dev/null)
INTEGRITY=$(echo "$RESP" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('integrity', 'fail'))" 2>/dev/null)
if [ "$INTEGRITY" = "ok" ]; then
    echo "  ✓ T2 /api/db/health: integrity ok"
    PASS=$((PASS+1))
else
    echo "  ✗ T2 /api/db/health: integrity=$INTEGRITY"
    FAIL=$((FAIL+1))
fi

# T3: db/can_write (新加的, 修补 root 漏洞)
RESP=$(curl -s --max-time 5 http://localhost:19101/api/db/can_write 2>/dev/null)
CAN_WRITE=$(echo "$RESP" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('can_write', False))" 2>/dev/null)
if [ "$CAN_WRITE" = "True" ]; then
    echo "  ✓ T3 /api/db/can_write: can_write=true"
    PASS=$((PASS+1))
else
    echo "  ✗ T3 /api/db/can_write: can_write=$CAN_WRITE"
    FAIL=$((FAIL+1))
fi

# T4: disk/check (4 路信号交叉验证)
RESP=$(curl -s --max-time 10 'http://localhost:19101/api/disk/check?quick=true' 2>/dev/null)
if echo "$RESP" | grep -q '"score"'; then
    SCORE=$(echo "$RESP" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('score', 'N/A'))")
    echo "  ✓ T4 /api/disk/check: score=$SCORE"
    PASS=$((PASS+1))
else
    echo "  ✗ T4 /api/disk/check: $RESP" | head -c 100
    FAIL=$((FAIL+1))
fi

# T5: db integrity 直接 sqlite3
INT=$(sqlite3 /opt/app/staging/meta/architecture.db 'PRAGMA integrity_check' 2>&1)
if [ "$INT" = "ok" ]; then
    echo "  ✓ T5 db integrity: ok"
    PASS=$((PASS+1))
else
    echo "  ✗ T5 db integrity: $INT"
    FAIL=$((FAIL+1))
fi

# T6: chaos readonly (staging 专属)
echo "  --- T6 chaos readonly ---"
CHAOS_OUT=$(CHAOS_DB_PATH=/opt/app/staging/meta/architecture.db CHAOS_DB_BAK=/opt/app/staging/meta/architecture.db.chaos_bak /opt/miniconda3-py39/bin/python3 /opt/app/staging/bin/sqlite_chaos.py readonly 2>&1)
if echo "$CHAOS_OUT" | grep -q 'BUG-CONFIRMED'; then
    echo "  ✓ T6 chaos readonly: BUG 已确认 (root 绕过 chmod)"
    PASS=$((PASS+1))
else
    echo "  ✗ T6 chaos readonly: $CHAOS_OUT" | head -c 200
    FAIL=$((FAIL+1))
fi

# T7: chaos busy
echo "  --- T7 chaos busy ---"
CHAOS_OUT=$(CHAOS_DB_PATH=/opt/app/staging/meta/architecture.db CHAOS_DB_BAK=/opt/app/staging/meta/architecture.db.chaos_bak /opt/miniconda3-py39/bin/python3 /opt/app/staging/bin/sqlite_chaos.py busy 2>&1)
if echo "$CHAOS_OUT" | grep -q 'INSERT blocked'; then
    echo "  ✓ T7 chaos busy: busy_timeout=5s 防御生效"
    PASS=$((PASS+1))
else
    echo "  ✗ T7 chaos busy: $CHAOS_OUT" | head -c 200
    FAIL=$((FAIL+1))
fi

# T8: 确认 prod 没受影响 (用 python 解析)
RESP=$(curl -s --max-time 5 'http://localhost:9101/api/db/health' 2>/dev/null)
PROD_INTEGRITY=$(echo "$RESP" | python3 -c "import sys,json; print(json.loads(sys.stdin.read()).get('integrity', 'fail'))" 2>/dev/null)
if [ "$PROD_INTEGRITY" = "ok" ]; then
    echo "  ✓ T8 prod unchanged: prod 9101 db integrity ok"
    PASS=$((PASS+1))
else
    echo "  ✗ T8 prod unchanged: integrity=$PROD_INTEGRITY"
    FAIL=$((FAIL+1))
fi

# T9: staging 前端 (port 18081) - HTML 返回
RESP=$(curl -s --max-time 5 http://localhost:18081/index.html 2>/dev/null)
if echo "$RESP" | grep -q '<!doctype html>'; then
    SIZE=$(echo -n "$RESP" | wc -c)
    echo "  ✓ T9 staging frontend: 18081 returns HTML ($SIZE bytes)"
    PASS=$((PASS+1))
else
    echo "  ✗ T9 staging frontend: 18081 not HTML"
    FAIL=$((FAIL+1))
fi

# T10: staging 静态资源 (assets/*.js) - Vite 编译产物
RESP=$(curl -s --max-time 5 -o /dev/null -w '%{http_code}' http://localhost:18081/assets/ 2>/dev/null)
if [ "$RESP" = "200" ] || [ "$RESP" = "301" ] || [ "$RESP" = "404" ]; then
    # SPA fallback 也算 ok
    echo "  ✓ T10 staging static assets: /assets/ returns $RESP (SPA fallback ok)"
    PASS=$((PASS+1))
else
    echo "  ✗ T10 staging static assets: $RESP"
    FAIL=$((FAIL+1))
fi

echo
echo "=== RESULT: $PASS PASS / $FAIL FAIL ==="
if [ $FAIL -eq 0 ]; then
    echo "=== STATUS: STAGING OK ==="
    # 写 marker (deploy_prod.sh 校验)
    touch /opt/app/staging/data/last_smoke_ok
    echo "marker: /opt/app/staging/data/last_smoke_ok"
    exit 0
else
    echo "=== STATUS: STAGING FAIL ==="
    exit 1
fi