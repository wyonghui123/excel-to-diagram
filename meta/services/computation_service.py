# -*- coding: utf-8 -*-
"""
统计规则计算服务

支持在列表查询时动态计算统计字段，如关系数量统计。

统一计算逻辑：
1. 优先从 ui_view_config.list.columns[].computation 获取计算配置（UI 驱动）
2. 同时支持从 meta_obj.rules 中的 MetaComputation 规则获取计算配置（元模型驱动）
3. 两种配置源的计算结果合并，UI 配置优先
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from meta.core.models import registry, MetaComputation, RuleType
from meta.core.table_name_validator import validate_table_name


@dataclass
class ComputationRule:
    type: str
    scope: str
    relation_type: Optional[str] = None


class ComputationService:
    """统计规则计算服务"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache = {}
        return cls._instance

    AGGREGATION_TYPES = {
        'sum_field': 'SUM',
        'avg_field': 'AVG',
        'max_field': 'MAX',
        'min_field': 'MIN'
    }

    def compute_field(self, data_source, object_type: str, record_id: int,
                      field_key: str, computation: Dict[str, Any]) -> Any:
        comp_type = computation.get('type', '')
        scope = computation.get('scope', 'self')

        if comp_type == 'count_relations':
            return self._count_relations(data_source, object_type, record_id, scope)

        if comp_type == 'count_children':
            return self._count_children(data_source, object_type, record_id, computation)

        if comp_type in self.AGGREGATION_TYPES:
            source_field = computation.get('source_field')
            filters = computation.get('filters')
            return self._aggregate_field(
                data_source, object_type, source_field, comp_type, filters
            )

        if comp_type == 'expression':
            return self._evaluate_expression(data_source, object_type, record_id, computation)

        return None

    def compute_batch(self, data_source, object_type: str, records: List[Dict],
                      computed_columns: List[Dict]) -> List[Dict]:
        if not computed_columns or not records:
            return records

        for col in computed_columns:
            computation = col.get('computation', {})
            if not computation:
                continue

            comp_type = computation.get('type', '')
            scope = computation.get('scope', 'self')

            if comp_type == 'count_relations':
                self._batch_count_relations(data_source, object_type, records, col['key'], scope)
            elif comp_type == 'count_children':
                self._batch_count_children(data_source, object_type, records, col['key'], computation)
            elif comp_type in self.AGGREGATION_TYPES:
                self._batch_aggregate_field(data_source, object_type, records, col['key'], computation)
            elif comp_type == 'expression' or computation.get('formula'):
                self._batch_evaluate_formula(data_source, object_type, records, col['key'], computation)

        return records

    def get_computed_columns_from_rules(self, object_type: str) -> List[Dict]:
        """从元模型规则中提取计算列配置

        扫描 meta_obj.rules 中类型为 COMPUTATION 的规则，
        转换为 ui_view_config.list.columns[].computation 兼容格式。

        Returns:
            计算列配置列表，格式: [{'key': field_id, 'computation': {...}}, ...]
        """
        meta_obj = registry.get(object_type)
        if not meta_obj or not meta_obj.rules:
            return []

        computed_columns = []
        for rule in meta_obj.rules:
            if not isinstance(rule, MetaComputation):
                continue

            if not rule.target_field:
                continue

            computation = {
                'type': 'expression',
                'formula': rule.formula,
                'source_fields': rule.source_fields or [],
            }

            if rule.condition:
                computation['condition'] = rule.condition

            computed_columns.append({
                'key': rule.target_field,
                'computation': computation,
                'rule_id': rule.id,
                'rule_name': rule.name,
            })

        return computed_columns

    def merge_computed_columns(self, ui_columns: List[Dict],
                                rule_columns: List[Dict]) -> List[Dict]:
        """合并 UI 配置和规则配置的计算列

        UI 配置优先，规则配置补充。

        Args:
            ui_columns: 从 ui_view_config 获取的计算列
            rule_columns: 从 meta_obj.rules 获取的计算列

        Returns:
            合并后的计算列列表
        """
        ui_keys = {col.get('key') for col in ui_columns}

        merged = list(ui_columns)
        for rule_col in rule_columns:
            if rule_col.get('key') not in ui_keys:
                merged.append(rule_col)

        return merged

    @staticmethod
    def collect_computed_columns(meta_obj) -> list:
        """[FR-005] SSOT: 从 ui_view_config + rules 收集计算列配置

        统一 import_export_service._compute_list_computed_fields_for_export
        和 query_service._compute_list_computed_fields 的重复逻辑。

        Args:
            meta_obj: MetaObject 实例

        Returns:
            合并后的计算列配置列表
        """
        from meta.services.computation_service import computation_service

        ui_computed_columns = []
        if hasattr(meta_obj, 'ui_view_config') and meta_obj.ui_view_config:
            list_config = getattr(meta_obj.ui_view_config, 'list', None)
            if list_config and hasattr(list_config, 'columns'):
                ui_computed_columns = [
                    {'key': col.key, 'computation': getattr(col, 'computation', None)}
                    for col in list_config.columns
                    if getattr(col, 'computed', False) and getattr(col, 'computation', None)
                ]

        rule_computed = computation_service.get_computed_columns_from_rules(meta_obj.id)
        return computation_service.merge_computed_columns(ui_computed_columns, rule_computed)

    def _count_children(self, data_source, object_type: str, record_id: int,
                        computation: Dict[str, Any]) -> int:
        target_object = computation.get('target_object') or computation.get('child_object', '')
        if not target_object:
            return 0

        meta_obj = registry.get(target_object)
        if not meta_obj:
            return 0

        table_name = meta_obj.table_name
        fk_field = computation.get('foreign_key', '')
        if not fk_field:
            from meta.services.cascade_service import HierarchyConfigLoader
            fk_field = HierarchyConfigLoader.get_foreign_key(target_object)

        if not fk_field:
            return 0

        try:
            sql = f"SELECT COUNT(*) FROM {table_name} WHERE {fk_field} = ?"
            cursor = data_source.execute(sql, (record_id,))
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _batch_count_children(self, data_source, object_type: str,
                               records: List[Dict], field_key: str,
                               computation: Dict[str, Any]):
        for record in records:
            record_id = record.get('id')
            if record_id:
                record[field_key] = self._count_children(
                    data_source, object_type, record_id, computation
                )
            else:
                record[field_key] = 0

    def _evaluate_expression(self, data_source, object_type: str, record_id: int,
                              computation: Dict[str, Any]) -> Any:
        formula = computation.get('formula', '')
        if not formula:
            return None

        try:
            from meta.core.rule_executor import ExpressionEvaluator, RuleContext
            context = RuleContext(
                object_type=object_type,
                action='compute',
                data={'id': record_id},
            )
            return ExpressionEvaluator.evaluate(formula, context)
        except Exception:
            return None

    def _batch_evaluate_formula(self, data_source, object_type: str,
                                 records: List[Dict], field_key: str,
                                 computation: Dict[str, Any]):
        """批量计算 formula 表达式"""
        formula = computation.get('formula', '')
        if not formula:
            return
        
        try:
            from meta.core.rule_executor import ExpressionEvaluator, RuleContext
            from meta.core.models import registry
            
            meta_obj = registry.get(object_type)
            if not meta_obj:
                return
            
            for record in records:
                context = RuleContext(meta_obj, record, data_source=data_source)
                value = ExpressionEvaluator.evaluate(formula, context)
                record[field_key] = value
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                "Failed to evaluate formula for %s.%s: %s", object_type, field_key, e
            )

    def _aggregate_field(self, data_source, object_type: str, field_name: str,
                         aggregation_type: str, filters: Dict = None) -> Any:
        if not field_name:
            return None

        from meta import get_meta_object
        meta_obj = get_meta_object(object_type)
        if not meta_obj:
            return None

        table_name = validate_table_name(meta_obj.table_name)
        sql_func = self.AGGREGATION_TYPES.get(aggregation_type)
        if not sql_func:
            return None

        try:
            sql = f"SELECT {sql_func}({field_name}) FROM {table_name}"
            params = []

            if filters:
                where_clauses = []
                for key, value in filters.items():
                    where_clauses.append(f"{key} = ?")
                    params.append(value)
                if where_clauses:
                    sql += " WHERE " + " AND ".join(where_clauses)

            cursor = data_source.execute(sql, tuple(params) if params else ())
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        except Exception:
            return None

    def _batch_aggregate_field(self, data_source, object_type: str,
                                records: List[Dict], field_key: str, computation: Dict):
        if not records:
            return

        source_field = computation.get('source_field')
        aggregation_type = computation.get('type')
        filters = computation.get('filters')

        result = self._aggregate_field(data_source, object_type, source_field, aggregation_type, filters)

        for record in records:
            record[field_key] = result

    def _count_relations(self, data_source, object_type: str, record_id: int,
                         scope: str) -> int:
        if object_type == 'business_object' and scope == 'self':
            return self._count_bo_relations(data_source, record_id)
        elif object_type in ('domain', 'sub_domain', 'service_module') and scope == 'descendants':
            return self._count_descendant_relations(data_source, object_type, record_id)
        return 0

    def _count_bo_relations(self, data_source, bo_id: int) -> int:
        try:
            sql = """
                SELECT COUNT(*) FROM relationships
                WHERE source_bo_id = ? OR target_bo_id = ?
            """
            cursor = data_source.execute(sql, (bo_id, bo_id))
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _count_descendant_relations(self, data_source, object_type: str,
                                     record_id: int) -> int:
        try:
            if object_type == 'domain':
                bo_sql = """
                    SELECT bo.id FROM business_objects bo
                    JOIN service_modules sm ON bo.service_module_id = sm.id
                    JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                    WHERE sd.domain_id = ?
                """
            elif object_type == 'sub_domain':
                bo_sql = """
                    SELECT bo.id FROM business_objects bo
                    JOIN service_modules sm ON bo.service_module_id = sm.id
                    WHERE sm.sub_domain_id = ?
                """
            elif object_type == 'service_module':
                bo_sql = """
                    SELECT bo.id FROM business_objects bo
                    WHERE bo.service_module_id = ?
                """
            else:
                return 0

            cursor = data_source.execute(bo_sql, (record_id,))
            bo_ids = [row[0] for row in cursor.fetchall()]

            if not bo_ids:
                return 0

            placeholders = ','.join(['?'] * len(bo_ids))
            rel_sql = f"""
                SELECT COUNT(DISTINCT r.id) FROM relationships r
                WHERE r.source_bo_id IN ({placeholders}) OR r.target_bo_id IN ({placeholders})
            """
            cursor = data_source.execute(rel_sql, tuple(bo_ids + bo_ids))
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception:
            return 0

    def _batch_count_relations(self, data_source, object_type: str,
                                records: List[Dict], field_key: str, scope: str):
        if object_type == 'business_object' and scope == 'self':
            self._batch_count_bo_relations(data_source, records, field_key)
        elif object_type in ('domain', 'sub_domain', 'service_module') and scope == 'descendants':
            self._batch_count_descendant_relations(data_source, object_type, records, field_key)
        elif object_type == 'user_group' and scope == 'self':
            self._batch_count_user_group_members(data_source, records, field_key)

    def _batch_count_bo_relations(self, data_source, records: List[Dict], field_key: str):
        if not records:
            return

        bo_ids = [r.get('id') for r in records if r.get('id')]
        if not bo_ids:
            return

        try:
            placeholders = ','.join(['?'] * len(bo_ids))
            sql = f"""
                SELECT
                    COALESCE(source_counts.bo_id, target_counts.bo_id) as bo_id,
                    COALESCE(source_counts.cnt, 0) + COALESCE(target_counts.cnt, 0) as total
                FROM (
                    SELECT source_bo_id as bo_id, COUNT(*) as cnt
                    FROM relationships WHERE source_bo_id IN ({placeholders})
                    GROUP BY source_bo_id
                ) source_counts
                FULL OUTER JOIN (
                    SELECT target_bo_id as bo_id, COUNT(*) as cnt
                    FROM relationships WHERE target_bo_id IN ({placeholders})
                    GROUP BY target_bo_id
                ) target_counts
                ON source_counts.bo_id = target_counts.bo_id
            """
            cursor = data_source.execute(sql, tuple(bo_ids + bo_ids))
            count_map = {}
            for row in cursor.fetchall():
                count_map[row[0]] = row[1]

            for record in records:
                record[field_key] = count_map.get(record.get('id'), 0)
        except Exception:
            try:
                sql = """
                    SELECT source_bo_id as bo_id, COUNT(*) as cnt
                    FROM relationships WHERE source_bo_id IN ({})
                    GROUP BY source_bo_id
                """.format(placeholders)
                cursor = data_source.execute(sql, tuple(bo_ids))
                source_map = {row[0]: row[1] for row in cursor.fetchall()}

                sql = """
                    SELECT target_bo_id as bo_id, COUNT(*) as cnt
                    FROM relationships WHERE target_bo_id IN ({})
                    GROUP BY target_bo_id
                """.format(placeholders)
                cursor = data_source.execute(sql, tuple(bo_ids))
                target_map = {row[0]: row[1] for row in cursor.fetchall()}

                all_ids = set(source_map.keys()) | set(target_map.keys())
                count_map = {}
                for bid in all_ids:
                    count_map[bid] = source_map.get(bid, 0) + target_map.get(bid, 0)

                for record in records:
                    record[field_key] = count_map.get(record.get('id'), 0)
            except Exception:
                for record in records:
                    record[field_key] = 0

    def _batch_count_descendant_relations(self, data_source, object_type: str,
                                           records: List[Dict], field_key: str):
        for record in records:
            record_id = record.get('id')
            if record_id:
                record[field_key] = self._count_descendant_relations(
                    data_source, object_type, record_id
                )
            else:
                record[field_key] = 0

    def _batch_count_user_group_members(self, data_source, records: List[Dict], field_key: str):
        if not records:
            return

        group_ids = [r.get('id') for r in records if r.get('id')]
        if not group_ids:
            return

        try:
            placeholders = ','.join(['?'] * len(group_ids))
            sql = f"""
                SELECT group_id, COUNT(*) as member_count
                FROM user_group_members
                WHERE group_id IN ({placeholders})
                GROUP BY group_id
            """
            cursor = data_source.execute(sql, tuple(group_ids))
            count_map = {row[0]: row[1] for row in cursor.fetchall()}

            for record in records:
                record[field_key] = count_map.get(record.get('id'), 0)
        except Exception:
            for record in records:
                record[field_key] = 0

    def invalidate_cache(self, object_type: Optional[str] = None):
        if object_type:
            self._cache.pop(object_type, None)
        else:
            self._cache.clear()

    def compute_by_semantics(self, object_type: str, records: List[Dict],
                             data_source=None) -> List[Dict]:
        if not records:
            return records

        meta_obj = registry.get(object_type)
        if not meta_obj:
            return records

        by_computed = {}
        for f in meta_obj.fields:
            semantics = getattr(f, 'semantics', None)
            if not semantics:
                continue
            cb = getattr(semantics, 'computed_by', None)
            if cb:
                by_computed.setdefault(cb, []).append(f.id)

        if not by_computed:
            return records

        for computed_by_val, field_ids in by_computed.items():
            if computed_by_val == 'hierarchy_scope':
                self._compute_hierarchy_scope(records, field_ids, data_source)

        return records

    def _compute_hierarchy_scope(self, records: List[Dict], field_ids: List[str],
                                  data_source=None):
        from meta.services.cascade_service import HierarchyConfigLoader
        from meta.services.query.computed_utils import ensure_hierarchy_ids_for_relationships

        if data_source:
            ensure_hierarchy_ids_for_relationships(data_source, records)

        for item in records:
            name, scope_id, _ = HierarchyConfigLoader.compute_scope(item)
            if not name:
                name = '同服务模块'
                scope_id = 'same_module'

            value_map = {
                'category_label': name,
                'category_type': scope_id,
            }
            for field_id in field_ids:
                if item.get(field_id) is None:
                    item[field_id] = value_map.get(field_id)


computation_service = ComputationService()
