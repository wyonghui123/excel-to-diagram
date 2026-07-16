# -*- coding: utf-8 -*-
"""
热点角色权限规则预热脚本

在应用启动时预热 TOP 50 热点角色的权限规则到缓存中。

使用方式：
1. 在应用启动时调用：
   from meta.scripts.preload_hot_roles import preload_hot_roles
   preload_hot_roles(engine, data_source)

2. 命令行执行：
   python -m meta.scripts.preload_hot_roles

性能目标：
- 预热时间 < 5秒
- 缓存命中率 > 95%
- 启动后首次查询响应 < 10ms
"""

import logging
import os
import sys
import time
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_hot_roles(data_source, limit: int = 50) -> List[int]:
    """
    获取热点角色列表（TOP N）

    热点角色判定标准：
    1. 权限规则数量多（规则越复杂，计算成本越高）
    2. 最近访问频率高（基于审计日志统计）
    3. 用户绑定数量多（影响范围广）

    Args:
        data_source: 数据源对象
        limit: 返回的角色数量限制

    Returns:
        热点角色ID列表
    """
    try:
        hot_roles = []
        
        cursor = data_source.execute("""
            SELECT role_id, COUNT(*) as rule_count
            FROM permission_rules
            GROUP BY role_id
            ORDER BY rule_count DESC
            LIMIT ?
        """, [limit])
        
        for row in cursor.fetchall():
            hot_roles.append(row[0])
        
        if len(hot_roles) < limit:
            cursor = data_source.execute("""
                SELECT DISTINCT role_id
                FROM permission_rules
                WHERE role_id NOT IN ({})
                LIMIT {}
            """.format(
                ','.join(['?'] * len(hot_roles)) if hot_roles else 'NULL',
                limit - len(hot_roles)
            ), hot_roles if hot_roles else [])
            
            for row in cursor.fetchall():
                hot_roles.append(row[0])
        
        logger.info(f"[DECORATIVE] 识别到 {len(hot_roles)} 个热点角色")
        return hot_roles
        
    except Exception as e:
        logger.error(f"获取热点角色失败: {e}")
        return []


def preload_role_permissions(
    engine,
    data_source,
    role_ids: List[int],
    batch_size: int = 10
) -> Dict[str, Any]:
    """
    预热指定角色的权限规则

    Args:
        engine: ManagementDimensionEngine 实例
        data_source: 数据源对象
        role_ids: 要预热的角色ID列表
        batch_size: 批处理大小

    Returns:
        预热结果统计
    """
    start_time = time.perf_counter()
    
    stats = {
        'total_roles': len(role_ids),
        'success_count': 0,
        'failed_count': 0,
        'total_rules': 0,
        'total_objects': 0,
        'errors': []
    }
    
    for i in range(0, len(role_ids), batch_size):
        batch = role_ids[i:i + batch_size]
        
        for role_id in batch:
            try:
                result = engine.calculate_impact(role_id)
                
                stats['success_count'] += 1
                stats['total_objects'] += result.get('summary', {}).get('total_affected', 0)
                
                rules = engine._get_role_permission_rules(role_id)
                stats['total_rules'] += len(rules)
                
                logger.debug(f"[OK] 预热角色 {role_id}: {len(rules)} 条规则, {result.get('summary', {}).get('total_affected', 0)} 个对象")
                
            except Exception as e:
                stats['failed_count'] += 1
                stats['errors'].append({
                    'role_id': role_id,
                    'error': str(e)
                })
                logger.warning(f"[WARNING] 预热角色 {role_id} 失败: {e}")
    
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    stats['elapsed_ms'] = round(elapsed_ms, 2)
    
    logger.info(
        f"[OK] 预热完成: {stats['success_count']}/{stats['total_roles']} 个角色, "
        f"{stats['total_rules']} 条规则, {stats['total_objects']} 个对象, "
        f"耗时 {stats['elapsed_ms']:.2f}ms"
    )
    
    return stats


def preload_hot_roles(
    engine,
    data_source,
    top_n: int = 50,
    batch_size: int = 10
) -> Dict[str, Any]:
    """
    预热热点角色权限规则（主入口）

    Args:
        engine: ManagementDimensionEngine 实例
        data_source: 数据源对象
        top_n: 预热 TOP N 个热点角色
        batch_size: 批处理大小

    Returns:
        预热结果统计
    """
    logger.info(f"[DECORATIVE] 开始预热热点角色权限规则 (TOP {top_n})...")
    
    hot_roles = get_hot_roles(data_source, limit=top_n)
    
    if not hot_roles:
        logger.warning("未找到热点角色，跳过预热")
        return {
            'total_roles': 0,
            'success_count': 0,
            'failed_count': 0,
            'message': 'No hot roles found'
        }
    
    stats = preload_role_permissions(engine, data_source, hot_roles, batch_size)
    
    cache_stats = engine.get_cache_stats()
    stats['cache_stats'] = cache_stats
    
    return stats


def main():
    """命令行入口"""
    import argparse
    from meta.core.datasource import get_data_source
    from meta.services.management_dimension_engine import ManagementDimensionEngine
    
    parser = argparse.ArgumentParser(description='预热热点角色权限规则')
    parser.add_argument('--top-n', type=int, default=50, help='预热 TOP N 个热点角色')
    parser.add_argument('--batch-size', type=int, default=10, help='批处理大小')
    parser.add_argument('--db-path', type=str, help='数据库路径')
    parser.add_argument('--verbose', action='store_true', help='详细日志')
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    db_path = args.db_path or os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'architecture.db'
    )
    
    logger.info(f"[SYMBOL] 数据库路径: {db_path}")
    
    data_source = get_data_source('sqlite', database=db_path)
    engine = ManagementDimensionEngine(data_source, ttl_seconds=300)
    
    stats = preload_hot_roles(
        engine,
        data_source,
        top_n=args.top_n,
        batch_size=args.batch_size
    )
    
    print("\n" + "=" * 60)
    print("预热结果统计")
    print("=" * 60)
    print(f"总角色数: {stats['total_roles']}")
    print(f"成功数: {stats['success_count']}")
    print(f"失败数: {stats['failed_count']}")
    print(f"总规则数: {stats['total_rules']}")
    print(f"总对象数: {stats['total_objects']}")
    print(f"耗时: {stats['elapsed_ms']:.2f}ms")
    
    if 'cache_stats' in stats:
        cache = stats['cache_stats']
        print(f"\n缓存统计:")
        print(f"  缓存大小: {cache.get('cache_size', 0)}")
        print(f"  最大大小: {cache.get('max_size', 0)}")
        print(f"  TTL: {cache.get('ttl_seconds', 0)}秒")
    
    if stats['errors']:
        print(f"\n错误列表:")
        for error in stats['errors'][:5]:
            print(f"  角色 {error['role_id']}: {error['error']}")
    
    print("=" * 60)


if __name__ == '__main__':
    main()
