"""
审计日志API
提供审计日志查询、导出等功能
"""

from flask import Blueprint, jsonify, request, g
from datetime import datetime
import csv
import io

audit_bp = Blueprint('audit', __name__)

from meta.core.datasource import get_data_source
from meta.api.auth_api import login_required, is_admin

_data_source = None


def init_audit_services(data_source=None):
    """初始化审计服务"""
    global _data_source
    _data_source = data_source

# 业务对象元数据定义 - 定义各对象类型的business key配置
BUSINESS_KEY_METADATA = {
    'user': {
        'primary': 'display_name',
        'secondary': 'username',
        'format': '{primary}({secondary})',
        'table': 'users',
        'fields': ['display_name', 'username']
    },
    'role': {
        'primary': 'name',
        'secondary': 'code',
        'format': '{primary}({secondary})',
        'table': 'roles',
        'fields': ['name', 'code']
    },
    'user_group': {
        'primary': 'name',
        'secondary': 'code',
        'format': '{primary}({secondary})',
        'table': 'user_groups',
        'fields': ['name', 'code']
    },
    'product': {
        'primary': 'name',
        'secondary': 'code',
        'format': '{primary}({secondary})',
        'table': 'products',
        'fields': ['name', 'code']
    },
    'version': {
        'primary': 'version_number',
        'secondary': 'product_id',
        'format': '{primary}',
        'table': 'versions',
        'fields': ['version_number']
    },
    'domain': {
        'primary': 'name',
        'secondary': 'code',
        'format': '{primary}',
        'table': 'domains',
        'fields': ['name']
    },
    'business_object': {
        'primary': 'name',
        'secondary': 'object_type',
        'format': '{primary}',
        'table': 'business_objects',
        'fields': ['name']
    },
    'relationship': {
        'primary': 'name',
        'secondary': 'relationship_type',
        'format': '{primary}',
        'table': 'relationships',
        'fields': ['name']
    },
    'annotation': {
        'primary': 'content',
        'secondary': 'category',
        'format': '{primary[:30]}...',
        'table': 'annotations',
        'fields': ['content']
    }
}


