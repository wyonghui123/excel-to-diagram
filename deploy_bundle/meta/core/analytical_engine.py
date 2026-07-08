# -*- coding: utf-8 -*-
"""
分析引擎（Analytical Engine）

核心职责：
1. 从元模型的 analytical_model 定义自动构建 OLAP 查询
2. 支持维度（dimension）和度量（measure）的灵活组合
3. 支持多层 JOIN 路径的维度解析
4. 支持下钻（drill_down）和上卷（roll_up）分析
5. 支持预聚合查询
6. 支持层级维度导航（hierarchy navigation）
7. 支持维度成员发现（dimension member discovery）
8. 支持 OLAP 查询缓存

设计参考：
- SAP CDS View 的 @Analytics 注解
- Salesforce Reports and Dashboards
- Palantir Ontology 的 analytical properties
- SSAS (SQL Server Analysis Services) 的维度层级模型

使用示例：
    from meta.core.analytical_engine import AnalyticalEngine
    
    engine = AnalyticalEngine(data_source)
    
    # 执行 OLAP 查询
    result = engine.execute_olap_query(
        'relationship',
        dimensions=['version_id', 'relation_code'],
        measures=['relation_count'],
        filters={'version_id': 1}
    )
    
    # 下钻分析
    result = engine.drill_down(
        'relationship',
        current_dimensions=['version_id'],
        drill_dimension='relation_code',
        measures=['relation_count'],
        filters={'version_id': 1}
    )
    
    # 层级导航
    nav = engine.get_hierarchy_navigation('relationship', ['version_id'])
    # nav.drill_down_options = ['relation_code', 'source_domain_id']
    # nav.roll_up_options = []
    
    # 维度成员发现
    members = engine.get_dimension_members('relationship', 'relation_code')
    # [{'value': 'DEPENDS_ON', 'display_name': 'DEPENDS_ON', 'count': 42}, ...]
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
import hashlib
import json
import time
import logging

from meta.core.models import registry

logger = logging.getLogger(__name__)


@dataclass
class MeasureDef:
    id: str
    field: str
    aggregation: str
    display_name: str = ""
    format: str = ""


@dataclass
class DimensionDef:
    id: str
    field: str
    display_name: str = ""
    hierarchy_level: int = 0
    join_path: List[Dict[str, str]] = field(default_factory=list)
    parent_dimension: str = ""


@dataclass
class AggregateDef:
    id: str
    name: str
    type: str
    dimensions: List[str] = field(default_factory=list)
    measures: List[str] = field(default_factory=list)
    refresh: str = "on_change"
    storage: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyticalModelDef:
    enabled: bool = False
    fact_table: str = ""
    fact_alias: str = ""
    measures: Dict[str, MeasureDef] = field(default_factory=dict)
    dimensions: Dict[str, DimensionDef] = field(default_factory=dict)
    aggregates: Dict[str, AggregateDef] = field(default_factory=dict)


@dataclass
class HierarchyNavigation:
    object_type: str
    current_dimensions: List[str]
    drill_down_options: List[Dict[str, Any]] = field(default_factory=list)
    roll_up_options: List[Dict[str, Any]] = field(default_factory=list)
    hierarchy_path: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class DimensionMember:
    value: Any
    display_name: str
    count: int = 0


@dataclass
class OlapCacheEntry:
    result: List[Dict[str, Any]]
    created_at: float
    hit_count: int = 0


AGGREGATION_SQL = {
    "count": "COUNT",
    "count_distinct": "COUNT(DISTINCT",
    "sum": "SUM",
    "avg": "AVG",
    "max": "MAX",
    "min": "MIN",
}


class OlapQueryCache:
    def __init__(self, max_size: int = 100, ttl_seconds: int = 300):
        self._cache: Dict[str, OlapCacheEntry] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}

    def _make_key(self, object_type: str, dimensions: List[str],
                  measures: List[str], filters: Optional[Dict[str, Any]],
                  order_by: Optional[List[str]], limit: Optional[int]) -> str:
        payload = json.dumps({
            "ot": object_type,
            "dims": sorted(dimensions),
            "meas": sorted(measures),
            "filt": filters or {},
            "ob": order_by or [],
            "lim": limit,
        }, sort_keys=True, default=str)
        return hashlib.md5(payload.encode()).hexdigest()

    def get(self, object_type: str, dimensions: List[str],
            measures: List[str], filters: Optional[Dict[str, Any]],
            order_by: Optional[List[str]], limit: Optional[int]) -> Optional[List[Dict[str, Any]]]:
        key = self._make_key(object_type, dimensions, measures, filters, order_by, limit)
        entry = self._cache.get(key)
        if entry is None:
            self._stats["misses"] += 1
            return None

        if time.time() - entry.created_at > self._ttl_seconds:
            del self._cache[key]
            self._stats["misses"] += 1
            return None

        entry.hit_count += 1
        self._stats["hits"] += 1
        return entry.result

    def put(self, object_type: str, dimensions: List[str],
            measures: List[str], filters: Optional[Dict[str, Any]],
            order_by: Optional[List[str]], limit: Optional[int],
            result: List[Dict[str, Any]]):
        key = self._make_key(object_type, dimensions, measures, filters, order_by, limit)

        if len(self._cache) >= self._max_size:
            self._evict()

        self._cache[key] = OlapCacheEntry(
            result=result,
            created_at=time.time(),
        )

    def _evict(self):
        if not self._cache:
            return

        oldest_key = min(self._cache, key=lambda k: self._cache[k].created_at)
        del self._cache[oldest_key]
        self._stats["evictions"] += 1

    def invalidate(self, object_type: str = ""):
        if not object_type:
            self._cache.clear()
            return

        keys_to_remove = []
        for key, entry in self._cache.items():
            if any(r.get("_object_type") == object_type for r in entry.result):
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._cache[key]

    def get_stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "ttl_seconds": self._ttl_seconds,
            **self._stats,
        }

    def clear(self):
        self._cache.clear()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}


class AnalyticalEngine:
    def __init__(self, data_source, cache_ttl: int = 300, cache_max_size: int = 100):
        self.ds = data_source
        self._model_cache: Dict[str, AnalyticalModelDef] = {}
        self._query_cache = OlapQueryCache(max_size=cache_max_size, ttl_seconds=cache_ttl)

    def get_analytical_model(self, object_type: str) -> Optional[AnalyticalModelDef]:
        if object_type in self._model_cache:
            return self._model_cache[object_type]

        meta_obj = registry.get(object_type)
        if not meta_obj or not meta_obj.analytical_model:
            return None

        model_def = self._parse_analytical_model(meta_obj.analytical_model)
        self._model_cache[object_type] = model_def
        return model_def

    def _parse_analytical_model(self, data: Dict[str, Any]) -> AnalyticalModelDef:
        model = AnalyticalModelDef(
            enabled=data.get("enabled", False),
        )

        fact_data = data.get("fact", {})
        model.fact_table = fact_data.get("table", "")
        model.fact_alias = fact_data.get("alias", "")

        for m_data in fact_data.get("measures", []):
            measure = MeasureDef(
                id=m_data.get("id", ""),
                field=m_data.get("field", ""),
                aggregation=m_data.get("aggregation", "count"),
                display_name=m_data.get("display_name", ""),
                format=m_data.get("format", ""),
            )
            if measure.id:
                model.measures[measure.id] = measure

        for d_data in data.get("dimensions", []):
            dim = DimensionDef(
                id=d_data.get("id", ""),
                field=d_data.get("field", ""),
                display_name=d_data.get("display_name", ""),
                hierarchy_level=d_data.get("hierarchy_level", 0),
                join_path=d_data.get("join_path", []),
                parent_dimension=d_data.get("parent_dimension", ""),
            )
            if dim.id:
                model.dimensions[dim.id] = dim

        for a_data in data.get("aggregates", []):
            agg = AggregateDef(
                id=a_data.get("id", ""),
                name=a_data.get("name", ""),
                type=a_data.get("type", "materialized"),
                dimensions=a_data.get("dimensions", []),
                measures=a_data.get("measures", []),
                refresh=a_data.get("refresh", "on_change"),
                storage=a_data.get("storage", {}),
            )
            if agg.id:
                model.aggregates[agg.id] = agg

        return model

    def build_star_query(
        self,
        object_type: str,
        dimensions: List[str],
        measures: List[str],
        filters: Optional[Dict[str, Any]] = None
    ) -> tuple:
        model = self.get_analytical_model(object_type)
        if not model or not model.enabled:
            return "", []

        alias = model.fact_alias or "t"

        select_parts = []
        group_by_parts = []
        join_parts = []
        where_parts = []
        params = []
        used_tables: Set[str] = set()

        prev_alias = alias

        for dim_id in dimensions:
            dim = model.dimensions.get(dim_id)
            if not dim:
                continue

            select_parts.append(f"{dim.field} AS {dim_id}")
            group_by_parts.append(dim.field)

            current_prev = prev_alias

            for join_step in dim.join_path:
                table_clause = join_step.get("table", "")
                on_clause = join_step.get("on", "")

                if not table_clause:
                    continue

                table_name = table_clause.split()[0] if table_clause else ""
                table_alias = table_clause.split()[1] if " " in table_clause else table_name

                if table_name in used_tables:
                    current_prev = table_alias
                    continue

                if on_clause:
                    join_parts.append(f"LEFT JOIN {table_clause} ON {on_clause}")
                else:
                    from_field = join_step.get("from", "")
                    to_field = join_step.get("to", "id")

                    if from_field and to_field:
                        join_on = f"{current_prev}.{from_field} = {table_alias}.{to_field}"
                    else:
                        join_on = f"{current_prev}.id = {table_alias}.id"

                    join_parts.append(f"LEFT JOIN {table_clause} ON {join_on}")

                used_tables.add(table_name)
                current_prev = table_alias

        for measure_id in measures:
            measure = model.measures.get(measure_id)
            if not measure:
                continue

            agg_sql = self._build_aggregation(measure.aggregation, measure.field, alias)
            select_parts.append(f"{agg_sql} AS {measure_id}")

        if filters:
            for key, value in filters.items():
                dim = model.dimensions.get(key)
                if dim:
                    where_parts.append(f"{dim.field} = ?")
                    params.append(value)
                elif key == model.fact_alias + ".version_id" or key == "version_id":
                    where_parts.append(f"{alias}.version_id = ?")
                    params.append(value)

        sql = f"SELECT {', '.join(select_parts)}"
        sql += f"\nFROM {model.fact_table} {alias}"

        if join_parts:
            sql += "\n" + "\n".join(join_parts)

        if where_parts:
            sql += f"\nWHERE {' AND '.join(where_parts)}"

        if group_by_parts:
            sql += f"\nGROUP BY {', '.join(group_by_parts)}"

        return sql, params

    def execute_olap_query(
        self,
        object_type: str,
        dimensions: List[str],
        measures: List[str],
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
        limit: Optional[int] = None,
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        if use_cache:
            cached = self._query_cache.get(
                object_type, dimensions, measures, filters, order_by, limit
            )
            if cached is not None:
                return cached

        sql, params = self.build_star_query(object_type, dimensions, measures, filters)

        if not sql:
            return []

        if order_by:
            order_parts = []
            for ob in order_by:
                desc = ob.startswith("-")
                field_name = ob.lstrip("-")
                dim = self.get_analytical_model(object_type).dimensions.get(field_name)
                if dim:
                    order_parts.append(f"{dim.field} {'DESC' if desc else 'ASC'}")
                elif field_name in measures:
                    order_parts.append(f"{field_name} {'DESC' if desc else 'ASC'}")
            if order_parts:
                sql += f"\nORDER BY {', '.join(order_parts)}"

        if limit:
            sql += f"\nLIMIT {limit}"

        try:
            cursor = self.ds.execute(sql, tuple(params))
            columns = [desc[0] for desc in cursor.description]

            results = []
            for row in cursor.fetchall():
                record = dict(zip(columns, row))
                results.append(record)

            if use_cache:
                self._query_cache.put(
                    object_type, dimensions, measures, filters, order_by, limit, results
                )

            return results

        except Exception as e:
            logger.error(
                "[AnalyticalEngine] OLAP 查询失败: %s: %s",
                object_type, str(e)
            )
            return []

    def drill_down(
        self,
        object_type: str,
        current_dimensions: List[str],
        drill_dimension: str,
        measures: List[str],
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        new_dimensions = list(current_dimensions)
        if drill_dimension not in new_dimensions:
            new_dimensions.append(drill_dimension)

        return self.execute_olap_query(
            object_type, new_dimensions, measures, filters
        )

    def roll_up(
        self,
        object_type: str,
        current_dimensions: List[str],
        roll_to_dimensions: List[str],
        measures: List[str],
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        return self.execute_olap_query(
            object_type, roll_to_dimensions, measures, filters
        )

    def get_hierarchy_navigation(
        self,
        object_type: str,
        current_dimensions: List[str]
    ) -> HierarchyNavigation:
        model = self.get_analytical_model(object_type)
        if not model:
            return HierarchyNavigation(
                object_type=object_type,
                current_dimensions=current_dimensions,
            )

        sorted_dims = sorted(
            model.dimensions.values(),
            key=lambda d: (d.hierarchy_level, d.id)
        )

        current_levels = set()
        for dim_id in current_dimensions:
            dim = model.dimensions.get(dim_id)
            if dim:
                current_levels.add(dim.hierarchy_level)

        max_current_level = max(current_levels) if current_levels else 0

        drill_down_options = []
        for dim in sorted_dims:
            if dim.id in current_dimensions:
                continue
            if dim.hierarchy_level > max_current_level or dim.hierarchy_level == 0:
                drill_down_options.append({
                    "dimension_id": dim.id,
                    "display_name": dim.display_name or dim.id,
                    "hierarchy_level": dim.hierarchy_level,
                    "has_join_path": bool(dim.join_path),
                    "is_hierarchical": dim.hierarchy_level > 0,
                })

        roll_up_options = []
        if current_dimensions:
            min_level = min(current_levels) if current_levels else 0
            for dim in sorted_dims:
                if dim.id in current_dimensions:
                    continue
                if 0 < dim.hierarchy_level < min_level:
                    roll_up_options.append({
                        "dimension_id": dim.id,
                        "display_name": dim.display_name or dim.id,
                        "hierarchy_level": dim.hierarchy_level,
                    })

        hierarchy_path = []
        for dim in sorted_dims:
            if dim.hierarchy_level > 0:
                hierarchy_path.append({
                    "level": dim.hierarchy_level,
                    "dimension_id": dim.id,
                    "display_name": dim.display_name or dim.id,
                    "is_active": dim.id in current_dimensions,
                })

        return HierarchyNavigation(
            object_type=object_type,
            current_dimensions=current_dimensions,
            drill_down_options=drill_down_options,
            roll_up_options=roll_up_options,
            hierarchy_path=hierarchy_path,
        )

    def get_dimension_members(
        self,
        object_type: str,
        dimension_id: str,
        filters: Optional[Dict[str, Any]] = None,
        search: Optional[str] = None,
        limit: int = 100
    ) -> List[DimensionMember]:
        model = self.get_analytical_model(object_type)
        if not model or not model.enabled:
            return []

        dim = model.dimensions.get(dimension_id)
        if not dim:
            return []

        alias = model.fact_alias or "t"

        select_parts = [f"{dim.field} AS member_value"]
        join_parts = []
        where_parts = []
        params = []
        used_tables: Set[str] = set()
        current_prev = alias

        for join_step in dim.join_path:
            table_clause = join_step.get("table", "")
            on_clause = join_step.get("on", "")

            if not table_clause:
                continue

            table_name = table_clause.split()[0]
            table_alias = table_clause.split()[1] if " " in table_clause else table_name

            if table_name in used_tables:
                current_prev = table_alias
                continue

            if on_clause:
                join_parts.append(f"LEFT JOIN {table_clause} ON {on_clause}")
            else:
                from_field = join_step.get("from", "")
                to_field = join_step.get("to", "id")
                if from_field and to_field:
                    join_on = f"{current_prev}.{from_field} = {table_alias}.{to_field}"
                else:
                    join_on = f"{current_prev}.id = {table_alias}.id"
                join_parts.append(f"LEFT JOIN {table_clause} ON {join_on}")

            used_tables.add(table_name)
            current_prev = table_alias

        count_expr = "COUNT(*)" if not dim.join_path else f"COUNT(DISTINCT {alias}.id)"
        select_parts.append(f"{count_expr} AS member_count")

        if filters:
            for key, value in filters.items():
                other_dim = model.dimensions.get(key)
                if other_dim and other_dim.id != dimension_id:
                    where_parts.append(f"{other_dim.field} = ?")
                    params.append(value)
                elif key == "version_id":
                    where_parts.append(f"{alias}.version_id = ?")
                    params.append(value)

        if search:
            where_parts.append(f"CAST({dim.field} AS TEXT) LIKE ?")
            params.append(f"%{search}%")

        sql = f"SELECT {', '.join(select_parts)}"
        sql += f"\nFROM {model.fact_table} {alias}"

        if join_parts:
            sql += "\n" + "\n".join(join_parts)

        if where_parts:
            sql += f"\nWHERE {' AND '.join(where_parts)}"

        sql += f"\nGROUP BY {dim.field}"
        sql += "\nORDER BY member_count DESC"
        sql += f"\nLIMIT {limit}"

        try:
            cursor = self.ds.execute(sql, tuple(params))
            members = []
            for row in cursor.fetchall():
                members.append(DimensionMember(
                    value=row[0],
                    display_name=str(row[0]) if row[0] is not None else "",
                    count=row[1] or 0,
                ))
            return members
        except Exception as e:
            logger.error(
                "[AnalyticalEngine] 维度成员查询失败: %s/%s: %s",
                object_type, dimension_id, str(e)
            )
            return []

    def get_dimension_hierarchy(self, object_type: str) -> List[Dict[str, Any]]:
        model = self.get_analytical_model(object_type)
        if not model:
            return []

        dims = sorted(
            model.dimensions.values(),
            key=lambda d: (d.hierarchy_level, d.id)
        )

        return [
            {
                "id": d.id,
                "field": d.field,
                "display_name": d.display_name,
                "hierarchy_level": d.hierarchy_level,
                "has_join_path": bool(d.join_path),
                "parent_dimension": d.parent_dimension,
            }
            for d in dims
        ]

    def get_available_measures(self, object_type: str) -> List[Dict[str, Any]]:
        model = self.get_analytical_model(object_type)
        if not model:
            return []

        return [
            {
                "id": m.id,
                "field": m.field,
                "aggregation": m.aggregation,
                "display_name": m.display_name,
                "format": m.format,
            }
            for m in model.measures.values()
        ]

    def get_aggregate_info(self, object_type: str) -> List[Dict[str, Any]]:
        model = self.get_analytical_model(object_type)
        if not model:
            return []

        return [
            {
                "id": a.id,
                "name": a.name,
                "type": a.type,
                "dimensions": a.dimensions,
                "measures": a.measures,
                "refresh": a.refresh,
                "storage_table": a.storage.get("table", ""),
            }
            for a in model.aggregates.values()
        ]

    def get_analytical_summary(self, object_type: str) -> Dict[str, Any]:
        model = self.get_analytical_model(object_type)
        if not model or not model.enabled:
            return {"enabled": False}

        hierarchy_dims = [d for d in model.dimensions.values() if d.hierarchy_level > 0]
        hierarchy_dims.sort(key=lambda d: d.hierarchy_level)

        return {
            "enabled": model.enabled,
            "fact_table": model.fact_table,
            "dimension_count": len(model.dimensions),
            "measure_count": len(model.measures),
            "aggregate_count": len(model.aggregates),
            "hierarchy_depth": max((d.hierarchy_level for d in hierarchy_dims), default=0),
            "hierarchy_path": [
                {"level": d.hierarchy_level, "id": d.id, "display_name": d.display_name}
                for d in hierarchy_dims
            ],
            "dimensions": self.get_dimension_hierarchy(object_type),
            "measures": self.get_available_measures(object_type),
            "aggregates": self.get_aggregate_info(object_type),
        }

    def get_cache_stats(self) -> Dict[str, Any]:
        return self._query_cache.get_stats()

    def invalidate_cache(self, object_type: str = ""):
        if object_type:
            self._query_cache.invalidate(object_type)
        else:
            self._query_cache.clear()

    def _build_aggregation(self, aggregation: str, field: str, fact_alias: str = "") -> str:
        if "." not in field and fact_alias:
            qualified_field = f"{fact_alias}.{field}"
        else:
            qualified_field = field

        if aggregation == "count_distinct":
            return f"COUNT(DISTINCT {qualified_field})"

        sql_func = AGGREGATION_SQL.get(aggregation, "COUNT")
        return f"{sql_func}({qualified_field})"

    def clear_cache(self):
        self._model_cache.clear()
        self._query_cache.clear()


_engine_instance: Optional[AnalyticalEngine] = None


def get_analytical_engine() -> Optional[AnalyticalEngine]:
    return _engine_instance


def init_analytical_engine(data_source, cache_ttl: int = 300, cache_max_size: int = 100) -> AnalyticalEngine:
    global _engine_instance
    _engine_instance = AnalyticalEngine(data_source, cache_ttl=cache_ttl, cache_max_size=cache_max_size)
    return _engine_instance
