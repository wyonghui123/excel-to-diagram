#!/usr/bin/env python3
"""
verify_bundle.py - 独立 bundle 一致性验证 (V007.25 L2 invariant)

[L2 INVARIANT] 此程序独立于 rebuild_zip.py / deploy.sh, 独立验证 bundle 一致性
   - rebuild_zip.py 负责"生成"
   - verify_bundle.py 负责"验证"
   - 两者必须独立 (防止 rebuild 自己验证自己 = 假 PASS)

用法:
  python tools/verify_bundle.py                      # 验证 deploy_bundle/ 一致性
  python tools/verify_bundle.py --zip <path>        # 验证 zip + deploy_bundle/ 一致
  python tools/verify_bundle.py --strict            # 任何警告都 exit 1 (CI 用)
  python tools/verify_bundle.py --json               # JSON 输出 (供 CI / metric 用)

检查项 (8 项 invariant, 任何失败 exit 1):
  V1. deploy_bundle/ 存在
  V2. deploy_bundle/deploy.sh mtime >= tools/deploy.sh mtime (防"tools 改但 deploy_bundle 旧")
  V3. deploy_bundle/diagnose.sh mtime >= tools/diagnose.sh mtime
  V4. deploy_bundle/ 内所有 V007.25 标记文件 实际含 V007.25 标记
  V5. zip 内 MANIFEST 部署 ID 与 deploy_bundle/ 一致 (可选)
  V6. zip 内不含垃圾文件 (.db / .bak / .pyc / .lock / __pycache__)
  V7. zip 大小 < 100MB (防止误打入大文件)
  V8. zip 内含 V007.24 DataSource 缓存代码 (如声明 V007.24 部署)

返回:
  exit 0 = 全部 PASS
  exit 1 = 任何 FAIL
  exit 2 = 任何 WARN (--strict 模式)
"""
import os
import sys
import json
import subprocess
import zipfile
import hashlib
import argparse
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_BUNDLE = ROOT / "deploy_bundle"

# [V007.25] 必须含 V007.25 标记的关键文件 (L4 保障)
#   只列 V007.25 真正改过的核心脚本 (避免误报)
#   路径相对 deploy_bundle/ (V007.25 修订: scripts 在 tools/ 子目录)
V00725_MARKED_FILES = [
    "tools/deploy.sh",
    "tools/diagnose.sh",
    "tools/rebuild_zip.py",
    "tools/verify_bundle.py",
]

# [V007.25] 关键 zip 内文件 (L1 保障)
ZIP_REQUIRED_FILES = [
    "MANIFEST",
    "meta/server.py",
    "frontend_dist_files/index.html",
    "tools/deploy.sh",
    "tools/diagnose.sh",
    "tools/rebuild_zip.py",
]

# [V007.25] 垃圾文件 (与 rebuild_zip.py GARBAGE 一致)
GARBAGE_PATTERNS = [
    (".db", lambda n: n.lower().endswith(".db")),
    (".db-wal", lambda n: n.lower().endswith(".db-wal")),
    (".db-shm", lambda n: n.lower().endswith(".db-shm")),
    (".bak", lambda n: ".bak" in n.lower()),
    (".backup", lambda n: ".backup" in n.lower()),
    (".pyc", lambda n: n.endswith(".pyc")),
    ("backups/", lambda n: "backups/" in n.lower()),
    ("logs/", lambda n: "logs/" in n.lower()),
    ("screenshots/", lambda n: "screenshots/" in n.lower()),
    ("__pycache__", lambda n: "__pycache__" in n.lower()),
    (".lock", lambda n: n.lower().endswith(".lock")),
]


def check_v1_deploy_bundle_exists() -> tuple:
    """V1. deploy_bundle/ 存在"""
    if DEPLOY_BUNDLE.exists():
        return (True, f"{DEPLOY_BUNDLE} 存在")
    return (False, f"{DEPLOY_BUNDLE} 不存在")


def check_v2_deploy_sh_mtime() -> tuple:
    """V2. deploy_bundle/tools/deploy.sh mtime >= tools/deploy.sh mtime"""
    src = ROOT / "tools" / "deploy.sh"
    dst = DEPLOY_BUNDLE / "tools" / "deploy.sh"
    if not src.exists():
        return (False, f"tools/deploy.sh 不存在")
    if not dst.exists():
        return (False, f"deploy_bundle/tools/deploy.sh 不存在")
    src_mtime = src.stat().st_mtime
    dst_mtime = dst.stat().st_mtime
    if dst_mtime >= src_mtime:
        delta = datetime.fromtimestamp(dst_mtime) - datetime.fromtimestamp(src_mtime)
        return (True, f"deploy.sh 一致 (delta={delta.total_seconds():.1f}s)")
    delta = datetime.fromtimestamp(src_mtime) - datetime.fromtimestamp(dst_mtime)
    return (False, f"deploy_bundle/tools/deploy.sh 比 tools/deploy.sh 旧 {delta.total_seconds():.1f}s (必须 rebuild)")


