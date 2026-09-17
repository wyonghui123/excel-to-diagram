#!/usr/bin/env python3
'''
pre_deploy_check.py - 部署前自动检查工具 [V007.49-C 2026-07-13]
[L17.2 fix]

背景: 今天多次部署都是先部署再发现问题 (multipart 污染, deploy_bundle drift, etc.)
       部署前 5 秒跑这些检查, 不通过则 abort 部署.

检查项 (按 4 问铁律 / V007.49 系列):
  1. 目标文件 magic number (zip: PK\\x03\\x04, .py: import)
  2. 部署 zip 内必需文件清单 (MANIFEST + 关键 .py)
  3. deploy_bundle/ vs git HEAD 一致性
  4. 关键修复是否包含 (按 commit list 查找 V007.49-B 标记)

用法:
  python tools/pre_deploy_check.py --zip deploy-v*.zip
  exit code: 0=OK, 1=FAIL
'''
import os
import sys
import zipfile
import hashlib
import argparse
import subprocess
from pathlib import Path
from datetime import datetime


# 关键文件 magic number 期望
EXPECTED_MAGIC = {
    '.zip': b'PK\x03\x04',
    '.py': None,  # 不强制 (有 docstring / import / shebang 等)
    '.sh': b'#!/',
    '.json': b'{' if False else None,  # JSON 不一定有 '{'
    '.md': None,
}

# 关键修复标记 (近期 commit) - 至少包含 1 个即通过
REQUIRED_MARKERS = {
    'tools/core_service.py': ['verified_size'],  # V007.49-B 契约
    'tools/rebuild_zip.py': ['META_FILES_TO_SYNC'],  # V007.49-B 自动同步
    'tools/post_deploy_check.py': ['post_deploy_check', 'L1', 'L2', 'L3'],
}

# 关键文件清单 (zip 必须包含)
REQUIRED_FILES = [
    'MANIFEST',
    'tools/core_service.py',
    'tools/rebuild_zip.py',
    'tools/post_deploy_check.py',
    'tools/log_service.py',
]


def check_zip_files(zip_path: str) -> dict:
    """检查 zip 内文件 magic number"""
    result = {"check": "zip_file_magic", "items": [], "ok": 0, "fail": 0}
    with zipfile.ZipFile(zip_path, "r") as z:
        for name in z.namelist():
            ext = os.path.splitext(name)[1]
            if ext not in EXPECTED_MAGIC:
                continue
            expected = EXPECTED_MAGIC[ext]
            if expected is None:
                continue
            try:
                content = z.read(name)
            except Exception:
                continue
            if content.startswith(expected):
                result["ok"] += 1
                result["items"].append({"file": name, "magic": "OK"})
            else:
                result["fail"] += 1
                # 找前 100 字节内容
                result["items"].append({"file": name, "magic": "WRONG",
                                         "expected": expected[:20],
                                         "actual_head": content[:50]})
    result["pass"] = result["fail"] == 0
    return result


def check_required_files(zip_path: str) -> dict:
    """检查 zip 必需文件清单"""
    result = {"check": "required_files", "missing": [], "ok": 0, "fail": 0}
    with zipfile.ZipFile(zip_path, "r") as z:
        names = z.namelist()
        for req in REQUIRED_FILES:
            if req in names:
                result["ok"] += 1
            else:
                result["missing"].append(req)
                result["fail"] += 1
    result["pass"] = result["fail"] == 0
    return result


def check_required_markers(zip_path: str) -> dict:
    """检查关键文件是否含 V007.49-B 标记"""
    result = {"check": "required_markers", "items": [], "ok": 0, "fail": 0}
    with zipfile.ZipFile(zip_path, "r") as z:
        for fname, markers in REQUIRED_MARKERS.items():
            if fname not in z.namelist():
                result["items"].append({"file": fname, "markers": "FILE_MISSING"})
                result["fail"] += 1
                continue
            try:
                content = z.read(fname).decode('utf-8', errors='replace')
            except Exception as e:
                result["items"].append({"file": fname, "err": str(e)})
                result["fail"] += 1
                continue
            missing = [m for m in markers if m not in content]
            if missing:
                result["items"].append({"file": fname, "missing_markers": missing})
                result["fail"] += 1
            else:
                result["items"].append({"file": fname, "markers": "OK"})
                result["ok"] += 1
    result["pass"] = result["fail"] == 0
    return result


def _normalize_lf(content: bytes) -> bytes:
    """Normalize CRLF/CR -> LF, 用于跨平台内容比较"""
    return content.replace(b'\r\n', b'\n').replace(b'\r', b'\n')


