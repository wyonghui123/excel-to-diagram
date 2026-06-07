# -*- coding: utf-8 -*-
"""
冗余字段一致性守护（Consistency Guard）

核心职责：
1. WriteGuard - 写入时同步物理冗余字段
2. CascadeGuard - 源对象变更时级联更新下游冗余字段
3. RedundancyAuditor - 定期校验和修复不一致数据

设计参考：
- SAP S/4HANA: CDS View 的冗余字段管理
- Salesforce: Cross-Object Formula Field 的级联更新
- Palantir: Ontology 的 derived property 一致性保障

使用示例：
    from meta.core.consistency_guard import WriteGuard, CascadeGuard
    from meta.core.redundancy_registry import redundancy_registry
    
    # 写入时同步
    write_guard = WriteGuard(data_source, redundancy_registry)
    data = write_guard.on_before_save('relationship', data)
    
    # 变更时级联
    cascade_guard = CascadeGuard(data_source, redundancy_registry)
    cascade_guard.on_after_update('business_object', record_id, {'code': 'NEW_CODE'})
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
import logging

from meta.core.redundancy_registry import (
    RedundancyRegistry,
    RedundancyDef,
    RedundancyType,
    CascadeChain,
    ConsistencyStrategy,
)

logger = logging.getLogger(__name__)


@dataclass
class ConsistencyViolation:
    """一致性违规记录"""
    object_type: str
    record_id: Any
    field_id: str
    expected_value: Any
    actual_value: Any
    severity: str = "high"


class WriteGuard:
    """写入时同步守护
    
    在数据写入数据库前，自动同步所有物理冗余字段。
    
    工作原理：
    1. 从注册表获取当前对象的所有 stored 类型冗余字段
    2. 根据 source_field 获取权威来源的 ID
    3. 根据 derived_from 查询派生值
    4. 自动填充到冗余字段
    
    示例：
        relationship 写入时：
        - source_bo_id = 123 → 查询 business_objects.code → 填充 source_code
        - target_bo_id = 456 → 查询 business_objects.code → 填充 target_code
    """
    
    def __init__(self, data_source, registry: RedundancyRegistry):
        self.ds = data_source
        self.registry = registry
    
    def on_before_save(
        self, 
        object_type: str, 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """保存前自动同步冗余字段
        
        Args:
            object_type: 对象类型
            data: 待保存的数据字典
            
        Returns:
            同步后的数据字典
        """
        obj_reds = self.registry.get_object_redundancies(object_type)
        if not obj_reds:
            return data
        
        stored_reds = {
            fid: red for fid, red in obj_reds.items()
            if red.redundancy_type == RedundancyType.STORED
        }
        
        if not stored_reds:
            return data
        
        data = dict(data)
        
        for field_id, red_def in stored_reds.items():
            source_value = data.get(red_def.source_field)
            
            if source_value is None:
                continue
            
            current_value = data.get(field_id)
            
            expected_value = self._resolve_derived_value(red_def, source_value)
            
            if expected_value is not None:
                if current_value != expected_value:
                    logger.info(
                        "[WriteGuard] %s.%s: 同步冗余字段 %s → %s (来源: %s=%s)",
                        object_type, field_id,
                        current_value, expected_value,
                        red_def.source_field, source_value
                    )
                    data[field_id] = expected_value
        
        return data
    
    def _resolve_derived_value(
        self, 
        red_def: RedundancyDef, 
        source_id: Any
    ) -> Optional[Any]:
        """解析派生值
        
        从 derived_from 路径查询派生值
        例如：business_object.code → 查询 business_objects 表的 code 字段
        """
        derived_table = red_def.derived_table
        derived_field = red_def.derived_field
        
        if not derived_table or not derived_field:
            return None
        
        table_name = self._get_table_name(derived_table)
        
        try:
            sql = f"SELECT {derived_field} FROM {table_name} WHERE id = ?"
            cursor = self.ds.execute(sql, (source_id,))
            row = cursor.fetchone()
            
            if row:
                return row[0]
            else:
                logger.warning(
                    "[WriteGuard] 未找到派生值: %s.%s WHERE id=%s",
                    table_name, derived_field, source_id
                )
                return None
                
        except Exception as e:
            logger.error(
                "[WriteGuard] 查询派生值失败: %s.%s WHERE id=%s: %s",
                table_name, derived_field, source_id, str(e)
            )
            return None
    
    def _get_table_name(self, object_type: str) -> str:
        """获取对象对应的表名"""
        from meta.core.models import registry as meta_registry
        
        meta_obj = meta_registry.get(object_type)
        if meta_obj and meta_obj.table_name:
            return meta_obj.table_name
        
        return f"{object_type}s"


class CascadeGuard:
    """变更时级联更新守护
    
    当源对象的字段变更时，自动级联更新所有依赖该字段的冗余字段。
    
    工作原理：
    1. 从注册表获取以当前对象为源的级联链
    2. 检查变更字段是否在级联链的 source_field 中
    3. 执行级联 UPDATE 更新下游冗余字段
    
    示例：
        business_object.code 变更时：
        - 级联更新 relationship.source_code (WHERE source_bo_id = ?)
        - 级联更新 relationship.target_code (WHERE target_bo_id = ?)
    """
    
    def __init__(self, data_source, registry: RedundancyRegistry):
        self.ds = data_source
        self.registry = registry
    
    def on_after_update(
        self, 
        source_object: str, 
        record_id: Any,
        changed_fields: Dict[str, Any]
    ) -> int:
        """更新后执行级联更新
        
        Args:
            source_object: 源对象类型
            record_id: 变更记录的 ID
            changed_fields: 变更的字段及其新值
            
        Returns:
            更新的记录数
        """
        if not changed_fields:
            return 0
        
        chains = self.registry.get_cascade_chains_for_source(source_object)
        if not chains:
            return 0
        
        total_updated = 0
        
        for chain in chains:
            if chain.source_field not in changed_fields:
                continue
            
            new_value = changed_fields[chain.source_field]
            updated = self._execute_cascade_update(chain, record_id, new_value)
            total_updated += updated
        
        if total_updated > 0:
            logger.info(
                "[CascadeGuard] %s.%s 变更 → 级联更新 %d 条记录",
                source_object, list(changed_fields.keys()), total_updated
            )
        
        return total_updated
    
    def on_after_delete(
        self, 
        source_object: str, 
        record_id: Any
    ) -> int:
        """删除后执行级联处理
        
        当源对象被删除时，相关冗余字段应该如何处理？
        当前策略：不做处理（依赖外键约束或业务逻辑）
        
        Args:
            source_object: 源对象类型
            record_id: 被删除记录的 ID
            
        Returns:
            处理的记录数
        """
        chains = self.registry.get_cascade_chains_for_source(source_object)
        
        for chain in chains:
            logger.warning(
                "[CascadeGuard] %s (id=%s) 被删除，存在级联依赖: %s.%s",
                source_object, record_id,
                chain.target_object, chain.target_field
            )
        
        return 0
    
    def _execute_cascade_update(
        self, 
        chain: CascadeChain, 
        source_id: Any,
        new_value: Any
    ) -> int:
        """执行级联更新"""
        red_def = chain.redundancy_def
        target_table = self._get_table_name(chain.target_object)
        source_fk_field = red_def.source_field
        target_field = red_def.field_id
        
        sql = f"""
            UPDATE {target_table}
            SET {target_field} = ?
            WHERE {source_fk_field} = ?
        """
        
        try:
            cursor = self.ds.execute(sql, (new_value, source_id))
            updated = cursor.rowcount
            
            if updated > 0:
                logger.info(
                    "[CascadeGuard] 级联更新: %s.%s = %s WHERE %s = %s (影响 %d 条)",
                    target_table, target_field, new_value,
                    source_fk_field, source_id, updated
                )
            
            return updated
            
        except Exception as e:
            logger.error(
                "[CascadeGuard] 级联更新失败: %s.%s: %s",
                target_table, target_field, str(e)
            )
            return 0
    
    def _get_table_name(self, object_type: str) -> str:
        """获取对象对应的表名"""
        from meta.core.models import registry as meta_registry
        
        meta_obj = meta_registry.get(object_type)
        if meta_obj and meta_obj.table_name:
            return meta_obj.table_name
        
        return f"{object_type}s"


class ComputedFieldHandler:
    """计算型字段处理器
    
    处理需要根据其他字段计算得出的字段。
    与 WriteGuard 不同，这些字段不是简单的冗余字段，
    而是需要复杂计算逻辑的派生字段。
    
    当前状态：
    - category_label/category_type 已改为 virtual 字段，查询时计算
    - 此类保留作为未来计算型字段的扩展点
    """
    
    def __init__(self, data_source):
        self.ds = data_source
    
    def on_before_save(
        self,
        object_type: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """保存前自动计算字段
        
        Args:
            object_type: 对象类型
            data: 待保存的数据字典
            
        Returns:
            计算后的数据字典
        """
        return data


class RedundancyAuditor:
    """冗余字段审计器
    
    定期校验冗余字段的一致性，并支持修复不一致数据。
    
    工作原理：
    1. 遍历所有 stored 类型的冗余字段
    2. 执行 JOIN 查询比较实际值和期望值
    3. 返回不一致记录列表
    4. 支持修复操作（重新计算）
    """
    
    def __init__(self, data_source, registry: RedundancyRegistry):
        self.ds = data_source
        self.registry = registry
    
    def validate_all(self) -> List[ConsistencyViolation]:
        """校验所有物理冗余字段的一致性
        
        Returns:
            不一致记录列表
        """
        violations = []
        
        for red_def in self.registry.get_stored_redundancies():
            obj_violations = self._validate_redundancy(red_def)
            violations.extend(obj_violations)
        
        if violations:
            logger.warning(
                "[RedundancyAuditor] 发现 %d 条不一致记录",
                len(violations)
            )
        
        return violations
    
    def validate_object(
        self, 
        object_type: str
    ) -> List[ConsistencyViolation]:
        """校验指定对象的冗余字段一致性"""
        violations = []
        
        obj_reds = self.registry.get_object_redundancies(object_type)
        for red_def in obj_reds.values():
            if red_def.redundancy_type == RedundancyType.STORED:
                violations.extend(self._validate_redundancy(red_def))
        
        return violations
    
    def _validate_redundancy(
        self, 
        red_def: RedundancyDef
    ) -> List[ConsistencyViolation]:
        """校验单个冗余字段"""
        violations = []
        
        derived_table = red_def.derived_table
        derived_field = red_def.derived_field
        
        if not derived_table or not derived_field:
            return violations
        
        target_table = self._get_table_name(red_def.object_type)
        derived_table_name = self._get_table_name(derived_table)
        
        sql = f"""
            SELECT t1.id, t1.{red_def.field_id}, t2.{derived_field}
            FROM {target_table} t1
            LEFT JOIN {derived_table_name} t2 ON t1.{red_def.source_field} = t2.id
            WHERE t1.{red_def.field_id} IS NOT NULL
              AND t2.{derived_field} IS NOT NULL
              AND t1.{red_def.field_id} != t2.{derived_field}
        """
        
        try:
            cursor = self.ds.execute(sql)
            
            for row in cursor.fetchall():
                violations.append(ConsistencyViolation(
                    object_type=red_def.object_type,
                    record_id=row[0],
                    field_id=red_def.field_id,
                    expected_value=row[2],
                    actual_value=row[1],
                    severity="high" if not red_def.consistency.allow_stale else "medium",
                ))
                
        except Exception as e:
            logger.error(
                "[RedundancyAuditor] 校验查询失败: %s: %s",
                red_def.object_type, str(e)
            )
        
        return violations
    
    def repair_all(self, dry_run: bool = False) -> Dict[str, Any]:
        """修复所有不一致记录
        
        Args:
            dry_run: 是否仅模拟运行（不实际修复）
            
        Returns:
            修复结果统计
        """
        violations = self.validate_all()
        
        if not violations:
            return {
                "total": 0,
                "repaired": 0,
                "failed": 0,
                "details": [],
            }
        
        repaired = 0
        failed = 0
        details = []
        
        for v in violations:
            result = self._repair_violation(v, dry_run)
            
            if result["success"]:
                repaired += 1
            else:
                failed += 1
            
            details.append(result)
        
        return {
            "total": len(violations),
            "repaired": repaired,
            "failed": failed,
            "details": details,
        }
    
    def _repair_violation(
        self, 
        violation: ConsistencyViolation,
        dry_run: bool
    ) -> Dict[str, Any]:
        """修复单条不一致记录"""
        result = {
            "object_type": violation.object_type,
            "record_id": violation.record_id,
            "field": violation.field_id,
            "action": "would_repair" if dry_run else "repair",
            "from": violation.actual_value,
            "to": violation.expected_value,
            "success": True,
        }
        
        if dry_run:
            return result
        
        table_name = self._get_table_name(violation.object_type)
        
        sql = f"""
            UPDATE {table_name}
            SET {violation.field_id} = ?
            WHERE id = ?
        """
        
        try:
            self.ds.execute(sql, (violation.expected_value, violation.record_id))
            logger.info(
                "[RedundancyAuditor] 修复: %s.%s id=%s: %s → %s",
                violation.object_type, violation.field_id,
                violation.record_id,
                violation.actual_value, violation.expected_value
            )
        except Exception as e:
            result["success"] = False
            result["error"] = str(e)
            logger.error(
                "[RedundancyAuditor] 修复失败: %s.%s id=%s: %s",
                violation.object_type, violation.field_id,
                violation.record_id, str(e)
            )
        
        return result
    
    def _get_table_name(self, object_type: str) -> str:
        """获取对象对应的表名"""
        from meta.core.models import registry as meta_registry
        
        meta_obj = meta_registry.get(object_type)
        if meta_obj and meta_obj.table_name:
            return meta_obj.table_name
        
        return f"{object_type}s"