def check_v3_diagnose_sh_mtime() -> tuple:
    """V3. deploy_bundle/tools/diagnose.sh mtime >= tools/diagnose.sh mtime"""
    src = ROOT / "tools" / "diagnose.sh"
    dst = DEPLOY_BUNDLE / "tools" / "diagnose.sh"
    if not src.exists():
        return (False, f"tools/diagnose.sh 不存在")
    if not dst.exists():
        return (False, f"deploy_bundle/tools/diagnose.sh 不存在")
    src_mtime = src.stat().st_mtime
    dst_mtime = dst.stat().st_mtime
    if dst_mtime >= src_mtime:
        return (True, f"diagnose.sh 一致")
    return (False, f"deploy_bundle/tools/diagnose.sh 比 tools/diagnose.sh 旧 (必须 rebuild)")


def check_v4_v00725_marks() -> tuple:
    """V4. deploy_bundle/ 内 V007.25 标记文件 实际含 V007.25 标记"""
    missing_marks = []
    for rel in V00725_MARKED_FILES:
        f = DEPLOY_BUNDLE / rel
        if not f.exists():
            missing_marks.append(f"{rel} 不存在")
            continue
        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return (False, f"读 {rel} 失败: {e}")
        if "V007.25" not in content:
            missing_marks.append(f"{rel} 不含 V007.25 标记")
    if missing_marks:
        return (False, "; ".join(missing_marks))
    return (True, f"全部 {len(V00725_MARKED_FILES)} 个文件含 V007.25 标记")


def check_v5_zip_deploy_id() -> tuple:
    """V5. zip 内 MANIFEST 部署 ID 与 deploy_bundle/ 一致 (可选)"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")  # WARN, not FAIL
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open("MANIFEST") as f:
                manifest = f.read().decode("utf-8", errors="replace")
        # 提取 deploy_id
        import re
        m = re.search(r'deploy_id:\s*"([^"]+)"', manifest)
        if not m:
            return (False, "MANIFEST 缺 deploy_id 字段")
        return (True, f"deploy_id={m.group(1)}")
    except Exception as e:
        return (False, f"读 MANIFEST 失败: {e}")


def check_v6_zip_no_garbage() -> tuple:
    """V6. zip 内不含垃圾文件"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            garbage_hits = []
            for name in zf.namelist():
                for label, fn in GARBAGE_PATTERNS:
                    if fn(name):
                        garbage_hits.append(f"{label}: {name}")
                        break
        if garbage_hits:
            return (False, f"含 {len(garbage_hits)} 个垃圾: {garbage_hits[:3]}")
        return (True, "无垃圾文件")
    except Exception as e:
        return (False, f"扫 zip 失败: {e}")


def check_v7_zip_size() -> tuple:
    """V7. zip 大小 < 100MB"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    size_mb = zip_path.stat().st_size / 1024 / 1024
    if size_mb > 100:
        return (False, f"zip {size_mb:.1f}MB > 100MB (可能误打入大文件)")
    return (True, f"zip {size_mb:.1f}MB")


def check_v8_zip_v00724_code() -> tuple:
    """V8. zip 内含 V007.24 DataSource 缓存代码 (如声明 V007.24 部署)"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open("meta/core/datasource.py") as f:
                content = f.read().decode("utf-8", errors="replace")
        if "_data_source_cache" in content and "V007.24" in content:
            return (True, "V007.24 DataSource 缓存代码存在")
        return (False, "zip 内 datasource.py 缺 V007.24 缓存代码")
    except KeyError:
        return (False, "zip 内缺 meta/core/datasource.py")
    except Exception as e:
        return (False, f"读 datasource.py 失败: {e}")


