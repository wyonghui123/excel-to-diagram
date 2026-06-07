# -*- coding: utf-8 -*-
"""
查询时填充引擎（Enrichment Engine）

核心职责：
1. 从冗余注册表获取虚拟冗余字段定义
2. 根据 join_path 自动生成 JOIN 查询
3. 批量填充记录的虚拟字段
4. 替代 _enrich_record_with_names() 的硬编码实现

设计参考：
- SAP CDS View 的 SELECT 从 CDS 投影
- Salesforce 的 Formula Field 运行时计算
- Palantir Ontology 的 derived property 解析

使用示例：
    from meta.core.enrichment_engine import enrichment_engine
    
    # 填充单条记录
    record = enrichment_engine.enrich_one('relationship', record)
    
    # 批量填充
    records = enrichment_engine.enrich_batch('business_object', records)
"""

from typing import List, Dict, Any, Optional, Set
import logging

from meta.core.redundancy_registry import (
    RedundancyRegistry,
    RedundancyDef,
    RedundancyType,
    JoinStep,
)

logger = logging.getLogger(__name__)


class EnrichmentEngine:
    """查询时填充引擎
    
    根据元模型的 redundancy 声明，自动填充虚拟冗余字段。
    支持单层和多层 JOIN 路径。
    """
    
    def __init__(self, data_source, registry: RedundancyRegistry):
        self.ds = data_source
        self.registry = registry
        
        self._name_cache: Dict[str, Dict[Any, Any]] = {}
        self._record_cache: Dict[str, Dict[Any, Dict[str, Any]]] = {}
    
    def enrich_one(self, object_type: str, record: Dict[str, Any]) -> Dict[str, Any]:
        """填充单条记录的虚拟冗余字段
        
        Args:
            object_type: 对象类型
            record: 原始记录
            
        Returns:
            填充后的记录
        """
        if not record:
            return record
        
        obj_reds = self.registry.get_object_redundancies(object_type)
        if not obj_reds:
            return record
        
        virtual_reds = {
            fid: red for fid, red in obj_reds.items()
            if red.redundancy_type in (RedundancyType.VIRTUAL, RedundancyType.RESOLUTION)
        }
        
        if not virtual_reds:
            return record
        
        enriched = dict(record)
        
        for field_id, red_def in virtual_reds.items():
            self._enrich_field(enriched, field_id, red_def)
        
        return enriched
    
    def enrich_batch(self, object_type: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量填充记录的虚拟冗余字段
        
        使用批量查询优化性能，避免 N+1 问题。
        
        Args:
            object_type: 对象类型
            records: 原始记录列表
            
        Returns:
            填充后的记录列表
        """
        if not records:
            return records
        
        obj_reds = self.registry.get_object_redundancies(object_type)
        if not obj_reds:
            return records
        
        virtual_reds = {
            fid: red for fid, red in obj_reds.items()
            if red.redundancy_type in (RedundancyType.VIRTUAL, RedundancyType.RESOLUTION)
        }
        
        if not virtual_reds:
            return records
        
        for field_id, red_def in virtual_reds.items():
            self._enrich_field_batch(records, field_id, red_def)
        
        return records
    
    def _enrich_field(self, record: Dict[str, Any], field_id: str, red_def: RedundancyDef):
        """填充单个字段"""
        source_id = record.get(red_def.source_field)
        if source_id is None:
            return
        
        if red_def.join_path:
            value = self._resolve_join_path(red_def.join_path, source_id)
        else:
            value = self._resolve_simple(red_def, source_id)
        
        if value is not None:
            record[field_id] = value
    
    def _enrich_field_batch(self, records: List[Dict[str, Any]], field_id: str, red_def: RedundancyDef):
        """批量填充单个字段"""
        source_ids = list(set(
            r.get(red_def.source_field) for r in records
            if r.get(red_def.source_field) is not None
        ))
        
        if not source_ids:
            return
        
        if red_def.join_path:
            lookup = self._resolve_join_path_batch(red_def.join_path, source_ids)
        else:
            lookup = self._resolve_simple_batch(red_def, source_ids)
        
        if not lookup:
            return
        
        for record in records:
            source_id = record.get(red_def.source_field)
            if source_id is not None and source_id in lookup:
                record[field_id] = lookup[source_id]
    
    def _resolve_simple(self, red_def: RedundancyDef, source_id: Any) -> Optional[Any]:
        """解析简单引用（单层）"""
        derived_table = red_def.derived_table
        derived_field = red_def.derived_field
        
        if not derived_table or not derived_field:
            return None
        
        table_name = self._get_table_name(derived_table)
        cache_key = f"{table_name}.{derived_field}"
        
        if cache_key not in self._name_cache:
            self._name_cache[cache_key] = {}
        
        if source_id in self._name_cache[cache_key]:
            return self._name_cache[cache_key][source_id]
        
        try:
            sql = f"SELECT {derived_field} FROM {table_name} WHERE id = ?"
            cursor = self.ds.execute(sql, (source_id,))
            row = cursor.fetchone()
            
            if row:
                value = row[0]
                self._name_cache[cache_key][source_id] = value
                return value
                
        except Exception as e:
            logger.warning(
                "[EnrichmentEngine] 查询失败: %s.%s WHERE id=%s: %s",
                table_name, derived_field, source_id, str(e)
            )
        
        return None
    
    def _resolve_simple_batch(self, red_def: RedundancyDef, source_ids: List[Any]) -> Dict[Any, Any]:
        """批量解析简单引用"""
        derived_table = red_def.derived_table
        derived_field = red_def.derived_field
        
        if not derived_table or not derived_field:
            return {}
        
        table_name = self._get_table_name(derived_table)
        cache_key = f"{table_name}.{derived_field}"
        
        if cache_key not in self._name_cache:
            self._name_cache[cache_key] = {}
        
        result = {}
        uncached_ids = []
        
        for sid in source_ids:
            if sid in self._name_cache[cache_key]:
                result[sid] = self._name_cache[cache_key][sid]
            else:
                uncached_ids.append(sid)
        
        if uncached_ids:
            placeholders = ','.join('?' * len(uncached_ids))
            sql = f"SELECT id, {derived_field} FROM {table_name} WHERE id IN ({placeholders})"
            
            try:
                cursor = self.ds.execute(sql, tuple(uncached_ids))
                for row in cursor.fetchall():
                    sid, value = row[0], row[1]
                    result[sid] = value
                    self._name_cache[cache_key][sid] = value
                    
            except Exception as e:
                logger.warning(
                    "[EnrichmentEngine] 批量查询失败: %s.%s: %s",
                    table_name, derived_field, str(e)
                )
        
        return result
    
    def _resolve_join_path(self, join_path: List[JoinStep], source_id: Any) -> Optional[Any]:
        """解析多层 JOIN 路径

        支持 fixed_conditions 用于 enum 关联等特殊 JOIN
        """
        if not join_path:
            return None

        first_step = join_path[0]
        last_step = join_path[-1]

        current_id = source_id
        current_record = None

        for i, step in enumerate(join_path):
            table_name = step.table

            cache_key = f"{table_name}_full"
            if cache_key not in self._record_cache:
                self._record_cache[cache_key] = {}

            if current_id in self._record_cache[cache_key]:
                current_record = self._record_cache[cache_key][current_id]
            else:
                where_conditions = []
                params = []

                where_conditions.append(f"{step.to_field} = ?")
                params.append(current_id)

                if step.fixed_conditions:
                    for fc_field, fc_op, fc_value in step.fixed_conditions:
                        where_conditions.append(f"{fc_field} {fc_op} ?")
                        params.append(fc_value)

                where_clause = " AND ".join(where_conditions)

                try:
                    sql = f"SELECT * FROM {table_name} WHERE {where_clause}"
                    cursor = self.ds.execute(sql, tuple(params))
                    row = cursor.fetchone()

                    if row:
                        columns = [desc[0] for desc in cursor.description]
                        current_record = dict(zip(columns, row))
                        cache_id = current_id
                        self._record_cache[cache_key][cache_id] = current_record
                    else:
                        return None

                except Exception as e:
                    logger.warning(
                        "[EnrichmentEngine] JOIN 查询失败: %s WHERE %s=%s: %s",
                        table_name, step.to_field, current_id, str(e)
                    )
                    return None

            if i < len(join_path) - 1:
                next_step = join_path[i + 1]
                current_id = current_record.get(step.select) if current_record else None

                if current_id is None:
                    return None

        if current_record:
            return current_record.get(last_step.select)

        return None
    
    def _resolve_join_path_batch(self, join_path: List[JoinStep], source_ids: List[Any]) -> Dict[Any, Any]:
        """批量解析多层 JOIN 路径

        支持 fixed_conditions 用于 enum 关联等特殊 JOIN
        """
        if not join_path:
            return {}
        
        first_step = join_path[0]

        result = {}

        first_step = join_path[0]
        last_step = join_path[-1]

        current_ids = list(source_ids)
        current_id_map: Dict[Any, Any] = {sid: sid for sid in source_ids}

        for i, step in enumerate(join_path):
            if not current_ids:
                break

            table_name = step.table

            cache_key = f"{table_name}_full"
            if cache_key not in self._record_cache:
                self._record_cache[cache_key] = {}

            uncached_ids = [
                cid for cid in current_ids
                if cid not in self._record_cache[cache_key]
            ]

            if uncached_ids:
                where_conditions = []
                params = []

                placeholders = ','.join('?' * len(uncached_ids))
                where_conditions.append(f"{step.to_field} IN ({placeholders})")
                params.extend(uncached_ids)

                if step.fixed_conditions:
                    for fc_field, fc_op, fc_value in step.fixed_conditions:
                        where_conditions.append(f"{fc_field} {fc_op} ?")
                        params.append(fc_value)

                where_clause = " AND ".join(where_conditions)
                sql = f"SELECT * FROM {table_name} WHERE {where_clause}"

                max_retries = 3
                for retry in range(max_retries):
                    try:
                        cursor = self.ds.execute(sql, tuple(params))
                        columns = [desc[0] for desc in cursor.description]

                        for row in cursor.fetchall():
                            record = dict(zip(columns, row))
                            cache_id = record.get(step.to_field)
                            if cache_id is not None:
                                self._record_cache[cache_key][cache_id] = record
                        break
                    except Exception as e:
                        if retry < max_retries - 1 and ("closed database" in str(e) or "operational" in str(e).lower()):
                            logger.debug("[EnrichmentEngine] 重试批量 JOIN 查询: %s (尝试 %d/%d)", table_name, retry + 2, max_retries)
                            continue
                        logger.warning(
                            "[EnrichmentEngine] 批量 JOIN 查询失败: %s: %s",
                            table_name, str(e)
                        )

            if i < len(join_path) - 1:
                next_ids = []
                next_id_map: Dict[Any, Any] = {}

                for original_sid in source_ids:
                    cid = current_id_map.get(original_sid)
                    if cid is None:
                        continue

                    record = self._record_cache[cache_key].get(cid)
                    if record:
                        next_id = record.get(step.select)
                        if next_id is not None:
                            next_ids.append(next_id)
                            next_id_map[original_sid] = next_id

                current_ids = list(set(next_ids))
                current_id_map = next_id_map

        for original_sid in source_ids:
            cid = current_id_map.get(original_sid)
            if cid is None:
                continue

            record = self._record_cache.get(f"{last_step.table}_full", {}).get(cid)
            if record:
                value = record.get(last_step.select)
                if value is not None:
                    result[original_sid] = value
        
        return result
    
    def _get_table_name(self, object_type: str) -> str:
        """获取对象对应的表名"""
        from meta.core.models import registry as meta_registry
        
        meta_obj = meta_registry.get(object_type)
        if meta_obj and meta_obj.table_name:
            return meta_obj.table_name
        
        return f"{object_type}s"
    
    def clear_cache(self):
        """清空缓存"""
        self._name_cache.clear()
        self._record_cache.clear()

    # ============================================================
    # v1 兼容：FK display + association count（从 enrich_utils 迁移）
    # 2026-06-05 M2 收敛：与 enrich_utils.enrich_fk_display_names /
    # enrich_association_counts 行为一致
    # ============================================================
    def enrich_fk_display_names(self, meta_object, records_or_record) -> Any:
        """为 FK 字段批量注入 {field}_display 字段（v1 兼容路径）。

        遍历 meta_object 的 fields，找到 value_help.source.type='bo' 的 FK 字段，
        批量查询目标表的 display_field，注入 {field}_display 到每条记录。

        支持单条记录（dict）或列表（list），原地修改。
        """
        is_single = False
        if isinstance(records_or_record, dict):
            records = [records_or_record]
            is_single = True
        else:
            records = records_or_record

        if not records:
            return records_or_record

        fields = getattr(meta_object, 'fields', [])
        if not fields:
            return records_or_record

        from meta.core.models import registry as _registry
        meta_registry = _registry

        enriched_count = 0
        for field in fields:
            value_help = getattr(field, 'value_help', None)
            if not value_help:
                continue
            source = getattr(value_help, 'source', None)
            if not source or getattr(source, 'type', '') != 'bo':
                continue

            target_bo = getattr(source, 'target_bo', '')
            display_field = getattr(source, 'display_field', 'name') or 'name'
            fk_field_id = getattr(field, 'id', '')
            if not target_bo or not fk_field_id:
                continue

            fk_values = {
                record[fk_field_id]
                for record in records
                if record.get(fk_field_id) is not None
            }
            if not fk_values:
                continue

            target_table = None
            if meta_registry:
                try:
                    target_meta = meta_registry.get(target_bo)
                    if target_meta:
                        target_table = getattr(target_meta, 'table_name', None)
                except Exception:
                    pass
            if not target_table:
                target_table = f'{target_bo}s'

            try:
                placeholders = ','.join(['?'] * len(fk_values))
                sql = f'SELECT id, {display_field} FROM {target_table} WHERE id IN ({placeholders})'
                cursor = self.ds.execute(sql, list(fk_values))
                display_map = {row[0]: row[1] for row in cursor.fetchall()}
                display_key = f'{fk_field_id}_display'
                for record in records:
                    fk_val = record.get(fk_field_id)
                    record[display_key] = display_map.get(fk_val) if fk_val is not None else None
                enriched_count += 1
                logger.info(
                    f'[EnrichmentEngine.enrich_fk_display_names] {fk_field_id}->{target_bo}: '
                    f'enriched {len(display_map)} values'
                )
            except Exception as e:
                logger.warning(
                    f'[EnrichmentEngine.enrich_fk_display_names] {fk_field_id}->{target_bo} failed: {e}'
                )

        if enriched_count > 0:
            logger.info(
                f'[EnrichmentEngine.enrich_fk_display_names] enriched {enriched_count} FK fields '
                f'for {getattr(meta_object, "id", "?")}'
            )

        return records_or_record if is_single else records

    def enrich_association_counts(self, meta_object, records) -> Any:
        """为记录批量注入 association count 字段（v1 兼容路径）。

        适用于 many_to_many 关联。通过 COUNT(*) 子查询计算每条记录的关联数量，
        注入 {assoc_name}_count 字段。

        原地修改 records 列表。
        """
        if not records:
            return records

        associations = getattr(meta_object, 'associations', None)
        if not associations:
            return records

        record_ids = [r.get('id') for r in records if r.get('id') is not None]
        if not record_ids:
            return records

        if isinstance(associations, dict):
            assoc_items = list(associations.values())
        else:
            assoc_items = list(associations)

        placeholders = ','.join(['?'] * len(record_ids))

        for assoc in assoc_items:
            assoc_type = getattr(assoc, 'type', None)
            if assoc_type != 'many_to_many':
                continue
            through = getattr(assoc, 'through', None)
            source_key = getattr(assoc, 'source_key', None)
            target_key = getattr(assoc, 'target_key', None)
            assoc_name = getattr(assoc, 'name', None)
            if not through or not source_key or not target_key or not assoc_name:
                continue

            count_field = f'{assoc_name}_count'
            if assoc_name == 'members':
                count_field = 'member_count'
            try:
                sql = (
                    f'SELECT {source_key}, COUNT(*) FROM {through} '
                    f'WHERE {source_key} IN ({placeholders}) GROUP BY {source_key}'
                )
                cursor = self.ds.execute(sql, record_ids)
                count_map = {row[0]: row[1] for row in cursor.fetchall()}
                for record in records:
                    record[count_field] = count_map.get(record.get('id'), 0)
                logger.info(
                    f'[EnrichmentEngine.enrich_association_counts] {assoc_name}: '
                    f'enriched {len(count_map)} counts'
                )
            except Exception as e:
                logger.debug(
                    f'[EnrichmentEngine.enrich_association_counts] {assoc_name} failed: {e}'
                )
                for record in records:
                    record[count_field] = 0

        return records

    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        return {
            "name_cache_tables": len(self._name_cache),
            "name_cache_entries": sum(len(v) for v in self._name_cache.values()),
            "record_cache_tables": len(self._record_cache),
            "record_cache_entries": sum(len(v) for v in self._record_cache.values()),
        }


_engine_instance: Optional[EnrichmentEngine] = None


def get_enrichment_engine() -> Optional[EnrichmentEngine]:
    """获取全局 EnrichmentEngine 实例"""
    return _engine_instance


def init_enrichment_engine(data_source) -> EnrichmentEngine:
    """初始化全局 EnrichmentEngine 实例"""
    global _engine_instance
    
    from meta.core.redundancy_registry import redundancy_registry
    
    _engine_instance = EnrichmentEngine(data_source, redundancy_registry)
    return _engine_instance


def enrich_record(object_type: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """便捷函数：填充单条记录"""
    if _engine_instance is None:
        return record
    return _engine_instance.enrich_one(object_type, record)


def enrich_records(object_type: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """便捷函数：批量填充记录"""
    if _engine_instance is None:
        return records
    return _engine_instance.enrich_batch(object_type, records)
