# -*- coding: utf-8 -*-
"""v256 —— 单据状态列 CHECK 对齐（DDL 单源 E2）。

背景:
  `schema_generator` 已按 YAML `enum_values` 渲染列级
  `CHECK (status IN (...))`；但历史库中状态列只有 VARCHAR 类型、没有 CHECK，
  于是 YAML 声明与真实 DDL 漂移（`sync_schema --check` 可复现）。

范围:
  只处理「表已存在、status 列已存在、且尚未带 CHECK」的单据/流程状态机表。
  主数据类 status（active/inactive）与 `users` / `audit_logs` 不在范围内：
  后两者由运行时写入（含 success / failure / denied 等内部状态），
  不能按 YAML 的 UI 枚举收窄。

做法（SQLite 无 ALTER ADD CONSTRAINT）:
  重建表 → 复制数据 → 删旧表 → 重命名 → 按 sqlite_master 重建索引/触发器。
  复用 `meta.core.schema_generator.rebuild_table_with_checks`，保持与
  `sync_schema --apply` 同一份实现。

幂等:
  已带 CHECK 的表直接跳过；重复执行打印 [SKIP]。
"""
import sqlite3
from pathlib import Path

from meta.core.schema_generator import parse_schema_text, rebuild_table_with_checks

MIGRATION_NAME = 'v256__align_status_check'

# 迁移固化当时的 YAML 枚举值（迁移不随 YAML 演化而改变语义）。
STATUS_CHECKS = {
    'receipts': ['draft', 'posted', 'reversed', 'cancelled'],
    'receipt_lines': ['draft', 'posted', 'reversed', 'cancelled'],
    'sales_orders': ['draft', 'submitted', 'confirmed', 'closed', 'cancelled'],
    'sales_order_lines': ['open', 'closed', 'cancelled'],
    'sales_order_schedules': ['planned', 'confirmed', 'completed', 'cancelled'],
    'purchase_orders': ['draft', 'submitted', 'confirmed', 'closed', 'cancelled'],
    'purchase_order_lines': ['open', 'closed', 'cancelled'],
    'purchase_order_schedules': ['planned', 'confirmed', 'completed', 'cancelled'],
    'requisitions': ['draft', 'submitted', 'approved', 'rejected', 'closed', 'cancelled'],
    'requisition_lines': ['open', 'closed', 'cancelled'],
    'transfer_orders': ['draft', 'released', 'closed', 'cancelled', 'reversed'],
    'transfer_order_lines': ['open', 'closed', 'cancelled'],
    'transfer_shipments': ['draft', 'posted', 'cancelled'],
    'shipments': ['draft', 'released', 'staged', 'shipped', 'delivered',
                  'reversed', 'closed', 'cancelled'],
    'shipment_lines': ['draft', 'staged', 'shipped', 'delivered', 'reversed', 'cancelled'],
    'customer_invoices': ['draft', 'submitted', 'posted', 'cancelled', 'reversed'],
    'customer_invoice_schedules': ['open', 'partial', 'closed', 'cancelled'],
    'inventory_adjustments': ['draft', 'released', 'posted', 'reversed', 'cancelled'],
    'inventory_counts': ['draft', 'counting', 'submitted', 'approved', 'posted', 'cancelled'],
    'inventory_reservations': ['open', 'partially_fulfilled', 'fulfilled',
                               'closed', 'cancelled', 'expired'],
    'handling_units': ['planned', 'open', 'sealed', 'in_transit', 'shipped', 'void'],
    'fulfillment_orders': ['draft', 'planned', 'in_progress', 'completed', 'cancelled'],
    'work_orders': ['New', 'In Progress', 'Waiting', 'Resolved', 'Closed', 'Cancelled'],
    'work_order_operations': ['pending', 'running', 'completed', 'cancelled'],
    'change_requests': ['draft', 'submitted', 'approved', 'rejected',
                        'applied', 'failed', 'cancelled'],
    'engineering_changes': ['draft', 'in_review', 'approved', 'applied',
                            'rejected', 'cancelled'],
    'projects': ['draft', 'active', 'inactive', 'closed', 'cancelled'],
    'project_tasks': ['draft', 'planned', 'in_progress', 'done', 'cancelled'],
    'service_requests': ['draft', 'submitted', 'approved', 'rejected',
                         'completed', 'closed', 'cancelled'],
    'service_request_lines': ['open', 'closed', 'cancelled'],
    'batches': ['planned', 'in_process', 'closed'],
    'configurations': ['draft', 'solved', 'invalid', 'frozen', 'superseded'],
    'production_versions': ['draft', 'active', 'obsolete'],
    'work_definitions': ['draft', 'active', 'obsolete'],
    'work_definition_operations': ['draft', 'active', 'obsolete'],
    'demand_allocations': ['active', 'reversed'],
}


def _has_table(conn, table):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [table]).fetchone())


def _has_status_check(conn, table):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    if not row or not row[0]:
        return False
    parsed = parse_schema_text(row[0])
    for name, info in parsed.items():
        if name.lower() != table.lower():
            continue
        column = info['columns'].get('status')
        return bool(column and column.get('check'))
    return False


def migrate(db_path, skip_backup=False):
    # skip_backup: MigrationRunner 已统一备份，迁移内部不再重复备份
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.isolation_level = None
    try:
        print('[v256] 开始: status 列 CHECK 对齐（%d 张候选表）' % len(STATUS_CHECKS))
        rebuilt, skipped = [], 0
        for table in STATUS_CHECKS:
            if not _has_table(conn, table):
                skipped += 1
                continue
            if _has_status_check(conn, table):
                skipped += 1
                continue
            if rebuild_table_with_checks(str(path), table, {'status': STATUS_CHECKS[table]},
                                         conn=conn):
                rebuilt.append(table)
        print('[v256] 完成: 重建 %d 张表 / 跳过 %d' % (len(rebuilt), skipped))
        if not rebuilt:
            print('[v256] [SKIP] status 列 CHECK 已就绪')
        elif len(rebuilt) <= 10:
            print('[v256] 重建表: %s' % ', '.join(rebuilt))
        return True
    finally:
        conn.close()


upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v256 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        missing = [table for table in STATUS_CHECKS
                   if _has_table(conn, table) and not _has_status_check(conn, table)]
        if missing:
            print('[v256 verify] FAIL: 缺少 status CHECK %d 张表: %s'
                  % (len(missing), ', '.join(missing[:10])))
            return False
        print('[v256 verify] OK: status 列 CHECK 已对齐')
        return True
    finally:
        conn.close()