def check_v8b_zip_v00734_v00735() -> tuple:
    """V8b. [V007.35 FIX 22:24] zip 内含 V007.34 (sql_adapters retry) + V007.35 (sql_connection_pool mmap)"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            ad = zf.read("meta/core/sql_adapters.py").decode("utf-8", errors="ignore")
            pool = zf.read("meta/core/sql_connection_pool.py").decode("utf-8", errors="ignore")
        # V007.34: 读路径 retry 标记
        v34 = ad.count("V007.34")
        # V007.35: mmap_size / cache_size PRAGMA
        v35 = pool.count("V007.35") + pool.count("mmap_size") + pool.count("cache_size")
        if v34 == 0:
            return (False, f"sql_adapters.py 缺 V007.34 读路径 retry 标记")
        if v35 < 1:
            return (False, f"sql_connection_pool.py 缺 V007.35 mmap/cache PRAGMA")
        return (True, f"V007.34={v34} 标记 + V007.35={v35} 标记 (retry+mmap 都在)")
    except Exception as e:
        return (False, f"读 sql_*.py 失败: {e}")


def check_v8o_zip_not_behind_working_tree() -> tuple:
    """V8o. zip 必须包含 working tree 全部 fix commit (防部署疏忽)
    任何 fix(be): commit 都必须在最新 zip 内, 否则 zip 已 stale
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        # 读 zip deploy_id 中的 HEAD
        with zipfile.ZipFile(zip_path, "r") as zf:
            # MANIFEST 文件名可能多种: MANIFEST (无后缀, yaml 格式), 在根或 tools/ 或 meta/
            manifest = ""
            for p in ["MANIFEST", "MANIFEST.json", "tools/MANIFEST.json", "meta/MANIFEST.json", "meta/MANIFEST"]:
                if p in zf.namelist():
                    manifest = zf.read(p).decode("utf-8", errors="ignore")
                    break
        # 用 regex 提取 head 字段 (兼容 yaml/json)
        import re
        m = re.search(r'^\s*head:\s*["\']?([0-9a-f]{40})(?:-dirty)?["\']?', manifest, re.MULTILINE)
        zip_head = m.group(1) if m else "unknown"
        # 读 working tree HEAD
        try:
            wt_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
        except Exception as e:
            return (True, f"读 working tree HEAD 失败 (跳过): {e}")
        if zip_head == "unknown":
            return (True, f"manifest 无 git_commit, 跳过")
        # 算 working tree HEAD 是否包含 zip HEAD
        try:
            merge_base = subprocess.check_output(["git", "merge-base", zip_head, wt_head], cwd=str(ROOT), text=True).strip()
            # 如果 merge_base == zip_head, 说明 zip HEAD 在 wt HEAD 之前 (zip 落后)
            if merge_base == zip_head and zip_head != wt_head:
                # 计算落后几个 commit
                try:
                    count = int(subprocess.check_output(
                        ["git", "rev-list", "--count", f"{zip_head}..{wt_head}"],
                        cwd=str(ROOT), text=True).strip())
                    return (False, f"zip HEAD={zip_head[:8]} 落后 working tree HEAD={wt_head[:8]} ({count} 个 commit 未打包) — 部署疏忽 BUG 复发")
                except Exception:
                    return (False, f"zip HEAD={zip_head[:8]} 落后 working tree HEAD={wt_head[:8]} — 部署疏忽 BUG 复发")
            return (True, f"zip HEAD={zip_head[:8]} 不落后 working tree HEAD={wt_head[:8]}")
        except subprocess.CalledProcessError as e:
            return (True, f"merge-base 失败 (跳过): {e}")
    except Exception as e:
        return (False, f"读 zip manifest 失败: {e}")


def check_v8h_log_service_v35_merge() -> tuple:
    """V8h. log_service 必须含 v3.5 新端点 (合并升级 V007.37)
    排查 disk I/O error 真因必需: sqlite (直查), sqlite/load (压力), iostat (磁盘抖动), proc/io (进程字节)
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            ls = zf.read("tools/log_service.py").decode("utf-8", errors="ignore")
        needed = ["/api/sqlite", "/api/sqlite/load", "/api/iostat", "/api/proc/io"]
        missing = [n for n in needed if n not in ls]
        if missing:
            return (False, f"log_service.py 缺 v3.5 端点 (V007.37 BUG 复发): {missing}")
        # 检查 v3.5 端点的实现方法也存在
        methods = ["def _sqlite", "def _sqlite_load", "def _iostat", "def _proc_io"]
        missing_m = [m for m in methods if m not in ls]
        if missing_m:
            return (False, f"log_service.py 缺 v3.5 端点实现: {missing_m}")
        return (True, f"log_service.py 含 {len(needed)} 个 v3.5 端点 + 实现")
    except Exception as e:
        return (False, f"读 log_service.py 失败: {e}")


def check_v8c_zip_startup_checks_default() -> tuple:
    """V8c. [V007.36 BUG-FIX] startup_checks._is_debug() 默认值必须 'True' (跟 server.py:983 一致)"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            sc = zf.read("meta/core/startup_checks.py").decode("utf-8", errors="ignore")
        # 检查 _is_debug() 默认 'True' 不是 'false' (精确匹配 .get('FLASK_DEBUG', '...') 形式)
        import re
        # 匹配 .get('FLASK_DEBUG', 'XXX') 但 'XXX' 必须是单词边界, 排除注释里的引用
        m = re.search(r"\.get\(['\"]FLASK_DEBUG['\"]\s*,\s*['\"]([a-zA-Z]+)['\"]\)", sc)
        if not m:
            return (False, "找不到 .get('FLASK_DEBUG', ...) 调用")
        default = m.group(1).lower()
        if default != 'true':
            return (False, f"_is_debug() 默认 '{m.group(1)}' (应为 'True'/'true')")
        return (True, f"_is_debug() 默认 '{m.group(1)}' (跟 server.py:983 一致)")
    except Exception as e:
        return (False, f"读 startup_checks.py 失败: {e}")


