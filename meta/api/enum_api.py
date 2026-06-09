# -*- coding: utf-8 -*-
"""
枚举值管理 API

提供枚举类型和枚举值的 CRUD 操作。
"""

from flask import Blueprint, request, jsonify
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

enum_bp = Blueprint('enum', __name__, url_prefix='/api/v1')

_data_source = None
_audit_interceptor = None

AUTH_ENABLED = os.environ.get('AUTH_ENABLED', 'false').lower() in ('true', '1', 'yes')


def init_enum_services(data_source=None, db_path=None):
    """初始化枚举服务"""
    global _data_source, _audit_interceptor
    if data_source:
        _data_source = data_source
        _ensure_enum_tables(data_source)
        from meta.services.audit_interceptor import AuditInterceptor
        _audit_interceptor = AuditInterceptor(data_source)

        if db_path is None:
            db_path = getattr(data_source, '_db_path', None)
        if db_path:
            try:
                from meta.scripts.migrate_enums import migrate_enums
                result = migrate_enums(db_path)
                logger.info(f"枚举迁移完成: 类型={result.get('types_created')}, 值={result.get('values_created')}")
            except Exception as e:
                logger.warning(f"枚举迁移失败（可能需要手动运行 migrate_enums.py）: {e}")


def _get_audit_interceptor():
    global _audit_interceptor
    if _audit_interceptor is None:
        init_enum_services()
    return _audit_interceptor


def _ensure_enum_tables(ds):
    """确保枚举表存在

    [FIX 2026-06-04] 移除 updated_at DATETIME 列：遵循 audit_aspect 设计，
    updated_at 是 virtual 字段（从 audit_logs 实时计算），不在表里物理存储。
    已存在表的迁移由 init_database.py / 一次性 ALTER 脚本负责。
    """
    try:
        ds.execute("""
            CREATE TABLE IF NOT EXISTS enum_types (
                id VARCHAR(200) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                category VARCHAR(200) NOT NULL,
                mutability VARCHAR(200) NOT NULL,
                dimension_schema TEXT,
                description TEXT,
                created_at DATETIME
            )
        """)
        ds.execute("""
            CREATE TABLE IF NOT EXISTS enum_values (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enum_type_id VARCHAR(200) NOT NULL,
                code VARCHAR(200) NOT NULL,
                name VARCHAR(200) NOT NULL,
                name_en VARCHAR(200),
                dimensions TEXT,
                sort_order INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                is_system INTEGER DEFAULT 0,
                parent_code VARCHAR(200),
                metadata TEXT,
                created_at DATETIME,
                FOREIGN KEY (enum_type_id) REFERENCES enum_types(id),
                UNIQUE(enum_type_id, code)
            )
        """)
    except Exception as e:
        logger.warning(f"Failed to ensure enum tables: {e}")


# [FIX 2026-06-04] 批量从 audit_logs 实时计算 updated_at（virtual 字段）。
# 遵循 aspects.yaml 中 audit_aspect 的 derive_rule：
#   updated_at = MAX(audit_logs.created_at) WHERE action='UPDATE'
#   若无 UPDATE 日志则 fallback 到记录自身的 created_at
# 一次性 GROUP BY 批量查询，避免 N+1。
def _enrich_updated_at(records, object_type):
    """为 records 列表中每条记录计算 updated_at（virtual 字段，来自 audit_logs）"""
    if not records:
        return records
    # 提取 id 列表（用字符串以避免 int/str 类型不匹配）
    record_ids = []
    for r in records:
        rid = r.get('id')
        if rid is not None:
            record_ids.append(str(rid))

    if not record_ids:
        for r in records:
            r['updated_at'] = r.get('created_at')
        return records

    # 批量查询：每个 object_id 最近一次 UPDATE 的时间
    placeholders = ','.join(['?'] * len(record_ids))
    update_times = {}
    try:
        cursor = _data_source.execute(
            f"SELECT object_id, MAX(created_at) as max_update_at "
            f"FROM audit_logs "
            f"WHERE object_type = ? AND object_id IN ({placeholders}) "
            f"AND action = 'UPDATE' "
            f"GROUP BY object_id",
            [object_type] + record_ids
        )
        for row in cursor.fetchall():
            if isinstance(row, dict):
                oid = str(row.get('object_id'))
                ts = row.get('max_update_at')
            else:
                oid = str(row[0])
                ts = row[1] if len(row) > 1 else None
            if ts:
                update_times[oid] = ts
    except Exception as e:
        logger.debug(f"[_enrich_updated_at] audit_logs query skipped: {e}")
        update_times = {}

    # 应用：UPDATE 时间存在则用之，否则 fallback 到 created_at
    for record in records:
        rid = str(record.get('id'))
        if rid in update_times:
            record['updated_at'] = update_times[rid]
        else:
            record['updated_at'] = record.get('created_at')
    return records


