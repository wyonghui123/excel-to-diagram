# -*- coding: utf-8 -*-
"""
[MODULE] chain_owner_resolver — 业务层级链 owner 解析 (v1.1.5)
[DESCRIPTION] 提供共享方法, 沿 HIERARCHY_CHAIN 向上追溯 product.owner_id.
              复用于:
              - DataPermissionInterceptor._add_owner_exception (读路径 owner 例外)
              - WriteScopeInterceptor._check_owner_chain (写路径 owner chain)

[背景 v1.1 owner refactor]
  - product 顶层有 owner_id 字段 (顶层 BO)
  - version/domain/sub_domain 顶层没有 owner_id 字段 (顶层 owner 在 product)
  - 之前两拦截器各自重复写 chain 追溯逻辑, 易出错
  - v1.1.5 提取到共享模块, 统一 SQL + 测试

[设计原则]
  - 单次 SQL JOIN 查 product.owner_id (避免 N+1)
  - BO 不在 HIERARCHY_CHAIN 时返回 None (caller 决定 fallback, e.g. created_by)
  - 纯函数 + 显式 data_source 注入, 便于测试 mock

[性能]
  - 1 次 SQL/次 (相比 N+1 节省 ~3 次)
  - 缓存: 留给 caller (per-request g 缓存)
"""
import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# [v1.1.5] 共享 HIERARCHY_CHAIN (从 dimension_scope_engine 复制定义, 避免循环 import)
# 链顺序: product → version → domain → sub_domain (顶层到底层)
HIERARCHY_CHAIN = ['product', 'version', 'domain', 'sub_domain']

# 子 BO 沿 chain 向上每步走的 FK 字段
PARENT_FIELD_MAP = {
    'version': 'product_id',
    'domain': 'version_id',
    'sub_domain': 'domain_id',
}

# BO -> DB 表名
RESOURCE_TABLE_MAP = {
    'product': 'products',
    'version': 'versions',
    'domain': 'domains',
    'sub_domain': 'sub_domains',
}


def is_in_chain(object_type: str) -> bool:
    """[v1.1.5] 检查 BO 是否在 HIERARCHY_CHAIN 中"""
    return object_type in HIERARCHY_CHAIN