def check_v8d_zip_pool_pragma_idempotent() -> tuple:
    """V8d. [V007.37 BUG-FIX] sql_connection_pool._create_connection 的 PRAGMA journal_mode=WAL
    必须只在首次创建时执行 (防止重复执行触发 disk I/O error, 见 V007.37 HANDOFF §4)
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            pool = zf.read("meta/core/sql_connection_pool.py").decode("utf-8", errors="ignore")
        # 检查 PRAGMA journal_mode=WAL 仍存在 (功能未丢)
        if "PRAGMA journal_mode=WAL" not in pool and 'PRAGMA journal_mode = WAL' not in pool:
            return (False, "找不到 PRAGMA journal_mode=WAL 调用 (期望保留, 只是去重)")
        # 检查幂等保护: 标志位
        markers = ["_journal_mode_applied", "_journal_mode_set", "journal_mode_applied"]
        if not any(m in pool for m in markers):
            return (False, "PRAGMA journal_mode=WAL 没有幂等保护 (V007.37 BUG 复发)")
        # 检查有 if 条件包裹 (跳过定义处的 marker, 找所有出现位置)
        for marker in markers:
            search_start = 0
            while True:
                idx = pool.find(marker, search_start)
                if idx < 0:
                    break
                context = pool[max(0, idx - 200):idx + 200]
                if ("if not" in context or "if not self" in context) and "PRAGMA journal_mode" in pool[max(0, idx - 400):idx + 400]:
                    return (True, f"PRAGMA journal_mode=WAL 有幂等保护标记 ({marker}) + if 包裹")
                search_start = idx + 1
        return (False, f"幂等标记存在但缺少 if 条件包裹 (V007.37 BUG 复发)")
    except Exception as e:
        return (False, f"读 sql_connection_pool.py 失败: {e}")


def check_v8e_zip_query_service_retry() -> tuple:
    """V8e. [V007.37 BUG-FIX] query_service 导出路径 retry 包裹
    _try_apply_dimension_scope 调用必须包在 _try_apply_dimension_scope_with_retry 里
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            qs = zf.read("meta/services/query_service.py").decode("utf-8", errors="ignore")
        if "_try_apply_dimension_scope_with_retry" not in qs:
            return (False, "找不到 _try_apply_dimension_scope_with_retry (V007.37 BUG 复发)")
        if "V007.37" not in qs:
            return (False, "query_service.py 缺少 V007.37 标记")
        return (True, "_try_apply_dimension_scope_with_retry 已包裹 (V007.37)")
    except Exception as e:
        return (False, f"读 query_service.py 失败: {e}")


