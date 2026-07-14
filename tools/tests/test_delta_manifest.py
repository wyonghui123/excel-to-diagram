"""Tests for manifest_utils.py - MANIFEST 读写/解析/sha256/delta [L17 智能 delta 部署]"""
import pytest
from pathlib import Path

from manifest_utils import (
    Manifest,
    FileEntry,
    parse_manifest,
    generate_manifest,
    compute_delta,
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
