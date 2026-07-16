"""dry_run_smart_extract.py - 本地模拟 L17 smart_extract.sh
[V007.68] 验证逻辑正确性 (Windows 没 bash, 跑不了 .sh)

测试场景:
  1. 生成旧 staging (含 10 个文件, 2KB)
  2. 模拟 V007.50 改动 3 个文件
  3. 用 manifest_utils 算 delta
  4. 模拟 build_delta_zip 生成 zip
  5. 模拟 smart_extract.sh 抽提
  6. 对比 抽提后目标目录跟期望目录
"""
import os
import sys
import shutil
import tempfile
import subprocess
from pathlib import Path

WORKTREE = Path("d:/filework/release-prep-worktree")
TEST_DIR = Path(tempfile.mkdtemp(prefix="l17_dryrun_"))
print(f"[DRY-RUN] 测试目录: {TEST_DIR}")

# 加 tools/ 绝对路径 (避免 'no module' if worktree 根跑 py)
sys.path.insert(0, str(WORKTREE / "tools"))
from manifest_utils import generate_manifest, compute_delta, build_delta_zip, Manifest, parse_manifest

# ========================= 1. 模拟旧 staging =========================
OLD_STAGING = TEST_DIR / "old"
OLD_STAGING.mkdir()
for i in range(10):
    (OLD_STAGING / f"file_{i:02d}.txt").write_text(f"old content {i}\n" * 10)
(OLD_STAGING / "subdir").mkdir()
for i in range(5):
    (OLD_STAGING / "subdir" / f"nested_{i:02d}.txt").write_text(f"old nested {i}\n" * 5)
print(f"[STEP 1] 旧 staging: {OLD_STAGING}")
print(f"  文件数: {sum(1 for _ in OLD_STAGING.rglob('*') if _.is_file())}")

# ========================= 2. 模拟 V007.50 改动 3 个文件 =========================
NEW_STAGING = TEST_DIR / "new"
shutil.copytree(OLD_STAGING, NEW_STAGING)
# 改 3 个文件 + 加 1 个 + 删 1 个
(NEW_STAGING / "file_03.txt").write_text("NEW content 03 (modified)\n" * 15)  # modified
(NEW_STAGING / "file_07.txt").write_text("NEW content 07 (modified)\n" * 12)  # modified
(NEW_STAGING / "subdir" / "nested_02.txt").write_text("NEW nested 02 (modified)\n" * 8)  # modified
(NEW_STAGING / "file_99_new.txt").write_text("brand new file\n")  # added
(NEW_STAGING / "file_05.txt").unlink()  # deleted
print(f"[STEP 2] 新 staging: 改 3 + 加 1 + 删 1")

# ========================= 3. 用 manifest_utils 算 delta =========================
old_manifest = generate_manifest(OLD_STAGING, version="v20260715_001")
new_manifest = generate_manifest(NEW_STAGING, version="v20260716_002", deployment_type="delta")
delta = compute_delta(old_manifest, new_manifest)
print(f"[STEP 3] delta 统计:")
print(f"  modified: {len(delta['modified'])} = {delta['modified']}")
print(f"  added: {len(delta['added'])} = {delta['added']}")
print(f"  deleted: {len(delta['deleted'])} = {delta['deleted']}")
assert set(delta['modified']) == {"file_03.txt", "file_07.txt", "subdir/nested_02.txt"}, "modified 错"
assert set(delta['added']) == {"file_99_new.txt"}, "added 错"
assert set(delta['deleted']) == {"file_05.txt"}, "deleted 错"
print(f"  [OK] delta 正确")

# ========================= 4. build_delta_zip =========================
ZIP_PATH = TEST_DIR / "deploy-v20260716_002.zip"
result = build_delta_zip(NEW_STAGING, old_manifest, new_manifest, ZIP_PATH)
size_kb = ZIP_PATH.stat().st_size / 1024
print(f"[STEP 4] delta zip: {ZIP_PATH.name} ({size_kb:.1f}KB)")
print(f"  zip 含:")
import zipfile
with zipfile.ZipFile(ZIP_PATH) as zf:
    for n in zf.namelist():
        print(f"    {n}")

# ========================= 5. 模拟 smart_extract.sh =========================
print(f"\n[STEP 5] 模拟 smart_extract.sh 抽提 (从旧 staging 出发, 模拟 yonaa 当前状态):")
# 关键: 抽提前先把旧 staging 复制到目标 (模拟 yonaa 已有上次部署的代码)
EXTRACT_TARGET = TEST_DIR / "extracted"
shutil.copytree(OLD_STAGING, EXTRACT_TARGET)
print(f"  [OK] 已把旧 staging 复制到 {EXTRACT_TARGET} (模拟 yonaa 当前代码)")

