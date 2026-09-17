#!/bin/bash
# reset_admin_password.sh - 重置 admin 密码为 admin123
# 用法: bash /tmp/deploy_bundle/reset_admin_password.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/lib/common.sh" 2>/dev/null || true

DB="${DB_PATH:-/opt/app/deployments/meta/architecture.db}"
PY="${PY:-/opt/miniconda3-py39/bin/python}"

# [FIX 2026-07-03] 智能检测: 只在 admin 不存在或 --force 时重置
USERNAME="admin"
NEW_PASSWORD="admin123"
FORCE=false
SEED_ONLY_IF_MISSING=true  # 默认安全模式
if [ "${1:-}" = "--force" ]; then
    FORCE=true
    SEED_ONLY_IF_MISSING=false
    warn "--force 模式: 会覆盖用户改的密码!"
fi

banner "RESET ADMIN PASSWORD"

if [ ! -f "$DB" ]; then
    die "db 不存在: $DB"
fi
ok "db: $DB"

# [FIX 2026-07-03] 检查 admin 是否存在 + 当前密码是否对
EXISTING=$($PY -c "
import sqlite3
conn = sqlite3.connect('$DB')
c = conn.cursor()
c.execute('SELECT id, password_hash FROM users WHERE username=?', ('$USERNAME',))
row = c.fetchone()
if not row:
    print('NOT_FOUND')
else:
    print(f'FOUND:{row[1][:8]}...')
")
if [[ "$EXISTING" == NOT_FOUND* ]]; then
    if [ "$SEED_ONLY_IF_MISSING" = "true" ] || [ "$FORCE" = "true" ]; then
        warn "admin 用户不存在, 将创建 + 设置密码为 $NEW_PASSWORD"
        SEED_MODE=true
    else
        die "admin 不存在且非 seed 模式, 退出"
    fi
else
    ok "admin 存在 ($EXISTING)"
    if [ "$FORCE" = "true" ]; then
        warn "--force: 将覆盖用户可能改过的密码为 $NEW_PASSWORD"
    elif [ "$SEED_ONLY_IF_MISSING" = "true" ]; then
        # 智能模式: 只在用户密码不匹配默认 admin123 时, 不自动重置
        # 先测试 login
        LOGIN_TEST=$(curl -s -X POST http://127.0.0.1:5001/api/v1/auth/login \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"$USERNAME\",\"password\":\"$NEW_PASSWORD\"}" 2>/dev/null)
        if echo "$LOGIN_TEST" | grep -q '"success":true'; then
            ok "admin 密码已经是 $NEW_PASSWORD, 跳过重置"
            banner "RESET ADMIN PASSWORD SKIPPED (密码正确)"
            exit 0
        else
            warn "admin 密码不是 $NEW_PASSWORD (用户可能改过), 不自动重置 (用 --force 重置)"
            banner "RESET ADMIN PASSWORD SKIPPED (需要 --force)"
            exit 0
        fi
    fi
fi

# 用 python 算 PBKDF2-SHA256 密码 hash (跟 meta/services/auth_provider.py _hash_password_pbdkdf2 一致)
HASH=$($PY -c "
import hashlib, secrets
# PBKDF2\$<iterations>\$<salt>\$<hash>
salt = secrets.token_hex(16)
iterations = 100000
pw = '$NEW_PASSWORD'.encode('utf-8')
h = hashlib.pbkdf2_hmac('sha256', pw, salt.encode('utf-8'), iterations).hex()
print(f'PBKDF2\${iterations}\${salt}\${h}')
")

if [ -z "$HASH" ]; then
    die "算 hash 失败"
fi
ok "新 hash: ${HASH:0:30}..."

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
    # 验证 PBKDF2 hash
    if h and h.startswith('PBKDF2$'):
        parts = h.split('$')
        if len(parts) == 4:
            iters, salt, hhex = int(parts[1]), parts[2], parts[3]
            calc = hashlib.pbkdf2_hmac('sha256', '$NEW_PASSWORD'.encode('utf-8'), salt.encode('utf-8'), iters).hex()
            if calc == hhex:
                print('LOGIN_OK')
            else:
                print(f'PBKDF2_MISMATCH: db[:30]={h[:30]}...')
        else:
            print(f'PBKDF2_FMT_ERR: {h[:30]}...')
    elif h and len(h) == 64:
        # 老格式纯 SHA-256
        if h == hashlib.sha256('$NEW_PASSWORD'.encode()).hexdigest():
            print('LOGIN_OK_SHA256_LEGACY')
        else:
            print(f'SHA256_MISMATCH: db[:16]={h[:16]}...')
    else:
        print(f'HASH_UNKNOWN: db={h[:30] if h else None}...')
")
echo "$LOGIN"

# 实际 curl 测
info "curl login test:"
curl -s -X POST http://127.0.0.1:5001/api/v1/auth/login \
    -H "Content-Type: application/json" \
    -d "{\"username\":\"$USERNAME\",\"password\":\"$NEW_PASSWORD\"}" 2>&1 | head -3

banner "RESET ADMIN PASSWORD DONE"
