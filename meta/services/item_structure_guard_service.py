# -*- coding: utf-8 -*-
"""物料结构守卫 —— 结构头 / 结构行 / 物料角色的写入不变量。

依据: meta/schemas/item_structure.yaml 头注释「生效版本唯一性」
      meta/schemas/item_structure_line.yaml 头注释「行级不变量 R1–R10」
      docs/superpowers/specs/2026-10-25-configuration-and-structure-spec.md §4.6

落点划分:
  R1  component_item_id 不等于所属结构的 item_id，且多层展开不成环
      —— `validate_line_write`（直连比较 + 全图可达性遍历）
  R2  (structure_id, line_no) 唯一 —— 唯一索引 `uidx_item_structure_line_no`，不重复
  R3  qty_per 与 fixed_qty 恰填一个 —— `validate_line_write`
  R4  optional_flag = false 的行忽略 min_qty / max_qty / default_qty
      —— 校验时跳过 R5（与 R4 的「忽略」语义一致）
  R5  min_qty <= max_qty，default_qty 落在区间内 —— `validate_line_write`（仅可选行）
  R6  default_flag = true 必须 optional_flag = true —— `validate_line_write`
  R7  组件角色合法组合矩阵 —— `validate_line_write`（角色取自 items.structure_role）。
      父项 none 只装标准件；model / option_class 可装标准件、选项类、子模型
  R8  同一 substitute_group_code 同组最多一行 optional_flag = false —— `validate_line_write`
  R9  组件停用不阻断保存，展开时进入告警集 —— 写时不做校验
  R10 included_in_base_price / bom_price 仅报价参考 —— 写时不做校验
  R11 服务类组件只在 usage = sales 的商务结构中允许；生产 / 工程 / 成本用途仍拒
      —— `validate_line_write`
  R12 结构父项必须是实物物料（item_type = goods），服务不得作为结构根
      —— `validate_structure_write`
  R16 sales 用途的服务行只承载「次数」：禁损耗率（须 0）、替代组、虚拟件、
      工序号、单位用量 —— `validate_line_write`
  R17 结构基准单位必须能与父项物料的基本单位换算（同单位 / 同组 / 物料级例外）
      —— `validate_structure_write`（`UomQuantityService.is_compatible`）
  R18 组件物料必须维护基本单位 —— `validate_line_write`
      （展开时子行单位取组件基本单位，不静默回退父行单位）

  S1  同一 (item_id, usage, alternative_no) 在任一日期上只能有一个 status = active 的版本
      —— `validate_structure_write`（item_structure.yaml 头注释「生效版本唯一性」）
  S2  生效止不得早于生效起 —— `validate_structure_write`
  S3  min_select / max_select 只对选项类结构有效，且区间自洽
      —— `validate_structure_write`（P2 启用；非选项类结构填值即拒）
  M1  结构角色必须与物料类型一致：服务类物料不得带结构角色 —— `validate_item_write`
  D1  仍有结构行、配置规则、或处于生效中的结构版本禁止物理删除，引导改为 inactive
      —— `validate_structure_delete`
  R15 被配置规则条件项引用的结构行禁止物理删除 —— `validate_line_delete`

  A1  只有 structure_role = model 的结构可以声明模型特征 —— `validate_attribute_write`
  A2  特征编码必须命中平台层（tenant_id = 0）且已启用的可配置属性
      —— `validate_attribute_write`
  A3  特征数据类型限 string / number / integer / boolean —— `validate_attribute_write`
  A4  默认值按数据类型解析，并落在值域内（list / range）—— `validate_attribute_write`

查询失败一律 fail-open + WARNING（沿用 payment_term_guard / currency_rate_guard 口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与其他守卫同一限制）。成环判定覆盖全部结构版本
（不区分 usage / status），跨版本的历史环会一并算入。
"""

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from meta.services.uom_quantity_service import UomQuantityService

logger = logging.getLogger(__name__)

