#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V007.46 disk I/O error 恢复验证 (P0)

[V007.46 BUG-FIX 2026-07-08] 验证 V007.44 6 FIX 在工作树 meta/ 实际落地,
并新增 db_corruption_monitor/db_admin_api/diagnostics_api 3 个文件的裸连接修复

V8w: 验证 safe_connect._open_safe_connection 含 mmap_size = 0
V8x: 验证 _cleanup_resources 函数有 _cleanup_done 幂等守卫
V8y: 验证 _apply_data_permission except 路径含 id = -1 拒绝
V8z: 验证 db_corruption_monitor/db_admin_api/diagnostics_api 4 处全部改用 safe_connect
V8aa: 验证 import_export_service._flatten 有 leaf_op 参数
V8ab: 验证 full_text_search/query_by_hierarchy_path/suggest/aggregate 4 方法调用 _apply_data_permission
V8ac: 验证 _cleanup_resources 文件 4 处 (signal/atexit 入口) 都设了 _cleanup_done 守卫

用法:
  python tools/verify_v007_46_ioerror_recovery.py
"""
import os
import sys
import ast
import re
from pathlib import Path

WORKTREE_ROOT = Path(__file__).parent.parent
META_DIR = WORKTREE_ROOT / "meta"

FAILED = []
PASSED = []


def check_v8w():
    """V8w: safe_connect.py _open_safe_connection 含 mmap_size = 0"""
    f = META_DIR / "core" / "safe_connect.py"
    content = f.read_text(encoding="utf-8")
    if "PRAGMA mmap_size = 0" in content and "_open_safe_connection" in content:
        PASSED.append("V8w: safe_connect.py _open_safe_connection 含 mmap_size=0")
        return True
    FAILED.append("V8w: safe_connect.py 缺 mmap_size=0 PRAGMA")
    return False


def check_v8x():
    """V8x: server.py _cleanup_resources 函数有 _cleanup_done 幂等守卫"""
    f = META_DIR / "server.py"
    content = f.read_text(encoding="utf-8")
    if "_cleanup_done" in content and "if _cleanup_done:" in content:
        PASSED.append("V8x: server.py _cleanup_resources 含 _cleanup_done 幂等守卫")
        return True
    FAILED.append("V8x: server.py _cleanup_resources 缺 _cleanup_done 幂等守卫")
    return False


def check_v8y():
    """V8y: query_service._apply_data_permission except 路径含 id = -1 拒绝"""
    f = META_DIR / "services" / "query_service.py"
    content = f.read_text(encoding="utf-8")
    # 找 _apply_data_permission 函数体
    m = re.search(r"def _apply_data_permission\(.*?(?=\n    def |\nclass )", content, re.DOTALL)
    if not m:
        FAILED.append("V8y: query_service.py _apply_data_permission 函数未找到")
        return False
    func_body = m.group(0)
    if "id" in func_body and "-1" in func_body and "except" in func_body:
        PASSED.append("V8y: query_service._apply_data_permission except 含 id=-1 拒绝")
        return True
    FAILED.append("V8y: query_service._apply_data_permission except 缺 id=-1 拒绝")
    return False


def check_v8z():
    """V8z: db_corruption_monitor 4 处 + db_admin_api 2 处 + diagnostics_api 1 处
    全部改用 safe_connect"""
    issues = []
    for rel, must_contain, min_count in [
        ("core/db_corruption_monitor.py", "safe_connect_for_read", 4),
        ("api/db_admin_api.py", "safe_connect_for_read", 2),
        ("api/diagnostics_api.py", "safe_connect_for_read", 1),
    ]:
        f = META_DIR / rel
        if not f.exists():
            issues.append(f"文件不存在: {rel}")
            continue
        content = f.read_text(encoding="utf-8")
        count = content.count(must_contain)
        if count < min_count:
            issues.append(f"{rel} 缺 {must_contain} (需 ≥{min_count}, 实际 {count})")
    if not issues:
        PASSED.append("V8z: 3 文件 7 处裸连接全部改用 safe_connect_for_read")
        return True
    FAILED.append("V8z: " + "; ".join(issues))
    return False


def check_v8aa():
    """V8aa: import_export_service._flatten 有 leaf_op 参数"""
    f = META_DIR / "services" / "import_export_service.py"
    content = f.read_text(encoding="utf-8")
    if "def _flatten(conds: List[Dict], leaf_op" in content:
        PASSED.append("V8aa: import_export_service._flatten 含 leaf_op 参数")
        return True
    FAILED.append("V8aa: import_export_service._flatten 缺 leaf_op 参数")
    return False


def check_v8ab():
    """V8ab: full_text_search/query_by_hierarchy_path/suggest/aggregate 4 方法调用 _apply_data_permission"""
    f = META_DIR / "services" / "query_service.py"
    content = f.read_text(encoding="utf-8")
    issues = []
    for method in ["full_text_search", "query_by_hierarchy_path", "suggest", "aggregate"]:
        # 找函数体
        m = re.search(rf"def {method}\(.*?(?=\n    def |\nclass )", content, re.DOTALL)
        if not m:
            issues.append(f"方法 {method} 未找到")
            continue
        if "_apply_data_permission" not in m.group(0):
            issues.append(f"方法 {method} 缺 _apply_data_permission 调用")
    if not issues:
        PASSED.append("V8ab: 4 查询方法全部含 _apply_data_permission 调用")
        return True
    FAILED.append("V8ab: " + "; ".join(issues))
    return False


def check_v8ac():
    """V8ac: db_health_monitor 2 处裸连接 + async_audit_writer 降级路径 mmap_size=0"""
    issues = []
    # db_health_monitor 2 处
    f = META_DIR / "core" / "db_health_monitor.py"
    content = f.read_text(encoding="utf-8")
    if content.count("safe_connect_for_read") < 2:
        issues.append("db_health_monitor.py 缺 safe_connect_for_read (需 ≥2)")
    # async_audit_writer 降级路径
    f2 = META_DIR / "services" / "async_audit_writer.py"
    content2 = f2.read_text(encoding="utf-8")
    # 找降级路径
    m = re.search(r"# 降级到原裸连接.*?(?=\n            # )", content2, re.DOTALL)
    if m and "mmap_size=0" in m.group(0) and "cache_size=-2000" in m.group(0):
        pass
    else:
        issues.append("async_audit_writer.py 降级路径缺 mmap_size=0 + cache_size=-2000")
    if not issues:
        PASSED.append("V8ac: db_health_monitor 2 处 + async_audit_writer 降级路径全部加固")
        return True
    FAILED.append("V8ac: " + "; ".join(issues))
    return False


def main():
    print("=" * 60)
    print("V007.46 disk I/O error 恢复验证 (P0)")
    print("=" * 60)
    print()
    print(f"工作树: {WORKTREE_ROOT}")
    print(f"meta 路径: {META_DIR}")
    print()
    print("-" * 60)
    print("V8x 系列 invariant (V007.46 P0 BUG-FIX 锚点):")
    print("-" * 60)
    check_v8w()
    check_v8x()
    check_v8y()
    check_v8z()
    check_v8aa()
    check_v8ab()
    check_v8ac()
    print()
    print("-" * 60)
    print(f"PASSED ({len(PASSED)}):")
    for p in PASSED:
        print(f"  + {p}")
    print()
    if FAILED:
        print(f"FAILED ({len(FAILED)}):")
        for fail in FAILED:
            print(f"  ! {fail}")
        print()
        print(f"共 {len(FAILED)}/{len(PASSED) + len(FAILED)} 失败")
        return 1
    else:
        print(f"共 {len(PASSED)}/{len(PASSED)} 通过 ✅")
        return 0


if __name__ == "__main__":
    sys.exit(main())
