# -*- coding: utf-8 -*-
"""项目 360 只读聚合（项目侧 P1 · AC-03）

定位:
  `project` 是商务层归集对象，金额事实仍只存在 sales_order / sales_order_line /
  sales_order_schedule 三处（I1：项目只留 budget_amount）。本服务只做**只读投影**，
  不复制、不重算、不回写任何金额。

为什么不用 `child_sections` 全部覆盖:
  `AssociationSection` 按子对象 schema 的 `hierarchy.parent_field` 反查父键，
  该字段单一值 —— sales_order 的父键是 project_id（P1 新增），可直接内联；
  但 sales_order_line / sales_order_schedule 的父键仍是 order_id（订单页签不能破坏），
  故行 / 计划行的项目归集走本接口，由前端只读展示。

口径:
  · sales_orders            按 sales_orders.project_id
  · sales_order_lines       按 sales_order_lines.project_id
  · sales_order_schedules   按 sales_order_schedules.project_id
  · work_orders             按 work_orders.project_id（P2 B1 新增列）
  · shipment                其 project_id 尚未落地（G6），本阶段不返回
"""

from typing import Any, Dict, List, Optional

PROJECT_SQL = (
    "SELECT id, project_no, name, project_type_id, status, org_id, "
    "customer_account_id, manager_user_id, start_date, end_date, "
    "budget_amount, currency_id FROM projects WHERE id = ?"
)

PROJECT_COLUMNS = (
    'id', 'project_no', 'name', 'project_type_id', 'status', 'org_id',
    'customer_account_id', 'manager_user_id', 'start_date', 'end_date',
    'budget_amount', 'currency_id',
)

SECTION_SPECS = {
    'sales_orders': {
        'table': 'sales_orders',
        'sql': (
            "SELECT id, order_no, order_date, status, customer_account_id, "
            "currency_id, net_amount FROM sales_orders WHERE project_id = ? "
            "ORDER BY order_date DESC, id DESC LIMIT ?"
        ),
        'columns': ('id', 'order_no', 'order_date', 'status',
                    'customer_account_id', 'currency_id', 'net_amount'),
    },
    'sales_order_lines': {
        'table': 'sales_order_lines',
        'sql': (
            "SELECT id, order_id, line_no, item_id, qty, uom_id, unit_price, "
            "net_amount, status FROM sales_order_lines WHERE project_id = ? "
            "ORDER BY order_id, line_no LIMIT ?"
        ),
        'columns': ('id', 'order_id', 'line_no', 'item_id', 'qty', 'uom_id',
                    'unit_price', 'net_amount', 'status'),
    },
    'sales_order_schedules': {
        'table': 'sales_order_schedules',
        'sql': (
            "SELECT id, order_id, line_id, schedule_no, schedule_kind, "
            "promised_date, promised_qty, billing_percent, "
            "status FROM sales_order_schedules WHERE project_id = ? "
            "ORDER BY promised_date, id LIMIT ?"
        ),
        # billing_amount 在 sales_order_schedule.yaml 中是 computed（db_column: null），
        # 不落库；本接口只透传 billing_percent，金额由调用方按行净额派生（不重算）
        'columns': ('id', 'order_id', 'line_id', 'schedule_no', 'schedule_kind',
                    'promised_date', 'promised_qty', 'billing_percent', 'status'),
    },
    'work_orders': {
        'table': 'work_orders',
        'sql': (
            "SELECT id, work_order_no, order_type, status, severity, "
            "schedule_id, opened_at, resolved_at FROM work_orders "
            "WHERE project_id = ? ORDER BY opened_at DESC, id DESC LIMIT ?"
        ),
        'columns': ('id', 'work_order_no', 'order_type', 'status', 'severity',
                    'schedule_id', 'opened_at', 'resolved_at'),
    },
}


class ProjectNotFound(Exception):
    """项目不存在（API 层映射 404）。"""


class ProjectOverviewService:
    """按项目 id 汇总销售侧单据与工单的只读投影。"""

    def __init__(self, data_source):
        self.ds = data_source

    def _fetch(self, sql: str, params: tuple) -> List[Any]:
        return self.ds.execute(sql, params).fetchall()

    def overview(self, project_id: int, limit: int = 20) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 20), 100))

        rows = self._fetch(PROJECT_SQL, (int(project_id),))
        if not rows:
            raise ProjectNotFound(project_id)
        project = dict(zip(PROJECT_COLUMNS, rows[0]))

        sections: Dict[str, Any] = {}
        for key, spec in SECTION_SPECS.items():
            items = [
                dict(zip(spec['columns'], row))
                for row in self._fetch(spec['sql'], (int(project_id), limit))
            ]
            total_rows = self._fetch(
                "SELECT COUNT(*) FROM {0} WHERE project_id = ?".format(spec['table']),
                (int(project_id),),
            )
            sections[key] = {
                'items': items,
                'total': int(total_rows[0][0]) if total_rows else 0,
            }

        return {
            'project': project,
            'sales_orders': sections['sales_orders'],
            'sales_order_lines': sections['sales_order_lines'],
            'sales_order_schedules': sections['sales_order_schedules'],
            'work_orders': sections['work_orders'],
            'readonly': True,
        }
