# -*- coding: utf-8 -*-
"""
拆分 / 分摊服务 (1→N, 守恒 Σ子行 = 父行)
=========================================

一期规则引擎只能修改「当前行」字段 (RuleExecutor 返回 RuleResult),
无法一次写 N 行, 与「拆分/分摊」语义冲突。故本能力独立成服务,
经 BO Action 暴露 (见 meta/services/allocation_apply.py)。

守恒算法: 最大余数法 (largest remainder)
    以整数最小单位 (分) 计算, 按权重分配基数, 余数按
    (余数降序, 序号升序) 确定性补给前 diff 行, 保证
    Σ 分配值 == 总额 精确成立 (无浮点误差)。

为什么不用 RuleType.ALLOCATION:
    RULE_TYPE_MAP 对未知 rule_type 静默回退为 VALIDATION
    (meta/core/yaml_loader.py L213-231), 新增枚举若漏注册映射,
    分摊规则会被当成校验静默执行, 爆炸半径大。
"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Dict, List, Sequence


_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _require_ident(name: str, label: str) -> str:
    """校验 SQL 标识符 (表名/字段名), 防止入参拼接注入。"""
    if not name or not _IDENT_RE.match(name):
        raise AllocationError(f'{label} 非法: {name!r}')
    return name


class AllocationError(ValueError):
    """分摊/拆分参数非法 (权重、总量、规模等)。"""

    status_code = 400

    def __init__(self, message: str, status_code: int = None):
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _to_decimal(value: Any) -> Decimal:
    """把数值统一转成 Decimal。

    float 先转 str 再转 Decimal, 避免二进制浮点误差
    (如 Decimal(0.1) != Decimal('0.1'))。
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        value = str(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except InvalidOperation:
            raise AllocationError(f'无法解析为数值: {value!r}')
    raise AllocationError(f'不支持的数值类型: {type(value).__name__}')


def plan(total: Any, weights: Sequence[Any], scale: int = 2) -> List[Decimal]:
    """按权重把 total 精确划分为 N 份 (最大余数法)。

    Args:
        total: 待分配总额 (int / float / str / Decimal), 允许为负 (红字/冲销)
        weights: N 个正权重, 与目标行一一对应
        scale: 小数位数 (默认 2, 即分)

    Returns:
        长度 N 的 Decimal 列表, 满足 sum(result) == total (精确)

    Raises:
        AllocationError: weights 为空 / 含非正权重 / scale 为负 / 数值非法
    """
    if scale < 0:
        raise AllocationError(f'scale 不能为负: {scale}')

    n = len(weights)
    if n == 0:
        raise AllocationError('weights 不能为空')

    w = [_to_decimal(x) for x in weights]
    for x in w:
        if x <= 0:
            raise AllocationError(f'权重必须为正数, 收到: {x}')

    # 权重统一放大为整数 (保持比例): Decimal 的 // 是截断除法而非下取整,
    # 负总额下会破坏 max-remainder 的 [0, n) 性质, 故用 Python int 运算。
    w_scale = max(0, max(-x.as_tuple().exponent for x in w))
    w_int = [int(x * (10 ** w_scale)) for x in w]
    w_sum = sum(w_int)

    factor = Decimal(10) ** scale
    total_dec = _to_decimal(total)

    # 转整数最小单位 (四舍五入到 scale 位)
    t = int((total_dec * factor).to_integral_value(rounding=ROUND_HALF_UP))

    bases: List[int] = []
    rems: List[int] = []
    for x in w_int:
        prod = t * x
        bases.append(prod // w_sum)
        rems.append(prod % w_sum)

    # 余数总额必然落在 [0, n) —— 逐份 remainder 均 < W, 合计 < n*W
    diff = t - sum(bases)
    order = sorted(range(n), key=lambda i: (-rems[i], i))
    for k in range(diff):
        bases[order[k]] += 1

    quant = Decimal(10) ** -scale
    return [(Decimal(b) / factor).quantize(quant) for b in bases]


class AllocationService:
    """把父行金额/数量按权重分摊到 N 个子行 (或拆分成 N 个新行)。"""

    def __init__(self, data_source=None):
        self._ds = data_source

    @property
    def ds(self):
        """懒取默认数据源 (避免 import 期连库)。"""
        if self._ds is None:
            from meta.core.db_path import get_meta_db_path
            from meta.core.datasource import get_data_source
            self._ds = get_data_source('sqlite', database=get_meta_db_path())
        return self._ds

    @staticmethod
    def resolve_foreign_key(target_object: str, fk_field: str = None) -> str:
        """解析子表指向父记录的外键字段。

        显式指定优先; 否则从层级/关联配置推导 (与 computation_service
        的 _resolve_parent_aggregation 口径一致)。
        """
        if fk_field:
            return fk_field
        from meta.services.cascade_service import HierarchyConfigLoader
        return HierarchyConfigLoader.get_foreign_key(target_object) or ''

    def _resolve_children(self, target_object: str, parent_id: Any,
                          fk_field: str = None,
                          expected_count: int = None) -> List[Any]:
        """定位属于 parent_id 的子行 (按 id 升序), 用于分摊写入。

        归属校验由 fk = parent_id 过滤天然保证 (不会命中他人数据);
        expected_count 不为 None 时, 行数不等即报 422。

        Returns:
            子行 id 列表 (升序)
        """
        from meta.core.models import registry

        meta_obj = registry.get(target_object)
        if not meta_obj:
            raise AllocationError(f'未知对象: {target_object}')

        fk = self.resolve_foreign_key(target_object, fk_field)
        if not fk:
            raise AllocationError(
                f'无法推导 {target_object} 的父外键, 请显式指定 fk_field'
            )

        rows = self.ds.find(meta_obj.table_name, {fk: parent_id}, order_by='id')
        ids = [r.get('id') for r in rows if r.get('id') is not None]

        if expected_count is not None and len(ids) != expected_count:
            raise AllocationError(
                f'{target_object} 下 fk={parent_id} 的子行数 {len(ids)} '
                f'与权重数 {expected_count} 不一致',
                status_code=422,
            )
        return ids

    # ------------------------------------------------------------------
    # v1: 分摊到已有 N 行
    # ------------------------------------------------------------------

    def _build_executor(self):
        """构造走完整保存链路的 ActionExecutor (WriteGuard/校验/规则/compute)。"""
        from meta.core.action_executor import ActionExecutor
        from meta.core.rule_executor import RuleEngine
        return ActionExecutor(self.ds, RuleEngine(self.ds))

    @staticmethod
    def _normalize_weights(weights: Any):
        """把 weights 归一为 (values, ids)。

        weights 支持 [1, 3, 7] 或 [{'id': 11, 'weight': 3}, ...];
        ids 全为 None 表示按子行 id 升序位置对齐。
        """
        if not isinstance(weights, (list, tuple)):
            raise AllocationError('weights 必须是数组')
        values, ids = [], []
        for item in weights:
            if isinstance(item, dict):
                if 'weight' not in item:
                    raise AllocationError('权重项缺少 weight 字段')
                values.append(item['weight'])
                ids.append(item.get('id'))
            else:
                values.append(item)
                ids.append(None)
        return values, ids

    @staticmethod
    def _quantize(value: Any, scale: int) -> Decimal:
        return _to_decimal(value).quantize(Decimal(10) ** -scale)

    def allocate(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """把父行 source_field 按权重分摊写入 N 个已有子行的 target_field。

        spec:
            parent_id      (必填) 父记录 id
            target_object  (必填) 子对象类型 (兼容别名 child_object)
            target_field   (必填) 子行待写入字段
            weights        (必填) 权重数组 (数值 或 {'id','weight'} 对象数组)
            source_field   默认 = target_field
            fk_field       默认由 HierarchyConfigLoader 推导
            parent_object  默认由 HierarchyConfigLoader 推导
            scale          默认 2 (小数位)

        Returns:
            {'parent_id','target_object','target_field','total',
             'allocations': [{'id','value'}], 'verified': True}

        Raises:
            AllocationError: 参数非法 / 子行数不匹配(422) / 写后守恒校验失败
        """
        parent_id = spec.get('parent_id')
        if parent_id is None:
            raise AllocationError('parent_id 必填')

        target_object = spec.get('target_object') or spec.get('child_object')
        if not target_object:
            raise AllocationError('target_object 必填')

        target_field = _require_ident(spec.get('target_field'), 'target_field')
        source_field = _require_ident(
            spec.get('source_field') or target_field, 'source_field'
        )
        scale = spec.get('scale', 2)
        if not isinstance(scale, int) or scale < 0:
            raise AllocationError(f'scale 必须是非负整数: {scale!r}')

        values, weight_ids = self._normalize_weights(spec.get('weights'))

        from meta.core.models import registry

        child_meta = registry.get(target_object)
        if not child_meta:
            raise AllocationError(f'未知对象: {target_object}')
        _require_ident(child_meta.table_name, 'table_name')

        fk_field = _require_ident(
            self.resolve_foreign_key(target_object, spec.get('fk_field')),
            'fk_field',
        )

        child_ids = self._resolve_children(
            target_object, parent_id, fk_field=fk_field,
            expected_count=len(values),
        )

        # 带 id 的权重 → 按 id 对齐并校验归属 (权重行必须属于该父)
        if any(wid is not None for wid in weight_ids):
            if any(wid is None for wid in weight_ids):
                raise AllocationError('weights 不能混用带 id 与不带 id 的项')
            by_id = dict(zip(weight_ids, values))
            if set(by_id) != set(child_ids):
                raise AllocationError(
                    'weights 的 id 与父行下的子行不一致',
                    status_code=422,
                )
            values = [by_id[cid] for cid in child_ids]

        _, total = self._resolve_parent_total(
            target_object, parent_id, source_field, spec.get('parent_object')
        )

        allocations = plan(total, values, scale)

        executor = self._build_executor()
        with self.ds.transaction():
            for child_id, value in zip(child_ids, allocations):
                result = executor.execute(
                    child_meta, 'crud_update',
                    {'id': child_id, target_field: float(value)},
                )
                if not result.success:
                    raise AllocationError(
                        f'写入子行 #{child_id} 失败: '
                        f'{result.error or result.message}',
                        status_code=422,
                    )

            read_back = self._sum_children(
                child_meta.table_name, fk_field, parent_id, target_field
            )
            if self._quantize(read_back, scale) != self._quantize(total, scale):
                raise AllocationError(
                    f'守恒校验失败: Σ子行={read_back} != 父行={total}'
                )

        return {
            'parent_id': parent_id,
            'target_object': target_object,
            'target_field': target_field,
            'total': str(self._quantize(total, scale)),
            'allocations': [
                {'id': cid, 'value': str(val)}
                for cid, val in zip(child_ids, allocations)
            ],
            'verified': True,
        }

    @staticmethod
    def _resolve_parent_object(target_object: str) -> str:
        from meta.services.cascade_service import HierarchyConfigLoader
        return HierarchyConfigLoader.get_parent_object(target_object) or ''

    def _resolve_parent_total(self, target_object: str, parent_id: Any,
                              source_field: str,
                              parent_object: str = None):
        """定位父行并取出待分配的总额 (allocate / split 共用)。"""
        from meta.core.models import registry

        parent_object = parent_object or self._resolve_parent_object(target_object)
        parent_meta = registry.get(parent_object) if parent_object else None
        if not parent_meta:
            raise AllocationError(f'无法推导 {target_object} 的父对象')
        _require_ident(parent_meta.table_name, 'table_name')

        parent_row = self.ds.find_by_id(parent_meta.table_name, parent_id)
        if not parent_row:
            raise AllocationError(
                f'{parent_object} #{parent_id} 不存在', status_code=404
            )
        total = parent_row.get(source_field)
        if total is None:
            raise AllocationError(
                f'父行 {source_field} 为空, 无法分摊', status_code=422
            )
        return parent_meta, total

    # ------------------------------------------------------------------
    # v2: 拆分成 N 个新行
    # ------------------------------------------------------------------

    def split(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """把父行 source_field 拆成 N 个**新建**子行 (共用同一守恒算法)。

        spec: 与 allocate 相同, 另有
            split_count  未给 weights 时按此均分 (weights 优先)
            template     每个新行的附加字段 (如 name/unit)

        Returns:
            {'parent_id','target_object','target_field','total',
             'allocations': [{'id','value'}], 'verified': True}

        Raises:
            AllocationError: 参数非法 / 写入失败 / 写后守恒校验失败
        """
        parent_id = spec.get('parent_id')
        if parent_id is None:
            raise AllocationError('parent_id 必填')

        target_object = spec.get('target_object') or spec.get('child_object')
        if not target_object:
            raise AllocationError('target_object 必填')

        target_field = _require_ident(spec.get('target_field'), 'target_field')
        source_field = _require_ident(
            spec.get('source_field') or target_field, 'source_field'
        )
        scale = spec.get('scale', 2)
        if not isinstance(scale, int) or scale < 0:
            raise AllocationError(f'scale 必须是非负整数: {scale!r}')

        if spec.get('weights') is not None:
            values, _ = self._normalize_weights(spec['weights'])
            if len(values) == 0:
                raise AllocationError('weights 不能为空')
        else:
            split_count = spec.get('split_count')
            if not isinstance(split_count, int) or split_count < 1:
                raise AllocationError('weights 与 split_count 至少提供一个')
            values = [1] * split_count

        template = spec.get('template') or {}
        if not isinstance(template, dict):
            raise AllocationError('template 必须是对象')

        from meta.core.models import registry

        child_meta = registry.get(target_object)
        if not child_meta:
            raise AllocationError(f'未知对象: {target_object}')
        _require_ident(child_meta.table_name, 'table_name')

        fk_field = _require_ident(
            self.resolve_foreign_key(target_object, spec.get('fk_field')),
            'fk_field',
        )

        _, total = self._resolve_parent_total(
            target_object, parent_id, source_field, spec.get('parent_object')
        )

        allocations = plan(total, values, scale)

        executor = self._build_executor()
        created: List[Any] = []
        with self.ds.transaction():
            for value in allocations:
                params = dict(template)
                params[fk_field] = parent_id
                params[target_field] = float(value)
                result = executor.execute(child_meta, 'crud_create', params)
                if not result.success or not result.last_insert_id:
                    raise AllocationError(
                        f'创建子行失败: {result.error or result.message}',
                        status_code=422,
                    )
                created.append(result.last_insert_id)

            read_back = self._sum_rows(
                child_meta.table_name, created, target_field
            )
            if self._quantize(read_back, scale) != self._quantize(total, scale):
                raise AllocationError(
                    f'守恒校验失败: Σ新行={read_back} != 父行={total}'
                )

        return {
            'parent_id': parent_id,
            'target_object': target_object,
            'target_field': target_field,
            'total': str(self._quantize(total, scale)),
            'allocations': [
                {'id': cid, 'value': str(val)}
                for cid, val in zip(created, allocations)
            ],
            'verified': True,
        }

    def _sum_children(self, table_name: str, fk_field: str, parent_id: Any,
                      target_field: str) -> Any:
        """按父外键回读子行目标字段合计 (守恒校验用)。"""
        sql = (
            f'SELECT SUM({target_field}) FROM {table_name} WHERE {fk_field} = ?'
        )
        cursor = self.ds.execute(sql, (parent_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0

    def _sum_rows(self, table_name: str, ids: Sequence[Any],
                  target_field: str) -> Any:
        """按主键集合回读目标字段合计 (split 守恒校验用)。"""
        if not ids:
            return 0
        placeholders = ','.join(['?'] * len(ids))
        sql = (
            f'SELECT SUM({target_field}) FROM {table_name} '
            f'WHERE id IN ({placeholders})'
        )
        cursor = self.ds.execute(sql, tuple(ids))
        row = cursor.fetchone()
        return row[0] if row and row[0] is not None else 0
