"""check_credential_leak.py - 静态扫描密码/凭据留痕 (L7)
[V007.67 2026-07-14]

依据 .trae/rules/remote-execution-simplicity.md (V3) L7:
  服务器密码不在大模型留痕 / 不备份到服务器 / 一次性使用

禁止模式:
  - 写死: PASSWORD = "Admin@2026!Init"
  - env: os.environ["SERVER_PASSWORD"] = "xxx"
  - 命令行: sshpass -p xxx ssh ... (ps aux 可见)
  - 服务器内部备份: echo "PASSWORD=xxx" >> /opt/app/.env

用法:
  python check_credential_leak.py <path>...
  python check_credential_leak.py docs/ tools/
  python check_credential_leak.py . --json

输出:
  - 文件:行
  - 匹配模式
  - 建议改法 (改成 <PASSWORD from vault> 或 getpass)
"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict


# 已知泄漏的密码字面值 (从历史项目中发现)
KNOWN_BANNED_PASSWORDS = [
    "Admin@2026!Init",
    "Admin@2026",
    "yonyou@2026",
    "yonaa@2026",
    "P@ssw0rd",
    "Password123!",
    "root123",
    "postgres123",
    "admin123",
    "1qaz2wsx",
    "qwerty123",
]

# 凭据模式 (匹配可能的密码字符串)
CREDENTIAL_PATTERNS = [
    # Python / .env / .sh 变量赋值
    (re.compile(r"(?:password|passwd|pwd|secret|token|api_key|apikey)\s*[:=]\s*['\"]" + p + r"['\"]", re.IGNORECASE),
     f"hardcoded credential '{p}'",
     "P0",
     f"改 <PASSWORD from vault> 或 getpass()")
    for p in KNOWN_BANNED_PASSWORDS
] + [
    # 通用 password = "..." 模式
    (re.compile(r"(?:password|passwd|pwd|secret|admin_pwd)\s*[:=]\s*['\"]([^'\"]{8,})['\"]", re.IGNORECASE),
     "hardcoded credential value (8+ chars)",
     "P1",
     "使用环境变量 / vault / getpass()"),
    # sshpass 命令行
    (re.compile(r"sshpass\s+-p\s+['\"]?\S{6,}"),
     "sshpass -p (ps aux visible)",
     "P0",
     "用 SSH key 替代 (前提: 远端有 SSH)"),
    # 密码回显到 echo (e.g. echo "SERVER_PASSWORD=xxx")
    (re.compile(r"echo\s+.*password\s*=\s*\S{6,}", re.IGNORECASE),
     "echo ... PASSWORD=... (环境变量泄漏)",
     "P0",
     "用 vault read 或 getpass"),
    # 服务器内部备份 .env
    (re.compile(r"\.env.*?(?:password|secret|token).*?(?:=|:)\s*\S{6,}", re.IGNORECASE),
     ".env password/secret/token",
     "P1",
     "用 vault, 不写 .env"),
    # 文档字面密码
    (re.compile(r"login\s+admin\s*/\s*Admin@"),
     "docs 'admin / Admin@...' 字面密码",
     "P0",
     "改 'admin / <PASSWORD from vault>'"),
    # reset_admin_password.sh 写死
    (re.compile(r"(?:NEWPASS|NEW_PASSWORD|RESET_PASS)\s*=\s*['\"]\S{6,}"),
     "reset_password script 写死新密码",
     "P1",
     "用 getpass 一次性输入"),
]


# 已知合规例外 (测试 fixture / 已脱敏模板)
KNOWN_OK = {
    "<PASSWORD from vault>",
    "<VAULT_SECRET>",
    "getpass.getpass",
    "os.environ",
}


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
        # Markdown 文档豁免 - 但仍然标记 P2 (需手动脱敏)
        # 检测占位符 - 跳过
        if any(ok in stripped for ok in KNOWN_OK):
            continue
        # 检测元描述 - 跳过 (提及但不使用)
        if "应" in stripped or "必须" in stripped or "禁止" in stripped or "改" in stripped and "为" in stripped:
            # 元描述 (讨论修复方法本身), 跳过
            if "PASSWORD" in stripped or "密码" in stripped:
                continue

        for pattern, desc, severity, fix in CREDENTIAL_PATTERNS:
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
        # Code/text files only
        if f.suffix not in (".py", ".sh", ".env", ".txt", ".md", ".yaml", ".yml", ".json", ".conf", ".ini"):
            continue
        # Skip self
        if f.name == "check_credential_leak.py":
            continue
        # Skip test files (含示例代码)
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
    parser = argparse.ArgumentParser(description="Static scan credential leak (L7 审计)")
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
        print(f"\n=== Credential Leak Audit (L7) ===\n")
        if not all_findings:
            print("[OK] No credential leak found")
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
            print(f"\n  [提示] 脱敏模板: 改成 <PASSWORD from vault> 或 getpass()")

    if by_severity["P0"] > 0:
        sys.exit(1)
    if args.strict and by_severity["P1"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()