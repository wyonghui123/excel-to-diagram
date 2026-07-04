#!/bin/bash
# ============================================================
# precheck.sh - 部署前健康检查 (防止 80% 部署失败)
# ============================================================
# 用法:
#   precheck.sh --version <v> --port <p> [--zip <z>]
#
# 检查项 (7 项):
#   1. Python 解释器可用
#   2. 磁盘空间 (>= 500MB)
#   3. systemd 可用性
#   4. 目标端口未被占用
#   5. zip 文件存在且可读
#   6. db 源可用
#   7. 远端时间/网络
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

# 不开 set -u (函数参数可选, set -u 太严)
set +u

show_help() {
    cat <<'EOF'
precheck.sh - 部署前健康检查

用法:
  bash precheck.sh --version VERSION --port PORT [--zip ZIP]

必填:
  --version VERSION   目标版本
  --port PORT         目标 backend 端口

可选:
  --zip ZIP           zip 路径 (验证存在)
  --db-source PATH    db 源路径 (验证可读)

示例:
  bash precheck.sh --version v20260703_002 --port 5001 --zip /opt/app/deploy-v20260703_002.zip

EOF
}

parse_args "$@"
VERSION="${ARG_VERSION:?--version 必填}"
BACKEND_PORT="${ARG_PORT:?--port 必填}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"
ZIP_PATH="${ARG_ZIP:-}"
DB_SOURCE="${ARG_DB_SOURCE:-}"

detect_remote_env

# zip 路径优先级: --zip > $SCRIPT_DIR/deploy-{VERSION}.zip (同目录) > $DEPLOY_ROOT/deploy-{VERSION}.zip
if [ -z "$ZIP_PATH" ]; then
    if [ -f "$SCRIPT_DIR/deploy-${VERSION}.zip" ]; then
        ZIP_PATH="$SCRIPT_DIR/deploy-${VERSION}.zip"
    elif [ -f "$DEPLOY_ROOT/deploy-${VERSION}.zip" ]; then
        ZIP_PATH="$DEPLOY_ROOT/deploy-${VERSION}.zip"
    else
        # 默认 fallback (远端标准位置)
        ZIP_PATH="$DEPLOY_ROOT/deploy-${VERSION}.zip"
    fi
fi

WARN_COUNT=0
CHECK_PASSED=0
CHECK_FAILED=0
CHECK_WARNED=0

run_check() {
    local name="$1"
    local result="$2"  # "pass" / "fail" / "warn"
    local detail="$3"
    if [ "$result" = "pass" ]; then
        ok "$name"
        [ -n "$detail" ] && info "  $detail"
        CHECK_PASSED=$((CHECK_PASSED+1))
    elif [ "$result" = "fail" ]; then
        err "$name"
        [ -n "$detail" ] && info "  $detail"
        CHECK_FAILED=$((CHECK_FAILED+1))
    else
        warn "$name"
        [ -n "$detail" ] && info "  $detail"
        CHECK_WARNED=$((CHECK_WARNED+1))
    fi
}

banner "PRECHECK - 部署前 7 项健康检查"

# ============================================================
# Check 1: Python 解释器
# ============================================================
hr; echo "[Check 1/7] Python 解释器"
if [ -x "$PY" ]; then
    PVER=$($PY --version 2>&1 | awk '{print $2}')
    run_check "Python 可用: $PY (v$PVER)" pass
else
    run_check "Python 不可用: $PY" fail "需要 /opt/miniconda3-py39/bin/python 或 --py 指定"
fi

# ============================================================
# Check 2: 磁盘空间
# ============================================================
hr; echo "[Check 2/7] 磁盘空间 ($DEPLOY_ROOT)"
DF_KB=$(df -P "$DEPLOY_ROOT" 2>/dev/null | tail -1 | awk '{print $4}')
DF_MB=$((DF_KB / 1024))
if [ "$DF_MB" -ge 500 ]; then
    run_check "磁盘空间充足: ${DF_MB}MB >= 500MB" pass
else
    run_check "磁盘空间不足: ${DF_MB}MB < 500MB" fail "清理日志或备份"
fi

# ============================================================
# Check 3: systemd 可用性
# ============================================================
hr; echo "[Check 3/7] systemd 可用性"
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-system-running >/dev/null 2>&1; then
        run_check "systemd 可用且在运行" pass
    else
        run_check "systemd 存在但未运行 (容器环境？)" warn "将用 nohup 启 backend"
    fi
