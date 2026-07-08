# -*- coding: utf-8 -*-
"""
M8 ETag middleware（QE-M8-2026-06-v2）

[M8.VP-5 2026-06-06] ETag / If-None-Match 中间件。

解决问题：客户端缓存 + 304 Not Modified。

设计：
- 监听 GET /api/v1/<entity> 响应
- 响应内容计算 MD5 → ETag
- 客户端带 If-None-Match 时 → 304
- 仅对包含 'items' 的 JSON 响应启用（避免误用）

用法：
    from meta.core.etag_middleware import init_etag_middleware
    init_etag_middleware(app)
"""
from __future__ import annotations
import logging
from typing import Any

from flask import request, make_response, jsonify

from meta.core.m8_utils import compute_etag, check_etag_match

logger = logging.getLogger(__name__)


def init_etag_middleware(app) -> None:
    """注册 ETag middleware 到 Flask app。"""

    @app.after_request
    def _add_etag_header(response):
        # 1. 仅 GET + JSON 响应
        if request.method != 'GET':
            return response
        if not response.is_json:
            return response
        # 2. 排除 SSE 端点
        path = request.path
        if '/subscribe/' in path or '/sse' in path:
            return response
        # 3. 排除导出
        if '/export' in path:
            return response
        # 4. 排除文件下载
        if not response.mimetype.startswith('application/json'):
            return response

        try:
            data = response.get_json()
        except Exception:
            return response
        if not isinstance(data, dict):
            return response
        # 仅对带 'items' 的列表类响应添加
        if 'items' not in data:
            return response

        # 5. 计算 ETag
        etag = compute_etag(data)

        # 6. 检查 If-None-Match
        if check_etag_match(etag, dict(request.headers)):
            # 304 Not Modified
            new_resp = make_response('', 304)
            new_resp.headers['ETag'] = f'"{etag}"'
            return new_resp

        # 7. 设置 ETag header
        response.headers['ETag'] = f'"{etag}"'
        response.headers['Cache-Control'] = 'private, must-revalidate'
        return response

    logger.info('[M8.VP-5] ETag middleware registered')
