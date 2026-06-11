# -*- coding: utf-8 -*-
"""
枚举值迁移脚本

将 meta/core/models.py 中定义的枚举类型迁移到数据库表：
- enum_types: 枚举类型元数据
- enum_values: 枚举值实例数据

【重要】新增业务枚举的完整流程（三处必改）：
  1. meta/core/models.py         — 定义 Python Enum 类
  2. 本文件 ENUM_CLASSES          — 注册枚举类
  3. 本文件 ENUM_DIMENSION_CONFIG — 如有维度/中文名/英文名，在此配置
  4. 本文件 ENUM_VALUE_NAME_MAP   — 如有自定义中文名称映射，在此配置
  5. 本文件 ENUM_TYPE_ID_OVERRIDE — 如需自定义枚举类型ID（避免驼峰转下划线冲突）

启动时自动执行: dev.py → server.py → init_enum_services() → migrate_enums()
仅当三处都正确配置，枚举类型才能在「系统管理 > 枚举类型管理」页面显示。
"""

import sys
import os
import json
from datetime import datetime
from enum import Enum

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

from meta.core.models import (
    FieldType,
    ObjectType,
    FieldStorage,
    FieldSource,
    ActionType,
    ValidationSeverity,
    QueryOperator,
    AggregateType,
    RuleType,
    RuleScope,
    RuleTrigger,
    DataCategory,
    DerivationType,
    DerivationStrategy,
    AnnotationCategory,
    ArchObjectType,
    DimensionKey,
    BusinessRelationType,
    RelationCategory,
    Direction,
    HierarchyScopeType,
)
from meta.core.datasource import get_data_source


ENUM_CLASSES = [
    FieldType,
    ObjectType,
    FieldStorage,
    FieldSource,
    ActionType,
    ValidationSeverity,
    QueryOperator,
    AggregateType,
    RuleType,
    RuleScope,
    RuleTrigger,
    DataCategory,
    DerivationType,
    DerivationStrategy,
    AnnotationCategory,
    ArchObjectType,
    DimensionKey,
    BusinessRelationType,
    RelationCategory,
    Direction,
    HierarchyScopeType,
]

# 枚举类型ID覆盖映射（避免驼峰转下划线产生冲突）
# key: Enum 类名, value: 自定义 enum_type_id
ENUM_TYPE_ID_OVERRIDE = {
    'BusinessRelationType': 'relation_type',
}

# 带维度定义的枚举配置
# key: enum_type_id, value: { dimension_schema, value_dimensions, value_names }
ENUM_DIMENSION_CONFIG = {
    'relation_type': {
        'category': 'system',
        'mutability': 'extensible',
        'dimension_schema': {
            "dimensions": [
                {
                    "id": "direction",
                    "name": "操作方式",
                    "name_en": "Direction",
                    "values": ["PUSH", "PULL", "BIDIRECTIONAL"],
                    "default": "PUSH",
                    "description": "数据流向的操作方式"
                },
                {
                    "id": "dependency_strength",
                    "name": "依赖强度",
                    "name_en": "Dependency Strength",
                    "values": ["STRONG", "WEAK"],
                    "default": "STRONG",
                    "condition": "business_meaning == 'REFERENCES'",
                    "description": "依赖关系的强度级别"
                }
            ]
        },
        'value_dimensions': {
            'GENERATES': {"direction": ["PUSH", "PULL", "BIDIRECTIONAL"]},
            'UPDATES': {"direction": ["PUSH", "PULL", "BIDIRECTIONAL"]},
            'TRIGGERS': {"direction": ["PUSH", "PULL", "BIDIRECTIONAL"]},
            'REFERENCES': {"dependency_strength": ["STRONG", "WEAK"]},
        },
        'value_names': {
            'GENERATES': '生成',
            'UPDATES': '更新',
            'TRIGGERS': '触发',
            'REFERENCES': '引用',
        },
        'value_names_en': {
            'GENERATES': 'Generates',
            'UPDATES': 'Updates',
            'TRIGGERS': 'Triggers',
            'REFERENCES': 'References',
        },
        'value_descriptions': {
            'GENERATES': '源对象生成目标对象',
            'UPDATES': '源对象更新目标对象',
            'TRIGGERS': '源对象触发目标对象的业务流程',
            'REFERENCES': '源对象引用目标对象',
        },
    },
}


