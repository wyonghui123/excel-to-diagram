#!/bin/bash
# reset_deploy_test_user.sh - 部署验证专用用户管理
#
# 设计:
#   - admin = 业务用户, deploy 不动 (用户改的密码保留)
#   - deploy_test = 部署验证专用, 每次 deploy 自动重置
#
# 用法:
#   bash reset_deploy_test_user.sh              # 创建/重置 deploy_test, 密码 DeployTest@2026!
#   bash reset_deploy_test_user.sh --remove     # 删除 deploy_test
#   bash reset_deploy_test_user.sh --check      # 只检查, 不修改

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib/common.sh" 2>/dev/null || true

DB="${DB_PATH:-/opt/app/deployments/meta/architecture.db}"
PY="${PY:-/opt/miniconda3-py39/bin/python}"
DEPLOY_USER="deploy_test"
DEPLOY_PASSWORD="DeployTest@2026!"

MODE="reset"
if [ "${1:-}" = "--check" ]; then
    MODE="check"
elif [ "${1:-}" = "--remove" ]; then
    MODE="remove"
fi

banner "RESET DEPLOY TEST USER ($DEPLOY_USER)"

if [ ! -f "$DB" ]; then
    die "db 不存在: $DB"
fi
ok "db: $DB"

# 1. 备份
BACKUP="/opt/app/backups/architecture_$(date +%Y%m%d_%H%M%S).db"
cp -p "$DB" "$BACKUP" && ok "备份: $BACKUP"

# 2. 看 users 表 schema
SCHEMA=$(sqlite3 "$DB" ".schema users" 2>/dev/null)
info "users schema:"
echo "$SCHEMA" | head -20

# 3. 找字段
PWD_COL=$(sqlite3 "$DB" "PRAGMA table_info(users);" 2>/dev/null | grep -iE "password|hash|pwd" | head -1 | awk -F'|' '{print $2}' | tr -d ' ')
[ -z "$PWD_COL" ] && PWD_COL="password_hash"
ok "password column: $PWD_COL"

# 看其他必要字段
ALL_COLS=$(sqlite3 "$DB" "PRAGMA table_info(users);" 2>/dev/null | awk -F'|' '{print $2}' | tr -d ' ')
info "users columns: $ALL_COLS"

# 4. 检查 deploy_test 是否存在
EXISTING=$($PY -c "
import sqlite3
conn = sqlite3.connect('$DB')
c = conn.cursor()
c.execute('SELECT id, $PWD_COL FROM users WHERE username=?', ('$DEPLOY_USER',))
row = c.fetchone()
if not row:
    print('NOT_FOUND')
else:
    print(f'FOUND:id={row[0]}, hash={row[1][:8]}...')
")
info "deploy_test 状态: $EXISTING"

# 5. 计算 hash (PBKDF2-SHA256, 跟 auth_provider.py 一致)
HASH=$($PY -c "
import hashlib, secrets
# 跟 meta/services/auth_provider.py _hash_password_pbdkdf2 一致
salt = secrets.token_hex(16)  # 32 chars hex
iterations = 100000
pw = '$DEPLOY_PASSWORD'.encode('utf-8')
salt_bytes = salt.encode('utf-8')
h = hashlib.pbkdf2_hmac('sha256', pw, salt_bytes, iterations).hex()
print(f'PBKDF2\${iterations}\${salt}\${h}')
")
ok "新 hash: ${HASH:0:30}..."

# 6. 按模式处理
if [ "$MODE" = "check" ]; then
    if [[ "$EXISTING" == NOT_FOUND* ]]; then
        warn "deploy_test 不存在, 用 reset 模式创建"
    else
        # 验证密码
        CURRENT_HASH=$($PY -c "
import sqlite3
conn = sqlite3.connect('$DB')
c = conn.cursor()
c.execute('SELECT $PWD_COL FROM users WHERE username=?', ('$DEPLOY_USER',))
row = c.fetchone()
if row:
    print(row[0])
")
        if [ "$CURRENT_HASH" = "$HASH" ]; then
            ok "deploy_test 密码 = $DEPLOY_PASSWORD (正确)"
        else
            warn "deploy_test 密码 ≠ $DEPLOY_PASSWORD (用 reset 模式重置)"
        fi
    fi
    banner "CHECK DONE"
    exit 0
fi

if [ "$MODE" = "remove" ]; then
    if [[ "$EXISTING" == NOT_FOUND* ]]; then
        info "deploy_test 不存在, 无需删除"
    else
        sqlite3 "$DB" "DELETE FROM users WHERE username='$DEPLOY_USER';" && ok "删除 deploy_test" || die "删除失败"
    fi
    banner "REMOVE DONE"
    exit 0
fi

# MODE = reset (默认)
if [[ "$EXISTING" == NOT_FOUND* ]]; then
    # 创建新用户 - 找必要字段
    info "创建 deploy_test 用户..."
    # 必须字段: username, password_hash, created_at (可能需要)
    # 通用做法: 只插 username + password_hash
    # 如果缺 created_at 触发 NOT NULL, 报错再处理
    sqlite3 "$DB" "INSERT INTO users (username, $PWD_COL) VALUES ('$DEPLOY_USER', '$HASH');" 2>/tmp/insert_err.log
    if [ $? -ne 0 ]; then
        # 可能缺字段, 尝试带 created_at
        info "重试带 created_at..."
        NOW=$(date -u +"%Y-%m-%d %H:%M:%S")
        sqlite3 "$DB" "INSERT INTO users (username, $PWD_COL, created_at) VALUES ('$DEPLOY_USER', '$HASH', '$NOW');" && ok "创建 + 设置密码" || die "创建失败: $(cat /tmp/insert_err.log)"
    else
        ok "创建 deploy_test + 设置密码"
    fi
else
    # 已有, 更新密码
    sqlite3 "$DB" "UPDATE users SET $PWD_COL='$HASH' WHERE username='$DEPLOY_USER';" && ok "重置密码" || die "重置失败"
fi

# 7. 验证
info "验证:"
sqlite3 "$DB" "SELECT id, username, length($PWD_COL) FROM users WHERE username='$DEPLOY_USER';" 2>/dev/null

# 8. curl login 测 (如果 backend alive)
if curl -s -m 2 http://127.0.0.1:5001/api/v1/enum-types >/dev/null 2>&1; then
    info "curl login 测试:"
    LOGIN_RESULT=$(curl -s -X POST http://127.0.0.1:5001/api/v1/auth/login \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"$DEPLOY_USER\",\"password\":\"$DEPLOY_PASSWORD\"}")
    echo "$LOGIN_RESULT" | head -1
    if echo "$LOGIN_RESULT" | grep -q '"success":true'; then
        ok "deploy_test login OK"
    else
        warn "deploy_test login FAIL: $LOGIN_RESULT"
    fi
else
    info "backend 不在 5001, 跳过 login 测试"
fi

banner "RESET DEPLOY TEST USER DONE"
echo "下次 deploy 可用: deploy_test / $DEPLOY_PASSWORD (自动重置)"
