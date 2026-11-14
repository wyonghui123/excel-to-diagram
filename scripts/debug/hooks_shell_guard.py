#!/usr/bin/env python
"""PreToolUse Hook - 命令工具三条硬拦截 (L1 / L2 / L3)。

L1 禁裸 pytest            -> 唯一入口 python d:\\filework\\test.py
L2 禁 curl 别名            -> 用 curl.exe
L3 禁 Get-Process python / taskkill /IM python.exe -> 用 service_manager

契约: stdin 为 JSON {tool_name, tool_input:{command}};
      exit 0 + allow JSON = 放行, exit 2 + deny JSON = 拒绝。
任何内部异常一律放行 (fail-open), 避免 hook 自身故障堵死所有命令。

与 hooks_shell_guard.ps1 行为等价；本文件为低开销实现 (~50ms vs ~490ms),
.ps1 保留作回退。
"""

import json
import os
import re
import sys

SHELL_TOOLS = {"Bash", "Shell", "run_command", "RunCommand", "runCommand", "execute_command"}

RULES = [
    (
        "L1",
        re.compile(r"(?<![\w.])pytest(?:\.exe)?(?![\w.])", re.I),
        r"禁止直接运行 pytest（铁律 L1）。唯一入口：python d:\filework\test.py --failed|--all|--single|--file",
    ),
    (
        "L2",
        re.compile(r"(?<![\w.\\/-])curl(?!\.exe)(?![\w.-])", re.I),
        "禁止使用 curl 别名（铁律 L2，PowerShell 中是 Invoke-WebRequest）。请改用 curl.exe",
    ),
    (
        "L3",
        re.compile(r"(?<![\w.-])Get-Process(?![\w-])[^;|&]*?(?<![\w.-])python", re.I),
        "禁止用 Get-Process python 判活（铁律 L3）。请用 python scripts/service_manager.py status",
    ),
    (
        "L3",
        re.compile(r"\btaskkill(?:\.exe)?\b[^;|&]*\/im\s+[\"']?python", re.I),
        "禁止用 taskkill /IM python*.exe 杀服务（铁律 L3）。请用 python scripts/service_manager.py stop|restart",
    ),
]


def allow():
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}, ensure_ascii=False))
    sys.exit(0)


def project_root():
    p = os.environ.get("TRAE_PROJECT_DIR")
    if p:
        return p
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def main():
    try:
        data = sys.stdin.buffer.read()
    except Exception:
        allow()
    # Windows 下 stdio 默认按 locale(cp936) 解码, 命令含中文会乱码; 显式按 UTF-8 再退回 GBK
    try:
        raw = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            raw = data.decode("gbk")
        except UnicodeDecodeError:
            allow()
    if not raw.strip():
        allow()

    try:
        payload = json.loads(raw)
    except Exception:
        allow()

    tool_name = payload.get("tool_name") or os.environ.get("TRAE_TOOL_NAME", "")
    if tool_name not in SHELL_TOOLS:
        allow()

    tool_input = payload.get("tool_input")
    if isinstance(tool_input, str):
        cmd = tool_input
    elif isinstance(tool_input, dict):
        cmd = ""
        for key in ("command", "cmd", "shell_command", "script"):
            value = tool_input.get(key)
            if value:
                cmd = str(value)
                break
    else:
        cmd = ""
    if not cmd:
        cmd = os.environ.get("TRAE_TOOL_INPUT", "")
    if not cmd:
        allow()

    for rule, pattern, reason in RULES:
        if pattern.search(cmd):
            message = f"[{rule} Hook 拦截] {reason}\n命令: {cmd}"
            try:
                log_dir = os.path.join(project_root(), ".trae", "debug", "logs")
                os.makedirs(log_dir, exist_ok=True)
                with open(os.path.join(log_dir, "hook_violations.log"), "a", encoding="utf-8") as fh:
                    fh.write(f"DENY {tool_name} ({rule}) {cmd}\n")
            except Exception:
                pass
            print(
                json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "permissionDecision": "deny",
                            "permissionDecisionReason": message,
                        }
                    },
                    ensure_ascii=False,
                )
            )
            sys.exit(2)

    allow()


if __name__ == "__main__":
    main()