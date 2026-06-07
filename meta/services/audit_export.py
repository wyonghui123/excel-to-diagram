# -*- coding: utf-8 -*-
"""
BO 业务 Action: audit.export (v3.1 文件流)
============================================

管理员导出审计日志为 xlsx/csv 文件。
直接走 SQL 查询 + openpyxl/csv 写文件 (不走 audit_service.export_audit_log, 那个有 r.id 属性 bug)。
返回 ActionResult 含 file_data (v3.1 新增文件流支持)。
"""
import csv
import logging
import os
from datetime import datetime
from typing import Any, Dict

logger = logging.getLogger(__name__)


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
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db',
    )

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

    # 查数据
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            f"""SELECT id, object_type, object_id, action, field_name, old_value, new_value,
                       user_id, user_name, ip_address, created_at
                FROM audit_logs
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT 10000""",
            sql_params
        )
        rows = cursor.fetchall()
        conn.close()
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

    try:
        if format_type == 'csv':
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'id', 'object_type', 'object_id', 'action', 'field_name',
                    'old_value', 'new_value', 'user_id', 'user_name',
                    'ip_address', 'created_at',
                ])
                for r in rows:
                    writer.writerow([
                        r['id'], r['object_type'], r['object_id'], r['action'],
                        r['field_name'], r['old_value'], r['new_value'],
                        r['user_id'], r['user_name'], r['ip_address'], r['created_at'],
                    ])
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
                    writer.writerow([
                        'id', 'object_type', 'object_id', 'action', 'field_name',
                        'old_value', 'new_value', 'user_id', 'user_name',
                        'ip_address', 'created_at',
                    ])
                    for r in rows:
                        writer.writerow([
                            r['id'], r['object_type'], r['object_id'], r['action'],
                            r['field_name'], r['old_value'], r['new_value'],
                            r['user_id'], r['user_name'], r['ip_address'], r['created_at'],
                        ])
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = 'Audit Log'
                ws.append([
                    'id', 'object_type', 'object_id', 'action', 'field_name',
                    'old_value', 'new_value', 'user_id', 'user_name',
                    'ip_address', 'created_at',
                ])
                for r in rows:
                    ws.append([
                        r['id'], r['object_type'], r['object_id'], r['action'],
                        r['field_name'], r['old_value'], r['new_value'],
                        r['user_id'], r['user_name'], r['ip_address'], r['created_at'],
                    ])
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
