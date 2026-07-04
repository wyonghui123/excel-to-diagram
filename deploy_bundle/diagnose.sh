#!/bin/bash
# ============================================================
# diagnose.sh - 一键诊断 (失败时快速定位)
# ============================================================
# 用法:
#   diagnose.sh [--port <p>] [--frontend-port <fp>] [--to <v>]
#
# 输出:
#   1. 部署状态 (current 链接 + 所有版本)
#   2. 端口检查
#   3. 进程检查
#   4. 服务健康
#   5. API 真实功能
#   6. 系统资源
#   7. 最近 log
#   8. 总结 + 建议
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

set +u

show_help() {
    cat <<'EOF'
diagnose.sh - 一键诊断 (失败时快速定位)

用法:
  bash diagnose.sh [--port <backend_port>] [--frontend-port <fp>] [--to <version>]

参数 (可选):
  --port PORT          主要检查的 backend 端口 (默认 5001)
  --frontend-port PORT frontend 端口 (默认 8081)
  --to VERSION         主要检查的版本 (默认: current 链接)

示例:
  bash diagnose.sh
  bash diagnose.sh --port 5001 --frontend-port 8081
  bash diagnose.sh --port 5000 --to v20260630_003

EOF
}

parse_args "$@"
BACKEND_PORT="${ARG_PORT:-5001}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"
VERSION="${ARG_TO:-}"
DEPLOY_ROOT="${ARG_DEPLOY_ROOT:-/opt/app}"
DEPLOYMENTS_DIR="$DEPLOY_ROOT/deployments"
CURRENT_LINK="$DEPLOY_ROOT/current"
LOG_DIR="$DEPLOY_ROOT/shared/logs"

# 如果没指定 VERSION, 用 current
if [ -z "$VERSION" ] && [ -L "$CURRENT_LINK" ]; then
    VERSION=$(basename "$(readlink -f "$CURRENT_LINK" 2>/dev/null)" 2>/dev/null)
fi

# 全局失败计数
DIAG_FAIL=0
DIAG_WARN=0
DIAG_OK=0

# ============================================================
# PHASE 1: 部署状态快照
# ============================================================
banner "[1/7] 部署状态快照"

hr; echo "[1a] current 链接"
if [ -L "$CURRENT_LINK" ]; then
    CUR=$(readlink -f "$CURRENT_LINK" 2>/dev/null)
    CUR_NAME=$(basename "$CUR" 2>/dev/null)
    ok "current → $CUR"
    if [ -n "$VERSION" ] && [ "$CUR_NAME" = "$VERSION" ]; then
        ok "current 与检查的版本一致: $VERSION"
    elif [ -n "$VERSION" ]; then
        warn "current ($CUR_NAME) ≠ 检查的版本 ($VERSION)"
    fi
else
    err "current 链接不存在: $CURRENT_LINK"
    DIAG_FAIL=$((DIAG_FAIL+1))
fi

