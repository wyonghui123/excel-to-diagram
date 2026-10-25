# -*- coding: utf-8 -*-
"""属性字典 lint —— 把「扩展准入」的五道否决项落成可执行的写入前校验。

依据: docs/superpowers/specs/2026-10-25-attribute-extension-and-dictionary-spec.md
      §3（判据与否决项）/ §4（对象模型与不变量）/ §5（多租户命名空间）

为什么是 lint 而不是文档红线: 文档里的红线 AI 与人都会忘，只有会让写入失败的规则才会被执行。
本服务只做「定义与范围」两组检查；值行的类型互斥与必填由属性值服务负责（另一处入口）。

检查项（编号与 spec 不变量对齐）:
  L1 平台层命名冲突（R5）—— tenant_id = 0 的 code 不得与任一已注册对象的字段名重名
  L2 使用分级越界（R1）—— usage_class 不是 descriptive / analytic 时不得为 active
  L3 可配置特征约束（R6）—— is_configurable 必须覆盖物料对象，且不得用日期类型
  L4 范围引用有效（R5）—— object 范围须为已注册的物理对象；item_group 范围须为已存在的分类
  L7 租户层不得占用平台层编码（R5）
"""

import logging
from typing import Any, Dict, Optional

from meta.core.models_enums import ObjectType

logger = logging.getLogger(__name__)

#: 只有这两类用途允许停在字典层；其余必须提为物理字段
ACTIVE_USAGE_CLASSES = ('descriptive', 'analytic')

#: 可配置特征支持的类型（日期类型不参与选配）
CONFIGURABLE_DATA_TYPES = ('string', 'number', 'integer', 'boolean')

#: 命名冲突检查时跳过的技术列（每个对象都有，不构成占名）
TECHNICAL_FIELDS = frozenset({
    'id', 'tenant_id', 'created_at', 'updated_at', 'created_by', 'updated_by',
})

#: 可配置特征必须覆盖的对象
CONFIGURABLE_REQUIRED_SCOPE = ('object', 'item')

#: 不能承载属性值的对象类型（视图 / 虚拟）
_NON_PERSISTENT_TYPES = (ObjectType.VIEW, ObjectType.VIRTUAL)


class AttributeLintError(ValueError):
    """属性定义 / 范围不满足准入约束 —— 拒绝写入。"""

    def __init__(self, message: str, rule: str, field_name: str = ''):
        super().__init__(message)
        self.rule = rule
        self.field_name = field_name


