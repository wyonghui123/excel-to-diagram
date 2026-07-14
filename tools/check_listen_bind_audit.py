"""check_0.0.0.0_audit.py - 静态扫描 0.0.0.0 绑定 (L4 禁止外网穿透)
[V007.67 2026-07-14]

依据 .trae/rules/remote-execution-simplicity.md (V3) L4:
  任何让远端服务器可被公网直接访问的方式都禁止.
  0.0.0.0 绑定 = 所有网卡都监听 = 内网隔离失效

用法:
  python check_0.0.0.0_audit.py <path>...
  python check_0.0.0.0_audit.py tools/  deploy_bundle/
  python check_0.0.0.0_audit.py tools/  --json
  python check_0.0.0.0_audit.py tools/  --exclude test_*.py

输出:
  - 文件:行
  - 风险等级 (P0 必修 / P1 强烈建议 / P2 内网可接受)
  - 建议改法
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict


# 0.0.0.0 绑定的不同模式
BIND_PATTERNS = [
    # Python Flask/Django
    (re.compile(r"\.run\s*\(\s*host\s*=\s*['\"]0\.0\.0\.0['\"]"),
     "Flask app.run(host='0.0.0.0')",
     "P0",
     "改 host='127.0.0.1' 或内网 IP"),
    (re.compile(r"\.run\s*\(\s*['\"]0\.0\.0\.0['\"]"),
     "Flask app.run('0.0.0.0', port=...)",
     "P0",
     "改 '127.0.0.1' 或内网 IP"),
    # Python http.server
    (re.compile(r"HTTPServer\s*\(\s*\(\s*['\"]0\.0\.0\.0['\"]"),
     "HTTPServer(('0.0.0.0', port), Handler)",
     "P0",
     "改 '127.0.0.1' 或 '172.20.59.7'"),
    # Python socketserver
    (re.compile(r"\.server_bind\s*\(\s*['\"]0\.0\.0\.0['\"]"),
     "socketserver server_bind '0.0.0.0'",
     "P0",
     "改 '127.0.0.1'"),
    # Python socket
    (re.compile(r"\.bind\s*\(\s*\(\s*['\"]0\.0\.0\.0['\"]"),
     "socket.bind(('0.0.0.0', port))",
     "P0",
     "改 ('127.0.0.1', port)"),
    # TCPServer
    (re.compile(r"TCPServer\s*\(\s*\(\s*['\"]0\.0\.0\.0['\"]"),
     "TCPServer(('0.0.0.0', port), Handler)",
     "P0",
     "改 '127.0.0.1'"),
    # Bash / sh
    (re.compile(r"\bbind\s+0\.0\.0\.0"),
     "shell bind 0.0.0.0",
     "P1",
     "用内网 IP 或 127.0.0.1"),
    (re.compile(r"(?:^|[\s=&|])listen\s*=\s*0\.0\.0\.0", re.IGNORECASE),
     "shell listen=0.0.0.0",
     "P1",
     "用内网 IP"),
    # nginx / config (require leading whitespace or start-of-line)
    (re.compile(r"^\s*listen\s+0\.0\.0\.0", re.MULTILINE),
     "nginx/apache listen 0.0.0.0",
     "P1",
     "用 listen 127.0.0.1 或内网 IP"),
    # Java
    (re.compile(r"InetAddress\.getByName\s*\(\s*[\"']0\.0\.0\.0"),
     "Java InetAddress.getByName('0.0.0.0')",
     "P0",
     "用 127.0.0.1"),
    # Node.js
    (re.compile(r"\.listen\s*\(\s*[^,)]*,\s*['\"]0\.0\.0\.0"),
     "Node.js listen(port, '0.0.0.0')",
     "P0",
     "用 '127.0.0.1'"),
]


# 已知合规例外 (内网监听 / 测试模式) - 不报警
KNOWN_OK = {
    "tools/log_service.py:9101",  # 内网必须
    "tools/core_service.py:9200",  # 内网必须
    "deploy_bundle/unified_server.py:8081",  # 浏览器入口 (CORS 限定)
    "tools/mock_remote.sh:163",  # mock 脚本, 不部署
}


def scan_file(path: Path) -> List[Dict]:
    """扫描单个文件, 返回所有发现的 0.0.0.0 绑定"""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [{"file": str(path), "error": str(e)}]

    lines = text.split("\n")
    in_docstring = False
    in_block_comment = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments and docstrings
        if '"""' in line or "'''" in line:
            in_docstring = not in_docstring
            continue
        if in_docstring or stripped.startswith("#"):
            continue

        for pattern, desc, severity, fix in BIND_PATTERNS:
            if pattern.search(line):
                key = f"{path}:{i}"
                if key in KNOWN_OK:
                    continue
                findings.append({
                    "file": str(path),
                    "line": i,
                    "pattern": desc,
                    "severity": severity,
                    "fix": fix,
                    "code": line.strip()[:200],
                })
    return findings


def scan_dir(root: Path, exclude: List[str] = None) -> List[Dict]:
    """递归扫描目录"""
    exclude = exclude or []
    findings = []
    if root.is_file():
        return scan_file(root)

    for f in root.rglob("*"):
        if not f.is_file():
            continue
        # Skip non-code files
        if f.suffix not in (".py", ".sh", ".js", ".ts", ".conf", ".ini", ".yaml", ".yml"):
            continue
        # Skip excluded patterns (match against filename only, not full path)
        if any(ex in f.name for ex in exclude):
            continue
        # Skip hidden / cache
        if any(part.startswith(".") for part in f.parts):
            continue
        if "__pycache__" in f.parts:
            continue
        # Skip self (避免正则描述符自我匹配)
        if f.name == "check_listen_bind_audit.py":
            continue
        # Skip test files (含示例代码)
        if f.name.startswith("test_") and f.suffix == ".py":
            continue
        findings.extend(scan_file(f))
    return findings


def main():
    parser = argparse.ArgumentParser(description="Static scan 0.0.0.0 bind (L4 审计)")
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument("--exclude", nargs="*", default=[], help="Path patterns to exclude")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--strict", action="store_true", help="P1 也算失败")
    args = parser.parse_args()

    all_findings = []
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            print(f"ERROR: path not found: {p}", file=sys.stderr)
            sys.exit(2)
        all_findings.extend(scan_dir(path, args.exclude))

    # Stats
    by_severity = {"P0": 0, "P1": 0, "P2": 0}
    for f in all_findings:
        if "severity" in f:
            by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1

    if args.json:
        print(json.dumps({
            "findings": all_findings,
            "summary": by_severity,
            "total": len(all_findings),
        }, indent=2, ensure_ascii=False))
    else:
        print(f"\n=== 0.0.0.0 Bind Audit (L4) ===\n")
        if not all_findings:
            print("[OK] No 0.0.0.0 binding found")
        else:
            for f in all_findings:
                if "error" in f:
                    print(f"  [ERR] {f['file']}: {f['error']}")
                    continue
                icon = {"P0": "[P0!]", "P1": "[P1!]", "P2": "[P2]"}.get(f["severity"], "[?]")
                print(f"  {icon} {f['file']}:{f['line']}  {f['pattern']}")
                print(f"      code: {f['code']}")
                print(f"      fix:  {f['fix']}")
            print(f"\n  P0 (必修): {by_severity['P0']}")
            print(f"  P1 (建议): {by_severity['P1']}")
            print(f"  P2 (合规): {by_severity['P2']}")

    # Exit code
    if by_severity["P0"] > 0:
        sys.exit(1)
    if args.strict and by_severity["P1"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()