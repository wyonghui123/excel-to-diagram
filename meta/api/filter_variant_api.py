# -*- coding: utf-8 -*-
"""
过滤变体 API
参考 SAP Fiori SmartFilterBar 的变体管理功能
"""

from flask import Blueprint, request, jsonify
import os
import json
from datetime import datetime

filter_variant_bp = Blueprint('filter_variant', __name__, url_prefix='/api/v1/filter-variants')

_db_path = None


def _get_db_path():
    global _db_path
    if _db_path is None:
        _db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'architecture.db')
    return _db_path


def _get_current_user_id():
    """获取当前用户ID"""
    from flask import g
    return getattr(g, 'user_id', None) or 1


def _is_admin():
    """检查是否为管理员"""
    from flask import g
    return getattr(g, 'is_admin', False)


def _execute_query(sql, params=(), fetch=True):
    """执行数据库查询"""
    import sqlite3
    db_path = _get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    try:
        cursor.execute(sql, params)
        if fetch:
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        else:
            conn.commit()
            return cursor.lastrowid
    finally:
        conn.close()


def _init_table():
    """初始化过滤变体表"""
    sql = '''
    CREATE TABLE IF NOT EXISTS filter_variants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        object_type TEXT NOT NULL,
        filters TEXT NOT NULL,
        user_id INTEGER,
        is_shared INTEGER DEFAULT 0,
        is_default INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )
    '''
    _execute_query(sql, fetch=False)
    
    _execute_query('CREATE INDEX IF NOT EXISTS idx_fv_user_obj ON filter_variants(user_id, object_type)', fetch=False)
    _execute_query('CREATE INDEX IF NOT EXISTS idx_fv_shared ON filter_variants(is_shared, object_type)', fetch=False)


@filter_variant_bp.before_request
def before_request():
    _init_table()


@filter_variant_bp.route('', methods=['GET'])
def list_variants():
    """获取过滤变体列表
    
    查询参数:
    - object_type: 对象类型（可选）
    - include_shared: 是否包含共享变体（默认true）
    """
    user_id = _get_current_user_id()
    object_type = request.args.get('object_type', '')
    include_shared = request.args.get('include_shared', 'true').lower() == 'true'
    
    sql = 'SELECT * FROM filter_variants WHERE 1=1'
    params = []
    
    if object_type:
        sql += ' AND object_type = ?'
        params.append(object_type)
    
    if include_shared:
        sql += ' AND (user_id = ? OR is_shared = 1)'
        params.append(user_id)
    else:
        sql += ' AND user_id = ?'
        params.append(user_id)
    
    sql += ' ORDER BY is_default DESC, updated_at DESC'
    
    variants = _execute_query(sql, params)
    
    for v in variants:
        v['is_shared'] = bool(v.get('is_shared', 0))
        v['is_default'] = bool(v.get('is_default', 0))
        if v.get('filters'):
            try:
                v['filters'] = json.loads(v['filters'])
            except:
                v['filters'] = {}
    
    return jsonify({
        'success': True,
        'data': variants
    })


@filter_variant_bp.route('/<int:variant_id>', methods=['GET'])
def get_variant(variant_id):
    """获取单个过滤变体"""
    user_id = _get_current_user_id()
    
    sql = 'SELECT * FROM filter_variants WHERE id = ? AND (user_id = ? OR is_shared = 1)'
    variant = _execute_query(sql, (variant_id, user_id))
    
    if not variant:
        return jsonify({'success': False, 'message': '变体不存在或无权访问'}), 404
    
    variant = variant[0]
    variant['is_shared'] = bool(variant.get('is_shared', 0))
    variant['is_default'] = bool(variant.get('is_default', 0))
    if variant.get('filters'):
        try:
            variant['filters'] = json.loads(variant['filters'])
        except:
            variant['filters'] = {}
    
    return jsonify({
        'success': True,
        'data': variant
    })