hr; echo "[1b] 所有部署版本"
if [ -d "$DEPLOYMENTS_DIR" ]; then
    for d in $(ls -d $DEPLOYMENTS_DIR/*/ 2>/dev/null); do
        V=$(basename "$d")
        # 找 entry point
        ENTRY="-"
        for sub in meta backend; do
            if [ -f "$d/$sub/server.py" ]; then
                ENTRY="$sub/server.py"
                break
            fi
        done
        # db 大小
        DB_SIZE="-"
        for sub in meta backend; do
            if [ -f "$d/$sub/architecture.db" ]; then
                DB_SIZE=$(stat -c%s "$d/$sub/architecture.db" 2>/dev/null)
                DB_SIZE="${DB_SIZE}B"
                break
            fi
        done
        if [ "$V" = "$CUR_NAME" ]; then
            ok "  [ACTIVE] $V (entry: $ENTRY, db: $DB_SIZE)"
        else
            info "  $V (entry: $ENTRY, db: $DB_SIZE)"
        fi
    done
else
    err "deployments 目录不存在: $DEPLOYMENTS_DIR"
    DIAG_FAIL=$((DIAG_FAIL+1))
fi

# ============================================================
# PHASE 2: 端口检查
# ============================================================
banner "[2/7] 端口检查"

hr; echo "[2a] 监听端口 (5000, 5001, 5002, 8081, 8082)"
PORTS_FOUND=$(ss -tlnp 2>/dev/null | grep -E ":(5000|5001|5002|5003|8081|8082)\s" | awk '{print $4}' | sed 's/.*://g' | sort -u)
if [ -n "$PORTS_FOUND" ]; then
    for p in $PORTS_FOUND; do
        # 找哪个进程
        PID=$(ss -tlnp 2>/dev/null | grep ":$p " | grep -oP 'pid=\K[0-9]+' | head -1)
        PROC=$(ps -p "$PID" -o comm= 2>/dev/null || echo "?")
        ok "  $p: 监听 (PID $PID: $PROC)"
    done
else
    warn "无相关端口监听"
    DIAG_WARN=$((DIAG_WARN+1))
fi

hr; echo "[2b] 主要检查的 backend 端口 $BACKEND_PORT"
if is_port_listening $BACKEND_PORT; then
    ok "  $BACKEND_PORT: 监听中"
else
    err "  $BACKEND_PORT: 未监听"
    DIAG_FAIL=$((DIAG_FAIL+1))
    info "    可能 backend 没启, 或启错了端口"
fi

hr; echo "[2c] 主要检查的 frontend 端口 $FRONTEND_PORT"
if is_port_listening $FRONTEND_PORT; then
    ok "  $FRONTEND_PORT: 监听中"
else
    err "  $FRONTEND_PORT: 未监听"
    DIAG_FAIL=$((DIAG_FAIL+1))
    info "    可能 unified_server 没启"
fi

# ============================================================
# PHASE 3: 进程检查
# ============================================================
banner "[3/7] 进程检查"

hr; echo "[3a] server.py 进程"
PROCS=$(ps -ef | grep -E "python.*server\.py" | grep -v grep)
if [ -n "$PROCS" ]; then
    echo "$PROCS" | while IFS= read -r line; do
        PID=$(echo "$line" | awk '{print $2}')
        CMD=$(echo "$line" | awk '{$1=$2=$3=$4=$5=$6=$7=""; print $0}' | xargs)
        ok "  PID $PID: $CMD"
    done
else
    warn "  无 server.py 进程"
    DIAG_WARN=$((DIAG_WARN+1))
fi

hr; echo "[3b] unified_server 进程"
PROCS=$(ps -ef | grep -E "unified_server" | grep -v grep)
if [ -n "$PROCS" ]; then
    echo "$PROCS" | while IFS= read -r line; do
        PID=$(echo "$line" | awk '{print $2}')
        CMD=$(echo "$line" | awk '{$1=$2=$3=$4=$5=$6=$7=""; print $0}' | xargs)
        ok "  PID $PID: $CMD"
    done
else
    warn "  无 unified_server 进程"
    DIAG_WARN=$((DIAG_WARN+1))
fi

hr; echo "[3c] systemd excel-backend"
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active excel-backend.service >/dev/null 2>&1; then
        ok "  excel-backend.service: active"
    else
        info "  excel-backend.service: not active"
    fi
else
    warn "  systemctl 不可用"
    DIAG_WARN=$((DIAG_WARN+1))
fi

# ============================================================
# PHASE 4: 服务健康
# ============================================================
banner "[4/7] 服务健康"

hr; echo "[4a] backend $BACKEND_PORT /health"
for i in 1 2 3; do
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$BACKEND_PORT/health" 2>/dev/null || echo "000")
    if [ "$code" = "200" ] || [ "$code" = "410" ]; then
        ok "  backend /health = $code (alive)"
        break
    fi
    sleep 1
done
[ "$code" != "200" ] && [ "$code" != "410" ] && { err "  backend /health = $code (3 attempts)"; DIAG_FAIL=$((DIAG_FAIL+1)); }

hr; echo "[4b] backend $BACKEND_PORT /api/v2/bo/health (BO 端点, 需 auth)"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$BACKEND_PORT/api/v2/bo/health" 2>/dev/null)
case "$code" in
    200) ok "  api/v2/bo/health = 200 (无需 auth)" ;;
    401|403) ok "  api/v2/bo/health = $code (alive, 需 auth - 预期)" ;;
    410) warn "  api/v2/bo/health = 410 (server alive, db 未 init)"; DIAG_WARN=$((DIAG_WARN+1)) ;;
    000) err "  api/v2/bo/health 不可达"; DIAG_FAIL=$((DIAG_FAIL+1)) ;;
    *) warn "  api/v2/bo/health = $code"; DIAG_WARN=$((DIAG_WARN+1)) ;;
esac

hr; echo "[4c] frontend $FRONTEND_PORT /"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "http://127.0.0.1:$FRONTEND_PORT/" 2>/dev/null || echo "000")
[ "$code" = "200" ] && ok "  frontend / = 200" || { err "  frontend / = $code"; DIAG_FAIL=$((DIAG_FAIL+1)); }

# ============================================================
# PHASE 5: API 真实功能
# ============================================================
banner "[5/7] API 真实功能 (通过 unified $FRONTEND_PORT)"

hr; echo "[5a] /api/v1/auth/login"
LOGIN_RESP=$(curl -s --max-time 3 -X POST "http://127.0.0.1:$FRONTEND_PORT/api/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' 2>/dev/null)
if echo "$LOGIN_RESP" | grep -q '"token"'; then
    ok "  login 返回 token"
    TOKEN=$(echo "$LOGIN_RESP" | python -c "import sys, json; print(json.load(sys.stdin).get('data', {}).get('token', ''))" 2>/dev/null)
    [ -n "$TOKEN" ] && info "  token 长度: ${#TOKEN}"
else
    err "  login 失败: $(echo $LOGIN_RESP | head -c 150)"
    DIAG_FAIL=$((DIAG_FAIL+1))
    TOKEN=""
fi

hr; echo "[5b] /api/v1/enum-types"
ENUM_RESP=$(curl -s --max-time 3 "http://127.0.0.1:$FRONTEND_PORT/api/v1/enum-types" 2>/dev/null)
if echo "$ENUM_RESP" | grep -q '"mutability"'; then
    ok "  enum-types 含 mutability"
    MUT_DIST=$(echo "$ENUM_RESP" | python -c "
import sys, json
from collections import Counter
try:
    d = json.load(sys.stdin)
    items = d.get('data', [])
    c = Counter(e.get('mutability', 'N/A') for e in items)
    print(dict(c))
except: pass
" 2>/dev/null)
    info "  mutability 分布: $MUT_DIST"
else
    err "  enum-types 无 mutability"
    DIAG_FAIL=$((DIAG_FAIL+1))
    info "  response: $(echo $ENUM_RESP | head -c 200)"
fi

hr; echo "[5c] /api/v1/users/me (用 token)"
if [ -n "$TOKEN" ]; then
    ME_RESP=$(curl -s --max-time 3 -H "Authorization: Bearer $TOKEN" \
        "http://127.0.0.1:$FRONTEND_PORT/api/v1/users/me" 2>/dev/null)
    if echo "$ME_RESP" | grep -q "401\|Unauthorized"; then
        err "  users/me = 401 (token 无效)"
        DIAG_FAIL=$((DIAG_FAIL+1))
    elif echo "$ME_RESP" | grep -q "admin\|success.*true"; then
        ok "  users/me 用 token 成功"
    else
        warn "  users/me 响应异常: $(echo $ME_RESP | head -c 200)"
        DIAG_WARN=$((DIAG_WARN+1))
    fi
else
    warn "  无 token, 跳过"
    DIAG_WARN=$((DIAG_WARN+1))
fi

# ============================================================
# PHASE 6: 系统资源
# ============================================================
banner "[6/7] 系统资源"

hr; echo "[6a] 磁盘 ($DEPLOY_ROOT)"
DF_OUT=$(df -h "$DEPLOY_ROOT" 2>/dev/null | tail -1)
if [ -n "$DF_OUT" ]; then
    DF_USED=$(echo "$DF_OUT" | awk '{print $3}')
    DF_AVAIL=$(echo "$DF_OUT" | awk '{print $4}')
    DF_PCT=$(echo "$DF_OUT" | awk '{print $5}')
    if [ "${DF_PCT%\%}" -lt 90 ]; then
        ok "  磁盘: used $DF_USED, avail $DF_AVAIL ($DF_PCT)"
    else
        warn "  磁盘: used $DF_USED, avail $DF_AVAIL ($DF_PCT) 空间紧张"
        DIAG_WARN=$((DIAG_WARN+1))
    fi
fi

hr; echo "[6b] 内存"
MEM_OUT=$(free -h 2>/dev/null | grep "Mem:")
if [ -n "$MEM_OUT" ]; then
    MEM_USED=$(echo "$MEM_OUT" | awk '{print $3}')
    MEM_TOTAL=$(echo "$MEM_OUT" | awk '{print $2}')
    info "  内存: used $MEM_USED / total $MEM_TOTAL"
fi

hr; echo "[6c] CPU load"
LOAD_OUT=$(uptime 2>/dev/null)
info "  $LOAD_OUT"

# ============================================================
# PHASE 7: 最近 log
# ============================================================
banner "[7/7] 最近 log"

if [ -d "$LOG_DIR" ]; then
    hr; echo "[7a] backend log (最近 10 行)"
    LATEST_BACKEND=$(ls -t $LOG_DIR/backend-*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_BACKEND" ]; then
        info "  log: $LATEST_BACKEND"
        tail -10 "$LATEST_BACKEND" 2>/dev/null | sed 's/^/    /'
    else
        warn "  无 backend-*.log"
    fi

    hr; echo "[7b] frontend log (最近 10 行)"
    LATEST_FRONTEND=$(ls -t $LOG_DIR/frontend-*.log 2>/dev/null | head -1)
    if [ -n "$LATEST_FRONTEND" ]; then
        info "  log: $LATEST_FRONTEND"
        tail -10 "$LATEST_FRONTEND" 2>/dev/null | sed 's/^/    /'
    else
        warn "  无 frontend-*.log"
    fi
else
    warn "  log 目录不存在: $LOG_DIR"
    DIAG_WARN=$((DIAG_WARN+1))
fi

# ============================================================
# [CHG 2026-07-04] 部署健康检查 (C1-C6)
# 深度诊断场景, 跟现有 DIAGNOSE STEPS 互补: 本节专注"代码身份",
# 现有 STEPS 专注"服务/端口/进程/日志".
# ============================================================
banner "部署健康检查 (C1-C6 - 代码身份)"
LOCAL_ZIP=$(ls -1t /tmp/deploy_bundle/deploy-v*.zip 2>/dev/null | head -1)
if [ -x "$SCRIPT_DIR/lib/check_deploy_health.sh" ]; then
    bash "$SCRIPT_DIR/lib/check_deploy_health.sh" "$LOCAL_ZIP" || true
else
    warn "check_deploy_health.sh 不存在 (跳过 C1-C6)"
fi

# ============================================================
# SUMMARY
# ============================================================
banner "DIAGNOSE SUMMARY"
echo -e "  ${GREEN}OK:    $DIAG_OK${NC}"
echo -e "  ${YELLOW}WARN:  $DIAG_WARN${NC}"
echo -e "  ${RED}FAIL:  $DIAG_FAIL${NC}"
echo ""

if [ $DIAG_FAIL -gt 0 ]; then
    err "有 $DIAG_FAIL 项 FAIL"
    echo ""
    echo -e "${YELLOW}建议操作:${NC}"
    echo "  1. 看 log: tail -f $LOG_DIR/backend-*.log $LOG_DIR/frontend-*.log"
    echo "  2. 重启后端: pkill -9 -f 'python.*server.py'; cd $DEPLOY_ROOT/deployments/$VERSION/meta; nohup $PY server.py > $LOG_DIR/backend.log 2>&1 &"
    echo "  3. 重启 unified: pkill -9 -f unified_server; cd $DEPLOY_ROOT/deployments/$VERSION; nohup $PY $SCRIPT_DIR/unified_server.py frontend_dist_files > $LOG_DIR/frontend.log 2>&1 &"
    echo "  4. 重新诊断: bash $SCRIPT_DIR/diagnose.sh"
    echo "  5. 仍有问题: 重新部署: bash $SCRIPT_DIR/deploy.sh --version $VERSION --port $BACKEND_PORT"
    echo "  6. 仍不行: 回滚: bash $SCRIPT_DIR/rollback.sh --to <previous_version> --port <previous_port>"
    exit 1
else
    if [ $DIAG_WARN -gt 0 ]; then
        warn "有 $DIAG_WARN 项 WARN, 但没 FAIL, 服务可能可用"
    else
        ok "全部正常"
    fi
    exit 0
fi
