"""[V3] run_security_audit.py 单元测试"""
import sys
import json
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from run_security_audit import (
    run_all_audits,
    print_report,
    _count_severity,
    L6_SERVICE_SECURITY,
)


def test_run_all_audits_empty_paths():
    """空路径列表不应 crash"""
    results = run_all_audits(["/nonexistent/path"])
    assert "L4_listen_bind" in results["audits"]
    assert "L7_credential_leak" in results["audits"]
    assert "L2_L5_unsafe_patterns" in results["audits"]
    assert results["total_findings"] == 0


def test_run_all_audits_finds_issues(tmp_path):
    """实际发现 P0/P1 issues"""
    (tmp_path / "bad.py").write_text("open('/tmp/x.py','w').write(base64.b64decode('x'))\n")
    (tmp_path / "creds.md").write_text("login admin / Admin@2026!Init\n")
    (tmp_path / "listen.py").write_text("TCPServer(('0.0.0.0', 8080), Handler)\n")

    results = run_all_audits([str(tmp_path)])

    assert results["audits"]["L4_listen_bind"]["by_severity"]["P0"] >= 1
    assert results["audits"]["L7_credential_leak"]["by_severity"]["P0"] >= 1
    assert results["audits"]["L2_L5_unsafe_patterns"]["count"] >= 1


def test_count_severity():
    """_count_severity 正确统计"""
    findings = [
        {"severity": "P0"},
        {"severity": "P0"},
        {"severity": "P1"},
        {"severity": "P2"},
        {"severity": "??"},  # unknown
    ]
    by_sev = _count_severity(findings)
    assert by_sev["P0"] == 2
    assert by_sev["P1"] == 1
    assert by_sev["P2"] == 1


def test_l6_security_config():
    """L6 服务端口安全配置完整"""
    assert "9101 (log_service)" in L6_SERVICE_SECURITY
    assert "9204 (dbops_service)" in L6_SERVICE_SECURITY
    # 9204 应该标为 P0 (DB 直写)
    assert "P0" in L6_SERVICE_SECURITY["9204 (dbops_service)"]["priority"]


def test_results_have_timestamp():
    """结果含时间戳"""
    results = run_all_audits([])
    assert "timestamp" in results
    assert "duration_sec" in results
    assert results["duration_sec"] >= 0


def test_print_report_doesnt_crash(tmp_path, capsys):
    """print_report 不应 crash"""
    (tmp_path / "test.py").write_text("print('hello')\n")
    results = run_all_audits([str(tmp_path)])
    print_report(results)
    captured = capsys.readouterr()
    assert "远程执行 + 安全审计报告" in captured.out
    assert "[L4]" in captured.out
    assert "[L7]" in captured.out
    assert "[L2+L5]" in captured.out
    assert "[L6]" in captured.out


def test_results_json_serializable(tmp_path):
    """结果可 JSON 序列化"""
    (tmp_path / "test.py").write_text("print('hi')\n")
    results = run_all_audits([str(tmp_path)])
    json_str = json.dumps(results, ensure_ascii=False)
    assert "L4_listen_bind" in json_str


def test_cli_runs_via_main(tmp_path):
    """命令行入口可运行"""
    import subprocess
    project_root = Path(__file__).resolve().parent.parent.parent
    # Use project root (has tools/, docs/) instead of tmp_path to avoid path not found
    result = subprocess.run(
        [sys.executable, "tools/run_security_audit.py",
         "--paths", "tools/",
         "--json"],
        capture_output=True,
        text=True,
        cwd=str(project_root),
    )
    # 应该 JSON 输出, exit 0 或 1 (有 P0)
    assert result.returncode in (0, 1), f"unexpected exit {result.returncode}: {result.stderr}"
    data = json.loads(result.stdout)
    assert "audits" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])