@filter_variant_bp.route('', methods=['POST'])
def create_variant():
    """创建过滤变体
    
    请求体:
    - name: 变体名称
    - object_type: 对象类型
    - filters: 过滤条件
    - is_shared: 是否共享（默认false）
    - is_default: 是否默认（默认false）
    """
    data = request.get_json() or {}
    user_id = _get_current_user_id()
    
    name = data.get('name', '').strip()
    object_type = data.get('object_type', '')
    filters = data.get('filters', {})
    is_shared = 1 if data.get('is_shared', False) else 0
    is_default = 1 if data.get('is_default', False) else 0
    
    if not name:
        return jsonify({'success': False, 'message': '变体名称不能为空'}), 400
    
    if not object_type:
        return jsonify({'success': False, 'message': '对象类型不能为空'}), 400
    
    if is_shared and not _is_admin():
        return jsonify({'success': False, 'message': '只有管理员可以创建共享变体'}), 403
    
    if is_default:
        _execute_query(
            'UPDATE filter_variants SET is_default = 0 WHERE user_id = ? AND object_type = ?',
            (user_id, object_type),
            fetch=False
        )
    
    now = datetime.now().isoformat()
    sql = '''
        INSERT INTO filter_variants (name, object_type, filters, user_id, is_shared, is_default, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    '''
    variant_id = _execute_query(
        sql,
        (name, object_type, json.dumps(filters), user_id, is_shared, is_default, now, now),
        fetch=False
    )
    
    return jsonify({
        'success': True,
        'data': {
            'id': variant_id,
            'name': name,
            'object_type': object_type,
            'filters': filters,
            'is_shared': bool(is_shared),
            'is_default': bool(is_default)
        }
    })


@filter_variant_bp.route('/<int:variant_id>', methods=['PUT'])
def update_variant(variant_id):
    """更新过滤变体"""
    data = request.get_json() or {}
    user_id = _get_current_user_id()
    
    existing = _execute_query(
        'SELECT * FROM filter_variants WHERE id = ? AND user_id = ?',
        (variant_id, user_id)
    )
    
    if not existing:
        return jsonify({'success': False, 'message': '变体不存在或无权修改'}), 404
    
    existing = existing[0]
    name = data.get('name', existing['name']).strip()
    filters = data.get('filters', json.loads(existing['filters'] or '{}'))
    is_shared = 1 if data.get('is_shared', existing['is_shared']) else 0
    is_default = 1 if data.get('is_default', False) else 0
    
    if is_shared and not _is_admin():
        return jsonify({'success': False, 'message': '只有管理员可以创建共享变体'}), 403
    
    if is_default:
        _execute_query(
            'UPDATE filter_variants SET is_default = 0 WHERE user_id = ? AND object_type = ?',
            (user_id, existing['object_type']),
            fetch=False
        )
    
    now = datetime.now().isoformat()
    _execute_query(
        'UPDATE filter_variants SET name = ?, filters = ?, is_shared = ?, is_default = ?, updated_at = ? WHERE id = ?',
        (name, json.dumps(filters), is_shared, is_default, now, variant_id),
        fetch=False
    )
    
    return jsonify({
        'success': True,
        'data': {
            'id': variant_id,
            'name': name,
            'filters': filters,
            'is_shared': bool(is_shared),
            'is_default': bool(is_default)
        }
    })


@filter_variant_bp.route('/<int:variant_id>', methods=['DELETE'])
def delete_variant(variant_id):
    """删除过滤变体"""
    user_id = _get_current_user_id()
    
    existing = _execute_query(
        'SELECT * FROM filter_variants WHERE id = ? AND user_id = ?',
        (variant_id, user_id)
    )
    
    if not existing:
        return jsonify({'success': False, 'message': '变体不存在或无权删除'}), 404
    
    _execute_query('DELETE FROM filter_variants WHERE id = ?', (variant_id,), fetch=False)
    
    return jsonify({
        'success': True,
        'message': '变体已删除'
    })


@filter_variant_bp.route('/<int:variant_id>/set-default', methods=['POST'])
def set_default_variant(variant_id):
    """设置默认变体"""
    user_id = _get_current_user_id()
    
    existing = _execute_query(
        'SELECT * FROM filter_variants WHERE id = ? AND (user_id = ? OR is_shared = 1)',
        (variant_id, user_id)
    )
    
    if not existing:
        return jsonify({'success': False, 'message': '变体不存在或无权访问'}), 404
    
    existing = existing[0]
    
    _execute_query(
        'UPDATE filter_variants SET is_default = 0 WHERE user_id = ? AND object_type = ?',
        (user_id, existing['object_type']),
        fetch=False
    )
    
    _execute_query(
        'UPDATE filter_variants SET is_default = 1 WHERE id = ?',
        (variant_id,),
        fetch=False
    )
    
    return jsonify({
        'success': True,
        'message': '已设置为默认变体'
    })
