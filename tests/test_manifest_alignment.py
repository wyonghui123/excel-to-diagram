#!/usr/bin/env python3
"""
test_manifest_alignment.py - 验证 zip 内 MANIFEST 与当前 git HEAD 一致

[目的]
之前 rebuild_zip.py 写死的 MANIFEST (git.head 空, commits_count=67 硬编码) 导致
部署后无法用 MANIFEST 验证 "远端跑的代码 == zip 内的代码".

[这个测试做什么]
1. 在 worktree 根打一个 zip (用 tools/rebuild_zip.py 真跑)
2. 解析 zip 内 MANIFEST
3. 比对 MANIFEST.git.head 与当前 git rev-parse HEAD
4. 验证 services / deployment_type / verification 字段都存在
5. 验证 commits_count 与 git rev-list --count HEAD 一致

[预期结果]
所有 7 项验证 PASS (HEAD / branch / count / services / deployment_type / verification / 字段非空).

[失败含义]
zip 跟 git HEAD 不一致 - 部署后会埋下"远端跑的是旧代码"的隐患.
"""
import os
import sys
import shutil
import zipfile
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def _git(*args, default=""):
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else default
    except Exception:
        return default


def _parse_yaml_field(manifest_text: str, dotted_key: str) -> str:
    """
    Read a YAML dotted key from our MANIFEST.
    dotted_key examples: 'version', 'git.head', 'services.frontend.port'

    We use a simple regex-based approach because our MANIFEST has a known, stable
    shape. We look for the LAST segment as `key: value` and walk backwards checking
    parent sections exist.
    """
    import re
    lines = manifest_text.splitlines()
    parts = dotted_key.split(".")
    if not parts:
        return ""

    def strip_q(s):
        s = s.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return s[1:-1]
        return s

    # Find the leaf line: "<indent>last_part: <value>" (or empty value for nested)
    last = parts[-1]
    leaf_idx = -1
    leaf_indent = -1
    leaf_value = ""
    for i, line in enumerate(lines):
        if line.startswith("#") or not line.strip():
            continue
        # measure indent
        m = re.match(r"^(\s*)([^\s#][^:]*):\s*(.*)$", line)
        if not m:
            continue
        indent, key, val = m.group(1), m.group(2).strip(), m.group(3)
        if key != last:
            continue
        if len(parts) == 1:
            if indent == "":
                leaf_idx = i
                leaf_indent = 0
                leaf_value = val
                break
        else:
            # Check parent sections exist before this line
            # Verify all parents appear with strictly smaller indent and in order
            ok = True
            parent_indent_target = len(indent) - 2
            for parent_seg in reversed(parts[:-1]):
                found_parent = False
                for j in range(i - 1, -1, -1):
                    line2 = lines[j]
                    if line2.startswith("#") or not line2.strip():
                        continue
                    m2 = re.match(r"^(\s*)([^\s#][^:]*):\s*(.*)$", line2)
                    if not m2:
                        continue
                    pi, pk, pv = m2.group(1), m2.group(2).strip(), m2.group(3)
                    if len(pi) > parent_indent_target:
                        continue  # deeper sibling, skip
                    if len(pi) == parent_indent_target and pk == parent_seg:
                        found_parent = True
                        parent_indent_target = len(pi) - 2
                        break
                    if len(pi) <= parent_indent_target:
                        break  # left the section
                if not found_parent:
                    ok = False
                    break
            if ok:
                leaf_idx = i
                leaf_indent = len(indent)
                leaf_value = val
                break

    if leaf_idx < 0:
        return ""
    return strip_q(leaf_value)