def _get_data_source():
    global _data_source
    if _data_source is None:
        from meta.api.manage_api import _get_data_source as get_manage_ds
        _data_source = get_manage_ds()
    return _data_source


def _api_error(message, error_code='INTERNAL_ERROR', status_code=400, detail=None):
    response = {
        'success': False,
        'error_code': error_code,
        'message': message
    }
    if detail and os.environ.get('FLASK_DEBUG') == '1':
        response['detail'] = detail
    return jsonify(response), status_code


def _api_success(data=None, message='Success', **kwargs):
    response = {
        'success': True,
        'message': message
    }
    if data is not None:
        response['data'] = data
    response.update(kwargs)
    return jsonify(response)


def _auth_required(f):
    """认证装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if AUTH_ENABLED:
            from meta.services.auth_middleware import login_required
            return login_required(f)(*args, **kwargs)
        return f(*args, **kwargs)
    return decorated_function


def _admin_required(f):
    """管理员权限装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if AUTH_ENABLED:
            from meta.services.auth_middleware import is_admin
            if not is_admin():
                return _api_error('需要管理员权限', 'FORBIDDEN', 403)
        return f(*args, **kwargs)
    return decorated_function


def _row_to_dict(cursor, row):
    """将 tuple row 转换为 dict"""
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


# ============================================
# 枚举类型 API
# ============================================

@enum_bp.route('/enum-types', methods=['GET'])
@_auth_required
def list_enum_types():
    """获取枚举类型列表"""
    try:
        ds = _get_data_source()
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', request.args.get('pageSize', 20, type=int), type=int)
        keyword = request.args.get('keyword', '')
        category = request.args.get('category', '')
        mutability = request.args.get('mutability', '')
        
        sql = "SELECT * FROM enum_types WHERE 1=1"
        params = []
        
        if keyword:
            sql += " AND (id LIKE ? OR name LIKE ?)"
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        
        if category:
            sql += " AND category = ?"
            params.append(category)
        
        if mutability:
            sql += " AND mutability = ?"
            params.append(mutability)
        
        count_sql = f"SELECT COUNT(*) as total FROM ({sql})"
        cursor = ds.execute(count_sql, params)
        total = cursor.fetchone()[0]
        
        sql += " ORDER BY id LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        
        cursor = ds.execute(sql, params)
        rows = cursor.fetchall()
        result = [_row_to_dict(cursor, row) for row in rows]

        # [FR-006] 批量获取 value_count, 避免 N+1 查询
        if result:
            enum_ids = [row['id'] for row in result]
            placeholders = ','.join(['?'] * len(enum_ids))
            cursor2 = ds.execute(
                f"SELECT enum_type_id, COUNT(*) as cnt FROM enum_values "
                f"WHERE enum_type_id IN ({placeholders}) GROUP BY enum_type_id",
                enum_ids
            )
            count_map = dict(cursor2.fetchall())
        else:
            count_map = {}

        for row in result:
            row['value_count'] = count_map.get(row['id'], 0)
            row['dimension_count'] = _get_dimension_count(row.get('dimension_schema'))

        # [FIX 2026-06-04] 补充 virtual 字段 updated_at（从 audit_logs 计算）
        _enrich_updated_at(result, 'enum_type')

        return _api_success({
            'data': result,
            'total': total,
            'page': page,
            'page_size': page_size
        })
    except Exception as e:
        logger.exception("获取枚举类型列表失败")
        return _api_error(str(e), 'LIST_ENUM_TYPES_ERROR')


