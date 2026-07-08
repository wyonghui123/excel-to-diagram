#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BO 分类体系数据库迁移脚本

为 business_objects 表添加 BO 分类支持字段，
并基于启发式规则自动推断现有 BO 的分类。
"""

import sys
import os
import logging
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from meta.core.models import BusinessObjectCategory, BoSubCategory

logger = logging.getLogger(__name__)


def get_data_source():
    """获取数据源连接"""
    # 复用现有的数据源获取逻辑
    try:
        from meta.api.manage_api import _get_data_source
        return _get_data_source()
    except Exception as e:
        logger.error(f"无法获取数据源: {e}")
        raise


def migrate_bo_category_columns(ds):
    """
    Step 1: 添加新列

    为 business_objects 表添加：
    - bo_category VARCHAR(20) DEFAULT 'master_data'
    - bo_sub_category VARCHAR(30)
    - category_config TEXT (JSON格式存储)
    """
    logger.info("=== Step 1: 添加 BO 分类列 ===")

    migrations = [
        """
        ALTER TABLE business_objects
        ADD COLUMN IF NOT EXISTS bo_category VARCHAR(20) DEFAULT 'master_data'
        """,
        """
        ALTER TABLE business_objects
        ADD COLUMN IF NOT EXISTS bo_sub_category VARCHAR(30)
        """,
        """
        ALTER TABLE business_objects
        ADD COLUMN IF NOT EXISTS category_config TEXT
        """,
    ]

    for sql in migrations:
        try:
            ds.execute(sql)
            logger.info(f"[OK] 执行成功: {sql.strip()[:50]}...")
        except Exception as e:
            logger.warning(f"[WARNING] 执行失败（可能已存在）: {e}")


def infer_bo_categories_heuristic(ds):
    """
    Step 2: 启发式推断现有 BO 的分类

    基于名称关键词自动推断 BO 类型：
    - 事务型：包含 订单/发票/审批/单据/流程 等关键词
    - 分析型：包含 统计/报表/分析/KPI/聚合 等关键词
    - 配置型：包含 枚举/参数/配置/类型定义 等关键词
    - 主数据型：其他所有情况（默认）
    """
    logger.info("=== Step 2: 启发式推断 BO 分类 ===")

    # 定义启发式规则
    transactional_keywords = ['订单', 'invoice', '审批', '单据', '流程', 'order', 'approval', 'process']
    analytical_keywords = ['统计', '报表', '分析', 'KPI', '聚合', 'analytic', 'report', 'statistics', 'dashboard']
    configuration_keywords = ['枚举', '参数', '配置', 'enum', 'parameter', 'config', '类型定义', 'type_def']

    # 读取所有需要更新的记录
    ds.execute("""
        SELECT id, name FROM business_objects
        WHERE bo_category IS NULL OR bo_category = 'master_data' OR bo_category = ''
    """)
    rows = ds.fetchall()

    updated_count = 0

    for row in rows:
        bo_id, bo_name = row[0], row[1] or ""

        # 推断分类
        bo_name_lower = bo_name.lower()

        if any(kw in bo_name or kw.lower() in bo_name_lower for kw in transactional_keywords):
            category = 'transactional'
            sub_category = infer_sub_category(bo_name, 'transactional')
        elif any(kw in bo_name or kw.lower() in bo_name_lower for kw in analytical_keywords):
            category = 'analytical'
            sub_category = infer_sub_category(bo_name, 'analytical')
        elif any(kw in bo_name or kw.lower() in bo_name_lower for kw in configuration_keywords):
            category = 'configuration'
            sub_category = infer_sub_category(bo_name, 'configuration')
        else:
            category = 'master_data'  # 默认
            sub_category = infer_sub_category(bo_name, 'master_data')

        # 更新记录
        try:
            ds.execute(
                "UPDATE business_objects SET bo_category=?, bo_sub_category=? WHERE id=?",
                (category, sub_category, bo_id)
            )
            updated_count += 1

            if updated_count <= 10:  # 只打印前10条日志避免刷屏
                logger.info(f"  [DECORATIVE] [{bo_id}] '{bo_name}' → {category}/{sub_category}")

        except Exception as e:
            logger.warning(f"[WARNING] 更新失败 [{bo_id}]: {e}")

    logger.info(f"\n[OK] 共更新 {updated_count} 条 BO 记录")


def infer_sub_category(name: str, category: str) -> str:
    """推断子类别"""
    name_lower = name.lower()

    if category == 'transactional':
        if any(k in name for k in ['订单', 'order', '发票', 'invoice']):
            return 'document'
        elif any(k in name for k in ['流程', 'process', '审批', 'approval']):
            return 'process_instance'
        elif any(k in name for k in ['日志', 'log', '事件', 'event']):
            return 'event_log'
        elif any(k in name for k in ['临时', 'temp', '中间', 'intermediate']):
            return 'temporary'
        return 'document'  # 默认

    elif category == 'master_data':
        if any(k in name for k in ['客户', 'customer', '供应商', 'supplier', '用户', 'user', '员工', 'employee']):
            return 'party'
        elif any(k in name for k in ['产品', 'product', '物料', 'material', 'SKU']):
            return 'product'
        elif any(k in name for k in ['组织', 'org', '部门', 'department', '成本中心', 'cost']):
            return 'organization'
        elif any(k in name for k in ['资产', 'asset', '设备', 'equipment', '固定资产']):
            return 'asset'
        return 'party'  # 默认

    elif category == 'analytical':
        if any(k in name for k in ['事实', 'fact', '明细', 'detail']):
            return 'fact_table'
        elif any(k in name for k in ['维度', 'dimension', '时间', 'time', '地理', 'geo']):
            return 'dimension_table'
        elif any(k in name for k in ['聚合', 'aggregate', '汇总', 'summary', '统计', 'statistic']):
            return 'aggregate'
        elif any(k in name for k in ['KPI', '仪表盘', 'dashboard', '指标']):
            return 'kpi_dashboard'
        return 'fact_table'  # 默认

    elif category == 'configuration':
        if any(k in name for k in ['枚举', 'enum', 'enumeration']):
            return 'enumeration'
        elif any(k in name for k in ['参数', 'param', 'parameter']):
            return 'parameter'
        elif any(k in name for k in ['对照', 'lookup', '币种', 'currency', '单位', 'unit']):
            return 'lookup'
        elif any(k in name for k in ['定制', 'customizing', '客户化', '单据类型', 'doc_type']):
            return 'customizing'
        return 'enumeration'  # 默认

    return None


def create_indexes(ds):
    """Step 3: 创建索引"""
    logger.info("\n=== Step 3: 创建索引 ===")

    index_sqls = [
        "CREATE INDEX IF NOT EXISTS idx_business_objects_bo_category ON business_objects(bo_category)",
        "CREATE INDEX IF NOT EXISTS idx_business_objects_bo_sub_category ON business_objects(bo_sub_category)",
    ]

    for sql in index_sqls:
        try:
            ds.execute(sql)
            logger.info(f"[OK] 创建索引成功")
        except Exception as e:
            logger.warning(f"[WARNING] 创建索引失败（可能已存在）: {e}")


def verify_migration(ds):
    """Step 4: 验证迁移结果"""
    logger.info("\n=== Step 4: 验证迁移结果 ===")

    # 检查列是否存在
    ds.execute("PRAGMA table_info(business_objects)")
    columns = [col[1] for col in ds.fetchall()]

    required_cols = ['bo_category', 'bo_sub_category', 'category_config']
    missing_cols = [col for col in required_cols if col not in columns]

    if missing_cols:
        logger.error(f"[X] 缺少必要的列: {missing_cols}")
        return False

    logger.info(f"[OK] 所有必需的列都已存在: {required_cols}")

    # 统计各分类的数量
    ds.execute("""
        SELECT bo_category, COUNT(*) as count
        FROM business_objects
        GROUP BY bo_category
        ORDER BY count DESC
    """)
    results = ds.fetchall()

    logger.info("\n[DECORATIVE] BO 分类统计:")
    total = 0
    for row in results:
        category, count = row[0] or '(空)', row[1]
        total += count
        logger.info(f"  • {category}: {count} 个BO")

    logger.info(f"\n  总计: {total} 个BO")

    return True


def main():
    """主函数"""
    print("\n" + "="*60)
    print("[DECORATIVE] BO 分类体系数据库迁移工具")
    print("="*60)
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S'
    )

    try:
        # 获取数据源
        ds = get_data_source()
        logger.info("[OK] 数据库连接成功\n")

        # Step 1: 添加列
        migrate_bo_category_columns(ds)

        # Step 2: 启发式推断
        infer_bo_categories_heuristic(ds)

        # Step 3: 创建索引
        create_indexes(ds)

        # Step 4: 验证
        success = verify_migration(ds)

        print("\n" + "="*60)
        if success:
            print("[OK] 迁移完成！所有步骤执行成功。")
        else:
            print("[WARNING] 迁移完成但验证发现问题，请检查上方日志。")
        print("="*60)
        print(f"⏱️  结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

        return 0 if success else 1

    except Exception as e:
        logger.error(f"[X] 迁移失败: {e}", exc_info=True)
        return 1


if __name__ == '__main__':
    exit(main())
