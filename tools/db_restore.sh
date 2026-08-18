#!/bin/bash
# ============================================================
# db_restore.sh - 从最近可用备份恢复损坏的 SQLite DB
# [2026-08-18] v20260817 事故恢复 SOP 固化
#
# 流程:
#   1. (可选) 优雅停止访问该 DB 的服务
#   2. 备份当前(损坏) DB -> <db>.corrupt_<ts>
#   3. 自动挑选最近的 quick_check=ok 备份 (或显式指定)
#   4. 替换 + 清理 -wal/-shm/-journal 残留
#   5. quick_check 验证
#   6. 提示重启服务
#
# 用法:
#   bash db_restore.sh <DB_PATH>                     # 自动选最近可用备份
#   bash db_restore.sh <DB_PATH> <BACKUP_PATH>       # 显式指定备份
# 退出码: 0=恢复成功 / 1=失败
# ============================================================
set -u

DB_PATH="${1:-}"
[ -z "$DB_PATH" ] && { echo "用法: $0 <DB_PATH> [BACKUP_PATH]" >&2; exit 1; }
BACKUP_PATH="${2:-}"
PY="${PYTHON:-python3}"

[ -f "$DB_PATH" ] || { echo "[FATAL] DB 不存在: $DB_PATH" >&2; exit 1; }
TS=$(date +%Y%m%d_%H%M%S)
DB_DIR=$(dirname "$DB_PATH")

check_ok() { # 检查一个 DB 文件 quick_check 是否 ok
    $PY - "$1" <<'PYEOF'
import sqlite3, sys
try:
    c = sqlite3.connect(sys.argv[1], timeout=10)
    r = c.execute("PRAGMA quick_check").fetchone()[0]
    c.close()
    print(r)
except Exception as e:
    print(f"ERROR: {e}")
PYEOF
}

# ---------- 0. 优雅停止访问 DB 的服务 (server/unified/log_service) ----------
echo "[restore] 优雅停止访问 DB 的服务 (SIGTERM)"
for pat in "server.py" "unified_server" "log_service.py"; do
    pkill -TERM -f "$pat" 2>/dev/null && echo "  $pat SIGTERM sent" || echo "  $pat not running"
done
for i in $(seq 1 10); do
    pgrep -f "server.py|unified_server|log_service.py" >/dev/null 2>&1 || break
    sleep 1
done
REMAIN=$(pgrep -f "server.py|unified_server|log_service.py" 2>/dev/null | wc -l)
if [ "${REMAIN:-0}" -gt 0 ]; then
    echo "  [WARN] ${REMAIN} 进程未退出, SIGKILL 兜底"
    pkill -9 -f "server.py" 2>/dev/null; pkill -9 -f "unified_server" 2>/dev/null; pkill -9 -f "log_service.py" 2>/dev/null
fi
sleep 2

# ---------- 1. 备份当前损坏 DB ----------
echo "[restore] 备份当前(损坏) DB"
cp -f "$DB_PATH" "${DB_PATH}.corrupt_${TS}" 2>/dev/null \
    && echo "  [OK] -> ${DB_PATH}.corrupt_${TS}" || echo "  [WARN] 备份当前 DB 失败 (继续)"

# ---------- 2. 确定备份源 ----------
if [ -n "$BACKUP_PATH" ]; then
    echo "[restore] 使用显式备份: $BACKUP_PATH"
    SRC="$BACKUP_PATH"
else
    echo "[restore] 自动挑选最近 quick_check=ok 备份..."
    # 候选: 各种备份模式, 按 mtime 降序
    CANDIDATES=$(ls -t "$DB_DIR"/architecture.db.bak.* "$DB_DIR"/architecture.db.pre_* "$DB_DIR"/architecture.db.predeploy_* \
        "$DB_DIR"/architecture.db.baseline 2>/dev/null)
    SRC=""
    for c in $CANDIDATES; do
        [ "$c" = "$DB_PATH" ] && continue
        R=$(check_ok "$c")
        echo "  $c -> $R"
        if [ "$R" = "ok" ]; then SRC="$c"; break; fi
    done
    [ -z "$SRC" ] && { echo "[FATAL] 未找到可用备份" >&2; exit 1; }
fi
echo "  [OK] 使用备份: $SRC"

# ---------- 3. 替换 + 清理残留 ----------
echo "[restore] 替换 DB + 清理残留"
cp -f "$SRC" "$DB_PATH" || { echo "[FATAL] 复制备份失败" >&2; exit 1; }
for suf in -wal -shm -journal; do
    rm -f "${DB_PATH}${suf}" 2>/dev/null && echo "  清理 ${suf} 残留"
done

# ---------- 4. 验证 ----------
R=$(check_ok "$DB_PATH")
echo "[restore] 恢复后 quick_check: $R"
if [ "$R" != "ok" ]; then
    echo "[FATAL] 恢复后 DB 仍不完整" >&2
    exit 1
fi

# 关键表计数
$PY - "$DB_PATH" <<'PYEOF'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1], timeout=10)
for t in ('users', 'business_objects'):
    try:
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t}: {n}")
    except Exception as e:
        print(f"  {t}: ERR {e}")
c.close()
PYEOF

echo "[restore] ===== 恢复完成: $DB_PATH ====="
echo "  请重启服务 (后端 13011: /opt/miniconda3-py39/bin/python -u $DB_DIR/current/server.py)"
echo "  或直接重新执行部署脚本 (会自动重启后端)"
exit 0
