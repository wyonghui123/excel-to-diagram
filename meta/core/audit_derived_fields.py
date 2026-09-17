# -*- coding: utf-8 -*-
"""
Audit-Derived Virtual Fields — SSOT 单一事实实现

【背景 2026-06-05】
v1.4 updated_at 统一规则：所有 object 的 `updated_at` 是**计算字段**，
不存储在业务表中，从 audit_logs 表实时派生。

【V007.51 Phase 2 更新 2026-07-14】
v2.0 物化列优先：有物化 updated_at 列的表直接从列读取，
无物化列的表仍走 v_audit_all 实时派生。

【PERF 2026-09-14 清理】
逐行路径（get_audit_derived_updated_at / _get_audit_field_value /
_normalize_rows / _execute_audit_query / _AUDIT_DERIVE_SELECT_SQL* 常量组）
已删除：全仓库无外部调用方（含 tests），且逐行 v_audit_all 全表扫描是
prod 列表接口 502 的根因。批量路径（_AUDIT_DERIVE_BATCH_SQL* + _batch_*）
是唯一实现，聚合语义为 MAX(created_at) ISO 字符串，不使用 created_at_epoch
（v007_45 回填的 epoch 按 UTC 解释会引入时区漂移，且新写入行 epoch 为 NULL）。

历史：项目内有 2 份重复实现：
  - meta.services.query_service.QueryService._enrich_audit_virtual_fields
  - meta.core.interceptors.persistence_interceptor.PersistenceInterceptor._enrich_audit_virtual_fields

v1.4 抽取为 SSOT helper，未来 2 处实现应改为调用本模块。

派生规则（SSOT）：
  1. 优先从物化列读取（V007.51 新增，零 SQL 开销）
  2. 只查询 action='UPDATE' 的审计日志
  3. 取每个 object_id 的 MAX(created_at)（ISO 字符串聚合）
  4. 没有 UPDATE 记录时，fallback 为该 record 自己的 created_at
  5. 测试环境优雅降级（audit_logs 表缺失时直接 fallback）
"""
import logging
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# [PERF 2026-09-14] 批量派生 SQL：一次聚合查询取整批 object_id 的 updated_at，
# 替代逐行 get_updated_at（O(n) 次 v_audit_all 全表扫描 → O(n/500) 次）。
# 语义与原 get_updated_at(audit_derived) 严格一致：只看 MAX(created_at)，
# 不使用 created_at_epoch（v007_45 回填的 epoch 按 UTC 解释会引入时区漂移，
# 且新写入行 epoch 为 NULL，混用会导致 MAX 取到旧记录）。
#
# [PERF 2026-09-15 r017] 拆双查 SQL：分查 audit_logs (热) + audit_logs_archive (冷)，
# Python 侧合并 MAX(created_at)。原因：prod 实测 v_audit_all 复合视图让 SQLite
# 无法下推 WHERE, 全表扫描 11.9 万 + 11.9 万行 = ~100ms; 直查 audit_logs 命中
# idx_audit_ssot_updated = ~3.9ms (26× 提速); 直查 audit_logs_archive 命中
# idx_audit_archive_type_id_action = ~4.5ms (合计 8.4ms, 12× 提速)。
# archive 表 prod 有 11.9 万行真实数据 (HOFF §1.1 "0 行" 错误),
# 不能简单 DROP, 必须保留并参与合并。
# ─────────────────────────────────────────────────────────────
_AUDIT_DERIVE_BATCH_SQL = (
    "SELECT object_id, MAX(created_at) as max_iso "
    "FROM v_audit_all "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)

_AUDIT_DERIVE_BATCH_SQL_NO_VIEW = (
    "SELECT object_id, MAX(created_at) as max_iso "
    "FROM audit_logs "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)

# [PERF 2026-09-15 r017] 方案 A: 热表直查 (命中索引)
_AUDIT_DERIVE_HOT_SQL = (
    "SELECT object_id, MAX(created_at) as max_iso "
    "FROM audit_logs "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)

