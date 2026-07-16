# -*- coding: utf-8 -*-
"""
聚合管理器（Aggregate Manager）

核心职责：
1. 管理物化聚合（materialized aggregate）的定义
2. 按需刷新聚合数据（全量刷新 / 增量刷新）
3. 提供缓存查询接口
4. 跟踪聚合数据新鲜度
5. 支持事件驱动的自动刷新

设计参考：
- SAP HANA 的 Calculation View + Materialized View
- Salesforce 的 Summary Custom Object
- Palantir 的 Materialized View

使用示例：
    from meta.core.aggregate_manager import AggregateManager
    
    manager = AggregateManager(data_source)
    
    # 注册聚合定义
    manager.register_from_analytical_model('relationship')
    
    # 全量刷新
    manager.refresh('version_relation_stats')
    
    # 查询聚合数据
    results = manager.query('version_relation_stats', filters={'version_id': 1})
    
    # 检查新鲜度
    freshness = manager.get_freshness('version_relation_stats')
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import logging

from meta.core.models import registry
from meta.core.analytical_engine import AnalyticalEngine, AggregateDef

logger = logging.getLogger(__name__)


@dataclass
class AggregateState:
    """聚合状态"""
    aggregate_id: str
    last_refreshed_at: Optional[str] = None
    row_count: int = 0
    status: str = "empty"


class AggregateManager:
    """聚合管理器
    
    管理物化聚合的创建、刷新和查询。
    聚合数据存储在独立的聚合表中，表名由 analytical_model.aggregates[].storage.table 定义。
    """
    
    AGGREGATE_META_TABLE = "_aggregate_meta"
    
    def __init__(self, data_source):
        self.ds = data_source
        self._aggregate_defs: Dict[str, AggregateDef] = {}
        self._states: Dict[str, AggregateState] = {}
        self._ensure_meta_table()
    
    def _ensure_meta_table(self):
        """确保聚合元数据表存在"""
        sql = f"""
            CREATE TABLE IF NOT EXISTS {self.AGGREGATE_META_TABLE} (
                aggregate_id TEXT PRIMARY KEY,
                last_refreshed_at TEXT,
                row_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'empty'
            )
        """
        try:
            self.ds.execute(sql)
            self.ds.commit()
        except Exception as e:
            logger.warning("[AggregateManager] 创建元数据表失败: %s", str(e))
    
    def register_from_analytical_model(self, object_type: str) -> int:
        """从分析模型注册聚合定义
        
        Args:
            object_type: 对象类型
            
        Returns:
            注册的聚合数量
        """
        engine = AnalyticalEngine(self.ds)
        model = engine.get_analytical_model(object_type)
        
        if not model:
            return 0
        
        count = 0
        for agg_id, agg_def in model.aggregates.items():
            self._aggregate_defs[agg_id] = agg_def
            count += 1
            
            if agg_id not in self._states:
                self._states[agg_id] = AggregateState(aggregate_id=agg_id)
                self._load_state(agg_id)
        
        logger.info(
            "[AggregateManager] 注册 %d 个聚合定义 (对象: %s)",
            count, object_type
        )
        
        return count
    
    def register_all(self) -> int:
        """注册所有对象类型的聚合定义
        
        Returns:
            注册的聚合总数
        """
        total = 0
        for obj_id in registry._objects:
            total += self.register_from_analytical_model(obj_id)
        
        return total
    
    def refresh(self, aggregate_id: str, force: bool = False) -> int:
        """刷新聚合数据（全量刷新）
        
        Args:
            aggregate_id: 聚合ID
            force: 是否强制刷新（忽略缓存TTL）
            
        Returns:
            刷新后的行数
        """
        agg_def = self._aggregate_defs.get(aggregate_id)
        if not agg_def:
            logger.warning("[AggregateManager] 未找到聚合定义: %s", aggregate_id)
            return 0
        
        cache_ttl = agg_def.storage.get("cache_ttl", 0)
        if not force and cache_ttl > 0:
            state = self._states.get(aggregate_id)
            if state and state.last_refreshed_at:
                try:
                    last_refresh = datetime.fromisoformat(state.last_refreshed_at)
                    elapsed = (datetime.now() - last_refresh).total_seconds()
                    if elapsed < cache_ttl:
                        logger.debug(
                            "[AggregateManager] 聚合 %s 缓存未过期 (TTL=%ds, 已过=%ds)",
                            aggregate_id, cache_ttl, int(elapsed)
                        )
                        return state.row_count
                except (ValueError, TypeError):
                    pass
        
        storage_table = agg_def.storage.get("table", f"agg_{aggregate_id}")
        
        engine = AnalyticalEngine(self.ds)
        
        object_type = self._find_object_type_for_aggregate(aggregate_id)
        if not object_type:
            return 0
        
        sql, params = engine.build_star_query(
            object_type,
            dimensions=agg_def.dimensions,
            measures=agg_def.measures
        )
        
        if not sql:
            return 0
        
        try:
            self._ensure_aggregate_table(storage_table, agg_def)
            
            self.ds.execute(f"DELETE FROM {storage_table}")
            
            insert_sql = f"INSERT INTO {storage_table} SELECT * FROM ({sql})"
            self.ds.execute(insert_sql, tuple(params))
            
            cursor = self.ds.execute(f"SELECT COUNT(*) FROM {storage_table}")
            row_count = cursor.fetchone()[0]
            
            self.ds.commit()
            
            state = self._states.get(aggregate_id, AggregateState(aggregate_id=aggregate_id))
            state.last_refreshed_at = datetime.now().isoformat()
            state.row_count = row_count
            state.status = "ready"
            self._states[aggregate_id] = state
            self._save_state(aggregate_id, state)
            
            logger.info(
                "[AggregateManager] 聚合 %s 刷新完成: %d 行",
                aggregate_id, row_count
            )
            
            return row_count
            
        except Exception as e:
            logger.error(
                "[AggregateManager] 聚合 %s 刷新失败: %s",
                aggregate_id, str(e)
            )
            try:
                self.ds.execute("ROLLBACK")
            except Exception:
                pass
            return 0
    
    def refresh_on_change(
        self,
        object_type: str,
        record_id: Any,
        event_type: str
    ) -> int:
        """变更触发的增量刷新
        
        当源数据变更时，检查是否有聚合需要刷新。
        
        Args:
            object_type: 变更的对象类型
            record_id: 变更记录ID
            event_type: 事件类型 (created/updated/deleted)
            
        Returns:
            刷新的聚合数量
        """
        refreshed = 0
        
        for agg_id, agg_def in self._aggregate_defs.items():
            if agg_def.refresh != "on_change":
                continue
            
            source_object = self._find_object_type_for_aggregate(agg_id)
            if source_object == object_type:
                self.refresh(agg_id, force=True)
                refreshed += 1
        
        return refreshed
    
    def query(
        self,
        aggregate_id: str,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """查询聚合数据
        
        Args:
            aggregate_id: 聚合ID
            filters: 过滤条件
            order_by: 排序字段
            limit: 返回数量限制
            
        Returns:
            查询结果列表
        """
        agg_def = self._aggregate_defs.get(aggregate_id)
        if not agg_def:
            return []
        
        storage_table = agg_def.storage.get("table", f"agg_{aggregate_id}")
        
        state = self._states.get(aggregate_id)
        if not state or state.status != "ready":
            self.refresh(aggregate_id)
        
        select_parts = ["*"]
        where_parts = []
        params = []
        
        if filters:
            for key, value in filters.items():
                where_parts.append(f"{key} = ?")
                params.append(value)
        
        sql = f"SELECT {', '.join(select_parts)} FROM {storage_table}"
        
        if where_parts:
            sql += f" WHERE {' AND '.join(where_parts)}"
        
        if order_by:
            order_parts = []
            for ob in order_by:
                desc = ob.startswith("-")
                field_name = ob.lstrip("-")
                order_parts.append(f"{field_name} {'DESC' if desc else 'ASC'}")
            sql += f" ORDER BY {', '.join(order_parts)}"
        
        if limit:
            sql += f" LIMIT {limit}"
        
        try:
            cursor = self.ds.execute(sql, tuple(params))
            columns = [desc[0] for desc in cursor.description]
            
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
            
        except Exception as e:
            logger.error(
                "[AggregateManager] 查询聚合 %s 失败: %s",
                aggregate_id, str(e)
            )
            return []
    
    def get_freshness(self, aggregate_id: str) -> Dict[str, Any]:
        """获取聚合数据新鲜度
        
        Args:
            aggregate_id: 聚合ID
            
        Returns:
            新鲜度信息
        """
        state = self._states.get(aggregate_id)
        if not state:
            return {
                "aggregate_id": aggregate_id,
                "status": "unknown",
                "last_refreshed_at": None,
                "row_count": 0,
                "is_stale": True,
            }
        
        agg_def = self._aggregate_defs.get(aggregate_id)
        cache_ttl = agg_def.storage.get("cache_ttl", 0) if agg_def else 0
        
        is_stale = True
        if state.last_refreshed_at and cache_ttl > 0:
            try:
                last_refresh = datetime.fromisoformat(state.last_refreshed_at)
                elapsed = (datetime.now() - last_refresh).total_seconds()
                is_stale = elapsed > cache_ttl
            except (ValueError, TypeError):
                pass
        elif state.status == "ready":
            is_stale = False
        
        return {
            "aggregate_id": aggregate_id,
            "status": state.status,
            "last_refreshed_at": state.last_refreshed_at,
            "row_count": state.row_count,
            "cache_ttl": cache_ttl,
            "is_stale": is_stale,
        }
    
    def get_all_freshness(self) -> List[Dict[str, Any]]:
        """获取所有聚合的新鲜度"""
        return [
            self.get_freshness(agg_id)
            for agg_id in self._aggregate_defs
        ]
    
    def get_registered_aggregates(self) -> List[Dict[str, Any]]:
        """获取所有已注册的聚合"""
        return [
            {
                "id": agg_id,
                "name": agg_def.name,
                "type": agg_def.type,
                "dimensions": agg_def.dimensions,
                "measures": agg_def.measures,
                "refresh": agg_def.refresh,
                "storage_table": agg_def.storage.get("table", ""),
                "state": {
                    "status": self._states.get(agg_id, AggregateState(aggregate_id=agg_id)).status,
                    "row_count": self._states.get(agg_id, AggregateState(aggregate_id=agg_id)).row_count,
                    "last_refreshed_at": self._states.get(agg_id, AggregateState(aggregate_id=agg_id)).last_refreshed_at,
                },
            }
            for agg_id, agg_def in self._aggregate_defs.items()
        ]
    
    def _ensure_aggregate_table(self, table_name: str, agg_def: AggregateDef):
        """确保聚合表存在"""
        engine = AnalyticalEngine(self.ds)
        
        object_type = self._find_object_type_for_aggregate(agg_def.id)
        if not object_type:
            return
        
        model = engine.get_analytical_model(object_type)
        if not model:
            return
        
        column_defs = []
        for dim_id in agg_def.dimensions:
            dim = model.dimensions.get(dim_id)
            if dim:
                column_defs.append(f"{dim_id} TEXT")
        
        for measure_id in agg_def.measures:
            measure = model.measures.get(measure_id)
            if measure:
                if measure.aggregation in ("count", "sum"):
                    column_defs.append(f"{measure_id} INTEGER")
                else:
                    column_defs.append(f"{measure_id} REAL")
        
        if not column_defs:
            return
        
        sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                {', '.join(column_defs)}
            )
        """
        
        self.ds.execute(sql)
        self.ds.commit()
    
    def _find_object_type_for_aggregate(self, aggregate_id: str) -> Optional[str]:
        """查找聚合所属的对象类型"""
        engine = AnalyticalEngine(self.ds)
        
        for obj_id in registry._objects:
            model = engine.get_analytical_model(obj_id)
            if model and aggregate_id in model.aggregates:
                return obj_id
        
        return None
    
    def _load_state(self, aggregate_id: str):
        """从元数据表加载聚合状态"""
        try:
            cursor = self.ds.execute(
                f"SELECT last_refreshed_at, row_count, status FROM {self.AGGREGATE_META_TABLE} WHERE aggregate_id = ?",
                (aggregate_id,)
            )
            row = cursor.fetchone()
            if row:
                state = self._states.get(aggregate_id)
                if state:
                    state.last_refreshed_at = row[0]
                    state.row_count = row[1] or 0
                    state.status = row[2] or "empty"
        except Exception:
            pass
    
    def _save_state(self, aggregate_id: str, state: AggregateState):
        """保存聚合状态到元数据表"""
        try:
            self.ds.execute(
                f"DELETE FROM {self.AGGREGATE_META_TABLE} WHERE aggregate_id = ?",
                (aggregate_id,)
            )
            self.ds.execute(
                f"INSERT INTO {self.AGGREGATE_META_TABLE} (aggregate_id, last_refreshed_at, row_count, status) VALUES (?, ?, ?, ?)",
                (aggregate_id, state.last_refreshed_at, state.row_count, state.status)
            )
            self.ds.commit()
        except Exception as e:
            logger.warning("[AggregateManager] 保存状态失败: %s", str(e))


_manager_instance: Optional[AggregateManager] = None


def get_aggregate_manager() -> Optional[AggregateManager]:
    """获取全局 AggregateManager 实例"""
    return _manager_instance


def init_aggregate_manager(data_source) -> AggregateManager:
    """初始化全局 AggregateManager 实例"""
    global _manager_instance
    _manager_instance = AggregateManager(data_source)
    _manager_instance.register_all()
    return _manager_instance