@audit_bp.route('/logs', methods=['GET'])
@login_required
def get_audit_logs():
    """查询审计日志列表"""
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        action = request.args.get('action', '')
        object_type = request.args.get('object_type', '')
        object_id = request.args.get('object_id', '')
        # [FIX 2026-06-12] 支持按 parent_object 查询 (角色/用户/用户组详情页"操作日志" tab)
        # 例如: RoleDetailDrawer 通过 parent_object_type='role' + parent_object_id=3606 拉日志
        parent_object_type = request.args.get('parent_object_type', '')
        parent_object_id = request.args.get('parent_object_id', '')
        user_name = request.args.get('user_name', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        log_category = request.args.get('log_category', '')
        log_level = request.args.get('log_level', '')
        sort_field = request.args.get('sort_field', 'created_at')
        sort_direction = request.args.get('sort_direction', 'desc')

        # 构建查询条件
        conditions = []
        params = []

        if action:
            conditions.append("action = ?")
            params.append(action)

        if object_type:
            conditions.append("object_type = ?")
            params.append(object_type)

        if object_id:
            conditions.append("object_id = ?")
            params.append(object_id)

        # [FIX 2026-06-12] parent_object 查询逻辑:
        # - 同时传 (object_type+object_id) 和 (parent_object_type+parent_object_id) 时, 用 OR 联合查询
        #   (角色自身日志 + 角色子对象日志一起返回)
        # - 只传 (parent_object_type+parent_object_id) 时, 走纯 parent_object 查询
        # - 只传 (object_type+object_id) 时, 走纯 object 查询 (向后兼容)
        # 重要: 走 OR 联合时, 必须 pop 掉前面已经加的 (object_type + object_id) 条件,
        #       否则会被 AND 收窄到 0 条
        if parent_object_type and parent_object_id:
            if object_type and object_id:
                # 移除刚才加的 object_type + object_id 单独条件, 改用 OR 联合
                if conditions and conditions[-1] == "object_id = ?":
                    conditions.pop()
                    params.pop()
                if conditions and conditions[-1] == "object_type = ?":
                    conditions.pop()
                    params.pop()
                conditions.append(
                    f"((object_type = ? AND object_id = ?) OR "
                    f"(parent_object_type = ? AND parent_object_id = ?))"
                )
                params.extend([object_type, object_id, parent_object_type, parent_object_id])
            else:
                # 仅 parent_object 查询
                conditions.append("parent_object_type = ?")
                params.append(parent_object_type)
                conditions.append("parent_object_id = ?")
                params.append(parent_object_id)
        elif parent_object_type:
            conditions.append("parent_object_type = ?")
            params.append(parent_object_type)
        elif parent_object_id:
            conditions.append("parent_object_id = ?")
            params.append(parent_object_id)

        if user_name:
            conditions.append("user_name LIKE ?")
            params.append(f"%{user_name}%")

        if start_date:
            conditions.append("created_at >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("created_at <= ?")
            params.append(end_date + ' 23:59:59')

        if log_category:
            conditions.append("log_category = ?")
            params.append(log_category)

        if log_level:
            conditions.append("log_level = ?")
            params.append(log_level)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        # 验证排序字段
        valid_sort_fields = ['id', 'object_type', 'object_id', 'action', 'user_name', 'log_category', 'log_level', 'created_at']
        if sort_field not in valid_sort_fields:
            sort_field = 'created_at'

        if sort_direction not in ['asc', 'desc']:
            sort_direction = 'desc'

        # 计算偏移量
        offset = (page - 1) * page_size

        # 查询总数
        count_sql = f"SELECT COUNT(*) FROM audit_logs WHERE {where_clause}"
        cursor = _data_source.execute(count_sql, params)
        total = cursor.fetchone()[0]

        # 查询数据
        query_sql = f"""
            SELECT id, object_type, object_id, action, field_name, old_value, new_value,
                   user_id, user_name, ip_address, user_agent, created_at, trace_id,
                   transaction_id, status, extra_data, parent_object_type, parent_object_id
            FROM audit_logs
            WHERE {where_clause}
            ORDER BY {sort_field} {sort_direction}
            LIMIT ? OFFSET ?
        """
        params.extend([page_size, offset])

        cursor = _data_source.execute(query_sql, params)
        columns = [desc[0] for desc in cursor.description]
        logs = []

        for row in cursor.fetchall():
            log = dict(zip(columns, row))
            # 转换None为空字符串
            for key, value in log.items():
                if value is None:
                    log[key] = ''

            # 生成business_key
            log['business_key'] = _generate_business_key(
                _data_source,
                log.get('object_type', ''),
                log.get('object_id', ''),
                log.get('field_name', ''),
                log.get('new_value', '')
            )

            # [FIX 2026-06-11] 解析 extra_data JSON: 提取 deleted_data (DELETE 明细)
            # 与 object_display (展示名) 字段, 供前端 drawer 渲染
            log['extra_data_parsed'] = _extract_deleted_data(log.pop('extra_data', ''))

            logs.append(log)

        return jsonify({
            'success': True,
            'data': logs,
            'total': total,
            'page': page,
            'page_size': page_size
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@audit_bp.route('/logs/<int:log_id>', methods=['GET'])
@login_required
def get_audit_log_detail(log_id):
    """查询审计日志详情"""
    try:
        cursor = _data_source.execute("""
            SELECT id, object_type, object_id, action, field_name, old_value, new_value,
                   user_id, user_name, ip_address, user_agent, created_at, trace_id,
                   transaction_id, status, retry_count, error_message, agent_id,
                   agent_session_id, tool_call_id, agent_reasoning, extra_data
            FROM audit_logs
            WHERE id = ?
        """, [log_id])
        
        columns = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        
        if not row:
            return jsonify({'success': False, 'message': '审计日志不存在'}), 404
        
        log = dict(zip(columns, row))

        # 转换None为空字符串
        for key, value in log.items():
            if value is None:
                log[key] = ''

        # 生成business_key
        log['business_key'] = _generate_business_key(
            _data_source,
            log.get('object_type', ''),
            log.get('object_id', ''),
            log.get('field_name', ''),
            log.get('new_value', '')
        )

        # [FIX 2026-06-11] 解析 extra_data JSON: deleted_data 与 object_display
        log['extra_data_parsed'] = _extract_deleted_data(log.pop('extra_data', ''))
        
        return jsonify({
            'success': True,
            'data': log
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@audit_bp.route('/logs/export', methods=['GET'])
@login_required
def export_audit_logs():
    """导出审计日志为CSV"""
    try:
        # 获取查询参数
        action = request.args.get('action', '')
        object_type = request.args.get('object_type', '')
        user_name = request.args.get('user_name', '')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')
        
        # 构建查询条件
        conditions = []
        params = []
        
        if action:
            conditions.append("action = ?")
            params.append(action)
        
        if object_type:
            conditions.append("object_type = ?")
            params.append(object_type)
        
        if user_name:
            conditions.append("user_name LIKE ?")
            params.append(f"%{user_name}%")
        
        if start_date:
            conditions.append("created_at >= ?")
            params.append(start_date)
        
        if end_date:
            conditions.append("created_at <= ?")
            params.append(end_date + ' 23:59:59')
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # 查询数据（限制最多导出10000条）
        query_sql = f"""
            SELECT id, object_type, object_id, action, field_name, old_value, new_value,
                   user_id, user_name, ip_address, created_at
            FROM audit_logs
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT 10000
        """
        
        cursor = _data_source.execute(query_sql, params)
        rows = cursor.fetchall()
        
        # 生成CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 写入表头
        writer.writerow(['ID', '对象类型', '对象ID', '操作类型', '字段名', '旧值', '新值', 
                        '用户ID', '用户名', 'IP地址', '操作时间'])
        
        # 写入数据
        for row in rows:
            writer.writerow(row)
        
        output.seek(0)
        
        from flask import Response
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename=audit_logs_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            }
        )
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@audit_bp.route('/failed', methods=['GET'])
@login_required
def get_failed_audit_logs():
    """查询失败的审计日志记录"""
    if not is_admin():
        return jsonify({'success': False, 'message': '需要管理员权限'}), 403
    
    try:
        cursor = _data_source.execute("""
            SELECT id, object_type, object_id, action, field_name, error_message,
                   retry_count, created_at
            FROM audit_logs
            WHERE status = 'failed'
            ORDER BY created_at DESC
            LIMIT 100
        """)
        
        columns = [desc[0] for desc in cursor.description]
        logs = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'data': logs
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@audit_bp.route('/overview', methods=['GET'])
@login_required
def get_audit_overview():
    """获取审计日志统计概览"""
    try:
        # 按操作类型统计
        cursor = _data_source.execute("""
            SELECT action, COUNT(*) as count
            FROM audit_logs
            GROUP BY action
            ORDER BY count DESC
        """)
        action_stats = [{'action': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # 按对象类型统计
        cursor = _data_source.execute("""
            SELECT object_type, COUNT(*) as count
            FROM audit_logs
            GROUP BY object_type
            ORDER BY count DESC
            LIMIT 10
        """)
        object_stats = [{'object_type': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # 按用户统计
        cursor = _data_source.execute("""
            SELECT user_name, COUNT(*) as count
            FROM audit_logs
            WHERE user_name IS NOT NULL AND user_name != ''
            GROUP BY user_name
            ORDER BY count DESC
            LIMIT 10
        """)
        user_stats = [{'user_name': row[0], 'count': row[1]} for row in cursor.fetchall()]
        
        # 总数
        cursor = _data_source.execute("SELECT COUNT(*) FROM audit_logs")
        total = cursor.fetchone()[0]
        
        # 失败数
        cursor = _data_source.execute("SELECT COUNT(*) FROM audit_logs WHERE status = 'failed'")
        failed = cursor.fetchone()[0]
        
        today_str = datetime.now().strftime('%Y-%m-%d')

        cursor = _data_source.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE created_at >= ?", [today_str]
        )
        today_count = cursor.fetchone()[0]

        cursor = _data_source.execute(
            "SELECT COUNT(*) FROM audit_logs WHERE log_category = 'security'"
        )
        security_count = cursor.fetchone()[0]

        cursor = _data_source.execute("""
            SELECT COALESCE(log_category, 'business'), COUNT(*) as count
            FROM audit_logs
            GROUP BY log_category
            ORDER BY count DESC
        """)
        category_stats = [{'category': row[0], 'count': row[1]} for row in cursor.fetchall()]

        days = request.args.get('days', 7, type=int)
        days = min(max(days, 7), 30)
        trend_stats = []
        for i in range(days - 1, -1, -1):
            from datetime import timedelta
            day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            cursor = _data_source.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE created_at >= ? AND created_at < ?",
                [day, (datetime.now() - timedelta(days=i - 1)).strftime('%Y-%m-%d') if i > 0 else (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')]
            )
            count = cursor.fetchone()[0]
            trend_stats.append({'date': day, 'count': count})

        return jsonify({
            'success': True,
            'data': {
                'total': total,
                'failed': failed,
                'today_count': today_count,
                'security_count': security_count,
                'by_action': action_stats,
                'by_object': object_stats,
                'by_user': user_stats,
                'by_category': category_stats,
                'trend': trend_stats
            }
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


def _generate_business_key(data_source, object_type: str, object_id: str, field_name: str = '', new_value: str = '') -> str:
    """
    生成业务标识（business key）
    
    @deprecated 使用 ObjectIdentityService 替代
    保留此函数以保持向后兼容
    
    根据元数据定义动态查询对应的业务标识信息，使审计日志更易读
    
    Args:
        data_source: 数据源
        object_type: 对象类型（如 user, role, user_group 等）
        object_id: 对象ID
        field_name: 变更的字段名（可选）
        new_value: 字段的新值（可选）
    
    Returns:
        格式化的业务标识字符串
    """
    if not object_type or not object_id:
        return ''

    # 提前判断 object_id 是否为纯数字字符串，非数字则直接返回格式化标识，避免无效的 int() 转换
    is_numeric_id = False
    try:
        int(object_id)
        is_numeric_id = True
    except (ValueError, TypeError):
        pass

    if not is_numeric_id:
        # 枚举类型 / 元数据对象使用字符串主键（如 'annotation_category'），直接返回
        if object_type and object_id:
            return f"{object_type}:{object_id}"
        return ''

    try:
        from meta.services.object_identity_service import ObjectIdentityService

        service = ObjectIdentityService(data_source)
        identity = service.get_identity(object_type, int(object_id), format='short')
        
        formatted = identity.get('formatted', '')
        if formatted:
            return formatted[:50]
        
        if field_name and new_value:
            if any(keyword in field_name.lower() for keyword in ['name', 'title', 'label', 'display']):
                return new_value[:50]
        
        return f"{object_type}:{object_id}"
    
    except Exception as e:
        print(f"[BusinessKey] Failed to use ObjectIdentityService for {object_type}:{object_id}: {e}")
        
        try:
            meta = BUSINESS_KEY_METADATA.get(object_type)
            
            if not meta:
                if field_name and new_value:
                    if any(keyword in field_name.lower() for keyword in ['name', 'title', 'label', 'display']):
                        return new_value[:50]
                return f"{object_type}:{object_id}"
            
            fields_str = ', '.join(meta['fields'])
            
            try:
                cursor = data_source.execute(
                    f"SELECT {fields_str} FROM {meta['table']} WHERE id = ?",
                    [int(object_id)]
                )
                row = cursor.fetchone()
                
                if not row:
                    return f"{object_type}:{object_id}"
                    
            except Exception as query_error:
                print(f"[BusinessKey] Query error for {object_type}:{object_id}: {query_error}")
                return f"{object_type}:{object_id}"
            
            field_values = {}
            for i, field in enumerate(meta['fields']):
                field_values[field] = row[i] or ''
            
            primary_value = field_values.get(meta.get('primary', ''), '')
            secondary_value = field_values.get(meta.get('secondary', ''), '')
            
            if primary_value and secondary_value and primary_value != secondary_value:
                return f"{primary_value}({secondary_value})"
            elif primary_value:
                return str(primary_value)[:50]
            elif secondary_value:
                return str(secondary_value)[:50]
            else:
                return f"{object_type}:{object_id}"
        
        except Exception as fallback_error:
            print(f"[BusinessKey] Fallback also failed for {object_type}:{object_id}: {fallback_error}")
            import traceback
            traceback.print_exc()
            return f"{object_type}:{object_id}"


def _extract_deleted_data(extra_data_raw) -> dict:
    """[FIX 2026-06-11] 解析 extra_data JSON, 返回 parsed 后的 dict.

    extra_data 通常是 JSON 字符串, 内部结构 (e.g.):
      {"deleted_data": {...整行原数据...}, "object_display": "AB001 → AB002"}

    Returns:
        dict: 解析后的 dict. 失败时返回空 dict.
        - 调用方可直接访问 parsed.get('deleted_data', {}) 获取删除明细
    """
    if not extra_data_raw:
        return {}

    if isinstance(extra_data_raw, (bytes, bytearray)):
        try:
            extra_data_raw = extra_data_raw.decode('utf-8')
        except Exception:
            return {}

    if isinstance(extra_data_raw, dict):
        return extra_data_raw

    import json
    try:
        result = json.loads(str(extra_data_raw))
        return result if isinstance(result, dict) else {}
    except (ValueError, TypeError):
        return {}