@enum_bp.route('/enum-types/<enum_type_id>', methods=['GET'])
@_auth_required
def get_enum_type(enum_type_id):
    """获取枚举类型详情"""
    try:
        ds = _get_data_source()
        sql = "SELECT * FROM enum_types WHERE id = ?"
        cursor = ds.execute(sql, [enum_type_id])
        row = cursor.fetchone()
        
        if not row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        
        enum_type = _row_to_dict(cursor, row)
        enum_type['value_count'] = _get_enum_value_count(ds, enum_type_id)
        enum_type['dimension_count'] = _get_dimension_count(enum_type.get('dimension_schema'))
        
        # 获取变更历史
        try:
            logger.info(f"正在查询枚举类型 {enum_type_id} 的变更历史...")
            cursor = ds.execute("""
                SELECT * FROM audit_logs
                WHERE object_type = 'enum_type' AND object_id = ?
                ORDER BY created_at DESC
                LIMIT 50
            """, [enum_type_id])
            history_rows = cursor.fetchall()
            change_history = []
            for history_row in history_rows:
                history_dict = _row_to_dict(cursor, history_row)
                change_history.append(history_dict)
            enum_type['change_history'] = change_history
            logger.info(f"成功获取 {len(change_history)} 条变更历史记录")
        except Exception as history_error:
            logger.warning(f"获取枚举类型变更历史失败: {history_error}")
            import traceback
            logger.warning(traceback.format_exc())
            enum_type['change_history'] = []

        # [FIX 2026-06-04] 补充 virtual 字段 updated_at（从 audit_logs 计算）
        _enrich_updated_at([enum_type], 'enum_type')

        return _api_success(enum_type)
    except Exception as e:
        logger.exception("获取枚举类型详情失败")
        return _api_error(str(e), 'GET_ENUM_TYPE_ERROR')


