# -*- coding: utf-8 -*-
r"""
Overlap Detection API — 重复配置检测 API

【背景 2026-06-04】
按 Spec v1.3 FR-005，Section 1 (管理维度) 和 Section 3 (条件型权限)
可能配相同字段，UI 需要显示警告。

端点：
    GET  /api/v1/roles/<int:role_id>/overlaps
        - 列出该角色的所有重叠加
        - Query 参数：
            - resource_type: 按资源类型过滤
        - 响应：
            {
                'success': true,
                'data': {
                    'overlaps': [...],
                    'summary': {
                        'has_overlap': true,
                        'count': 2,
                        'fields': ['domain', 'product']
                    }
                }
            }

    GET  /api/v1/roles/<int:role_id>/overlaps/summary
        - 仅返回摘要（轻量级）
"""
import os
import sys
import logging

from flask import Blueprint, request, jsonify, g

# 路径处理
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from meta.core.dim_scope_overlap_detector import get_overlap_detector

logger = logging.getLogger(__name__)

overlap_bp = Blueprint('overlap', __name__)


def _login_required(f):
    """简化的登录校验（与项目其他 API 一致）"""
    from functools import wraps
    @wraps(f)
    def wrapper(*args, **kwargs):
        from meta.core.auth_helpers import is_authenticated
        if not is_authenticated():
            return jsonify({'success': False, 'error': '未登录'}), 401
        return f(*args, **kwargs)
    return wrapper


def get_role_overlaps(role_id: int):
    """获取角色的所有重叠加"""
    try:
        resource_type = request.args.get('resource_type', None)
        detector = get_overlap_detector()
        overlaps = detector.detect_overlaps(role_id, resource_type=resource_type)
        summary = detector.get_overlap_summary(role_id)
        return jsonify({
            'success': True,
            'data': {
                'overlaps': overlaps,
                'summary': summary,
            }
        })
    except Exception as e:
        logger.error(f"get_role_overlaps failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def get_role_overlap_summary(role_id: int):
    """获取角色的重叠加摘要（轻量级）"""
    try:
        detector = get_overlap_detector()
        summary = detector.get_overlap_summary(role_id)
        return jsonify({
            'success': True,
            'data': summary,
        })
    except Exception as e:
        logger.error(f"get_role_overlap_summary failed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# v1.4 修复：用 helper 注册 v1+v2 双路由（v1 保留 6 个月过渡）
from meta.api._dual_route import add_dual_routes
add_dual_routes(overlap_bp, '/roles/<int:role_id>/overlaps', get_role_overlaps, ['GET'])
add_dual_routes(overlap_bp, '/roles/<int:role_id>/overlaps/summary', get_role_overlap_summary, ['GET'])
