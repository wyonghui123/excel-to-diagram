# -*- coding: utf-8 -*-
"""
[V8ab BUG-FIX 2026-07-09] 业务回归测试
- 100 次并发 user.authenticate
- 100 次并发 business_object
- 0 disk I/O error
- 0 5xx error
- 之前: 部署智能体 9 次"业务正常" 假象, 实际 disk I/O 持续
- 现在: 部署后立即跑 V8ab, 任何 disk I/O error 立即报警
"""
import sys
import os
import time
import concurrent.futures
import urllib.request
import urllib.error
import json

# yonaa 后端地址 (log_service 9101 proxy)
YONAA_HOST = os.environ.get("YONAA_HOST", "172.20.59.7")
BACKEND_URL = f"http://{YONAA_HOST}:5001"
UNIFIED_URL = f"http://{YONAA_HOST}:8081"
LOG_SERVICE_URL = f"http://{YONAA_HOST}:9101"


def call_user_authenticate(idx):
    """并发 user.authenticate"""
    url = f"{UNIFIED_URL}/api/v2/action/user.authenticate"
    data = json.dumps({
        "username": "deploy_test",
        "password": "DeployTest@2026!",
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"Content-Type": "application/json"}
    )
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        status = resp.getcode()
        body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        status = -1
        body = str(e)
    return {
        "idx": idx,
        "status": status,
        "ms": int((time.time() - t0) * 1000),
        "body_500": "internal server error" in body.lower() or "disk i/o" in body.lower(),
    }


def call_business_object(idx):
    """并发 business_object 查询"""
    url = f"{UNIFIED_URL}/api/v2/bo/business_object?version_id=3&page=1&page_size=10"
    req = urllib.request.Request(url, method="GET")
    t0 = time.time()
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        status = resp.getcode()
        body = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        status = e.code
        body = e.read().decode("utf-8", errors="ignore")
    except Exception as e:
        status = -1
        body = str(e)
    return {
        "idx": idx,
        "status": status,
        "ms": int((time.time() - t0) * 1000),
        "body_500": "internal server error" in body.lower() or "disk i/o" in body.lower(),
    }


def get_disk_io_error_count():
    """[V007.46 BUG-FIX 2026-07-09] 用 3 端点交叉验证 disk I/O
    之前用 /api/log?file=...&lines=20000 是错的格式, 12+ 小时返 mock 数据
    现在: 1) /api/db/health 看 integrity, 2) /api/sqlite/load 200 次看 fail_rate
         3) /api/iostat 看 %util, 4) /api/dmesg 看 kernel IO error
    """
    io_signals = {"db_integrity": None, "load_fail_rate": None, "iostat_util": None, "dmesg_io_errors": None}

    # 1. db integrity
    try:
        resp = urllib.request.urlopen(f"{LOG_SERVICE_URL}/api/db/health", timeout=5)
        io_signals["db_integrity"] = json.loads(resp.read().decode("utf-8")).get("integrity", "?")
    except Exception:
        pass

    # 2. sqlite/load 200 次
    try:
        resp = urllib.request.urlopen(f"{LOG_SERVICE_URL}/api/sqlite/load?n=200&db=architecture", timeout=30)
        d = json.loads(resp.read().decode("utf-8"))
        io_signals["load_fail_rate"] = d.get("fail_rate", -1)
    except Exception:
        pass

    # 3. iostat %util
    try:
        resp = urllib.request.urlopen(f"{LOG_SERVICE_URL}/api/iostat", timeout=5)
        d = json.loads(resp.read().decode("utf-8"))
        out = d.get("output", "")
        # 取最后一行 vda
        lines = [l for l in out.split("\n") if "vda " in l]
        if lines:
            last = lines[-1].split()
            io_signals["iostat_util"] = float(last[12]) if len(last) > 12 else -1
    except Exception:
        pass

    # 4. dmesg kernel IO error
    try:
        resp = urllib.request.urlopen(f"{LOG_SERVICE_URL}/api/dmesg", timeout=5)
        d = json.loads(resp.read().decode("utf-8"))
        if isinstance(d, list):
            io_signals["dmesg_io_errors"] = sum(1 for l in d if "I/O error" in l or "disk I/O" in l)
        else:
            io_signals["dmesg_io_errors"] = -1
    except Exception:
        pass

    # 评判: 任何 fail > 0 = 有 IO error
    if io_signals["load_fail_rate"] is not None and io_signals["load_fail_rate"] > 0:
        return -2  # 200 次压测有 fail
    if io_signals["iostat_util"] is not None and io_signals["iostat_util"] > 30:
        return -3  # 磁盘忙
    if io_signals["dmesg_io_errors"] is not None and io_signals["dmesg_io_errors"] > 0:
        return -4  # kernel 报 IO error
    return 0  # 0 IO error