# [PERF 2026-09-15 r017] 方案 A: 冷表直查 (命中索引)
_AUDIT_DERIVE_ARCHIVE_SQL = (
    "SELECT object_id, MAX(created_at) as max_iso "
    "FROM audit_logs_archive "
    "WHERE object_type = ? AND object_id IN ({placeholders}) "
    "AND action = 'UPDATE' "
    "GROUP BY object_id"
)

# SQLite 变量数上限兜底（旧版编译默认 999），IN 列表按此分片
_SQL_PARAM_CHUNK = 500


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


def _chunked(seq: List[Any], size: int):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _execute_batch_audit_query(ds, object_type: str, object_ids: List[str]):
    """[PERF 2026-09-14] 执行批量派生查询（v_audit_all → audit_logs 兜底）"""
    if not object_ids:
        return None
    placeholders = ','.join(['?' for _ in object_ids])
    sql = _AUDIT_DERIVE_BATCH_SQL.format(placeholders=placeholders)
    try:
        if hasattr(ds, 'query'):
            return ds.query(sql, [object_type] + object_ids)
        return ds.execute(sql, [object_type] + object_ids)
    except Exception as e:
        if "no such table: v_audit_all" in str(e).lower():
            logger.warning(
                "[audit_derived_fields] v_audit_all not found, batch fallback to audit_logs"
            )
            fallback_sql = _AUDIT_DERIVE_BATCH_SQL_NO_VIEW.format(placeholders=placeholders)
            try:
                if hasattr(ds, 'query'):
                    return ds.query(fallback_sql, [object_type] + object_ids)
                return ds.execute(fallback_sql, [object_type] + object_ids)
            except Exception as e2:
                logger.warning(
                    "[audit_derived_fields] Batch fallback to audit_logs also failed: %s", e2
                )
                return None
        logger.warning(
            "[audit_derived_fields] Batch query failed (object_type=%s): %s", object_type, e
        )
        return None


def _rows_to_iso_map(rows) -> Dict[str, str]:
    """归一化批量派生结果为 {object_id: max_iso}（与原 get_updated_at 同语义，仅 ISO 字符串）"""
    result_map: Dict[str, str] = {}
    if not rows:
        return result_map
    for row in rows:
        if isinstance(row, dict):
            oid = str(row.get('object_id'))
            iso_val = row.get('max_iso')
        else:
            oid = str(row[0])
            iso_val = row[1] if len(row) > 1 else None
        if iso_val:
            result_map[oid] = iso_val
    return result_map


