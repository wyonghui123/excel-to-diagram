#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PowerShell 重定向风险检测工具 - V2.1 P2-4 新增

背景：2026-06-20 多 Agent 报告 trae-sandbox + PowerShell 下
       `> file`、`>> file`、`Out-File`、`Set-Content` 等会假成功
       （exit 0 + stdout 正常 + 但文件未创建）。

       平均每次假成功浪费 60 分钟（见 violation_cost_report.md）

为什么不用 hooks.json 拦截？
- 2026-06-21 用户报告 "昨天的 hook 问题" → 所有 hooks 已关闭
- 加新 hook 可能再次触发问题
- **改用主动检测**：AI Agent 启动前自动跑本工具

用法：
    # 检测 PS 重定向使用（通过扫描最近命令历史）
    python scripts/check_powershell_redirection.py check

    # 检测当前命令是否危险
    python scripts/check_powershell_redirection.py detect "git diff > file.txt"

    # 列出已知危险的 PS 操作
    python scripts/check_powershell_redirection.py list

    # 显示安全替代方案
    python scripts/check_powershell_redirection.py alternatives "echo hello > file.txt"

    # 集成到 debug_backend.py
    python scripts/debug_backend.py check  # 自动运行本工具
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Tuple


# 已知危险的 PowerShell 重定向模式
DANGEROUS_PATTERNS = [
    # PS 重定向操作符（trae-sandbox 假成功高发区）
    (r'>\s*\S+\.(txt|md|json|log|patch|out|err)', "PS 重定向 '>' 在 trae-sandbox 下假成功"),
    (r'>>\s*\S+\.(txt|md|json|log|patch|out|err)', "PS 重定向 '>>' 在 trae-sandbox 下假成功"),
    (r'2>&1.*>\s*\S+', "PS '2>&1 >' 重定向在沙箱下不可靠"),

    # PS 文件写入 cmdlet（trae-sandbox 隔离时假成功）
    (r'\bOut-File\s+-Path\s+\S+', "Out-File 在沙箱隔离时假成功"),
    (r'\bSet-Content\s+-Path\s+\S+', "Set-Content 在沙箱隔离时假成功"),
    (r'\bAdd-Content\s+-Path\s+\S+', "Add-Content 在沙箱隔离时假成功"),

    # Bash 风格重定向（在 PS 中通过 curl.exe 调用）
    (r'echo\s+.*>\s*\S+\.\w+', "'echo > file' 在沙箱下假成功"),
    (r'tee\s+-?\w*\s*\S+\.\w+', "'tee' 在沙箱下假成功"),

    # 这里特别针对有问题的复合操作
    (r'git\s+diff\s+>\s*\S+', "git diff > file 假成功案例（多次发生）"),
    (r'git\s+show\s+>\s*\S+', "git show > file 假成功案例"),
]

# 安全替代方案
SAFE_ALTERNATIVES = {
    "> file.txt": "用 Write 工具（Claude IDE 内置）",
    ">> file.txt": "用 Edit 工具（追加场景）",
    "Out-File -Path file.txt": "用 Write 工具",
    "Set-Content -Path file.txt": "用 Write 工具",
    "echo > file": "用 Write 工具 + 'echo' 内容",
    "tee file.txt": "用 Write 工具（先收集内容）",
    "git diff > file.patch": "用 Read 工具 + Write 工具（手动传内容）",
}


def _log(msg: str, level: str = "INFO"):
    icons = {"OK": "[OK]", "FAIL": "[X]", "WARN": "[!]", "INFO": "[i]"}
    print(f"{icons.get(level, '[?]}')} {msg}")


def detect_dangerous_commands(text: str) -> List[Tuple[str, str]]:
    """检测文本中的危险 PS 重定向操作

    Returns:
        list of (matched_pattern, risk_description)
    """
    risks = []
    for pattern, description in DANGEROUS_PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for m in matches:
            risks.append((m.group(0), description))
    return risks


def get_alternative(command: str) -> str:
    """为给定的危险命令推荐安全替代方案"""
    cmd_stripped = command.strip()

    # 精确匹配
    for dangerous, alt in SAFE_ALTERNATIVES.items():
        if dangerous.lower() in cmd_stripped.lower():
            return alt

    # 模糊匹配
    if re.search(r'>\s*\S+\.\w+', cmd_stripped):
        return "用 Write 工具（Claude IDE 内置，避免 PS 重定向假成功）"
    if re.search(r'\b(Out-File|Set-Content|Add-Content)\b', cmd_stripped, re.IGNORECASE):
        return "用 Write 工具"

    return "用 Write 工具替代"