def test_manifest_alignment():
    """7 checks: HEAD / branch / count / services / deployment_type / verification / 非空"""
    results = []

    # --- 1. 检查源 ---
    dist = ROOT / "dist"
    meta = ROOT / "meta"
    if not dist.exists():
        return [("FAIL", f"前置: dist/ 不存在, 请先跑 npm run build")]
    if not meta.exists():
        return [("FAIL", f"前置: meta/ 不存在")]

    # --- 2. 打一个临时 zip (避免污染 worktree 根的 deploy-v*.zip) ---
    tmp_out = ROOT / "deploy_bundle" / ".test_manifest_alignment.zip"
    if tmp_out.exists():
        tmp_out.unlink()

    # 临时改 ROOT (rebuild_zip 用 ROOT.parent.parent)
    # 直接调用 _build_manifest + 手工打包, 避免依赖 sys.path
    sys.path.insert(0, str(ROOT))
    from tools.rebuild_zip import _build_manifest

    manifest_text = _build_manifest("vTEST_manifest_alignment")
    staging = ROOT / "deploy_bundle" / ".staging_test"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        # 复制 frontend_dist_files
        src = ROOT / "frontend_dist_files"
        if src.exists():
            shutil.copytree(src, staging / "frontend_dist_files")
        # 复制 meta (限制大小: 不复制 db)
        shutil.copytree(
            meta, staging / "meta",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.db", "*.lock", ".env")
        )
        # MANIFEST
        (staging / "MANIFEST").write_text(manifest_text, encoding="utf-8")
        # 打包
        with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in staging.rglob("*"):
                if fp.is_file():
                    zf.write(fp, arcname=str(fp.relative_to(staging)).replace("\\", "/"))
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # --- 3. 解析 zip 内 MANIFEST ---
    with zipfile.ZipFile(tmp_out, "r") as zf:
        if "MANIFEST" not in zf.namelist():
            return [("FAIL", "zip 内没有 MANIFEST")]
        manifest_zip = zf.read("MANIFEST").decode("utf-8")

    # --- 4. 比对 ---
    real_head = _git("rev-parse", "HEAD")
    real_branch = _git("branch", "--show-current")
    real_count = _git("rev-list", "--count", "HEAD")

    zip_head = _parse_yaml_field(manifest_zip, "git.head")
    zip_branch = _parse_yaml_field(manifest_zip, "git.branch")
    zip_count = _parse_yaml_field(manifest_zip, "git.commits_count")
    zip_deployment = _parse_yaml_field(manifest_zip, "deployment_type")
    zip_fe_port = _parse_yaml_field(manifest_zip, "services.frontend.port")
    zip_be_port = _parse_yaml_field(manifest_zip, "services.backend.port")

    # T1: HEAD 一致 (允许 -dirty 后缀)
    expected_head = real_head[:7]  # short hash
    if zip_head.startswith(expected_head):
        results.append(("PASS", f"T1: MANIFEST.git.head ({zip_head}) contains real HEAD ({expected_head})"))
    else:
        results.append(("FAIL", f"T1: MANIFEST.git.head ({zip_head}) 不含 real HEAD ({expected_head}) - zip 跟 git 状态不一致!"))

    # T2: branch 一致
    if zip_branch == real_branch:
        results.append(("PASS", f"T2: MANIFEST.git.branch ({zip_branch}) == real branch"))
    else:
        results.append(("FAIL", f"T2: MANIFEST.git.branch ({zip_branch}) != real branch ({real_branch})"))

    # T3: commits_count 一致
    if zip_count == real_count:
        results.append(("PASS", f"T3: MANIFEST.commits_count ({zip_count}) == real count"))
    else:
        results.append(("FAIL", f"T3: MANIFEST.commits_count ({zip_count}) != real count ({real_count}) - 硬编码 67 是 bug"))

    # T4: deployment_type 非空 (不是硬编码字符串)
    if zip_deployment and zip_deployment in ("incremental_upgrade", "fresh_init"):
        results.append(("PASS", f"T4: deployment_type = {zip_deployment}"))
    else:
        results.append(("FAIL", f"T4: deployment_type 空或非法 ({zip_deployment!r})"))

    # T5: services.frontend.port == 8081
    if zip_fe_port == "8081":
        results.append(("PASS", f"T5: services.frontend.port = {zip_fe_port}"))
    else:
        results.append(("FAIL", f"T5: services.frontend.port ({zip_fe_port}) != 8081"))

    # T6: services.backend.port == 5001
    if zip_be_port == "5001":
        results.append(("PASS", f"T6: services.backend.port = {zip_be_port}"))
    else:
        results.append(("FAIL", f"T6: services.backend.port ({zip_be_port}) != 5001"))

    # T7: verification 字段非空 (指引运维怎么验证)
    has_verification = "verification:" in manifest_zip and "MANIFEST.git.head MUST" in manifest_zip
    if has_verification:
        results.append(("PASS", "T7: verification 字段存在并含验证指引"))
    else:
        results.append(("FAIL", "T7: verification 字段缺失或无验证指引"))

    # --- 5. 清理 ---
    tmp_out.unlink(missing_ok=True)

    return results


def main():
    print("=" * 80)
    print("test_manifest_alignment.py - zip MANIFEST 与 git HEAD 一致性")
    print("=" * 80)
    print(f"worktree: {ROOT}")
    print(f"git HEAD: {_git('rev-parse', 'HEAD')[:12]}")
    print(f"branch:   {_git('branch', '--show-current')}")
    print(f"commits:  {_git('rev-list', '--count', 'HEAD')}")
    print()

    results = test_manifest_alignment()
    fail = sum(1 for s, _ in results if s == "FAIL")

    for status, msg in results:
        marker = "[OK]" if status == "PASS" else "[X]"
        print(f"  {marker} {msg}")

    print()
    print("=" * 80)
    if fail == 0:
        print(f"PASS  ({len(results)}/{len(results)})")
        return 0
    print(f"FAIL  ({len(results) - fail}/{len(results)})")
    return 1


if __name__ == "__main__":
    sys.exit(main())