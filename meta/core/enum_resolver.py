"""ENUM 值解析 SSOT (Single Source of Truth)

统一 import_export_service / enum_api / annotation_routes_api 中的枚举查询逻辑。

背景：
- import_export_service._get_enum_value_map_from_value_help: 查 DB enum_values 表
- import_export_service._validate_enum_value: 查 DB enum_values 表
- import_export_service._get_enum_type_id_from_value_help: 从 value_help 解析 enum_type_id
- enum_api.get_enum_value_name: 查 DB enum_values 表
- annotation_routes_api: 硬编码 SQL 查 enum_values 表

依赖：data_source（通过参数传入，不持有实例状态）
依赖：value_help_accessor（获取 value_help 配置）
"""

from typing import Dict, Optional, Any


def get_enum_map(meta_field, data_source) -> Optional[Dict[str, str]]:
    """获取字段的枚举映射 {code: name}

    优先级：field.enum_values（静态列表） → value_help.source.enum_type_id（DB 查询）

    Args:
        meta_field: MetaField 实例
        data_source: 数据源实例

    Returns:
        {code: name} 映射字典，无枚举配置时返回 None
    """
    # 1. 先查静态 enum_values
    static_enum = getattr(meta_field, 'enum_values', None)
    if static_enum:
        result = {}
        for v in static_enum:
            if isinstance(v, dict):
                code = v.get('value')
                label = v.get('label', v.get('name', ''))
                if code is not None:
                    result[str(code)] = label
        if result:
            return result

    # 2. 再查 value_help → DB
    from meta.core.value_help_accessor import get_value_help
    vh = get_value_help(meta_field)
    if not vh:
        return None

    source = getattr(vh, 'source', None)
    if not source or getattr(source, 'type', None) != 'enum':
        return None

    enum_type_id = getattr(source, 'enum_type_id', None)
    if not enum_type_id:
        return None

    try:
        sql = "SELECT code, name FROM enum_values WHERE enum_type_id = ? AND is_active = 1 ORDER BY sort_order"
        cursor = data_source.execute(sql, [enum_type_id])
        rows = cursor.fetchall()
        return {row[0]: row[1] for row in rows} if rows else None
    except Exception:
        return None


def get_enum_type_id(meta_field) -> Optional[str]:
    """获取字段的 enum_type_id

    Args:
        meta_field: MetaField 实例

    Returns:
        enum_type_id 字符串，无则返回 None
    """
    from meta.core.value_help_accessor import get_value_help
    vh = get_value_help(meta_field)
    if not vh:
        return None

    source = getattr(vh, 'source', None)
    if not source or getattr(source, 'type', None) != 'enum':
        return None

    return getattr(source, 'enum_type_id', None)


def validate_enum_value(enum_type_id: str, code: str, data_source) -> bool:
    """验证枚举值是否有效 (DB only)

    Args:
        enum_type_id: 枚举类型 ID（如 'relation_type'）
        code: 枚举值编码
        data_source: 数据源实例

    Returns:
        True 表示有效，False 表示无效。
        验证异常时默认返回 True（与现有行为一致，避免误报）。

    [BUG-V040 2026-07-04] 此函数仅查 DB enum_values 表, 不查 schema inline enum_values.
    对于仅在 schema inline enum_values 中定义、且没有 DB seed 的枚举
    (例 user.yaml status 字段 inline {active, inactive, locked}),
    此函数会一直返回 False → 误报"枚举值无效".
    推荐使用 validate_enum_value_with_field(meta_field, ...) 替代本函数.
    """
    try:
        sql = "SELECT COUNT(*) FROM enum_values WHERE enum_type_id = ? AND code = ? AND is_active = 1"
        cursor = data_source.execute(sql, [enum_type_id, code])
        result = cursor.fetchone()
        return result[0] > 0 if result else False
    except Exception:
        return True


def validate_enum_value_with_field(meta_field, code: str, data_source) -> bool:
    """[NEW BUG-V040 2026-07-04] 验证枚举值, 兼容 schema inline enum_values

    优先级:
      1. schema inline enum_values (例 user.yaml status: [active, inactive, locked])
      2. DB enum_values 表 (例 relation_type, direction 等已 seed 的枚举)

    背景:
      之前 import_export_service._validate_enum_value 只走 validate_enum_value (仅查 DB),
      对于只在 schema inline 声明的 enum 字段, DB 没有 seed 记录 → 误报"枚举值无效".
      导出 Excel 时 schema inline enum_values 序列化为 "CODE - LABEL" 格式,
      用户拿这个 Excel 再导入时 _parse_enum_display_to_code 拆出 CODE,
      然后 _validate_enum_value 查 DB 失败, 用户无法导入 → BUG-V040.

    Args:
        meta_field: MetaField 实例 (含 enum_values inline list 和 value_help)
        code: 枚举值编码 (已通过 _parse_enum_display_to_code 拆解)
        data_source: 数据源实例

    Returns:
        True 表示有效, False 表示无效.
        无法判断时返回 True (与 validate_enum_value 默认行为一致, 避免误报).
    """
    # 1. 优先: meta_field.inline enum_values (静态 schema 内联)
    static_enum = getattr(meta_field, 'enum_values', None)
    if static_enum:
        for v in static_enum:
            if isinstance(v, dict):
                vcode = v.get('value')
                if vcode is not None and str(vcode) == str(code):
                    return True
        # 如果有 static enum 但 code 不在列表中 → 确定无效 (无需再查 DB)
        return False

    # 2. fallback: DB enum_values 表
    enum_type_id = get_enum_type_id(meta_field)
    if enum_type_id:
        return validate_enum_value(enum_type_id, code, data_source)

    # 3. 实在查不到 enum_type_id, fallback True (避免误报)
    return True