class AttributeLintService:
    """属性定义与适用范围的写入前校验。

    覆写查询辅助方法可注入测试数据，避免单测依赖真实库。
    """

    DEFINITION_TABLE = 'attribute_definitions'
    SCOPE_TABLE = 'attribute_scopes'
    ITEM_GROUP_TABLE = 'item_groups'

    def __init__(self, data_source=None):
        self.ds = data_source

    # ---------- 定义 ----------

    def check_definition(self, data: Dict[str, Any],
                         exclude_id: Optional[int] = None) -> None:
        """校验 attribute_definition 写入载荷（更新场景应传入合并后的有效行）。"""
        code = (data.get('code') or '').strip()
        if not code:
            return  # 缺编码归 required / pattern 校验

        tenant_id = _as_int(data.get('tenant_id'), default=0)
        usage_class = (data.get('usage_class') or 'descriptive').strip()
        status = (data.get('status') or 'active').strip()
        data_type = (data.get('data_type') or 'string').strip()
        is_configurable = _as_bool(data.get('is_configurable'))

        # L1 / L7 命名空间：平台层不得与字段重名；租户层不得占用平台层编码
        if tenant_id == 0:
            owner = self._field_owner(code)
            if owner:
                raise AttributeLintError(
                    f"属性编码 '{code}' 与对象 {owner} 的字段重名。"
                    '平台层属性是全局命名空间，请换一个编码。',
                    rule='attribute_code_conflict_field',
                    field_name='code',
                )
        elif self._platform_code_exists(code, exclude_id=exclude_id):
            raise AttributeLintError(
                f"属性编码 '{code}' 已被平台层定义占用。租户层不得与平台层重名，"
                '请换一个编码或直接复用平台层定义。',
                rule='attribute_code_conflict_platform',
                field_name='code',
            )

        # L2 使用分级越界：参与计算 / 需索引 / 被引用 / 有生命周期 / 切权限的属性不进字典
        if usage_class not in ACTIVE_USAGE_CLASSES and status == 'active':
            raise AttributeLintError(
                f"使用分级 '{usage_class}' 的属性不能启用。"
                '这类属性须走属性提升通道（attribute_promotion）提为物理字段；'
                '只有 descriptive / analytic 允许停在字典层。',
                rule='attribute_usage_class_not_allowed',
                field_name='usage_class',
            )

        # L3 可配置特征：类型受限（不含日期），且必须覆盖物料对象
        if not is_configurable:
            return

        if data_type not in CONFIGURABLE_DATA_TYPES:
            raise AttributeLintError(
                f"可配置特征不支持数据类型 '{data_type}'；"
                f'只允许 {"/".join(CONFIGURABLE_DATA_TYPES)}。',
                rule='attribute_configurable_data_type',
                field_name='data_type',
            )

        if status != 'active':
            return  # 未启用的定义不检查范围；启用时再校验

        attribute_id = data.get('id') if exclude_id is not None else None
        if attribute_id is None:
            raise AttributeLintError(
                '可配置特征须两步建立：先以非启用状态创建定义，'
                '配置 item 适用范围后再启用。',
                rule='attribute_configurable_requires_scope',
                field_name='status',
            )
        if not self._has_scope(attribute_id, *CONFIGURABLE_REQUIRED_SCOPE):
            raise AttributeLintError(
                '可配置特征缺少物料范围声明：请先在属性适用范围中添加 '
                'scope_type=object、scope_ref=item 的行，再启用。',
                rule='attribute_configurable_requires_scope',
                field_name='status',
            )

    # ---------- 范围 ----------

    def check_scope(self, data: Dict[str, Any]) -> None:
        """校验 attribute_scope 写入载荷。"""
        scope_type = (data.get('scope_type') or '').strip()
        scope_ref = (data.get('scope_ref') or '').strip()
        if not scope_type or not scope_ref:
            return  # 缺字段归 required 校验

        if scope_type == 'object':
            obj = self._get_object(scope_ref)
            if obj is None:
                raise AttributeLintError(
                    f"范围引用 '{scope_ref}' 不是已注册对象。",
                    rule='attribute_scope_object_missing',
                    field_name='scope_ref',
                )
            if getattr(obj, 'object_type', None) in _NON_PERSISTENT_TYPES:
                raise AttributeLintError(
                    f"对象 '{scope_ref}' 是视图 / 虚拟对象，不能承载属性值；"
                    '请改用可持久化的对象。',
                    rule='attribute_scope_object_not_persistent',
                    field_name='scope_ref',
                )
            return

        if scope_type == 'item_group':
            if not self._item_group_exists(scope_ref):
                raise AttributeLintError(
                    f"物料分类 '{scope_ref}' 不存在。",
                    rule='attribute_scope_item_group_missing',
                    field_name='scope_ref',
                )
            return

        raise AttributeLintError(
            f"未知的范围类型 '{scope_type}'；只允许 object / item_group。",
            rule='attribute_scope_type_invalid',
            field_name='scope_type',
        )

    # ---------- 查询辅助（可覆写注入）----------

    def _get_object(self, object_id: str):
        from meta.core.models import registry
        return registry.get(object_id)

    def _field_owner(self, code: str) -> Optional[str]:
        """返回占用该字段名的对象 id；未占用返回 None。"""
        from meta.core.models import registry
        if code in TECHNICAL_FIELDS:
            return None
        for object_id, obj in registry.get_all().items():
            for field in obj.fields or []:
                if getattr(field, 'id', None) == code:
                    return object_id
        return None

    def _platform_code_exists(self, code: str,
                              exclude_id: Optional[int] = None) -> bool:
        sql = (f'SELECT id FROM {self.DEFINITION_TABLE} '
               'WHERE tenant_id = 0 AND code = ?')
        params = [code]
        if exclude_id is not None:
            sql += ' AND id != ?'
            params.append(exclude_id)
        sql += ' LIMIT 1'
        return bool(self._query(sql, params))

    def _has_scope(self, attribute_id: Any, scope_type: str, scope_ref: str) -> bool:
        sql = (f'SELECT id FROM {self.SCOPE_TABLE} '
               'WHERE attribute_id = ? AND scope_type = ? AND scope_ref = ? '
               "AND status = 'active' LIMIT 1")
        return bool(self._query(sql, [attribute_id, scope_type, scope_ref]))

    def _item_group_exists(self, code: str) -> bool:
        sql = f'SELECT id FROM {self.ITEM_GROUP_TABLE} WHERE code = ? LIMIT 1'
        return bool(self._query(sql, [code]))

    def _query(self, sql: str, params) -> list:
        if self.ds is None:
            return []
        try:
            rows = self.ds.query(sql, params)
            return rows or []
        except Exception as e:  # 查询失败 → fail-open（不阻断定义维护）
            logger.warning(f'[attribute_lint] 查询失败，跳过该项检查: {e}')
            return []


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'y')
    return bool(value)