def _batch_read_audit_derived(ds, object_type: str, ids: List[Any]) -> Dict[str, str]:
    """[PERF 2026-09-15 r017] 方案 A 拆双查 + Python 合并

    分查 audit_logs (热) + audit_logs_archive (冷), Python 侧对同一 object_id
    取 MAX(created_at)。避免 v_audit_all 复合视图无法下推 WHERE 的全表扫描。

    prod 实测（2026-09-15 远端探针 _r017_prod_probe.py）:
      - v_audit_all 5000 batch: 100.28ms (SCAN audit_logs + SCAN audit_logs_archive)
      - audit_logs 基线:        2.54ms  (SEARCH USING idx_audit_ssot_updated)
      - 本地基准推算方案 A:     ~50ms   (1.5-2× 提速)

    兼容性:
      - 缺 audit_logs_archive 表时自动降级为单表查询
      - 缺 idx_audit_ssot_updated 索引时降级为 SCAN, 性能等同旧路径
      - 异常/无数据时降级为 created_at fallback（由 _batch_enrich_updated_at 处理）

    Args:
        ds: data source (DataSource 或 sqlite3.Connection)
        object_type: 审计对象类型 (如 'service_module')
        ids: 业务对象 id 列表

    Returns:
        {object_id: max_iso_created_at}
    """
    result_map: Dict[str, str] = {}
    # [FIX 2026-09-15 r017 二次检查] 防御性过滤 None, 防止 str(None)='None'
    # 误查。理论上前序 _batch_enrich_updated_at 已过滤 None, 此处为保险。
    str_ids = [str(i) for i in ids if i is not None]
    if len(str_ids) != len(ids):
        logger.warning(
            "[audit_derived_fields r017] filtered None ids: %d → %d",
            len(ids), len(str_ids),
        )

    for chunk in _chunked(str_ids, _SQL_PARAM_CHUNK):
        placeholders = ','.join(['?' for _ in chunk])

        # 1. 热表直查 (命中 idx_audit_ssot_updated)
        hot_map: Dict[str, str] = {}
        try:
            hot_sql = _AUDIT_DERIVE_HOT_SQL.format(placeholders=placeholders)
            if hasattr(ds, 'query'):
                hot_rows = ds.query(hot_sql, [object_type] + chunk)
            else:
                hot_rows = ds.execute(hot_sql, [object_type] + chunk).fetchall()
            hot_map = _rows_to_iso_map(hot_rows)
        except Exception as e:
            # [FIX 2026-09-15 r017 二次检查] 热表失败不再降级到 v_audit_all
            # 原因: v_audit_all 复合视图 5000 batch 实测 100ms (SCAN × 2),
            #       降级路径等于从 8ms 退化到 100ms (12× 慢), 违背优化目的.
            # 改为返回 {}, 让 _batch_enrich_updated_at 走 record.created_at fallback.
            logger.warning(
                "[audit_derived_fields r017] hot table query failed, "
                "use created_at fallback (skip archive too): %s", e
            )
            continue

        # 2. 冷表直查 (命中 idx_audit_archive_type_action_created)
        arch_map: Dict[str, str] = {}
        try:
            arch_sql = _AUDIT_DERIVE_ARCHIVE_SQL.format(placeholders=placeholders)
            if hasattr(ds, 'query'):
                arch_rows = ds.query(arch_sql, [object_type] + chunk)
            else:
                arch_rows = ds.execute(arch_sql, [object_type] + chunk).fetchall()
            arch_map = _rows_to_iso_map(arch_rows)
        except Exception as e:
            # 冷表缺失 (部署未启用归档) → 仅用 hot 结果, 不降级
            if "no such table: audit_logs_archive" in str(e).lower():
                logger.debug(
                    "[audit_derived_fields r017] archive table not found, "
                    "use hot only"
                )
            else:
                logger.warning(
                    "[audit_derived_fields r017] archive query failed: %s", e
                )

        # 3. Python 侧合并: 同 oid 取 MAX(created_at) (字符串字典序与时间序一致)
        for oid, ts in hot_map.items():
            arch_ts = arch_map.get(oid)
            if not arch_ts or ts >= arch_ts:
                result_map[oid] = ts
            else:
                result_map[oid] = arch_ts
        # archive 独有 oid (hot 未返回)
        for oid, ts in arch_map.items():
            if oid not in result_map:
                result_map[oid] = ts

    return result_map


def _batch_read_materialized(ds, table_name: str, ids: List[Any]) -> Dict[str, str]:
    """[PERF 2026-09-14] 批量物化列读取：一次 SELECT id, updated_at IN (...) 替代逐行 SELECT

    分片容错：单个分片查询失败仅跳过该分片（warning 日志），保留已成功分片的结果，
    避免中途异常导致整批结果丢弃、全部退化 fallback。
    """
    from meta.core.table_name_validator import validate_table_name
    table_name = validate_table_name(table_name)
    result_map: Dict[str, str] = {}
    for chunk_no, chunk in enumerate(_chunked(ids, _SQL_PARAM_CHUNK), 1):
        placeholders = ','.join(['?' for _ in chunk])
        sql = f"SELECT id, updated_at FROM {table_name} WHERE id IN ({placeholders})"
        try:
            if hasattr(ds, 'query'):
                rows = ds.query(sql, chunk)
            else:
                rows = ds.execute(sql, chunk).fetchall()
        except Exception as e:
            logger.warning(
                "[audit_derived_fields] Batch materialized read failed for %s "
                "(chunk %s, %d ids): %s - 该分片结果跳过",
                table_name, chunk_no, len(chunk), e
            )
            continue
        for row in rows or []:
            if isinstance(row, dict):
                rid, val = row.get('id'), row.get('updated_at')
            else:
                rid = row[0]
                val = row[1] if len(row) > 1 else None
            if val:
                result_map[str(rid)] = val
    return result_map