def get_enum_type_name(enum_class: type) -> str:
    """获取枚举类型名称（驼峰转下划线），支持 ENUM_TYPE_ID_OVERRIDE 覆盖"""
    class_name = enum_class.__name__
    if class_name in ENUM_TYPE_ID_OVERRIDE:
        return ENUM_TYPE_ID_OVERRIDE[class_name]
    result = []
    for i, char in enumerate(class_name):
        if char.isupper() and i > 0:
            result.append('_')
        result.append(char.lower())
    return ''.join(result)


def get_enum_type_display_name(enum_class: type) -> str:
    """获取枚举类型显示名称"""
    doc = enum_class.__doc__
    if doc:
        return doc.strip().split('\n')[0].strip()
    return enum_class.__name__


def check_enum_type_exists(ds, enum_type_id: str) -> bool:
    """检查枚举类型是否已存在"""
    sql = "SELECT id FROM enum_types WHERE id = ?"
    result = ds.query(sql, [enum_type_id])
    return len(result) > 0


def check_enum_value_exists(ds, enum_type_id: str, code: str) -> bool:
    """检查枚举值是否已存在"""
    sql = "SELECT id FROM enum_values WHERE enum_type_id = ? AND code = ?"
    result = ds.query(sql, [enum_type_id, code])
    return len(result) > 0


