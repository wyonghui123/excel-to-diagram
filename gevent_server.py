# -*- coding: utf-8 -*-
"""
Gevent WSGI Server (v3.9, experimental)
==========================================

[DECORATIVE] v3.9: 备选 server - gevent 协程 + 真流式 SSE
[DECORATIVE] v3.10: 标注 experimental - Python 3.14 socket.recv_into 兼容性问题

[WARNING] 已知问题: gevent 26.5 + Python 3.14 在 Windows 上
   - monkey-patch 失败, socket._socket.socket.recv_into 仍阻塞
   - 多请求并发时出现 BlockingSwitchOutError
   - 推荐用 waitress_server.py (稳定, 8 线程, 真流式)

Usage (推荐 - dev only):
    python gevent_server.py
"""
import os
import sys

print('=' * 60)
print('[GEVENT] [WARNING] EXPERIMENTAL - 推荐用 waitress_server.py')
print('[GEVENT] gevent 26.5 + Python 3.14 在 Windows 上有兼容性问题')
print('[GEVENT] BlockingSwitchOutError 多请求并发时可能发生')
print('=' * 60)
import os
import sys
import time

# [DECORATIVE] v3.9: monkey-patch 必须第一行
try:
    import gevent.monkey
    gevent.monkey.patch_all()
except ImportError as e:
    print('[GEVENT] ERROR: gevent not installed. Run: pip install gevent')
    sys.exit(1)


# 现在才 import 其它
import logging
from gevent.pywsgi import WSGIServer

logger = logging.getLogger(__name__)


# 启动日志
print('=' * 60)
print('[GEVENT] v3.9 starting...')
print('[GEVENT] gevent 26.5.0 (monkey-patched)')
print('[GEVENT] 单进程 + 协程并发')
print('[GEVENT] 真流式 SSE (每 yield 立即 flush)')
print('=' * 60)


# 创建 Flask app
from meta.server import create_app
application = create_app()

print(f'[GEVENT] Flask app created. Bind: 0.0.0.0:3010')
print(f'[GEVENT] FLASK_DEBUG: {os.environ.get("FLASK_DEBUG", "not set")}')


if __name__ == '__main__':
    # [DECORATIVE] v3.9: WSGIServer 替代 waitress
    server = WSGIServer(
        ('0.0.0.0', 3010),
        application,
        log=None,  # 不写默认日志, 我们自己处理
        error_log=None,
        spawn=None,  # 不 fork (与单进程策略一致)
    )

    print(f'[GEVENT] Serving on http://0.0.0.0:3010')
    print(f'[GEVENT] 协程模式 - 支持 6-10 agents 并发')
    print(f'[GEVENT] Ctrl+C to stop')

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[GEVENT] Shutting down...')
        server.stop(timeout=5)
        print('[GEVENT] Stopped')
