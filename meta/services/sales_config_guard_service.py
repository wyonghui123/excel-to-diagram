# -*- coding: utf-8 -*-
"""销售配置守卫 —— 控制参数与行类型确定的写入一致性校验。

依据:
  meta/schemas/control_parameter_def.yaml 头注释「进入门槛 / 解析口径」
  meta/schemas/control_parameter_value.yaml 头注释「命中规则 ④」
  meta/schemas/line_type_assignment.yaml 头注释「命中规则 ④」

落点划分:
  D1  value_type=enum 时 enum_type_id 必填，其它值类型必须为空      —— validate_parameter_def_write
  D2  value_type=ref 时 target_bo 必填且必须是已注册对象，其它值类型必须为空
  D3  default_value 必须能按 value_type 解释（含 enum 值集 / ref 存在性）
  D4  已有取值（control_parameter_values 行）后，code / value_type /
      enum_type_id / target_bo 不可改 —— 否则已配置的取值会被静默改义
  V1  取值 value 必须能按所属定义的 value_type 解释（含 enum / ref 校验）
  V2  同一参数下「维度组合 + specificity_rank」唯一 —— SQLite 中 NULL 不参与
      唯一约束，故必须按 NULL 归一化后在应用层判重
  A1  同一单据类型下「物料组 + specificity_rank」唯一（同理 NULL 归一化）
  X1  删除被 ref 参数引用的业务对象前，参数取值里不能还有悬空引用
      （restrict_on 只能表达列级外键，表达不了 value 文本列里的主键）

查询失败一律 fail-open + WARNING（沿用 currency_rate / payment_term 守卫口径）：
读侧守卫不应因一次瞬时查询异常把整条写入路径打死。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与其他守卫同一限制）。
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TRUE_VALUES = frozenset({'true', '1', 'yes', 'y', '是'})
_FALSE_VALUES = frozenset({'false', '0', 'no', 'n', '否'})
#: specificity_rank 的兜底值（与 schema 默认值一致，防 NULL 参与比较）
_RANK_FALLBACK = 100


class SalesConfigGuardError(ValueError):
    """销售配置守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

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


def _same_optional(left: Any, right: Any) -> bool:
    """可空字段比较：空白与 None 等价，其余按字符串比（规避 int/str 差异）。"""
    if _is_blank(left) and _is_blank(right):
        return True
    return str(left).strip() == str(right).strip()


def _rank(value: Any) -> int:
    if _is_blank(value):
        return _RANK_FALLBACK
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return _RANK_FALLBACK


