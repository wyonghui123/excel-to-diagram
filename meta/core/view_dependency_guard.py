# -*- coding: utf-8 -*-
"""视图依赖守卫

【问题】
SQLite 的 CREATE VIEW 是延迟解析：建视图时不校验被引用表，只有 SELECT 时才抛
`OperationalError: no such table: main.<表名>`。当某个部署的库里缺这些表时
（典型：BIP 应用架构管理部署把 org 托管在别库，本库只跑本仓库的非 org 迁移），
面对象的读写路径会在运行期 500，而不是启动期暴露。

【做法】
启动期一次性探测视图依赖的物理表，缺任意一张就把该视图从元数据注册表摘除。
摘除后请求按「对象不存在」处理（BO 层 Unknown object type / UI 配置 404），
得到确定的 4xx，而不是运行期 500。

【影响面】
正常部署（依赖表齐备）零动作：不改对象、不打日志。
"""
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: 视图 id → 依赖的物理表。新增依赖外部表的视图时在此登记。
VIEW_DEPENDENCIES: Dict[str, Tuple[str, ...]] = {
    # 谓词: parties.source='org' AND EXISTS(org_functions 具备 BU/LE 职能)
    'party_internal': ('parties', 'orgs', 'org_functions'),
    # 谓词: EXISTS(org_functions 具备 legal_entity 职能)
    'org_legal_entity': ('orgs', 'org_functions'),
}


def _table_exists(data_source, table_name: str) -> bool:
    """表存在性检查（不经由 ds.table_exists 的白名单校验）。

    org_functions 是直建表、未在 YAML schema 登记，走 SqliteAdapter.table_exists
    会抛 ValueError: Invalid table name。故优先查 sqlite_master；非 SQLite 适配器
    不支持该查询时降级回适配器方法。
    """
    try:
        cursor = data_source.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view') "
            "AND name = ?",
            (table_name,),
        )
        return cursor.fetchone() is not None
    except Exception as e:
        logger.debug(f"[ViewDependencyGuard] sqlite_master 检查失败 {table_name}: {e}")
    try:
        return bool(data_source.table_exists(table_name))
    except Exception as e:
        logger.debug(f"[ViewDependencyGuard] 表存在性检查失败 {table_name}: {e}")
        return False


def prune_unusable_views(data_source, reg=None) -> List[str]:
    """摘除依赖表缺失的视图对象。

    Args:
        data_source: 数据源适配器（需支持 execute / table_exists）
        reg: 元数据注册表，缺省用全局 registry

    Returns:
        被摘除的视图 id 列表（正常部署为空列表）
    """
    if data_source is None:
        return []

    if reg is None:
        from meta.core.models import registry as reg

    pruned: List[str] = []
    for view_id, dependencies in VIEW_DEPENDENCIES.items():
        if reg.get(view_id) is None:
            continue
        missing = [t for t in dependencies if not _table_exists(data_source, t)]
        if not missing:
            continue
        reg.unregister(view_id)
        pruned.append(view_id)
        logger.warning(
            "[ViewDependencyGuard] 视图 %s 的依赖表缺失 %s，已从元数据注册表摘除"
            "（该部署下按对象不存在处理，相关接口返回 4xx）",
            view_id, missing,
        )
    return pruned
