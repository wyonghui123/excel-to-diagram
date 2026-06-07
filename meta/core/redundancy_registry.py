# -*- coding: utf-8 -*-
"""
冗余字段注册表（Redundancy Registry）

核心职责：
1. 从元模型的 semantics.redundancy 声明自动构建冗余字段注册表
2. 按 type 分类索引（stored / virtual / resolution）
3. 提供变更级联链分析
4. 为 WriteGuard、CascadeGuard、EnrichmentEngine 提供数据支持

设计参考：
- SAP CDS View 的冗余字段管理
- Salesforce 的 IsIndexed + Formula Field 机制
- Palantir Ontology 的 derived property 体系

使用示例：
    from meta.core.redundancy_registry import redundancy_registry
    
    # 构建注册表（通常在应用启动时调用）
    redundancy_registry.build_from_registry()
    
    # 获取所有物理冗余字段（需要写入时同步）
    stored_reds = redundancy_registry.get_stored_redundancies()
    
    # 获取某对象的所有冗余字段
    obj_reds = redundancy_registry.get_object_redundancies('relationship')
    
    # 获取变更级联链
    chains = redundancy_registry.get_cascade_chains_for_source('business_object')
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class RedundancyType(Enum):
    """冗余类型枚举"""
    STORED = "stored"          # 物理冗余：存储到数据库，需要一致性保障
    VIRTUAL = "virtual"        # 虚拟冗余：不存储，查询时动态填充
    RESOLUTION = "resolution"  # 解析冗余：用于导入导出时从业务键解析到技术ID


class ConsistencyStrategy(Enum):
    """一致性策略枚举"""
    SYNC_ON_WRITE = "sync_on_write"    # 写入时同步（最强一致性）
    SYNC_ON_READ = "sync_on_read"      # 读取时同步（允许短暂不一致）
    EVENTUAL = "eventual"               # 最终一致性（允许不一致窗口期)


class RepairStrategy(Enum):
    """修复策略枚举"""
    RECOMPUTE = "recompute"    # 重新计算（从权威来源重算）
    RESTORE = "restore"        # 从备份恢复
    NULLIFY = "nullify"        # 置空处理


@dataclass
class JoinStep:
    """JOIN 步骤定义

    用于定义虚拟冗余字段的 JOIN 路径
    """
    table: str           # 表名
    from_field: str      # 当前表的关联字段
    to_field: str        # 目标表的关联字段
    select: str          # 要选择的字段
    # Phase X: 扩展支持固定条件（enum 的特殊 JOIN）
    fixed_conditions: List[tuple] = field(default_factory=list)
    # 例: [("enum_type_id", "=", "relation_type"), ("is_active", "=", 1)]


@dataclass
class ConsistencyConfig:
    """一致性配置"""
    strategy: ConsistencyStrategy = ConsistencyStrategy.SYNC_ON_WRITE
    cascade_on_change: bool = False    # 源对象变更时是否级联更新
    allow_stale: bool = False          # 是否允许不一致
    repair_strategy: RepairStrategy = RepairStrategy.RECOMPUTE


@dataclass
class RedundancyDef:
    """冗余字段定义
    
    完整描述一个冗余字段的元数据
    """
    object_type: str                              # 所属对象类型
    field_id: str                                 # 字段ID
    redundancy_type: RedundancyType               # 冗余类型
    source_field: str                             # 权威来源字段（外键字段）
    derived_from: str                             # 派生来源路径，如 "business_object.code"
    join_path: List[JoinStep] = field(default_factory=list)  # JOIN 路径（用于虚拟冗余）
    consistency: ConsistencyConfig = field(default_factory=ConsistencyConfig)
    
    @property
    def derived_table(self) -> str:
        """获取派生来源的表名"""
        parts = self.derived_from.split('.')
        return parts[0] if len(parts) == 2 else ""
    
    @property
    def derived_field(self) -> str:
        """获取派生来源的字段名"""
        parts = self.derived_from.split('.')
        return parts[1] if len(parts) == 2 else ""
    
    def __repr__(self) -> str:
        return (
            f"RedundancyDef({self.object_type}.{self.field_id}, "
            f"type={self.redundancy_type.value}, "
            f"source={self.source_field}, "
            f"derived={self.derived_from})"
        )


@dataclass
class CascadeChain:
    """变更级联链
    
    描述当源对象变更时，需要级联更新的目标冗余字段
    """
    source_object: str           # 源对象类型（如 business_object）
    source_field: str            # 源字段（如 code）
    target_object: str           # 目标对象类型（如 relationship）
    target_field: str            # 目标冗余字段（如 source_code）
    redundancy_def: RedundancyDef  # 关联的冗余定义
    
    def __repr__(self) -> str:
        return (
            f"CascadeChain({self.source_object}.{self.source_field} → "
            f"{self.target_object}.{self.target_field})"
        )


class RedundancyRegistry:
    """冗余字段注册表
    
    管理所有冗余字段的元数据，提供查询和级联分析功能
    """
    
    def __init__(self):
        self._redundancies: Dict[str, Dict[str, RedundancyDef]] = {}
        self._cascade_chains: List[CascadeChain] = []
        self._built: bool = False
    
    def build_from_registry(self) -> int:
        """从元模型注册表构建冗余注册表
        
        Returns:
            构建的冗余字段数量
        """
        from meta.core.models import registry as meta_registry
        
        total_count = 0
        self._redundancies.clear()
        self._cascade_chains.clear()
        
        for obj_id, meta_obj in meta_registry._objects.items():
            obj_redundancies = {}

            for f in meta_obj.fields:
                redundancy = getattr(f.semantics, 'redundancy', None)
                if redundancy:
                    red_def = self._parse_redundancy(obj_id, f.id, redundancy)
                    if red_def:
                        obj_redundancies[f.id] = red_def
                        total_count += 1

                        if red_def.consistency.cascade_on_change:
                            self._build_cascade_chain(meta_obj, f.id, red_def)

                enum_type_ref = getattr(f.semantics, 'enum_type_ref', None)
                if enum_type_ref:
                    red_def = self._parse_enum_ref(obj_id, f.id, enum_type_ref, f.semantics)
                    if red_def:
                        obj_redundancies[f.id] = red_def
                        total_count += 1
                        logger.info(
                            f"[RedundancyRegistry] Registered enum ref: "
                            f"{obj_id}.{f.id} -> enum_values.{enum_type_ref}"
                        )

            if obj_redundancies:
                self._redundancies[obj_id] = obj_redundancies
        
        self._built = True
        logger.info(
            "[RedundancyRegistry] 构建完成: %d 个冗余字段, %d 条级联链",
            total_count, len(self._cascade_chains)
        )
        
        return total_count
    
    def _parse_redundancy(
        self, 
        object_type: str, 
        field_id: str, 
        redundancy: Dict[str, Any]
    ) -> Optional[RedundancyDef]:
        """解析冗余声明为 RedundancyDef"""
        try:
            red_type_str = redundancy.get('type', 'virtual')
            red_type = RedundancyType(red_type_str)
        except ValueError:
            logger.warning(
                "[RedundancyRegistry] 未知的冗余类型: %s, 对象: %s, 字段: %s",
                red_type_str, object_type, field_id
            )
            return None
        
        join_steps = []
        for step in redundancy.get('join_path', []):
            fixed_conditions = []
            for fc in step.get('fixed_conditions', []):
                if isinstance(fc, dict):
                    for field, value in fc.items():
                        fixed_conditions.append((field, '=', value))
                elif isinstance(fc, (list, tuple)) and len(fc) >= 3:
                    fixed_conditions.append((fc[0], fc[1], fc[2]))
            join_steps.append(JoinStep(
                table=step.get('table', ''),
                from_field=step.get('from', ''),
                to_field=step.get('to', ''),
                select=step.get('select', ''),
                fixed_conditions=fixed_conditions,
            ))
        
        consistency_data = redundancy.get('consistency', {})
        try:
            strategy = ConsistencyStrategy(
                consistency_data.get('strategy', 'sync_on_write')
            )
        except ValueError:
            strategy = ConsistencyStrategy.SYNC_ON_WRITE
        
        try:
            repair_strategy = RepairStrategy(
                consistency_data.get('repair_strategy', 'recompute')
            )
        except ValueError:
            repair_strategy = RepairStrategy.RECOMPUTE
        
        consistency = ConsistencyConfig(
            strategy=strategy,
            cascade_on_change=consistency_data.get('cascade_on_change', False),
            allow_stale=consistency_data.get('allow_stale', False),
            repair_strategy=repair_strategy,
        )
        
        return RedundancyDef(
            object_type=object_type,
            field_id=field_id,
            redundancy_type=red_type,
            source_field=redundancy.get('source_field', ''),
            derived_from=redundancy.get('derived_from', ''),
            join_path=join_steps,
            consistency=consistency,
        )

    def _parse_enum_ref(
        self,
        object_type: str,
        field_id: str,
        enum_type_ref: str,
        semantics
    ) -> Optional[RedundancyDef]:
        """
        解析 semantics.enum_type_ref 声明为 RedundancyDef

        将 enum 关联转换为虚拟冗余字段，与普通 BO 关联统一处理
        """
        db_column = getattr(semantics, 'db_column', None) or field_id

        enum_join_fields = getattr(semantics, 'enum_join_fields', None) or ['name']
        select_field = enum_join_fields[0]

        join_step = JoinStep(
            table='enum_values',
            from_field=db_column,
            to_field='code',
            select=f'{select_field} as {field_id}_{select_field}',
            fixed_conditions=[
                ('enum_type_id', '=', enum_type_ref),
                ('is_active', '=', 1),
            ]
        )

        return RedundancyDef(
            object_type=object_type,
            field_id=field_id,
            redundancy_type=RedundancyType.VIRTUAL,
            source_field=db_column,
            derived_from=f'enum_values.{select_field}',
            join_path=[join_step],
            consistency=ConsistencyConfig(
                strategy=ConsistencyStrategy.SYNC_ON_READ,
                allow_stale=True,
                repair_strategy=RepairStrategy.RECOMPUTE
            )
        )
    
    def _build_cascade_chain(
        self, 
        meta_obj, 
        field_id: str, 
        red_def: RedundancyDef
    ):
        """构建变更级联链"""
        parts = red_def.derived_from.split('.')
        if len(parts) != 2:
            return
        
        source_obj_name, source_field_name = parts
        
        self._cascade_chains.append(CascadeChain(
            source_object=source_obj_name,
            source_field=source_field_name,
            target_object=meta_obj.id,
            target_field=field_id,
            redundancy_def=red_def,
        ))
    
    def get_stored_redundancies(self) -> List[RedundancyDef]:
        """获取所有物理冗余字段（需要写入时同步）"""
        result = []
        for obj_reds in self._redundancies.values():
            for red_def in obj_reds.values():
                if red_def.redundancy_type == RedundancyType.STORED:
                    result.append(red_def)
        return result
    
    def get_virtual_redundancies(self) -> List[RedundancyDef]:
        """获取所有虚拟冗余字段（查询时动态填充）"""
        result = []
        for obj_reds in self._redundancies.values():
            for red_def in obj_reds.values():
                if red_def.redundancy_type == RedundancyType.VIRTUAL:
                    result.append(red_def)
        return result
    
    def get_resolution_redundancies(self) -> List[RedundancyDef]:
        """获取所有解析冗余字段（用于导入导出）"""
        result = []
        for obj_reds in self._redundancies.values():
            for red_def in obj_reds.values():
                if red_def.redundancy_type == RedundancyType.RESOLUTION:
                    result.append(red_def)
        return result
    
    def get_redundancy(self, object_type: str, field_id: str) -> Optional[RedundancyDef]:
        """获取指定对象和字段的冗余定义"""
        return self._redundancies.get(object_type, {}).get(field_id)
    
    def get_object_redundancies(self, object_type: str) -> Dict[str, RedundancyDef]:
        """获取指定对象的所有冗余定义"""
        return self._redundancies.get(object_type, {})
    
    def get_cascade_chains_for_source(self, source_object: str) -> List[CascadeChain]:
        """获取指定源对象的所有级联链"""
        return [
            c for c in self._cascade_chains 
            if c.source_object == source_object
        ]
    
    def get_cascade_chains_for_target(self, target_object: str) -> List[CascadeChain]:
        """获取指定目标对象的所有级联链"""
        return [
            c for c in self._cascade_chains 
            if c.target_object == target_object
        ]
    
    def get_all_cascade_chains(self) -> List[CascadeChain]:
        """获取所有级联链"""
        return self._cascade_chains.copy()
    
    def get_objects_with_stored_redundancy(self) -> Set[str]:
        """获取所有有物理冗余字段的对象类型"""
        result = set()
        for obj_type, obj_reds in self._redundancies.items():
            for red_def in obj_reds.values():
                if red_def.redundancy_type == RedundancyType.STORED:
                    result.add(obj_type)
                    break
        return result
    
    def is_built(self) -> bool:
        """检查注册表是否已构建"""
        return self._built
    
    def clear(self):
        """清空注册表"""
        self._redundancies.clear()
        self._cascade_chains.clear()
        self._built = False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计信息"""
        stored_count = len(self.get_stored_redundancies())
        virtual_count = len(self.get_virtual_redundancies())
        resolution_count = len(self.get_resolution_redundancies())
        
        return {
            "built": self._built,
            "total_redundancies": stored_count + virtual_count + resolution_count,
            "stored_count": stored_count,
            "virtual_count": virtual_count,
            "resolution_count": resolution_count,
            "cascade_chains": len(self._cascade_chains),
            "objects_with_redundancy": list(self._redundancies.keys()),
        }


redundancy_registry = RedundancyRegistry()
