# -*- coding: utf-8 -*-
"""
性能优化索引迁移脚本

为权限系统添加必要的数据库索引，优化查询性能。

索引策略：
1. 单列索引：高频查询字段
2. 复合索引：多字段联合查询
3. 部分索引：条件过滤场景

性能目标：
- 权限规则查询 < 10ms
- 影响范围计算 < 100ms
- 维度实例查询 < 50ms
"""

import logging
import sqlite3
import time
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


INDEX_DEFINITIONS = [
    {
        'name': 'idx_permission_rules_role_id',
        'table': 'permission_rules',
        'columns': ['role_id'],
        'type': 'btree',
        'description': '角色ID索引，加速按角色查询权限规则',
        'priority': 'high'
    },
    {
        'name': 'idx_permission_rules_resource_type',
        'table': 'permission_rules',
        'columns': ['resource_type'],
        'type': 'btree',
        'description': '资源类型索引，加速按维度查询权限规则',
        'priority': 'high'
    },
    {
        'name': 'idx_permission_rules_role_resource',
        'table': 'permission_rules',
        'columns': ['role_id', 'resource_type'],
        'type': 'btree',
        'description': '角色+资源类型复合索引，加速联合查询',
        'priority': 'high'
    },
    {
        'name': 'idx_permission_rules_is_denied',
        'table': 'permission_rules',
        'columns': ['is_denied'],
        'type': 'btree',
        'description': '拒绝标志索引，加速权限判断',
        'priority': 'medium'
    },
    {
        'name': 'idx_permission_rules_created_at',
        'table': 'permission_rules',
        'columns': ['created_at'],
        'type': 'btree',
        'description': '创建时间索引，支持时间范围查询',
        'priority': 'low'
    },
    {
        'name': 'idx_domains_code',
        'table': 'domains',
        'columns': ['code'],
        'type': 'btree',
        'description': '领域编码索引，加速编码查询',
        'priority': 'high'
    },
    {
        'name': 'idx_domains_version_id',
        'table': 'domains',
        'columns': ['version_id'],
        'type': 'btree',
        'description': '版本ID索引，加速层级查询',
        'priority': 'high'
    },
    {
        'name': 'idx_sub_domains_domain_id',
        'table': 'sub_domains',
        'columns': ['domain_id'],
        'type': 'btree',
        'description': '领域ID索引，加速子领域查询',
        'priority': 'high'
    },
    {
        'name': 'idx_sub_domains_code',
        'table': 'sub_domains',
        'columns': ['code'],
        'type': 'btree',
        'description': '子领域编码索引',
        'priority': 'high'
    },
    {
        'name': 'idx_service_modules_sub_domain_id',
        'table': 'service_modules',
        'columns': ['sub_domain_id'],
        'type': 'btree',
        'description': '子领域ID索引，加速服务模块查询',
        'priority': 'high'
    },
    {
        'name': 'idx_service_modules_code',
        'table': 'service_modules',
        'columns': ['code'],
        'type': 'btree',
        'description': '服务模块编码索引',
        'priority': 'high'
    },
    {
        'name': 'idx_business_objects_service_module_id',
        'table': 'business_objects',
        'columns': ['service_module_id'],
        'type': 'btree',
        'description': '服务模块ID索引，加速业务对象查询',
        'priority': 'high'
    },
    {
        'name': 'idx_business_objects_code',
        'table': 'business_objects',
        'columns': ['code'],
        'type': 'btree',
        'description': '业务对象编码索引',
        'priority': 'high'
    },
]


