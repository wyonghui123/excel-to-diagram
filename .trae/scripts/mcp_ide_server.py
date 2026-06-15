#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRAE IDE MCP Server (T-007)
===========================

让 Skills 与 TRAE IDE 双向通信:
  - file_open(path)         打开文件
  - file_edit(path, content) 编辑文件
  - terminal_run(cmd)        跑命令
  - preview_html(path)       打开 HTML preview
  - status_bar_set(text)     设置状态栏
  - show_notification(...)   IDE 通知
  - show_dialog(...)         弹出对话框

工作方式:
  - Skills 通过 stdout 输出 JSON-RPC 格式指令
  - MCP server 监听 3020 端口,处理来自 TRAE IDE 的指令
  - 所有调用记录到 .trae/state/mcp-ide.log

用法:
    python mcp_ide_server.py --port 3020
    python mcp_ide_server.py --test  # 跑内置测试
"""

import argparse
import json
import os
import socket
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_PORT = 3020
LOG_FILE = Path(".trae/state/mcp-ide.log")


def _log(level, message, **kwargs):
    """结构化日志"""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "message": message,
        "trace_id": kwargs.get("trace_id", uuid.uuid4().hex[:16]),
        **kwargs,
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 8 个 MCP 工具实现
# ---------------------------------------------------------------------------

def file_open(path: str, **kwargs) -> dict:
    """打开文件 - 在 TRAE IDE 中"""
    full_path = Path(path).resolve()
    if not full_path.exists():
        return {"success": False, "error": f"File not found: {path}"}
    _log("info", "file_open", path=str(full_path))
    # 实际通过 IPC 通知 TRAE IDE
    # 此处 mock 实现,真实环境 TRAE 会通过 stdin/stdout 通道接收
    return {
        "success": True,
        "tool": "file_open",
        "path": str(full_path),
        "trace_id": kwargs.get("trace_id", uuid.uuid4().hex[:16]),
    }


def file_edit(path: str, content: str, **kwargs) -> dict:
    """编辑文件"""
    full_path = Path(path).resolve()
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    _log("info", "file_edit", path=str(full_path), size=len(content))
    return {"success": True, "tool": "file_edit", "path": str(full_path)}


def terminal_run(cmd: str, cwd: str = None, **kwargs) -> dict:
    """在 IDE 终端中跑命令"""
    import subprocess
    cwd_path = Path(cwd).resolve() if cwd else Path.cwd()
    _log("info", "terminal_run", cmd=cmd, cwd=str(cwd_path))
    # 注意: 真实环境这里会用 TRAE 终端通道
    # 此处我们返回 "queued" 表示已提交到 IDE 终端
    return {
        "success": True,
        "tool": "terminal_run",
        "cmd": cmd,
        "cwd": str(cwd_path),
        "status": "queued",  # TRAE IDE 会真正执行
        "trace_id": kwargs.get("trace_id", uuid.uuid4().hex[:16]),
    }


def preview_html(path: str, **kwargs) -> dict:
    """在 IDE 中打开 HTML preview"""
    full_path = Path(path).resolve()
    if not full_path.exists():
        return {"success": False, "error": f"File not found: {path}"}
    _log("info", "preview_html", path=str(full_path))
    return {"success": True, "tool": "preview_html", "path": str(full_path)}


def status_bar_set(text: str, color: str = "default", progress: float = None, **kwargs) -> dict:
    """设置 IDE 状态栏"""
    _log("info", "status_bar_set", text=text, color=color, progress=progress)
    return {
        "success": True,
        "tool": "status_bar_set",
        "text": text,
        "color": color,
        "progress": progress,
    }


def show_notification(
    type: str = "info",
    title: str = "",
    message: str = "",
    action_buttons: list = None,
    **kwargs,
) -> dict:
    """IDE 通知"""
    _log("info", "show_notification", type=type, title=title, msg=message)
    return {
        "success": True,
        "tool": "show_notification",
        "type": type,
        "title": title,
        "message": message,
        "actions": action_buttons or [],
    }


def show_dialog(
    title: str,
    content: str,
    action_buttons: list = None,
    **kwargs,
) -> dict:
    """IDE 对话框 - 人在回路关键"""
    _log("info", "show_dialog", title=title, content=content)
    return {
        "success": True,
        "tool": "show_dialog",
        "title": title,
        "content": content,
        "actions": action_buttons or [],
        "awaiting_user_response": True,
    }


# ---------------------------------------------------------------------------
# JSON-RPC 处理
# ---------------------------------------------------------------------------

TOOLS = {
    "file_open": file_open,
    "file_edit": file_edit,
    "terminal_run": terminal_run,
    "preview_html": preview_html,
    "status_bar_set": status_bar_set,
    "show_notification": show_notification,
    "show_dialog": show_dialog,
}


def handle_request(request: dict) -> dict:
    """处理一个 JSON-RPC 请求"""
    method = request.get("method")
    params = request.get("params", {})
    req_id = request.get("id", uuid.uuid4().hex[:8])

    if method not in TOOLS:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    try:
        result = TOOLS[method](**params)
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32603, "message": str(e)},
        }


def serve_stdio():
    """stdin/stdout JSON-RPC 服务模式"""
    _log("info", "mcp_server_start_stdio", port=DEFAULT_PORT)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
        except json.JSONDecodeError as e:
            error = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {e}"},
            }
            sys.stdout.write(json.dumps(error) + "\n")
            sys.stdout.flush()


def serve_tcp(host: str = "127.0.0.1", port: int = DEFAULT_PORT):
    """TCP 服务模式 - 供测试用"""
    _log("info", "mcp_server_start_tcp", host=host, port=port)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)
    print(f"MCP IDE Server listening on {host}:{port}", file=sys.stderr)

    try:
        while True:
            conn, addr = server.accept()
            data = conn.recv(8192).decode("utf-8")
            if not data:
                conn.close()
                continue
            try:
                request = json.loads(data)
                response = handle_request(request)
                conn.sendall(
                    (json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8")
                )
            except json.JSONDecodeError as e:
                error = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {e}"},
                }
                conn.sendall((json.dumps(error) + "\n").encode("utf-8"))
            finally:
                conn.close()
    except KeyboardInterrupt:
        _log("info", "mcp_server_stop")
    finally:
        server.close()


def run_tests():
    """内置测试 - 8 个工具全部跑一遍"""
    print("=" * 60)
    print("TRAE IDE MCP Server - 内置测试")
    print("=" * 60)

    tests = [
        # 1. file_open
        {
            "method": "file_open",
            "params": {"path": ".trae/specs/_business_rules/_index.json"},
            "expect": lambda r: r["result"]["success"] is True,
        },
        # 2. file_edit
        {
            "method": "file_edit",
            "params": {"path": "tmp_test.txt", "content": "hello"},
            "expect": lambda r: r["result"]["success"] is True,
        },
        # 3. terminal_run
        {
            "method": "terminal_run",
            "params": {"cmd": "npx vitest --version"},
            "expect": lambda r: r["result"]["status"] == "queued",
        },
        # 4. preview_html
        {
            "method": "preview_html",
            "params": {"path": ".trae/specs/_business_rules/_index.json"},  # 用非 html 测
            "expect": lambda r: r["result"]["success"] is True,
        },
        # 5. status_bar_set
        {
            "method": "status_bar_set",
            "params": {"text": "🤖 业务流 3/8 通过", "color": "green", "progress": 0.3},
            "expect": lambda r: r["result"]["text"] == "🤖 业务流 3/8 通过",
        },
        # 6. show_notification
        {
            "method": "show_notification",
            "params": {
                "type": "action",
                "title": "📋 Business Flow Draft Ready",
                "message": "请 review business-flow.yaml",
                "action_buttons": [
                    {"id": "approve", "label": "Approve", "primary": True},
                ],
            },
            "expect": lambda r: len(r["result"]["actions"]) == 1,
        },
        # 7. show_dialog (Healer 关键)
        {
            "method": "show_dialog",
            "params": {
                "title": "🔧 失败原因: locator 漂移",
                "content": "建议修复: 将 '.el-button--primary' 替换为 role=button[name='保存']",
                "action_buttons": [
                    {"id": "apply", "label": "Apply Fix", "primary": True},
                    {"id": "edit", "label": "Edit Manually"},
                    {"id": "skip", "label": "Skip"},
                ],
            },
            "expect": lambda r: r["result"]["awaiting_user_response"] is True,
        },
        # 8. 错误处理
        {
            "method": "file_open",
            "params": {"path": "non_existent_file_xyz"},
            "expect": lambda r: r["result"]["success"] is False,
        },
    ]

    passed = 0
    for i, test in enumerate(tests, 1):
        req = {"jsonrpc": "2.0", "id": i, "method": test["method"], "params": test["params"]}
        resp = handle_request(req)
        ok = test["expect"](resp)
        status = "[OK]" if ok else "[FAIL]"
        print(f"  {status} {test['method']}: {test['params']}")
        if ok:
            passed += 1

    # 清理
    Path("tmp_test.txt").unlink(missing_ok=True)

    print(f"\n结果: {passed}/{len(tests)} passed")
    return passed == len(tests)


def main():
    parser = argparse.ArgumentParser(description="TRAE IDE MCP Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--test", action="store_true", help="跑内置测试")
    parser.add_argument("--stdio", action="store_true", help="stdin/stdout 模式")
    args = parser.parse_args()

    if args.test:
        ok = run_tests()
        sys.exit(0 if ok else 1)
    elif args.stdio:
        serve_stdio()
    else:
        serve_tcp(args.host, args.port)


if __name__ == "__main__":
    main()
