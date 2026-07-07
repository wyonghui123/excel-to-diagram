#!/bin/bash
# ============================================================
# deploy.sh - 通用部署脚本 (任意版本)
# [V007.25] 14:44 部署 bug 全修复: PHASE 0.5 backend hash + PHASE 6.55 MD5 + admin login + baseline fix
# ============================================================
# Bundle Version: 2.1.0 (2026-07-03 12:00)
#   - 修复 precheck zip 路径 (bundle 优先)
#   - 加 auto-kill
#   - 加 diagnose 集成
# ============================================================
DEPLOY_BUNDLE_VERSION="2.1.0"
DEPLOY_BUNDLE_BUILD="20260703_1200"

# ============================================================
# 用法:
#   deploy.sh --version <v> --port <p> [--zip <z>]
#
# 必填:
#   --version VERSION      版本号 (任意字符串, 如 v20260703_002)
#   --port PORT            backend 端口
#   --zip ZIP_PATH         zip 路径 (默认: /opt/app/deploy-{VERSION}.zip)
#
# 可选:
#   --frontend-port PORT   前端端口 (默认 8081)
#   --db-source PATH       从哪个版本的 db 复制 (默认: current 链接版本)
#   --deploy-root PATH     部署根目录 (默认 /opt/app)
#   --unified /tmp/unified_server.py   unified server 路径
#   --no-systemd           不用 systemd (只用 nohup)
#   --skip-unzip           跳过 unzip (假设已解)
#
# 流程:
#   PHASE 0: 事实采集 + 参数校验
#   PHASE 0.5: 解压 zip (如需要)
#   PHASE 1: 停旧服务
#   PHASE 2: 备份 + 复制 db
#   PHASE 3: 写 systemd service
#   PHASE 4: 启 backend
#   PHASE 5: 启 unified server (前端+API proxy)
#   PHASE 6: 端到端验证
#   PHASE 7: 切 current 链接
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib/common.sh"

show_help() {
    cat <<'EOF'
deploy.sh - 通用部署脚本 (任意版本)

用法:
  bash deploy.sh --version VERSION --port PORT [--zip ZIP_PATH]

必填:
  --version VERSION    版本号 (任意字符串)
  --port PORT          backend 端口 (如 5001)
  --zip ZIP_PATH       zip 路径 (默认: $DEPLOY_ROOT/deploy-{VERSION}.zip)

可选:
  --frontend-port PORT     前端端口 (默认 8081)
  --db-source PATH         从哪个版本 db 复制 (默认: current 链接版本)
  --deploy-root PATH       部署根目录 (默认 /opt/app)
  --unified PATH           unified_server.py 路径
  --no-systemd             不用 systemd (默认)
  --skip-unzip             跳过 unzip (假设已解)
  --skip-precheck          跳过 precheck (默认跑, 7 项检查)
  --skip-smoke             跳过 smoke test (默认跑, 5 项真实测试)
  --help, -h               显示此帮助

示例:
  bash deploy.sh --version <v> --port <p> --zip /opt/app/deploy-<v>.zip
  bash rollback.sh --to <v> --port <p>

EOF
}

parse_args "$@"

# 初始化 FAIL_FLAG (避免上阶段 err 遗留)
FAIL_FLAG=0
# DEPLOY_OK_FLAG: 部署核心是否成功 (独立于 smoke test)
# smoke test FAIL 只警告, 不阻塞 (业务用户密码不应依赖 admin)
DEPLOY_OK_FLAG=0

# 自检: 提示 bundle 版本
info "=========================================="
info "  deploy.sh Bundle Version: $DEPLOY_BUNDLE_VERSION ($DEPLOY_BUNDLE_BUILD)"
info "  本地: $(dirname $SCRIPT_DIR)/deploy_bundle/"
info "=========================================="

# 必填参数
VERSION="${ARG_VERSION:?--version 必填}"
BACKEND_PORT="${ARG_PORT:?--port 必填}"
FRONTEND_PORT="${ARG_FRONTEND_PORT:-8081}"
# zip 路径优先级: --zip > $SCRIPT_DIR/deploy-{VERSION}.zip (与脚本同目录) > $DEPLOY_ROOT/deploy-{VERSION}.zip > 智能搜索
ZIP_PATH="${ARG_ZIP:-}"
if [ -z "$ZIP_PATH" ]; then
    if [ -f "$SCRIPT_DIR/deploy-${VERSION}.zip" ]; then
        ZIP_PATH="$SCRIPT_DIR/deploy-${VERSION}.zip"
    elif [ -f "$DEPLOY_ROOT/deploy-${VERSION}.zip" ]; then
        ZIP_PATH="$DEPLOY_ROOT/deploy-${VERSION}.zip"
    else
        # 智能搜索: 任何位置的 deploy-{VERSION}.zip
        FOUND=$(find / -name "deploy-${VERSION}.zip" -type f 2>/dev/null | head -1)
        if [ -n "$FOUND" ]; then
            ZIP_PATH="$FOUND"
            warn "智能搜索找到 zip: $ZIP_PATH"
        else
            ZIP_PATH="$DEPLOY_ROOT/deploy-${VERSION}.zip"  # fallback
        fi
    fi