class SalesConfigGuardService:
    """控制参数 / 行类型确定的写入前校验。

    覆写 `_resolve_table` / `_count_ref` / `_count_enum_value` / `_fetch_def`
    / `_count_values` / `_count_value_dup` / `_count_assignment_dup`
    / `_count_ref_values` 即可注入测试数据（不依赖真实库）。
    """

    DEF_TABLE = 'control_parameter_defs'
    VALUE_TABLE = 'control_parameter_values'
    ASSIGNMENT_TABLE = 'line_type_assignments'
    ENUM_VALUE_TABLE = 'enum_values'

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    def validate_parameter_def_write(self, data: Dict[str, Any],
                                     exclude_id: Any = None) -> None:
        """参数定义创建 / 更新前校验 D1 / D2 / D3 / D4。"""
        value_type = str(data.get('value_type') or 'string').strip().lower()
        enum_type_id = data.get('enum_type_id')
        target_bo = str(data.get('target_bo') or '').strip()

        # D1 / D2：值类型与「值集 / 目标对象」双向一致
        if value_type == 'enum':
            if _is_blank(enum_type_id):
                raise SalesConfigGuardError(
                    '值类型为枚举时必须选择枚举类型',
                    field_name='enum_type_id', rule='enum_type_required')
            if target_bo:
                raise SalesConfigGuardError(
                    '值类型为枚举时不能再指定引用对象',
                    field_name='target_bo', rule='target_bo_not_allowed')
        elif value_type == 'ref':
            if not target_bo:
                raise SalesConfigGuardError(
                    '值类型为引用时必须填写引用对象',
                    field_name='target_bo', rule='target_bo_required')
            if self._resolve_table(target_bo) is None:
                raise SalesConfigGuardError(
                    f'引用对象「{target_bo}」不是已注册的业务对象',
                    field_name='target_bo', rule='unknown_target_bo')
            if not _is_blank(enum_type_id):
                raise SalesConfigGuardError(
                    '值类型为引用时不能再指定枚举类型',
                    field_name='enum_type_id', rule='enum_type_not_allowed')
        else:
            if not _is_blank(enum_type_id):
                raise SalesConfigGuardError(
                    '仅枚举型参数可以指定枚举类型',
                    field_name='enum_type_id', rule='enum_type_not_allowed')
            if target_bo:
                raise SalesConfigGuardError(
                    '仅引用型参数可以指定引用对象',
                    field_name='target_bo', rule='target_bo_not_allowed')

        # D3：兜底默认值必须能被该值类型解释
        definition = dict(data)
        definition['value_type'] = value_type
        default_value = data.get('default_value')
        if not _is_blank(default_value):
            self._validate_typed_value(definition, default_value, 'default_value')

        # D4：已有取值后，参数语义（编码 / 值类型 / 值集 / 目标对象）不可改
        if exclude_id is None or self._count_values(exclude_id) <= 0:
            return
        old = self._fetch_def(exclude_id)
        if not old:
            return
        if not _same_optional(old.get('code'), data.get('code')):
            raise SalesConfigGuardError(
                '该参数已有取值记录，参数编码不可修改',
                field_name='code', rule='immutable_after_values')
        if not _same_optional(old.get('value_type'), value_type):
            raise SalesConfigGuardError(
                '该参数已有取值记录，值类型不可修改',
                field_name='value_type', rule='immutable_after_values')
        if not _same_optional(old.get('enum_type_id'), enum_type_id):
            raise SalesConfigGuardError(
                '该参数已有取值记录，枚举类型不可修改',
                field_name='enum_type_id', rule='immutable_after_values')
        if not _same_optional(old.get('target_bo'), target_bo):
            raise SalesConfigGuardError(
                '该参数已有取值记录，引用对象不可修改',
                field_name='target_bo', rule='immutable_after_values')

    def validate_parameter_value_write(self, data: Dict[str, Any],
                                       exclude_id: Any = None) -> None:
        """参数取值创建 / 更新前校验 V1 / V2。"""
        param_id = data.get('control_parameter_id')
        if _is_blank(param_id):
            return  # 缺父键交给必填校验兜底

        definition = self._fetch_def(param_id)
        if definition is None:
            return  # 参数不存在时交给外键 / 层级校验兜底

        # V1：取值按所属定义的值类型解释
        value = data.get('value')
        if not _is_blank(value):
            self._validate_typed_value(definition, value, 'value')

        # V2：维度组合 + specificity_rank 唯一（NULL 归一化后判重）
        if self._count_value_dup(
            param_id,
            data.get('org_id'),
            data.get('document_type_id'),
            data.get('line_type_id'),
            data.get('item_group_id'),
            _rank(data.get('specificity_rank')),
            exclude_id,
        ) > 0:
            raise SalesConfigGuardError(
                '同一参数下「组织 / 单据类型 / 行类型 / 物料组 + 具体度」'
                '已有取值记录，不能重复配置',
                field_name='specificity_rank', rule='dimension_conflict')

    def validate_assignment_write(self, data: Dict[str, Any],
                                  exclude_id: Any = None) -> None:
        """行类型确定创建 / 更新前校验 A1。"""
        doc_type_id = data.get('document_type_id')
        if _is_blank(doc_type_id):
            return  # 缺父键交给必填校验兜底

        if self._count_assignment_dup(
            doc_type_id,
            data.get('item_group_id'),
            _rank(data.get('specificity_rank')),
            exclude_id,
        ) > 0:
            raise SalesConfigGuardError(
                '同一单据类型下「物料组 + 具体度」已有确定规则，不能重复配置',
                field_name='specificity_rank', rule='assignment_conflict')

    def assert_no_ref_values(self, target_bo: str, record_id: Any) -> None:
        """X1：删除业务对象前，ref 型参数的取值里不能还有指向它的引用。"""
        if _is_blank(target_bo) or _is_blank(record_id):
            return
        codes = self._count_ref_values(target_bo, record_id)
        if not codes:
            return
        names = '、'.join(str(c) for c in codes[:5])
        more = '' if len(codes) <= 5 else f' 等 {len(codes)} 个参数'
        raise SalesConfigGuardError(
            f'该记录仍被控制参数「{names}」{more}的取值引用，请先清理参数取值',
            field_name='id', rule='ref_target_in_use')

    # ------------------------------------------------------------------
    # 类型解释（V1 / D3 共用）
    # ------------------------------------------------------------------

    def _validate_typed_value(self, definition: Dict[str, Any], raw: Any,
                              field: str) -> None:
        """按 value_type 校验原始值；无法判定（查询失败）时 fail-open。"""
        value_type = str(definition.get('value_type') or 'string').strip().lower()
        text = str(raw).strip()

        if value_type == 'bool':
            if text.lower() not in (_TRUE_VALUES | _FALSE_VALUES):
                raise SalesConfigGuardError(
                    f'取值「{raw}」不是布尔值（应为 true / false）',
                    field_name=field, rule='invalid_value')

        elif value_type == 'int':
            try:
                int(text)
            except (TypeError, ValueError):
                raise SalesConfigGuardError(
                    f'取值「{raw}」不是整数',
                    field_name=field, rule='invalid_value')

        elif value_type == 'decimal':
            try:
                if not Decimal(text).is_finite():
                    raise InvalidOperation
            except (InvalidOperation, ValueError):
                raise SalesConfigGuardError(
                    f'取值「{raw}」不是数值',
                    field_name=field, rule='invalid_value')

        elif value_type == 'ref':
            try:
                ref_id = int(text)
            except (TypeError, ValueError):
                raise SalesConfigGuardError(
                    f'引用型参数取值「{raw}」必须是目标对象主键',
                    field_name=field, rule='invalid_value')
            target_bo = str(definition.get('target_bo') or '').strip()
            if not target_bo:
                raise SalesConfigGuardError(
                    '引用型参数未配置目标对象，无法校验取值',
                    field_name=field, rule='invalid_value')
            missing = self._count_ref(target_bo, ref_id)
            if missing == 0:
                raise SalesConfigGuardError(
                    f'引用对象 {target_bo} #{ref_id} 不存在',
                    field_name=field, rule='ref_not_found')

        elif value_type == 'enum':
            enum_type_id = definition.get('enum_type_id')
            if _is_blank(enum_type_id):
                raise SalesConfigGuardError(
                    '枚举型参数未配置枚举类型，无法校验取值',
                    field_name=field, rule='invalid_value')
            missing = self._count_enum_value(enum_type_id, text)
            if missing == 0:
                raise SalesConfigGuardError(
                    f'取值「{raw}」不在该枚举类型的值集中',
                    field_name=field, rule='enum_value_not_found')

        # string：任意文本，无需校验

    # ------------------------------------------------------------------
    # 查询（可覆写，便于单测注入）
    # ------------------------------------------------------------------

    def _one(self, sql: str, params: List[Any]) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(sql, params)
        except Exception as e:  # 查询失败 → fail-open（不阻断正常写入）
            logger.warning(f'[sales_config_guard] 查询失败: {e}')
            return None
        return rows[0] if rows else None

    def _fetch_def(self, param_id: Any) -> Optional[Dict[str, Any]]:
        return self._one(
            f'SELECT * FROM {self.DEF_TABLE} WHERE id = ?', [param_id])

    def _count_values(self, param_id: Any) -> int:
        row = self._one(
            f'SELECT COUNT(*) AS cnt FROM {self.VALUE_TABLE} '
            'WHERE control_parameter_id = ?', [param_id])
        return self._cnt(row)

    def _count_value_dup(self, param_id: Any, org_id: Any, doc_type_id: Any,
                         line_type_id: Any, item_group_id: Any, rank: int,
                         exclude_id: Any) -> int:
        sql = (
            f'SELECT COUNT(*) AS cnt FROM {self.VALUE_TABLE} '
            'WHERE control_parameter_id = ? '
            'AND COALESCE(org_id, 0) = COALESCE(?, 0) '
            'AND COALESCE(document_type_id, 0) = COALESCE(?, 0) '
            'AND COALESCE(line_type_id, 0) = COALESCE(?, 0) '
            'AND COALESCE(item_group_id, 0) = COALESCE(?, 0) '
            'AND COALESCE(specificity_rank, ?) = ? '
            'AND id <> ?'
        )
        params = [param_id, org_id, doc_type_id, line_type_id, item_group_id,
                  _RANK_FALLBACK, rank, -1 if exclude_id is None else exclude_id]
        return self._cnt(self._one(sql, params))

    def _count_assignment_dup(self, doc_type_id: Any, item_group_id: Any,
                              rank: int, exclude_id: Any) -> int:
        sql = (
            f'SELECT COUNT(*) AS cnt FROM {self.ASSIGNMENT_TABLE} '
            'WHERE document_type_id = ? '
            'AND COALESCE(item_group_id, 0) = COALESCE(?, 0) '
            'AND COALESCE(specificity_rank, ?) = ? '
            'AND id <> ?'
        )
        params = [doc_type_id, item_group_id, _RANK_FALLBACK, rank,
                  -1 if exclude_id is None else exclude_id]
        return self._cnt(self._one(sql, params))

    def _count_ref(self, target_bo: str, ref_id: Any) -> Optional[int]:
        """引用目标是否存在：0 = 不存在，None = 无法判定（fail-open）。"""
        table = self._resolve_table(target_bo)
        if table is None:
            return None
        row = self._one(f'SELECT COUNT(*) AS cnt FROM {table} WHERE id = ?', [ref_id])
        return None if row is None else self._cnt(row)

    def _count_enum_value(self, enum_type_id: Any, code: str) -> Optional[int]:
        row = self._one(
            f'SELECT COUNT(*) AS cnt FROM {self.ENUM_VALUE_TABLE} '
            'WHERE enum_type_id = ? AND code = ? AND COALESCE(is_active, 1) = 1',
            [enum_type_id, code])
        return None if row is None else self._cnt(row)

    def _count_ref_values(self, target_bo: str, record_id: Any) -> List[str]:
        """返回指向该记录的参数编码列表；查询失败 → 空列表（fail-open）。"""
        try:
            defs = self.ds.query(
                f"SELECT id, code FROM {self.DEF_TABLE} "
                "WHERE value_type = 'ref' AND target_bo = ?", [target_bo])
        except Exception as e:
            logger.warning(f'[sales_config_guard] 查询引用型参数失败: {e}')
            return []
        ids = [row.get('id') for row in defs or [] if row.get('id') is not None]
        if not ids:
            return []
        placeholders = ','.join('?' * len(ids))
        try:
            rows = self.ds.query(
                f"SELECT DISTINCT control_parameter_id FROM {self.VALUE_TABLE} "
                f'WHERE control_parameter_id IN ({placeholders}) AND value = ?',
                ids + [str(record_id).strip()])
        except Exception as e:
            logger.warning(f'[sales_config_guard] 查询参数取值引用失败: {e}')
            return []
        hit_ids = {str(row.get('control_parameter_id')) for row in rows or []}
        return [row.get('code') for row in defs
                if str(row.get('id')) in hit_ids]

    @staticmethod
    def _resolve_table(target_bo: str) -> Optional[str]:
        """对象 id → 物理表名（未注册对象返回 None）。"""
        try:
            from meta.core.models import registry
            meta = registry.get(target_bo)
            return getattr(meta, 'table_name', None) if meta else None
        except Exception as e:
            logger.warning(f'[sales_config_guard] 解析对象 {target_bo} 失败: {e}')
            return None

    @staticmethod
    def _cnt(row: Optional[Dict[str, Any]]) -> int:
        if not row:
            return 0
        try:
            return int(row.get('cnt') or 0)
        except (TypeError, ValueError):
            return 0
