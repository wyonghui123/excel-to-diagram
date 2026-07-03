#!/bin/bash
# reset_admin_password.sh - 重置 admin 密码为 admin123
# 用法: bash /tmp/deploy_bundle/reset_admin_password.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib/common.sh" 2>/dev/null || true

DB="${DB_PATH:-/opt/app/deployments/meta/architecture.db}"
PY="${PY:-/opt/miniconda3-py39/bin/python}"
USERNAME="${1:-admin}"
NEW_PASSWORD="${2:-admin123}"

banner "RESET ADMIN PASSWORD"

if [ ! -f "$DB" ]; then
    die "db 不存在: $DB"
fi
ok "db: $DB"

# 用 python 算 SHA-256 密码 hash (跟 meta/scripts 一致)
HASH=$($PY -c "
import hashlib
print(hashlib.sha256('$NEW_PASSWORD'.encode()).hexdigest())
" 2>/dev/null)

if [ -z "$HASH" ] || [ "${#HASH}" -ne 64 ]; then
    die "算 hash 失败: $HASH"
fi
ok "新 hash: $HASH (64 chars)"

# 备份 db
BACKUP="/opt/app/backups/architecture_$(date +%Y%m%d_%H%M%S).db"
cp -p "$DB" "$BACKUP" && ok "备份: $BACKUP" || die "备份失败"

# 看 users 表 schema
SCHEMA=$(sqlite3 "$DB" ".schema users" 2>/dev/null)
info "users schema:"
echo "$SCHEMA" | head -20

# 看现有 admin
info "现有 admin:"
sqlite3 "$DB" "SELECT id, username, length(password_hash) FROM users WHERE username='$USERNAME';" 2>/dev/null

# 看 password_hash 字段名 (password_hash vs password)
PWD_COL=$(sqlite3 "$DB" "PRAGMA table_info(users);" 2>/dev/null | grep -iE "password|hash|pwd" | head -1 | awk -F'|' '{print $2}' | tr -d ' ')
if [ -z "$PWD_COL" ]; then
    PWD_COL="password_hash"
fi
ok "password column: $PWD_COL"

# 找 salt 字段 (有些方案用 salt)
SALT_COL=$(sqlite3 "$DB" "PRAGMA table_info(users);" 2>/dev/null | grep -iE "salt" | head -1 | awk -F'|' '{print $2}' | tr -d ' ')

# 更新密码
if [ -n "$SALT_COL" ]; then
    # 有 salt 字段
    info "有 salt 字段, 用 salt 模式"
    HASH_FULL=$($PY -c "
import hashlib
salt = 'fixed_salt'  # 或留空
combined = '$NEW_PASSWORD' + salt
print(hashlib.sha256(combined.encode()).hexdigest())
")
    sqlite3 "$DB" "UPDATE users SET $PWD_COL='$HASH_FULL' WHERE username='$USERNAME';" && ok "更新 $PWD_COL (带 salt)" || die "更新失败"
else
    # 无 salt, 直接 SHA-256
    sqlite3 "$DB" "UPDATE users SET $PWD_COL='$HASH' WHERE username='$USERNAME';" && ok "更新 $PWD_COL (SHA-256)" || die "更新失败"
fi

# 验证
info "更新后:"
sqlite3 "$DB" "SELECT id, username, length($PWD_COL) FROM users WHERE username='$USERNAME';" 2>/dev/null

# 测试 login
info "测试 login:"
LOGIN=$($PY -c "
import sqlite3
conn = sqlite3.connect('$DB')
c = conn.cursor()
c.execute('SELECT $PWD_COL FROM users WHERE username=?', ('$USERNAME',))
row = c.fetchone()
if not row:
    print('USER_NOT_FOUND')
else:
    h = row[0]
    import hashlib
    if h == hashlib.sha256('$NEW_PASSWORD'.encode()).hexdigest():
        print('LOGIN_OK')
    elif h == hashlib.sha256(('$NEW_PASSWORD'+'fixed_salt').encode()).hexdigest():
        print('LOGIN_OK_SALT')
    else:
        print(f'HASH_MISMATCH: db={h[:16]}...')
")
echo "$LOGIN"

# 实际 curl 测
info "curl login test:"
curl -s -X POST http://127.0.0.1:5001/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$NEW_PASSWORD\"}" 2>&1 | head -3

banner "RESET ADMIN PASSWORD DONE"
