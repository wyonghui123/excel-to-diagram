# -*- coding: utf-8 -*-
"""
BO 业务 Action: audit.export (v3.1 文件流)
============================================

管理员导出审计日志为 xlsx/csv 文件。
直接走 SQL 查询 + openpyxl/csv 写文件 (不走 audit_service.export_audit_log, 那个有 r.id 属性 bug)。
返回 ActionResult 含 file_data (v3.1 新增文件流支持)。

[R018 FIX] 增强:
  1. SQL 增 trace_id, transaction_id, agent_id, agent_session_id, tool_call_id,
     user_agent, outcome, cascade_root_id, cascade_root_action 8 列
  2. 解析 FK 结构化 JSON (new_value/old_value) 提取 target_display 给运维人员看
"""
import csv
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from meta.core.db_path import get_meta_db_path

logger = logging.getLogger(__name__)


def _safe_parse_target_display(value: Any) -> Optional[str]:
    """
    [R018] 从 FK 结构化 JSON 提取 target_display 给人看
    例如: '{"target_type":"versions","target_id":764,"target_display":"v1.0"}' -> 'v1.0'
    若不是 JSON 或无 display, 返回 None (调用方决定是否落回原值)
    """
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not (s.startswith('{') and s.endswith('}')):
        return None
    try:
        obj = json.loads(s)
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    display = obj.get('target_display')
    if display:
        return str(display)
    return None


def audit_export_handler(params: Dict[str, Any], context: Dict[str, Any]) -> 'ActionResult':
    """
    audit.export Action 处理器 (返回 ActionResult 含文件流)

    Args:
        params: {
            'action': str (optional),
            'object_type': str (optional),
            'user_name': str (optional),
            'start_date': str (optional),
            'end_date': str (optional),
            'format': 'xlsx' | 'csv' (default 'xlsx'),
        }
    """
    from meta.api.bo_action_api import ActionResult

    # 引入 db
    import os
    db_path = get_meta_db_path()

    # 构造 SQL 条件
    conditions = []
    sql_params = []
    if params.get('action'):
        conditions.append("action = ?")
        sql_params.append(params['action'])
    if params.get('object_type'):
        conditions.append("object_type = ?")
        sql_params.append(params['object_type'])
    if params.get('user_name'):
        conditions.append("user_name LIKE ?")
        sql_params.append(f"%{params['user_name']}%")
    if params.get('start_date'):
        conditions.append("created_at >= ?")
        sql_params.append(params['start_date'])
    if params.get('end_date'):
        conditions.append("created_at <= ?")
        sql_params.append(params['end_date'] + ' 23:59:59')

    where_clause = " AND ".join(conditions) if conditions else "1=1"
    format_type = params.get('format', 'xlsx')
    if format_type not in ('xlsx', 'csv'):
        format_type = 'xlsx'

    # [R018 FIX] 增加 8 列: trace_id, transaction_id, agent_id, agent_session_id,
    # tool_call_id, user_agent, outcome, cascade_root_id, cascade_root_action
    # 增加 2 列辅助: target_display_new, target_display_old (从 FK JSON 提取)
    HEADERS = [
        'id', 'object_type', 'object_id', 'action', 'field_name',
        'old_value', 'new_value', 'target_display_old', 'target_display_new',
        'user_id', 'user_name', 'ip_address', 'user_agent',
        'trace_id', 'transaction_id',
        'agent_id', 'agent_session_id', 'tool_call_id', 'agent_reasoning',
        'outcome', 'cascade_root_id', 'cascade_root_action',
        'log_category', 'log_level',
        'created_at',
    ]

    # 查数据
    try:
        # [V007.41 BUG-FIX] 用 safe_connect_for_read 统一 L0 入口
        with safe_connect_for_read(db_path) as conn:
            cursor = conn.execute(
                f"""SELECT id, object_type, object_id, action, field_name, old_value, new_value,
                           user_id, user_name, ip_address, user_agent, created_at,
                           trace_id, transaction_id,
                           agent_id, agent_session_id, tool_call_id, agent_reasoning,
                           outcome, cascade_root_id, cascade_root_action,
                           log_category, log_level
                    FROM v_audit_all
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT 10000""",
                sql_params
            )
            rows = cursor.fetchall()
    except Exception as e:
        logger.exception(f"[audit.export] query failed: {e}")
        return ActionResult(success=False, data=None, message=f'查询失败: {e}')

    if not rows:
        return ActionResult(success=False, data=None, message='没有审计日志可导出')

    # 写文件
    output_dir = os.path.join(os.getcwd(), 'meta', 'exports')
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        return ActionResult(success=False, data=None, message=f'创建目录失败: {e}')

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_name = f"audit_log_{timestamp}.{format_type}"
    file_path = os.path.join(output_dir, file_name)

    def _row_to_record(r):
        """[R018] 把 row dict 转成与 HEADERS 对齐的列表, 同时附加 target_display 解析"""
        old_val = r['old_value']
        new_val = r['new_value']
        target_display_old = _safe_parse_target_display(old_val)
        target_display_new = _safe_parse_target_display(new_val)
        return [
            r['id'], r['object_type'], r['object_id'], r['action'], r['field_name'],
            old_val, new_val, target_display_old, target_display_new,
            r['user_id'], r['user_name'], r['ip_address'], r['user_agent'],
            r['trace_id'], r['transaction_id'],
            r['agent_id'], r['agent_session_id'], r['tool_call_id'], r['agent_reasoning'],
            r['outcome'], r['cascade_root_id'], r['cascade_root_action'],
            r['log_category'], r['log_level'],
            r['created_at'],
        ]

    try:
        if format_type == 'csv':
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(HEADERS)
                for r in rows:
                    writer.writerow(_row_to_record(r))
        else:  # xlsx
            try:
                from openpyxl import Workbook
            except ImportError:
                # openpyxl 不可用, fallback csv
                format_type = 'csv'
                file_name = f"audit_log_{timestamp}.csv"
                file_path = os.path.join(output_dir, file_name)
                with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(HEADERS)
                    for r in rows:
                        writer.writerow(_row_to_record(r))
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = 'Audit Log'
                ws.append(HEADERS)
                for r in rows:
                    ws.append(_row_to_record(r))
                wb.save(file_path)
                wb.close()
    except Exception as e:
        logger.exception(f"[audit.export] write file failed: {e}")
        return ActionResult(success=False, data=None, message=f'写文件失败: {e}')

    # 读为字节流
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
    except OSError as e:
        return ActionResult(success=False, data=None, message=f'读文件失败: {e}')

    # 删临时文件
    try:
        os.remove(file_path)
    except OSError:
        pass

    # 构造响应
    if format_type == 'xlsx':
        mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    else:
        mimetype = 'text/csv'

    filename = f'audit_logs_{timestamp}.{format_type}'

    return ActionResult(
        success=True,
        data={
            'filename': filename,
            'size_bytes': len(file_data),
            'format': format_type,
            'row_count': len(rows),
        },
        message=f'导出成功 ({len(rows)} 条记录, {len(file_data)} bytes)',
        file_data=file_data,
        file_mimetype=mimetype,
        file_filename=filename,
    )
