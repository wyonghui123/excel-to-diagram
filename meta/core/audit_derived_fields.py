# -*- coding: utf-8 -*-
"""
Audit-Derived Virtual Fields — SSOT 单一事实实现

【背景 2026-06-05】
v1.4 updated_at 统一规则：所有 object 的 `updated_at` 是**计算字段**，
不存储在业务表中，从 audit_logs 表实时派生。

【V007.51 Phase 2 更新 2026-07-14】
v2.0 物化列优先：有物化 updated_at 列的表直接从列读取，
无物化列的表仍走 v_audit_all 实时派生。

历史：项目内有 2 份重复实现：
  - meta.services.query_service.QueryService._enrich_audit_virtual_fields
  - meta.core.interceptors.persistence_interceptor.PersistenceInterceptor._enrich_audit_virtual_fields

v1.4 抽取为 SSOT helper，未来 2 处实现应改为调用本模块。

派生规则（SSOT）：
  1. 优先从物化列读取（V007.51 新增，零 SQL 开销）
  2. 只查询 action='UPDATE' 的审计日志
  3. 取每个 object_id 的 MAX(created_at_epoch) | MAX(created_at)
  4. 没有 UPDATE 记录时，fallback 为该 record 自己的 created_at
  5. 测试环境优雅降级（audit_logs 表缺失时直接 fallback）
"""
import logging
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


# 派生 SQL（不带 WHERE/IN 列表，由调用方拼接）
# [V007.50] 改用 v_audit_all VIEW，覆盖已归档到 audit_logs_archive 的记录
_AUDIT_DERIVE_SELECT_SQL = (
    "SELECT object_id, MAX(created_at_epoch) as max_epoch, MAX(created_at) as max_iso "
    "FROM v_audit_all "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)

# Fallback SQL（测试环境 audit_logs 缺少 created_at_epoch 列时）
_AUDIT_DERIVE_SELECT_SQL_FALLBACK = (
    "SELECT object_id, NULL as max_epoch, MAX(created_at) as max_iso "
    "FROM v_audit_all "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)

# [V007.50] v_audit_all VIEW 不存在时的兜底 SQL (查热表 audit_logs)
# 仅在异常路径使用：测试环境未运行迁移 / 旧版部署未升级
_AUDIT_DERIVE_SELECT_SQL_NO_VIEW = (
    "SELECT object_id, MAX(created_at_epoch) as max_epoch, MAX(created_at) as max_iso "
    "FROM audit_logs "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)
_AUDIT_DERIVE_SELECT_SQL_NO_VIEW_FALLBACK = (
    "SELECT object_id, NULL as max_epoch, MAX(created_at) as max_iso "
    "FROM audit_logs "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)


def _execute_audit_query(ds, object_type: str, object_ids: List[str], use_fallback: bool = False):
    """执行 audit_logs 派生查询

    Args:
        ds: data source
        object_type: 对象类型（如 'user_group'）
        object_ids: 对象 ID 列表（字符串）
        use_fallback: True 时使用不带 created_at_epoch 的 SQL

    Returns:
        cursor（调用方负责 fetchall）

    [V007.50] v_audit_all VIEW 不存在时自动回退到 audit_logs (热表)
    """
    if not object_ids:
        return None
    placeholders = ','.join(['?' for _ in object_ids])
    sql = _AUDIT_DERIVE_SELECT_SQL_FALLBACK if use_fallback else _AUDIT_DERIVE_SELECT_SQL
    sql = sql.format(placeholders=placeholders)
    try:
        if hasattr(ds, 'query'):
            return ds.query(sql, [object_type] + object_ids)
        else:
            return ds.execute(sql, [object_type] + object_ids)
    except Exception as e:
        err_msg = str(e).lower()
        if "no such table: v_audit_all" in err_msg:
            # VIEW 不存在，回退到 audit_logs (热表)
            logger.warning(
                "[audit_derived_fields] v_audit_all not found, fallback to audit_logs"
            )
            fallback_sql = (
                _AUDIT_DERIVE_SELECT_SQL_NO_VIEW_FALLBACK
                if use_fallback
                else _AUDIT_DERIVE_SELECT_SQL_NO_VIEW
            )
            fallback_sql = fallback_sql.format(placeholders=placeholders)
            try:
                if hasattr(ds, 'query'):
                    return ds.query(fallback_sql, [object_type] + object_ids)
                else:
                    return ds.execute(fallback_sql, [object_type] + object_ids)
            except Exception as e2:
                logger.warning(
                    "[audit_derived_fields] Fallback to audit_logs also failed: %s", e2
                )
                return None
        logger.warning("[audit_derived_fields] Query failed (object_type=%s): %s", object_type, e)
        return None