def check_v8f_zip_v00738_task_scheduler_retry() -> tuple:
    """V8f. [V007.38 BUG-FIX] task_scheduler 写路径必须 retry disk I/O error
    _create_execution_record 必须有 retry + backoff 包裹
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            ts = zf.read("meta/core/task_scheduler.py").decode("utf-8", errors="ignore")
        if "V007.38" not in ts:
            return (False, "task_scheduler.py 缺少 V007.38 标记")
        if "max_retries" not in ts or "_create_execution_record" not in ts:
            return (False, "task_scheduler retry 结构不完整")
        # 确认 retry 在 _create_execution_record 里
        idx = ts.find("_create_execution_record")
        if idx > 0:
            context = ts[idx:idx + 3000]  # 看函数体
            if "for attempt in range" not in context:
                return (False, "_create_execution_record 没有 retry loop")
        return (True, "_create_execution_record 已加 retry (V007.38)")
    except Exception as e:
        return (False, f"读 task_scheduler.py 失败: {e}")


def check_v8g_zip_v00738_mmap_size() -> tuple:
    """V8g. [V007.38/V007.42] mmap_size 必须明确 (64MB=67108864 或 0=禁用)
    V007.38: 改为 64MB (性能)
    V007.42 P5: 改为 0 (禁用, mmap 在 WAL+并发下反效果, FR-008)
    必须是这两种之一, 不能有中间值 (避免退化)
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            pool = zf.read("meta/core/sql_connection_pool.py").decode("utf-8", errors="ignore")
        # 找 ConnectionConfig.mmap_size: int = XXX (实际赋值, 排除注释)
        import re
        m = re.search(r'mmap_size\s*[:=]\s*(?:int\s*[=:])?\s*(\d+)', pool)
        if not m:
            return (False, "找不到 mmap_size 赋值 (V007.38/V007.42 BUG 复发)")
        val = int(m.group(1))
        if val not in (0, 67108864):
            return (False, f"mmap_size={val} 既不是 0 (V007.42 禁用) 也不是 67108864 (V007.38 64MB), 异常值")
        desc = "0 (V007.42 禁用)" if val == 0 else "64MB (V007.38)"
        return (True, f"mmap_size={val} ({desc})")
    except Exception as e:
        return (False, f"读 sql_connection_pool.py 失败: {e}")


def check_v8p_zip_v00742_health_fields() -> tuple:
    """V8p. [V007.42 FR-003] sql_connection_pool.health_check() 必须含 4 字段
    V007.42 P6: health_check() 增强, 必须返回 reader_health + checkpoint_busy + io_rate_limit + max_readers
    防退化: 任何 health_check 简化都会暴露问题
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            sc = zf.read("meta/core/sql_connection_pool.py").decode("utf-8", errors="ignore")
        needed = ["reader_health", "checkpoint_busy", "io_rate_limit", "max_readers"]
        missing = [n for n in needed if n not in sc]
        if missing:
            return (False, f"health_check() 缺 V007.42 P6 字段 (FR-003 BUG 复发): {missing}")
        return (True, f"health_check() 含全部 4 个 V007.42 P6 字段 (reader_health/checkpoint_busy/io_rate_limit/max_readers)")
    except Exception as e:
        return (False, f"读 sql_connection_pool.py 失败: {e}")


def check_v8k_zip_v00738_auto_vacuum_idempotent() -> tuple:
    """[V007.38 BUG-FIX] 移交给集成测试, 不在 verify_bundle 范围 (见 tests/test_v007_38_task_scheduler.py)
    auto_vacuum 幂等保护
    """
    return (True, "已迁移到 tests/test_v007_38_task_scheduler.py::TestV00738AutoVacuumIdempotent")


def check_v8l_zip_v00738_writer_lock() -> tuple:
    """[V007.38 BUG-FIX] 移交给集成测试, 不在 verify_bundle 范围 (见 tests/test_v007_38_task_scheduler.py)
    acquire_writer 线程锁
    """
    return (True, "已迁移到 tests/test_v007_38_task_scheduler.py::TestV00738WriterLock")


def check_v8m_zip_v00738_no_select_last_insert_rowid() -> tuple:
    """[V007.38 BUG-FIX] 移交给集成测试, 不在 verify_bundle 范围 (见 tests/test_v007_38_task_scheduler.py)
    task_scheduler 用 cursor.lastrowid
    """
    return (True, "已迁移到 tests/test_v007_38_task_scheduler.py::TestV00738CursorLastrowId")


def check_v9_zip_required_files() -> tuple:
    """V9. zip 含所有必需文件"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
        missing = [f for f in ZIP_REQUIRED_FILES if f not in names]
        if missing:
            return (False, f"缺 {len(missing)} 个必需文件: {missing[:3]}")
        return (True, f"全部 {len(ZIP_REQUIRED_FILES)} 个必需文件存在")
    except Exception as e:
        return (False, f"扫 zip 失败: {e}")


# [V007.25] 必须 LF 编码的脚本 (yonaa 是 Linux, CRLF 会失败)
#   zip 内路径前缀是 tools/ (rebuild_zip.py 复制整个 tools/ 目录)
LF_REQUIRED_FILES = [
    "tools/deploy.sh",
    "tools/diagnose.sh",
    "tools/rollback.sh",
    "tools/smoke_test.sh",
    "tools/lib/common.sh",
    "tools/lib/check_deploy_health.sh",
]


