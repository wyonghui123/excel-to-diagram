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

from decimal import (
    Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP,
)
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence
import uuid


_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# allocation_rule.basis 的六种分摊基数（Oracle LCM）。前四种需调用方给出
# `basis_field`（从子行哪一列取权重）——引擎不内置业务字段名映射，见
# `_derive_weights`。`equal` 与 `manual` 不读子行数据。
BASIS_EQUAL = 'equal'
BASIS_VALUE = 'value'
BASIS_QUANTITY = 'quantity'
BASIS_WEIGHT = 'weight'
BASIS_VOLUME = 'volume'
BASIS_MANUAL = 'manual'

BASES = frozenset({
    BASIS_EQUAL, BASIS_VALUE, BASIS_QUANTITY,
    BASIS_WEIGHT, BASIS_VOLUME, BASIS_MANUAL,
})
#: 需从子行字段取权重的基数（`equal`/`manual` 除外）
BASIS_FROM_FIELD = frozenset({
    BASIS_VALUE, BASIS_QUANTITY, BASIS_WEIGHT, BASIS_VOLUME,
})

#: allocation_rule.rounding 的取整方式。`none` = 保持 plan() 原样（四舍五入到
#: scale 位，最大余数法保证 Σ 守恒），其余三种是**先按方向取整总额**再分摊，
#: 故 Σ 仍守恒（总额本身就是取整后的值），只是总额与未取整源值可能差 ≤1 单位。
ROUNDING_MODES = frozenset({'none', 'round', 'ceil', 'floor'})


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


def plan(total: Any, weights: Sequence[Any], scale: int = 2,
         rounding: str = 'none') -> List[Decimal]:
    """按权重把 total 精确划分为 N 份 (最大余数法)。

    Args:
        total: 待分配总额 (int / float / str / Decimal), 允许为负 (红字/冲销)
        weights: N 个正权重, 与目标行一一对应
        scale: 小数位数 (默认 2, 即分)
        rounding: 取整方式（`allocation_rule.rounding`）：
            `none`（默认，= 原行为，`ROUND_HALF_UP`）/ `round`（同上，显式）
            / `ceil`（`ROUND_CEILING`）/ `floor`（`ROUND_FLOOR`）。

            【为什么 `none` 与 `round` 等价】不取整不是"不量化"——总额必须落到
            `scale` 位最小单位才能做整数除法，否则 `sum != total`。二者只差在
            是否由配置显式声明。

    Returns:
        长度 N 的 Decimal 列表, 满足 sum(result) == total (精确)。
        `ceil`/`floor` 下 `total` 是**取整后**的总额，故守恒仍精确成立，
        但与传入的未取整源值可能相差 ≤1 个最小单位。

    Raises:
        AllocationError: weights 为空 / 含非正权重 / scale 为负 /
            数值非法 / rounding 非法
    """
    if scale < 0:
        raise AllocationError(f'scale 不能为负: {scale}')
    if rounding not in ROUNDING_MODES:
        raise AllocationError(
            f'rounding 非法: {rounding!r}；可选 {sorted(ROUNDING_MODES)}'
        )

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

    # 转整数最小单位。`none`/`round` 走四舍五入（原有行为）；
    # `ceil`/`floor` 按配置方向取整总额 —— 守恒仍成立，因为分摊基数就是取整后的 t。
    mode = ROUND_HALF_UP if rounding in ('none', 'round') else (
        ROUND_CEILING if rounding == 'ceil' else ROUND_FLOOR
    )
    t = int((total_dec * factor).to_integral_value(rounding=mode))

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


