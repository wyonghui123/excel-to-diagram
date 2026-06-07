# -*- coding: utf-8 -*-
"""
[MODULE] M.2 结构化 JSON logger (v3.18)
[DESCRIPTION] 机器可解析, AI Agent 可 grep + jq 解析

合规:
- [OK] 替代 print (走 logging 框架)
- [OK] JSON 1 行 1 条 (便于 grep)
- [OK] 含 trace_id
"""
import os
import json
import logging
from datetime import datetime
from typing import Optional


class JsonFormatter(logging.Formatter):
    """[DECORATIVE] v3.18 M.2: JSON formatter for stdout"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'ts': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        # [DECORATIVE] v3.18 M.1: trace_id 自动注入
        try:
            from meta.core.trace_id import TraceId
            log_data['trace_id'] = TraceId.get()
        except Exception:
            pass

        # 额外字段 (extra=...)
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)

        # 异常
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


_initialized = False


def setup_json_logging(log_dir: Optional[str] = None) -> logging.Logger:
    """[DECORATIVE] v3.18 M.2: 设置 JSON log 框架

    Args:
        log_dir: 日志目录, 默认 ./logs

    Returns:
        root logger
    """
    global _initialized
    if _initialized:
        return logging.getLogger()

    if log_dir is None:
        log_dir = os.path.join(os.getcwd(), 'logs')
    os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # 清理已有 handlers (避免重复)
    for h in list(root.handlers):
        root.removeHandler(h)

    # 1. stdout (JSON)
    stdout_h = logging.StreamHandler()
    stdout_h.setFormatter(JsonFormatter())
    root.addHandler(stdout_h)

    # 2. 文件 (JSON, 1 天 1 文件)
    log_file = os.path.join(log_dir, 'app.jsonl')
    file_h = logging.FileHandler(log_file, encoding='utf-8')
    file_h.setFormatter(JsonFormatter())
    root.addHandler(file_h)

    _initialized = True
    return root


def log_event(level: int, event: str, **fields) -> None:
    """[DECORATIVE] 便捷方法: log 一条事件"""
    logger = logging.getLogger('meta.event')
    logger.log(level, event, extra={'extra_fields': {'event': event, **fields}})