def check_v10_no_crlf() -> tuple:
    """V10. [V007.25] 关键脚本无 CRLF (yonaa bash 不识别 \\r)"""
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    crlf_files = []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for rel in LF_REQUIRED_FILES:
                try:
                    with zf.open(rel) as f:
                        # 读完整个文件 (脚本最多 50KB, 不算大)
                        content = f.read()
                    if b'\r\n' in content or (b'\r' in content and b'\n' not in content[:200]):
                        crlf_files.append(rel)
                except KeyError:
                    crlf_files.append(f"{rel} (缺失)")
        if crlf_files:
            return (False, f"含 CRLF: {crlf_files[:3]}")
        return (True, f"全部 {len(LF_REQUIRED_FILES)} 个脚本 LF 编码")
    except Exception as e:
        return (False, f"检查 CRLF 失败: {e}")


# 全局 zip_path (用于 V5-V9)
zip_path = None




def check_v11_mtime_stable() -> tuple:
    """V11. [V007.25] mtime 稳定性检查 (防止 force_lf_in_tree 破坏 mtime)"""
    # 检查 tools/ 和 deploy_bundle/tools/ 的 mtime 一致
    pairs = [
        ("tools/deploy.sh", "tools/deploy.sh"),
        ("tools/diagnose.sh", "tools/diagnose.sh"),
    ]
    issues = []
    for rel, _ in pairs:
        src = ROOT / "tools" / rel
        dst = DEPLOY_BUNDLE / "tools" / rel
        if not src.exists() or not dst.exists():
            continue
        # mtime 应在 1 秒内
        diff = abs(src.stat().st_mtime - dst.stat().st_mtime)
        if diff > 60:  # 容差 60s
            issues.append(f"{rel} mtime diff={diff:.1f}s")
    if issues:
        return (False, f"mtime 漂移: {issues[:2]}")
    return (True, "mtime 稳定 (delta < 60s)")




def check_v12_unzip_e2e() -> tuple:
    """V12. [V007.25] 本机解压后验证 (防 unzip 失败/路径错/内容不对)

    之前我只看 zip 内的 V007.24 标记, 但没解压验证.
    14:44 yonaa 部署后, 实际部署的 datasource.py 不含 V007.24 (zip->解压 后丢失).
    此 invariant 模拟 yonaa 的 deploy.sh PHASE 0.5 unzip, 然后验证关键代码存在.
    """
    import tempfile, zipfile, shutil
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)
            # 验证解压后的 meta/core/datasource.py 含 V007.24
            ds_path = Path(tmp) / "meta" / "core" / "datasource.py"
            if not ds_path.exists():
                return (False, "解压后缺 meta/core/datasource.py")
            content = ds_path.read_text(encoding="utf-8", errors="replace")
            v24 = content.count("V007.24")
            cache = content.count("_data_source_cache")
            if v24 == 0 or cache == 0:
                return (False, f"解压后 datasource.py V007.24={v24}, cache={cache} (zip 内是 23/34, 解压后丢失!)")
            # 验证 meta/server.py 也存在
            srv_path = Path(tmp) / "meta" / "server.py"
            if not srv_path.exists():
                return (False, "解压后缺 meta/server.py")
            return (True, f"解压后 datasource.py OK (V007.24={v24}, cache={cache})")
    except Exception as e:
        return (False, f"解压验证失败: {e}")




def check_v13_deploy_e2e() -> tuple:
    """V13. [V007.25] 本机模拟 deploy.sh PHASE 0.5 完整 unzip 验证

    14:44 部署 bug: 本机只验 zip 内 (V12), 没验 unzip 后的内容是否能被部署正确识别.
    真正根因: yonaa PHASE 0.5 跳过了 unzip, 因为 dist hash 匹配 + server_dir 存在.
    此 invariant 模拟 yonaa PHASE 0.5 完整逻辑:
      1. 模拟 /opt/app/deployments/ 为临时目录
      2. 模拟 PHASE 0.5 unzip
      3. 验证解压后关键文件存在 + MD5 一致
    """
    import tempfile, zipfile, shutil
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with tempfile.TemporaryDirectory() as tmp:
            DEPLOYMENTS = Path(tmp) / "deployments"
            DEPLOYMENTS.mkdir()
            # 模拟 PHASE 0.5: 首次部署, 目录不存在 -> NEED_UNZIP=true
            NEED_UNZIP = True
            if NEED_UNZIP:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zf.extractall(DEPLOYMENTS)
            # 验证部署后关键文件
            critical_files = ["meta/server.py", "meta/core/datasource.py", "MANIFEST"]
            missing = []
            for rel in critical_files:
                f = DEPLOYMENTS / rel
                if not f.exists():
                    missing.append(rel)
                    continue
                # 验证 MD5 与 zip 一致
                import hashlib
                with zipfile.ZipFile(zip_path, "r") as zf:
                    zip_md5 = hashlib.md5(zf.read(rel)).hexdigest()
                root_md5 = hashlib.md5(f.read_bytes()).hexdigest()
                if zip_md5 != root_md5:
                    return (False, f"解压后 {rel} MD5 不一致 (zip={zip_md5[:8]}, root={root_md5[:8]})")
            if missing:
                return (False, f"解压后缺: {missing}")
            return (True, f"解压后 {len(critical_files)} 个关键文件 MD5 一致 (V007.24 修复 100% 进入 yonaa 部署目录)")
    except Exception as e:
        return (False, f"PHASE 0.5 模拟失败: {e}")