import zipfile
import yaml

with zipfile.ZipFile(ZIP_PATH) as zf:
    # 读 MANIFEST 判类型
    manifest_text = zf.read("MANIFEST").decode("utf-8")
    manifest_dict = yaml.safe_load(manifest_text)
    print(f"  deployment_type: {manifest_dict.get('deployment_type')}")
    assert manifest_dict.get("deployment_type") == "delta", "应该识别为 delta"

    # 抽 changed/
    CHANGED_ROOT = TEST_DIR / "changed_root"
    if CHANGED_ROOT.exists():
        shutil.rmtree(CHANGED_ROOT)
    CHANGED_ROOT.mkdir()
    zf.extractall(CHANGED_ROOT)
    print(f"  [OK] 抽提到 {CHANGED_ROOT}")

    # 模拟 smart_extract.sh 复制 changed/* 到目标
    CHANGED_SRC = CHANGED_ROOT / "changed"
    applied = 0
    for f in CHANGED_SRC.rglob("*"):
        if f.is_file():
            rel = f.relative_to(CHANGED_SRC)
            dst = EXTRACT_TARGET / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)
            applied += 1
    print(f"  [OK] 覆盖 {applied} 个文件到 {EXTRACT_TARGET}")

    # 处理 DELETED
    deleted_text = zf.read("DELETED.txt").decode("utf-8").strip()
    deleted_count = 0
    for line in deleted_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        dst = EXTRACT_TARGET / line
        if dst.exists():
            dst.unlink()
            deleted_count += 1
    print(f"  [OK] 删 {deleted_count} 个文件 (DELETED.txt)")

# ========================= 6. 验证最终结果 =========================
print(f"\n[STEP 6] 验证:")
print(f"  目标文件列表:")
for f in sorted(EXTRACT_TARGET.rglob("*")):
    if f.is_file():
        rel = f.relative_to(EXTRACT_TARGET)
        # 跟新 staging 对比内容
        new_content = (NEW_STAGING / rel).read_bytes()
        extracted_content = f.read_bytes()
        match = "[OK]" if new_content == extracted_content else "[FAIL]"
        print(f"    {match} {rel}")

# 应该: 改了的 3 个 + 加的 1 个, 删的 1 个没了
expected_files = set()
for f in NEW_STAGING.rglob("*"):
    if f.is_file():
        expected_files.add(str(f.relative_to(NEW_STAGING)).replace(os.sep, "/"))

actual_files = set()
for f in EXTRACT_TARGET.rglob("*"):
    if f.is_file():
        actual_files.add(str(f.relative_to(EXTRACT_TARGET)).replace(os.sep, "/"))

# 抽出 subdir/ 因为空目录可能被 rglob 跳过, 但 NEW_STAGING 的 subdir/ 还在
# 实际只比文件, 目录不参与
missing = expected_files - actual_files
extra = actual_files - expected_files

print(f"\n  expected (新 staging 文件): {len(expected_files)}")
print(f"  actual (抽提后): {len(actual_files)}")
print(f"  missing: {missing}")
print(f"  extra: {extra}")

# 关键断言: 改了的 3 个 + 加的 1 个 = 都在; 删的 1 个 = 不在
must_have = {"file_03.txt", "file_07.txt", "subdir/nested_02.txt", "file_99_new.txt"}
must_not_have = {"file_05.txt"}
ok_have = must_have.issubset(actual_files)
ok_not = not (must_not_have & actual_files)
print(f"  改+加 都在: {ok_have}")
print(f"  删 真的删: {ok_not}")

if ok_have and ok_not and not missing and not extra:
    print(f"\n[OK] L17 dry-run 通过!")
    # 跟全量对比
    FULL_SIZE = sum(f.stat().st_size for f in NEW_STAGING.rglob("*") if f.is_file()) / 1024
    print(f"  跟全量对比:")
    print(f"    全量 zip (估算): {FULL_SIZE:.1f}KB (15 个文件)")
    print(f"    delta zip (实际): {size_kb:.1f}KB (4 个 changed + MANIFEST + CHANGES + DELETED)")
    print(f"    节省: {100*(1-size_kb/FULL_SIZE):.1f}%")
else:
    print(f"\n[FAIL] L17 dry-run 失败")
    sys.exit(1)

# 清理
shutil.rmtree(TEST_DIR)
print(f"\n[CLEAN] 测试目录清理: {TEST_DIR}")