def cmd_check(args):
    """检查最近的命令历史（如果有）"""
    # 暂未实现 - 需要 hook 命令历史采集
    # 留接口，未来可从 trae-sandbox log 提取
    _log("当前实现：手动检测（扫描 AI 输入的命令）", "INFO")
    _log("未来：自动从 trae-sandbox log 提取命令历史", "INFO")
    print()
    print("手动检测用法：")
    print("  python scripts/check_powershell_redirection.py detect \"<你的命令>\"")
    print()
    print("或者直接看：")
    print("  python scripts/check_powershell_redirection.py list")


def cmd_detect(args):
    """检测给定的命令是否危险"""
    command = " ".join(args.command)

    risks = detect_dangerous_commands(command)
    print("=" * 70)
    print(f"检测命令: {command}")
    print("=" * 70)
    print()

    if not risks:
        _log(f"未发现危险 PS 重定向模式 ✓", "OK")
        return 0

    _log(f"发现 {len(risks)} 个潜在风险:", "FAIL")
    for i, (matched, desc) in enumerate(risks, 1):
        print(f"  {i}. 命令片段: {matched!r}")
        print(f"     风险描述: {desc}")

    print()
    alt = get_alternative(command)
    _log(f"建议替代方案: {alt}", "WARN")
    print()
    return 1


def cmd_list(args):
    """列出所有已知危险的 PS 操作"""
    print("=" * 70)
    print("已知危险的 PowerShell 重定向操作（trae-sandbox 下假成功高发区）")
    print("=" * 70)
    print()

    categories = {
        "PS 重定向操作符": [
            ("> file.txt", "PS 重定向 '>' 在沙箱下假成功"),
            (">> file.txt", "PS 重定向 '>>' 在沙箱下假成功"),
            ("2>&1 > file.txt", "PS '2>&1 >' 复合重定向不可靠"),
        ],
        "PS 文件写入 cmdlet": [
            ("Out-File -Path file.txt", "Out-File 在沙箱隔离时假成功"),
            ("Set-Content -Path file.txt", "Set-Content 在沙箱隔离时假成功"),
            ("Add-Content -Path file.txt", "Add-Content 在沙箱隔离时假成功"),
        ],
        "Bash 风格（PS 中）": [
            ("echo > file", "echo > 在 PS 沙箱下假成功"),
            ("tee file.txt", "tee 在 PS 沙箱下假成功"),
            ("git diff > file.patch", "git diff > file 多次假成功案例"),
        ],
    }

    for category, items in categories.items():
        print(f"## {category}")
        print()
        for cmd, risk in items:
            alt = SAFE_ALTERNATIVES.get(cmd.split()[0] + " " + cmd.split()[1] if len(cmd.split()) > 1 else cmd, "用 Write 工具")
            print(f"  ❌ {cmd}")
            print(f"     风险: {risk}")
            print(f"     ✅ 替代: {alt}")
            print()


def cmd_alternatives(args):
    """显示安全替代方案"""
    command = " ".join(args.command)
    alt = get_alternative(command)

    print(f"命令: {command}")
    print(f"替代: {alt}")


def main():
    parser = argparse.ArgumentParser(
        description="PowerShell 重定向风险检测 - V2.1 P2-4",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("check", help="检查最近的命令历史（手动模式）")
    det = sub.add_parser("detect", help="检测给定命令是否危险")
    det.add_argument("command", nargs="+", help="要检测的命令")
    sub.add_parser("list", help="列出已知危险的 PS 操作")
    alt_cmd = sub.add_parser("alternatives", help="显示安全替代方案")
    alt_cmd.add_argument("command", nargs="+", help="要给替代方案的危险命令")

    args = parser.parse_args()

    if args.cmd == "check":
        return cmd_check(args)
    elif args.cmd == "detect":
        return cmd_detect(args)
    elif args.cmd == "list":
        return cmd_list(args)
    elif args.cmd == "alternatives":
        return cmd_alternatives(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)