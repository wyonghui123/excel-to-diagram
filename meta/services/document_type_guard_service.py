# -*- coding: utf-8 -*-
"""单据类型守卫（平台层规范 T-D20）。

所有声明 `document_type_id` 的业务单据头统一走这里，不再每张单据各写一套：

  · 创建时必填；
  · 只能是本单据归属域（`scope_bo` = 当前 BO）的 header 类型；
  · 类型必须 active；
  · 离开草稿后不可修改。

切面 `document_type_aspect`（meta/schemas/aspects.yaml）负责字段与 value_help；
本服务负责写入侧校验。二者合起来保证「加一张单据只需加一行 aspects」。
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

DOCUMENT_TYPE_FIELD = 'document_type_id'
LINE_TYPE_FIELD = 'line_type_id'
DEFAULT_TYPE_FIELD = 'default_type_id'
HEADER_LEVEL = 'header'
STATUS_ACTIVE = 'active'
STATUS_DRAFT = 'draft'

#: 引用类型字典的列名（用于删除保护扫描）
_TYPE_REFERENCE_FIELDS = (DOCUMENT_TYPE_FIELD, LINE_TYPE_FIELD, DEFAULT_TYPE_FIELD)

#: 业务单据头的语义类别；单据类型维度表（控制参数取值 / 行类型分配）不属此类
BUSINESS_DOCUMENT_CATEGORY = 'business_document'

#: 单据类型切面名（声明即视为业务单据头）
DOCUMENT_TYPE_ASPECT = 'document_type_aspect'


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == '')


def object_declares_document_type(meta_object: Any) -> bool:
    """对象是否声明了**自身**的单据类型（切面或本地字段均可）。

    `document_type_id` 同时出现在「把单据类型当维度」的配置表
    （control_parameter_value / line_type_assignment）里，那类对象不是业务单据头，
    其类型值属于别的单据域，不能按本对象归属域校验
    ⇒ 仅当对象声明 `document_type_aspect` 或语义类别为 business_document 才纳入守卫。
    """
    if meta_object is None:
        return False
    aspects = getattr(meta_object, 'aspects', None) or []
    semantics = getattr(meta_object, 'semantics', None)
    is_business_document = str(getattr(semantics, 'category', '') or '') == BUSINESS_DOCUMENT_CATEGORY
    if DOCUMENT_TYPE_ASPECT not in aspects and not is_business_document:
        return False
    for field in getattr(meta_object, 'fields', []) or []:
        if (getattr(field, 'db_column', None) or getattr(field, 'id', None)) == DOCUMENT_TYPE_FIELD:
            return True
    return False


def _object_display_name(object_type: str) -> str:
    try:
        from meta import get_meta_object
        meta = get_meta_object(object_type)
        name = getattr(meta, 'name', None) if meta else None
        return name or object_type
    except Exception:
        return object_type


def type_reference_tables() -> List[Tuple[str, str, str]]:
    """扫描注册表，返回所有引用类型字典的 (表名, 列名, 中文说明)。

    删除保护不再硬编码表名：新增单据只要声明 `document_type_id` / `line_type_id`
    就会自动纳入检查，避免「加了单据却忘了加保护」。
    """
    tables: List[Tuple[str, str, str]] = []
    try:
        from meta.core.models import registry
        for obj_id in registry.list_objects():
            meta = registry.get(obj_id)
            if meta is None or not getattr(meta, 'table_name', None):
                continue
            for field in getattr(meta, 'fields', []) or []:
                column = getattr(field, 'db_column', None) or getattr(field, 'id', None)
                if column in _TYPE_REFERENCE_FIELDS:
                    label = getattr(meta, 'name', None) or obj_id
                    tables.append((meta.table_name, column, label))
                    break
    except Exception as error:
        logger.warning('[document_type_guard] 扫描类型字典引用失败: %s', error)
    return tables


class DocumentTypeGuardService:
    """单据类型写入校验（创建必填 / 归属域 / 停用 / 离草稿冻结）。"""

    TABLE = 'type_definitions'

    def __init__(self, data_source):
        self._ds = data_source

    def validate(self, object_type: str, payload: Dict[str, Any],
                 old_data: Optional[Dict[str, Any]] = None,
                 is_create: bool = False) -> None:
        type_id = (payload or {}).get(DOCUMENT_TYPE_FIELD)
        if is_create:
            if _blank(type_id):
                raise ValueError('单据类型不能为空')
        else:
            if _blank(type_id):
                return
            old_type = (old_data or {}).get(DOCUMENT_TYPE_FIELD)
            if not _blank(old_type):
                if str(type_id) == str(old_type):
                    return
                current_status = (old_data or {}).get('status')
                if not _blank(current_status) and str(current_status) != STATUS_DRAFT:
                    raise ValueError('单据类型离开草稿后不可修改')
        self._assert_type(object_type, type_id)

    def _assert_type(self, object_type: str, type_id: Any) -> None:
        rows = self._ds.query(
            'SELECT id, scope_bo, level, status FROM {0} WHERE id = ?'.format(self.TABLE),
            [type_id])
        if not rows:
            raise ValueError('单据类型不存在')
        row = rows[0]
        if str(row.get('scope_bo')) != str(object_type) \
                or str(row.get('level')) != HEADER_LEVEL:
            raise ValueError(
                '单据类型不属于{0}（须 scope_bo={0} / level=header）'.format(
                    _object_display_name(object_type)))
        if str(row.get('status')) != STATUS_ACTIVE:
            raise ValueError('单据类型已停用')
