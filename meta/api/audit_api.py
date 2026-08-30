"""
审计日志API
提供审计日志查询、导出等功能
"""

from flask import Blueprint, jsonify, request, g
from datetime import datetime
from typing import Optional
import csv
import io

audit_bp = Blueprint('audit', __name__)

from meta.core.datasource import get_data_source
from meta.api._messages import MSG_ADMIN_REQUIRED
from meta.api.auth_api import login_required, is_admin
from meta.services.auth_middleware import get_current_user

_data_source = None


def init_audit_services(data_source=None):
    """初始化审计服务"""
    global _data_source
    _data_source = data_source


def _require_audit_log_read():
    """[BMRD-2026-06-14] 审计日志读权限校验 — admin/* 旁路, 否则需要 audit_log:read."""
    user = get_current_user()
    if user and is_admin(user):
        return None
    if user:
        perms = user.get('permissions', []) or []
        if '*' in perms or 'admin' in perms or 'audit_log:read' in perms:
            return None
    return jsonify({
        'success': False,
        'message': '缺少权限: audit_log:read',
        'error_code': 'permission.audit_log.read.missing',
    }), 403

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
    perm_check = _require_audit_log_read()
    if perm_check:
        return perm_check
    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('page_size', 20, type=int)
        action = request.args.get('action', '')
        object_type = request.args.get('object_type', '')
        object_id = request.args.get('object_id', '')
        # [FIX 2026-08-30] Spec 16 别名归一化: user_group → org
        # 前端 OrgManagement 详情仍以 'user_group' 作为 objectType 查询审计日志,
        # 而 Spec 16 迁移后审计日志写入 object_type='org', 直接按 alias 查询返回空。
        # 用 registry 别名解析 (org.yaml semantics.aliases) 归一到规范 object_type。
        if object_type:
            try:
                from meta.core.models import registry
                meta_obj = registry.get(object_type)
                if meta_obj is not None and meta_obj.id != object_type:
                    object_type = meta_obj.id
            except Exception:
                pass
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

        # [FIX 2026-06-15] 默认过滤审计系统自监控记录:
        # - __audit_failure__ 是 async_audit_writer 在 audit 写入失败时 fallback 记的元记录
        #   (id=object_id=0, action=UNKNOWN), 对业务查询无意义
        #   但 detail 页面 OR 联合查询时会混入, 拖慢查询 + 干扰 UI 显示
        # - escape hatch: admin 可通过 ?include_internal=true 显式查询内部记录
        #   用于监控 audit 系统健康度 (AsyncAuditWriter / AuditRetryWorker 的运维视图)
        include_internal = request.args.get('include_internal', 'false').lower() == 'true'
        if not include_internal:
            conditions.append("object_type != '__audit_failure__'")

        if action:
            conditions.append("action = ?")
            params.append(action)

        if object_type:
            conditions.append("object_type = ?")
            params.append(object_type)

        if object_id:
            conditions.append("object_id = ?")
            params.append(object_id)

        # [FIX 2026-06-12 + 2026-06-14] parent_object 查询逻辑:
        # - 同时传 (object_type+object_id) 和 (parent_object_type+parent_object_id) 时, 用 OR 联合查询
        #   (角色自身日志 + 角色子对象日志一起返回)
        # - 只传 (parent_object_type+parent_object_id) 时, 走纯 parent_object 查询
        # - 只传 (object_type+object_id) 时, 走纯 object 查询 (向后兼容)
        # - [FIX 2026-06-14] 只传 parent_object_id (不传 parent_object_type) 时, 也要走 OR 联合
        #   原因: HistorySection 对所有对象 (domain/sub_domain/relationship 等) 默认传
        #         parent_object_id=<自身id> 让查询覆盖 "自身日志 + 子对象日志". 这些对象的日志
        #         自身 parent_object_type 可能是 version/dimension 等其他类型, 所以不传
        #         parent_object_type; 仅用 parent_object_id 走 OR 联合才能正确返回 (object_id=683) 的日志.
        #   旧逻辑 (BUG): 单传 parent_object_id 会 AND 一个 parent_object_id=? 条件, 与 object_id 收窄到 0 条
        # 重要: 走 OR 联合时, 必须 pop 掉前面已经加的 (object_type + object_id) 条件,
        #       否则会被 AND 收窄到 0 条
        def _pop_object_conditions():
            """移除已添加的 object_type + object_id 单独条件, 改用 OR 联合"""
            for expected in ("object_id = ?", "object_type = ?"):
                if conditions and conditions[-1] == expected:
                    conditions.pop()
                    params.pop()

        if parent_object_id:
            # 任意 parent_object_id 传了 + (object_type+object_id) 也传了 -> OR 联合
            if object_type and object_id:
                _pop_object_conditions()
                if parent_object_type:
                    conditions.append(
                        f"((object_type = ? AND object_id = ?) OR "
                        f"(parent_object_type = ? AND parent_object_id = ?))"
                    )
                    params.extend([object_type, object_id, parent_object_type, parent_object_id])
                else:
                    conditions.append(
                        f"((object_type = ? AND object_id = ?) OR "
                        f"(parent_object_id = ?))"
                    )
                    params.extend([object_type, object_id, parent_object_id])
            else:
                # 仅 parent_object_id 查询
                if parent_object_type:
                    conditions.append("parent_object_type = ?")
                    params.append(parent_object_type)
                conditions.append("parent_object_id = ?")
                params.append(parent_object_id)
        elif parent_object_type:
            # 仅 parent_object_type 查询 (罕见)
            conditions.append("parent_object_type = ?")
            params.append(parent_object_type)

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

            # [NEW 2026-07-18] 注入 object_type_label / field_name_label /
            # parent_object_type_label (中英文映射), 解决 test_audit_labels T8 端到端冒烟
            _enrich_log_labels(log)

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
    perm_check = _require_audit_log_read()
    if perm_check:
        return perm_check
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

        # [OPT 2026-07-25 P0-3] detail 接口也注入 label 字段, 与 list 接口一致
        _enrich_log_labels(log)

        return jsonify({
            'success': True,
            'data': log
        })
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@audit_bp.route('/meta/actions', methods=['GET'])
@login_required
def get_audit_meta_actions():
    """[P0-3 2026-07-25] 返回 audit_log action 字段的 enum_values 元数据

    单一事实源: meta/schemas/audit_log.yaml fields[action].enum_values

    Returns:
      {
        "success": true,
        "data": [
          {"value": "CREATE", "label": "创建", "color": "success"},
          {"value": "UPDATE", "label": "更新", "color": "info"},
          ...
        ]
      }

    用途:
      - 前端启动时调一次, 缓存到 store, 替代 auditLogFormat.js ACTION_LABELS
      - 前端 ACTION_TAG_TYPES color_mapping 也可由此驱动
      - 列表筛选 dropdown 的 options 来源
    """
    perm_check = _require_audit_log_read()
    if perm_check:
        return perm_check

    try:
        result: list = []
        try:
            from meta.core.yaml_loader import registry
            audit_meta = registry.get('audit_log')
            if audit_meta and hasattr(audit_meta, 'fields'):
                for field in audit_meta.fields:
                    if getattr(field, 'id', None) != 'action':
                        continue
                    enum_values = getattr(field, 'enum_values', None) or []
                    for ev in enum_values:
                        if isinstance(ev, dict):
                            val = ev.get('value')
                            if not val:
                                continue
                            result.append({
                                'value': val,
                                'label': ev.get('label', val),
                                'color': ev.get('color', ''),
                            })
                        elif isinstance(ev, str):
                            result.append({'value': ev, 'label': ev, 'color': ''})
                    break
        except Exception as _e:
            import logging
            logging.getLogger(__name__).warning(
                f"[audit_api] /meta/actions load enum_values failed: {_e}"
            )

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@audit_bp.route('/logs/export', methods=['GET'])
@login_required
def export_audit_logs():
    """导出审计日志为CSV"""
    perm_check = _require_audit_log_read()
    if perm_check:
        return perm_check
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
        return jsonify({'success': False, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403
    
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
    perm_check = _require_audit_log_read()
    if perm_check:
        return perm_check
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


@audit_bp.route('/retry/status', methods=['GET'])
@login_required
def get_retry_worker_status():
    """获取 audit retry worker 状态"""
    if not is_admin():
        return jsonify({'success': False, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403

    try:
        from meta.services.audit_retry_worker import get_audit_retry_worker

        worker = get_audit_retry_worker()
        if worker is None:
            return jsonify({
                'success': True,
                'data': {
                    'running': False,
                    'message': 'Retry worker not initialized'
                }
            })

        stats = worker.get_stats()
        return jsonify({
            'success': True,
            'data': {
                'running': True,
                'interval_sec': worker._interval,
                'batch_size': worker._batch_size,
                'stats': stats
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


@audit_bp.route('/retry/trigger', methods=['POST'])
@login_required
def trigger_retry_worker():
    """手动触发 audit retry worker 执行一次"""
    if not is_admin():
        return jsonify({'success': False, 'message': '您没有执行此操作的权限，需要管理员权限'}), 403

    try:
        from meta.services.audit_retry_worker import get_audit_retry_worker

        worker = get_audit_retry_worker()
        if worker is None:
            return jsonify({'success': False, 'message': 'Retry worker not initialized'}), 500

        # 手动触发一次扫描
        worker._scan_and_retry()

        stats = worker.get_stats()
        return jsonify({
            'success': True,
            'message': 'Retry worker triggered',
            'data': stats
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': str(e)}), 500


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


# ============================================================
# [NEW 2026-07-18] 审计日志 label 映射 + enrich 函数
# 解决 test_audit_labels 缺失符号 (OBJECT_TYPE_LABELS / FIELD_NAME_LABELS /
# _enrich_log_labels / _enrich_log_labels_batch) 导致 33 个 integration fail
# ============================================================

OBJECT_TYPE_LABELS = {
    # 核心对象
    "user": "用户",
    "role": "角色",
    "user_group": "用户组",
    "menu": "菜单",
    "permission": "权限",
    "permission_rule": "权限规则",
    "product": "产品",
    "version": "版本",
    "domain": "领域",
    "sub_domain": "子领域",
    "service_module": "服务模块",
    "business_object": "业务对象",
    "relationship": "关系",
    "annotation": "标注",
    "enum_type": "枚举类型",
    "enum_value": "枚举值",
    # 权限相关
    "role_menu": "角色菜单权限",
    "role_dimension_scope": "角色维度范围",
    "role_permissions": "角色功能权限",
    "role_data_permission": "角色数据权限",
    "role_v2_menu_permissions": "角色菜单权限(v2)",
    "user_group_members": "用户组成员",
    "group_roles": "用户组角色",
    # 系统
    "audit_log": "审计日志",
    "system_config": "系统配置",
    "view_config": "视图配置",
}


# [OPT 2026-07-25 P0-3] ACTION_LABELS: 从 audit_log.yaml 的 enum_values 单一事实源加载
#   - 避免前后端双重维护 (前端 auditLogFormat.js ACTION_LABELS 已降级为 fallback)
#   - 启动时加载一次, 模块级缓存
_ACTION_LABELS_CACHE: Optional[dict] = None


def _load_action_labels_from_schema() -> dict:
    """从 audit_log.yaml 加载 action 字段的 enum_values → {value: label}

    单一事实源: meta/schemas/audit_log.yaml fields[action].enum_values
    失败时降级返回空 dict (调用方用原值)
    """
    global _ACTION_LABELS_CACHE
    if _ACTION_LABELS_CACHE is not None:
        return _ACTION_LABELS_CACHE

    result: dict = {}
    try:
        from meta.core.yaml_loader import registry
        audit_meta = registry.get('audit_log')
        if audit_meta and hasattr(audit_meta, 'fields'):
            for field in audit_meta.fields:
                if getattr(field, 'id', None) != 'action':
                    continue
                enum_values = getattr(field, 'enum_values', None) or []
                for ev in enum_values:
                    # 兼容 dict 和 str 两种形式 (见 bo_api.py:3229)
                    if isinstance(ev, dict):
                        val = ev.get('value')
                        label = ev.get('label', val)
                        if val:
                            result[val] = label
                    elif isinstance(ev, str):
                        result[ev] = ev
                break
    except Exception as _e:
        # 降级: 返回空 dict, 调用方用原值
        import logging
        logging.getLogger(__name__).warning(
            f"[audit_api] _load_action_labels_from_schema failed: {_e}, "
            f"action_label will fallback to raw action"
        )

    _ACTION_LABELS_CACHE = result
    return result


def get_action_label(action: str) -> str:
    """[P0-3] action → 业务动作 label (供 _enrich_log_labels 和 /meta/actions 使用)"""
    if not action:
        return ''
    labels = _load_action_labels_from_schema()
    return labels.get(action, action)


# [P0-2 2026-07-25] 字段值业务化显示
#   - 解决前端 auditLogFormat.getFieldValueDisplay 客户端 N 次 JSON.parse 的性能问题
#   - 后端在 list/detail 接口直接返回 old_value_display / new_value_display
def _format_field_value(value) -> str:
    """格式化字段值为业务可读形式

    规则:
      1. None/空 → '(空)'
      2. JSON 字符串 (FK 结构化值) → 解析出 target_display / target_key
      3. 原值 → str(value)

    Args:
        value: 后端字段原值 (可能是 str/None/int/float)

    Returns:
        str: 业务可读字符串
    """
    if value is None:
        return ''
    if isinstance(value, str):
        if value == '':
            return ''
        # FK 结构化值: {"target_type":"...","target_id":470,"target_display":"采购订单"}
        if value.startswith('{'):
            try:
                import json as _json
                parsed = _json.loads(value)
                if isinstance(parsed, dict):
                    if parsed.get('target_display'):
                        return str(parsed['target_display'])
                    if parsed.get('target_key'):
                        return str(parsed['target_key'])
            except (ValueError, TypeError):
                pass
        return value
    return str(value)

FIELD_NAME_LABELS = {
    # 通用字段
    "name": "名称",
    "code": "编码",
    "description": "描述",
    "status": "状态",
    "display_name": "显示名",
    "email": "邮箱",
    "username": "用户名",
    "password": "密码",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    # 菜单/权限相关
    "menu_codes": "菜单编码列表",
    "menu_names": "菜单名称列表",
    "dimension_codes": "维度编码列表",
    "permission_ids": "权限ID列表",
    "permission_names": "权限名称列表",
    "scopes_count": "范围数量",
    "is_denied": "是否禁止",
    "inherit_to_children": "是否继承给子级",
    "synced_permissions_count": "已同步权限数量",
    # 关系/对象相关
    "object_type": "对象类型",
    "object_id": "对象ID",
    "parent_object_type": "父对象类型",
    "parent_object_id": "父对象ID",
    "relation_type": "关系类型",
    "relation_code": "关系编码",
    "category_type": "分类类型",
    "category_label": "分类标签",
    # 版本/产品
    "product_id": "产品ID",
    "version_id": "版本ID",
    "visibility": "可见性",
    "owner_id": "所有者ID",
    # 操作
    "action": "操作",
    "old_value": "旧值",
    "new_value": "新值",
    "field_name": "字段名",
}


_display_name_service = None


def _get_display_name_service():
    """[P1-D 2026-07-25] 懒加载 DisplayNameService (基于 yaml registry)

    DisplayNameService 是字段显示名称的单一事实源:
      - 字段级: registry.get(object_type).fields[i].name (yaml schema 定义)
      - 对象级: registry.get(object_type).name (yaml schema 顶层 name)
      - 视图覆盖: ui_view_config.list.columns[].title (例外配置)

    失败时返回 None, 调用方降级走 OBJECT_TYPE_LABELS / FIELD_NAME_LABELS.
    """
    global _display_name_service
    if _display_name_service is not None:
        return _display_name_service
    try:
        from meta.services.display_name_service import DisplayNameService
        from meta.core.yaml_loader import registry as _yaml_registry
        _display_name_service = DisplayNameService(_yaml_registry)
    except Exception as _e:
        import logging
        logging.getLogger(__name__).warning(
            f"[audit_api] DisplayNameService init failed: {_e}, "
            f"field_name_label will fallback to FIELD_NAME_LABELS"
        )
        _display_name_service = None
    return _display_name_service


def _get_object_type_label(object_type: str) -> str:
    """[P1-D 2026-07-25] 获取 object_type 的中文标签

    优先级:
      1. yaml registry.get(object_type).name (单一事实源)
         - 覆盖 user→用户, role→角色, product→产品, version→版本 等
      2. OBJECT_TYPE_LABELS 硬编码 fallback
         - 覆盖 audit 专用伪类型 (如 __audit_failure__, _unknown)
         - 覆盖 registry 未注册的衍生类型 (如 role_menu, role_permissions)
      3. object_type 原值
    """
    if not object_type:
        return ''
    # 优先: yaml registry (单一事实源)
    try:
        from meta.core.yaml_loader import registry as _yaml_registry
        meta = _yaml_registry.get(object_type)
        if meta and getattr(meta, 'name', None):
            return meta.name
    except Exception:
        pass
    # 降级: 硬编码 (audit 专用伪类型 / 衍生类型)
    return OBJECT_TYPE_LABELS.get(object_type, object_type)


def _get_field_name_label(object_type: str, field_name: str) -> str:
    """[P1-D 2026-07-25] 获取字段的中文标签

    优先级:
      1. DisplayNameService.get_field_name(object_type, field_name, context='list')
         - yaml schema fields[].name (单一事实源)
         - 视图覆盖: ui_view_config.list.columns[].title
      2. FIELD_NAME_LABELS 硬编码 fallback
         - 覆盖 audit 专用字段 (action, old_value, new_value, field_name)
         - 覆盖 registry 未注册的 object_type 场景
      3. field_name 原值

    注意:
      - DisplayNameService 只对 registry 中已注册的 object_type 有效,
        对于 audit 专用伪类型 (如 __audit_failure__) 会直接降级到硬编码.
      - 当 DisplayNameService 返回值等于 field_name 时, 视为未找到, 继续降级.
    """
    if not field_name:
        return ''
    # 优先: DisplayNameService (yaml schema field.name 单一事实源)
    if object_type:
        try:
            svc = _get_display_name_service()
            if svc is not None:
                label = svc.get_field_name(object_type, field_name, context='list')
                if label and label != field_name:
                    return label
        except Exception:
            pass
    # 降级: 硬编码
    return FIELD_NAME_LABELS.get(field_name, field_name)


def _enrich_log_labels(log):
    """[NEW 2026-07-18] 为单条审计日志注入 6 个 label/display 字段.

    注入字段:
      - action_label: 根据 action 查 audit_log.yaml enum_values (单一事实源)
      - object_type_label: 根据 object_type 查 yaml registry (DisplayNameService)
      - field_name_label: 根据 field_name 查 yaml schema (DisplayNameService)
      - parent_object_type_label: 根据 parent_object_type 查 yaml registry
      - old_value_display: 格式化 old_value (FK JSON 解析为 target_display)
      - new_value_display: 格式化 new_value (FK JSON 解析为 target_display)

    规则:
      - 空/None 值不注入 (避免 label="" 前端显示空白)
      - 已有 *_label 字段不覆盖 (调用方自定义优先)
      - 未知类型降级为原值 (label == key)
      - 非 dict 入参静默忽略 (不抛异常)

    [OPT 2026-07-25 P0-3] 新增 action_label 注入, 消除前端 ACTION_LABELS 重复表
    [OPT 2026-07-25 P0-2] 新增 old_value_display / new_value_display,
                          消除前端 N 次 JSON.parse 的性能问题
    [OPT 2026-07-25 P1-D] object_type_label / field_name_label 改用
                          DisplayNameService (yaml schema 单一事实源),
                          OBJECT_TYPE_LABELS / FIELD_NAME_LABELS 降级为 fallback.
                          消除后端硬编码与 yaml schema 字段中文名的重复维护.
    """
    if not isinstance(log, dict):
        return

    act = log.get('action', '') or ''
    ot = log.get('object_type', '') or ''
    fn = log.get('field_name', '') or ''
    pot = log.get('parent_object_type', '') or ''

    # [P0-3] action_label 从 schema 加载, 单一事实源
    if act and not log.get('action_label'):
        log['action_label'] = get_action_label(act)
    # [P1-D] object_type_label 优先 DisplayNameService (yaml registry.name)
    if ot and not log.get('object_type_label'):
        log['object_type_label'] = _get_object_type_label(ot)
    # [P1-D] field_name_label 优先 DisplayNameService (yaml schema field.name)
    if fn and not log.get('field_name_label'):
        log['field_name_label'] = _get_field_name_label(ot, fn)
    # [P1-D] parent_object_type_label 同样走 DisplayNameService
    if pot and not log.get('parent_object_type_label'):
        log['parent_object_type_label'] = _get_object_type_label(pot)

    # [P0-2] 字段值业务化显示, 替代前端 getFieldValueDisplay 客户端解析
    if 'old_value_display' not in log:
        log['old_value_display'] = _format_field_value(log.get('old_value'))
    if 'new_value_display' not in log:
        log['new_value_display'] = _format_field_value(log.get('new_value'))


def _enrich_log_labels_batch(logs):
    """[NEW 2026-07-18] 批量注入 label 字段 (列表版本).

    Args:
        logs: list[dict] 或 None. None/空列表静默忽略.
    """
    if not logs:
        return
    for log in logs:
        _enrich_log_labels(log)


# ============================================================================
# [P9-T3 2026-07-20] 审计 API — GET /audit/decisions + /compliance
# Spec §4.9 / §8.9 P9-T3
# ============================================================================

# 审计可访问角色 (Admin + Auditor)
_AUDIT_ACCESSIBLE_ROLE_CODES = frozenset({'admin', 'auditor'})


def _is_audit_accessible(current_user: dict) -> bool:
    """[P9-T3] 校验当前用户是否有审计访问权限

    仅 admin / auditor 角色可访问; 其他角色返回 403.

    Args:
        current_user: {'id': int, 'username': str, 'role_id': Optional[int]}

    Returns:
        True 表示可访问; False 表示禁止访问
    """
    if not current_user:
        return False

    # 检查 role_code (优先) 或 role_id (兜底)
    role_code = current_user.get('role_code')
    if role_code and role_code.lower() in _AUDIT_ACCESSIBLE_ROLE_CODES:
        return True

    # role_id 1 (Admin) / 2 (Auditor) — Spec §3.17 / §8.9 角色约定
    role_id = current_user.get('role_id')
    if role_id in (1, 2):
        return True

    # is_superuser / is_admin 旁路
    if current_user.get('is_superuser') or current_user.get('is_admin'):
        return True

    # 通配符权限 '*'
    perms = current_user.get('permissions', []) or []
    if '*' in perms or 'audit_log:read' in perms:
        return True

    return False


def get_permission_decisions(
    data_source,
    page: int = 1,
    page_size: int = 20,
    current_user: Optional[dict] = None,
    filters: Optional[dict] = None,
) -> dict:
    """[P9-T3] GET /audit/decisions — 分页查询权限决策日志

    仅审计角色 (admin/auditor) 可访问.

    Args:
        data_source: DB 数据源
        page: 页码 (1-based)
        page_size: 每页条数 (默认 20)
        current_user: 当前用户 (用于权限校验)
        filters: 可选过滤条件 {'user_id': N, 'resource_type': 'product', 'decision': 'allow'}

    Returns:
        分页结果 dict:
            {'data': [...], 'total': N, 'page': P, 'page_size': S, 'total_pages': T}
        或
            {'error': 'forbidden', 'forbidden': True}
    """
    # 权限校验
    if current_user is not None and not _is_audit_accessible(current_user):
        return {
            'error': 'permission_denied',
            'forbidden': True,
            'message': '仅审计角色 (admin/auditor) 可访问决策日志',
        }

    try:
        # 查询全部
        all_records = data_source.find('permission_decisions', filters=filters or {}) or []

        # 按 created_at 倒序
        all_records.sort(key=lambda r: r.get('created_at', ''), reverse=True)

        total = len(all_records)
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0

        start = (page - 1) * page_size
        end = start + page_size
        page_records = all_records[start:end]

        return {
            'data': page_records,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        }
    except Exception as e:
        return {
            'error': str(e),
            'data': [],
            'total': 0,
            'page': page,
            'page_size': page_size,
            'total_pages': 0,
        }


def get_compliance_report(
    data_source,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: Optional[dict] = None,
) -> dict:
    """[P9-T3] GET /audit/compliance — 生成合规报告

    仅审计角色 (admin/auditor) 可访问.

    Args:
        data_source: DB 数据源
        start_date: 可选, 起始日期
        end_date: 可选, 结束日期
        current_user: 当前用户 (用于权限校验)

    Returns:
        {'report': {...}} 或 {'error': 'forbidden', 'forbidden': True}
    """
    # 权限校验
    if current_user is not None and not _is_audit_accessible(current_user):
        return {
            'error': 'permission_denied',
            'forbidden': True,
            'message': '仅审计角色 (admin/auditor) 可访问合规报告',
        }

    try:
        from meta.services.compliance_reporter import ComplianceReporter
        reporter = ComplianceReporter(data_source)
        report = reporter.generate_report(start_date=start_date, end_date=end_date)
        return {'report': report}
    except Exception as e:
        return {'error': str(e), 'report': {}}


# ============================================================================
# Flask 路由 (Blueprint)
# ============================================================================

@audit_bp.route('/decisions', methods=['GET'])
@login_required
def get_audit_decisions_route():
    """[P9-T3] GET /audit/decisions — Flask 路由"""
    user = get_current_user()
    # 提取 role_id (兼容 dict / object)
    current_user = {
        'id': user.get('id') if isinstance(user, dict) else getattr(user, 'id', None),
        'username': user.get('username') if isinstance(user, dict) else getattr(user, 'username', ''),
        'role_id': user.get('role_id') if isinstance(user, dict) else getattr(user, 'role_id', None),
        'role_code': user.get('role_code') if isinstance(user, dict) else getattr(user, 'role_code', None),
        'permissions': user.get('permissions', []) if isinstance(user, dict) else getattr(user, 'permissions', []),
    }

    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))

    # 过滤参数
    filters = {}
    if request.args.get('user_id'):
        filters['user_id'] = int(request.args['user_id'])
    if request.args.get('resource_type'):
        filters['resource_type'] = request.args['resource_type']
    if request.args.get('decision'):
        filters['decision'] = request.args['decision']

    ds = _data_source or get_data_source()
    result = get_permission_decisions(
        ds, page=page, page_size=page_size,
        current_user=current_user, filters=filters,
    )

    if result.get('forbidden'):
        return jsonify(result), 403
    return jsonify(result)


@audit_bp.route('/compliance', methods=['GET'])
@login_required
def get_compliance_report_route():
    """[P9-T3] GET /audit/compliance — Flask 路由"""
    user = get_current_user()
    current_user = {
        'id': user.get('id') if isinstance(user, dict) else getattr(user, 'id', None),
        'username': user.get('username') if isinstance(user, dict) else getattr(user, 'username', ''),
        'role_id': user.get('role_id') if isinstance(user, dict) else getattr(user, 'role_id', None),
        'role_code': user.get('role_code') if isinstance(user, dict) else getattr(user, 'role_code', None),
        'permissions': user.get('permissions', []) if isinstance(user, dict) else getattr(user, 'permissions', []),
    }

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    ds = _data_source or get_data_source()
    result = get_compliance_report(
        ds, start_date=start_date, end_date=end_date,
        current_user=current_user,
    )

    if result.get('forbidden'):
        return jsonify(result), 403
    return jsonify(result)