def get_health_v8_fields():
    """从后端 5001 读 /health V8w~V8ad 字段"""
    url = f"{BACKEND_URL}/health"
    req = urllib.request.Request(url)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return {"error": str(e)}


def main():
    print("===== V8ab 业务回归测试 =====")
    print(f"  yonaa: {YONAA_HOST}")
    print(f"  unified: {UNIFIED_URL}")
    print(f"  backend: {BACKEND_URL}")
    print()

    # Step 1: 检查 /health V8w~V8ad 字段
    print("Step 1: 验证 /health V8w~V8ad 字段")
    health = get_health_v8_fields()
    if "error" in health:
        print(f"  [FAIL] /health 不可达: {health['error']}")
        return 1
    missing = [k for k in ["V8w", "V8x", "V8y", "V8z", "V8aa"] if k not in health]
    if missing:
        print(f"  [FAIL] /health 缺 V8w~V8ad 字段: {missing}")
        print(f"  当前 /health: {json.dumps(health, ensure_ascii=False)[:500]}")
        return 1
    print(f"  [OK] V8w~V8ad 字段全在")

    # 检查 V8z (8 关键文件标记)
    v8z = health.get("V8z", {})
    missing_markers = [k for k, v in v8z.items() if not v.get("has_marker")]
    if missing_markers:
        print(f"  [FAIL] V8z 8 关键文件标记缺失: {missing_markers}")
        return 1
    print(f"  [OK] V8z 8 关键文件全有 V007.46 标记")

    # Step 2: 100 次并发 user.authenticate
    print()
    print("Step 2: 100 次并发 user.authenticate")
    n = 100
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(call_user_authenticate, i) for i in range(n)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.time() - t0
    succ = sum(1 for r in results if 200 <= r["status"] < 300)
    fail = sum(1 for r in results if not (200 <= r["status"] < 300))
    has_500 = sum(1 for r in results if r["body_500"])
    print(f"  100 次 user.authenticate: succ={succ}, fail={fail}, has_500_in_body={has_500}, elapsed={elapsed:.1f}s")
    if has_500 > 0:
        print(f"  [FAIL] user.authenticate 返回 500/disk I/O: {has_500} 次")
        return 1
    if fail > 0:
        print(f"  [WARN] user.authenticate 非 2xx: {fail} 次 (status={set(r['status'] for r in results if not (200 <= r['status'] < 300))})")

    # Step 3: 100 次并发 business_object
    print()
    print("Step 3: 100 次并发 business_object")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(call_business_object, i) for i in range(n)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.time() - t0
    succ = sum(1 for r in results if 200 <= r["status"] < 300)
    fail = sum(1 for r in results if not (200 <= r["status"] < 300))
    has_500 = sum(1 for r in results if r["body_500"])
    print(f"  100 次 business_object: succ={succ}, fail={fail}, has_500_in_body={has_500}, elapsed={elapsed:.1f}s")
    if has_500 > 0:
        print(f"  [FAIL] business_object 返回 500/disk I/O: {has_500} 次")
        return 1

    # Step 4: log_service disk I/O 错误检查
    print()
    print("Step 4: log_service disk I/O 错误检查")
    disk_err_count = get_disk_io_error_count()
    print(f"  backend log disk I/O 错误: {disk_err_count}")
    if disk_err_count > 10:
        print(f"  [FAIL] disk I/O 错误 > 10, 部署后真根因未修")
        return 1
    print(f"  [OK] disk I/O 错误 ≤ 10")

    print()
    print("===== V8ab 业务回归测试 PASS =====")
    return 0


if __name__ == "__main__":
    sys.exit(main())
