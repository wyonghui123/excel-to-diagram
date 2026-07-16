# -*- coding: utf-8 -*-
"""
增量索引策略

设计参考：
- Palantir Foundry: Funnel 增量索引管道（基于 Change Log）
- Salesforce: MT_Indexes 增量同步（基于 Metadata Change Event）
- DataHub: MAE (Metadata Audit Event) 驱动增量索引更新
- SAP S/4HANA: CDS Index Rebuild（基于 Transport 变更集）

核心职责：
1. 检测元数据模型变更对索引的影响
2. 增量创建缺失索引（不重建已有索引）
3. 清理废弃索引（字段删除时）
4. 索引版本管理
"""

import logging
import time
from typing import List, Dict, Any, Optional, Set, Tuple
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
class IndexChange:
    """索引变更记录"""
    change_type: str  # "create", "drop", "rebuild"
    index_name: str
    table_name: str
    columns: List[str]
    index_type: IndexType
    source: IndexSource
    reason: str
    sql: str = ""


@dataclass
class IncrementalSyncResult:
    """增量同步结果"""
    created: List[IndexChange] = field(default_factory=list)
    dropped: List[IndexChange] = field(default_factory=list)
    skipped: List[IndexChange] = field(default_factory=list)
    errors: List[Dict[str, str]] = field(default_factory=list)
    duration_ms: float = 0