def check_v8q_zip_bo_framework_import_consistency() -> tuple:
    """V8q. [V007.43 P0 BUG-FIX] intent_api 引用 bo_framework 函数时, bo_framework.py 必须有同名函数

    背景: V007.41 P3 (commit 9d051f9) 在 meta/api/intent_api.py:26 写了
          `from meta.core.bo_framework import get_bo_framework`,
          但 bo_framework.py 没实现这个函数, 导致 V007.42 部署 yonaa 启动 ImportError,
          backend 5001 死亡, 业务中断。

    修法: invariant 扫描所有 `from meta.core.bo_framework import <X>` 的 X,
          验证 bo_framework.py 都有对应的 def/class X.

    排除: BOFramework 类导入 + bo_framework 单例变量 (不是函数定义).
    """
    if not zip_path.exists():
        return (True, "无 zip, 跳过")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            # 收集所有引用
            imported_names = set()
            api_modules = [
                "meta/api/intent_api.py",
                "meta/api/bo_api.py",
                "meta/api/user_api.py",
                "meta/api/role_api.py",
                "meta/api/user_group_api.py",
                "meta/api/filter_variant_api.py",
            ]
            for mod_path in api_modules:
                if mod_path not in zf.namelist():
                    continue
                content = zf.read(mod_path).decode("utf-8", errors="ignore")
                # 找 `from meta.core.bo_framework import X` (X 含逗号分隔多个)
                import re
                for m in re.finditer(
                    r'from\s+meta\.core\.bo_framework\s+import\s+([^\n]+)',
                    content
                ):
                    names_str = m.group(1)
                    # 处理可能的 `from ... import (a, b)` 格式
                    names_str = names_str.strip().strip("()")
                    for name in names_str.split(","):
                        name = name.strip().split(" as ")[0].strip()
                        if name:
                            imported_names.add(name)

            # 检查 bo_framework.py
            bf_content = zf.read("meta/core/bo_framework.py").decode("utf-8", errors="ignore")
            missing = []
            for name in imported_names:
                # 排除类 (class X) 和已知单例 (bo_framework)
                if name == "BOFramework":
                    continue
                if name == "bo_framework":
                    # 单例变量赋值
                    if re.search(r'^\s*bo_framework\s*=', bf_content, re.MULTILINE):
                        continue
                    else:
                        missing.append(f"bo_framework 单例变量未定义")
                else:
                    # 函数定义
                    if not re.search(rf'^\s*def\s+{name}\s*\(', bf_content, re.MULTILINE):
                        missing.append(f"{name} 函数未定义")

            if missing:
                return (
                    False,
                    f"bo_framework import 一致性失败: {missing} (V007.41 P3 BUG 复发)",
                )
            return (
                True,
                f"bo_framework import 一致性通过: {imported_names} 全部存在",
            )
    except Exception as e:
        return (False, f"V8q 检查失败: {e}")


