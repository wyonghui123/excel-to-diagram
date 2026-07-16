"""[L4] check_0.0.0.0_audit.py 单元测试"""
import sys
import json
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from check_listen_bind_audit import scan_file, scan_dir, BIND_PATTERNS, KNOWN_OK


def test_scan_file_flask_run():
    """检测 Flask app.run(host='0.0.0.0')"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("app.run(host='0.0.0.0', port=8081)\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 1
        assert "0.0.0.0" in findings[0]["pattern"]
        assert findings[0]["severity"] == "P0"
    finally:
        path.unlink()


def test_scan_file_tcpserver():
    """检测 TCPServer(('0.0.0.0', ...))"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("httpd = TCPServer(('0.0.0.0', 9101), Handler)\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) >= 1
        assert any("TCPServer" in f["pattern"] for f in findings)
    finally:
        path.unlink()


def test_scan_file_socket_bind():
    """检测 socket.bind(('0.0.0.0', ...))"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("sock.bind(('0.0.0.0', 9200))\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert any("bind" in f["pattern"].lower() for f in findings)
    finally:
        path.unlink()


def test_scan_file_ignores_comments():
    """注释中的 0.0.0.0 不应报警"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("# app.run(host='0.0.0.0', port=8081)\nprint('clean')\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 0
    finally:
        path.unlink()


def test_scan_file_ignores_docstring():
    """docstring 中的 0.0.0.0 不应报警"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write('''"""
This module used to bind 0.0.0.0 but was fixed.
"""
print("clean")
''')
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) == 0
    finally:
        path.unlink()


def test_scan_file_known_ok_excluded():
    """KNOWN_OK 列表中的位置不应报警"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("TCPServer(('0.0.0.0', 9101), Handler)\n")
        path = Path(f.name)
    try:
        # Simulate known path (KNOWN_OK is a set)
        global KNOWN_OK
        original = set(KNOWN_OK)
        KNOWN_OK.clear()
        KNOWN_OK.add(f"{path}:1")
        try:
            findings = scan_file(path)
            assert len(findings) == 0
        finally:
            KNOWN_OK.clear()
            KNOWN_OK.update(original)
    finally:
        path.unlink()


def test_scan_dir_recursive(tmp_path):
    """递归扫描目录"""
    (tmp_path / "good.py").write_text("print('clean')\n")
    (tmp_path / "bad.py").write_text("TCPServer(('0.0.0.0', 8080), Handler)\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.py").write_text("app.run(host='0.0.0.0')\n")

    findings = scan_dir(tmp_path)
    files_with_findings = {f["file"] for f in findings}
    assert any("bad.py" in f for f in files_with_findings)
    assert any("nested.py" in f for f in files_with_findings)
    assert not any("good.py" in f for f in files_with_findings)


def test_scan_dir_excludes_patterns(tmp_path):
    """exclude 模式生效 (test_*.py 现在默认跳过, 用非 test 前缀验证)"""
    (tmp_path / "mock_app.py").write_text("TCPServer(('0.0.0.0', 8080), Handler)\n")
    (tmp_path / "app.py").write_text("TCPServer(('0.0.0.0', 8080), Handler)\n")

    findings_with_exclude = scan_dir(tmp_path, exclude=["mock_"])
    findings_no_exclude = scan_dir(tmp_path)

    assert len(findings_with_exclude) == 1
    assert len(findings_no_exclude) == 2


def test_scan_dir_skips_pycache(tmp_path):
    """__pycache__ 不应扫描"""
    pycache = tmp_path / "__pycache__"
    pycache.mkdir()
    (pycache / "cached.py").write_text("TCPServer(('0.0.0.0', 8080), Handler)\n")

    findings = scan_dir(tmp_path)
    assert all("__pycache__" not in f["file"] for f in findings)


def test_real_tools_audit():
    """实际扫描 tools/ 目录, 验证审计能力"""
    tools_path = Path("tools")
    if not tools_path.exists():
        pytest.skip("tools/ not found (run from project root)")

    findings = scan_dir(tools_path)
    p0_count = sum(1 for f in findings if f.get("severity") == "P0")
    p1_count = sum(1 for f in findings if f.get("severity") == "P1")
    print(f"\nReal audit: P0={p0_count}, P1={p1_count}")
    # 实际: deploy_service.py (1 P0) + mock_remote.sh (1 P0) = 2
    # KNOWN_OK 排除了 log_service/core_service/unified_server
    assert p0_count >= 2, f"expected >=2 P0 findings, got {p0_count}"


def test_nginx_config_detected():
    """检测 nginx 配置中的 0.0.0.0"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
        f.write("server {\n  listen 0.0.0.0:8081;\n}\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) >= 1
        assert any("nginx" in f["pattern"].lower() or "listen" in f["pattern"].lower() for f in findings)
    finally:
        path.unlink()


def test_bash_bind_detected():
    """检测 bash bind 0.0.0.0"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write("#!/bin/bash\nbind 0.0.0.0 8080\n")
        path = Path(f.name)
    try:
        findings = scan_file(path)
        assert len(findings) >= 1
    finally:
        path.unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])