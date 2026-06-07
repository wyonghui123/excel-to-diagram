# -*- coding: utf-8 -*-
"""
索引监控与自动优化

设计参考：
- Palantir Foundry: Ontology Health Monitor（索引健康度检测）
- Salesforce: Query Plan Analyzer（查询计划分析 + 索引推荐）
- SAP S/4HANA: SQL Monitor + Index Advisor（SQL监控 + 索引顾问）
- DataHub: Search Index Health Check（搜索索引健康检查）

核心职责：
1. 索引使用率监控（SQLite 不支持直接统计，通过查询模式分析）
2. 索引健康度检测（冗余索引、重复索引、未使用索引）
3. 索引推荐（基于查询模式分析）
4. 索引优化建议
"""

import logging
import time
from typing import List, Dict, Any, Optional, Set
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
class IndexHealthIssue:
    """索引健康问题"""
    severity: str  # "critical", "warning", "info"
    issue_type: str  # "missing", "redundant", "duplicate", "suboptimal"
    index_name: str
    table_name: str
    description: str
    recommendation: str


@dataclass
class IndexHealthReport:
    """索引健康报告"""
    table_name: str
    object_id: str
    total_indexes: int
    derived_indexes: int
    existing_indexes: int
    missing_indexes: int
    redundant_indexes: int
    health_score: float  # 0-100
    issues: List[IndexHealthIssue] = field(default_factory=list)


