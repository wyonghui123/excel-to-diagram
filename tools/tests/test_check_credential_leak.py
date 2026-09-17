"""[L7] check_credential_leak.py 单元测试"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from check_credential_leak import scan_file, scan_dir, KNOWN_BANNED_PASSWORDS


def test_detects_banned_password():
    """检测已知封禁密码"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('PASSWORD = "Admin@2026!Init"\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) >= 1
        assert any("Admin@2026" in f.get("pattern", "") for f in findings)
    finally:
        path.unlink()


def test_detects_generic_password():
    """检测通用 password = "xxx" 模式"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('db_password = "superSecret123"\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("hardcoded credential" in f.get("pattern", "").lower() for f in findings)
    finally:
        path.unlink()


def test_detects_sshpass():
    """检测 sshpass -p (命令行密码泄漏)"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write('sshpass -p MySecret123 ssh root@host\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("sshpass" in f.get("pattern", "").lower() for f in findings)
    finally:
        path.unlink()


def test_detects_doc_login():
    """检测文档 'admin / Admin@...' 字面密码"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("Browser login admin / Admin@2026!Init\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("docs" in f.get("pattern", "").lower() or "admin" in f.get("pattern", "") for f in findings)
    finally:
        path.unlink()


def test_detects_echo_password():
    """检测 echo PASSWORD=... (环境变量泄漏)"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write('echo "SERVER_PASSWORD=Admin@2026!Init" >> /tmp/.env\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("echo" in f.get("pattern", "").lower() for f in findings)
    finally:
        path.unlink()


def test_ignores_getpass():
    """getpass.getpass 应豁免"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('pwd = getpass.getpass("Password: ")\n')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        # getpass 字符串不应触发
        assert len(findings) == 0
    finally:
        path.unlink()


def test_ignores_placeholder():
    """占位符 <PASSWORD from vault> 应豁免"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("login admin / <PASSWORD from vault>\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 0
    finally:
        path.unlink()


def test_ignores_docstring():
    """docstring 中提及密码模式应豁免"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('''"""
This module used to hardcode PASSWORD = "Admin@2026!Init" but was fixed.
"""
import getpass
pwd = getpass.getpass()
''')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        # docstring 中的字面密码应被豁免
        assert len(findings) == 0
    finally:
        path.unlink()


def test_ignores_meta_description():
    """元描述 (讨论密码修复方法) 应豁免"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write("应改 password 为 <PASSWORD from vault>\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 0
    finally:
        path.unlink()


def test_scan_dir_recursive(tmp_path):
    """递归扫描"""
    (tmp_path / "ok.py").write_text('pwd = getpass.getpass()\n')
    (tmp_path / "bad.py").write_text('PASSWORD = "Admin@2026!Init"\n')
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.sh").write_text('sshpass -p Secret123 ssh root@host\n')

    findings = scan_dir(tmp_path)
    files = {f["file"] for f in findings}
    assert any("bad.py" in f for f in files)
    assert any("nested.sh" in f for f in files)
    assert not any("ok.py" in f for f in files)


def test_scan_dir_skips_pycache(tmp_path):
    """__pycache__ 不应扫描"""
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.py").write_text('PASSWORD = "Admin@2026!Init"\n')

    findings = scan_dir(tmp_path)
    assert all("__pycache__" not in f["file"] for f in findings)


def test_real_docs_audit():
    """实际扫描 docs/ 目录 (应有大量泄漏, 需要脱敏)"""
    docs_path = Path("docs")
    if not docs_path.exists():
        pytest.skip("docs/ not found")

    findings = scan_dir(docs_path)
    p0_count = sum(1 for f in findings if f.get("severity") == "P0")
    p1_count = sum(1 for f in findings if f.get("severity") == "P1")
    print(f"\nReal audit: P0={p0_count}, P1={p1_count}")
    # docs/DEPLOY-CHEATSHEET-*.txt 应该有 ~5+ P0 命中
    assert p0_count >= 5, f"expected >=5 P0 findings, got {p0_count}"


def test_no_self_match():
    """check_credential_leak.py 自身不应被检测"""
    findings = scan_file(Path("tools/check_credential_leak.py"))
    # 脚本自身的 KNOWN_BANNED_PASSWORDS 列表不应触发 (因为它在 docstring/列表中)
    # 实际检查: 严重泄漏 (P0) 应为 0
    p0 = [f for f in findings if f.get("severity") == "P0"]
    assert len(p0) == 0, f"self-match detected: {[f['pattern'] for f in p0]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])