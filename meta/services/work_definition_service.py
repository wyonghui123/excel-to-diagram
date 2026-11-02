# -*- coding: utf-8 -*-
"""作业定义服务 —— 配方基准 / 工序产出 / 替代资源组的写前校验与只读计算。

依据: docs/specs/spec-routing-process-manufacturing-benchmark-2026-11-01.md
      §10.2（work_definitions 扩展）/ §10.3（工序产出）/ §10.4（替代资源组）
      §10.6（recipe 语义）/ §10.7（服务层）

口径:
  · `definition_kind=recipe` 必须填 `item_id` / `base_qty` / `base_uom_id`，
    且 `base_qty > 0`；routing / service_template 的基准量三列必须为空。
  · `base_uom_id` 必须与 `items.base_uom` 同 `uom_group`（跨组拒绝）。
  · 已有工序或已生效后，`definition_kind` / `base_qty` / `base_uom_id` 不可改，
    改版走新 revision。
  · 主产出唯一且必须 `output_type=product`；联/副产品才可填成本分摊，
    同工序合计 ≤100。
  · 替代资源组按 `replacement_group` 整包替换；包内 `role` / `qty` /
    `required_skill_id` / `min_level` 必须一致；生效时每个替代组至少 2 个替换包。
  · 本服务只读校验 / 计算，不写业务字段，也不引入自定义 CRUD；写路径仍走通用 BO API。

覆写 `_load_*` 即可注入测试数据。
"""

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

DEFINITION_TABLE = 'work_definitions'
OPERATION_TABLE = 'work_definition_operations'
OUTPUT_TABLE = 'work_definition_operation_outputs'
REQUIREMENT_TABLE = 'operation_resource_requirements'
ITEM_TABLE = 'items'
UOM_TABLE = 'uoms'
RESOURCE_TABLE = 'resources'
RESOURCE_GROUP_TABLE = 'resource_groups'

KIND_ROUTING = 'routing'
KIND_RECIPE = 'recipe'
KIND_SERVICE_TEMPLATE = 'service_template'
DEFINITION_KINDS = (KIND_ROUTING, KIND_RECIPE, KIND_SERVICE_TEMPLATE)

OUTPUT_PRODUCT = 'product'
OUTPUT_CO_PRODUCT = 'co_product'
OUTPUT_BY_PRODUCT = 'by_product'
OUTPUT_TYPES = (OUTPUT_PRODUCT, OUTPUT_CO_PRODUCT, OUTPUT_BY_PRODUCT)

STATUS_DRAFT = 'draft'
STATUS_ACTIVE = 'active'

#: 替换包内必须一致的需求行字段
PACKAGE_CONSISTENCY_FIELDS = ('role', 'qty', 'required_skill_id', 'min_level')

_MAX_COST_ALLOCATION = Decimal('100')