@enum_bp.route('/enum-types', methods=['POST'])
@_auth_required
@_admin_required
def create_enum_type():
    """创建枚举类型（仅业务枚举）"""
    try:
        ds = _get_data_source()
        data = request.get_json()
        
        enum_type_id = data.get('id')
        name = data.get('name')
        category = data.get('category', 'business')
        mutability = data.get('mutability', 'extensible')
        dimension_schema = data.get('dimension_schema')
        description = data.get('description', '')
        
        if not enum_type_id or not name:
            return _api_error('编码和名称不能为空', 'VALIDATION_ERROR')
        
        import json
        dimension_schema_str = json.dumps(dimension_schema) if dimension_schema else None
        
        now = datetime.now().isoformat()
        sql = """
            INSERT INTO enum_types (id, name, category, mutability, dimension_schema, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        ds.execute(sql, [enum_type_id, name, category, mutability, dimension_schema_str, description, now])
        ds.commit()
        
        user_id = None
        user_name = 'system'
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                user_id = getattr(current_user, 'id', None)
                user_name = getattr(current_user, 'username', 'system') or getattr(current_user, 'name', 'system')
        except:
            pass
        
        _get_audit_interceptor().log_create(
            object_type='enum_type',
            object_id=enum_type_id,
            data={'name': name, 'category': category, 'description': description},
            user_id=str(user_id) if user_id else None,
            user_name=user_name,
        )
        
        return _api_success({'id': enum_type_id}, '创建成功')
    except Exception as e:
        logger.exception("创建枚举类型失败")
        if 'UNIQUE constraint' in str(e):
            return _api_error('枚举类型编码已存在', 'DUPLICATE_ID')
        return _api_error(str(e), 'CREATE_ENUM_TYPE_ERROR')


@enum_bp.route('/enum-types/<enum_type_id>', methods=['PUT'])
@_auth_required
@_admin_required
def update_enum_type(enum_type_id):
    """更新枚举类型"""
    try:
        ds = _get_data_source()
        data = request.get_json()
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [enum_type_id])
        existing = cursor.fetchone()
        if not existing:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        
        existing = _row_to_dict(cursor, existing)
        if existing['category'] == 'system':
            return _api_error('系统枚举不可修改', 'SYSTEM_ENUM_IMMUTABLE')
        
        name = data.get('name', existing['name'])
        mutability = data.get('mutability', existing['mutability'])
        dimension_schema = data.get('dimension_schema')
        description = data.get('description', existing['description'])
        
        import json
        dimension_schema_str = json.dumps(dimension_schema) if dimension_schema else existing.get('dimension_schema')
        
        now = datetime.now().isoformat()
        sql = """
            UPDATE enum_types 
            SET name = ?, mutability = ?, dimension_schema = ?, description = ?
            WHERE id = ?
        """
        ds.execute(sql, [name, mutability, dimension_schema_str, description, enum_type_id])
        ds.commit()
        
        changes = {}
        if name != existing.get('name'):
            changes['name'] = (existing.get('name'), name)
        if mutability != existing.get('mutability'):
            changes['mutability'] = (existing.get('mutability'), mutability)
        if description != existing.get('description'):
            changes['description'] = (existing.get('description'), description)
        
        user_id = None
        user_name = 'system'
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                user_id = getattr(current_user, 'id', None)
                user_name = getattr(current_user, 'username', 'system') or getattr(current_user, 'name', 'system')
        except:
            pass
        
        if changes:
            new_data = existing.copy()
            new_data.update({k: v for k, (_, v) in changes.items()})
            _get_audit_interceptor().log_update(
                object_type='enum_type',
                object_id=enum_type_id,
                old_data=existing,
                new_data=new_data,
                user_id=str(user_id) if user_id else None,
                user_name=user_name,
            )
        
        return _api_success({'id': enum_type_id}, '更新成功')
    except Exception as e:
        logger.exception("更新枚举类型失败")
        return _api_error(str(e), 'UPDATE_ENUM_TYPE_ERROR')


@enum_bp.route('/enum-types/<enum_type_id>', methods=['DELETE'])
@_auth_required
@_admin_required
def delete_enum_type(enum_type_id):
    """删除枚举类型（仅无值时）"""
    try:
        ds = _get_data_source()
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [enum_type_id])
        existing = cursor.fetchone()
        if not existing:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        
        existing = _row_to_dict(cursor, existing)
        if existing['category'] == 'system':
            return _api_error('系统枚举不可删除', 'SYSTEM_ENUM_IMMUTABLE')
        
        value_count = _get_enum_value_count(ds, enum_type_id)
        if value_count > 0:
            return _api_error(f'该枚举类型下有 {value_count} 个枚举值，无法删除', 'HAS_VALUES')
        
        user_id = None
        user_name = 'system'
        try:
            from flask_login import current_user
            if current_user.is_authenticated:
                user_id = getattr(current_user, 'id', None)
                user_name = getattr(current_user, 'username', 'system') or getattr(current_user, 'name', 'system')
        except:
            pass
        
        _get_audit_interceptor().log_delete(
            object_type='enum_type',
            object_id=enum_type_id,
            data={'name': existing.get('name'), 'category': existing.get('category'), 'description': existing.get('description')},
            user_id=str(user_id) if user_id else None,
            user_name=user_name,
        )
        
        ds.execute("DELETE FROM enum_types WHERE id = ?", [enum_type_id])
        ds.commit()
        
        return _api_success(message='删除成功')
    except Exception as e:
        logger.exception("删除枚举类型失败")
        return _api_error(str(e), 'DELETE_ENUM_TYPE_ERROR')


@enum_bp.route('/enum-types/<enum_type_id>/history', methods=['GET'])
@_auth_required
def get_enum_type_history(enum_type_id):
    """获取枚举类型的变更历史"""
    try:
        ds = _get_data_source()
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [enum_type_id])
        enum_type_row = cursor.fetchone()
        if not enum_type_row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', request.args.get('pageSize', 20), type=int)
        
        cursor = ds.execute("""
            SELECT * FROM audit_logs 
            WHERE object_type = 'enum_type' AND object_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, [enum_type_id, page_size, (page - 1) * page_size])
        
        history_rows = cursor.fetchall()
        result = []
        for row in history_rows:
            row_dict = _row_to_dict(cursor, row)
            result.append(row_dict)
        
        cursor = ds.execute("""
            SELECT COUNT(*) as total FROM audit_logs 
            WHERE object_type = 'enum_type' AND object_id = ?
        """, [enum_type_id])
        total = cursor.fetchone()[0]
        
        return _api_success({
            'data': result,
            'total': total,
            'page': page,
            'page_size': page_size
        })
    except Exception as e:
        logger.exception("获取枚举类型历史失败")
        return _api_error(str(e), 'GET_ENUM_TYPE_HISTORY_ERROR')


