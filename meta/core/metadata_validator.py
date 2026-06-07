# -*- coding: utf-8 -*-
"""
元数据验证器（Metadata Validator）

核心职责：
1. 验证 source_of_truth 与 derivation 一致性
2. 检测 derivation 规则缺失时报错
3. 检测 redundant_storage 技术债务时输出警告
4. 输出 errors, warnings, tech_debts 三类结果

设计原则：
- 单一事实源（Single Source of Truth）：确保数据来源明确
- 规则完整性：派生字段必须有对应的派生规则
- 技术债务可见性：冗余存储作为技术债务被追踪

使用示例：
    from meta.core.metadata_validator import MetadataValidator
    
    validator = MetadataValidator()
    results = validator.validate_all()
    validator.log_results(results)
    
    if results['has_errors']:
        raise ValidationError("元数据验证失败")
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set
from enum import Enum
import logging

from meta.core.models import (
    MetaObject,
    MetaField,
    MetaDerivation,
    RuleType,
    registry as meta_registry,
)

logger = logging.getLogger(__name__)


class ValidationLevel(Enum):
    """验证级别"""
    ERROR = "error"
    WARNING = "warning"
    TECH_DEBT = "tech_debt"
    INFO = "info"


@dataclass
class ValidationResult:
    """验证结果项"""
    level: ValidationLevel
    object_id: str
    field_id: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        return f"[{self.level.value.upper()}] {self.object_id}.{self.field_id}: {self.message}"


@dataclass
class ValidationReport:
    """验证报告"""
    errors: List[ValidationResult] = field(default_factory=list)
    warnings: List[ValidationResult] = field(default_factory=list)
    tech_debts: List[ValidationResult] = field(default_factory=list)
    info: List[ValidationResult] = field(default_factory=list)
    
    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0
    
    @property
    def has_tech_debts(self) -> bool:
        return len(self.tech_debts) > 0
    
    @property
    def total_issues(self) -> int:
        return len(self.errors) + len(self.warnings) + len(self.tech_debts)
    
    def add_result(self, result: ValidationResult):
        """添加验证结果"""
        if result.level == ValidationLevel.ERROR:
            self.errors.append(result)
        elif result.level == ValidationLevel.WARNING:
            self.warnings.append(result)
        elif result.level == ValidationLevel.TECH_DEBT:
            self.tech_debts.append(result)
        else:
            self.info.append(result)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "has_errors": self.has_errors,
            "has_warnings": self.has_warnings,
            "has_tech_debts": self.has_tech_debts,
            "total_issues": self.total_issues,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "tech_debt_count": len(self.tech_debts),
            "info_count": len(self.info),
            "errors": [
                {
                    "object_id": r.object_id,
                    "field_id": r.field_id,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.errors
            ],
            "warnings": [
                {
                    "object_id": r.object_id,
                    "field_id": r.field_id,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.warnings
            ],
            "tech_debts": [
                {
                    "object_id": r.object_id,
                    "field_id": r.field_id,
                    "message": r.message,
                    "details": r.details,
                }
                for r in self.tech_debts
            ],
        }


class MetadataValidator:
    """元数据验证器
    
    验证元模型的完整性和一致性，确保：
    1. source_of_truth 声明的字段有对应的 derivation 规则
    2. redundant_storage 策略被正确标记为技术债务
    3. 字段的派生逻辑与 source_of_truth 一致
    
    验证规则：
    - ERROR: source_of_truth 声明但缺少 derivation 规则
    - ERROR: derivation 规则引用了不存在的源对象
    - WARNING: derivation 规则的 from 与 source_of_truth 不一致
    - TECH_DEBT: 使用 redundant_storage 策略的字段
    """
    
    def __init__(self, registry=None):
        self.registry = registry or meta_registry
        self._validated_objects: Set[str] = set()
    
    def validate_all(self) -> ValidationReport:
        """验证所有元对象
        
        Returns:
            ValidationReport: 验证报告
        """
        report = ValidationReport()
        self._validated_objects.clear()
        
        all_objects = self.registry.get_all()
        
        for obj_id, meta_obj in all_objects.items():
            self._validated_objects.add(obj_id)
            self._validate_object(meta_obj, report)
        
        self._validate_cross_object_consistency(report)
        
        logger.info(
            "[MetadataValidator] 验证完成: %d 错误, %d 警告, %d 技术债务",
            len(report.errors), len(report.warnings), len(report.tech_debts)
        )
        
        return report
    
    def validate_object(self, object_id: str) -> ValidationReport:
        """验证单个元对象
        
        Args:
            object_id: 对象ID
            
        Returns:
            ValidationReport: 验证报告
        """
        report = ValidationReport()
        
        meta_obj = self.registry.get(object_id)
        if not meta_obj:
            report.add_result(ValidationResult(
                level=ValidationLevel.ERROR,
                object_id=object_id,
                field_id="",
                message=f"对象 '{object_id}' 不存在于注册表中",
                details={"object_id": object_id}
            ))
            return report
        
        self._validate_object(meta_obj, report)
        
        return report
    
    def _validate_object(self, meta_obj: MetaObject, report: ValidationReport):
        """验证单个元对象的内部一致性"""
        for field in meta_obj.fields:
            self._validate_field(meta_obj, field, report)
        
        self._validate_derivations(meta_obj, report)
    
    def _validate_field(
        self, 
        meta_obj: MetaObject, 
        field: MetaField, 
        report: ValidationReport
    ):
        """验证字段的元数据一致性"""
        semantics = field.semantics
        
        source_of_truth = getattr(semantics, 'source_of_truth', None) or \
                         semantics.custom.get('source_of_truth')
        
        derivation = getattr(semantics, 'derivation', None) or \
                    semantics.custom.get('derivation')
        
        materialization = getattr(semantics, 'redundancy', None) or \
                         semantics.custom.get('materialization')
        
        if source_of_truth:
            self._validate_source_of_truth(
                meta_obj, field, source_of_truth, derivation, report
            )
        
        if materialization:
            self._validate_materialization(
                meta_obj, field, materialization, report
            )
        
        if derivation and not source_of_truth:
            report.add_result(ValidationResult(
                level=ValidationLevel.WARNING,
                object_id=meta_obj.id,
                field_id=field.id,
                message="字段有 derivation 规则但未声明 source_of_truth",
                details={
                    "derivation": derivation,
                    "suggestion": f"建议添加 source_of_truth 声明以明确数据来源"
                }
            ))
    
    def _validate_source_of_truth(
        self,
        meta_obj: MetaObject,
        field: MetaField,
        source_of_truth: str,
        derivation: Optional[Dict[str, Any]],
        report: ValidationReport
    ):
        """验证 source_of_truth 一致性
        
        检查：
        1. source_of_truth 引用的对象是否存在
        2. 是否有对应的 derivation 规则
        3. derivation 规则的 from 是否与 source_of_truth 一致
        """
        source_obj = self.registry.get(source_of_truth)
        if not source_obj:
            report.add_result(ValidationResult(
                level=ValidationLevel.ERROR,
                object_id=meta_obj.id,
                field_id=field.id,
                message=f"source_of_truth '{source_of_truth}' 引用的对象不存在",
                details={
                    "source_of_truth": source_of_truth,
                    "available_objects": list(self.registry.list_objects())
                }
            ))
            return
        
        if not derivation:
            has_derivation_rule = self._check_derivation_rule_exists(
                meta_obj, field, source_of_truth
            )
            
            if not has_derivation_rule:
                report.add_result(ValidationResult(
                    level=ValidationLevel.ERROR,
                    object_id=meta_obj.id,
                    field_id=field.id,
                    message=f"source_of_truth '{source_of_truth}' 声明但缺少 derivation 规则",
                    details={
                        "source_of_truth": source_of_truth,
                        "suggestion": f"请添加 derivation 规则定义字段如何从 '{source_of_truth}' 派生"
                    }
                ))
        else:
            derivation_from = derivation.get('from', '')
            if derivation_from and derivation_from != source_of_truth:
                report.add_result(ValidationResult(
                    level=ValidationLevel.WARNING,
                    object_id=meta_obj.id,
                    field_id=field.id,
                    message=f"derivation.from '{derivation_from}' 与 source_of_truth '{source_of_truth}' 不一致",
                    details={
                        "source_of_truth": source_of_truth,
                        "derivation_from": derivation_from,
                        "suggestion": "确保 derivation.from 与 source_of_truth 一致"
                    }
                ))
            
            derivation_rule = derivation.get('rule', '')
            if not derivation_rule:
                report.add_result(ValidationResult(
                    level=ValidationLevel.WARNING,
                    object_id=meta_obj.id,
                    field_id=field.id,
                    message="derivation 规则缺少 rule 表达式",
                    details={
                        "derivation": derivation,
                        "suggestion": "请添加 rule 表达式定义派生逻辑"
                    }
                ))
    
    def _check_derivation_rule_exists(
        self,
        meta_obj: MetaObject,
        field: MetaField,
        source_of_truth: str
    ) -> bool:
        """检查是否存在对应的派生规则
        
        检查 MetaObject.rules 中是否有 MetaDerivation 规则
        指向该字段
        """
        for rule in meta_obj.rules:
            if isinstance(rule, MetaDerivation):
                if field.id in rule.get_target_fields():
                    if rule.source_object == source_of_truth:
                        return True
        
        return False
    
    def _validate_materialization(
        self,
        meta_obj: MetaObject,
        field: MetaField,
        materialization: Dict[str, Any],
        report: ValidationReport
    ):
        """验证物化策略
        
        检测 redundant_storage 作为技术债务
        """
        strategy = materialization.get('strategy', '')
        
        if strategy == 'redundant_storage':
            description = materialization.get('description', '')
            
            report.add_result(ValidationResult(
                level=ValidationLevel.TECH_DEBT,
                object_id=meta_obj.id,
                field_id=field.id,
                message="字段使用 redundant_storage 策略，存在数据冗余",
                details={
                    "strategy": strategy,
                    "description": description,
                    "sync_policy": materialization.get('sync_policy', ''),
                    "suggestion": "考虑将字段改为 virtual 类型，通过查询时 JOIN 获取数据"
                }
            ))
        
        redundancy_type = materialization.get('type', '')
        if redundancy_type == 'stored':
            consistency = materialization.get('consistency', {})
            allow_stale = consistency.get('allow_stale', False)
            
            if allow_stale:
                report.add_result(ValidationResult(
                    level=ValidationLevel.WARNING,
                    object_id=meta_obj.id,
                    field_id=field.id,
                    message="冗余字段允许数据不一致 (allow_stale=true)",
                    details={
                        "consistency": consistency,
                        "suggestion": "请评估数据不一致的风险，考虑使用更严格的一致性策略"
                    }
                ))
    
    def _validate_derivations(self, meta_obj: MetaObject, report: ValidationReport):
        """验证对象的派生规则
        
        检查：
        1. 派生规则引用的源对象是否存在
        2. 派生规则引用的字段是否存在
        """
        derivations = meta_obj.get_derivations()
        
        for derivation in derivations:
            if derivation.source_object:
                source_obj = self.registry.get(derivation.source_object)
                if not source_obj:
                    report.add_result(ValidationResult(
                        level=ValidationLevel.ERROR,
                        object_id=meta_obj.id,
                        field_id="",
                        message=f"派生规则 '{derivation.id}' 引用的源对象 '{derivation.source_object}' 不存在",
                        details={
                            "rule_id": derivation.id,
                            "source_object": derivation.source_object,
                        }
                    ))
                else:
                    for source_field_id in derivation.source_fields:
                        source_field = source_obj.get_field(source_field_id)
                        if not source_field:
                            report.add_result(ValidationResult(
                                level=ValidationLevel.WARNING,
                                object_id=meta_obj.id,
                                field_id="",
                                message=f"派生规则 '{derivation.id}' 引用的源字段 '{source_field_id}' 在对象 '{derivation.source_object}' 中不存在",
                                details={
                                    "rule_id": derivation.id,
                                    "source_object": derivation.source_object,
                                    "source_field": source_field_id,
                                }
                            ))
            
            for target_field_id in derivation.get_target_fields():
                target_field = meta_obj.get_field(target_field_id)
                if not target_field:
                    report.add_result(ValidationResult(
                        level=ValidationLevel.WARNING,
                        object_id=meta_obj.id,
                        field_id="",
                        message=f"派生规则 '{derivation.id}' 的目标字段 '{target_field_id}' 在当前对象中不存在",
                        details={
                            "rule_id": derivation.id,
                            "target_field": target_field_id,
                        }
                    ))
    
    def _validate_cross_object_consistency(self, report: ValidationReport):
        """验证跨对象一致性
        
        检查：
        1. 冗余字段的派生来源是否有效
        2. 级联更新链是否形成循环
        """
        from meta.core.redundancy_registry import redundancy_registry
        
        if not redundancy_registry.is_built():
            redundancy_registry.build_from_registry()
        
        for red_def in redundancy_registry.get_stored_redundancies():
            derived_table = red_def.derived_table
            derived_field = red_def.derived_field
            
            if derived_table:
                source_obj = self.registry.get(derived_table)
                if not source_obj:
                    report.add_result(ValidationResult(
                        level=ValidationLevel.ERROR,
                        object_id=red_def.object_type,
                        field_id=red_def.field_id,
                        message=f"冗余字段的派生来源对象 '{derived_table}' 不存在",
                        details={
                            "derived_from": red_def.derived_from,
                            "redundancy_type": red_def.redundancy_type.value,
                        }
                    ))
                elif derived_field:
                    source_field = source_obj.get_field(derived_field)
                    if not source_field:
                        report.add_result(ValidationResult(
                            level=ValidationLevel.WARNING,
                            object_id=red_def.object_type,
                            field_id=red_def.field_id,
                            message=f"冗余字段的派生来源字段 '{derived_field}' 在对象 '{derived_table}' 中不存在",
                            details={
                                "derived_from": red_def.derived_from,
                                "source_object": derived_table,
                            }
                        ))
        
        self._check_circular_cascade(report)
    
    def _check_circular_cascade(self, report: ValidationReport):
        """检查级联更新链是否存在循环"""
        from meta.core.redundancy_registry import redundancy_registry
        
        chains = redundancy_registry.get_all_cascade_chains()
        
        graph: Dict[str, Set[str]] = {}
        for chain in chains:
            source_key = f"{chain.source_object}.{chain.source_field}"
            target_key = f"{chain.target_object}.{chain.target_field}"
            
            if source_key not in graph:
                graph[source_key] = set()
            graph[source_key].add(target_key)
        
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str, path: List[str]) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor, path + [neighbor]):
                        return True
                elif neighbor in rec_stack:
                    cycle_path = path + [neighbor]
                    report.add_result(ValidationResult(
                        level=ValidationLevel.ERROR,
                        object_id="",
                        field_id="",
                        message=f"检测到级联更新循环: {' -> '.join(cycle_path)}",
                        details={
                            "cycle_path": cycle_path,
                        }
                    ))
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in graph:
            if node not in visited:
                has_cycle(node, [node])
    
    def log_results(self, report: ValidationReport, log_level: str = "INFO"):
        """输出验证结果
        
        Args:
            report: 验证报告
            log_level: 日志级别 (INFO, WARNING, ERROR)
        """
        log_func = getattr(logger, log_level.lower(), logger.info)
        
        print("\n" + "=" * 60)
        print("元数据验证报告")
        print("=" * 60)
        
        if report.errors:
            print(f"\n[错误] ({len(report.errors)} 条)")
            print("-" * 40)
            for i, error in enumerate(report.errors, 1):
                print(f"  {i}. {error.object_id}.{error.field_id}")
                print(f"     {error.message}")
                if error.details.get('suggestion'):
                    print(f"     建议: {error.details['suggestion']}")
        
        if report.warnings:
            print(f"\n[警告] ({len(report.warnings)} 条)")
            print("-" * 40)
            for i, warning in enumerate(report.warnings, 1):
                print(f"  {i}. {warning.object_id}.{warning.field_id}")
                print(f"     {warning.message}")
                if warning.details.get('suggestion'):
                    print(f"     建议: {warning.details['suggestion']}")
        
        if report.tech_debts:
            print(f"\n[技术债务] ({len(report.tech_debts)} 条)")
            print("-" * 40)
            for i, debt in enumerate(report.tech_debts, 1):
                print(f"  {i}. {debt.object_id}.{debt.field_id}")
                print(f"     {debt.message}")
                if debt.details.get('suggestion'):
                    print(f"     建议: {debt.details['suggestion']}")
        
        print("\n" + "-" * 60)
        print(f"总计: {report.total_issues} 个问题")
        print(f"  - 错误: {len(report.errors)}")
        print(f"  - 警告: {len(report.warnings)}")
        print(f"  - 技术债务: {len(report.tech_debts)}")
        print("=" * 60 + "\n")
        
        log_func(
            "[MetadataValidator] 验证结果: %d 错误, %d 警告, %d 技术债务",
            len(report.errors), len(report.warnings), len(report.tech_debts)
        )
    
    def get_validation_summary(self, report: ValidationReport) -> str:
        """获取验证摘要字符串
        
        Args:
            report: 验证报告
            
        Returns:
            验证摘要字符串
        """
        lines = [
            "元数据验证摘要:",
            f"  错误: {len(report.errors)}",
            f"  警告: {len(report.warnings)}",
            f"  技术债务: {len(report.tech_debts)}",
        ]
        
        if report.has_errors:
            lines.append("  状态: 验证失败 (存在错误)")
        elif report.has_warnings:
            lines.append("  状态: 验证通过 (存在警告)")
        elif report.has_tech_debts:
            lines.append("  状态: 验证通过 (存在技术债务)")
        else:
            lines.append("  状态: 验证通过")
        
        return "\n".join(lines)


metadata_validator = MetadataValidator()
