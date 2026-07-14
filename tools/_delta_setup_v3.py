"""[V3] delta deploy E2E 测试 v3 (Python API 而非 CLI) [V007.67]
用 manifest_utils 的 Python API 直接跑
"""
#!/opt/miniconda3-py39/bin/python3
import sys
from pathlib import Path

sys.path.insert(0, "/tmp/delta_test")  # import /tmp/delta_test/manifest_utils.py
from manifest_utils import (
    generate_manifest,
    compute_delta,
    build_delta_zip,
    parse_manifest,
)
import json
import shutil
import tarfile
import subprocess
import os

ROOT = Path("/tmp/delta_test")
PYTHON_BIN = "/opt/miniconda3-py39/bin/python3"

print("=" * 70)
print(f" E2E delta deploy v3 (Python API) using {PYTHON_BIN}")
print("=" * 70)

# Step 1: 清理 + 创建 v1 (50 文件) + v2 (52 文件)
print("\n=== STEP 1: create v1 + v2 ===")
shutil.rmtree(ROOT / "v1", ignore_errors=True)
shutil.rmtree(ROOT / "v2", ignore_errors=True)
shutil.rmtree(ROOT / "target", ignore_errors=True)
for f in [ROOT / "full.tar.gz", ROOT / "delta.zip", ROOT / "v1_manifest.json",
          ROOT / "v2_manifest.json", ROOT / "delta.json"]:
    if f.exists():
        f.unlink()
(ROOT / "v1/api").mkdir(parents=True)
(ROOT / "v1/core").mkdir(parents=True)
(ROOT / "v1/utils").mkdir(parents=True)
(ROOT / "v2/api").mkdir(parents=True)
(ROOT / "v2/core").mkdir(parents=True)
(ROOT / "v2/utils").mkdir(parents=True)

# v1 - 50 files
for i in range(1, 21):
    (ROOT / f"v1/api/api_{i}.py").write_text(f'def api{i}(): return {{"v": 1, "id": {i}}}')
for i in range(1, 21):
    (ROOT / f"v1/core/core_{i}.py").write_text(f"class Core{i}:\n    v=1\n    id={i}\n")
for i in range(1, 11):
    (ROOT / f"v1/utils/util_{i}.py").write_text(f"# utils {i}\nVALUE_{i}=1\n")

# v2 = v1 + 5 modify + 2 add
for src in (ROOT / "v1").rglob("*"):
    if src.is_file():
        rel = src.relative_to(ROOT / "v1")
        dst = ROOT / "v2" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
(ROOT / "v2/api/api_1.py").write_text('def api1(): return {"v": 2, "id": 1, "new": True}')
(ROOT / "v2/api/api_5.py").write_text('def api5(): return {"v": 2, "id": 5, "new": True}')
(ROOT / "v2/api/api_10.py").write_text('def api10(): return {"v": 2, "id": 10, "new": True}')
(ROOT / "v2/core/core_3.py").write_text("class Core3:\n    v=2\n    id=3\n    NEW=True\n")
(ROOT / "v2/core/core_15.py").write_text("class Core15:\n    v=2\n    id=15\n    NEW=True\n")
(ROOT / "v2/api/api_new_1.py").write_text('def api_new1(): return {"v": 2, "new": True}')
(ROOT / "v2/api/api_new_2.py").write_text('def api_new2(): return {"v": 2, "new": True}')

v1_count = sum(1 for _ in (ROOT / "v1").rglob("*") if _.is_file())
v2_count = sum(1 for _ in (ROOT / "v2").rglob("*") if _.is_file())
print(f"v1 files: {v1_count}")
print(f"v2 files: {v2_count}")

# Step 2: full.tar.gz
print("\n=== STEP 2: full.tar.gz ===")
with tarfile.open(ROOT / "full.tar.gz", "w:gz") as tar:
    tar.add(ROOT / "v1", arcname=".")
print(f"full.tar.gz: {(ROOT / 'full.tar.gz').stat().st_size} bytes")

# Step 3: generate_manifest
print("\n=== STEP 3: generate_manifest ===")
m_v1 = generate_manifest(ROOT / "v1", version="v1", deployment_type="full")
m_v2 = generate_manifest(ROOT / "v2", version="v2", deployment_type="full")