# ============================================
# 枚举值 API
# ============================================

@enum_bp.route('/enums/<enum_type_id>/options', methods=['GET'])
@_auth_required
def get_enum_options(enum_type_id):
    """高速枚举选项端点 - 轻量级，仅返回 {code, name} 列表"""
    try:
        ds = _get_data_source()

        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [enum_type_id])
        enum_type_row = cursor.fetchone()
        if not enum_type_row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)

        is_active = request.args.get('is_active', '')
        page_size = request.args.get('pageSize', 1000, type=int)

        sql = "SELECT code, name FROM enum_values WHERE enum_type_id = ?"
        params = [enum_type_id]

        if is_active != '':
            sql += " AND is_active = ?"
            params.append(1 if is_active.lower() == 'true' else 0)

        sql += " ORDER BY sort_order, code LIMIT ?"
        params.append(page_size)

        cursor = ds.execute(sql, params)
        rows = cursor.fetchall()

        result = [{'code': r[0], 'name': r[1]} for r in rows]

        return _api_success(result)
    except Exception as e:
        logger.exception("获取枚举选项失败")
        return _api_error(str(e), 'GET_ENUM_OPTIONS_ERROR')


@enum_bp.route('/enum-types/<enum_type_id>/values', methods=['GET'])
@_auth_required
def list_enum_values(enum_type_id):
    """获取枚举值列表（支持维度过滤）"""
    try:
        ds = _get_data_source()
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [enum_type_id])
        enum_type_row = cursor.fetchone()
        if not enum_type_row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        enum_type = _row_to_dict(cursor, enum_type_row)
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 50, type=int)
        keyword = request.args.get('keyword', '')
        is_active = request.args.get('is_active', '')
        
        dimension_filters = {}
        for key in request.args:
            if key not in ['page', 'pageSize', 'keyword', 'is_active']:
                dimension_filters[key] = request.args.get(key)
        
        sql = "SELECT * FROM enum_values WHERE enum_type_id = ?"
        params = [enum_type_id]
        
        if keyword:
            sql += " AND (code LIKE ? OR name LIKE ?)"
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        
        if is_active != '':
            sql += " AND is_active = ?"
            params.append(1 if is_active.lower() == 'true' else 0)
        
        if dimension_filters:
            import json
            for dim_key, dim_value in dimension_filters.items():
                sql += f" AND json_extract(dimensions, '$.{dim_key}') = ?"
                params.append(dim_value)
        
        count_sql = f"SELECT COUNT(*) as total FROM ({sql})"
        cursor = ds.execute(count_sql, params)
        total = cursor.fetchone()[0]
        
        sql += " ORDER BY sort_order, code LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        
        cursor = ds.execute(sql, params)
        rows = cursor.fetchall()
        result = []
        for row in rows:
            row_dict = _row_to_dict(cursor, row)
            if row_dict.get('dimensions'):
                import json
                try:
                    row_dict['dimensions'] = json.loads(row_dict['dimensions'])
                except:
                    pass
            if row_dict.get('metadata'):
                import json
                try:
                    row_dict['metadata'] = json.loads(row_dict['metadata'])
                except:
                    pass
            result.append(row_dict)

        # [FIX 2026-06-04] 补充 virtual 字段 updated_at（从 audit_logs 计算）
        _enrich_updated_at(result, 'enum_value')

        return _api_success({
            'data': result,
            'total': total,
            'page': page,
            'page_size': page_size,
            'enum_type': enum_type
        })
    except Exception as e:
        logger.exception("获取枚举值列表失败")
        return _api_error(str(e), 'LIST_ENUM_VALUES_ERROR')


