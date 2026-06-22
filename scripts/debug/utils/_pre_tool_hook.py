#!/usr/bin/env python3
"""
_pre_tool_hook.py - V3.5 P5 重写版

设计原则（关键修正）：
1. 不用 inline PowerShell（容易触发 sandbox skip）
2. 不用管道（`2>&1 |`, `|` 容易缓冲卡死）
3. 不用 Select-Object（变量被吞）
4. 不用多语句分号（触发 sandbox skip）

替代方案：
- 直接用 Read 工具写日志文件
- AI 在跑命令前自己读 .trae/debug/sandbox_logs/last_event.json
"""
import sys
import os
import json
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path("d:/filework/excel-to-diagram")
DEBUG_DIR = PROJECT_ROOT / ".trae" / "debug"
SANDBOX_LOGS_DIR = DEBUG_DIR / "sandbox_logs"


def main():
    # Trae hook 输入通过 TRAE_TOOL_INPUT 环境变量
    tool_input = os.environ.get("TRAE_TOOL_INPUT", "")
    tool_name = os.environ.get("TRAE_TOOL_NAME", "unknown")

    # 简单写文件（Python I/O 在 sandbox 故障时仍可用）
    SANDBOX_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # 记录到事件日志（rotate daily）
    log_file = SANDBOX_LOGS_DIR / f"events_{datetime.now().strftime('%Y%m%d')}.jsonl"

    # 截断 input（防止敏感信息泄露）
    truncated = tool_input[:200] if len(tool_input) > 200 else tool_input

    event = {
        "timestamp": datetime.now().isoformat(),
        "tool": tool_name,
        "input_preview": truncated,
    }

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception:
        pass  # 写日志失败不阻塞

    # 短消息到 stdout（避免缓冲）
    print(f"[V3.5] Tool: {tool_name}, log: {log_file.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # hook 永不抛异常
    sys.exit(0)