# -*- coding: utf-8 -*-
"""库存组织上下文解析唯一入口。

各单据/行的组织来源优先级不同（字段 → 项目 → 订单抬头 → 库位 → 单一组织兜底），
但「怎么查、查不到怎么办」只应有一份实现。本模块只做解析，不写任何业务事实；
解析失败统一抛 `OrgNotResolved`，由调用方映射成各自的错误码/跳过语义。

解析**不做跨组织猜**：订单多组织行、系统多活跃组织时一律视为无法解析。
"""


def _to_int(value) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class OrgNotResolved(Exception):
    """组织无法唯一确定。"""

    code = 'ORG_NOT_RESOLVED'

    def __init__(self, message, candidates=None):
        super().__init__(message)
        self.candidates = list(candidates or [])


class OrgContextResolver:
    def __init__(self, data_source):
        self._ds = data_source

    # ---------------------------------------------------------------- 公开
    def from_fields(self, record, fields) -> int:
        """按声明顺序取第一个非零组织字段；全空即无法解析。"""
        fields = tuple(fields or ())
        for field in fields:
            value = _to_int((record or {}).get(field))
            if value:
                return value
        raise OrgNotResolved(
            '组织字段均缺失: %s' % (', '.join(fields) or '(未声明)'),
            candidates=fields)

    def from_project(self, project_id) -> int:
        org_id = self._row_org('projects', _to_int(project_id))
        if org_id:
            return org_id
        raise OrgNotResolved('项目 %s 未解析到库存组织' % project_id)

    def from_sales_order_line(self, line) -> tuple:
        """返回 (org_id, location_id)；库位组织优先，抬头组织兜底。"""
        line = line or {}
        location_id = _to_int(line.get('plant_location_id'))
        org_id = self._location_org(location_id) \
            or _to_int(line.get('header_org_id'))
        if org_id:
            return org_id, location_id
        raise OrgNotResolved('销售订单行 %s 未解析到库存组织' % line.get('id'))

    def from_work_order(self, work_order) -> int:
        """项目 → 订单抬头 → 订单行库位 → 订单唯一行组织 → 单一组织兜底。"""
        work_order = work_order or {}
        org_id = 0
        project_id = _to_int(work_order.get('project_id'))
        if project_id:
            org_id = self._row_org('projects', project_id)
        order_id = _to_int(work_order.get('order_id'))
        if not org_id and order_id:
            org_id = self._row_org('sales_orders', order_id)
        if not org_id:
            org_id = self._so_line_org(_to_int(work_order.get('order_line_id')))
        if not org_id and order_id:
            org_id = self._order_single_line_org(order_id)
        if not org_id:
            org_id = self.single_active_org()
        return org_id

    def single_active_org(self) -> int:
        """仅当系统只有一个活跃组织时兜底；多组织不猜。"""
        try:
            rows = self._ds.query(
                "SELECT id FROM orgs WHERE status = 'active' ORDER BY id")
        except Exception:
            rows = []
        if len(rows) == 1:
            org_id = _to_int(rows[0].get('id'))
            if org_id:
                return org_id
        raise OrgNotResolved(
            '系统存在 %s 个活跃组织，无法唯一确定库存组织' % len(rows))

    # ---------------------------------------------------------------- 内部
    def _row_org(self, table: str, row_id: int) -> int:
        if row_id <= 0:
            return 0
        try:
            rows = self._ds.query(
                'SELECT org_id FROM %s WHERE id = ?' % table, [row_id])
        except Exception:
            return 0
        return _to_int(rows[0].get('org_id')) if rows else 0

    def _location_org(self, location_id) -> int:
        return self._row_org('locations', _to_int(location_id))

    def _so_line_org(self, line_id: int) -> int:
        """销售订单行发运/生产库位所属组织。"""
        if line_id <= 0:
            return 0
        try:
            rows = self._ds.query(
                'SELECT plant_location_id FROM sales_order_lines WHERE id = ?',
                [line_id])
        except Exception:
            return 0
        return self._location_org(rows[0].get('plant_location_id')) \
            if rows else 0

    def _order_single_line_org(self, order_id: int) -> int:
        """订单全部行指向同一组织时才兜底，避免跨厂/跨组织猜测。"""
        if order_id <= 0:
            return 0
        try:
            rows = self._ds.query(
                'SELECT DISTINCT loc.org_id FROM sales_order_lines l '
                'JOIN locations loc ON loc.id = l.plant_location_id '
                'WHERE l.order_id = ? AND loc.org_id IS NOT NULL '
                'AND loc.org_id > 0', [order_id])
        except Exception:
            return 0
        org_ids = {_to_int(row.get('org_id')) for row in rows}
        return org_ids.pop() if len(org_ids) == 1 else 0
