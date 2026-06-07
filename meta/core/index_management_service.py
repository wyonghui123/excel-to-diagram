# -*- coding: utf-8 -*-
"""
索引管理服务

设计参考：
- Palantir Foundry: Ontology Indexing Service（增量索引 + 监控）
- Salesforce: MT_Indexes 虚拟索引表（元数据驱动索引生命周期管理）
- SAP S/4HANA: CDS Index Management（注解驱动 + 自动维护）
- DataHub: 流式索引管理（Kafka MCE/MAE 事件驱动）

核心职责：
1. 从元数据模型自动创建索引
2. 索引生命周期管理（创建、监控、优化、删除）
3. 索引使用统计和性能监控
4. 增量索引维护
"""

import logging
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from meta.core.models import (
    MetaObject,
    MetaIndex,
    IndexType,
    IndexPriority,
    IndexSource,
    registry,
)
from meta.core.index_rule_engine import IndexRuleEngine
from meta.core.datasource import DataSource

logger = logging.getLogger(__name__)


@dataclass
class IndexExecutionResult:
    """索引执行结果"""
    index_name: str
    table_name: str
    success: bool
    sql: str = ""
    error: str = ""
    duration_ms: float = 0


@dataclass
class IndexStats:
    """索引统计信息"""
    name: str
    table_name: str
    columns: List[str]
    unique: bool
    index_type: str
    priority: str
    source: str
    exists: bool = False
    size_bytes: int = 0
    usage_count: int = -1