class WorkDefinitionError(Exception):
    """作业定义业务校验错误（拦截器转为 ValidationFailedError）。"""

    def __init__(self, message: str, field_name: Optional[str] = None,
                 rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


def _status(value: Any) -> str:
    return _text(value).lower() or STATUS_DRAFT


def _decimal(value: Any, field_name: str, rule: str) -> Optional[Decimal]:
    if _blank(value):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise WorkDefinitionError('%s 必须是数字' % field_name,
                                  field_name=field_name, rule=rule)


def _as_date(value: Any, field_name: str) -> Optional[date]:
    if _blank(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except (TypeError, ValueError):
        raise WorkDefinitionError('%s 必须是日期' % field_name,
                                  field_name=field_name, rule='WD_DATE_INVALID')


class WorkDefinitionService:
    """作业定义 / 工序产出 / 替代资源组的业务校验。"""

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 作业定义（recipe / routing）
    # ------------------------------------------------------------------
    def validate_definition(self, payload: Dict[str, Any],
                            existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """校验作业定义创建 / 更新，返回归一化后的合并值。

        `payload` 为本次写入字段，`existing` 为库内原行（更新时传入）。
        只校验不落库；拦截器按返回的 `base_qty` / `base_uom_id` 回填归一化值。
        """
        patch = dict(payload or {})
        old = dict(existing or {})
        merged = dict(old)
        merged.update(patch)
        definition_id = old.get('id')

        kind = _text(merged.get('definition_kind') or KIND_ROUTING).lower()
        if kind not in DEFINITION_KINDS:
            raise WorkDefinitionError(
                '未知的作业定义类型 %s' % kind,
                field_name='definition_kind', rule='WD_KIND_INVALID')

        self._validate_kind_immutable(kind, old, patch, definition_id)
        self._validate_base_freeze(old, patch, definition_id)
        self._validate_validity(merged)

        if kind == KIND_RECIPE:
            self._validate_recipe_base(merged)
        else:
            self._validate_non_recipe_base(merged, kind)

        target_status = _status(patch.get('status') or merged.get('status'))
        if kind == KIND_RECIPE and target_status == STATUS_ACTIVE:
            if not definition_id or not self._has_primary_output(definition_id):
                raise WorkDefinitionError(
                    '生效的配方至少需要一个主产出（is_primary=1）',
                    field_name='status', rule='WD_RECIPE_PRIMARY_REQUIRED')
        return merged

    def _validate_kind_immutable(self, kind: str, old: Dict[str, Any],
                                 patch: Dict[str, Any],
                                 definition_id: Any) -> None:
        if not old or 'definition_kind' not in patch:
            return
        old_kind = _text(old.get('definition_kind') or KIND_ROUTING).lower()
        if kind == old_kind:
            return
        if self._count_operations(definition_id) > 0 \
                or _status(old.get('status')) != STATUS_DRAFT:
            raise WorkDefinitionError(
                '已有工序或非草稿状态的作业定义不可修改定义类型',
                field_name='definition_kind', rule='WD_KIND_IMMUTABLE')

    def _validate_base_freeze(self, old: Dict[str, Any],
                              patch: Dict[str, Any],
                              definition_id: Any) -> None:
        """recipe 的 base_qty / base_uom_id 在已有工序或生效后冻结。"""
        if not old or _text(old.get('definition_kind')) != KIND_RECIPE:
            return
        if self._count_operations(definition_id) <= 0 \
                and _status(old.get('status')) == STATUS_DRAFT:
            return
        for field in ('base_qty', 'base_uom_id'):
            if field not in patch:
                continue
            old_value = old.get(field)
            new_value = patch.get(field)
            if _blank(old_value) and _blank(new_value):
                continue
            if self._same_number(old_value, new_value):
                continue
            raise WorkDefinitionError(
                '配方基准字段 %s 在已有工序或生效后不可修改，请新建版本' % field,
                field_name=field, rule='WD_BASE_IMMUTABLE')

    @staticmethod
    def _same_number(left: Any, right: Any) -> bool:
        if _blank(left) or _blank(right):
            return False
        try:
            return Decimal(str(left)) == Decimal(str(right))
        except (InvalidOperation, TypeError, ValueError):
            return left == right

    def _validate_validity(self, merged: Dict[str, Any]) -> None:
        valid_from = _as_date(merged.get('valid_from'), 'valid_from')
        valid_to = _as_date(merged.get('valid_to'), 'valid_to')
        if valid_from and valid_to and valid_to <= valid_from:
            raise WorkDefinitionError(
                '有效期止必须晚于有效期起',
                field_name='valid_to', rule='WD_VALIDITY_INVALID')

    def _validate_recipe_base(self, merged: Dict[str, Any]) -> None:
        if _blank(merged.get('item_id')):
            raise WorkDefinitionError(
                '配方必须指定物料', field_name='item_id',
                rule='WD_RECIPE_ITEM_REQUIRED')
        base_qty = _decimal(merged.get('base_qty'), 'base_qty',
                            'WD_BASE_QTY_INVALID')
        if base_qty is None or base_qty <= 0:
            raise WorkDefinitionError(
                '配方基准量必须大于 0', field_name='base_qty',
                rule='WD_BASE_QTY_INVALID')
        if _blank(merged.get('base_uom_id')):
            raise WorkDefinitionError(
                '配方必须指定基准单位', field_name='base_uom_id',
                rule='WD_BASE_UOM_REQUIRED')
        batch_qty = _decimal(merged.get('batch_qty'), 'batch_qty',
                             'WD_BATCH_QTY_INVALID')
        if batch_qty is not None and batch_qty <= 0:
            raise WorkDefinitionError(
                '标准批次量必须大于 0', field_name='batch_qty',
                rule='WD_BATCH_QTY_INVALID')
        self._assert_uom_group(merged.get('item_id'),
                               merged.get('base_uom_id'),
                               'base_uom_id', 'WD_BASE_UOM_GROUP')

    def _validate_non_recipe_base(self, merged: Dict[str, Any],
                                  kind: str) -> None:
        for field in ('base_qty', 'base_uom_id', 'batch_qty'):
            if not _blank(merged.get(field)):
                raise WorkDefinitionError(
                    '%s 类型的作业定义不得填写 %s' % (kind, field),
                    field_name=field, rule='WD_BASE_NOT_ALLOWED')

    def _has_primary_output(self, definition_id: Any) -> bool:
        rows = self._query(
            'SELECT COUNT(*) AS cnt FROM work_definition_operation_outputs '
            'WHERE is_primary = 1 AND output_type = ? AND operation_id IN '
            '(SELECT id FROM work_definition_operations WHERE definition_id = ?)',
            [OUTPUT_PRODUCT, definition_id])
        return int((rows or [{}])[0].get('cnt') or 0) > 0

    def _count_operations(self, definition_id: Any) -> int:
        if _blank(definition_id):
            return 0
        rows = self._query(
            'SELECT COUNT(*) AS cnt FROM work_definition_operations '
            'WHERE definition_id = ?', [definition_id])
        return int((rows or [{}])[0].get('cnt') or 0)

    # ------------------------------------------------------------------
    # 工序产出
    # ------------------------------------------------------------------
    def validate_operation_outputs(self, operation_id: Any,
                                   payload: Optional[Dict[str, Any]] = None,
                                   record_id: Any = None) -> List[Dict[str, Any]]:
        """校验某工序的产出集合（含本次写入的候选行）。

        `payload` 为本次写入字段；`record_id` 为更新行 id（None 表示新增）。
        返回归一化后的完整产出清单，供拦截器回填数量 / 单位。
        """
        if _blank(operation_id):
            raise WorkDefinitionError(
                '产出必须归属工序', field_name='operation_id',
                rule='WD_OUTPUT_OPERATION_REQUIRED')

        rows = [dict(row) for row in (self._load_outputs(operation_id) or [])]
        if payload is not None:
            candidate = dict(payload)
            if record_id is None:
                rows.append(candidate)
            else:
                replaced = False
                for index, row in enumerate(rows):
                    if str(row.get('id')) == str(record_id):
                        merged = dict(row)
                        merged.update(candidate)
                        rows[index] = merged
                        replaced = True
                        break
                if not replaced:
                    candidate['id'] = record_id
                    rows.append(candidate)

        normalized = [self._normalize_output(row) for row in rows]

        seen_items = set()
        for row in normalized:
            item_key = _text(row.get('item_id'))
            if item_key in seen_items:
                raise WorkDefinitionError(
                    '同一工序不能重复挂载物料 %s' % item_key,
                    field_name='item_id', rule='WD_OUTPUT_ITEM_DUPLICATE')
            seen_items.add(item_key)

        primaries = [row for row in normalized if row.get('is_primary')]
        if len(primaries) > 1:
            raise WorkDefinitionError(
                '同一工序至多一条主产出',
                field_name='is_primary', rule='WD_OUTPUT_PRIMARY_DUPLICATE')
        for row in primaries:
            if row.get('output_type') != OUTPUT_PRODUCT:
                raise WorkDefinitionError(
                    '主产出必须是主产品类型',
                    field_name='is_primary', rule='WD_OUTPUT_PRIMARY_TYPE')
        for row in normalized:
            if row.get('output_type') in (OUTPUT_CO_PRODUCT, OUTPUT_BY_PRODUCT) \
                    and row.get('is_primary'):
                raise WorkDefinitionError(
                    '联产品 / 副产品不能设为主产出',
                    field_name='is_primary', rule='WD_OUTPUT_PRIMARY_TYPE')

        allocation = Decimal('0')
        for row in normalized:
            pct = _decimal(row.get('cost_allocation_pct'),
                           'cost_allocation_pct', 'WD_OUTPUT_ALLOC_INVALID')
            if pct is None:
                continue
            if row.get('output_type') == OUTPUT_PRODUCT:
                raise WorkDefinitionError(
                    '主产品不填成本分摊比例',
                    field_name='cost_allocation_pct',
                    rule='WD_OUTPUT_ALLOC_NOT_ALLOWED')
            if pct < 0 or pct > _MAX_COST_ALLOCATION:
                raise WorkDefinitionError(
                    '成本分摊比例必须在 0 到 100 之间',
                    field_name='cost_allocation_pct',
                    rule='WD_OUTPUT_ALLOC_RANGE')
            allocation += pct
        if allocation > _MAX_COST_ALLOCATION:
            raise WorkDefinitionError(
                '联产品 / 副产品成本分摊合计不得超过 100%',
                field_name='cost_allocation_pct',
                rule='WD_OUTPUT_ALLOC_TOTAL')
        return normalized

    def _normalize_output(self, row: Dict[str, Any]) -> Dict[str, Any]:
        output_type = _text(row.get('output_type') or OUTPUT_PRODUCT).lower()
        if output_type not in OUTPUT_TYPES:
            raise WorkDefinitionError(
                '未知的产出类型 %s' % output_type,
                field_name='output_type', rule='WD_OUTPUT_TYPE_INVALID')
        qty = _decimal(row.get('qty'), 'qty', 'WD_OUTPUT_QTY_INVALID')
        if qty is None or qty <= 0:
            raise WorkDefinitionError(
                '产出数量必须大于 0', field_name='qty',
                rule='WD_OUTPUT_QTY_INVALID')
        if _blank(row.get('item_id')):
            raise WorkDefinitionError(
                '产出必须指定物料', field_name='item_id',
                rule='WD_OUTPUT_ITEM_REQUIRED')
        qty_uom_id = row.get('qty_uom_id')
        if not _blank(qty_uom_id):
            self._assert_uom_group(row.get('item_id'), qty_uom_id,
                                   'qty_uom_id', 'WD_OUTPUT_UOM_GROUP')
        normalized = dict(row)
        normalized['output_type'] = output_type
        normalized['qty'] = float(qty)
        normalized['is_primary'] = bool(row.get('is_primary'))
        return normalized

    # ------------------------------------------------------------------
    # 计划量缩放（只读）
    # ------------------------------------------------------------------
    def scale_operation_outputs(self, definition_id: Any,
                                order_qty: Any) -> List[Dict[str, Any]]:
        """按订单量缩放工序产出计划量（只读，不落库）。

        公式: planned = qty × (order_qty / base_qty) × operation.qty_per；
        routing 的 `base_qty` 视为 1。
        """
        order_value = _decimal(order_qty, 'order_qty', 'WD_ORDER_QTY_INVALID')
        if order_value is None or order_value <= 0:
            raise WorkDefinitionError(
                '订单量必须大于 0', field_name='order_qty',
                rule='WD_ORDER_QTY_INVALID')

        definition = self._load_definition(definition_id) or {}
        kind = _text(definition.get('definition_kind') or KIND_ROUTING).lower()
        base_qty = _decimal(definition.get('base_qty'), 'base_qty',
                            'WD_BASE_QTY_INVALID')
        if kind == KIND_RECIPE and (base_qty is None or base_qty <= 0):
            raise WorkDefinitionError(
                '配方缺少有效的基准量，无法缩放',
                field_name='base_qty', rule='WD_BASE_QTY_INVALID')
        if base_qty is None or base_qty <= 0:
            base_qty = Decimal('1')

        operations = self._load_operations(definition_id) or []
        outputs = self._load_definition_outputs(definition_id) or []
        by_operation: Dict[str, List[Dict[str, Any]]] = {}
        for row in outputs:
            by_operation.setdefault(str(row.get('operation_id')), []).append(row)

        factor = order_value / base_qty
        result: List[Dict[str, Any]] = []
        for operation in operations:
            operation_id = operation.get('id')
            qty_per = _decimal(operation.get('qty_per'), 'qty_per',
                               'WD_QTY_PER_INVALID')
            if qty_per is None or qty_per <= 0:
                qty_per = Decimal('1')
            for row in by_operation.get(str(operation_id), []):
                qty = _decimal(row.get('qty'), 'qty', 'WD_OUTPUT_QTY_INVALID')
                if qty is None:
                    continue
                planned = qty * factor * qty_per
                result.append({
                    'operation_id': operation_id,
                    'operation_seq': operation.get('seq'),
                    'item_id': row.get('item_id'),
                    'output_type': row.get('output_type'),
                    'qty': round(float(planned), 6),
                    'qty_uom_id': row.get('qty_uom_id'),
                    'is_primary': bool(row.get('is_primary')),
                })
        return result

    # ------------------------------------------------------------------
    # 替代资源组
    # ------------------------------------------------------------------
    def validate_active_substitutes(self, definition_id: Any) -> None:
        """作业定义生效前，逐工序校验替代组（每包至少 2 个替换包）。"""
        for operation in self._load_operations(definition_id) or []:
            self.validate_substitute_groups(operation.get('id'), active=True)

    def validate_substitute_groups(self, operation_id: Any,
                                   active: bool = False) -> List[str]:
        """校验替代资源组，返回告警（仅 1 包时告警；生效时直接拒绝）。

        `active=True` 表示作业定义即将生效：每个替代组至少 2 个替换包，
        不足即抛错；`active=False`（保存）只返回告警。
        """
        rows = list(self._load_requirements(operation_id) or [])
        warnings: List[str] = []
        groups: Dict[str, List[Dict[str, Any]]] = {}

        for row in rows:
            substitute = _text(row.get('substitute_group'))
            replacement = _text(row.get('replacement_group'))
            if replacement and not substitute:
                raise WorkDefinitionError(
                    '替换包必须指定替代组',
                    field_name='substitute_group',
                    rule='WD_SUBSTITUTE_GROUP_REQUIRED')
            if substitute:
                groups.setdefault(substitute, []).append(row)

        for substitute, group_rows in groups.items():
            packages: Dict[str, List[Dict[str, Any]]] = {}
            for row in group_rows:
                packages.setdefault(
                    _text(row.get('replacement_group')), []).append(row)

            if len(packages) < 2:
                message = '替代组 %s 仅有 %d 个替换包，至少需要 2 个' % (
                    substitute, len(packages))
                if active:
                    raise WorkDefinitionError(
                        message, field_name='replacement_group',
                        rule='WD_SUBSTITUTE_PACKAGES')
                warnings.append(message)

            for replacement, package_rows in packages.items():
                self._validate_package_fields(
                    substitute, replacement, package_rows)

            self._validate_group_primary(substitute, group_rows)
        return warnings

    def _validate_package_fields(self, substitute: str, replacement: str,
                                 rows: List[Dict[str, Any]]) -> None:
        baseline = rows[0]
        for row in rows[1:]:
            for field in PACKAGE_CONSISTENCY_FIELDS:
                left = baseline.get(field)
                right = row.get(field)
                if field == 'qty' and self._same_number(left, right):
                    continue
                if field != 'qty' and _text(left) == _text(right):
                    continue
                raise WorkDefinitionError(
                    '替代组 %s 的替换包 %s 内 %s 不一致' % (
                        substitute, replacement, field),
                    field_name=field, rule='WD_SUBSTITUTE_PACKAGE_MISMATCH')

    def _validate_group_primary(self, substitute: str,
                                rows: List[Dict[str, Any]]) -> None:
        by_role: Dict[str, int] = {}
        for row in rows:
            if not bool(row.get('is_primary')):
                continue
            role = _text(row.get('role'))
            by_role[role] = by_role.get(role, 0) + 1
        for role, count in by_role.items():
            if count > 1:
                raise WorkDefinitionError(
                    '替代组 %s 的角色 %s 至多一条主资源' % (substitute, role),
                    field_name='is_primary',
                    rule='WD_SUBSTITUTE_PRIMARY_DUPLICATE')

    def resolve_substitute_options(self, operation_id: Any) -> List[Dict[str, Any]]:
        """按 `priority` 返回替换包列表，并做「目标是否存在」的预判。

        不查实时产能；`satisfiable` 仅表示包内每行都有可用的资源 / 资源组引用。
        """
        rows = list(self._load_requirements(operation_id) or [])
        packages: Dict[tuple, List[Dict[str, Any]]] = {}
        for row in rows:
            substitute = _text(row.get('substitute_group'))
            if not substitute:
                continue
            key = (substitute, _text(row.get('replacement_group')))
            packages.setdefault(key, []).append(row)

        result: List[Dict[str, Any]] = []
        for (substitute, replacement), package_rows in packages.items():
            priorities = []
            for row in package_rows:
                priority = _decimal(row.get('priority'), 'priority',
                                    'WD_PRIORITY_INVALID')
                priorities.append(priority if priority is not None
                                  else Decimal('1'))
            result.append({
                'substitute_group': substitute,
                'replacement_group': replacement,
                'priority': float(min(priorities)),
                'is_primary': any(bool(row.get('is_primary'))
                                  for row in package_rows),
                'satisfiable': all(self._row_target_exists(row)
                                   for row in package_rows),
                'rows': package_rows,
            })
        result.sort(key=lambda item: (
            0 if item['is_primary'] else 1,
            item['priority'],
            item['substitute_group'],
            item['replacement_group'],
        ))
        return result

    def _row_target_exists(self, row: Dict[str, Any]) -> bool:
        resource_id = row.get('resource_id')
        group_id = row.get('resource_group_id')
        if not _blank(resource_id):
            return bool(self._load_resource(resource_id))
        if not _blank(group_id):
            return bool(self._load_resource_group(group_id))
        return False

    # ------------------------------------------------------------------
    # 单位组校验
    # ------------------------------------------------------------------
    def _assert_uom_group(self, item_id: Any, uom_id: Any,
                          field_name: str, rule: str) -> None:
        item = self._load_item(item_id) or {}
        base_uom = item.get('base_uom')
        if _blank(base_uom):
            raise WorkDefinitionError(
                '物料缺少基本单位，无法校验单位组',
                field_name=field_name, rule=rule)
        target_uom = self._load_uom(uom_id) or {}
        if not target_uom:
            raise WorkDefinitionError(
                '计量单位 %s 不存在' % uom_id,
                field_name=field_name, rule=rule)
        item_uom = self._load_uom(base_uom) or {}
        item_group = item_uom.get('uom_group_id')
        target_group = target_uom.get('uom_group_id')
        if not _blank(item_group) and not _blank(target_group) \
                and _text(item_group) != _text(target_group):
            raise WorkDefinitionError(
                '单位与物料基本单位不属于同一计量单位组',
                field_name=field_name, rule=rule)

    # ------------------------------------------------------------------
    # 数据访问（测试可覆写）
    # ------------------------------------------------------------------
    def _query(self, sql: str, params: Optional[Iterable[Any]] = None) -> List[Dict[str, Any]]:
        try:
            return self.ds.query(sql, list(params or [])) or []
        except Exception:  # pragma: no cover - 数据源异常交由上层处理
            logger.exception('work definition query failed: %s', sql)
            return []

    def _load_definition(self, definition_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(definition_id):
            return None
        rows = self._query(
            'SELECT * FROM work_definitions WHERE id = ?', [definition_id])
        return rows[0] if rows else None

    def _load_item(self, item_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(item_id):
            return None
        rows = self._query('SELECT * FROM items WHERE id = ?', [item_id])
        return rows[0] if rows else None

    def _load_uom(self, uom_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(uom_id):
            return None
        rows = self._query('SELECT * FROM uoms WHERE id = ?', [uom_id])
        return rows[0] if rows else None

    def _load_operations(self, definition_id: Any) -> List[Dict[str, Any]]:
        if _blank(definition_id):
            return []
        return self._query(
            'SELECT * FROM work_definition_operations WHERE definition_id = ? '
            'ORDER BY seq, id', [definition_id])

    def _load_outputs(self, operation_id: Any) -> List[Dict[str, Any]]:
        if _blank(operation_id):
            return []
        return self._query(
            'SELECT * FROM work_definition_operation_outputs '
            'WHERE operation_id = ? ORDER BY id', [operation_id])

    def _load_definition_outputs(self, definition_id: Any) -> List[Dict[str, Any]]:
        if _blank(definition_id):
            return []
        return self._query(
            'SELECT o.* FROM work_definition_operation_outputs o '
            'JOIN work_definition_operations op ON op.id = o.operation_id '
            'WHERE op.definition_id = ? ORDER BY op.seq, o.id', [definition_id])

    def _load_requirements(self, operation_id: Any) -> List[Dict[str, Any]]:
        if _blank(operation_id):
            return []
        return self._query(
            'SELECT * FROM operation_resource_requirements '
            'WHERE operation_id = ? ORDER BY priority, id', [operation_id])

    def _load_resource(self, resource_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(resource_id):
            return None
        rows = self._query('SELECT * FROM resources WHERE id = ?', [resource_id])
        return rows[0] if rows else None

    def _load_resource_group(self, group_id: Any) -> Optional[Dict[str, Any]]:
        if _blank(group_id):
            return None
        rows = self._query(
            'SELECT * FROM resource_groups WHERE id = ?', [group_id])
        return rows[0] if rows else None