_STRUCTURE_TABLE = 'item_structures'
_LINE_TABLE = 'item_structure_lines'
_ATTRIBUTE_TABLE = 'attribute_definitions'
_ENUM_VALUE_TABLE = 'enum_values'
_CONFIG_RULE_TABLE = 'config_rules'
_CONFIG_RULE_TERM_TABLE = 'config_rule_terms'

# A3 可配置特征支持的数据类型（日期不参与选配，与属性字典 lint 同源）
_CONFIGURABLE_TYPES = ('string', 'number', 'integer', 'boolean')

_BOOLEAN_TEXTS = {'true', 'false', '1', '0', 'yes', 'no', 'y', 'n'}

_RANGE_PATTERN = re.compile(
    r'^\s*([\[\(])\s*([^,]+?)\s*,\s*([^\]\)]+?)\s*([\]\)])\s*$')

# 属性定义查询失败的哨兵（区别于「查无此行」的 None）
_QUERY_FAILED = object()

# R7 组件角色合法组合矩阵（Spec §4.6）：父项角色 → 允许的组件角色
#   none（标准件）       → 只装标准件
#   model（模型）        → 标准件 / 选项类 / 子模型
#   option_class（选项类）→ 标准件 / 选项类 / 子模型
_ROLE_MATRIX = {
    'none': {'none'},
    'model': {'none', 'option_class', 'model'},
    'option_class': {'none', 'option_class', 'model'},
}

_FAR_FUTURE = '9999-12-31'