class IndexManagementService:
    """索引管理服务
    
    整合索引规则引擎和 SQL 适配器，提供完整的索引生命周期管理。
    
    使用方式：
    ```python
    from meta.core.index_management_service import IndexManagementService
    from meta.core.datasource import DataSource
    
    service = IndexManagementService(data_source)
    
    # 为所有元模型创建索引
    results = service.create_all_indexes()
    
    # 查看索引推导报告
    report = service.get_derivation_report("business_object")
    
    # 查看索引统计
    stats = service.get_index_stats()
    ```
    """
    
    def __init__(self, data_source: DataSource):
        self.ds = data_source
        self.rule_engine = IndexRuleEngine()
        self._execution_log: List[IndexExecutionResult] = []
    
    def create_all_indexes(self, priority_filter: str = None) -> List[IndexExecutionResult]:
        """为所有已注册的元模型创建索引
        
        Args:
            priority_filter: 优先级过滤，仅创建指定优先级的索引
            
        Returns:
            索引执行结果列表
        """
        results = []
        
        for obj_id in registry.list_objects():
            meta_obj = registry.get(obj_id)
            if not meta_obj or not meta_obj.persistent:
                continue
            
            obj_results = self.create_indexes_for_object(meta_obj, priority_filter)
            results.extend(obj_results)
        
        logger.info("索引创建完成: 成功 %d, 失败 %d",
                     sum(1 for r in results if r.success),
                     sum(1 for r in results if not r.success))
        
        return results
    
    def create_indexes_for_object(self, meta_obj: MetaObject,
                                   priority_filter: str = None) -> List[IndexExecutionResult]:
        """为单个元模型创建索引
        
        Args:
            meta_obj: 元数据对象
            priority_filter: 优先级过滤
            
        Returns:
            索引执行结果列表
        """
        if not meta_obj.table_name:
            return []
        
        if not self.ds.table_exists(meta_obj.table_name):
            logger.debug("表 %s 不存在，跳过索引创建", meta_obj.table_name)
            return []
        
        all_indexes = self.rule_engine.derive_indexes(meta_obj)
        results = []
        
        for index in all_indexes:
            if not index.auto_create:
                continue
            
            if priority_filter and index.priority.value != priority_filter:
                continue
            
            if index.index_type == IndexType.FTS:
                result = self._create_fts_index(meta_obj, index)
            elif index.index_type == IndexType.PARTIAL:
                result = self._create_partial_index(meta_obj, index)
            else:
                result = self._create_btree_index(meta_obj, index)
            
            results.append(result)
            self._execution_log.append(result)
        
        return results
    
    def _create_btree_index(self, meta_obj: MetaObject, index: MetaIndex) -> IndexExecutionResult:
        """创建 B-Tree 索引"""
        idx_name = index.name or self._generate_index_name(meta_obj.table_name, index)
        columns = index.db_columns or self._resolve_db_columns(meta_obj, index.fields)
        
        if not columns:
            return IndexExecutionResult(
                index_name=idx_name,
                table_name=meta_obj.table_name,
                success=False,
                error="无法解析索引列",
            )
        
        unique_clause = "UNIQUE" if index.unique else ""
        columns_str = ", ".join(columns)
        
        sql = "CREATE {0} INDEX IF NOT EXISTS {1} ON {2}({3})".format(
            unique_clause, idx_name, meta_obj.table_name, columns_str
        )
        
        start = time.time()
        try:
            self.ds.execute(sql)
            if not getattr(self.ds, 'in_transaction', False):
                self.ds.commit()
            duration = (time.time() - start) * 1000
            
            logger.info("索引创建成功: %s (%.1fms)", idx_name, duration)
            return IndexExecutionResult(
                index_name=idx_name,
                table_name=meta_obj.table_name,
                success=True,
                sql=sql,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error("索引创建失败: %s, 错误: %s", idx_name, str(e))
            return IndexExecutionResult(
                index_name=idx_name,
                table_name=meta_obj.table_name,
                success=False,
                sql=sql,
                error=str(e),
                duration_ms=duration,
            )
    
    def _create_fts_index(self, meta_obj: MetaObject, index: MetaIndex) -> IndexExecutionResult:
        """创建全文索引（SQLite FTS5）"""
        columns = index.db_columns or self._resolve_db_columns(meta_obj, index.fields)
        
        if not columns:
            return IndexExecutionResult(
                index_name=index.name,
                table_name=meta_obj.table_name,
                success=False,
                error="FTS索引缺少列定义",
            )
        
        fts_table = "{0}_fts".format(meta_obj.table_name)
        columns_str = ", ".join(columns)
        
        sql = "CREATE VIRTUAL TABLE IF NOT EXISTS {0} USING fts5({1}, content='{2}')".format(
            fts_table, columns_str, meta_obj.table_name
        )
        
        start = time.time()
        try:
            self.ds.execute(sql)
            
            self._create_fts_sync_triggers(meta_obj.table_name, fts_table, columns)
            
            if not getattr(self.ds, 'in_transaction', False):
                self.ds.commit()
            duration = (time.time() - start) * 1000
            
            return IndexExecutionResult(
                index_name=fts_table,
                table_name=meta_obj.table_name,
                success=True,
                sql=sql,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return IndexExecutionResult(
                index_name=fts_table,
                table_name=meta_obj.table_name,
                success=False,
                sql=sql,
                error=str(e),
                duration_ms=duration,
            )
    
    def _create_fts_sync_triggers(self, table_name: str, fts_table: str, columns: List[str]):
        """创建 FTS 同步触发器（借鉴 Palantir Funnel 增量索引机制）"""
        cols = ", ".join(columns)
        new_vals = ", ".join(["NEW.{0}".format(c) for c in columns])
        old_vals = ", ".join(["OLD.{0}".format(c) for c in columns])
        
        trigger_prefix = "{0}_fts".format(table_name)
        
        try:
            self.ds.execute("""
                CREATE TRIGGER IF NOT EXISTS {0}_ai AFTER INSERT ON {1}
                BEGIN
                    INSERT INTO {2}(rowid, {3}) VALUES (NEW.id, {4});
                END
            """.format(trigger_prefix, table_name, fts_table, cols, new_vals))
            
            self.ds.execute("""
                CREATE TRIGGER IF NOT EXISTS {0}_ad AFTER DELETE ON {1}
                BEGIN
                    INSERT INTO {2}({3}, rowid) VALUES ('delete', OLD.id);
                END
            """.format(trigger_prefix, table_name, fts_table, cols))
            
            self.ds.execute("""
                CREATE TRIGGER IF NOT EXISTS {0}_au AFTER UPDATE ON {1}
                BEGIN
                    INSERT INTO {2}({3}, rowid) VALUES ('delete', OLD.id);
                    INSERT INTO {2}(rowid, {3}) VALUES (NEW.id, {4});
                END
            """.format(trigger_prefix, table_name, fts_table, cols, new_vals))
        except Exception as e:
            logger.warning("FTS同步触发器创建失败: %s", str(e))
    
    def _create_partial_index(self, meta_obj: MetaObject, index: MetaIndex) -> IndexExecutionResult:
        """创建部分索引（带WHERE条件）"""
        idx_name = index.name or self._generate_index_name(meta_obj.table_name, index)
        columns = index.db_columns or self._resolve_db_columns(meta_obj, index.fields)
        
        if not columns or not index.condition:
            return IndexExecutionResult(
                index_name=idx_name,
                table_name=meta_obj.table_name,
                success=False,
                error="部分索引缺少列定义或条件",
            )
        
        unique_clause = "UNIQUE" if index.unique else ""
        columns_str = ", ".join(columns)
        
        sql = "CREATE {0} INDEX IF NOT EXISTS {1} ON {2}({3}) WHERE {4}".format(
            unique_clause, idx_name, meta_obj.table_name, columns_str, index.condition
        )
        
        start = time.time()
        try:
            self.ds.execute(sql)
            if not getattr(self.ds, 'in_transaction', False):
                self.ds.commit()
            duration = (time.time() - start) * 1000
            
            return IndexExecutionResult(
                index_name=idx_name,
                table_name=meta_obj.table_name,
                success=True,
                sql=sql,
                duration_ms=duration,
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return IndexExecutionResult(
                index_name=idx_name,
                table_name=meta_obj.table_name,
                success=False,
                sql=sql,
                error=str(e),
                duration_ms=duration,
            )
    
    def get_derivation_report(self, object_id: str) -> Optional[Dict[str, Any]]:
        """获取索引推导报告"""
        meta_obj = registry.get(object_id)
        if not meta_obj:
            return None
        return self.rule_engine.get_derivation_report(meta_obj)
    
    def get_all_derivation_reports(self) -> List[Dict[str, Any]]:
        """获取所有元模型的索引推导报告"""
        reports = []
        for obj_id in registry.list_objects():
            report = self.get_derivation_report(obj_id)
            if report:
                reports.append(report)
        return reports
    
    def get_index_stats(self, table_name: str = None) -> List[IndexStats]:
        """获取索引统计信息"""
        stats = []
        
        for obj_id in registry.list_objects():
            meta_obj = registry.get(obj_id)
            if not meta_obj or not meta_obj.table_name:
                continue
            
            if table_name and meta_obj.table_name != table_name:
                continue
            
            all_indexes = self.rule_engine.derive_indexes(meta_obj)
            existing_indexes = self._get_existing_indexes(meta_obj.table_name)
            
            for index in all_indexes:
                idx_name = index.name or self._generate_index_name(meta_obj.table_name, index)
                
                stats.append(IndexStats(
                    name=idx_name,
                    table_name=meta_obj.table_name,
                    columns=index.db_columns or index.fields,
                    unique=index.unique,
                    index_type=index.index_type.value,
                    priority=index.priority.value,
                    source=index.source.value,
                    exists=idx_name in existing_indexes,
                ))
        
        return stats
    
    def get_missing_indexes(self) -> List[IndexStats]:
        """获取缺失的索引"""
        all_stats = self.get_index_stats()
        return [s for s in all_stats if not s.exists and s.source != "query_analysis"]
    
    def get_execution_log(self, limit: int = 50) -> List[IndexExecutionResult]:
        """获取索引执行日志"""
        return self._execution_log[-limit:]
    
    def _get_existing_indexes(self, table_name: str) -> Set[str]:
        """获取表上已存在的索引"""
        indexes = set()
        try:
            sql = "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=?"
            cursor = self.ds.execute(sql, (table_name,))
            for row in cursor.fetchall():
                indexes.add(row[0])
        except Exception:
            pass
        return indexes
    
    def _resolve_db_columns(self, meta_obj: MetaObject, field_ids: List[str]) -> List[str]:
        """将字段ID列表解析为数据库列名"""
        columns = []
        for fid in field_ids:
            f = meta_obj.get_field(fid)
            if f and f.db_column:
                columns.append(f.db_column)
            else:
                columns.append(fid)
        return columns
    
    @staticmethod
    def _generate_index_name(table_name: str, index: MetaIndex) -> str:
        """生成索引名称"""
        prefix = "uidx" if index.unique else "idx"
        columns_part = "_".join(index.db_columns or index.fields)
        return "{0}_{1}_{2}".format(prefix, table_name, columns_part)


from typing import Set
