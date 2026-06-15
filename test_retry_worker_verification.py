# -*- coding: utf-8 -*-
"""
验证 audit retry worker 运行状态和 AUDIT_WRITE_FAILED 处理情况
"""
import requests
import json
import time

BASE_URL = "http://localhost:3010"

def login():
    """登录获取 auth_token"""
    resp = requests.post(f"{BASE_URL}/api/v1/auth/login", json={
        "username": "admin",
        "password": "admin123"
    })
    if resp.status_code == 200:
        data = resp.json()
        if data.get("success"):
            return data["data"]["token"]
    return None

def check_retry_worker_status(token):
    """检查 retry worker 状态"""
    cookies = {"auth_token": token}
    resp = requests.get(f"{BASE_URL}/api/v1/audit/retry/status", cookies=cookies)
    if resp.status_code == 200:
        data = resp.json()
        print("\n=== Retry Worker Status ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data
    else:
        print(f"Failed to get retry status: {resp.status_code}")
        print(resp.text)
        return None

def check_audit_write_failed_count(token):
    """检查 AUDIT_WRITE_FAILED 记录数量"""
    cookies = {"auth_token": token}
    
    # 查询 status='failed' 的 AUDIT_WRITE_FAILED 记录
    resp = requests.get(f"{BASE_URL}/api/v1/audit/logs", cookies=cookies, params={
        "page": 1,
        "page_size": 1,
        "filters": json.dumps([
            {"field": "action", "operator": "eq", "value": "AUDIT_WRITE_FAILED"},
            {"field": "status", "operator": "eq", "value": "failed"}
        ])
    })
    
    if resp.status_code == 200:
        data = resp.json()
        # data 格式: {"success": True, "data": [...], "total": 100, ...}
        total = data.get("total", 0)
        print(f"\n=== AUDIT_WRITE_FAILED (status=failed) Count: {total} ===")
        return total
    else:
        print(f"Failed to query AUDIT_WRITE_FAILED: {resp.status_code}")
        return None

def check_retried_count(token):
    """检查已重试成功的记录数量"""
    cookies = {"auth_token": token}
    
    resp = requests.get(f"{BASE_URL}/api/v1/audit/logs", cookies=cookies, params={
        "page": 1,
        "page_size": 1,
        "filters": json.dumps([
            {"field": "status", "operator": "eq", "value": "retried"}
        ])
    })
    
    if resp.status_code == 200:
        data = resp.json()
        # data 格式: {"success": True, "data": [...], "total": 100, ...}
        total = data.get("total", 0)
        print(f"\n=== Retried (status=retried) Count: {total} ===")
        return total
    else:
        print(f"Failed to query retried: {resp.status_code}")
        return None

def trigger_retry(token):
    """手动触发 retry worker 执行一次"""
    cookies = {"auth_token": token}
    resp = requests.post(f"{BASE_URL}/api/v1/audit/retry/trigger", cookies=cookies)
    if resp.status_code == 200:
        data = resp.json()
        print("\n=== Trigger Retry Worker ===")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return data
    else:
        print(f"Failed to trigger retry: {resp.status_code}")
        print(resp.text)
        return None

def main():
    print("=" * 60)
    print("Audit Retry Worker Verification")
    print("=" * 60)
    
    # 1. 登录
    print("\n[1] Logging in...")
    token = login()
    if not token:
        print("Login failed!")
        return
    print(f"Login success, token: {token[:20]}...")
    
    # 2. 检查 retry worker 状态
    print("\n[2] Checking retry worker status...")
    status = check_retry_worker_status(token)
    
    # 3. 检查 AUDIT_WRITE_FAILED 记录数
    print("\n[3] Checking AUDIT_WRITE_FAILED count...")
    failed_count = check_audit_write_failed_count(token)
    
    # 4. 检查已重试记录数
    print("\n[4] Checking retried count...")
    retried_count = check_retried_count(token)
    
    # 5. 如果有 failed 记录，手动触发 retry
    if failed_count and failed_count > 0:
        print(f"\n[5] Found {failed_count} failed records, triggering retry...")
        trigger_retry(token)
        
        # 等待 retry worker 处理
        print("\n[6] Waiting 5 seconds for retry worker...")
        time.sleep(5)
        
        # 再次检查状态
        print("\n[7] Re-checking status after retry...")
        check_retry_worker_status(token)
        check_audit_write_failed_count(token)
        check_retried_count(token)
    else:
        print("\n[5] No failed records found, skip trigger")
    
    print("\n" + "=" * 60)
    print("Verification complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