class ItemStructureGuardError(ValueError):
    """物料结构守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

    def __init__(self, message: str, field_name: str = '', rule: str = ''):
        super().__init__(message)
        self.field_name = field_name
        self.rule = rule


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


def _to_decimal(value: Any) -> Decimal:
    if _is_blank(value):
        return Decimal('0')
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        logger.warning('[item_structure_guard] 数值无法解析，按 0 计: %r', value)
        return Decimal('0')


def _to_date_text(value: Any) -> str:
    """把 DATETIME / date / str 截断为 yyyy-mm-dd 文本（与 YAML 的 date 语义一致）。"""
    if value is None:
        return ''
    text = str(value).strip()
    return text[:10]


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y')
    return bool(value)


def _parse_decimal(value: Any) -> Optional[Decimal]:
    """解析数值文本；无法解析返回 None（与 `_to_decimal` 的容错口径区分）。"""
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


def _parse_range(value: Any) -> Optional[Tuple[Decimal, Decimal, bool, bool]]:
    """解析值域区间表达式，如 "[0, 99999]" / "(0, 100]"。

    返回 (下界, 上界, 下界含, 上界含)；表达式无法解析返回 None。
    """
    if value is None:
        return None
    match = _RANGE_PATTERN.match(str(value))
    if not match:
        return None
    low = _parse_decimal(match.group(2))
    high = _parse_decimal(match.group(3))
    if low is None or high is None:
        return None
    return low, high, match.group(1) == '[', match.group(4) == ']'


class ItemStructureGuardService:
    """物料结构头 / 行 / 物料角色的写入前校验。

    查询方法均可覆写，便于单测注入数据（不依赖真实库）。
    """

    def __init__(self, data_source):
        self.ds = data_source
        self._uom = UomQuantityService(data_source)

    # ---------- 公开入口 ----------

    def validate_item_write(self, data: Dict[str, Any]) -> None:
        """M1：服务类物料不得带结构角色（结构角色只有 goods 才能承载）。"""
        role = data.get('structure_role')
        if _is_blank(role) or str(role) == 'none':
            return
        if str(data.get('item_type') or '') != 'service':
            return
        raise ItemStructureGuardError(
            '服务类物料不能承担结构角色；请把「结构角色」置为「无」',
            field_name='structure_role',
            rule='item_structure_role_requires_goods')

    def validate_structure_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """结构头创建 / 更新前校验 R12 / S2 / S3 / S1。"""
        parent_item_id = data.get('item_id')
        if not _is_blank(parent_item_id) and self._fetch_item_type(parent_item_id) == 'service':
            raise ItemStructureGuardError(
                '服务物料不能作为结构根；请把结构挂在实物物料上'
                '（纯服务组合请用商务包方式建模）',
                field_name='item_id',
                rule='item_structure_parent_requires_goods')
        self._validate_validity_window(data)
        self._validate_select_bounds(data)
        self._validate_base_uom(data)

        if data.get('status') != 'active':
            return

        item_id = data.get('item_id')
        usage = data.get('usage')
        alternative_no = data.get('alternative_no')
        if _is_blank(item_id) or _is_blank(usage) or _is_blank(alternative_no):
            return  # 缺业务键交给必填校验兜底

        new_from = _to_date_text(data.get('valid_from'))
        if not new_from:
            return  # 缺生效起交给必填校验兜底
        new_to = _to_date_text(data.get('valid_to')) or _FAR_FUTURE

        for row in self._fetch_active_versions(item_id, usage, alternative_no, exclude_id):
            other_from = _to_date_text(row.get('valid_from'))
            other_to = _to_date_text(row.get('valid_to')) or _FAR_FUTURE
            if not other_from:
                continue
            if new_from <= other_to and other_from <= new_to:
                raise ItemStructureGuardError(
                    f'同一物料的 {usage} 结构在 {other_from} ~ {other_to} 已有生效版本，'
                    '生效区间重叠；请先停用旧版本或填写 valid_to',
                    field_name='status',
                    rule='item_structure_version_overlap')

    def validate_structure_delete(self, structure_id: Any) -> None:
        """D1：仍有结构行 / 配置规则、或处于生效中的结构版本禁止物理删除。"""
        if _is_blank(structure_id):
            return
        line_count = self._count_lines(structure_id)
        if line_count > 0:
            raise ItemStructureGuardError(
                f'该结构版本还有 {line_count} 行结构行，请先删除结构行',
                field_name='id',
                rule='item_structure_in_use')
        rule_count = self._count_config_rules(structure_id)
        if rule_count > 0:
            raise ItemStructureGuardError(
                f'该结构版本还有 {rule_count} 条配置规则，请先删除规则',
                field_name='id',
                rule='item_structure_in_use')
        state = self._fetch_structure_state(structure_id)
        if not state:
            return
        if str(state.get('status') or '') == 'active':
            raise ItemStructureGuardError(
                '生效中的结构版本不能删除；请先置为「停用」',
                field_name='status',
                rule='item_structure_in_use')

    def validate_line_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """结构行创建 / 更新前校验 R1 / R3 / R5–R8 / R11。

        `exclude_id`：更新场景传入当前行 id，避免把自己重复计入。
        """
        structure_id = data.get('structure_id')
        component_item_id = data.get('component_item_id')
        if _is_blank(structure_id) or _is_blank(component_item_id):
            return  # 缺必填交给必填校验兜底

        # R3：qty_per 与 fixed_qty 恰填一个
        has_qty_per = not _is_blank(data.get('qty_per'))
        has_fixed_qty = not _is_blank(data.get('fixed_qty'))
        if has_qty_per == has_fixed_qty:
            raise ItemStructureGuardError(
                '单位用量与固定用量必须填写且只填写一个',
                field_name='fixed_qty' if has_qty_per else 'qty_per',
                rule='item_structure_line_qty_exclusive')

        # R6：默认选中只能出现在可选行
        optional_flag = bool(data.get('optional_flag'))
        if bool(data.get('default_flag')) and not optional_flag:
            raise ItemStructureGuardError(
                '必选件不能设为默认选中；请先勾选「可选」',
                field_name='default_flag',
                rule='item_structure_line_default_requires_optional')

        # R4 / R5：数量口径只对可选行生效
        if optional_flag:
            self._validate_optional_qty(data)

        # R8：同替代组最多一行必选锚点（判定对象是必选行）
        self._validate_substitute_anchor(data, exclude_id)

        # R1 / R7 / R11：需要结构头与物料角色
        structure = self._fetch_structure(structure_id)
        if not structure:
            return
        parent_item_id = structure.get('item_id')
        if _is_blank(parent_item_id):
            return
        if str(component_item_id) == str(parent_item_id):
            raise ItemStructureGuardError(
                '组件物料不能是结构自身的父项物料',
                field_name='component_item_id',
                rule='item_structure_self_reference')
        if self._creates_cycle(component_item_id, parent_item_id, exclude_id):
            raise ItemStructureGuardError(
                '该组件会把结构引成环：从组件物料沿现有结构可回到父项物料',
                field_name='component_item_id',
                rule='item_structure_cycle')
        if self._fetch_item_type(component_item_id) == 'service':
            if str(structure.get('usage') or '') != 'sales':
                raise ItemStructureGuardError(
                    '服务类物料只能出现在「销售」用途的结构中；'
                    '生产 / 工程 / 成本结构请选择物料类型为「物料」的组件',
                    field_name='component_item_id',
                    rule='item_structure_component_service_item')
            self._validate_service_line(data)
        self._validate_role_matrix(parent_item_id, component_item_id)
        self._validate_component_uom(component_item_id)

    def _validate_service_line(self, data: Dict[str, Any]) -> None:
        """R16：sales 用途的服务行只承载「次数」，不承载实物语义。"""
        if _to_decimal(data.get('scrap_rate')) != 0:
            raise ItemStructureGuardError(
                '服务组件的损耗率必须为 0',
                field_name='scrap_rate',
                rule='item_structure_service_line_scrap_rate')
        if not _is_blank(data.get('substitute_group_code')):
            raise ItemStructureGuardError(
                '服务组件不能加入替代料组',
                field_name='substitute_group_code',
                rule='item_structure_service_line_substitute')
        if _to_bool(data.get('phantom_flag')):
            raise ItemStructureGuardError(
                '服务组件不能标记为虚拟件',
                field_name='phantom_flag',
                rule='item_structure_service_line_phantom')
        if not _is_blank(data.get('operation_seq')):
            raise ItemStructureGuardError(
                '服务组件不占用工序号',
                field_name='operation_seq',
                rule='item_structure_service_line_operation_seq')
        if not _is_blank(data.get('qty_per')):
            raise ItemStructureGuardError(
                '服务组件只接受「固定用量」（次数），不支持单位用量',
                field_name='qty_per',
                rule='item_structure_service_line_qty_per')

    def validate_line_delete(self, line_id: Any) -> None:
        """R15：被配置规则条件项引用的结构行禁止物理删除。"""
        if _is_blank(line_id):
            return
        ref_count = self._count_line_rule_refs(line_id)
        if ref_count > 0:
            raise ItemStructureGuardError(
                f'该结构行被 {ref_count} 条配置规则条件项引用，请先删除规则条件项',
                field_name='id',
                rule='item_structure_line_in_use')

    def validate_attribute_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """模型特征声明创建 / 更新前校验 A1–A4。

        `exclude_id` 为更新场景的当前行 id（特征编码唯一性由索引兜底，此处不用）。
        """
        structure_id = data.get('structure_id')
        attribute_code = str(data.get('attribute_code') or '').strip()
        if _is_blank(structure_id) or not attribute_code:
            return  # 缺必填交给必填校验兜底

        # A1：只有模型可以声明特征
        structure = self._fetch_structure(structure_id)
        if structure and not _is_blank(structure.get('item_id')):
            role = self._fetch_item_role(structure.get('item_id'))
            if role and role != 'model':
                raise ItemStructureGuardError(
                    f'只有模型（结构角色 = 模型）可以声明特征；'
                    f'该结构的父项角色是「{role}」，选项类请用行的可选性表达',
                    field_name='structure_id',
                    rule='item_structure_attribute_requires_model')

        # A2：编码必须命中平台层已启用的可配置属性
        definition = self._fetch_attribute_definition(attribute_code)
        if definition is _QUERY_FAILED:
            return  # 查询失败 → fail-open
        if definition is None:
            raise ItemStructureGuardError(
                f"特征编码 '{attribute_code}' 不在平台层属性字典中；"
                '请先建立属性定义并配置物料适用范围',
                field_name='attribute_code',
                rule='item_structure_attribute_code_not_found')
        if not _to_bool(definition.get('is_configurable')):
            raise ItemStructureGuardError(
                f"属性 '{attribute_code}' 未标记为可配置特征；"
                '结构版本只能声明 is_configurable = true 的属性',
                field_name='attribute_code',
                rule='item_structure_attribute_not_configurable')
        if str(definition.get('status') or '') != 'active':
            raise ItemStructureGuardError(
                f"属性 '{attribute_code}' 未启用；请先启用属性定义再声明到模型上",
                field_name='attribute_code',
                rule='item_structure_attribute_not_configurable')

        # A3：类型必须在可配置范围内
        data_type = str(definition.get('data_type') or '')
        if data_type not in _CONFIGURABLE_TYPES:
            raise ItemStructureGuardError(
                f"属性 '{attribute_code}' 的数据类型 '{data_type}' 不参与选配；"
                f"只允许 {'/'.join(_CONFIGURABLE_TYPES)}",
                field_name='attribute_code',
                rule='item_structure_attribute_type_unsupported')

        # A4：默认值按类型解析并落在值域内
        default_value = data.get('default_value_text')
        if not _is_blank(default_value):
            self._validate_attribute_default(attribute_code, definition, default_value)

    # ---------- 规则实现 ----------

    def _validate_validity_window(self, data: Dict[str, Any]) -> None:
        """S2：生效止不得早于生效起（空 = 长期有效）。"""
        start = _to_date_text(data.get('valid_from'))
        end = _to_date_text(data.get('valid_to'))
        if start and end and end < start:
            raise ItemStructureGuardError(
                f'生效止 {end} 早于生效起 {start}；留空表示长期有效',
                field_name='valid_to',
                rule='item_structure_validity_inverted')

    def _validate_select_bounds(self, data: Dict[str, Any]) -> None:
        """S3：选择数只对选项类结构有效，且 min <= max。"""
        min_select = data.get('min_select')
        max_select = data.get('max_select')
        if _is_blank(min_select) and _is_blank(max_select):
            return

        item_id = data.get('item_id')
        if not _is_blank(item_id):
            role = self._fetch_item_role(item_id)
            if role and role != 'option_class':
                field = 'min_select' if not _is_blank(min_select) else 'max_select'
                raise ItemStructureGuardError(
                    '最少 / 最多选择数只对选项类结构有效；'
                    '标准件与模型请留空，用行的可选性表达',
                    field_name=field,
                    rule='item_structure_select_requires_option_class')

        if not _is_blank(min_select) and not _is_blank(max_select):
            if _to_decimal(min_select) > _to_decimal(max_select):
                raise ItemStructureGuardError(
                    f'最少选择数 {min_select} 不能大于最多选择数 {max_select}',
                    field_name='max_select',
                    rule='item_structure_select_range')

        # 最多选择数不得超过现有结构行数（尚未建行时放行，交给建行阶段）
        structure_id = data.get('id')
        if not _is_blank(structure_id) and not _is_blank(max_select):
            line_count = self._count_lines(structure_id)
            if line_count and _to_decimal(max_select) > line_count:
                raise ItemStructureGuardError(
                    f'最多选择数 {max_select} 超过现有结构行数 {line_count}',
                    field_name='max_select',
                    rule='item_structure_select_exceeds_children')

    def _validate_base_uom(self, data: Dict[str, Any]) -> None:
        """R17：结构基准单位必须能与父项物料的基本单位换算。

        结构基准数量（`base_qty` + `base_uom_id`）是组件用量的分母，展开时
        订单数量先要折成基准单位；两侧不可换算会让数量整体错标。允许同单位、
        同组组内换算、以及物料级例外（跨组换算）。数据不足（物料缺失 /
        查询失败 / 换算链未维护）一律 fail-open，不阻断维护。
        """
        base_uom_id = data.get('base_uom_id')
        item_id = data.get('item_id')
        if _is_blank(base_uom_id) or _is_blank(item_id):
            return  # 缺必填交给必填校验兜底
        item_uom = self._fetch_item_base_uom(item_id)
        if item_uom is _QUERY_FAILED or _is_blank(item_uom):
            return  # 查询失败 / 物料缺基本单位 → 物料侧兜底
        if self._uom.is_compatible(item_id, base_uom_id, item_uom) is False:
            raise ItemStructureGuardError(
                '结构基准单位与父项物料的基本单位不可换算；'
                '请选择同一计量单位组内的单位，或先为该物料维护单位换算',
                field_name='base_uom_id',
                rule='item_structure_base_uom_incompatible')

    def _validate_component_uom(self, component_item_id: Any) -> None:
        """R18：组件物料必须维护基本单位（展开时子行单位取它）。"""
        item_uom = self._fetch_item_base_uom(component_item_id)
        if item_uom is _QUERY_FAILED or item_uom is None:
            return  # 查询失败 / 物料不存在 → fail-open
        if _is_blank(item_uom):
            raise ItemStructureGuardError(
                '组件物料未维护基本单位；结构行用量以组件基本单位计量，'
                '请先在物料主数据上补齐「基本单位」',
                field_name='component_item_id',
                rule='item_structure_component_uom_missing')

    def _validate_optional_qty(self, data: Dict[str, Any]) -> None:
        """R5：min_qty <= max_qty，default_qty 落在区间内。"""
        min_qty = data.get('min_qty')
        max_qty = data.get('max_qty')
        default_qty = data.get('default_qty')

        if not _is_blank(min_qty) and not _is_blank(max_qty):
            if _to_decimal(min_qty) > _to_decimal(max_qty):
                raise ItemStructureGuardError(
                    f'最少数量 {min_qty} 不能大于最多数量 {max_qty}',
                    field_name='max_qty',
                    rule='item_structure_line_qty_range')

        if not _is_blank(default_qty):
            if not _is_blank(min_qty) and _to_decimal(default_qty) < _to_decimal(min_qty):
                raise ItemStructureGuardError(
                    f'默认数量 {default_qty} 不能小于最少数量 {min_qty}',
                    field_name='default_qty',
                    rule='item_structure_line_qty_range')
            if not _is_blank(max_qty) and _to_decimal(default_qty) > _to_decimal(max_qty):
                raise ItemStructureGuardError(
                    f'默认数量 {default_qty} 不能大于最多数量 {max_qty}',
                    field_name='default_qty',
                    rule='item_structure_line_qty_range')

    def _validate_substitute_anchor(self, data: Dict[str, Any], exclude_id: Any) -> None:
        """R8：同一结构的同一替代组，最多一行 optional_flag = false。"""
        group_code = data.get('substitute_group_code')
        if _is_blank(group_code) or bool(data.get('optional_flag')):
            return
        structure_id = data.get('structure_id')
        others = self._count_substitute_anchors(structure_id, str(group_code), exclude_id)
        if others > 0:
            raise ItemStructureGuardError(
                f'替代组 {group_code} 已有一行必选锚点，同组最多一行必选',
                field_name='substitute_group_code',
                rule='item_structure_substitute_anchor_duplicate')

    def _validate_role_matrix(self, parent_item_id: Any, component_item_id: Any) -> None:
        """R7：父项角色 → 组件角色必须落在合法组合矩阵内。"""
        parent_role = self._fetch_item_role(parent_item_id)
        component_role = self._fetch_item_role(component_item_id)
        if not parent_role or not component_role:
            return  # 角色未知（物料不存在或字段缺失）时 fail-open
        allowed = _ROLE_MATRIX.get(parent_role)
        if allowed is None or component_role not in allowed:
            raise ItemStructureGuardError(
                f'父项角色「{parent_role}」不允许挂「{component_role}」组件；'
                '标准结构只能装标准件',
                field_name='component_item_id',
                rule='item_structure_role_combination_invalid')

    def _validate_attribute_default(self, code: str, definition: Dict[str, Any],
                                    value: Any) -> None:
        """A4：默认值按 data_type 解析，并落在值域内（list / range）。"""
        text = str(value).strip()
        data_type = str(definition.get('data_type') or '')

        if data_type == 'boolean':
            if text.lower() not in _BOOLEAN_TEXTS:
                self._raise_default_invalid(code, text, '布尔值只接受 true / false')
            return

        if data_type in ('number', 'integer'):
            number = _parse_decimal(text)
            if number is None:
                self._raise_default_invalid(code, text, f'{data_type} 类型需要一个数值')
            if data_type == 'integer' and number != number.to_integral_value():
                self._raise_default_invalid(code, text, 'integer 类型不接受小数')
            self._validate_domain_range(code, definition, number)
            return

        self._validate_domain_list(code, definition, text)

    def _validate_domain_list(self, code: str, definition: Dict[str, Any], text: str) -> None:
        if str(definition.get('value_domain_type') or '') != 'list':
            return
        enum_code = str(definition.get('value_domain_ref') or '').strip()
        if not enum_code:
            return
        if not self._enum_value_exists(enum_code, text):
            self._raise_default_invalid(
                code, text, f"不在枚举清单 '{enum_code}' 中")

    def _validate_domain_range(self, code: str, definition: Dict[str, Any],
                               number: Decimal) -> None:
        if str(definition.get('value_domain_type') or '') != 'range':
            return
        bounds = _parse_range(definition.get('value_domain_ref'))
        if bounds is None:
            return  # 区间表达式无法解析 → fail-open，不阻断维护
        low, high, low_inclusive, high_inclusive = bounds
        too_low = number < low if low_inclusive else number <= low
        too_high = number > high if high_inclusive else number >= high
        if too_low or too_high:
            self._raise_default_invalid(
                code, str(number),
                f"超出值域 {definition.get('value_domain_ref')}")

    @staticmethod
    def _raise_default_invalid(code: str, text: str, reason: str) -> None:
        raise ItemStructureGuardError(
            f"特征 '{code}' 的默认值 '{text}' 无效：{reason}",
            field_name='default_value_text',
            rule='item_structure_attribute_default_invalid')

    # ---------- 查询（可覆写，便于单测注入）----------

    def _fetch_structure(self, structure_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f"SELECT item_id, usage FROM {_STRUCTURE_TABLE} WHERE id = ?", [structure_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 读取结构头失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_structure_state(self, structure_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f"SELECT id, status FROM {_STRUCTURE_TABLE} WHERE id = ?", [structure_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 读取结构状态失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_item_role(self, item_id: Any) -> str:
        try:
            rows = self.ds.query(
                "SELECT structure_role FROM items WHERE id = ?", [item_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 读取物料角色失败: {e}')
            return ''
        if not rows:
            return ''
        return str(rows[0].get('structure_role') or '')

    def _fetch_item_type(self, item_id: Any) -> str:
        try:
            rows = self.ds.query(
                "SELECT item_type FROM items WHERE id = ?", [item_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 读取物料类型失败: {e}')
            return ''
        if not rows:
            return ''
        return str(rows[0].get('item_type') or '')

    def _fetch_item_base_uom(self, item_id: Any):
        """读取物料基本单位（`uoms.id`）。

        查询失败 → `_QUERY_FAILED`；无此物料行 → `None`；
        物料存在但未维护基本单位 → 空串（供 R18 与「物料缺失」区分）。
        """
        try:
            rows = self.ds.query(
                "SELECT base_uom FROM items WHERE id = ?", [item_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 读取物料基本单位失败: {e}')
            return _QUERY_FAILED
        if not rows:
            return None
        value = rows[0].get('base_uom')
        return '' if value is None else value

    def _fetch_attribute_definition(self, code: str):
        """A2：平台层（tenant_id = 0）属性定义；查询失败返回 `_QUERY_FAILED`。"""
        try:
            rows = self.ds.query(
                f"SELECT code, data_type, is_configurable, status, "
                f"value_domain_type, value_domain_ref FROM {_ATTRIBUTE_TABLE} "
                "WHERE tenant_id = 0 AND code = ? LIMIT 1", [code])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 读取属性定义失败: {e}')
            return _QUERY_FAILED
        return rows[0] if rows else None

    def _enum_value_exists(self, enum_type_code: str, value: str) -> bool:
        sql = (f"SELECT id FROM {_ENUM_VALUE_TABLE} "
               "WHERE enum_type_id = ? AND code = ? AND is_active = 1 LIMIT 1")
        try:
            return bool(self.ds.query(sql, [enum_type_code, value]))
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 查询枚举值失败: {e}')
            return True

    def _count_lines(self, structure_id: Any) -> int:
        try:
            rows = self.ds.query(
                f"SELECT COUNT(*) AS cnt FROM {_LINE_TABLE} WHERE structure_id = ?",
                [structure_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 统计结构行失败: {e}')
            return 0
        if not rows:
            return 0
        return int(rows[0].get('cnt') or 0)

    def _count_config_rules(self, structure_id: Any) -> int:
        try:
            rows = self.ds.query(
                f"SELECT COUNT(*) AS cnt FROM {_CONFIG_RULE_TABLE} WHERE structure_id = ?",
                [structure_id])
        except Exception as e:  # fail-open
            logger.warning(f'[item_structure_guard] 统计配置规则失败: {e}')
            return 0
        return int(rows[0].get('cnt') or 0) if rows else 0

    def _count_line_rule_refs(self, line_id: Any) -> int:
        try:
            rows = self.ds.query(
                f"SELECT COUNT(*) AS cnt FROM {_CONFIG_RULE_TERM_TABLE} "
                "WHERE target_line_id = ?", [line_id])
        except Exception as e:  # fail-open
            logger.warning(f'[item_structure_guard] 统计规则条件项失败: {e}')
            return 0
        return int(rows[0].get('cnt') or 0) if rows else 0

    def _fetch_active_versions(self, item_id: Any, usage: Any,
                               alternative_no: Any, exclude_id: Any = None):
        sql = (
            f"SELECT id, valid_from, valid_to FROM {_STRUCTURE_TABLE} "
            "WHERE item_id = ? AND usage = ? AND alternative_no = ? AND status = 'active'"
        )
        params = [item_id, usage, alternative_no]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        try:
            return self.ds.query(sql, params) or []
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 查询生效版本失败: {e}')
            return []

    def _fetch_edges(self, exclude_id: Any = None) -> Iterable[Tuple[Any, Any]]:
        sql = (
            f"SELECT s.item_id AS parent_item, l.component_item_id AS child_item "
            f"FROM {_LINE_TABLE} l JOIN {_STRUCTURE_TABLE} s ON s.id = l.structure_id"
        )
        params = []
        if exclude_id is not None:
            sql += " WHERE l.id != ?"
            params.append(exclude_id)
        try:
            rows = self.ds.query(sql, params) or []
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 读取结构图失败: {e}')
            return []
        return [(row.get('parent_item'), row.get('child_item')) for row in rows]

    def _count_substitute_anchors(self, structure_id: Any, group_code: str,
                                  exclude_id: Any = None) -> int:
        sql = (
            f"SELECT COUNT(*) AS cnt FROM {_LINE_TABLE} "
            "WHERE structure_id = ? AND substitute_group_code = ? AND optional_flag = 0"
        )
        params = [structure_id, group_code]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[item_structure_guard] 查询替代组失败: {e}')
            return 0
        if not rows:
            return 0
        return int(rows[0].get('cnt') or 0)

    def _creates_cycle(self, component_item_id: Any, parent_item_id: Any,
                       exclude_id: Any = None) -> bool:
        """R1：从组件物料沿「父项 → 组件」边能否回到父项物料。"""
        adjacency: Dict[str, Set[str]] = {}
        for parent, child in self._fetch_edges(exclude_id):
            if _is_blank(parent) or _is_blank(child):
                continue
            adjacency.setdefault(str(parent), set()).add(str(child))
        target = str(parent_item_id)
        seen: Set[str] = set()
        stack = [str(component_item_id)]
        while stack:
            current = stack.pop()
            for nxt in adjacency.get(current, ()):
                if nxt == target:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        return False
