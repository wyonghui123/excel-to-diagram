# -*- coding: utf-8 -*-
"""
SSE 客户端封装 (v3.9 测试基础设施)
====================================

提供统一的 SSE 流式客户端, 用于所有 SSE 相关测试。
- 支持逐 event 读取
- 记录每个 event 的时间戳
- 自动鉴权 (Cookie)
- 解析 event: type / data: json
"""
import http.client
import json
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple


class SSEEvent:
    """单个 SSE 事件"""
    def __init__(self, event_type: str, data: Any, timestamp: float):
        self.event_type = event_type
        self.data = data
        self.timestamp = timestamp

    def __repr__(self):
        return f'SSEEvent({self.event_type}, t={self.timestamp:.3f}s, data={str(self.data)[:50]})'


class SSEClient:
    """
    SSE 客户端

    Usage:
        with SSEClient('/api/v2/action/_chain_stream', {'name': 'test', 'steps': [...]}, cookie) as sse:
            for event in sse.read_events():
                print(event)
    """
    def __init__(self, path: str, body: Dict[str, Any], cookie: Optional[str] = None,
                  host: str = 'localhost', port: int = 3010, timeout: float = 30.0):
        self.path = path
        self.body = body
        self.cookie = cookie
        self.host = host
        self.port = port
        self.timeout = timeout
        self.response: Optional[http.client.HTTPResponse] = None

    def __enter__(self):
        conn = http.client.HTTPConnection(self.host, self.port, timeout=self.timeout)
        body_bytes = json.dumps(self.body).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': str(len(body_bytes)),
            'Accept': 'text/event-stream',
        }
        if self.cookie:
            headers['Cookie'] = self.cookie
        conn.request('POST', self.path, body=body_bytes, headers=headers)
        self.response = conn.getresponse()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.response:
            self.response.close()

    def read_events(self, max_events: int = 1000) -> Iterator[SSEEvent]:
        """逐事件 yield"""
        if not self.response:
            return

        buf = b''
        start = time.time()
        count = 0

        while count < max_events:
            chunk = self.response.read(1)
            if not chunk:
                break
            buf += chunk
            if buf.endswith(b'\n\n'):
                ev_str = buf.decode('utf-8', errors='ignore').strip()
                buf = b''
                event_type = None
                event_data = None
                for line in ev_str.split('\n'):
                    if line.startswith('event: '):
                        event_type = line[7:]
                    elif line.startswith('data: '):
                        try:
                            event_data = json.loads(line[6:])
                        except Exception:
                            event_data = line[6:]
                if event_type:
                    yield SSEEvent(event_type, event_data, time.time() - start)
                    count += 1
                    if event_type == 'final':
                        break

    def read_all_events(self, max_events: int = 1000) -> List[SSEEvent]:
        """读所有事件到列表"""
        return list(self.read_events(max_events))