def _batch_enrich_updated_at(
    ds, object_type: str, records: List[Dict[str, Any]], preserve_existing: bool = False,
) -> None:
    """[PERF 2026-09-14] updated_at 批量富化（in-place）

    策略路由与原 get_updated_at 保持一致：
    - materialized: 批量 SELECT id, updated_at
    - audit_derived: 分片批量聚合 v_audit_all
    - none / 未注册 / 查询失败: 全部 fallback created_at

    Args:
        preserve_existing: True 时已有 updated_at 值（非 None）的记录保持不变。
            供早期自行实现"跳过已有值"语义的调用方（如 enum_api）接入 SSOT 时
            保持原行为；默认 False 维持 query_service / persistence_interceptor
            既有语义（物化表重读同列值，幂等）。
    """
    from meta.core.materialization_registry import get_registry, STRATEGY_AUDIT_DERIVED

    table_name = _object_type_to_table_name(object_type)
    registry = get_registry()
    strategy = registry.get_strategy(table_name)

    pending_ids: List[Any] = []
    for record in records:
        if preserve_existing and record.get('updated_at') is not None:
            continue
        rid = record.get('id')
        if rid is None:
            record['updated_at'] = record.get('created_at')
        else:
            pending_ids.append(rid)

    if not pending_ids:
        return

    if registry.is_materialized(table_name):
        result_map = _batch_read_materialized(ds, table_name, pending_ids)
    elif strategy == STRATEGY_AUDIT_DERIVED:
        result_map = _batch_read_audit_derived(ds, object_type, pending_ids)
    else:
        result_map = {}

    for record in records:
        if preserve_existing and record.get('updated_at') is not None:
            continue
        rid = record.get('id')
        if rid is None:
            continue
        record['updated_at'] = result_map.get(str(rid)) or record.get('created_at')


def enrich_audit_virtual_fields(
    ds,
    object_type: str,
    records: List[Dict[str, Any]],
    field_ids: Optional[Iterable[str]] = None,
    preserve_existing: bool = False,
) -> List[Dict[str, Any]]:
    """SSOT: 批量为 records 注入派生 virtual 字段（如 updated_at）

    [PERF 2026-09-14] updated_at 走批量路径（_batch_enrich_updated_at）：
    物化表批量 SELECT id, updated_at；audit_derived 表分片聚合 v_audit_all。
    物化值由批量重读提供（与列值一致），非"跳过已有值"。
    逐行 get_updated_at 的 O(n) 次 v_audit_all 全表扫描（prod 列表接口 502
    根因）已随死代码一并删除。

    Args:
        ds: data source
        object_type: 对象类型（如 'user_group'）
        records: 待增强的记录列表（每条是 dict）
        field_ids: 要注入的字段 ID 集合；None 表示默认 ['updated_at']
        preserve_existing: True 时已有 updated_at（非 None）的记录不覆盖；
            默认 False 保持既有调用方语义

    Returns:
        增强后的 records（同对象 in-place 修改 + 返回）

    用法：
        from meta.core.audit_derived_fields import enrich_audit_virtual_fields

        records = enrich_audit_virtual_fields(
            ds=ds,
            object_type='user_group',
            records=user_groups,
            field_ids=['updated_at'],
        )
    """
    if not records:
        return records

    target_fields = list(field_ids) if field_ids else ['updated_at']

    if 'updated_at' in target_fields:
        _batch_enrich_updated_at(ds, object_type, records, preserve_existing=preserve_existing)

    # 其他虚拟字段暂未 SSOT 化，保持原样
    for f in target_fields:
        if f == 'updated_at':
            continue
        for record in records:
            record[f] = record.get(f) or record.get('created_at')

    return records