def check_deploy_bundle_drift(worktree: str) -> dict:
    """对比 git HEAD vs deploy_bundle/ MD5 (LF 归一化, 避免 CRLF 误报)"""
    result = {"check": "deploy_bundle_drift", "drift": [], "ok": 0, "fail": 0}
    worktree = Path(worktree).resolve()
    deploy_bundle = worktree / "deploy_bundle"
    if not deploy_bundle.exists():
        result["err"] = "deploy_bundle/ not exists"
        result["pass"] = False
        return result
    for rel in ['tools/core_service.py', 'tools/rebuild_zip.py', 'tools/post_deploy_check.py',
                'tools/pre_deploy_check.py', 'meta/core/action_executor.py']:
        head_path = worktree / rel
        bundle_path = deploy_bundle / rel
        if not head_path.exists():
            continue
        if not bundle_path.exists():
            result["drift"].append({"file": rel, "status": "MISSING_IN_BUNDLE"})
            result["fail"] += 1
            continue
        # LF 归一化后比较 (Windows CRLF vs Linux LF)
        head_md5 = hashlib.md5(_normalize_lf(head_path.read_bytes())).hexdigest()
        bundle_md5 = hashlib.md5(_normalize_lf(bundle_path.read_bytes())).hexdigest()
        if head_md5 != bundle_md5:
            result["drift"].append({"file": rel, "head": head_md5[:8],
                                    "bundle": bundle_md5[:8]})
            result["fail"] += 1
        else:
            result["ok"] += 1
    result["pass"] = result["fail"] == 0
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--zip", default="", help="部署 zip 路径")
    p.add_argument("--worktree", default=".", help="git worktree 根目录")
    p.add_argument("--skip-magic", action="store_true")
    p.add_argument("--skip-required", action="store_true")
    p.add_argument("--skip-markers", action="store_true")
    p.add_argument("--skip-drift", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    if not args.zip:
        print("ERROR: --zip required")
        sys.exit(2)

    report = {
        "timestamp": datetime.now().isoformat(),
        "zip": args.zip,
        "worktree": args.worktree,
        "checks": [],
        "summary": {"ok": 0, "fail": 0},
    }

    if not args.skip_magic:
        r = check_zip_files(args.zip)
        report["checks"].append(r)
        report["summary"]["ok"] += r["ok"]
        report["summary"]["fail"] += r["fail"]

    if not args.skip_required:
        r = check_required_files(args.zip)
        report["checks"].append(r)
        report["summary"]["fail"] += r["fail"]

    if not args.skip_markers:
        r = check_required_markers(args.zip)
        report["checks"].append(r)
        report["summary"]["ok"] += r["ok"]
        report["summary"]["fail"] += r["fail"]

    if not args.skip_drift:
        r = check_deploy_bundle_drift(args.worktree)
        report["checks"].append(r)
        report["summary"]["ok"] += r["ok"]
        report["summary"]["fail"] += r["fail"]

    report["pass"] = report["summary"]["fail"] == 0

    if args.json:
        print(__import__("json").dumps(report, indent=2, ensure_ascii=False))
    else:
        print('=' * 70)
        print(f'[PRE-DEPLOY CHECK] {report["timestamp"]}')
        print(f'  zip: {args.zip}')
        print(f'  worktree: {args.worktree}')
        print('=' * 70)
        for c in report["checks"]:
            status = "OK" if c["pass"] else "FAIL"
            print(f'\n[{status}] {c["check"]}  (ok={c.get("ok",0)} fail={c.get("fail",0)})')
            for it in c.get("items", []):
                print(f'  - {it}')
            if c.get("drift"):
                for d in c["drift"]:
                    print(f'  DRIFT: {d}')
            if c.get("missing"):
                for m in c["missing"]:
                    print(f'  MISSING: {m}')
        print()
        print('=' * 70)
        s = report["summary"]
        print(f'[SUMMARY] ok={s["ok"]}  fail={s["fail"]}')
        if report["pass"]:
            print('[OK] 部署可继续')
        else:
            print('[FAIL] 部署必须修复问题')
            print('  建议:')
            print('    1. cd worktree && python deploy_bundle/tools/rebuild_zip.py (重打包)')
            print('    2. python tools/post_deploy_check.py (对账)')
            print('    3. 修复后重跑 pre_deploy_check.py')

    sys.exit(0 if report["pass"] else 1)


if __name__ == "__main__":
    main()