# -*- coding: utf-8 -*-
"""类型字典守卫 —— 单据类型 / 行类型写入的一致性校验。

依据:
  docs/superpowers/specs/2026-10-25-type-definition-generalization-spec.md §4.1
  meta/schemas/type_definition.yaml 头注释「层级与字段适用」

落点划分:
  I1  level=header ⇒ document_category 非空；level=line ⇒ 该列必须为空
  I2  level=line   ⇒ line_category 非空；level=header ⇒ 该列必须为空
  I3  level=line   ⇒ number_sequence_id / default_type_id 必须为空
  I4  default_type_id 目标必须同 scope_bo 且 level=line（DB 无法表达）
  I6  scope_bo / level 创建后不可变

  I5（code 在 scope_bo + level 内唯一）由数据库唯一索引
  idx_type_definition_scope_code 承担，不在服务层重复。

  D1  删除前检查引用：被销售订单 / 销售订单行 / 其他类型的默认行类型引用时拒绝。
      物理库未开启 PRAGMA foreign_keys，外键不会拦截，必须由服务层承担。

  scope_bo 的目标 BO 存在性只给 WARNING：当前 sales_order 尚未建模，
  提前判死会让类型字典无法录入。

查询失败一律 fail-open + WARNING（沿用 sales_config_guard 口径）：
一次瞬时查询异常不应把整条写入路径打死。

已知边界：拦截器链只覆盖 bo_api 写路径；manage_api 与 Excel 导入绕过拦截器链，
本守卫对这两条路径不生效（与其他守卫同一限制）。
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_LEVELS = ('header', 'line')

#: (引用表, 引用列, 中文说明) —— D1 删除前引用检查
_REFERENCE_TABLES = (
    ('sales_orders', 'order_type_id', '销售订单'),
    ('sales_order_lines', 'line_type_id', '销售订单行'),
    ('type_definitions', 'default_type_id', '其他类型的默认行类型'),
)


class TypeDefinitionGuardError(ValueError):
    """类型字典守卫拒绝写入。`field_name` / `rule` 供前端定位字段与规则。"""

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


def _text(value: Any) -> str:
    return '' if value is None else str(value).strip()


class TypeDefinitionGuardService:
    """类型字典写入前校验（I1 / I2 / I3 / I4 / I6）。"""

    TABLE = 'type_definitions'

    def __init__(self, data_source):
        self.ds = data_source

    # ------------------------------------------------------------------
    # 公开入口
    # ------------------------------------------------------------------

    def validate_write(self, data: Dict[str, Any], exclude_id: Any = None) -> None:
        """创建 / 更新前校验。`data` 应是「更新后的有效行」。"""
        scope_bo = _text(data.get('scope_bo'))
        level = _text(data.get('level')).lower()

        if not scope_bo:
            raise TypeDefinitionGuardError(
                '归属对象不能为空', field_name='scope_bo', rule='scope_bo_required')
        if level not in _LEVELS:
            raise TypeDefinitionGuardError(
                '层级必须是「单据头」或「单据行」',
                field_name='level', rule='invalid_level')

        # I6：创建后 scope_bo / level 不可变
        if exclude_id is not None:
            old = self._fetch(exclude_id)
            if old:
                if _text(old.get('scope_bo')) != scope_bo:
                    raise TypeDefinitionGuardError(
                        '归属对象创建后不可修改',
                        field_name='scope_bo', rule='immutable')
                if _text(old.get('level')).lower() != level:
                    raise TypeDefinitionGuardError(
                        '层级创建后不可修改',
                        field_name='level', rule='immutable')

        document_category = data.get('document_category')
        line_category = data.get('line_category')
        default_type_id = data.get('default_type_id')
        number_sequence_id = data.get('number_sequence_id')

        # I1：单据类别只属于 header
        if level == 'header' and _is_blank(document_category):
            raise TypeDefinitionGuardError(
                '单据头类型必须填写单据类别',
                field_name='document_category', rule='document_category_required')
        if level == 'line' and not _is_blank(document_category):
            raise TypeDefinitionGuardError(
                '单据行类型不能填写单据类别',
                field_name='document_category', rule='document_category_not_allowed')

        # I2：行类别只属于 line
        if level == 'line' and _is_blank(line_category):
            raise TypeDefinitionGuardError(
                '单据行类型必须填写行类别',
                field_name='line_category', rule='line_category_required')
        if level == 'header' and not _is_blank(line_category):
            raise TypeDefinitionGuardError(
                '单据头类型不能填写行类别',
                field_name='line_category', rule='line_category_not_allowed')

        # I3：取号规则与默认行类型只属于 header
        if level == 'line':
            if not _is_blank(number_sequence_id):
                raise TypeDefinitionGuardError(
                    '单据行类型不能绑定编号序列',
                    field_name='number_sequence_id', rule='header_only_field')
            if not _is_blank(default_type_id):
                raise TypeDefinitionGuardError(
                    '单据行类型不能指定默认行类型',
                    field_name='default_type_id', rule='header_only_field')

        # I4：默认行类型必须同 scope_bo 且 level=line
        if not _is_blank(default_type_id):
            self._assert_default_type(default_type_id, scope_bo)

        # scope_bo 目标 BO 暂按警告级（sales_order 尚未建模）
        if self._resolve_table(scope_bo) is None:
            logger.warning(
                '[type_definition_guard] 归属对象「%s」未注册为业务对象，'
                '暂按警告放行', scope_bo)

    # ------------------------------------------------------------------
    # D1：删除前引用检查
    # ------------------------------------------------------------------

    def validate_delete(self, type_id: Any) -> None:
        """被订单 / 订单行 / 其他类型引用时禁止删除。

        物理库未启用 PRAGMA foreign_keys（外键声明存在但不拦截），
        若不做此检查，删除会静默成功并留下悬空引用。
        """
        if _is_blank(type_id):
            return
        for table, column, label in _REFERENCE_TABLES:
            count = self._count_refs(table, column, type_id)
            if count:
                raise TypeDefinitionGuardError(
                    f'该类型已被 {count} 条{label}引用，不能删除',
                    field_name='id', rule='referenced_in_use')

    # ------------------------------------------------------------------
    # I4
    # ------------------------------------------------------------------

    def _assert_default_type(self, default_type_id: Any, scope_bo: str) -> None:
        target = self._fetch(default_type_id)
        if target is None:
            # 记录不存在或查询失败：交给外键 / 后续校验兜底（fail-open）
            return
        if _text(target.get('scope_bo')) != scope_bo:
            raise TypeDefinitionGuardError(
                '默认行类型必须与当前类型属于同一归属对象',
                field_name='default_type_id', rule='default_type_scope_mismatch')
        if _text(target.get('level')).lower() != 'line':
            raise TypeDefinitionGuardError(
                '默认行类型必须是单据行类型',
                field_name='default_type_id', rule='default_type_level_mismatch')

    # ------------------------------------------------------------------
    # 查询（可覆写，便于单测注入）
    # ------------------------------------------------------------------

    def _fetch(self, record_id: Any) -> Optional[Dict[str, Any]]:
        try:
            rows = self.ds.query(
                f'SELECT * FROM {self.TABLE} WHERE id = ?', [record_id])
        except Exception as e:  # 查询失败 → fail-open
            logger.warning(f'[type_definition_guard] 查询失败: {e}')
            return None
        return rows[0] if rows else None

    def _count_refs(self, table: str, column: str, record_id: Any) -> int:
        try:
            rows = self.ds.query(
                f'SELECT COUNT(*) AS cnt FROM {table} WHERE {column} = ?',
                [record_id])
        except Exception as e:  # 表不存在 / 查询失败 → fail-open
            logger.warning(
                f'[type_definition_guard] 统计 {table}.{column} 引用失败: {e}')
            return 0
        if not rows:
            return 0
        try:
            return int(rows[0].get('cnt') or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _resolve_table(bo_id: str) -> Optional[str]:
        """对象 id → 物理表名（未注册对象返回 None）。"""
        try:
            from meta.core.models import registry
            meta = registry.get(bo_id)
            return getattr(meta, 'table_name', None) if meta else None
        except Exception as e:
            logger.warning(f'[type_definition_guard] 解析对象 {bo_id} 失败: {e}')
            return None