# 写 JSON 备用
v1_json = ROOT / "v1_manifest.json"
v2_json = ROOT / "v2_manifest.json"
with open(v1_json, "w") as f:
    json.dump({"version": m_v1.version, "deployment_type": m_v1.deployment_type,
               "files": [{"path": e.path, "sha256": e.sha256, "size": e.size} for e in m_v1.files]}, f)
with open(v2_json, "w") as f:
    json.dump({"version": m_v2.version, "deployment_type": m_v2.deployment_type,
               "files": [{"path": e.path, "sha256": e.sha256, "size": e.size} for e in m_v2.files]}, f)
print(f"v1 manifest: {len(m_v1.files)} files, saved to {v1_json} ({v1_json.stat().st_size} bytes)")
print(f"v2 manifest: {len(m_v2.files)} files, saved to {v2_json} ({v2_json.stat().st_size} bytes)")

# Step 4: compute_delta
print("\n=== STEP 4: compute_delta ===")
delta = compute_delta(m_v1, m_v2)
delta_path = ROOT / "delta.json"
with open(delta_path, "w") as f:
    json.dump(delta, f, indent=2)
print(f"delta: modified={len(delta['modified'])} added={len(delta['added'])} deleted={len(delta['deleted'])}")
print(f"modified: {delta['modified']}")
print(f"added: {delta['added']}")
print(f"saved to {delta_path} ({delta_path.stat().st_size} bytes)")

# Step 5: build_delta_zip
print("\n=== STEP 5: build_delta_zip ===")
result = build_delta_zip(
    src_dir=ROOT / "v2",
    old_manifest=m_v1,
    new_manifest=m_v2,
    output_zip=ROOT / "delta.zip"
)
print(f"build_delta_zip: {result}")

# Step 6: 大小对比
print("\n=== STEP 6: 大小对比 ===")
full_size = (ROOT / "full.tar.gz").stat().st_size
delta_size = (ROOT / "delta.zip").stat().st_size
ratio = delta_size * 100 / full_size
print(f"full.tar.gz = {full_size} bytes")
print(f"delta.zip   = {delta_size} bytes")
print(f"压缩比      = {ratio:.2f}% (delta 是 full 的 {ratio:.2f}%)")

# Step 7: delta.zip 内部结构
print("\n=== STEP 7: delta.zip 内部 ===")
import zipfile
with zipfile.ZipFile(ROOT / "delta.zip") as zf:
    for name in zf.namelist():
        info = zf.getinfo(name)
        print(f"  {name} ({info.file_size} bytes)")

# Step 8: smart_extract 模拟
print("\n=== STEP 8: smart_extract (用 Python 替代 shell source) ===")
# 直接用 zipfile 解压 delta.zip 到 target
target = ROOT / "target"
shutil.rmtree(target, ignore_errors=True)
target.mkdir()
with zipfile.ZipFile(ROOT / "delta.zip") as zf:
    zf.extractall(target)
n = sum(1 for _ in target.rglob("*") if _.is_file())
print(f"target files after extract: {n}")
for p in sorted(target.rglob("*"))[:20]:
    if p.is_file():
        print(f"  {p.relative_to(target)}")

# Step 9: sha256 验证
print("\n=== STEP 9: sha256 api_1.py ===")
import hashlib
def sha256(p):
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()

v2_h = sha256(ROOT / "v2/api/api_1.py")
tgt_h = sha256(target / "changed/api/api_1.py")
print(f"v2:     {v2_h}")
print(f"target: {tgt_h}")
print(f"MATCH" if v2_h == tgt_h else "MISMATCH")

# Step 10: 新文件验证
print("\n=== STEP 10: 新文件验证 ===")
new_file = target / "changed/api/api_new_1.py"
if new_file.exists():
    new_h = sha256(new_file)
    v2_new_h = sha256(ROOT / "v2/api/api_new_1.py")
    if new_h == v2_new_h:
        print(f"target/changed/api/api_new_1.py 存在 + 内容一致")
    else:
        print(f"内容不一致")
else:
    print(f"target/changed/api/api_new_1.py 不存在")

print("\n=== DONE ===")