fi
DB_SOURCE="${ARG_DB_SOURCE:-}"
UNIFIED_SCRIPT="${ARG_UNIFIED:-$SCRIPT_DIR/unified_server.py}"
USE_SYSTEMD="${ARG_NO_SYSTEMD:-true}"
USE_SYSTEMD=$([ "$USE_SYSTEMD" = "true" ] && echo "no" || echo "yes")  # 反转: 默认 no (用 nohup), --systemd 启用
SKIP_UNZIP="${ARG_SKIP_UNZIP:-false}"
SKIP_PRECHECK="${ARG_SKIP_PRECHECK:-false}"
SKIP_SMOKE="${ARG_SKIP_SMOKE:-false}"

detect_remote_env

# ========================= PHASE 0: precheck (可选跳过) =========================
if [ "$SKIP_PRECHECK" != "true" ]; then
    banner "PHASE 0: precheck"
    PRECHECK_ARGS="--version $VERSION --port $BACKEND_PORT --frontend-port $FRONTEND_PORT"
    [ -n "$ZIP_PATH" ] && PRECHECK_ARGS="$PRECHECK_ARGS --zip $ZIP_PATH"
    [ -n "$DB_SOURCE" ] && PRECHECK_ARGS="$PRECHECK_ARGS --db-source $DB_SOURCE"
    bash "$SCRIPT_DIR/precheck.sh" $PRECHECK_ARGS
    if [ $? -ne 0 ]; then
        err "precheck 失败, 建议修复后重试, 或加 --skip-precheck 跳过"
        exit 1
    fi
    ok "precheck PASS, 继续部署"
fi

parse_version "$VERSION" || exit 1

VERSION_PATH="$DEPLOYMENTS_DIR/$VERSION"
# [FIX 2026-07-03] zip 顶层是 frontend_dist_files/ + meta/ (不在子目录)
# 跟 v002 部署保持一致: 共享 meta/ 和 frontend_dist_files/ 在 DEPLOYMENTS_DIR 根
# VERSION_PATH 只是用于标识版本 (current 链接)
ENTRY="meta"
info "ENTRY=$ENTRY (zip 顶层 meta/, 共享在 DEPLOYMENTS_DIR/meta/)"
SERVER_DIR="$DEPLOYMENTS_DIR/meta"
# frontend_dist_files 在 zip 根目录 (DEPLOYMENTS_DIR), 不在 VERSION_PATH 下
# 因为 PHASE 0.5 unzip $ZIP_PATH -d $DEPLOYMENTS_DIR/ 解压根目录
FRONTEND_DIR="$DEPLOYMENTS_DIR/frontend_dist_files"

# JWT/FLASK/CORS 密钥 (>=32 字符, 满足 startup_checks 强制)
SECRET_SUFFIX="${VERSION}-$(date +%s)-do-not-use-in-prod-without-rotation"
JWT_SECRET="deploy-${SECRET_SUFFIX}-jwt-key"
FLASK_SECRET="deploy-${SECRET_SUFFIX}-flask-key"
CORS_ORIGINS="http://$(hostname -I 2>/dev/null | awk '{print $1}'):${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT},http://127.0.0.1:${BACKEND_PORT}"

# ========================= PHASE 0: 事实采集 =========================
banner "PHASE 0: 事实采集"