def plan_floor(total: Any, weights: Sequence[Any], floor: Any = None,
               scale: int = 2, rounding: str = 'none') -> List[Decimal]:
    """在 `plan()` 之上加**地板价**下限（waterfall 迭代），守恒不变。

    【为什么必须迭代而非一次钳制】`plan()` 只保证 Σ 守恒，不保证每份 ≥ floor。
    一次钳制（`max(v, floor)`）会把 Σ 抬高，守恒即破。waterfall 的做法是：
    把低于 floor 的行**钉在 floor**，剩余金额在**未触顶行**按原权重重分，
    直到无人低于 floor 或无人可再分。故本函数是 O(n²) 最坏、但 n = 子行数
    （数十量级），无需优化。

    【守恒恒等式】每轮重分的是 `total - Σ已钉住行`，故最终
    `Σ = Σ已钉住 + (total - Σ已钉住) = total` 精确成立。

    【触顶耗尽】若所有行都被 floor 钉住而仍有余额（即 `n × floor > total`），
    数学上无解 → 抛 `AllocationError`（422），**不静默截断**：截断会让
    「摊得总额 ≠ 待摊总额」，正是分摊最忌的静默错误。

    Args:
        floor: 地板价；None / 非正 → 退化为 `plan()`（不做任何钳制）

    Returns:
        长度 N 的 Decimal 列表，每份 ≥ floor 且 Σ == total（精确）
    """
    if floor is None:
        return plan(total, weights, scale, rounding)

    f = _to_decimal(floor)
    quant = Decimal(10) ** -scale
    f = f.quantize(quant)
    if f <= 0:
        # 地板价非正 = 无约束（负地板价对正金额无意义，对负金额是放宽）
        return plan(total, weights, scale, rounding)

    n = len(weights)
    values = plan(total, weights, scale, rounding)
    if n * f > _to_decimal(total).quantize(quant):
        raise AllocationError(
            f'地板价无法满足: {n} 行 × {f} = {n * f} > 待摊总额 '
            f'{_to_decimal(total).quantize(quant)}',
            status_code=422,
        )

    pinned: Dict[int, Decimal] = {}
    while True:
        active = [i for i in range(n) if i not in pinned]
        if not active:
            break
        below = [i for i in active if values[i] < f]
        if not below:
            break
        for i in below:
            values[i] = f
            pinned[i] = f
        # 已钉住的行退出候选，剩余额度在未触顶行按**原权重**重分
        free = [i for i in active if i not in pinned]
        if not free:
            # 全部行都被钉在 floor 而仍有余额 → 守恒无法维持。
            # 上面的 n×f ≤ total 预检查已排除此分支，这里是防御性断言：
            # 静默返回会让「Σ摊得 ≠ 待摊」被当成成功。
            raise AllocationError(
                f'地板价钳制后仍无行可承接余额（Σfloor={n * f} < '
                f'total={_to_decimal(total).quantize(quant)}），无法守恒',
                status_code=422,
            )
        rest_total = _to_decimal(total).quantize(quant) - sum(pinned.values())
        for i, v in zip(free, plan(rest_total, [weights[i] for i in free],
                                    scale, rounding)):
            values[i] = v

    return values