class IncrementalIndexStrategy:
    """增量索引策略
    
    借鉴 Palantir Funnel 和 Salesforce MT_Indexes 的增量索引机制：
    
    1. 比对当前数据库索引与元数据推导索引的差异
    2. 仅创建缺失的索引（增量创建）
    3. 标记废弃索引（字段已删除但索引仍存在）
    4. 不自动删除索引（需要人工确认）
    
    使用方式：
    ```python
    strategy = IncrementalIndexStrategy(data_source)
    
    # 检测索引变更
    changes = strategy.detect_changes()
    
    # 执行增量同步
    result = strategy.sync()
    ```
    """
    
    def __init__(self, data_source: DataSource):
        self.ds = data_source
        self.rule_engine = IndexRuleEngine()
    
    def detect_changes(self) -> List[IndexChange]:
        """检测索引变更
        
        对比元数据推导索引与数据库实际索引，生成变更列表。
        """
        changes = []
        
        for obj_id in registry.list_objects():
            meta_obj = registry.get(obj_id)
            if not meta_obj or not meta_obj.table_name or not meta_obj.persistent:
                continue
            
            if not self.ds.table_exists(meta_obj.table_name):
                continue
            
            obj_changes = self._detect_object_changes(meta_obj)
            changes.extend(obj_changes)
        
        return changes
    
    def _detect_object_changes(self, meta_obj: MetaObject) -> List[IndexChange]:
        """检测单个元模型的索引变更"""
        changes = []
        
        derived_indexes = self.rule_engine.derive_indexes(meta_obj)
        existing_indexes = self._get_existing_index_info(meta_obj.table_name)
        
        derived_names = set()
        for idx in derived_indexes:
            if not idx.auto_create:
                continue
            
            idx_name = idx.name or self._generate_index_name(meta_obj.table_name, idx)
            derived_names.add(idx_name)
            
            if idx_name not in existing_indexes:
                columns = idx.db_columns or self._resolve_columns(meta_obj, idx.fields)
                changes.append(IndexChange(
                    change_type="create",
                    index_name=idx_name,
                    table_name=meta_obj.table_name,
                    columns=columns,
                    index_type=idx.index_type,
                    source=idx.source,
                    reason="元数据推导索引不存在于数据库",
                ))
        
        for idx_name, idx_info in existing_indexes.items():
            if idx_name.startswith("sqlite_"):
                continue
            
            if idx_name not in derived_names:
                changes.append(IndexChange(
                    change_type="drop",
                    index_name=idx_name,
                    table_name=meta_obj.table_name,
                    columns=idx_info.get("columns", []),
                    index_type=IndexType.BTREE,
                    source=IndexSource.MANUAL,
                    reason="索引不在元数据推导范围内（可能是废弃索引）",
                ))
        
        return changes
    
    def sync(self, auto_create: bool = True, auto_drop: bool = False,
             priority_filter: str = None) -> IncrementalSyncResult:
        """执行增量索引同步
        
        Args:
            auto_create: 是否自动创建缺失索引
            auto_drop: 是否自动删除废弃索引（默认False，需人工确认）
            priority_filter: 优先级过滤
        """
        start = time.time()
        result = IncrementalSyncResult()
        
        changes = self.detect_changes()
        
        for change in changes:
            if change.change_type == "create":
                if priority_filter and change.index_type == IndexType.BTREE:
                    continue
                
                if auto_create:
                    sql = self._generate_create_sql(change)
                    change.sql = sql
                    try:
                        self.ds.execute(sql)
                        if not getattr(self.ds, 'in_transaction', False):
                            self.ds.commit()
                        result.created.append(change)
                        logger.info("增量创建索引: %s", change.index_name)
                    except Exception as e:
                        result.errors.append({
                            "index": change.index_name,
                            "table": change.table_name,
                            "error": str(e),
                        })
                        logger.error("增量创建索引失败: %s, 错误: %s", change.index_name, str(e))
                else:
                    result.skipped.append(change)
            
            elif change.change_type == "drop":
                if auto_drop:
                    sql = "DROP INDEX IF EXISTS {0}".format(change.index_name)
                    change.sql = sql
                    try:
                        self.ds.execute(sql)
                        if not getattr(self.ds, 'in_transaction', False):
                            self.ds.commit()
                        result.dropped.append(change)
                        logger.info("增量删除索引: %s", change.index_name)
                    except Exception as e:
                        result.errors.append({
                            "index": change.index_name,
                            "table": change.table_name,
                            "error": str(e),
                        })
                else:
                    result.skipped.append(change)
        
        result.duration_ms = (time.time() - start) * 1000
        return result
    
    def sync_object(self, meta_obj: MetaObject, auto_create: bool = True,
                     auto_drop: bool = False) -> IncrementalSyncResult:
        """为单个元模型执行增量索引同步"""
        start = time.time()
        result = IncrementalSyncResult()
        
        if not self.ds.table_exists(meta_obj.table_name):
            return result
        
        changes = self._detect_object_changes(meta_obj)
        
        for change in changes:
            if change.change_type == "create" and auto_create:
                sql = self._generate_create_sql(change)
                change.sql = sql
                try:
                    self.ds.execute(sql)
                    if not getattr(self.ds, 'in_transaction', False):
                        self.ds.commit()
                    result.created.append(change)
                except Exception as e:
                    result.errors.append({
                        "index": change.index_name,
                        "table": change.table_name,
                        "error": str(e),
                    })
            elif change.change_type == "drop" and auto_drop:
                sql = "DROP INDEX IF EXISTS {0}".format(change.index_name)
                change.sql = sql
                try:
                    self.ds.execute(sql)
                    if not getattr(self.ds, 'in_transaction', False):
                        self.ds.commit()
                    result.dropped.append(change)
                except Exception as e:
                    result.errors.append({
                        "index": change.index_name,
                        "table": change.table_name,
                        "error": str(e),
                    })
            else:
                result.skipped.append(change)
        
        result.duration_ms = (time.time() - start) * 1000
        return result
    
    def get_stale_indexes(self) -> List[IndexChange]:
        """获取废弃索引列表"""
        changes = self.detect_changes()
        return [c for c in changes if c.change_type == "drop"]
    
    def _get_existing_index_info(self, table_name: str) -> Dict[str, Dict[str, Any]]:
        """获取表上已存在索引的详细信息"""
        indexes = {}
        try:
            sql = "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?"
            cursor = self.ds.execute(sql, (table_name,))
            for row in cursor.fetchall():
                idx_name = row[0]
                idx_sql = row[1] or ""
                
                columns = self._parse_index_columns(idx_sql)
                
                indexes[idx_name] = {
                    "name": idx_name,
                    "sql": idx_sql,
                    "columns": columns,
                }
        except Exception:
            pass
        return indexes
    
    def _parse_index_columns(self, index_sql: str) -> List[str]:
        """从 CREATE INDEX SQL 中解析列名"""
        if not index_sql:
            return []
        
        try:
            paren_start = index_sql.rindex("(")
            paren_end = index_sql.rindex(")")
            cols_str = index_sql[paren_start + 1:paren_end]
            return [c.strip().strip('"').strip("'") for c in cols_str.split(",")]
        except (ValueError, IndexError):
            return []
    
    def _resolve_columns(self, meta_obj: MetaObject, field_ids: List[str]) -> List[str]:
        """将字段ID解析为数据库列名"""
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
        prefix = "uidx" if index.unique else "idx"
        columns_part = "_".join(index.db_columns or index.fields)
        return "{0}_{1}_{2}".format(prefix, table_name, columns_part)
    
    def _generate_create_sql(self, change: IndexChange) -> str:
        """生成 CREATE INDEX SQL"""
        columns_str = ", ".join(change.columns)
        
        if change.index_type == IndexType.PARTIAL:
            return "CREATE INDEX IF NOT EXISTS {0} ON {1}({2})".format(
                change.index_name, change.table_name, columns_str
            )
        elif change.index_type == IndexType.UNIQUE:
            return "CREATE UNIQUE INDEX IF NOT EXISTS {0} ON {1}({2})".format(
                change.index_name, change.table_name, columns_str
            )
        else:
            return "CREATE INDEX IF NOT EXISTS {0} ON {1}({2})".format(
                change.index_name, change.table_name, columns_str
            )