def check_index_exists(cursor, index_name: str) -> bool:
    """检查索引是否存在"""
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='index' AND name=?
    """, [index_name])
    return cursor.fetchone() is not None


def create_index(cursor, index_def: Dict[str, Any]) -> bool:
    """
    创建索引

    Args:
        cursor: 数据库游标
        index_def: 索引定义

    Returns:
        是否创建成功
    """
    index_name = index_def['name']
    table_name = index_def['table']
    columns = index_def['columns']

    if check_index_exists(cursor, index_name):
        logger.info(f"  ⏭️  索引已存在: {index_name}")
        return False

    try:
        columns_str = ', '.join(columns)
        sql = f"CREATE INDEX {index_name} ON {table_name}({columns_str})"

        start_time = time.perf_counter()
        cursor.execute(sql)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(f"  ✅ 创建索引: {index_name} ({elapsed_ms:.2f}ms)")
        return True

    except Exception as e:
        logger.error(f"  ❌ 创建索引失败 {index_name}: {e}")
        return False


def analyze_query_performance(cursor, table_name: str) -> Dict[str, Any]:
    """
    分析表的查询性能

    Args:
        cursor: 数据库游标
        table_name: 表名

    Returns:
        性能分析结果
    """
    try:
        cursor.execute(f"ANALYZE {table_name}")

        cursor.execute(f"""
            SELECT name, sql FROM sqlite_master
            WHERE type='index' AND tbl_name=?
        """, [table_name])

        indexes = cursor.fetchall()

        cursor.execute(f"PRAGMA index_list({table_name})")
        index_list = cursor.fetchall()

        return {
            'table': table_name,
            'index_count': len(indexes),
            'indexes': [idx[0] for idx in indexes],
            'index_list': index_list
        }

    except Exception as e:
        logger.error(f"分析表性能失败 {table_name}: {e}")
        return {'table': table_name, 'error': str(e)}


def run_migration(db_path: str) -> Dict[str, Any]:
    """
    执行索引迁移

    Args:
        db_path: 数据库文件路径

    Returns:
        迁移结果统计
    """
    logger.info(f"🚀 开始执行索引迁移: {db_path}")

    stats = {
        'total_indexes': len(INDEX_DEFINITIONS),
        'created_count': 0,
        'skipped_count': 0,
        'failed_count': 0,
        'details': []
    }

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        logger.info("\n📋 创建索引:")
        for index_def in INDEX_DEFINITIONS:
            logger.info(f"\n  [{index_def['priority'].upper()}] {index_def['name']}")
            logger.info(f"    表: {index_def['table']}, 列: {', '.join(index_def['columns'])}")
            logger.info(f"    说明: {index_def['description']}")

            result = create_index(cursor, index_def)

            if result:
                stats['created_count'] += 1
            elif check_index_exists(cursor, index_def['name']):
                stats['skipped_count'] += 1
            else:
                stats['failed_count'] += 1

            stats['details'].append({
                'name': index_def['name'],
                'table': index_def['table'],
                'created': result,
                'priority': index_def['priority']
            })

        conn.commit()

        logger.info("\n📊 分析查询性能:")
        tables = ['permission_rules', 'domains', 'sub_domains', 'service_modules', 'business_objects']
        for table in tables:
            perf = analyze_query_performance(cursor, table)
            if 'error' not in perf:
                logger.info(f"  ✅ {table}: {perf['index_count']} 个索引")
            stats[f'{table}_analysis'] = perf

        conn.close()

        logger.info("\n" + "=" * 60)
        logger.info("迁移结果统计")
        logger.info("=" * 60)
        logger.info(f"总索引数: {stats['total_indexes']}")
        logger.info(f"创建成功: {stats['created_count']}")
        logger.info(f"已存在跳过: {stats['skipped_count']}")
        logger.info(f"创建失败: {stats['failed_count']}")
        logger.info("=" * 60)

        return stats

    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        stats['error'] = str(e)
        return stats


def verify_indexes(db_path: str) -> bool:
    """
    验证索引是否正确创建

    Args:
        db_path: 数据库文件路径

    Returns:
        验证是否通过
    """
    logger.info(f"\n🔍 验证索引: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        all_passed = True

        for index_def in INDEX_DEFINITIONS:
            exists = check_index_exists(cursor, index_def['name'])

            if exists:
                logger.info(f"  ✅ {index_def['name']}")
            else:
                logger.warning(f"  ❌ {index_def['name']} 不存在")
                all_passed = False

        conn.close()

        if all_passed:
            logger.info("\n✅ 所有索引验证通过")
        else:
            logger.warning("\n⚠️ 部分索引验证失败")

        return all_passed

    except Exception as e:
        logger.error(f"❌ 验证失败: {e}")
        return False


def main():
    """命令行入口"""
    import argparse
    import os

    parser = argparse.ArgumentParser(description='性能优化索引迁移')
    parser.add_argument('--db-path', type=str, help='数据库路径')
    parser.add_argument('--verify', action='store_true', help='仅验证索引')
    parser.add_argument('--verbose', action='store_true', help='详细日志')

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(message)s'
    )

    db_path = args.db_path or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'architecture.db'
    )

    if not os.path.exists(db_path):
        logger.error(f"❌ 数据库文件不存在: {db_path}")
        return

    if args.verify:
        verify_indexes(db_path)
    else:
        stats = run_migration(db_path)

        if stats.get('failed_count', 0) > 0:
            logger.warning("\n⚠️ 部分索引创建失败，请检查日志")
        else:
            logger.info("\n✅ 索引迁移完成")


if __name__ == '__main__':
    main()