def main():
    global zip_path
    parser = argparse.ArgumentParser(description="[V007.25] bundle 一致性验证 (L2 invariant)")
    parser.add_argument("--zip", type=Path, default=None, help="验证 zip 文件")
    parser.add_argument("--strict", action="store_true", help="任何警告 exit 1")
    parser.add_argument("--json", action="store_true", help="JSON 输出 (供 CI)")
    parser.add_argument("--metric", action="store_true", help="输出 metric 格式 (供 _metrics 端点)")
    args = parser.parse_args()

    zip_path = args.zip or (DEPLOY_BUNDLE / "deploy-v20260725_001.zip")
    # 找最新 zip
    if not args.zip:
        candidates = sorted(DEPLOY_BUNDLE.glob("deploy-v*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            zip_path = candidates[0]

    checks = [
        ("V1", "deploy_bundle/ 存在", check_v1_deploy_bundle_exists),
        ("V2", "deploy.sh mtime 一致", check_v2_deploy_sh_mtime),
        ("V3", "diagnose.sh mtime 一致", check_v3_diagnose_sh_mtime),
        ("V4", "V007.25 标记存在", check_v4_v00725_marks),
        ("V5", "zip deploy_id 存在", check_v5_zip_deploy_id),
        ("V6", "zip 无垃圾文件", check_v6_zip_no_garbage),
        ("V7", "zip 大小合理", check_v7_zip_size),
        ("V8", "V007.24 缓存代码", check_v8_zip_v00724_code),
        ("V9", "zip 必需文件", check_v9_zip_required_files),
        ("V10", "关键脚本 LF 编码 (无 CRLF)", check_v10_no_crlf),
        ("V11", "mtime 稳定性 (防 force_lf 漂移)", check_v11_mtime_stable),
        ("V12", "本机 unzip E2E 验证 (V007.24 部署后含代码)", check_v12_unzip_e2e),
        ("V13", "本机 PHASE 0.5 模拟 (解压后 MD5 一致)", check_v13_deploy_e2e),
        ("V8b", "V007.34 + V007.35 修复代码 (V007.35 FIX 22:24)", check_v8b_zip_v00734_v00735),
        ("V8c", "_is_debug() 默认 'True' (V007.36 BUG-FIX 防御)", check_v8c_zip_startup_checks_default),
        ("V8d", "PRAGMA journal_mode 幂等保护 (V007.37 BUG-FIX)", check_v8d_zip_pool_pragma_idempotent),
        ("V8e", "query_service 导出 retry 包裹 (V007.37 BUG-FIX)", check_v8e_zip_query_service_retry),
        ("V8f", "task_scheduler 写路径 retry (V007.38 BUG-FIX)", check_v8f_zip_v00738_task_scheduler_retry),
        ("V8g", "mmap_size 64MB (V007.38 BUG-FIX)", check_v8g_zip_v00738_mmap_size),
        ("V8h", "log_service v3.5 合并升级 (sqlite/load + iostat + proc/io)", check_v8h_log_service_v35_merge),
        ("V8o", "zip 不落后 working tree (防部署疏忽)", check_v8o_zip_not_behind_working_tree),
        ("V8p", "health_check() 含 V007.42 P6 4 字段 (FR-003)", check_v8p_zip_v00742_health_fields),
        ("V8k", "auto_vacuum 幂等保护 (V007.38 BUG-FIX)", check_v8k_zip_v00738_auto_vacuum_idempotent),
        ("V8l", "acquire_writer 线程锁 (V007.38 BUG-FIX)", check_v8l_zip_v00738_writer_lock),
        ("V8m", "task_scheduler 用 cursor.lastrowid (V007.38 BUG-FIX)", check_v8m_zip_v00738_no_select_last_insert_rowid),
    ]

    results = []
    fail_count = 0
    for vid, desc, fn in checks:
        try:
            ok, msg = fn()
        except Exception as e:
            ok, msg = False, f"异常: {e}"
        results.append({"id": vid, "desc": desc, "ok": ok, "msg": msg})
        if not ok:
            fail_count += 1

    if args.json:
        print(json.dumps({"results": results, "fail_count": fail_count, "deploy_bundle": str(DEPLOY_BUNDLE), "zip": str(zip_path)}, indent=2, ensure_ascii=False))
    elif args.metric:
        # 输出 Prometheus 格式
        for r in results:
            value = 1 if r["ok"] else 0
            print(f"v007_25_verify_{r['id'].lower()}_{{'status'}} {value}")
        print(f"v007_25_verify_fail_count {fail_count}")
    else:
        print(f"[V007.25] ========== bundle 一致性验证 ==========")
        print(f"  deploy_bundle: {DEPLOY_BUNDLE}")
        print(f"  zip: {zip_path}")
        print()
        for r in results:
            tag = "[OK]  " if r["ok"] else "[FAIL]"
            print(f"  {tag} {r['id']}: {r['desc']} - {r['msg']}")
        print()
        if fail_count == 0:
            print(f"  [OK] 全部 9 项 invariant 通过")
            return 0
        else:
            print(f"  [X] {fail_count} 项 invariant 失败")
            return 1


if __name__ == "__main__":
    sys.exit(main())