def create_enum_type(ds, enum_type_id: str, name: str, description: str = "",
                     category: str = 'system', mutability: str = 'locked',
                     dimension_schema: dict = None) -> None:
    """创建枚举类型

    [FIX 2026-06-04] updated_at 不再写入：遵循 audit_aspect 设计，
    updated_at 是 virtual 字段（从 audit_logs 实时计算），不应在表里物理存储。
    """
    now = datetime.now().isoformat()
    dimension_schema_str = json.dumps(dimension_schema, ensure_ascii=False) if dimension_schema else None
    sql = """
        INSERT INTO enum_types (id, name, category, mutability, dimension_schema, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    ds.execute(sql, [enum_type_id, name, category, mutability, dimension_schema_str, description, now])
    ds.commit()
    print(f"  [创建枚举类型] {enum_type_id}: {name} (category={category}, mutability={mutability})")


# 枚举值中文名称映射
ENUM_VALUE_NAME_MAP = {
    'annotation_category': {
        'important': '重要',
        'warning': '警告',
        'info': '信息',
        'tip': '提示',
    },
    'arch_object_type': {
        'product': '产品',
        'version': '版本',
        'domain': '领域',
        'sub_domain': '子领域',
        'service_module': '服务模块',
        'business_object': '业务对象',
        'relationship': '关系',
        'annotation': '备注',
    },
    'dimension_key': {
        'default': '默认',
        'language': '语言',
        'region': '地区',
        'country': '国家',
        'currency': '货币',
        'status': '状态',
        'priority': '优先级',
        'category': '类别',
        'type': '类型',
        'phase': '阶段',
        'channel': '渠道',
        'department': '部门',
    },
    'relation_category': {
        'data_flow': '数据流',
        'process_flow': '流程触发',
        'dependency': '依赖引用',
    },
    'relation_type': {
        'GENERATES': '生成',
        'UPDATES': '更新',
        'TRIGGERS': '触发',
        'REFERENCES': '引用',
    },
    'direction': {
        'PUSH': '推',
        'PULL': '拉',
        'BIDIRECTIONAL': '双向',
    },
    'hierarchy_scope_type': {
        'cross_domain': '跨领域',
        'same_domain_cross_subdomain': '同领域跨子领域',
        'same_subdomain_cross_module': '同子领域跨服务模块',
        'same_module': '同服务模块',
    },
}


def get_enum_value_name(enum_type_id: str, code: str, default_name: str) -> str:
    """获取枚举值显示名称，支持中文映射"""
    return ENUM_VALUE_NAME_MAP.get(enum_type_id, {}).get(code, default_name)


def create_enum_value(ds, enum_type_id: str, code: str, name: str, sort_order: int = 0,
                      name_en: str = None, dimensions: dict = None, description: str = None) -> None:
    """创建枚举值"""
    now = datetime.now().isoformat()
    display_name = get_enum_value_name(enum_type_id, code, name)
    dimensions_str = json.dumps(dimensions, ensure_ascii=False) if dimensions else None
    sql = """
        INSERT INTO enum_values
        (enum_type_id, code, name, name_en, dimensions, sort_order, is_active, is_system, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?)
    """
    # [FIX 2026-06-04] updated_at 不写入（参见 audit_aspect 的 virtual 字段设计）
    ds.execute(sql, [enum_type_id, code, display_name, name_en, dimensions_str, sort_order, now])
    ds.commit()
    print(f"    [创建枚举值] {code}: {display_name}")


def migrate_enum_class(ds, enum_class: type) -> tuple:
    """迁移单个枚举类，返回 (类型创建数, 值创建数)"""
    enum_type_id = get_enum_type_name(enum_class)
    display_name = get_enum_type_display_name(enum_class)

    dim_config = ENUM_DIMENSION_CONFIG.get(enum_type_id, {})

    # AnnotationCategory 和 DimensionKey 作为业务枚举，可编辑
    if enum_class.__name__ in ('AnnotationCategory', 'DimensionKey'):
        category = 'business'
        mutability = 'fully_editable'
    elif dim_config:
        category = dim_config.get('category', 'system')
        mutability = dim_config.get('mutability', 'locked')
    else:
        category = 'system'
        mutability = 'locked'

    type_created = 0
    value_created = 0

    dimension_schema = dim_config.get('dimension_schema')

    if not check_enum_type_exists(ds, enum_type_id):
        create_enum_type(ds, enum_type_id, display_name, display_name, category, mutability, dimension_schema)
        type_created = 1
    else:
        update_enum_type_category(ds, enum_type_id, category, mutability)
        if dim_config:
            update_enum_type_name(ds, enum_type_id, display_name)
        if dimension_schema:
            update_enum_type_dimension_schema(ds, enum_type_id, dimension_schema)
        print(f"  [枚举类型已存在] {enum_type_id}")

    members = list(enum_class)
    value_dimensions = dim_config.get('value_dimensions', {})
    value_names = dim_config.get('value_names', {})
    value_names_en = dim_config.get('value_names_en', {})
    value_descriptions = dim_config.get('value_descriptions', {})

    for idx, member in enumerate(members):
        code = member.value
        name = value_names.get(code) or member.name
        display_name = get_enum_value_name(enum_type_id, code, name)
        name_en = value_names_en.get(code)
        dimensions = value_dimensions.get(code)
        description = value_descriptions.get(code, '')

        if not check_enum_value_exists(ds, enum_type_id, code):
            create_enum_value(ds, enum_type_id, code, name, sort_order=idx,
                              name_en=name_en, dimensions=dimensions, description=description)
            value_created += 1
        else:
            update_enum_value_name(ds, enum_type_id, code, display_name)
            if dimensions:
                update_enum_value_dimensions(ds, enum_type_id, code, dimensions)
            if name_en:
                update_enum_value_name_en(ds, enum_type_id, code, name_en)
            if description:
                update_enum_value_description(ds, enum_type_id, code, description)
            print(f"    [枚举值已存在] {code}: {display_name}")

    return type_created, value_created


def update_enum_type_category(ds, enum_type_id: str, category: str, mutability: str) -> None:
    """更新枚举类型的 category 和 mutability

    [FIX 2026-06-04] 不再写 updated_at：virtual 字段由 audit_aspect 从 audit_logs 计算。
    """
    sql = """
        UPDATE enum_types SET category = ?, mutability = ?
        WHERE id = ?
    """
    ds.execute(sql, [category, mutability, enum_type_id])
    ds.commit()
    print(f"  [更新枚举类型] {enum_type_id}: category={category}, mutability={mutability}")


def update_enum_type_name(ds, enum_type_id: str, name: str) -> None:
    """更新枚举类型的显示名称（updated_at 由 audit_aspect 接管）"""
    sql = """
        UPDATE enum_types SET name = ?
        WHERE id = ?
    """
    ds.execute(sql, [name, enum_type_id])
    ds.commit()


def update_enum_value_name(ds, enum_type_id: str, code: str, name: str) -> None:
    """更新枚举值的名称（updated_at 由 audit_aspect 接管）"""
    sql = """
        UPDATE enum_values SET name = ?
        WHERE enum_type_id = ? AND code = ?
    """
    ds.execute(sql, [name, enum_type_id, code])
    ds.commit()


def update_enum_type_dimension_schema(ds, enum_type_id: str, dimension_schema: dict) -> None:
    """更新枚举类型的维度定义（updated_at 由 audit_aspect 接管）"""
    dimension_schema_str = json.dumps(dimension_schema, ensure_ascii=False)
    sql = """
        UPDATE enum_types SET dimension_schema = ?
        WHERE id = ?
    """
    ds.execute(sql, [dimension_schema_str, enum_type_id])
    ds.commit()


def update_enum_value_dimensions(ds, enum_type_id: str, code: str, dimensions: dict) -> None:
    """更新枚举值的维度值（updated_at 由 audit_aspect 接管）"""
    dimensions_str = json.dumps(dimensions, ensure_ascii=False)
    sql = """
        UPDATE enum_values SET dimensions = ?
        WHERE enum_type_id = ? AND code = ?
    """
    ds.execute(sql, [dimensions_str, enum_type_id, code])
    ds.commit()


def update_enum_value_name_en(ds, enum_type_id: str, code: str, name_en: str) -> None:
    """更新枚举值的英文名称（updated_at 由 audit_aspect 接管）"""
    sql = """
        UPDATE enum_values SET name_en = ?
        WHERE enum_type_id = ? AND code = ?
    """
    ds.execute(sql, [name_en, enum_type_id, code])
    ds.commit()


def update_enum_value_description(ds, enum_type_id: str, code: str, description: str) -> None:
    """更新枚举值的描述（占位，当前表无 description 列）"""
    pass


# 需要清理的旧枚举值（不在当前 ENUM_CLASSES 和 ENUM_DIMENSION_CONFIG 中）
_ORPHAN_ENUM_VALUES = [
    ('relation_type', 'parent_child'),
    ('relation_type', 'reference'),
    ('relation_type', 'many_to_many'),
    ('relation_type', 'composition'),
]


def cleanup_orphan_enum_values(ds) -> int:
    """清理不再属于任何枚举类的孤立枚举值，返回删除数量"""
    removed = 0
    for enum_type_id, code in _ORPHAN_ENUM_VALUES:
        ds.execute("DELETE FROM enum_values WHERE enum_type_id = ? AND code = ?",
                   [enum_type_id, code])
        ds.commit()
        removed += 1
        print(f"  [清理孤立值] {enum_type_id}.{code}")
    return removed


def migrate_enums(db_path: str = None) -> dict:
    """
    迁移所有枚举类型到数据库
    
    Args:
        db_path: 数据库路径，默认为 meta/architecture.db
        
    Returns:
        迁移统计信息
    """
    if db_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        db_path = os.path.join(project_root, 'meta', 'architecture.db')
    
    print(f"开始迁移枚举值到数据库: {db_path}")
    print("=" * 60)
    
    ds = get_data_source("sqlite", database=db_path)
    
    total_types_created = 0
    total_values_created = 0
    total_values_removed = 0
    
    for enum_class in ENUM_CLASSES:
        print(f"\n处理枚举类: {enum_class.__name__}")
        print("-" * 40)
        type_count, value_count = migrate_enum_class(ds, enum_class)
        total_types_created += type_count
        total_values_created += value_count
    
    removed = cleanup_orphan_enum_values(ds)
    total_values_removed += removed
    
    print("\n" + "=" * 60)
    print(f"迁移完成!")
    print(f"  - 枚举类型创建: {total_types_created}")
    print(f"  - 枚举值创建: {total_values_created}")
    print(f"  - 孤立枚举值清理: {total_values_removed}")
    
    return {
        "types_created": total_types_created,
        "values_created": total_values_created,
        "db_path": db_path,
    }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='迁移枚举值到数据库')
    parser.add_argument('--db', dest='db_path', help='数据库路径')
    
    args = parser.parse_args()
    migrate_enums(args.db_path)
