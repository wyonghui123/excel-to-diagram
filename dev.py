#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
开发环境启动脚本
- 启动 Flask 服务器
- 启动守卫: 检测端口冲突 + 引导使用 service_manager
- --clean-cache: 清理 Python 缓存（默认跳过以加速启动）
"""
from __future__ import print_function

import os
import sys
import io
import json
import socket
from pathlib import Path

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')


def _check_port(host, port, timeout=2):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except OSError:
        return False


def _startup_guard(port):
    project_root = Path(__file__).parent
    status_file = project_root / '.service_status.json'

    if _check_port('127.0.0.1', port):
        existing_info = ''
        if status_file.exists():
            try:
                data = json.loads(status_file.read_text(encoding='utf-8'))
                for svc_name, svc in data.items():
                    if svc.get('port') == port:
                        existing_info = (
                            "\n  已知信息: %s (PID=%s, since=%s)"
                            % (svc_name, svc.get('pid', '?'), svc.get('started_at', '?'))
                        )
                        break
            except (json.JSONDecodeError, OSError):
                pass

        print("""
============================================================
[STARTUP GUARD] 端口 %d 已被占用%s

多Agent并行环境下，请使用统一服务管理器:
  查看状态:  powershell -File scripts/service_manager.ps1 status
  重启服务:  powershell -File scripts/service_manager.ps1 restart

当前服务已在运行，无需重复启动。如确需重启请用上面命令。
============================================================
""" % (port, existing_info), file=sys.stderr)
        sys.exit(1)


def main():
    base_dir = Path(__file__).parent
    port = int(os.environ.get('FLASK_PORT', 5000))

    _startup_guard(port)

    if '--clean-cache' in sys.argv:
        import shutil
        removed_count = 0
        for cache_dir in base_dir.rglob("__pycache__"):
            shutil.rmtree(cache_dir, ignore_errors=True)
            removed_count += 1
        for pyc_file in base_dir.rglob("*.pyc"):
            try:
                pyc_file.unlink()
                removed_count += 1
            except:
                pass
        print("[Startup] Cleaned %d cache files/directories" % removed_count)

    os.environ.setdefault('FLASK_DEBUG', 'True')
    os.environ.setdefault('PYTHONUNBUFFERED', '1')

    print("[Startup] Starting server with FLASK_DEBUG=%s" % os.environ.get('FLASK_DEBUG'))
    print("[Startup] Press Ctrl+C to stop\n")

    from dotenv import load_dotenv
    load_dotenv()

    import meta.server as server_module
    server_module.app = server_module.create_app()

    port = int(os.environ.get('FLASK_PORT', 5000))
    print("[Startup] Starting Flask on port %d" % port)
    server_module.app.run(
        host='0.0.0.0',
        port=port,
        debug=True,
        use_reloader=False
    )


if __name__ == '__main__':
    main()
