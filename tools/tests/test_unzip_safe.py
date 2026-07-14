"""[L8.6] Magic number 检测 + multipart 头自动剥离"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unzip_safe import detect_magic, auto_strip_multipart, check_file, MAGIC_PATTERNS


# ─── Test 1: detect_magic 各类型 ──────────────────────────────────────

def test_detect_zip_magic():
    """zip 文件 magic number = PK\\x03\\x04"""
    assert detect_magic(b"PK\x03\x04xxxxxx") == "zip"


def test_detect_python_magic():
    """python 文件 magic = \"\"\" 或 import/from"""
    assert detect_magic(b'"""docstring"""') == "python"
    assert detect_magic(b"import os") == "python"
    assert detect_magic(b"from sys import") == "python"


def test_detect_shell_magic():
    """shell 文件 magic = #!/bin/bash"""
    assert detect_magic(b"#!/bin/bash\necho hi") == "shell"
    assert detect_magic(b"#!/usr/bin/env bash") == "shell"


def test_detect_unknown():
    """未知 magic 应返回 unknown"""
    assert detect_magic(b"\x00\x01\x02\x03random bytes") == "unknown"


def test_detect_gzip_magic():
    """gzip magic = \\x1f\\x8b\\x08"""
    assert detect_magic(b"\x1f\x8b\x08\x00xxxx") == "gzip"


# ─── Test 2: auto_strip_multipart ──────────────────────────────────────

def test_auto_strip_multipart_basic():
    """自动剥离 multipart 头污染"""
    polluted = (b'--CoreUploadBoundary777\r\n'
                b'Content-Disposition: form-data; name="file"; filename="x.py"\r\n'
                b'\r\n'
                b'import os\nprint("hello")\r\n'
                b'--CoreUploadBoundary777--\r\n')
    clean = auto_strip_multipart(polluted)
    assert clean == b'import os\nprint("hello")'


def test_auto_strip_multipart_no_boundary():
    """无 multipart 边界时返回原数据"""
    data = b'import os\nprint("hi")'
    assert auto_strip_multipart(data) == data


def test_auto_strip_multipart_multiple_parts():
    """多个 part 时选最长的"""
    polluted = (b'--BoundaryABC\r\n'
                b'Content-Type: text/plain\r\n'
                b'\r\n'
                b'short\r\n'
                b'--BoundaryABC\r\n'
                b'Content-Type: text/plain\r\n'
                b'\r\n'
                b'this is the longer python content here\r\n'
                b'--BoundaryABC--\r\n')
    clean = auto_strip_multipart(polluted)
    assert b"longer python content" in clean


# ─── Test 3: check_file 集成检测 ──────────────────────────────────────

def test_check_file_clean(tmp_path):
    """干净文件 is_polluted=False"""
    f = tmp_path / "test.py"
    f.write_bytes(b'import os\nprint("hi")')
    r = check_file(f)
    assert r["is_polluted"] is False
    assert r["cleaned_type"] == "python"


def test_check_file_polluted(tmp_path):
    """multipart 污染文件 is_polluted=True"""
    f = tmp_path / "polluted.py"
    polluted = (b'--Boundary123\r\n'
                b'Content-Disposition: form-data; name="f"\r\n'
                b'\r\n'
                b'import os\nprint("hi")\r\n'
                b'--Boundary123--\r\n')
    f.write_bytes(polluted)
    r = check_file(f)
    assert r["is_polluted"] is True
    assert r["cleaned_type"] == "python"
    assert r["original_type"] in ("unknown",)


def test_check_file_missing(tmp_path):
    """不存在的文件返回 error"""
    r = check_file(tmp_path / "nope.py")
    assert "error" in r


def test_magic_patterns_completeness():
    """至少覆盖 6 种常见类型"""
    names = {name for name, _ in MAGIC_PATTERNS}
    assert {"zip", "gzip", "python", "shell"}.issubset(names)