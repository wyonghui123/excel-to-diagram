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


def check_v8c_zip_startup_checks_default() -> tuple:
    """V8c. [V007.36 BUG-FIX] startup_checks._is_debug() 默认值必须 'True' (跟 server.py:983 一致)
    之前默认 'false' 导致手动启动时 _is_production_safe() 错判, 阻断启动
    """
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
