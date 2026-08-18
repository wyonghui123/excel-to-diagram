#!/bin/bash
# ============================================================
# db_preflight.sh - 部署前 DB 安全预检 + WAL→DELETE 迁移
# [2026-08-18] 针对根因: WAL checkpoint TRUNCATE + 并发连接 + 强杀 → malformed
#
# 背景 (v20260817 部署事故):
#   - 部署期间对 WAL 模式 DB 执行 wal_checkpoint(TRUNCATE)
#   - 进程被 pkill -9 强杀 + 两次进程启动反复 checkpoint + 并发连接未释放
#   - → WAL 与主库不一致 → "database disk image is malformed"
#
# 本脚本职责 (调用方必须先停止访问该 DB 的服务):
#   1. 检查 DB 存在 + 无 -wal/-shm/-journal 残留
#   2. wal_checkpoint(PASSIVE) 合并 WAL (非 TRUNCATE, 有并发连接时更安全)
#   3. journal_mode=DELETE (持久化, 根治 WAL 损坏面)
#   4. PRAGMA quick_check 验证完整性
#   5. 任何失败退出非 0, 调用方应中止部署 (fail-fast)
#
# 用法: bash db_preflight.sh <DB_PATH>
# 退出码: 0=OK / 1=失败
# ============================================================
set -u

DB_PATH="${1:-}"
if [ -z "$DB_PATH" ]; then
    echo "[db_preflight] FATAL: 用法 $0 <DB_PATH>" >&2
    exit 1
fi

PY="${PYTHON:-python3}"
FAIL=0

echo "[db_preflight] ===== DB 安全预检: $DB_PATH ====="

# ---------- 0. DB 存在性 ----------
if [ ! -f "$DB_PATH" ]; then
    echo "[db_preflight] FATAL: DB 不存在: $DB_PATH" >&2
    exit 1
fi

# ---------- 1. 残留文件检查 ----------
for suf in -wal -shm -journal; do
    f="${DB_PATH}${suf}"
    if [ -f "$f" ]; then
        echo "[db_preflight] WARN: 残留 ${suf} 文件: $f ($(stat -c%s "$f" 2>/dev/null) bytes)"
        # WAL 残留: 交给下方 checkpoint 合并; shm/journal 残留: 在 DELETE 模式切换后由 SQLite 清理
    else
        echo "[db_preflight] OK: 无 ${suf} 残留"
    fi
done

# ---------- 2. Python 执行: PASSIVE checkpoint → DELETE → quick_check ----------
echo "[db_preflight] Python 步骤: wal_checkpoint(PASSIVE) → journal_mode=DELETE → quick_check"
$PY - "$DB_PATH" <<'PYEOF'
import sqlite3, sys

db = sys.argv[1]
conn = sqlite3.connect(db, timeout=10)
conn.execute("PRAGMA busy_timeout = 10000")
fail = False

# 2.1 PASSIVE checkpoint (合并 WAL, 不强制 TRUNCATE)
try:
    busy, log_frames, checkpointed = conn.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
    print(f"[db_preflight] wal_checkpoint(PASSIVE): busy={busy} log_frames={log_frames} checkpointed={checkpointed}")
    if busy:
        print(f"[db_preflight] WARN: checkpoint 被 {busy} 个并发连接阻塞 (调用方应确认服务已停止)")
except Exception as e:
    print(f"[db_preflight] ERROR: wal_checkpoint(PASSIVE) 失败: {e}")
    fail = True

# 2.2 journal_mode=DELETE (持久化, 根治 WAL 损坏面)
try:
    mode = conn.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
    print(f"[db_preflight] journal_mode=DELETE -> {mode}")
    if mode.lower() != "delete":
        print(f"[db_preflight] ERROR: journal_mode 未切换到 DELETE (实际={mode})")
        fail = True
except Exception as e:
    print(f"[db_preflight] ERROR: journal_mode=DELETE 失败: {e}")
    fail = True

# 2.3 quick_check 完整性
try:
    result = conn.execute("PRAGMA quick_check").fetchone()[0]
    if result == "ok":
        print("[db_preflight] OK: quick_check 通过")
    else:
        print(f"[db_preflight] FATAL: quick_check 失败: {result}")
        fail = True
except Exception as e:
    print(f"[db_preflight] FATAL: quick_check 异常: {e}")
    fail = True

conn.close()
sys.exit(1 if fail else 0)
PYEOF
[ $? -ne 0 ] && FAIL=1

# ---------- 3. 结果 ----------
if [ $FAIL -eq 0 ]; then
    echo "[db_preflight] ===== 预检通过, DB 已处于 DELETE 模式且完整 ===== $DB_PATH"
    exit 0
else
    echo "[db_preflight] ===== 预检失败, 中止部署 ===== $DB_PATH" >&2
    exit 1
fi
