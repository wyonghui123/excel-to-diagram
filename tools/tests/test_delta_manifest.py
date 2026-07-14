"""Tests for manifest_utils.py - MANIFEST 读写/解析/sha256/delta [L17 智能 delta 部署]"""
import pytest
from pathlib import Path

from manifest_utils import (
    Manifest,
    FileEntry,
    parse_manifest,
    generate_manifest,
    compute_delta,
    build_delta_zip,
)

_SHA_A = "a" * 64
_SHA_B = "b" * 64


# ─── Test 1: parse_manifest ───────────────────────────────────────────────

def test_parse_manifest_basic():
    """解析标准 MANIFEST (含 files.entries)"""
    content = f'''version: "v20260714_001"
git:
  head: "abc123"
  branch: "test"
files:
  count: 2
  total_size: 100
  entries:
    - path: "meta/server.py"
      sha256: "{_SHA_A}"
      size: 50
      mode: "0644"
    - path: "meta/datasource.py"
      sha256: "{_SHA_B}"
      size: 50
      mode: "0644"
'''
    m = parse_manifest(content)
    assert m.version == "v20260714_001"
    assert m.git_head == "abc123"
    assert len(m.files) == 2
    assert m.files[0].path == "meta/server.py"


# ─── Test 2: generate_manifest ────────────────────────────────────────────

def test_generate_manifest(tmp_path):
    """扫描目录生成 MANIFEST"""
    # 创建临时目录 + 几个文件
    (tmp_path / "meta").mkdir()
    (tmp_path / "meta" / "server.py").write_text("print('hello')")
    (tmp_path / "MANIFEST").write_text("v1")

    m = generate_manifest(tmp_path, version="v20260714_001")
    assert m.version == "v20260714_001"
    assert len(m.files) >= 2  # 至少 server.py + MANIFEST
    paths = [f.path for f in m.files]
    assert "meta/server.py" in paths


# ─── Test 3: compute_delta ────────────────────────────────────────────────

def test_compute_delta():
    """计算新旧 MANIFEST 的差异 (modified/added/deleted)"""
    old = Manifest(version="v1", git_head="aaa", git_branch="b",
                   files=[
                       FileEntry(path="a.py", sha256="aaa", size=1, mode="0644"),
                       FileEntry(path="b.py", sha256="bbb", size=1, mode="0644"),
                       FileEntry(path="c.py", sha256="ccc", size=1, mode="0644"),
                   ])
    new = Manifest(version="v2", git_head="bbb", git_branch="b",
                   files=[
                       FileEntry(path="a.py", sha256="aaa", size=1, mode="0644"),  # 未变
                       FileEntry(path="b.py", sha256="xxx", size=1, mode="0644"),  # 改了
                       FileEntry(path="d.py", sha256="ddd", size=1, mode="0644"),  # 新增
                       # c.py 删了
                   ])

    delta = compute_delta(old, new)
    assert "a.py" not in delta["modified"]
    assert "b.py" in delta["modified"]
    assert "d.py" in delta["added"]
    assert "c.py" in delta["deleted"]


# ─── Test 4: build_delta_zip ──────────────────────────────────────────────

def test_build_delta_zip(tmp_path):
    """生成 delta zip: 只含 changed files"""
    # 准备源目录 (含多个文件)
    src = tmp_path / "src"
    src.mkdir()
    (src / "meta").mkdir()
    (src / "meta" / "server.py").write_text("server content v1")
    (src / "meta" / "datasource.py").write_text("datasource content v1")
    (src / "frontend").mkdir()
    (src / "frontend" / "index.html").write_text("<html>v1</html>")

    # 旧 MANIFEST (server.py 是 v1)
    old_manifest = generate_manifest(src, version="v1")

    # 修改 server.py 为 v2
    (src / "meta" / "server.py").write_text("server content v2 (CHANGED)")

    # 生成新 MANIFEST + delta zip
    new_manifest = generate_manifest(src, version="v2")
    delta_zip = tmp_path / "delta.zip"

    build_delta_zip(src, old_manifest, new_manifest, delta_zip)

    # 验证 zip 内容
    import zipfile
    with zipfile.ZipFile(delta_zip) as zf:
        names = zf.namelist()
        assert "MANIFEST" in names
        assert "DELETED.txt" in names
        # server.py 应该在 changed/
        changed_files = [n for n in names if n.startswith("changed/")]
        assert any("server.py" in n for n in changed_files)
        # datasource.py 不应该在 changed/ (没改)
        assert not any("datasource.py" in n for n in changed_files)
        # index.html 不应该在 changed/
        assert not any("index.html" in n for n in changed_files)

    # 验证 zip 大小远小于全量 (粗略: < 5KB)
    assert delta_zip.stat().st_size < 5000