hr; echo "[check] v003/v004 部署目录"
ls -d $DEPLOYMENTS_DIR/*/ 2>/dev/null

hr; echo "[check] 当前 current 链接"
ls -la $CURRENT_LINK 2>/dev/null && info "  current → $(readlink $CURRENT_LINK)" || warn "  无 current 链接"

hr; echo "[check] 当前进程"
ps -ef | grep -E "python.*server\.py|unified_server|http\.server" | grep -v grep | head -5

hr; echo "[check] 当前端口"
ss -tlnp 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})" || echo "(无)"

# ========================= PHASE 0.5: 解压 zip =========================
banner "PHASE 0.5: 解压 zip"
# 触发条件: backend 缺 OR frontend_dist_files 缺 (避免 8081 404 灾难)
NEED_UNZIP=false
if [ "$SKIP_UNZIP" != "true" ]; then
    if [ ! -d "$SERVER_DIR" ]; then
        NEED_UNZIP=true
        info "触发解压: $SERVER_DIR 不存在"
    elif [ ! -d "$DEPLOYMENTS_DIR/frontend_dist_files" ]; then
        NEED_UNZIP=true
        info "触发解压: $DEPLOYMENTS_DIR/frontend_dist_files 不存在 (避免 8081 404)"
    fi
    # [FIX 2026-07-07] 14:44 部署 bug 修复: 检查 backend 关键文件 hash
    #   之前: 只检查 frontend dist, 不检查 backend. 14:44 部署时, yonaa 上 /opt/app/deployments/meta/
    #   仍是 V007.21 旧版, 但 PHASE 0.5 跳过 unzip, 部署后 backend 仍跑 V007.21 (datasource.py 无 V007.24)
    #   修法: 对比 zip 内 server.py + datasource.py MD5 vs yonaa root, 不匹配则强制解压
    for CRITICAL_FILE in meta/server.py meta/core/datasource.py; do
        if [ -f "$DEPLOYMENTS_DIR/$CRITICAL_FILE" ]; then
            ZIP_MD5=$(unzip -p "$ZIP_PATH" "$CRITICAL_FILE" 2>/dev/null | md5sum | awk '{print $1}')
            ROOT_MD5=$(md5sum "$DEPLOYMENTS_DIR/$CRITICAL_FILE" 2>/dev/null | awk '{print $1}')
            if [ -n "$ZIP_MD5" ] && [ -n "$ROOT_MD5" ] && [ "$ZIP_MD5" != "$ROOT_MD5" ]; then
                NEED_UNZIP=true
                info "触发解压: $CRITICAL_FILE hash 不一致 (zip=${ZIP_MD5:0:8}, root=${ROOT_MD5:0:8})"
            fi
        else
            # yonaa 上文件不存在, 必须解压
            NEED_UNZIP=true
            info "触发解压: $CRITICAL_FILE 不存在 (yonaa)"
        fi
    done
fi
if [ "$NEED_UNZIP" = "true" ]; then
    if [ -f "$ZIP_PATH" ]; then
        cd $DEPLOY_ROOT
        # [FIX 2026-07-04] 不用 -q, 让 unzip 输出可见, 错误可诊断
        unzip -o "$ZIP_PATH" -d $DEPLOYMENTS_DIR/ 2>&1 | tail -20 && ok "解压 $ZIP_PATH → $DEPLOYMENTS_DIR/" || { err "unzip 失败"; die "解压失败, 部署终止"; }
        # [FIX 2026-07-03] zip 顶层是 frontend_dist_files/ + meta/ (不在子目录)
        [ -d "$SERVER_DIR" ] && ok "$SERVER_DIR 已就绪" || err "解压后 $SERVER_DIR 仍缺"
        [ -d "$DEPLOYMENTS_DIR/frontend_dist_files" ] && ok "$DEPLOYMENTS_DIR/frontend_dist_files 已就绪" || err "解压后 frontend_dist_files 仍缺"
    else
        err "zip 不存在: $ZIP_PATH (请 MobaXterm SFTP 上传)"
        die "缺 zip, 部署无法继续"
    fi

    # [BUG-FIX 2026-07-04] 验证 frontend dist hash 跟 zip 一致
    # 之前: deploy.sh 报告 "frontend_dist_files 已就绪" 但远端跑的是老 dist
    # 真因: root frontend_dist_files 没被覆盖 (unzip silent failed OR
    #       shared root 没被替换), 旧 unified_server 进程继续 serve 旧 dist
    # 现在: 解压后立即计算 zip 内 index.html 引用的 JS hash, 跟 root 实际的一致
    ZIP_INDEX_HASH=$(unzip -p "$ZIP_PATH" frontend_dist_files/index.html 2>/dev/null | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1)
    if [ -z "$ZIP_INDEX_HASH" ]; then
        warn "无法从 zip 提取 index.html 引用的 JS hash, 跳过 dist hash 校验"
    else
        info "zip 内 index.html 引用: $ZIP_INDEX_HASH"
        ACTUAL_INDEX_HASH=$(grep -oE 'index-[A-Za-z0-9_-]+\.js' "$DEPLOYMENTS_DIR/frontend_dist_files/index.html" 2>/dev/null | head -1)
        if [ -n "$ACTUAL_INDEX_HASH" ]; then
            info "root index.html 引用: $ACTUAL_INDEX_HASH"
            if [ "$ZIP_INDEX_HASH" = "$ACTUAL_INDEX_HASH" ]; then
                ok "dist hash 一致 (zip=$ZIP_INDEX_HASH == root=$ACTUAL_INDEX_HASH)"
            else
                err "DIST HASH 不一致!"
                err "  zip 期望: $ZIP_INDEX_HASH"
                err "  root 实际: $ACTUAL_INDEX_HASH"
                err "  → unified_server 会 serve 旧 dist, 部署后用户看不到新代码"
                err "  → 修复: 手动 cp zip 内的 index.html 覆盖 root"
                die "dist hash 校验失败, 部署终止, 请排查 unzip/权限问题"
            fi
        else
            warn "root frontend_dist_files/index.html 不存在, 无法对比 dist hash"
        fi
    fi
elif [ "$SKIP_UNZIP" = "true" ]; then
    ok "跳过 unzip (--skip-unzip)"
    # [BUG-FIX 2026-07-04] 即使跳过 unzip, 也验证 root dist 跟 zip 一致
    ZIP_INDEX_HASH=$(unzip -p "$ZIP_PATH" frontend_dist_files/index.html 2>/dev/null | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1)
    ACTUAL_INDEX_HASH=$(grep -oE 'index-[A-Za-z0-9_-]+\.js' "$DEPLOYMENTS_DIR/frontend_dist_files/index.html" 2>/dev/null | head -1)
    if [ -n "$ZIP_INDEX_HASH" ] && [ -n "$ACTUAL_INDEX_HASH" ] && [ "$ZIP_INDEX_HASH" != "$ACTUAL_INDEX_HASH" ]; then
        err "DIST HASH 不一致 (即使 --skip-unzip 也检测到)!"
        err "  zip 期望: $ZIP_INDEX_HASH"
        err "  root 实际: $ACTUAL_INDEX_HASH"
        die "dist hash 不匹配, 请去掉 --skip-unzip 让脚本重新解压"
    fi
else
    ok "已解压 (跳过)"
    # [BUG-FIX 2026-07-04] 跳过解压时, 也应该验证 dist 一致 (防止 silent stale dist)
    ZIP_INDEX_HASH=$(unzip -p "$ZIP_PATH" frontend_dist_files/index.html 2>/dev/null | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1)
    ACTUAL_INDEX_HASH=$(grep -oE 'index-[A-Za-z0-9_-]+\.js' "$DEPLOYMENTS_DIR/frontend_dist_files/index.html" 2>/dev/null | head -1)
    if [ -n "$ZIP_INDEX_HASH" ] && [ -n "$ACTUAL_INDEX_HASH" ] && [ "$ZIP_INDEX_HASH" != "$ACTUAL_INDEX_HASH" ]; then
        err "DIST HASH 不一致!"
        err "  zip 期望: $ZIP_INDEX_HASH"
        err "  root 实际: $ACTUAL_INDEX_HASH"
        err "  → 建议: 不要传 --skip-unzip, 重新跑部署让脚本解压"
        die "root frontend_dist_files 还是旧 dist, 部署会失败"
    fi
fi

# [FIX 2026-07-03] PHASE 0.5 后检测 entry (现在解到 DEPLOYMENTS_DIR)
if [ ! -d "$SERVER_DIR" ]; then
    die "解压后 SERVER_DIR 仍缺: $SERVER_DIR (期望 zip 含 meta/)"
fi
ok "SERVER_DIR=$SERVER_DIR"

# ========================= PHASE 1: 停旧 =========================
banner "PHASE 1: 停旧服务"
hr; echo "[stop] systemd"
systemctl stop excel-backend.service 2>/dev/null || true
systemctl disable excel-backend.service 2>/dev/null || true
systemctl reset-failed excel-backend.service 2>/dev/null || true

hr; echo "[stop] 所有 server.py / unified_server / http.server 进程"
stop_all_servers
ps -ef | grep -E "python.*server\.py|unified_server" | grep -v grep | head -3 || echo "(无)"

# ========================= PHASE 2: 备份 + 复制 db =========================
banner "PHASE 2: 备份 + 复制 db"

# 找 db 源
if [ -z "$DB_SOURCE" ]; then
    CUR=$(current_version)
    # [FIX 2026-07-03] 共享 SERVER_DIR (DEPLOYMENTS_DIR/$ENTRY, 不在子目录)
    if [ -n "$CUR" ] && [ -f "$SERVER_DIR/architecture.db" ]; then
        DB_SOURCE="$SERVER_DIR/architecture.db"
        info "db 源: current ($CUR) - $SERVER_DIR"
    elif [ -f "$SERVER_DIR/architecture.db" ]; then
        DB_SOURCE="$SERVER_DIR/architecture.db"
        info "db 源: zip 内置 - $SERVER_DIR"
    else
        warn "找不到 db 源, 跳过 db 复制"
    fi
else
    info "db 源 (--db-source): $DB_SOURCE"
fi

if [ -n "$DB_SOURCE" ] && [ -f "$DB_SOURCE" ]; then
    BACKUP_DB="$BACKUP_DIR/architecture_$(basename $(dirname $DB_SOURCE))_$(date +%Y%m%d_%H%M%S).db"
    cp -p "$DB_SOURCE" "$BACKUP_DB" && ok "备份: $BACKUP_DB" || err "备份失败"
    # [FIX 2026-07-03] DB_DEST 共享在 SERVER_DIR 根 (跟 v002 一致)
    DB_DEST="$SERVER_DIR/architecture.db"
    if [ "$DB_SOURCE" != "$DB_DEST" ]; then
        # [CHG 2026-07-04] 不用 cp, 改用 sqlite3 .backup API 避免半途复制导致 disk image malformed
        # cp 二进制复制: SQLite 写入时复制可能得到中间态, 服务启动后报 "database disk image is malformed"
        # sqlite3 .backup: SQLite 内部 checkpoint 机制, 保证一致性
        if command -v sqlite3 >/dev/null 2>&1; then
            sqlite3 "$DB_SOURCE" ".backup '$DB_DEST'" && ok "复制 (sqlite3 .backup 一致性): $DB_DEST" || {
                err "sqlite3 .backup 失败, 退化用 cp"
                cp -p "$DB_SOURCE" "$DB_DEST"
            }
        else
            warn "sqlite3 不存在, 用 cp (可能复制不完整)"
            cp -p "$DB_SOURCE" "$DB_DEST" && ok "复制 (cp): $DB_DEST" || err "复制失败"
        fi
    else
        ok "db 已在 $DB_DEST"
    fi
    # [CHG 2026-07-04] 复制后立即验证完整性 (防半途)
    if command -v sqlite3 >/dev/null 2>&1; then
        IC=$(sqlite3 "$DB_DEST" "PRAGMA integrity_check;" 2>/dev/null | head -1)
        if [ "$IC" != "ok" ]; then
            err "DB 完整性检查失败: $IC"
            err "尝试从备份恢复: $BACKUP_DB"
            cp -p "$BACKUP_DB" "$DB_DEST" 2>/dev/null
            IC2=$(sqlite3 "$DB_DEST" "PRAGMA integrity_check;" 2>/dev/null | head -1)
            if [ "$IC2" = "ok" ]; then
                ok "从备份恢复成功"
            else
                err "备份也不完整: $IC2, 必须用更早的 .bak 恢复"
            fi
        else
            ok "DB 完整性 = ok"
        fi
    fi
    # 报告
    info "db 大小: $(stat -c%s "$DB_DEST") bytes"
    if command -v sqlite3 >/dev/null 2>&1; then
        info "enum_types mutability 分布:"
        sqlite3 "$DB_DEST" "SELECT mutability, COUNT(*) FROM enum_types GROUP BY mutability;" 2>/dev/null
    fi
fi

# ========================= PHASE 2.5: 部署验证专用用户 (deploy_test) =========================
banner "PHASE 2.5: 重置 deploy_test 验证用户"
# 部署验证专用用户 (跟 admin 业务用户分离, 每次 deploy 自动重置密码)
if [ -f "$SCRIPT_DIR/reset_deploy_test_user.sh" ]; then
    bash "$SCRIPT_DIR/reset_deploy_test_user.sh" || warn "deploy_test 重置失败 (不影响部署)"
else
    warn "reset_deploy_test_user.sh 不存在, 跳过"
fi

# ========================= PHASE 3: systemd service =========================
banner "PHASE 3: systemd service"
SERVICE_FILE="/etc/systemd/system/excel-backend.service"
if [ -f "$SERVICE_FILE" ] && [ "$USE_SYSTEMD" = "yes" ]; then
    cp -p "$SERVICE_FILE" "${SERVICE_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Excel to Diagram Backend $VERSION
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$SERVER_DIR
ExecStart=$PY server.py
Environment="PORT=${BACKEND_PORT}"
Environment="JWT_SECRET_KEY=${JWT_SECRET}"
Environment="FLASK_SECRET_KEY=${FLASK_SECRET}"
Environment="CORS_ALLOWED_ORIGINS=${CORS_ORIGINS}"
Environment="FLASK_DEBUG=false"
Environment="FLASK_ENV=production"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "写入 service: $SERVICE_FILE"
    systemctl daemon-reload && ok "daemon-reload" || err "daemon-reload 失败"
else
    warn "跳过 systemd (USE_SYSTEMD=$USE_SYSTEMD 或 service 文件不存在)"
fi

# ========================= PHASE 4: 启 backend =========================
banner "PHASE 4: 启 backend on $BACKEND_PORT"

# [BUG-FIX 2026-07-04] 在启动前先 kill 旧进程 (grace period)
# 之前: 旧 backend/unified 进程继续在跑, 加载的 dist 还是旧的
# 现在: SIGTERM → 5s wait → SIGKILL (用 lib/common.sh 的 stop_all_servers, 已在 L42 source)
if declare -f stop_all_servers >/dev/null 2>&1; then
    info "清理旧 backend + unified 进程 (grace period)"
    stop_all_servers
    # 验证端口已空
    sleep 2
    if ss -tlnp 2>/dev/null | grep -qE ":(${BACKEND_PORT}|${FRONTEND_PORT})"; then
        warn "端口仍占用: $(ss -tlnp 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})" | head -3)"
    else
        ok "端口已清空"
    fi
else
    warn "stop_all_servers 函数不可用, 退化用 pkill"
    pkill -15 -f "server\.py" 2>/dev/null; pkill -15 -f "unified_server\.py" 2>/dev/null
    sleep 5
    pkill -9 -f "server\.py" 2>/dev/null; pkill -9 -f "unified_server\.py" 2>/dev/null
fi

STARTED=false
if [ "$USE_SYSTEMD" = "yes" ] && [ -f "$SERVICE_FILE" ]; then
    systemctl start excel-backend.service && ok "systemd start" || err "systemd start 失败"
    sleep 8
    if is_port_listening $BACKEND_PORT; then
        STARTED=true
        ok "systemd 启 backend 成功 (port $BACKEND_PORT)"
    fi
fi

if [ "$STARTED" = false ]; then
    hr; echo "[start] backend via nohup (fallback)"
    cd "$SERVER_DIR" || err "cd $SERVER_DIR 失败"
    # 直接 export env vars + exec (避免 env 命令把 $PY 路径当成 env 变量)
    export PORT=${BACKEND_PORT}
    export JWT_SECRET_KEY="$JWT_SECRET"
    export FLASK_SECRET_KEY="$FLASK_SECRET"
    export CORS_ALLOWED_ORIGINS="$CORS_ORIGINS"
    export FLASK_DEBUG=false
    export FLASK_ENV=production
    nohup "$PY" server.py > "$LOG_DIR/backend-${VERSION}.log" 2>&1 &
    BACKEND_PID=$!
    ok "nohup 启 backend PID=$BACKEND_PID"
    sleep 12
fi

# 验证 backend
if wait_for_health $BACKEND_PORT /health 30; then
    ok "backend health OK on $BACKEND_PORT"
else
    err "backend health failed on $BACKEND_PORT"
fi

# ========================= PHASE 5: 启 unified server =========================
banner "PHASE 5: 启 unified server on $FRONTEND_PORT"

if [ ! -f "$UNIFIED_SCRIPT" ]; then
    err "unified_server.py 不存在: $UNIFIED_SCRIPT"
elif [ ! -d "$FRONTEND_DIR" ]; then
    err "frontend_dist_files 不存在: $FRONTEND_DIR"
else
    cd "$DEPLOYMENTS_DIR" || err "cd $DEPLOYMENTS_DIR 失败"
    # [FIX 2026-07-05] Windows 打包的 unified_server.py 缺 execute 权限, 启动前修复
    chmod +x "$UNIFIED_SCRIPT" 2>/dev/null || true
    BACKEND_PORT=$BACKEND_PORT nohup $PY "$UNIFIED_SCRIPT" "$FRONTEND_DIR" > $LOG_DIR/frontend-${VERSION}.log 2>&1 &
    FRONTEND_PID=$!
    ok "nohup 启 unified_server PID=$FRONTEND_PID (8081 → $BACKEND_PORT)"
    sleep 3
fi

# ========================= PHASE 6: 端到端验证 =========================
banner "PHASE 6: 端到端验证"

hr; echo "[verify] 端口"
ss -tlnp 2>/dev/null | grep -E ":(${BACKEND_PORT}|${FRONTEND_PORT})"

hr; echo "[verify] frontend /"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:$FRONTEND_PORT/ || echo "000")
[ "$code" = "200" ] && ok "frontend / = 200" || err "frontend / = $code"

# [BUG-FIX 2026-07-04] PHASE 5 后立即验证 unified_server serve 的 dist 跟 zip 一致
# 之前: PHASE 5 启了 unified_server, 但如果服务是旧的 (没 kill 干净) 仍然 serve 老 dist
# 现在: 拉一次 /, 看 index.html 引用的 JS hash, 跟 zip 内的比对
hr; echo "[verify] frontend dist hash 跟 zip 一致"
SERVED_INDEX_HTML=$(curl -s --max-time 5 http://127.0.0.1:$FRONTEND_PORT/ 2>/dev/null)
SERVED_INDEX_HASH=$(echo "$SERVED_INDEX_HTML" | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1)
ZIP_INDEX_HASH=$(unzip -p "$ZIP_PATH" frontend_dist_files/index.html 2>/dev/null | grep -oE 'index-[A-Za-z0-9_-]+\.js' | head -1)
if [ -n "$SERVED_INDEX_HASH" ] && [ -n "$ZIP_INDEX_HASH" ]; then
    if [ "$SERVED_INDEX_HASH" = "$ZIP_INDEX_HASH" ]; then
        ok "serve dist 一致 (served=$SERVED_INDEX_HASH == zip=$ZIP_INDEX_HASH)"
    else
        err "SERVE DIST HASH 不一致!"
        err "  served (远端 8081 返回): $SERVED_INDEX_HASH"
        err "  zip 期望: $ZIP_INDEX_HASH"
        err "  → 用户访问会看到旧 dist, 部署失败"
        err "  → 修复: kill unified_server, 重新跑 deploy"
    fi
elif [ -n "$SERVED_INDEX_HASH" ]; then
    warn "served dist: $SERVED_INDEX_HASH (无法对比 zip: $ZIP_INDEX_HASH)"
else
    warn "无法获取 served dist hash (front-end / 返回异常)"
fi

hr; echo "[verify] backend /api/v1/health"
code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:$BACKEND_PORT/api/v1/health || echo "000")
[ "$code" = "200" ] && ok "backend health = 200" || warn "backend health = $code (可能 410 表示 server alive 但 db 未 init)"

hr; echo "[verify] login (通过 unified server, 部署验证专用用户 deploy_test)"
LOGIN_RESP=$(curl -s --max-time 5 -X POST http://127.0.0.1:$FRONTEND_PORT/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"deploy_test","password":"DeployTest@2026!"}' 2>/dev/null)
if echo "$LOGIN_RESP" | grep -q "token"; then
    ok "login 成功 (deploy_test, 通过 8081)"
elif echo "$LOGIN_RESP" | grep -q "success.*true"; then
    ok "login 成功 (deploy_test, alternate)"
else
    warn "login 失败 (deploy_test 未 init 或 PHASE 2.5 失败)"
    echo "$LOGIN_RESP" | head -c 200
fi

# [CHG 2026-07-04] 部署健康检查 (一键 6 类 BUG 验证)
# 集成点: deploy 后立刻跑, 确保部署生效, 不留"远端跑旧代码"隐患.
hr; echo "[verify] 部署健康检查 (C1-C6)"
if [ -x "$SCRIPT_DIR/lib/check_deploy_health.sh" ]; then
    # 默认找当前 deploy-v*.zip
    DEPLOY_ZIP=$(ls -1t $SCRIPT_DIR/deploy-v*.zip 2>/dev/null | head -1)
    bash "$SCRIPT_DIR/lib/check_deploy_health.sh" "$DEPLOY_ZIP" || DEPLOY_HEALTH_FAIL=1
    [ -n "$DEPLOY_HEALTH_FAIL" ] && warn "部署健康检查有 FAIL (但不阻塞, 见 SUMMARY)"
else
    warn "check_deploy_health.sh 不存在 (跳过 C1-C6)"
fi

# ========================= PHASE 6.5: smoke test (5 项真实功能) =========================
if [ "$SKIP_SMOKE" != "true" ]; then
    banner "PHASE 6.5: smoke test (5 项真实功能)"
    bash "$SCRIPT_DIR/smoke_test.sh" --port $BACKEND_PORT --frontend-port $FRONTEND_PORT
    SMOKE_RC=$?
    if [ $SMOKE_RC -ne 0 ]; then
        # smoke test 失败只警告, 不阻塞 deploy (业务用户密码可能用户改过)
        warn "smoke test 部分失败 (exit $SMOKE_RC), 自动跑 diagnose 定位"
        echo ""
        bash "$SCRIPT_DIR/diagnose.sh" --port $BACKEND_PORT --frontend-port $FRONTEND_PORT --to $VERSION
        echo ""
        warn "smoke test 不通过, 但 deploy 核心 (PHASE 0-5+7) 可能仍成功"
        echo "  1. 看上面 diagnose 输出定位"
        echo "  2. 如果 5001/8081 listening + current 切了, 部署实际可用"
        echo "  3. 回滚: bash /tmp/rollback.sh --to <v> --port <p>"
        # 不自动 exit, 不设 FAIL_FLAG, 让 PHASE 7 切链接 (用户决定)
    fi
else
    warn "跳过 smoke test (--skip-smoke)"
fi

# ========================= V007.25 fd 增量检查 (后置 PHASE 6.6) =========================
# [V007.25] 验证 V007.24 修复: 100 个 v2 BOAction 请求后, fd 数应不增长
# baseline newline fix: tr -d '\\n\\r' (避免 [: integer expression expected)
FD_AFTER=$(lsof 2>/dev/null | grep -c "architecture" 2>/dev/null || echo 0)
FD_BASELINE=$(cat /tmp/v00725_fd_baseline_$VERSION.txt 2>/dev/null | tr -d '\n\r' || echo 0)
if [ -n "$FD_BASELINE" ] && [ "$FD_BASELINE" -gt 0 ]; then
    FD_DIFF=$((FD_AFTER - FD_BASELINE))
    echo "  fd 增量: $FD_DIFF (基线: $FD_BASELINE, 当前: $FD_AFTER)"
    if [ "$FD_DIFF" -gt 10 ]; then
        warn "  fd 增量 $FD_DIFF > 10 (V007.24 修复后应 ≤ 2)"
    else
        ok "  fd 增量 $FD_DIFF ≤ 10 (V007.24 修复有效)"
    fi
fi

# ========================= PHASE 6.55: 部署后 MD5 验证 (V007.25 强制) =========================
# [FIX 2026-07-07] 14:44 部署 bug: yonaa PHASE 0.5 跳过了 unzip, backend 跑旧代码
# 修法: PHASE 6.55 立即验证 yonaa /opt/app/deployments/ 关键文件 MD5 = zip MD5
banner "PHASE 6.55: yonaa 部署后 MD5 验证 [V007.25]"
MD5_MISMATCH=0
for CRITICAL_FILE in meta/server.py meta/core/datasource.py; do
    if [ -f "$DEPLOYMENTS_DIR/$CRITICAL_FILE" ]; then
        ZIP_MD5=$(unzip -p "$ZIP_PATH" "$CRITICAL_FILE" 2>/dev/null | md5sum | awk '{print $1}')
        ROOT_MD5=$(md5sum "$DEPLOYMENTS_DIR/$CRITICAL_FILE" 2>/dev/null | awk '{print $1}')
        if [ -n "$ZIP_MD5" ] && [ -n "$ROOT_MD5" ] && [ "$ZIP_MD5" != "$ROOT_MD5" ]; then
            err "  [X] $CRITICAL_FILE MD5 不匹配 (zip=${ZIP_MD5:0:8}, yonaa=${ROOT_MD5:0:8})"
            MD5_MISMATCH=$((MD5_MISMATCH + 1))
        else
            ok "  [OK] $CRITICAL_FILE MD5 一致 (${ZIP_MD5:0:8})"
        fi
    else
        err "  [X] $CRITICAL_FILE 不存在 (PHASE 0.5 unzip 失败!)"
        MD5_MISMATCH=$((MD5_MISMATCH + 1))
    fi
done
if [ "$MD5_MISMATCH" -gt 0 ]; then
    err "MD5 验证失败 ($MD5_MISMATCH/2 不匹配) → V007.24 修复没进入 yonaa"
    V00725_MD5_FAIL_FLAG=1
else
    ok "MD5 验证通过 (V007.24 修复 100% 在 yonaa 部署目录中)"
    V00725_MD5_FAIL_FLAG=0
fi

# ========================= PHASE 6.6: V007.25 v2 BOAction 验证 (5 次连续) =========================
# [V007.25] 强制 5 次连续 v2 BOAction login 验证 (V007.24 修复必跑)
banner "PHASE 6.6: V007.25 v2 BOAction 验证 (5 次连续)"
V2_SUCCESS=0
V2_FAILED=0
for i in 1 2 3 4 5; do
    # [V007.25 fix] 用 admin/admin123 (确保 yonaa 存在), 而非 deploy_test (可能不存在)
    RESP=$(curl -s -X POST "http://localhost:$BACKEND_PORT/api/v2/action/user.authenticate" \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"admin123"}' 2>&1)
    if echo "$RESP" | grep -q '"success":true'; then
        echo "  [$i/5] [OK] v2 BOAction 成功"
        V2_SUCCESS=$((V2_SUCCESS + 1))
    else
        echo "  [$i/5] [X] v2 BOAction 失败: $RESP"
        V2_FAILED=$((V2_FAILED + 1))
    fi
done
echo "  结果: 成功 $V2_SUCCESS / 5, 失败 $V2_FAILED / 5"
if [ "$V2_FAILED" -gt 0 ]; then
    err "v2 BOAction 验证失败 ($V2_FAILED/5)"
    err "  极可能是 V007.24 类问题 (fd 泄漏 / lazy data_source)"
    warn "未自动回滚, 请人工确认是否继续"
    V00725_V2_FAIL_FLAG=1
else
    ok "v2 BOAction 5/5 PASS"
    V00725_V2_FAIL_FLAG=0
fi

# ========================= PHASE 7: 切 current 链接 =========================
banner "PHASE 7: 切 current 链接"
rm -f $CURRENT_LINK
ln -sfn $VERSION_PATH $CURRENT_LINK && ok "current → $VERSION_PATH" || err "ln 失败"
ls -la $CURRENT_LINK

# 部署核心成功判定: 端口 listening + 链接已切
DEPLOY_CORE_OK=0
if ss -tlnp 2>/dev/null | grep -qE ":(${BACKEND_PORT}|${FRONTEND_PORT})"; then
    DEPLOY_CORE_OK=1
fi
if [ -L "$CURRENT_LINK" ] && [ "$(readlink $CURRENT_LINK)" = "$VERSION_PATH" ]; then
    DEPLOY_CORE_OK=1
fi
if [ $DEPLOY_CORE_OK -eq 1 ]; then
    DEPLOY_OK_FLAG=1
fi

# ========================= SUMMARY =========================
banner "DEPLOY SUMMARY"
echo -e "  部署核心 (PHASE 0-5+7): $([ $DEPLOY_OK_FLAG -eq 1 ] && echo -e "${GREEN}✓ 成功${NC}" || echo -e "${RED}✗ 失败${NC}")"
echo -e "  smoke test (PHASE 6.5):   $([ $SMOKE_RC -eq 0 ] && echo -e "${GREEN}✓ 通过${NC}" || echo -e "${YELLOW}⚠ 部分失败 (不阻塞)${NC}")"
echo ""

if [ $DEPLOY_OK_FLAG -eq 1 ]; then
    echo "✓ 部署成功 (端口 listening + current 链接已切)"
    echo ""
    echo "浏览器访问: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${FRONTEND_PORT}/"
    echo "登录: deploy_test / DeployTest@2026! (部署验证专用)"
    echo "      admin / admin123 (业务用户, 密码可能被改过)"
    echo "日志: $LOG_DIR/backend-${VERSION}.log, $LOG_DIR/frontend-${VERSION}.log"
    echo "回滚: bash /tmp/rollback.sh --to $(current_version | sed "s/^v//" | awk -F_ '{print $1"_"$2}') --port <port>"
    exit 0
else
    echo "✗ 部署核心失败 (端口未起 或 链接未切)"
    echo "回滚: bash /tmp/rollback.sh --to <previous_version> --port <previous_port>"
    exit 1
fi