class IndexMonitor:
    """索引监控器
    
    借鉴 Palantir Health Monitor 和 Salesforce Query Plan Analyzer：
    
    1. 健康度检测
       - 缺失索引：元数据推导存在但数据库不存在
       - 冗余索引：被更宽的复合索引覆盖的单列索引
       - 重复索引：相同列的多个索引
       - 次优索引：查询模式与索引不匹配
    
    2. 优化建议
       - 合并冗余索引为复合索引
       - 推荐缺失索引
       - 标记可删除的废弃索引
    """
    
    def __init__(self, data_source: DataSource):
        self.ds = data_source
        self.rule_engine = IndexRuleEngine()
    
    def get_health_report(self, object_id: str = None) -> List[IndexHealthReport]:
        """获取索引健康报告"""
        reports = []
        
        for obj_id in registry.list_objects():
            if object_id and obj_id != object_id:
                continue
            
            meta_obj = registry.get(obj_id)
            if not meta_obj or not meta_obj.table_name or not meta_obj.persistent:
                continue
            
            report = self._analyze_object_health(meta_obj)
            reports.append(report)
        
        return reports
    
    def _analyze_object_health(self, meta_obj: MetaObject) -> IndexHealthReport:
        """分析单个元模型的索引健康度"""
        derived_indexes = self.rule_engine.derive_indexes(meta_obj)
        existing_indexes = self._get_existing_indexes(meta_obj.table_name)
        
        derived_names = set()
        for idx in derived_indexes:
            idx_name = idx.name or self._generate_index_name(meta_obj.table_name, idx)
            derived_names.add(idx_name)
        
        existing_names = set(existing_indexes.keys())
        
        missing = derived_names - existing_names
        extra = existing_names - derived_names
        
        issues = []
        
        for idx_name in missing:
            idx = next((i for i in derived_indexes if i.name == idx_name), None)
            priority = idx.priority.value if idx else "medium"
            severity = "critical" if priority == "high" else "warning"
            issues.append(IndexHealthIssue(
                severity=severity,
                issue_type="missing",
                index_name=idx_name,
                table_name=meta_obj.table_name,
                description="元数据推导索引 {0} 不存在于数据库".format(idx_name),
                recommendation="执行增量索引同步创建缺失索引",
            ))
        
        redundant = self._detect_redundant_indexes(meta_obj, derived_indexes, existing_indexes)
        for idx_name, reason in redundant:
            issues.append(IndexHealthIssue(
                severity="info",
                issue_type="redundant",
                index_name=idx_name,
                table_name=meta_obj.table_name,
                description=reason,
                recommendation="考虑删除冗余索引以减少写入开销",
            ))
        
        for idx_name in extra:
            if idx_name.startswith("sqlite_") or idx_name.startswith("idx_"):
                continue
            issues.append(IndexHealthIssue(
                severity="info",
                issue_type="extra",
                index_name=idx_name,
                table_name=meta_obj.table_name,
                description="索引 {0} 不在元数据推导范围内".format(idx_name),
                recommendation="确认是否为手动创建的索引，如废弃可删除",
            ))
        
        total = len(derived_names)
        existing_count = len(derived_names & existing_names)
        health_score = (existing_count / total * 100) if total > 0 else 100
        
        return IndexHealthReport(
            table_name=meta_obj.table_name,
            object_id=meta_obj.id,
            total_indexes=total,
            derived_indexes=len(derived_indexes),
            existing_indexes=len(existing_names),
            missing_indexes=len(missing),
            redundant_indexes=len(redundant),
            health_score=round(health_score, 1),
            issues=issues,
        )
    
    def _detect_redundant_indexes(self, meta_obj: MetaObject,
                                   derived_indexes: List[MetaIndex],
                                   existing_indexes: Dict[str, Dict]) -> List[tuple]:
        """检测冗余索引
        
        规则：如果一个单列索引的列是某个复合索引的前缀，
        则该单列索引是冗余的（SQLite B-Tree 索引的最左前缀原则）。
        """
        redundant = []
        
        composite_columns = []
        for idx in derived_indexes:
            if idx.index_type == IndexType.COMPOSITE and len(idx.fields) > 1:
                columns = idx.db_columns or self._resolve_columns(meta_obj, idx.fields)
                composite_columns.append(columns)
        
        for idx in derived_indexes:
            if len(idx.fields) == 1 and idx.index_type != IndexType.UNIQUE:
                columns = idx.db_columns or self._resolve_columns(meta_obj, idx.fields)
                if columns:
                    for comp_cols in composite_columns:
                        if len(comp_cols) > 1 and comp_cols[0] == columns[0]:
                            idx_name = idx.name or self._generate_index_name(meta_obj.table_name, idx)
                            redundant.append((
                                idx_name,
                                "单列索引 {0} 被复合索引前缀覆盖".format(columns[0])
                            ))
                            break
        
        return redundant
    
    def get_optimization_recommendations(self) -> List[Dict[str, Any]]:
        """获取索引优化建议"""
        recommendations = []
        reports = self.get_health_report()
        
        for report in reports:
            for issue in report.issues:
                if issue.issue_type == "missing" and issue.severity == "critical":
                    recommendations.append({
                        "priority": "P0",
                        "table": report.table_name,
                        "action": "create_index",
                        "index_name": issue.index_name,
                        "reason": issue.description,
                        "recommendation": issue.recommendation,
                    })
            
            for issue in report.issues:
                if issue.issue_type == "missing" and issue.severity == "warning":
                    recommendations.append({
                        "priority": "P1",
                        "table": report.table_name,
                        "action": "create_index",
                        "index_name": issue.index_name,
                        "reason": issue.description,
                        "recommendation": issue.recommendation,
                    })
            
            for issue in report.issues:
                if issue.issue_type == "redundant":
                    recommendations.append({
                        "priority": "P2",
                        "table": report.table_name,
                        "action": "consider_drop",
                        "index_name": issue.index_name,
                        "reason": issue.description,
                        "recommendation": issue.recommendation,
                    })
        
        return recommendations
    
    def get_summary(self) -> Dict[str, Any]:
        """获取索引监控摘要"""
        reports = self.get_health_report()
        
        total_tables = len(reports)
        total_indexes = sum(r.total_indexes for r in reports)
        total_missing = sum(r.missing_indexes for r in reports)
        total_redundant = sum(r.redundant_indexes for r in reports)
        
        critical_issues = sum(
            1 for r in reports for i in r.issues if i.severity == "critical"
        )
        warning_issues = sum(
            1 for r in reports for i in r.issues if i.severity == "warning"
        )
        
        avg_health = sum(r.health_score for r in reports) / total_tables if total_tables > 0 else 100
        
        return {
            "total_tables": total_tables,
            "total_derived_indexes": total_indexes,
            "total_missing_indexes": total_missing,
            "total_redundant_indexes": total_redundant,
            "critical_issues": critical_issues,
            "warning_issues": warning_issues,
            "average_health_score": round(avg_health, 1),
            "tables": [
                {
                    "table": r.table_name,
                    "object_id": r.object_id,
                    "derived": r.derived_indexes,
                    "existing": r.existing_indexes,
                    "missing": r.missing_indexes,
                    "redundant": r.redundant_indexes,
                    "health_score": r.health_score,
                }
                for r in reports
            ],
        }
    
    def _get_existing_indexes(self, table_name: str) -> Dict[str, Dict]:
        """获取表上已存在的索引"""
        indexes = {}
        try:
            sql = "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=?"
            cursor = self.ds.execute(sql, (table_name,))
            for row in cursor.fetchall():
                indexes[row[0]] = {"name": row[0], "sql": row[1] or ""}
        except Exception:
            pass
        return indexes
    
    def _resolve_columns(self, meta_obj: MetaObject, field_ids: List[str]) -> List[str]:
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
