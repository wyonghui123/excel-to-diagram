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
from datetime import datetime, timezone
from logging.handlers import TimedRotatingFileHandler
from typing import Optional


class JsonFormatter(logging.Formatter):
    """[DECORATIVE] v3.18 M.2: JSON formatter for stdout"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        # [FR-010] trace_id / request_id 自动注入：优先 Flask 请求上下文，退回线程本地
        trace_id = ''
        try:
            from flask import g, has_request_context
            if has_request_context():
                trace_id = getattr(g, 'trace_id', '') or ''
        except Exception:
            pass
        if not trace_id:
            try:
                from meta.core.trace_id import TraceId
                trace_id = TraceId.get() or ''
            except Exception:
                pass
        log_data['trace_id'] = trace_id
        log_data['request_id'] = trace_id

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
        # [FR-010] 默认落到仓库 scripts/logs，避免随 cwd 漂移
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        log_dir = os.environ.get('PLATFORM_LOG_DIR') or os.path.join(repo_root, 'scripts', 'logs')
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

    # 2. 文件 (JSON, 按天轮转，保留 7 天) —— FR-010
    log_file = os.path.join(log_dir, 'backend.jsonl')
    file_h = TimedRotatingFileHandler(
        log_file, when='midnight', backupCount=7, encoding='utf-8', delay=True,
    )
    file_h.suffix = '%Y-%m-%d'
    file_h.setFormatter(JsonFormatter())
    root.addHandler(file_h)

    _initialized = True
    return root


def log_event(level: int, event: str, **fields) -> None:
    """[DECORATIVE] 便捷方法: log 一条事件"""
    logger = logging.getLogger('meta.event')
    logger.log(level, event, extra={'extra_fields': {'event': event, **fields}})