class AllocationService:
    """把父行的量按权重分摊到 N 个子行 (或拆分成 N 个新行)。

    `amount` 列语义是「量」而非「钱」——金额场景填金额，工时/数量/重量
    场景填各自的量；算法层（`plan` / `plan_floor`）对两者完全一致。
    """

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

    # ------------------------------------------------------------------
    # v3: allocation_rule 驱动（FR-013 / P4.5）
    # ------------------------------------------------------------------

    def _load_rule(self, rule_id: Any) -> Dict[str, Any]:
        """按 id 取分摊规则行。

        【为什么不在服务层缓存】规则是**配置**，会被用户在界面上改；
        缓存会让「改完规则仍按旧规则分摊」，且失效时机无从判断。
        分摊是低频写操作，每次读一行可忽略。
        """
        row = self.ds.find_by_id('allocation_rules', rule_id)
        if not row:
            raise AllocationError(
                f'分摊规则 #{rule_id} 不存在', status_code=404
            )
        return row

    @staticmethod
    def _derive_weights(basis: str, rows: List[Dict[str, Any]],
                        basis_field: str = None,
                        manual_factor: Any = None) -> List[Any]:
        """按分摊基数从子行取权重（`allocate_by_rule` 用）。

        Args:
            basis: `allocation_rule.basis` 六枚举之一
            rows: 子行记录（`_resolve_child_rows` 返回，已按 id 升序）
            basis_field: basis ∈ {value,quantity,weight,volume} 时**必填**，
                         指明从子行哪一列取权重
            manual_factor: basis = manual 时用的**单值**系数

        【为什么 basis_field 由调用方给】引擎不知道业务表哪列是"重量"——
        同一张订单行表，重量可能是 `gross_weight` 也可能是 `net_weight`。
        内置映射表（value→amount / weight→weight）会把引擎焊死在某一套
        字段命名上，换个对象就得改代码。故把「读哪一列」交给配置者，
            引擎只负责「按这一列的占比分」。

        【manual_factor 只能均分】schema 声明它是**单值** number，
        所以 `basis=manual` + 单值系数 = 等权。这不是本层的简化——
        是配置的表达能力上限；真要逐行手工系数，调用方应直接用
        `allocate(weights=[...])`。此处显式按等权处理而非报错。
        """
        n = len(rows)
        if basis == BASIS_EQUAL:
            return [1] * n

        if basis == BASIS_MANUAL:
            if manual_factor is None:
                raise AllocationError('basis=manual 必须提供 manual_factor')
            f = _to_decimal(manual_factor)
            if f <= 0:
                raise AllocationError(
                    f'manual_factor 必须为正数, 收到: {f}'
                )
            return [f] * n

        if basis not in BASIS_FROM_FIELD:
            raise AllocationError(
                f'未知分摊基数: {basis!r}；可选 {sorted(BASES)}'
            )

        if not basis_field:
            raise AllocationError(
                f'basis={basis} 必须提供 basis_field（指明从子行哪一列取权重）'
            )
        _require_ident(basis_field, 'basis_field')

        weights = []
        for r in rows:
            v = r.get(basis_field)
            if v is None:
                raise AllocationError(
                    f'子行 #{r.get("id")} 的 {basis_field} 为空, '
                    f'无法按该基数分摊',
                    status_code=422,
                )
            try:
                d = _to_decimal(v)
            except AllocationError as e:
                raise AllocationError(
                    f'子行 #{r.get("id")} 的 {basis_field} 非法: {e}',
                    status_code=422,
                )
            if d <= 0:
                raise AllocationError(
                    f'子行 #{r.get("id")} 的 {basis_field} 必须为正数, '
                    f'收到: {d}（零/负权重会让该行分不到量）',
                    status_code=422,
                )
            weights.append(d)
        return weights

    def _resolve_child_rows(self, target_object: str, parent_id: Any,
                            fk_field: str) -> List[Dict[str, Any]]:
        """取父行下的子行**完整记录**（`_resolve_children` 只回 id）。"""
        from meta.core.models import registry
        meta_obj = registry.get(target_object)
        if not meta_obj:
            raise AllocationError(f'未知对象: {target_object}')
        return self.ds.find(
            meta_obj.table_name, {fk_field: parent_id}, order_by='id'
        )

    @staticmethod
    def _group_rows(rows: List[Dict[str, Any]], group_by: str,
                    basis_weights: List[Any]):
        """按 `group_by` 字段把子行聚成组（按组首次出现顺序，确定性）。

        Returns:
            [(group_key, [(行下标, weight), ...]), ...]

        【为什么携带下标而非 row 对象】同组行在 `rows` 里**不连续**
        （`[A(g1), B(g2), C(g1)]` → g1 含 A、C），故必须按下标回填，
        不能靠"顺序递推"。
        """
        groups: Dict[Any, List] = {}
        for idx, (row, w) in enumerate(zip(rows, basis_weights)):
            groups.setdefault(row.get(group_by), []).append((idx, w))
        return list(groups.items())

    def allocate_by_rule(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """按 `allocation_rule` 配置分摊父行的量到 N 个已有子行（FR-013）。

        spec:
            allocation_rule_id  必填  分摊规则 id（allocation_rules.id）
            parent_id           必填  父记录 id
            target_object       必填  子对象类型（兼容别名 child_object）
            target_field        必填  子行待写入字段
            basis_field         选填  basis ∈ {value,quantity,weight,volume}
                                 时的权重来源列；equal/manual 不需要
            group_by            选填  覆盖规则配置的分组维度
            floor               选填  覆盖规则配置的地板价
            rounding            选填  覆盖规则配置的取整方式
            weights             选填  显式权重，**优先于 basis**（调试/特例用）
            source_field        默认 = target_field
            fk_field            默认由 HierarchyConfigLoader 推导
            parent_object       默认由 HierarchyConfigLoader 推导
            scale               默认 2
            persist_result      默认 true；false = 只摊不落 allocation_results
            document_type       结果行的宿主对象；默认同上推导
            charge_source       费用来源单据类型（order/invoice/...）
            source_document_type/id  费用**来源**单据（可 ≠ 宿主单据）
            target              归集方向 cost/expense；默认 rule.target
            currency            默认 CNY

        Returns:
            {'parent_id','target_object','target_field',
             'total'（实际摊派总额，配置了 ceil/floor 时与 source_total 不同）,
             'source_total'（父行原值）,
             'allocation_rule_id','basis','basis_field','group_by',
             'allocations':[{'id','value','group'}],
             'result_ids': {'header_result_id','line_result_ids'} | None,
             'verified': True}

        【守恒恒等式】`plan_floor` 在任何 basis / group_by / floor / rounding
        组合下都保证 Σ子行 == 待摊总额；写入后再从 DB 回读校验一次
        （`_sum_children`），避免"算对了但没写进去"被当成成功。
        """
        rule_id = spec.get('allocation_rule_id')
        if rule_id is None:
            raise AllocationError('allocation_rule_id 必填')

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

        rule = self._load_rule(rule_id)
        explicit_weights = spec.get('weights')

        from meta.core.models import registry
        child_meta = registry.get(target_object)
        if not child_meta:
            raise AllocationError(f'未知对象: {target_object}')
        _require_ident(child_meta.table_name, 'table_name')

        fk_field = _require_ident(
            self.resolve_foreign_key(target_object, spec.get('fk_field')),
            'fk_field',
        )
        rows = self._resolve_child_rows(target_object, parent_id, fk_field)
        if not rows:
            raise AllocationError(
                f'{target_object} 下 fk={parent_id} 无子行, 无法分摊',
                status_code=422,
            )

        if explicit_weights is not None:
            basis_weights, weight_ids = self._normalize_weights(explicit_weights)
            if len(basis_weights) != len(rows):
                raise AllocationError(
                    f'weights 数 {len(basis_weights)} 与子行数 {len(rows)} '
                    f'不一致',
                    status_code=422,
                )
            if any(wid is not None for wid in weight_ids):
                by_id = dict(zip(weight_ids, basis_weights))
                row_ids = [r.get('id') for r in rows]
                if set(by_id) != set(row_ids):
                    raise AllocationError(
                        'weights 的 id 与父行下的子行不一致',
                        status_code=422,
                    )
                basis_weights = [by_id[rid] for rid in row_ids]
        else:
            basis_weights = self._derive_weights(
                rule.get('basis') or BASIS_EQUAL,
                rows,
                basis_field=spec.get('basis_field'),
                manual_factor=rule.get('manual_factor'),
            )

        _, total = self._resolve_parent_total(
            target_object, parent_id, source_field, spec.get('parent_object')
        )

        rounding = spec.get('rounding') or rule.get('rounding') or 'none'
        if rounding not in ROUNDING_MODES:
            raise AllocationError(
                f'rounding 非法: {rounding!r}；可选 {sorted(ROUNDING_MODES)}'
            )
        floor = spec.get('floor') if spec.get('floor') is not None \
            else rule.get('floor')
        group_by = spec.get('group_by') or rule.get('group_by')

        values, groups = self._plan_by_rule(
            total, rows, basis_weights, group_by=group_by,
            floor=floor, scale=scale, rounding=rounding,
        )

        # 写后守恒的**比对基准**：rounding=ceil/floor 时 plan 分配的是
        # 「取整后的总额」（10.4 → ceil → 11），拿原值 10.4 去比会误报
        # 「Σ子行=11 != 父行=10.4」。守恒的语义是「摊完的钱 == 该摊的钱」，
        # 而「该摊的钱」在配置了取整方向时就是取整后的值。
        allocated_total = sum(values)

        executor = self._build_executor()
        with self.ds.transaction():
            for row, value in zip(rows, values):
                result = executor.execute(
                    child_meta, 'crud_update',
                    {'id': row.get('id'), target_field: float(value)},
                )
                if not result.success:
                    raise AllocationError(
                        f'写入子行 #{row.get("id")} 失败: '
                        f'{result.error or result.message}',
                        status_code=422,
                    )

            read_back = self._sum_children(
                child_meta.table_name, fk_field, parent_id, target_field
            )
            if self._quantize(read_back, scale) != self._quantize(
                    allocated_total, scale):
                raise AllocationError(
                    f'守恒校验失败: Σ子行={read_back} != '
                    f'待摊总额={allocated_total}'
                )

            # 留痕与业务写入同事务：结果行写失败 → 业务行一并回滚，
            # 不会出现「行上摊了钱但没有结果行」的不可回放状态。
            result_ids = None
            if spec.get('persist_result', True):
                document_type = spec.get('document_type') or spec.get(
                    'parent_object'
                ) or self._resolve_parent_object(target_object)
                if not document_type:
                    raise AllocationError(
                        'persist_result=true 时必须给出 document_type'
                        '（结果行的宿主对象；默认由层级配置推导）',
                        status_code=422,
                    )
                result_ids = self.record_allocation_results(
                    document_type, parent_id, values, rows, allocated_total,
                    rule,
                    charge_source=spec.get('charge_source'),
                    source_document_type=spec.get('source_document_type'),
                    source_document_id=spec.get('source_document_id'),
                    target=spec.get('target'),
                    currency=spec.get('currency') or 'CNY',
                    # 【2026-10-07 拆表】快照当次配置——规则会被改，
                    # 只存 rule_id 答不出「当时按什么摊的」
                    parent_id=parent_id,
                    basis_field=spec.get('basis_field'),
                    group_by=group_by,
                    rounding=rounding,
                    floor=floor,
                )

        return {
            'parent_id': parent_id,
            'target_object': target_object,
            'target_field': target_field,
            'total': str(self._quantize(allocated_total, scale)),
            # source_total **不量化**：它的用途就是与 total 对账，说明
            # 「原本该摊多少 → 实际摊了多少」。若按 scale 量化，scale=0
            # 时 10.4 会变成 '10'，恰好把取整带来的差额抹平。
            'source_total': str(_to_decimal(total)),
            'allocation_rule_id': rule_id,
            'basis': rule.get('basis') or BASIS_EQUAL,
            'basis_field': spec.get('basis_field'),
            'group_by': group_by,
            'allocations': [
                {'id': r.get('id'), 'value': str(v), 'group': g}
                for r, v, g in zip(rows, values, groups)
            ],
            'result_ids': result_ids,
            'verified': True,
        }

    def _plan_by_rule(self, total: Any, rows: List[Dict[str, Any]],
                      basis_weights: List[Any], group_by: str = None,
                      floor: Any = None, scale: int = 2,
                      rounding: str = 'none'):
        """按 `group_by` 决定分组层级，再逐组分摊，返回 (values, group_keys)。

        【group_by 数学语义 · 用户拍板】**组间均分 + 组内按 basis**：
        先把总额等分成 G 份给 G 个组，组内再按 basis 权重分。
        另两种候选被否：①「两级都按 basis」因权重可加而恒等于不分组
        （死字段）；②「只做统计分组」同理。故组间**必须**均分才有区分度。

        【floor 在分组下的层级】floor 是**最终行值**的下限，故在组内
        分摊时施加；组间均分不做钳制（组总额是中间量，不是行值）。
        但组内钳制会破坏「组内守恒」→ 组总额与 Σ组内 不等。故这里的
        做法是：组间均分保证总额守恒，floor 冲突由**跨组 waterfall**
        统一处理（见 `_plan_waterfall_across`），不做组内局部钳制。
        """
        if not group_by:
            values = plan_floor(total, basis_weights, floor, scale, rounding)
            return values, [None] * len(rows)

        _require_ident(group_by, 'group_by')
        groups = self._group_rows(rows, group_by, basis_weights)
        group_totals = plan(total, [1] * len(groups), scale, rounding)

        values: List[Optional[Decimal]] = [None] * len(rows)
        group_keys: List[Any] = [None] * len(rows)
        for (key, members), gt in zip(groups, group_totals):
            idxs = [m[0] for m in members]
            member_w = [m[1] for m in members]
            # floor 不在组内施加（会破组内守恒），统一走下面的跨组 waterfall
            for i, v in zip(idxs, plan(gt, member_w, scale, rounding)):
                values[i] = v
                group_keys[i] = key

        if floor is not None and _to_decimal(floor) > 0:
            values = self._plan_waterfall_across(
                total, values, basis_weights, floor, scale, rounding
            )
        return values, group_keys

    @staticmethod
    def _plan_waterfall_across(total: Any, values: List[Optional[Decimal]],
                               weights: List[Any], floor: Any, scale: int,
                               rounding: str):
        """分组场景下的 floor 钳制：全行一起 waterfall，跨组重分余额。

        【为什么不在组内局部钳制】组内钳到 floor 会让「Σ组内 > 组总额」，
        组总额是 `plan` 按守恒分好的，破坏它就等于破坏总额守恒。故 floor
        只能在**全部行**这一层统一施加，钳制出的缺口由未触顶行（含其他组）
        按原权重重分——守恒恒等式与 `plan_floor` 相同。
        """
        quant = Decimal(10) ** -scale
        f = _to_decimal(floor).quantize(quant)
        total_q = _to_decimal(total).quantize(quant)
        if f <= 0 or total_q <= 0:
            return values
        if len(values) * f > total_q:
            raise AllocationError(
                f'地板价无法满足: {len(values)} 行 × {f} = '
                f'{len(values) * f} > 待摊总额 {total_q}',
                status_code=422,
            )

        out = list(values)
        pinned: Dict[int, Decimal] = {}
        while True:
            active = [i for i in range(len(out)) if i not in pinned]
            below = [i for i in active if out[i] < f]
            if not below:
                break
            for i in below:
                out[i] = f
                pinned[i] = f
            free = [i for i in range(len(out)) if i not in pinned]
            if not free:
                break
            rest_total = total_q - sum(pinned.values())
            for i, v in zip(free, plan(rest_total, [weights[i] for i in free],
                                       scale, rounding)):
                out[i] = v
        return out

    # ------------------------------------------------------------------
    # v3: 分摊结果留痕（FR-013 AC「分摊可回放」）
    # ------------------------------------------------------------------

    def record_allocation_results(
        self, document_type: str, document_id: Any, values: List[Decimal],
        rows: List[Dict[str, Any]], total: Any, rule: Dict[str, Any],
        charge_source: str = None, source_document_type: str = None,
        source_document_id: Any = None, target: str = None,
        currency: str = 'CNY',
        parent_id: Any = None, basis_field: str = None,
        group_by: str = None, rounding: str = None, floor: Any = None,
    ) -> Dict[str, Any]:
        """把分摊结果落 `allocation_results`：**头记总额 + 行记摊得额**。

        FR-013 AC「分摊可回放：头记总额、行记摊得额，来源单据与分摊规则可查」。
        落结果表而非只在业务行上写数字——业务行会被下一次分摊覆盖，
        只有结果行能回答「这笔钱当初按什么规则摊的、摊给了谁、来源是哪张单」。

        【2026-10-07 拆表 · TBD-18】原写 `calc_results`（定价结果表），导致
        定价重算会作废本留痕、`write_back` 又把金额写回两遍（实测缺陷，
        非推测）。现改为写 `allocation_results` 专用表，与定价**物理隔离**。

        【列集取舍】**不写任何价格列**（rate / base / price_mode /
        rate_source / result_semantic）。原实现硬塞 `price_mode='carry'`
        （意为"无价格"）、`base=待摊总额`（把金额当计算基数）——非金额分摊
        （工时 / 数量 / 重量）下这些不是空值而是**错值**。新表每列对分摊
        语义成立，故 amount 列命名也不带 currency。

        【快照语义】规则会改，故把当次的 basis / basis_field / group_by /
        rounding / floor 全部快照进留痕——事后才能复现「当时按什么摊的」；
        只存 allocation_rule_id 只能答"按哪条规则"，答不出"那条规则当时
        长什么样"。

        Args:
            document_type/id: **宿主**单据（被摊到的那些行所属的单据）
            values / rows: 与 `allocate_by_rule` 的返回一一对应
            total: 待摊总额（头记行的 amount）
            rule: `allocation_rules` 行（回填 allocation_rule_id / basis）
            parent_id: 被分摊的父记录 id（留痕锚点，区别于宿主行）
            basis_field / group_by / rounding / floor: 当次配置快照
            currency: 仅金额场景有意义；非金额分摊传 None 即可

        【sign 由总额方向推导，不接受外部传入】`plan()` 允许负总额
        （红字 / 冲销），此时各行摊得额同为负。若由调用方传 sign，负金额
        配上 `'+'` 就会让留痕的「分摊方向」与实际摊销方向相反——故此处
        从 `total` 推导，保证 `sign` 与 `amount` 符号恒一致。

        Returns:
            {'header_result_id': int, 'line_result_ids': [int, ...]}
        """
        now = datetime.now().isoformat(timespec='seconds')
        basis = rule.get('basis') or BASIS_EQUAL
        target = target or rule.get('target') or 'expense'
        floor_val = _to_decimal(floor) if floor is not None else None
        sign = '-' if _to_decimal(total) < 0 else '+'

        header_code = f"AR_{uuid.uuid4().hex[:16]}"
        cur = self.ds.execute(
            """INSERT INTO allocation_results
               (code, document_type, document_id, document_line_id, parent_id,
                level, sequence, amount, net_amount, currency, sign,
                allocation_rule_id, allocation_basis, allocation_basis_field,
                group_by, rounding, floor_value, origin, charge_source,
                source_document_type, source_document_id, target, status,
                created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                header_code, document_type, document_id, None, parent_id,
                'header', 0, float(total), float(total), currency, sign,
                rule.get('id'), basis, basis_field,
                group_by, rounding,
                None if floor_val is None else float(floor_val), 'unplanned',
                charge_source, source_document_type, source_document_id,
                target, 'active', now, now,
            ],
        )
        header_id = cur.lastrowid

        line_ids = []
        for seq, (row, value) in enumerate(zip(rows, values), start=1):
            line_code = f"AR_{uuid.uuid4().hex[:16]}"
            c = self.ds.execute(
                """INSERT INTO allocation_results
                   (code, document_type, document_id, document_line_id,
                    parent_id, level, sequence, amount, net_amount, currency,
                    sign, allocation_rule_id, allocation_basis,
                    allocation_basis_field, group_by, rounding, floor_value,
                    origin, charge_source, source_document_type,
                    source_document_id, target, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [
                    line_code, document_type, document_id,
                    row.get('id'), parent_id, 'line', seq,
                    float(value), float(value), currency, sign,
                    rule.get('id'), basis, basis_field,
                    group_by, rounding,
                    None if floor_val is None else float(floor_val), 'unplanned',
                    charge_source, source_document_type, source_document_id,
                    target, 'active', now, now,
                ],
            )
            line_ids.append(c.lastrowid)

        return {'header_result_id': header_id, 'line_result_ids': line_ids}

    def query_results(self, document_type: str, document_id: Any,
                      document_line_id: Any = None,
                      status: str = 'active') -> List[Dict[str, Any]]:
        """回放某宿主的 `allocation_results`（FR-013 AC「分摊可回放」）。

        【为什么查询归本服务而非 PricingService】拆表后两张表分属两条链路；
        让 `PricingService.explain` 去读 `allocation_results` 只是把共表时的
        跨域耦合搬到服务层——表边界建了，查询边界也得跟着建。故留痕的
        读与写都由本服务自己的表负责。

        Args:
            document_type/id: 宿主单据（与写入时口径一致）
            document_line_id: 选填；给定则只回该行级留痕（头级仍按宿主匹配）
            status: 默认只回 `active`；传 None 则含已作废行（审计用）

        Returns:
            留痕行列表（头 + N 行），按 sequence / id 升序；amount 系列已归一为数值。
        """
        sql = ("SELECT * FROM allocation_results"
               " WHERE document_type = ? AND document_id = ?")
        params: List[Any] = [document_type, document_id]
        if document_line_id is not None:
            sql += " AND document_line_id = ?"
            params.append(document_line_id)
        if status is not None:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY sequence ASC, id ASC"

        cur = self.ds.execute(sql, params)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        out = [dict(zip(cols, r)) for r in rows]
        # sqlite 的 REAL 在部分驱动下读回 str（DECIMAL 亲和性），
        # 回放接口须归一为数值，否则前端拿到 "100.0" 做不了算术。
        for r in out:
            for k in ('amount', 'net_amount', 'floor_value'):
                v = r.get(k)
                if v is not None:
                    try:
                        r[k] = float(v)
                    except (TypeError, ValueError):
                        r[k] = None
        return out

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