else
    run_check "systemctl 不可用" warn "将用 nohup 启 backend"
fi

# ============================================================
# Check 4: 端口占用 (智能判定 - 2026-07-04)
# ============================================================
# 之前: 端口被占 → 直接 FAIL (误报率高, 实际 deploy PHASE 1 会自动停)
# 现在: 端口被占 → 检查 PID 加载的代码路径
#   - PID 加载 /opt/app/current/* 代码 → WARN (deploy 会自动处理)
#   - PID 加载其他路径代码 → FAIL (需要人工干预)
#   - 进程不存在/无法读 → FAIL (回退到严格判定)
hr; echo "[Check 4/7] 端口占用 (智能判定)"

# Helper: 看 PID 加载的代码路径是否在 current 下
pid_loaded_from_current() {
    local pid="$1"
    if [ -z "$pid" ] || [ ! -d "/proc/$pid" ]; then
        return 1
    fi
    # 优先 /proc/PID/maps (Linux), 退化 /proc/PID/exe + cmdline
    if [ -r "/proc/$pid/maps" ]; then
        # grep server.py / unified_server.py / python
        local loaded
        loaded=$(grep -E "(server\.py|unified_server\.py)" "/proc/$pid/maps" 2>/dev/null | awk '{print $NF}' | sort -u | head -3)
        if [ -z "$loaded" ]; then
            # 退化: 看 cwd
            local cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null)
            if [ -n "$cwd" ]; then
                loaded="$cwd"
            fi
        fi
        if [ -z "$loaded" ]; then
            return 1  # 无法判定 → 严格
        fi
        # 检查任一加载路径在 /opt/app/current/ 或 /opt/app/deployments/ 下
        echo "$loaded" | while IFS= read -r p; do
            case "$p" in
                /opt/app/current/*|/opt/app/deployments/*)
                    exit 0 ;;
            esac
        done
        # 上面 while 是子 shell, 用更简单方式:
        if echo "$loaded" | grep -qE "/opt/app/(current|deployments)/"; then
            return 0
        fi
        return 1
    fi
    return 1  # 非 Linux 或不可读
}

if is_port_listening $BACKEND_PORT; then
    PORT_PID=$(ss -tlnp 2>/dev/null | grep ":$BACKEND_PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
    PORT_PROC=$(ps -p "$PORT_PID" -o args= 2>/dev/null | head -c 100 || echo "?")
    if [ "${ARG_AUTO_KILL:-false}" = "true" ]; then
        info "  端口被 PID $PORT_PID 占用: $PORT_PROC, 自动杀..."
        kill -15 $PORT_PID 2>/dev/null
        sleep 2
        kill -0 $PORT_PID 2>/dev/null && kill -9 $PORT_PID 2>/dev/null
        sleep 1
        if is_port_listening $BACKEND_PORT; then
            run_check "backend 端口 $BACKEND_PORT 仍被占用" fail "auto-kill 失败"
        else
            run_check "backend 端口 $BACKEND_PORT 杀后空闲" pass
        fi
    else
        # 智能判定: PID 加载的代码是否在 current 下
        if pid_loaded_from_current "$PORT_PID"; then
            run_check "backend 端口 $BACKEND_PORT 被 PID $PORT_PID 占用 (加载 /opt/app/current/* 代码)" warn "deploy.sh PHASE 1 会自动停旧, 可继续"
            info "  PID $PORT_PID 加载的代码在 /opt/app/current 下, deploy 会处理"
        else
            run_check "backend 端口 $BACKEND_PORT 被 PID $PORT_PID 占用 (代码路径异常)" fail "杀掉旧进程 ($PORT_PROC) 或换端口 (--port), 或加 --auto-kill"
        fi
    fi
else
    run_check "backend 端口 $BACKEND_PORT 空闲" pass
fi

if is_port_listening $FRONTEND_PORT; then
    PORT_PID=$(ss -tlnp 2>/dev/null | grep ":$FRONTEND_PORT " | grep -oP 'pid=\K[0-9]+' | head -1)
    if [ -n "$PORT_PID" ] && pid_loaded_from_current "$PORT_PID"; then
        run_check "frontend 端口 $FRONTEND_PORT 被 PID $PORT_PID 占用 (加载 /opt/app/current/* 代码)" warn "deploy.sh PHASE 1 会自动停旧, 可继续"
    else
        run_check "frontend 端口 $FRONTEND_PORT 被 PID $PORT_PID 占用 (代码路径异常)" warn "可能旧 unified_server, 杀掉旧进程 (PID $PORT_PID) 后重跑"
    fi
else
    run_check "frontend 端口 $FRONTEND_PORT 空闲" pass
fi

# ============================================================
# Check 5: zip 文件
# ============================================================
hr; echo "[Check 5/7] zip 文件"
info "zip 路径: $ZIP_PATH"
if [ -f "$ZIP_PATH" ]; then
    ZIP_SIZE=$(stat -c%s "$ZIP_PATH" 2>/dev/null)
    if [ "$ZIP_SIZE" -gt 1024 ]; then
        run_check "zip 存在: $ZIP_PATH (${ZIP_SIZE} bytes)" pass
    else
        run_check "zip 太小: $ZIP_PATH (${ZIP_SIZE} bytes)" fail "可能损坏"
    fi
else
    run_check "zip 不存在: $ZIP_PATH" fail "请 MobaXterm SFTP 上传"
fi

# ============================================================
# Check 6: db 源
# ============================================================
hr; echo "[Check 6/7] db 源"
if [ -z "$DB_SOURCE" ]; then
    CUR=$(current_version)
    if [ -n "$CUR" ]; then
        info "current 版本: $CUR"
        # 找 entry point
        if [ -d "$DEPLOYMENTS_DIR/$CUR/meta" ]; then
            DB_SOURCE="$DEPLOYMENTS_DIR/$CUR/meta/architecture.db"
        elif [ -d "$DEPLOYMENTS_DIR/$CUR/backend" ]; then
            DB_SOURCE="$DEPLOYMENTS_DIR/$CUR/backend/architecture.db"
        fi
    fi
fi
if [ -n "$DB_SOURCE" ] && [ -f "$DB_SOURCE" ]; then
    DB_SIZE=$(stat -c%s "$DB_SOURCE" 2>/dev/null)
    if [ "$DB_SIZE" -gt 1024 ]; then
        run_check "db 源可用: $DB_SOURCE (${DB_SIZE} bytes)" pass
    else
        run_check "db 源太小: $DB_SOURCE (${DB_SIZE} bytes)" warn "可能空 db, fresh init"
    fi
else
    run_check "db 源不可用: $DB_SOURCE" warn "升级模式需要 db 源, 将用 fresh init"
fi

# ============================================================
# Check 7: 网络 + 时间
# ============================================================
hr; echo "[Check 7/8] 网络 + 时间"
# 网络测 (host)
if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
    run_check "外网可达" pass "可以下载依赖"
else
    run_check "外网不可达" warn "如果是内网环境正常"
fi
# 本机时间
INFO_TIME=$(date -Iseconds 2>/dev/null || date)
run_check "本机时间: $INFO_TIME" pass

# ============================================================
# Check 8: frontend_dist_files (避免 8081 404 灾难)
# ============================================================
hr; echo "[Check 8/8] frontend_dist_files"
FRONTEND_DIR="$DEPLOYMENTS_DIR/frontend_dist_files"
if [ -d "$FRONTEND_DIR" ]; then
    if [ -f "$FRONTEND_DIR/index.html" ]; then
        run_check "frontend_dist_files 已解压: $FRONTEND_DIR" pass
    else
        run_check "frontend_dist_files 缺 index.html: $FRONTEND_DIR" fail "deploy 时会重新解压"
    fi
else
    run_check "frontend_dist_files 缺: $FRONTEND_DIR" fail "deploy 时 PHASE 0.5 会重新解压"
fi

# ============================================================
# SUMMARY
# ============================================================
banner "PRECHECK SUMMARY"
echo -e "  ${GREEN}PASS:${NC}  $CHECK_PASSED"
echo -e "  ${YELLOW}WARN:${NC}  $CHECK_WARNED"
echo -e "  ${RED}FAIL:${NC}  $CHECK_FAILED"
echo ""

if [ $CHECK_FAILED -gt 0 ]; then
    err "有 $CHECK_FAILED 项 FAIL, 建议修复后再部署"
    exit 1
elif [ $CHECK_WARNED -gt 0 ]; then
    warn "有 $CHECK_WARNED 项 WARN, 可继续部署但要留意"
    exit 0
else
    ok "全部 7 项 PASS, 可以部署"
    exit 0
fi
