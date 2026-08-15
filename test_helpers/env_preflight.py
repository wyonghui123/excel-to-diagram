"""
env_preflight.py - 图表验证环境统一端口配置 + 前置探活
========================================================

[P0 2026-08-14] 解决复盘中的两个效率阻碍点:
  1. 端口约定混乱 (vite.config 默认 3005 / service_manager 前端 3004+后端 3010 /
     e2e BASE_URL 3006 / probe 脚本写死 3005) → 环境一换就静默跑错目标.
     统一从此处读取, 新脚本/已有脚本一律 import, 不再各自写死.
  2. 环境停止时诊断脚本静默卡 90s (wait_for_function 超时) 且无"服务未就绪"提示
     → preflight() 启动前探活, 失败立即报错 + 给出启动命令, 快速失败.

用法:
    from test_helpers.env_preflight import FRONTEND_URL, BACKEND_URL, preflight
    preflight(require_backend=True)   # 启动脚本前先探活, 失败 SystemExit(1)
"""
import socket
import sys

# 统一端口约定 (与 scripts/service_manager.ps1 保持一致):
#   FRONTEND: Vite dev server (service_manager 默认前端 3004)
#   BACKEND:  Waitress/Flask (service_manager -Port 3010)
FRONTEND_PORT = 3004
BACKEND_PORT = 3010
FRONTEND_URL = f'http://localhost:{FRONTEND_PORT}'
BACKEND_URL = f'http://localhost:{BACKEND_PORT}'


def probe_port(port, timeout=1.5):
    """探测端口是否可连接 (TCP connect, 快于 HTTP 请求)."""
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=timeout):
            return True
    except OSError:
        return False


def preflight(require_backend=False, fail=True):
    """前置探活: 检查前端 (必需) 与后端 (可选) 是否就绪.

    失败时打印诊断 + 启动命令, 默认 SystemExit(1) 快速失败,
    避免脚本随后静默卡在 wait_for_function 90s 超时.
    返回 True/False (fail=False 时不退出, 由调用方决定).
    """
    ok = True
    msgs = []
    if not probe_port(FRONTEND_PORT):
        ok = False
        msgs.append(f'[FAIL] 前端 {FRONTEND_URL} 未就绪 (端口 {FRONTEND_PORT} 无监听)')
    else:
        msgs.append(f'[OK]   前端 {FRONTEND_URL}')
    if require_backend:
        if not probe_port(BACKEND_PORT):
            ok = False
            msgs.append(f'[FAIL] 后端 {BACKEND_URL} 未就绪 (端口 {BACKEND_PORT} 无监听)')
        else:
            msgs.append(f'[OK]   后端 {BACKEND_URL}')
    print('--- 环境探活 ---')
    for m in msgs:
        print(' ' + m)
    print('-----------------')
    if not ok:
        print('[HINT] 启动开发环境:')
        print('  方式1: powershell -File scripts/service_manager.ps1 start -Port 3010')
        print('  方式2: .\\scripts\\start-dev.ps1')
        if fail:
            sys.exit(1)
    return ok