def _normalize_rows(rows) -> Dict[str, str]:
    """归一化查询结果为 {object_id: iso_string} 字典

    支持 dict-like rows（ds.query 返回）和 tuple-like rows（ds.execute 返回）
    """
    result_map: Dict[str, str] = {}
    if not rows:
        return result_map

    for row in rows:
        if isinstance(row, dict):
            oid = str(row.get('object_id'))
            epoch_val = row.get('max_epoch')
            iso_val = row.get('max_iso')
        else:
            oid = str(row[0])
            epoch_val = row[1] if len(row) > 1 else None
            iso_val = row[2] if len(row) > 2 else None

        if epoch_val is not None:
            try:
                dt = datetime.fromtimestamp(epoch_val / 1000.0)
                result_map[oid] = dt.isoformat()
            except (TypeError, ValueError, OSError):
                # 无效 epoch 值，fallback 到 ISO
                if iso_val is not None:
                    result_map[oid] = iso_val
        elif iso_val is not None:
            result_map[oid] = iso_val
        # else: 该记录没有 UPDATE 审计，不加入 result_map

    return result_map


def _get_audit_field_value(ds, object_type: str, object_id: str) -> Optional[str]:
    """获取单个 object 的派生 updated_at 值

    内部使用 _execute_audit_query + _normalize_rows
    """
    cursor = _execute_audit_query(ds, object_type, [object_id])
    if cursor is None:
        return None

    # 尝试 fetchall
    try:
        rows = cursor.fetchall() if hasattr(cursor, 'fetchall') else cursor
    except Exception:
        rows = cursor

    result_map = _normalize_rows(rows)
    return result_map.get(object_id)


def _object_type_to_table_name(object_type: str) -> str:
    """[V007.52] object_type -> table_name 反查（SSOT）"""
    try:
        from meta.core.materialization_registry import get_registry
        entry = get_registry().get_by_object_type(object_type)
        if entry:
            return entry['name']
    except Exception:
        pass
    _fallback_map = {
        'enum_type': 'enum_types',
        'enum_value': 'enum_values',
        'user': 'users',
        'role': 'roles',
        'user_group': 'user_groups',
        'product': 'products',
        'version': 'versions',
        'domain': 'domains',
    }
    return _fallback_map.get(object_type, object_type + 's')


def enrich_audit_virtual_fields(
    ds,
    object_type: str,
    records: List[Dict[str, Any]],
    field_ids: Optional[Iterable[str]] = None,
) -> List[Dict[str, Any]]:
    """SSOT: 批量为 records 注入派生 virtual 字段（如 updated_at）

    [V007.51 Phase 2] 物化列优先策略：
      1. 如果 record 已有 'updated_at' 字段（来自物化列），直接使用
      2. 否则走 v_audit_all 实时派生

    用法：
        from meta.core.audit_derived_fields import enrich_audit_virtual_fields

        records = enrich_audit_virtual_fields(
            ds=ds,
            object_type='user_group',
            records=user_groups,
            field_ids=['updated_at'],
        )

    Args:
        ds: data source
        object_type: 对象类型（如 'user_group'）
        records: 待增强的记录列表（每条是 dict）
        field_ids: 要注入的字段 ID 集合；None 表示默认 ['updated_at']

    Returns:
        增强后的 records（同对象 in-place 修改 + 返回）
    """
    if not records:
        return records

    target_fields = list(field_ids) if field_ids else ['updated_at']

    # [V007.52 SSOT] 通过 MaterializationRegistry 统一读取
    # - materialized 策略：直接读表列（零 SQL 开销）
    # - audit_derived 策略：聚合 v_audit_all
    # - none / 未注册：fallback 到 created_at
    from meta.core.materialization_registry import get_updated_at

    for record in records:
        rid = record.get('id')
        if rid is None:
            for f in target_fields:
                record[f] = record.get('created_at')
            continue

        for f in target_fields:
            if f == 'updated_at':
                # 统一入口：从 SSOT 选择最优路径
                value = get_updated_at(
                    ds=ds,
                    table_name=_object_type_to_table_name(object_type),
                    object_id=rid,
                    object_type=object_type,
                    fallback=record.get('created_at'),
                )
                record[f] = value
            else:
                # 其他虚拟字段暂未 SSOT 化，保持原样
                record[f] = record.get(f) or record.get('created_at')

    return records


def get_audit_derived_updated_at(
    ds,
    object_type: str,
    object_id: Any,
    fallback: Optional[str] = None,
) -> Optional[str]:
    """便捷方法：获取单个 object 的派生 updated_at

    Args:
        ds: data source
        object_type: 对象类型
        object_id: 对象 ID
        fallback: 兜底值（默认 None）

    Returns:
        ISO 字符串 或 fallback
    """
    value = _get_audit_field_value(ds, object_type, str(object_id))
    return value if value is not None else fallback
