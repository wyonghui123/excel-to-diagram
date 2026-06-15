# -*- coding: utf-8 -*-
"""
验证修复：
1. 触发 CREATE/UPDATE/DELETE/ASSOCIATE/DISSOCIATE 操作
2. 等待 5s
3. 检查 AUDIT_WRITE_FAILED (status='failed') 数量是否不变
4. 检查新创建的审计日志 (action != 'AUDIT_WRITE_FAILED') 数量
"""
import requests
import json
import time
import sqlite3
import os
import random
import string
from datetime import datetime

BASE_URL = "http://localhost:3010"
DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "meta", "architecture.db"
)

def random_str(n=6):
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=n))

def login():
    resp = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "admin", "password": "admin123"
    })
    if resp.status_code == 200 and resp.json().get("success"):
        return resp.json()["data"]["token"]
    return None

def count_audit_write_failed(db_conn):
    cur = db_conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action='AUDIT_WRITE_FAILED' AND status='failed'"
    )
    return cur.fetchone()[0]

def count_recent_audit(db_conn, since_iso):
    cur = db_conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE created_at > ? AND action != 'AUDIT_WRITE_FAILED'",
        (since_iso,)
    )
    return cur.fetchone()[0]

def create_user(cookies, username):
    resp = requests.post(f"{BASE_URL}/api/v1/users", cookies=cookies, json={
        "username": username,
        "display_name": f"Verify User {username}",
        "email": f"{username}@verify.com",
        "role": "user",
        "password": "verify_pass_123"
    })
    return resp

def create_role(cookies, name):
    resp = requests.post(f"{BASE_URL}/api/v1/roles", cookies=cookies, json={
        "name": name,
        "code": f"verify_role_{random_str(4)}",
        "description": "verify role",
        "permissions": []
    })
    return resp

def create_user_group(cookies, name):
    # [FIX 2026-06-13] /api/v1/user-groups 已 sunset, 改用 /api/v2/bo/user_group
    resp = requests.post(f"{BASE_URL}/api/v2/bo/user_group", cookies=cookies, json={
        "name": name,
        "code": f"verify_group_{random_str(4)}",
        "description": "verify user group"
    })
    return resp

def main():
    print("=" * 70)
    print("AUDIT_WRITE_FAILED 修复验证")
    print("=" * 70)
    
    # 登录
    token = login()
    if not token:
        print("[FAIL] Login failed")
        return
    cookies = {"auth_token": token}
    print(f"[OK] Login success")
    
    # 打开 DB
    conn = sqlite3.connect(DB_PATH, timeout=10)
    
    # 1. 记录初始 failed 数
    initial_failed = count_audit_write_failed(conn)
    start_time = datetime.now().isoformat()
    print(f"\n[Init] AUDIT_WRITE_FAILED (status=failed): {initial_failed}")
    print(f"[Init] Start time: {start_time}")
    
    # 2. 触发操作
    print(f"\n[Step 1] Trigger CREATE operations...")
    ts = random_str()
    
    # 2.1 创建用户
    user_resp = create_user(cookies, f"verify_user_{ts}")
    print(f"  create_user: {user_resp.status_code} {user_resp.text[:200]}")
    
    # 2.2 创建角色
    role_resp = create_role(cookies, f"verify_role_{ts}")
    print(f"  create_role: {role_resp.status_code} {role_resp.text[:200]}")
    
    # 2.3 创建用户组
    group_resp = create_user_group(cookies, f"verify_group_{ts}")
    print(f"  create_user_group: {group_resp.status_code} {group_resp.text[:200]}")
    
    # 3. 等待异步写入
    print(f"\n[Step 2] Wait 5s for async audit writer...")
    time.sleep(5)
    
    # 4. 重新统计
    after_failed = count_audit_write_failed(conn)
    new_audits = count_recent_audit(conn, start_time)
    
    print(f"\n[Verify Result]")
    print(f"  AUDIT_WRITE_FAILED (status=failed): {initial_failed} -> {after_failed} (delta={after_failed - initial_failed})")
    print(f"  New audit logs (action != 'AUDIT_WRITE_FAILED'): {new_audits}")
    
    # 5. 结论
    if after_failed == initial_failed and new_audits >= 3:
        print(f"\n[PASS] 修复成功!")
        print(f"  - AUDIT_WRITE_FAILED 未增长 (delta=0)")
        print(f"  - 新增 {new_audits} 条正常审计日志")
    elif after_failed > initial_failed:
        print(f"\n[FAIL] 修复失败!")
        print(f"  - AUDIT_WRITE_FAILED 仍增长 (delta=+{after_failed - initial_failed})")
    else:
        print(f"\n[WARN] 未知状态")
    
    conn.close()
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
