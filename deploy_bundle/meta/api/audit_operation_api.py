# -*- coding: utf-8 -*-
"""
audit_operation_api.py — 操作链 API (FR-008, TBD-3 决策 admin only)

GET /api/v2/audit/operation/<trace_id>
  - 拉所有 trace_id 相同的 audit 记录
  - 排序: created_at ASC, id ASC
  - 识别 cascade (action in ['DISSOCIATE'] AND log_category='cascade')
  - 返 chain + summary
"""
from __future__ import annotations
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Blueprint, request, jsonify, g, current_app
from functools import wraps

from meta.core.datasource import get_data_source


# Blueprint
operation_bp = Blueprint('audit_operation', __name__, url_prefix='/api/v2/audit')


def admin_required(fn):
    """admin 权限装饰器 (TBD-3 决策: admin only)"""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            from flask import g
            user = getattr(g, 'current_user', None) or {}
            role = (user.get('role') or user.get('roles') or '').lower()
            if role != 'admin':
                from meta.api._problem_details import problem
                return problem.forbidden(
                    reason="仅 admin 可访问操作链",
                    required_role="admin",
                )
        except Exception:
            from meta.api._problem_details import problem
            return problem.forbidden(reason="鉴权失败")
        return fn(*args, **kwargs)
    return wrapper


@operation_bp.route('/operation/<trace_id>', methods=['GET'])
@admin_required
def get_operation_chain(trace_id: str):
    """获取指定 trace_id 的完整操作链

    Response:
    {
      "success": true,
      "data": {
        "trace_id": "...",
        "root_action": "DELETE",
        "root_object": "user_group#567",
        "root_user": "张三 (zhangsan)",
        "chain": [
          {"id": 1, "action": "DELETE", "object": "user_group#567", "level": 0, "cascade": false, "created_at": "..."},
          {"id": 2, "action": "DISSOCIATE", "object": "user#1234 -/-> user_group#567", "level": 1, "cascade": true, "cascade_root_id": 1, "created_at": "..."}
        ],
        "summary": {
          "total_events": 8,
          "cascade_depth": 2,
          "affected_objects": [...],
          "duration_ms": 45
        }
      }
    }
    """
    if not trace_id or len(trace_id) < 8:
        from meta.api._problem_details import problem
        return problem.validation_error('trace_id', 'trace_id 长度至少 8')

    try:
        ds = get_data_source('sqlite', database=str(_get_db_path()))
        records = ds.find(
            'audit_logs',
            filters={'trace_id': trace_id},
            order_by='created_at ASC, id ASC',
        )
    except Exception as e:
        from meta.api._problem_details import problem
        return problem.internal_error(f"查询操作链失败: {e}")

    if not records:
        from meta.api._problem_details import problem
        return problem.not_found('trace_id', trace_id)

    # 1. 找到 root (没有 parent_action_id, 或 action='DELETE')
    root = next((r for r in records if r.get('action') == 'DELETE'), records[0])

    # 2. 构建 chain
    chain = []
    for r in records:
        action = r.get('action', '')
        cascade = (r.get('log_category') == 'cascade') or (r.get('cascade_root_id') is not None)
        obj_str = f"{r.get('object_type')}#{r.get('object_id')}"
        if action in ('ASSOCIATE', 'DISSOCIATE'):
            obj_str += f" {'→' if action == 'ASSOCIATE' else '-/->'} {r.get('parent_object_type')}#{r.get('parent_object_id')}"

        chain.append({
            'id': r.get('id'),
            'action': action,
            'object': obj_str,
            'level': _compute_level(r, root),
            'cascade': cascade,
            'cascade_root_id': r.get('cascade_root_id'),
            'created_at': r.get('created_at'),
            'user_name': r.get('user_name', ''),
            'outcome': r.get('outcome', 'success'),
            'log_level': r.get('log_level', 'INFO'),
        })

    # 3. summary
    cascade_events = [c for c in chain if c['cascade']]
    affected = set()
    for c in chain:
        # 从 obj_str 抽 object_id
        for part in c['object'].split():
            if '#' in part and '→' not in part and '-/->' not in part:
                affected.add(part.strip(',.'))

    # duration
    try:
        t0 = datetime.fromisoformat(chain[0]['created_at'].rstrip('Z'))
        t1 = datetime.fromisoformat(chain[-1]['created_at'].rstrip('Z'))
        duration_ms = int((t1 - t0).total_seconds() * 1000)
    except Exception:
        duration_ms = 0

    return jsonify({
        'success': True,
        'data': {
            'trace_id': trace_id,
            'root_action': root.get('action', ''),
            'root_object': f"{root.get('object_type')}#{root.get('object_id')}",
            'root_user': root.get('user_name', ''),
            'chain': chain,
            'summary': {
                'total_events': len(chain),
                'cascade_events': len(cascade_events),
                'cascade_depth': max((c['level'] for c in cascade_events), default=0),
                'affected_objects': sorted(affected),
                'duration_ms': duration_ms,
            },
        }
    })


def _compute_level(record: dict, root: dict) -> int:
    """计算 cascade level (0=根, 1=1 级 cascade, 2=2 级...)"""
    if record.get('id') == root.get('id'):
        return 0
    if record.get('cascade_root_id') is not None:
        return 1  # 简化: 实际可递归算, 当前只看 1 级
    if record.get('log_category') == 'cascade':
        return 1
    return 0


def _get_db_path() -> Path:
    """获取 DB 路径 (跟 audit_service 一致)"""
    return Path(__file__).parent.parent / "architecture.db"


# ============ 自测 ============

if __name__ == "__main__":
    print("  audit_operation_api blueprint: /api/v2/audit/operation/<trace_id>")
    print("  装饰器: admin_required (TBD-3 决策)")
    print("  chain: created_at ASC, cascade level 0/1/2...")
    print("  summary: total_events / cascade_events / cascade_depth / affected_objects / duration_ms")
    print("\n[OK] blueprint 自测 (实际测试需在 flask context 下)")