def resolve_root_owner(
    data_source, object_type: str, record_id: int
) -> Optional[int]:
    """[v1.1.5] 沿 HIERARCHY_CHAIN 查 product.owner_id

    策略:
    - product: 直接返回 product.owner_id
    - version/domain/sub_domain: 沿 chain 向上 LEFT JOIN 查 product.owner_id
    - 其他 BO (e.g. relationship): 返回 None (caller 决定 fallback)

    Args:
        data_source: DB 数据源 (有 .execute(sql, params) 方法)
        object_type: BO 名 (e.g. 'version', 'domain')
        record_id: 记录 ID

    Returns:
        product.owner_id (int) 或 None (无 product 父链)

    性能: 单次 SQL JOIN, 避免 N+1
    """
    if not record_id or not object_type:
        return None

    # product: 直接查
    if object_type == 'product':
        try:
            row = data_source.execute(
                "SELECT owner_id FROM products WHERE id = ? LIMIT 1",
                [record_id]
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.debug(f'resolve_root_owner (product) failed: {e}')
            return None

    # 不在 chain 的 BO: 返回 None
    if not is_in_chain(object_type):
        return None

    # version/domain/sub_domain: 沿 chain 向上 SQL JOIN
    try:
        if object_type == 'version':
            sql = (
                "SELECT p.owner_id FROM products p "
                "WHERE p.id = (SELECT v.product_id FROM versions v WHERE v.id = ?)"
            )
        elif object_type == 'domain':
            sql = (
                "SELECT p.owner_id FROM products p "
                "JOIN versions v ON v.id = ("
                "  SELECT d.version_id FROM domains d WHERE d.id = ?"
                ") "
                "WHERE p.id = v.product_id"
            )
        elif object_type == 'sub_domain':
            sql = (
                "SELECT p.owner_id FROM products p "
                "JOIN versions v ON v.id = ("
                "  SELECT d.version_id FROM domains d "
                "  WHERE d.id = ("
                "    SELECT sd.domain_id FROM sub_domains sd WHERE sd.id = ?"
                "  )"
                ") "
                "WHERE p.id = v.product_id"
            )
        else:
            return None
        row = data_source.execute(sql, [record_id]).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.debug(f'resolve_root_owner ({object_type}) failed: {e}')
        return None


def resolve_root_product_id(
    data_source, object_type: str, record_id: int
) -> Optional[int]:
    """[v1.1.5] 沿 HIERARCHY_CHAIN 查 product.id (用于 chain_root 报告)

    Args:
        data_source: DB 数据源
        object_type: BO 名
        record_id: 记录 ID

    Returns:
        product.id (int) 或 None
    """
    if not record_id or not object_type:
        return None

    if object_type == 'product':
        return record_id

    if not is_in_chain(object_type):
        return None

    try:
        if object_type == 'version':
            sql = "SELECT product_id FROM versions WHERE id = ?"
        elif object_type == 'domain':
            sql = (
                "SELECT v.product_id FROM domains d "
                "JOIN versions v ON v.id = d.version_id WHERE d.id = ?"
            )
        elif object_type == 'sub_domain':
            sql = (
                "SELECT v.product_id FROM sub_domains sd "
                "JOIN domains d ON d.id = sd.domain_id "
                "JOIN versions v ON v.id = d.version_id WHERE sd.id = ?"
            )
        else:
            return None
        row = data_source.execute(sql, [record_id]).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.debug(f'resolve_root_product_id ({object_type}) failed: {e}')
        return None


def build_owner_exception_subquery(
    data_source, object_type: str, user_id: int
) -> Optional[str]:
    """[v1.1.5] 构造 owner 例外的 SQL 子查询 (纯子查询, 不带 id IN 前缀)

    用途: 配合 persistence_interceptor 的 in_subquery operator
        QueryCondition: {'field': 'id', 'operator': 'in_subquery', 'value': <本函数返回值>}
        渲染后: id IN (<本函数返回值>)

    Args:
        data_source: DB 数据源
        object_type: BO 名 (version/domain/sub_domain/product)
        user_id: 当前用户 ID

    Returns:
        SQL 表达式字符串 (纯子查询, 不含 id IN 前缀), 或 None

    例 (注意: value 是纯子查询, 不要带 id IN 前缀):
        version: 'SELECT id FROM versions WHERE product_id IN (SELECT id FROM products WHERE owner_id = 333)'
        domain: 'SELECT id FROM domains WHERE version_id IN (SELECT id FROM versions WHERE product_id IN (SELECT id FROM products WHERE owner_id = 333))'
        sub_domain: 'SELECT id FROM sub_domains WHERE domain_id IN (SELECT id FROM domains WHERE version_id IN (SELECT id FROM versions WHERE product_id IN (SELECT id FROM products WHERE owner_id = 333)))'

    [v1.1.5 BUG FIX 2026-06-15] 之前版本 value 含 'id IN (...)' 前缀, persistence 渲染时
    会拼成 'id IN (id IN (...))' 嵌套 IN, SQL 语法错误, 导致 owner exception 失效.
    """
    if not user_id or not object_type:
        return None

    if not is_in_chain(object_type):
        return None

    # owner 子查询: SELECT id FROM products WHERE owner_id = $user
    user_owned_products = (
        f"SELECT id FROM products WHERE owner_id = {int(user_id)}"
    )

    # 沿 chain 从 object_type 走到 product, 累加嵌套子查询
    if object_type == 'product':
        # 直接返回 owner 子查询
        return user_owned_products

    if object_type == 'version':
        return (
            f"SELECT id FROM versions "
            f"WHERE product_id IN ({user_owned_products})"
        )

    if object_type == 'domain':
        return (
            f"SELECT id FROM domains "
            f"WHERE version_id IN ("
            f"  SELECT id FROM versions "
            f"  WHERE product_id IN ({user_owned_products})"
            f")"
        )

    if object_type == 'sub_domain':
        return (
            f"SELECT id FROM sub_domains "
            f"WHERE domain_id IN ("
            f"  SELECT id FROM domains "
            f"  WHERE version_id IN ("
            f"    SELECT id FROM versions "
            f"    WHERE product_id IN ({user_owned_products})"
            f"  )"
            f")"
        )

    return None