@enum_bp.route('/enum-values/<int:value_id>', methods=['GET'])
@_auth_required
def get_enum_value(value_id):
    """获取枚举值详情"""
    try:
        ds = _get_data_source()
        sql = "SELECT * FROM enum_values WHERE id = ?"
        cursor = ds.execute(sql, [value_id])
        row = cursor.fetchone()
        
        if not row:
            return _api_error('枚举值不存在', 'NOT_FOUND', 404)
        
        value = _row_to_dict(cursor, row)
        if value.get('dimensions'):
            import json
            try:
                value['dimensions'] = json.loads(value['dimensions'])
            except:
                pass
        if value.get('metadata'):
            import json
            try:
                value['metadata'] = json.loads(value['metadata'])
            except:
                pass

        # [FIX 2026-06-04] 补充 virtual 字段 updated_at（从 audit_logs 计算）
        _enrich_updated_at([value], 'enum_value')

        return _api_success(value)
    except Exception as e:
        logger.exception("获取枚举值详情失败")
        return _api_error(str(e), 'GET_ENUM_VALUE_ERROR')


@enum_bp.route('/enum-types/<enum_type_id>/values', methods=['POST'])
@_auth_required
@_admin_required
def create_enum_value(enum_type_id):
    """创建枚举值"""
    try:
        ds = _get_data_source()
        data = request.get_json()
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [enum_type_id])
        enum_type_row = cursor.fetchone()
        if not enum_type_row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        enum_type = _row_to_dict(cursor, enum_type_row)
        
        if enum_type['mutability'] == 'locked':
            return _api_error('该枚举类型已锁定，不可添加值', 'ENUM_LOCKED')
        
        code = data.get('code')
        name = data.get('name')
        name_en = data.get('name_en', '')
        dimensions = data.get('dimensions', {})
        sort_order = data.get('sort_order', 0)
        is_active = data.get('is_active', True)
        is_system = data.get('is_system', False)
        parent_code = data.get('parent_code', '')
        metadata = data.get('metadata', {})
        
        if not code or not name:
            return _api_error('编码和名称不能为空', 'VALIDATION_ERROR')
        
        cursor = ds.execute(
            "SELECT id FROM enum_values WHERE enum_type_id = ? AND code = ?",
            [enum_type_id, code]
        )
        existing = cursor.fetchone()
        if existing:
            return _api_error('该编码已存在', 'DUPLICATE_CODE')
        
        import json
        dimensions_str = json.dumps(dimensions) if dimensions else None
        metadata_str = json.dumps(metadata) if metadata else None
        
        now = datetime.now().isoformat()
        sql = """
            INSERT INTO enum_values 
            (enum_type_id, code, name, name_en, dimensions, sort_order, is_active, is_system, parent_code, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        ds.execute(sql, [
            enum_type_id, code, name, name_en, dimensions_str, sort_order, 
            1 if is_active else 0, 1 if is_system else 0, parent_code, metadata_str, now
        ])
        ds.commit()
        
        return _api_success({'code': code}, '创建成功')
    except Exception as e:
        logger.exception("创建枚举值失败")
        return _api_error(str(e), 'CREATE_ENUM_VALUE_ERROR')


@enum_bp.route('/enum-values/<int:value_id>', methods=['PUT'])
@_auth_required
@_admin_required
def update_enum_value(value_id):
    """更新枚举值"""
    try:
        ds = _get_data_source()
        data = request.get_json()
        
        cursor = ds.execute("SELECT * FROM enum_values WHERE id = ?", [value_id])
        existing_row = cursor.fetchone()
        if not existing_row:
            return _api_error('枚举值不存在', 'NOT_FOUND', 404)
        existing = _row_to_dict(cursor, existing_row)
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [existing['enum_type_id']])
        enum_type_row = cursor.fetchone()
        if not enum_type_row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        enum_type = _row_to_dict(cursor, enum_type_row)
        
        if enum_type['mutability'] == 'locked':
            return _api_error('该枚举类型已锁定，不可修改值', 'ENUM_LOCKED')
        
        name = data.get('name', existing['name'])
        name_en = data.get('name_en', existing.get('name_en', ''))
        dimensions = data.get('dimensions')
        sort_order = data.get('sort_order', existing.get('sort_order', 0))
        is_active = data.get('is_active', bool(existing.get('is_active', 1)))
        parent_code = data.get('parent_code', existing.get('parent_code', ''))
        metadata = data.get('metadata')
        
        import json
        dimensions_str = json.dumps(dimensions) if dimensions is not None else existing.get('dimensions')
        metadata_str = json.dumps(metadata) if metadata is not None else existing.get('metadata')
        
        now = datetime.now().isoformat()
        sql = """
            UPDATE enum_values 
            SET name = ?, name_en = ?, dimensions = ?, sort_order = ?, is_active = ?, parent_code = ?, metadata = ?
            WHERE id = ?
        """
        ds.execute(sql, [
            name, name_en, dimensions_str, sort_order, 1 if is_active else 0, parent_code, metadata_str, value_id
        ])
        ds.commit()
        
        return _api_success({'id': value_id}, '更新成功')
    except Exception as e:
        logger.exception("更新枚举值失败")
        return _api_error(str(e), 'UPDATE_ENUM_VALUE_ERROR')


@enum_bp.route('/enum-values/<int:value_id>', methods=['DELETE'])
@_auth_required
@_admin_required
def delete_enum_value(value_id):
    """删除枚举值"""
    try:
        ds = _get_data_source()
        
        cursor = ds.execute("SELECT * FROM enum_values WHERE id = ?", [value_id])
        existing_row = cursor.fetchone()
        if not existing_row:
            return _api_error('枚举值不存在', 'NOT_FOUND', 404)
        existing = _row_to_dict(cursor, existing_row)
        
        if existing.get('is_system'):
            return _api_error('系统预置值不可删除', 'SYSTEM_VALUE_IMMUTABLE')
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [existing['enum_type_id']])
        enum_type_row = cursor.fetchone()
        if not enum_type_row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        enum_type = _row_to_dict(cursor, enum_type_row)
        
        if enum_type['mutability'] == 'locked':
            return _api_error('该枚举类型已锁定，不可删除值', 'ENUM_LOCKED')
        
        ds.execute("DELETE FROM enum_values WHERE id = ?", [value_id])
        ds.commit()
        
        return _api_success(message='删除成功')
    except Exception as e:
        logger.exception("删除枚举值失败")
        return _api_error(str(e), 'DELETE_ENUM_VALUE_ERROR')


# ============================================
# 辅助函数
# ============================================

def _get_enum_value_count(ds, enum_type_id):
    """获取枚举类型的值数量"""
    try:
        cursor = ds.execute("SELECT COUNT(*) as cnt FROM enum_values WHERE enum_type_id = ?", [enum_type_id])
        result = cursor.fetchone()
        return result[0] if result else 0
    except:
        return 0


def _get_dimension_count(dimension_schema):
    """获取维度数量"""
    if not dimension_schema:
        return 0
    try:
        import json
        if isinstance(dimension_schema, str):
            schema = json.loads(dimension_schema)
        else:
            schema = dimension_schema
        if isinstance(schema, list):
            return len(schema)
        return 0
    except:
        return 0


@enum_bp.route('/enum-values', methods=['GET'])
@_auth_required
def query_enum_values():
    """查询枚举值（支持维度过滤）
    
    支持参数：
    - enum_type_id: 枚举类型ID（必填）
    - dimension: 维度键（可选，与 value 配合使用）
    - value: 维度值（可选，与 dimension 配合使用）
    - 其他维度参数: 可直接传递 dimension_key=value 格式
    
    示例：
    - /api/v1/enum-values?enum_type_id=relation_type&dimension=direction&value=PUSH
    - /api/v1/enum-values?enum_type_id=relation_type&direction=PUSH&category=DATA_FLOW
    """
    try:
        ds = _get_data_source()
        enum_type_id = request.args.get('enum_type_id')
        
        if not enum_type_id:
            return _api_error('enum_type_id 参数必填', 'VALIDATION_ERROR')
        
        cursor = ds.execute("SELECT * FROM enum_types WHERE id = ?", [enum_type_id])
        enum_type_row = cursor.fetchone()
        if not enum_type_row:
            return _api_error('枚举类型不存在', 'NOT_FOUND', 404)
        enum_type = _row_to_dict(cursor, enum_type_row)
        
        dimension = request.args.get('dimension')
        value = request.args.get('value')
        
        dimension_filters = {}
        if dimension and value:
            dimension_filters[dimension] = value
        
        for key in request.args:
            if key not in ['enum_type_id', 'dimension', 'value', 'page', 'pageSize', 'keyword', 'is_active']:
                if key != 'dimension' and key != 'value':
                    dimension_filters[key] = request.args.get(key)
        
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 100, type=int)
        keyword = request.args.get('keyword', '')
        is_active = request.args.get('is_active', '')
        
        sql = "SELECT * FROM enum_values WHERE enum_type_id = ?"
        params = [enum_type_id]
        
        if keyword:
            sql += " AND (code LIKE ? OR name LIKE ?)"
            params.extend([f'%{keyword}%', f'%{keyword}%'])
        
        if is_active != '':
            sql += " AND is_active = ?"
            params.append(1 if is_active.lower() == 'true' else 0)
        
        if dimension_filters:
            import json
            for dim_key, dim_value in dimension_filters.items():
                sql += f" AND json_extract(dimensions, '$.{dim_key}') = ?"
                params.append(dim_value)
        
        count_sql = f"SELECT COUNT(*) as total FROM ({sql})"
        cursor = ds.execute(count_sql, params)
        total = cursor.fetchone()[0]
        
        sql += " ORDER BY sort_order, code LIMIT ? OFFSET ?"
        params.extend([page_size, (page - 1) * page_size])
        
        cursor = ds.execute(sql, params)
        rows = cursor.fetchall()
        result = []
        for row in rows:
            row_dict = _row_to_dict(cursor, row)
            if row_dict.get('dimensions'):
                import json
                try:
                    row_dict['dimensions'] = json.loads(row_dict['dimensions'])
                except:
                    pass
            if row_dict.get('metadata'):
                import json
                try:
                    row_dict['metadata'] = json.loads(row_dict['metadata'])
                except:
                    pass
            result.append(row_dict)
        
        return _api_success({
            'data': result,
            'total': total,
            'page': page,
            'page_size': page_size,
            'enum_type': {
                'id': enum_type['id'],
                'name': enum_type['name'],
                'category': enum_type['category'],
                'dimension_schema': json.loads(enum_type.get('dimension_schema', '[]')) if enum_type.get('dimension_schema') else []
            }
        })
    except Exception as e:
        logger.exception("查询枚举值失败")
        return _api_error(str(e), 'QUERY_ENUM_VALUES_ERROR')


def get_enum_value_name(ds, enum_type_id: str, code: str) -> str:
    """获取枚举值的名称
    
    Args:
        ds: 数据源
        enum_type_id: 枚举类型ID
        code: 枚举值编码
        
    Returns:
        枚举值名称，如果未找到返回编码本身
    """
    if not enum_type_id or not code:
        return code or ''
    
    try:
        cursor = ds.execute(
            "SELECT name FROM enum_values WHERE enum_type_id = ? AND code = ? AND is_active = 1",
            [enum_type_id, code]
        )
        row = cursor.fetchone()
        if row:
            return row[0]
    except Exception as e:
        logger.warning(f"获取枚举值名称失败: {e}")
    
    return code
