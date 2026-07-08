"""[SPR-06 T-S08-02] 通用 descendant_path SQL 子查询构建器.

设计: 业务对象通过层级 (domain → sub_domain → service_module → business_object)
能找到归属的 relationships. 这里的 descendant_path 是从 business_objects 出发的
JOIN 链, 末步的 right 表隐式含一个 <top>_id 字段指向顶层对象.

注册表格式 (object_type → [join_steps]):
  [
    ('service_modules', 'service_module_id'),  # JOIN sm ON bo.service_module_id = sm.id
    ('sub_domains', 'sub_domain_id'),          # JOIN sd ON sm.sub_domain_id = sd.id
  ]

最终 SQL 形如 (object_type='domain' 时):
  EXISTS (SELECT 1 FROM business_objects bo
    JOIN service_modules sm ON bo.service_module_id = sm.id
    JOIN sub_domains sd ON sm.sub_domain_id = sd.id
    WHERE sd.domain_id = domains.id
    AND (r.source_bo_id = bo.id OR r.target_bo_id = bo.id))

约定:
  - 起点表固定为 business_objects
  - 最后一步 right 表隐式含 `<object_type>_id` 字段 (约定俗成, 如 sd.domain_id)
  - 顶层对象 table = `<object_type>s` (domain → domains, 等)
  - 顶层对象 fk = `<object_type>_id` (约定俗成)

未来 YAML 可声明 descendant_path, 此模块从 meta_object 读取.
暂时使用内置注册表 (T-S08-01 YAML 改 schema 后可省略).
"""
from typing import List, Tuple, Optional

# 表别名映射 (显式声明, 不依赖 first-2-chars)
_TABLE_ALIAS = {
    'business_objects': 'bo',
    'service_modules':  'sm',
    'sub_domains':      'sd',
    'domains':          'd',
    'products':         'p',
    'versions':         'v',
    'users':            'u',
    'user_groups':      'ug',
    'roles':            'r',
    'relationships':    'rel',
}

# 起点表 (恒为 business_objects)
_START_TABLE = 'business_objects'

# 注册表: object_type → 中间 JOIN 链
# 每个 step: (right_table, left_fk) 表示 JOIN right_table ON prev_alias.left_fk = right_table.id
_DESCENDANT_PATH_REGISTRY: dict = {
    'domain': [
        ('service_modules', 'service_module_id'),
        ('sub_domains',     'sub_domain_id'),
    ],
    'sub_domain': [
        ('service_modules', 'service_module_id'),
    ],
    'service_module': [],
}


def _alias_of(table: str) -> str:
    """[SPR-06] 查表别名; 找不到时退化为前 2 字符."""
    return _TABLE_ALIAS.get(table, table[:2])


def get_descendant_path(object_type: str) -> Optional[List[Tuple[str, str]]]:
    """[SPR-06] 获取 object_type 的 descendant_path 链. 找不到返回 None."""
    return _DESCENDANT_PATH_REGISTRY.get(object_type)


def register_descendant_path(object_type: str, path: List[Tuple[str, str]]) -> None:
    """[SPR-06] 注册自定义 descendant_path (供 YAML 加载后注入)."""
    _DESCENDANT_PATH_REGISTRY[object_type] = list(path)


def build_descendant_exists_sql(
    object_type: str,
    target_alias: str = '',
) -> Optional[str]:
    """[SPR-06] 生成 EXISTS 子句, 用于 count_relations descendants 场景匹配 r.

    Args:
        object_type: 顶层对象类型 (domain/sub_domain/service_module)
        target_alias: 顶层对象在主查询中的别名 (e.g. "domains", "sub_domains")

    Returns:
        EXISTS 字符串, 或 None (object_type 未注册)
    """
    path = get_descendant_path(object_type)
    if path is None:
        return None

    # 起点: business_objects
    start_alias = _alias_of(_START_TABLE)
    join_lines = [f"FROM {_START_TABLE} {start_alias}"]

    prev_alias = start_alias
    last_table = _START_TABLE
    for right_table, left_fk in path:
        right_alias = _alias_of(right_table)
        join_lines.append(
            f"JOIN {right_table} {right_alias} ON {prev_alias}.{left_fk} = {right_alias}.id"
        )
        prev_alias = right_alias
        last_table = right_table

    # 顶层对象
    top_table = object_type + 's'  # domain → domains, sub_domain → sub_domains, service_module → service_modules
    top_alias = target_alias or top_table
    top_fk = object_type + '_id'   # 约定俗成, 与现状一致
    last_alias = _alias_of(last_table)

    join_block = ("\n" + "\n".join(join_lines[1:])) if len(join_lines) > 1 else ""
    return (
        f"EXISTS (SELECT 1 {join_lines[0]}{join_block}\n"
        f"WHERE {last_alias}.{top_fk} = {top_alias}.id\n"
        f"AND (r.source_bo_id = {start_alias}.id OR r.target_bo_id = {start_alias}.id))"
    )
