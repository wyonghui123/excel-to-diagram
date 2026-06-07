"""
审计日志验证框架

提供结构化的审计日志内容验证能力，确保日志信息架构合理、内容完整。

核心验证维度：
1. 通用字段验证 — object_type, object_id, action, user, timestamp, trace_id
2. 特定 action 内容验证 — CREATE/UPDATE/DELETE/ASSOCIATE/DISSOCIATE 各有不同要求
3. FK 结构验证 — 外键值应包含目标对象的类型、ID、显示名称
4. 对象标识验证 — 应包含业务 key 和 display_name

使用示例：
    from test_helpers.audit_log_verifier import AuditLogVerifier

    verifier = AuditLogVerifier(data_source)

    # 验证单条日志
    result = verifier.verify(log_record)
    assert result['valid'], result['errors']

    # 验证对象历史
    history = verifier.verify_object_history('business_object', 123)
    assert history['complete'], history['gaps']

    # 验证特定操作
    create_logs = verifier.filter_by_action('CREATE')
    for log in create_logs:
        result = verifier.verify_create_log(log)
        assert result['valid'], result['missing_fields']
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Set, Callable
from datetime import datetime
import json
import re


# ============================================================
# Schema 定义：每种 action 应包含的字段
# ============================================================

@dataclass
class AuditLogSchema:
    """
    审计日志内容 Schema
    
    定义每种 action 类型应包含的字段和格式要求
    """
    
    # 通用必需字段（所有 action 都必须有）
    COMMON_REQUIRED_FIELDS: Set[str] = field(default_factory=lambda: {
        'object_type', 'object_id', 'action', 'user_id', 'created_at'
    })
    
    # 通用可选字段
    COMMON_OPTIONAL_FIELDS: Set[str] = field(default_factory=lambda: {
        'user_name', 'ip_address', 'user_agent', 'trace_id', 'transaction_id',
        'parent_object_type', 'parent_object_id', 'log_category', 'log_level',
        'agent_id', 'agent_session_id', 'tool_call_id'
    })
    
    # 标准 action 类型
    STANDARD_ACTIONS: Set[str] = field(default_factory=lambda: {
        'CREATE', 'UPDATE', 'DELETE', 'ASSOCIATE', 'DISSOCIATE',
        'ASSIGN', 'REVOKE', 'LOGIN', 'LOGOUT'
    })
    
    # 自定义 action 类型（从 YAML 配置加载）
    CUSTOM_ACTIONS: Set[str] = field(default_factory=lambda: {
        'READ_OBJECT', 'UPDATE_OBJECT', 'BULK_CREATE', 'BULK_DELETE',
        'IMPORT', 'EXPORT', 'EXECUTE'
    })
    
    # action 别名映射
    ACTION_ALIASES: Dict[str, str] = field(default_factory=lambda: {
        'UPDATE_OBJECT': 'UPDATE',
        'ASSIGN': 'ASSOCIATE',
        'REVOKE': 'DISSOCIATE',
    })
    
    # CREATE 操作：应包含所有业务字段的 new_value
    CREATE_EXPECTED_PATTERNS: Dict[str, str] = field(default_factory=lambda: {
        'field_coverage': 'all',  # 应覆盖所有业务字段
        'new_value_required': True,
        'old_value_empty': True,
    })
    
    # UPDATE 操作：应包含变更字段的 old_value 和 new_value
    UPDATE_EXPECTED_PATTERNS: Dict[str, str] = field(default_factory=lambda: {
        'field_coverage': 'changed_only',
        'new_value_required': True,
        'old_value_required': True,
    })
    
    # DELETE 操作：应包含所有业务字段的 old_value
    DELETE_EXPECTED_PATTERNS: Dict[str, str] = field(default_factory=lambda: {
        'field_coverage': 'business_only',  # 排除系统字段
        'old_value_required': True,
        'new_value_empty': True,
    })
    
    # ASSOCIATE 操作：应包含关联目标信息
    ASSOCIATE_EXPECTED_PATTERNS: Dict[str, str] = field(default_factory=lambda: {
        'field_name_required': True,
        'new_value_format': 'json',  # 应是 JSON: {target_type, target_id, target_display}
        'target_info_required': True,  # 必须包含目标对象信息
    })
    
    # DISSOCIATE 操作：应包含被移除关联的信息
    DISSOCIATE_EXPECTED_PATTERNS: Dict[str, str] = field(default_factory=lambda: {
        'field_name_required': True,
        'old_value_format': 'json',
        'target_info_required': True,
    })


# ============================================================
# FK 值结构定义
# ============================================================

@dataclass
class FKValueStructure:
    """
    外键值应包含的结构
    
    期望格式：
    {
        "target_type": "business_object",
        "target_id": 123,
        "target_key": "BO_001",
        "target_display": "客户管理"
    }
    """
    
    REQUIRED_FIELDS: Set[str] = field(default_factory=lambda: {
        'target_type', 'target_id'
    })
    
    OPTIONAL_FIELDS: Set[str] = field(default_factory=lambda: {
        'target_key', 'target_display'
    })


# ============================================================
# 对象标识结构定义
# ============================================================

@dataclass
class ObjectIdentityStructure:
    """
    对象标识应包含的结构
    
    期望格式（在 extra_data 或新增字段中）：
    {
        "object_key": "BO_001",
        "object_display_name": "客户管理"
    }
    """
    
    REQUIRED_FIELDS: Set[str] = field(default_factory=lambda: {
        'object_key', 'object_display_name'
    })


# ============================================================
# 验证结果
# ============================================================

@dataclass
class VerificationResult:
    """验证结果"""
    valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(self, msg: str):
        self.errors.append(msg)
        self.valid = False
    
    def add_warning(self, msg: str):
        self.warnings.append(msg)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'valid': self.valid,
            'errors': self.errors,
            'warnings': self.warnings,
            'details': self.details
        }


# ============================================================
# 审计日志验证器
# ============================================================

class AuditLogVerifier:
    """
    审计日志验证器
    
    提供多层验证能力：
    1. 结构验证 — 字段是否存在
    2. 格式验证 — 值格式是否正确
    3. 内容验证 — 内容是否完整、合理
    4. 一致性验证 — 关联数据是否一致
    """
    
    AUDIT_TABLE = "audit_logs"
    
    # 系统字段（DELETE 时不应该记录）
    SYSTEM_FIELDS: Set[str] = {'id', 'created_at', 'updated_at', 'created_by', 'updated_by'}
    
    # FK 字段模式（以 _id 结尾，但不是 id 本身）
    FK_FIELD_PATTERN = re.compile(r'^(?!id$).*_id$')
    
    def __init__(self, data_source=None, schema: AuditLogSchema = None):
        self.ds = data_source
        self.schema = schema or AuditLogSchema()
        self._object_meta_cache: Dict[str, Dict] = {}
    
    # ============================================================
    # 核心验证方法
    # ============================================================
    
    def verify(self, log: Dict[str, Any]) -> VerificationResult:
        """
        验证单条审计日志
        
        Args:
            log: 审计日志记录
            
        Returns:
            VerificationResult
        """
        result = VerificationResult(valid=True)
        
        # 1. 验证通用必需字段
        self._verify_common_fields(log, result)
        
        # 2. 根据 action 类型验证特定内容
        action = log.get('action', '')
        
        # 处理 action 别名
        resolved_action = self.schema.ACTION_ALIASES.get(action, action)
        
        if resolved_action == 'CREATE':
            self._verify_create_log(log, result)
        elif resolved_action == 'UPDATE':
            self._verify_update_log(log, result)
        elif resolved_action == 'DELETE':
            self._verify_delete_log(log, result)
        elif resolved_action in ('ASSOCIATE', 'ASSIGN'):
            self._verify_associate_log(log, result)
        elif resolved_action in ('DISSOCIATE', 'REVOKE'):
            self._verify_dissociate_log(log, result)
        elif action in self.schema.CUSTOM_ACTIONS:
            # 自定义 action：产生 info 提示，不阻止验证
            result.details['custom_action'] = action
            # 可以添加特定验证逻辑
        elif action and action not in self.schema.STANDARD_ACTIONS:
            # 未定义的 action：产生 info 提示
            result.details['undefined_action'] = action
        
        # 3. 验证对象标识
        self._verify_object_identity(log, result)
        
        # 4. 验证 FK 结构
        self._verify_fk_structure(log, result)
        
        return result
    
    def verify_batch(self, logs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        批量验证审计日志
        
        Returns:
            { total, valid_count, invalid_count, results: [...] }
        """
        results = []
        valid_count = 0
        invalid_count = 0
        
        for log in logs:
            result = self.verify(log)
            results.append({
                'log_id': log.get('id'),
                'action': log.get('action'),
                'object_type': log.get('object_type'),
                'object_id': log.get('object_id'),
                **result.to_dict()
            })
            if result.valid:
                valid_count += 1
            else:
                invalid_count += 1
        
        return {
            'total': len(logs),
            'valid_count': valid_count,
            'invalid_count': invalid_count,
            'valid_rate': valid_count / len(logs) if logs else 0,
            'results': results
        }
    
    # ============================================================
    # 通用字段验证
    # ============================================================
    
    def _verify_common_fields(self, log: Dict, result: VerificationResult):
        """验证通用必需字段"""
        for field in self.schema.COMMON_REQUIRED_FIELDS:
            value = log.get(field)
            if value is None or value == '':
                result.add_error(f"缺少必需字段: {field}")
        
        # 验证 action 值
        action = log.get('action', '')
        all_known_actions = self.schema.STANDARD_ACTIONS | self.schema.CUSTOM_ACTIONS
        
        if action:
            if action in self.schema.CUSTOM_ACTIONS:
                # 自定义 action：info 级别
                result.details['action_type'] = 'custom'
            elif action not in self.schema.STANDARD_ACTIONS:
                # 未定义的 action：info 级别（不阻止验证）
                result.details['action_type'] = 'undefined'
        
        # 验证 created_at 格式
        created_at = log.get('created_at')
        if created_at:
            try:
                datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
            except:
                result.add_error(f"created_at 格式无效: {created_at}")
    
    # ============================================================
    # 特定 action 验证
    # ============================================================
    
    def _verify_create_log(self, log: Dict, result: VerificationResult):
        """
        验证 CREATE 日志
        
        期望：
        - 每个业务字段都应有 new_value
        - old_value 应为空
        - 应包含关键业务字段（name, code 等）
        """
        field_name = log.get('field_name', '')
        new_value = log.get('new_value')
        old_value = log.get('old_value')
        
        # old_value 应为空
        if old_value and str(old_value).strip():
            result.add_warning(f"CREATE 操作的 old_value 应为空，实际: {old_value}")
        
        # new_value 不应为空（除非是占位记录）
        if field_name and field_name != '_record' and not new_value:
            result.add_warning(f"CREATE 操作缺少 new_value: field={field_name}")
        
        result.details['field_name'] = field_name
        result.details['has_new_value'] = bool(new_value)
    
    def _verify_update_log(self, log: Dict, result: VerificationResult):
        """
        验证 UPDATE 日志
        
        期望：
        - field_name 应明确
        - old_value 和 new_value 都应有值
        - 值应该不同
        """
        field_name = log.get('field_name', '')
        new_value = log.get('new_value')
        old_value = log.get('old_value')
        
        if not field_name:
            result.add_error("UPDATE 操作缺少 field_name")
        
        # 检查值是否真的变化了
        if old_value == new_value:
            result.add_warning(f"UPDATE 操作值未变化: {field_name} = {old_value}")
        
        result.details['field_name'] = field_name
        result.details['value_changed'] = old_value != new_value
    
    def _verify_delete_log(self, log: Dict, result: VerificationResult):
        """
        验证 DELETE 日志
        
        期望：
        - 应记录所有业务字段的 old_value
        - 不应记录系统字段
        - new_value 应为空
        """
        field_name = log.get('field_name', '')
        old_value = log.get('old_value')
        new_value = log.get('new_value')
        
        # new_value 应为空
        if new_value and str(new_value).strip():
            result.add_warning(f"DELETE 操作的 new_value 应为空，实际: {new_value}")
        
        # 检查是否记录了系统字段
        if field_name in self.SYSTEM_FIELDS:
            result.add_warning(f"DELETE 操作不应记录系统字段: {field_name}")
        
        # old_value 不应为空（业务字段）
        if field_name and field_name not in self.SYSTEM_FIELDS and field_name != '_record':
            if not old_value:
                result.add_warning(f"DELETE 操作缺少 old_value: field={field_name}")
        
        result.details['field_name'] = field_name
        result.details['has_old_value'] = bool(old_value)
    
    def _verify_associate_log(self, log: Dict, result: VerificationResult):
        """
        验证 ASSOCIATE 日志
        
        期望：
        - field_name 应明确（关联字段名）
        - new_value 应包含目标对象信息
        - 目标信息格式：{target_type, target_id, target_display}
        """
        field_name = log.get('field_name', '')
        new_value = log.get('new_value')
        
        if not field_name:
            result.add_error("ASSOCIATE 操作缺少 field_name（关联字段）")
        
        # 解析目标信息
        target_info = self._parse_target_info(new_value)
        if target_info:
            result.details['target_type'] = target_info.get('target_type')
            result.details['target_id'] = target_info.get('target_id')
            result.details['target_display'] = target_info.get('target_display')
            
            # 验证目标信息完整性
            if not target_info.get('target_type'):
                result.add_warning("ASSOCIATE 缺少 target_type")
            if not target_info.get('target_id'):
                result.add_warning("ASSOCIATE 缺少 target_id")
            if not target_info.get('target_display'):
                result.add_warning("ASSOCIATE 缺少 target_display（建议包含）")
        else:
            result.add_warning(f"ASSOCIATE 的 new_value 格式不标准: {new_value}")
    
    def _verify_dissociate_log(self, log: Dict, result: VerificationResult):
        """
        验证 DISSOCIATE 日志
        
        期望：
        - field_name 应明确
        - old_value 应包含被移除关联的目标信息
        """
        field_name = log.get('field_name', '')
        old_value = log.get('old_value')
        
        if not field_name:
            result.add_error("DISSOCIATE 操作缺少 field_name（关联字段）")
        
        # 解析目标信息
        target_info = self._parse_target_info(old_value)
        if target_info:
            result.details['target_type'] = target_info.get('target_type')
            result.details['target_id'] = target_info.get('target_id')
            result.details['target_display'] = target_info.get('target_display')
        else:
            result.add_warning(f"DISSOCIATE 的 old_value 格式不标准: {old_value}")
    
    # ============================================================
    # 对象标识验证
    # ============================================================
    
    def _verify_object_identity(self, log: Dict, result: VerificationResult):
        """
        验证对象标识
        
        期望（在 extra_data 或直接字段中）：
        - object_key: 业务 key
        - object_display_name: 显示名称
        """
        extra_data = log.get('extra_data')
        object_key = log.get('object_key')
        object_display_name = log.get('object_display_name')
        
        # 尝试从 extra_data 解析
        if extra_data:
            try:
                if isinstance(extra_data, str):
                    extra = json.loads(extra_data)
                else:
                    extra = extra_data
                object_key = object_key or extra.get('object_key')
                object_display_name = object_display_name or extra.get('object_display_name')
            except:
                pass
        
        # 检查是否有对象标识
        has_identity = bool(object_key or object_display_name)
        result.details['has_object_key'] = bool(object_key)
        result.details['has_object_display_name'] = bool(object_display_name)
        
        if not has_identity:
            result.add_warning("缺少对象标识（object_key / object_display_name）")
    
    # ============================================================
    # FK 结构验证
    # ============================================================
    
    def _verify_fk_structure(self, log: Dict, result: VerificationResult):
        """
        验证外键值结构
        
        如果 field_name 是 FK 字段（以 _id 结尾），
        其值应包含目标对象信息
        """
        field_name = log.get('field_name', '')
        new_value = log.get('new_value')
        old_value = log.get('old_value')
        
        if not field_name:
            return
        
        # 检查是否是 FK 字段
        if self.FK_FIELD_PATTERN.match(field_name):
            # 验证 new_value
            if new_value:
                target_info = self._parse_target_info(new_value)
                if not target_info:
                    result.add_warning(
                        f"FK 字段 {field_name} 的值应包含目标对象信息: {new_value}"
                    )
            
            # 验证 old_value
            if old_value:
                target_info = self._parse_target_info(old_value)
                if not target_info:
                    result.add_warning(
                        f"FK 字段 {field_name} 的旧值应包含目标对象信息: {old_value}"
                    )
    
    # ============================================================
    # 辅助方法
    # ============================================================
    
    def _parse_target_info(self, value: Any) -> Optional[Dict]:
        """
        解析目标对象信息
        
        支持格式：
        1. JSON 字符串: '{"target_type": "bo", "target_id": 123, ...}'
        2. 字典对象: {'target_type': 'bo', ...}
        """
        if not value:
            return None
        
        try:
            if isinstance(value, str):
                parsed = json.loads(value)
            elif isinstance(value, dict):
                parsed = value
            else:
                return None
            
            # 检查是否有目标信息字段
            if 'target_type' in parsed or 'target_id' in parsed:
                return parsed
            
            return None
        except:
            return None
    
    # ============================================================
    # 对象历史验证
    # ============================================================
    
    def verify_object_history(
        self, 
        object_type: str, 
        object_id: Any,
        expect_actions: List[str] = None
    ) -> Dict[str, Any]:
        """
        验证对象历史记录完整性
        
        Args:
            object_type: 对象类型
            object_id: 对象 ID
            expect_actions: 期望的 action 列表
            
        Returns:
            { logs, verification, gaps, complete }
        """
        if not self.ds:
            return {'error': 'No data source configured'}
        
        # 查询对象历史
        filters = {
            'object_type': object_type,
            'object_id': str(object_id)
        }
        logs = self.ds.find(self.AUDIT_TABLE, filters=filters, order_by="created_at DESC")
        
        # 验证每条日志
        batch_result = self.verify_batch(list(logs))
        
        # 检查期望的 action 是否存在
        actual_actions = set(log.get('action') for log in logs)
        expected_actions = set(expect_actions) if expect_actions else set()
        missing_actions = expected_actions - actual_actions
        
        return {
            'object_type': object_type,
            'object_id': object_id,
            'logs': logs,
            'log_count': len(logs),
            'verification': batch_result,
            'actual_actions': list(actual_actions),
            'missing_actions': list(missing_actions),
            'complete': len(missing_actions) == 0 and batch_result['invalid_count'] == 0
        }
    
    # ============================================================
    # 事务完整性验证
    # ============================================================
    
    def verify_transaction(
        self, 
        transaction_id: str
    ) -> Dict[str, Any]:
        """
        验证事务完整性
        
        同一 transaction_id 的多条日志应该：
        1. 有相同的 user_id, user_name
        2. 有相同或相近的 created_at
        3. 覆盖完整的操作序列
        """
        if not self.ds:
            return {'error': 'No data source configured'}
        
        filters = {'transaction_id': transaction_id}
        logs = self.ds.find(self.AUDIT_TABLE, filters=filters, order_by="created_at ASC")
        
        if not logs:
            return {'error': 'Transaction not found', 'transaction_id': transaction_id}
        
        logs_list = list(logs)
        
        # 验证一致性
        user_ids = set(log.get('user_id') for log in logs_list)
        user_names = set(log.get('user_name') for log in logs_list)
        
        issues = []
        if len(user_ids) > 1:
            issues.append(f"事务内 user_id 不一致: {user_ids}")
        if len(user_names) > 1:
            issues.append(f"事务内 user_name 不一致: {user_names}")
        
        # 验证每条日志
        batch_result = self.verify_batch(logs_list)
        
        # 提取操作序列
        action_sequence = [
            {
                'action': log.get('action'),
                'object_type': log.get('object_type'),
                'field_name': log.get('field_name')
            }
            for log in logs_list
        ]
        
        return {
            'transaction_id': transaction_id,
            'log_count': len(logs_list),
            'user_id': list(user_ids),
            'user_name': list(user_names),
            'action_sequence': action_sequence,
            'issues': issues,
            'verification': batch_result,
            'valid': len(issues) == 0 and batch_result['invalid_count'] == 0
        }
    
    # ============================================================
    # 统计分析
    # ============================================================
    
    def analyze_field_coverage(
        self, 
        object_type: str,
        action: str = None,
        sample_size: int = 100
    ) -> Dict[str, Any]:
        """
        分析字段覆盖率
        
        检查审计日志是否覆盖了所有重要字段
        """
        if not self.ds:
            return {'error': 'No data source configured'}
        
        filters = {'object_type': object_type}
        if action:
            filters['action'] = action
        
        logs = self.ds.find(self.AUDIT_TABLE, filters=filters, order_by="created_at DESC")
        logs_list = list(logs)[:sample_size]
        
        # 统计字段出现频率
        field_counts: Dict[str, int] = {}
        for log in logs_list:
            field_name = log.get('field_name')
            if field_name:
                field_counts[field_name] = field_counts.get(field_name, 0) + 1
        
        # 计算覆盖率
        total_logs = len(logs_list)
        field_coverage = {
            field: {
                'count': count,
                'coverage': count / total_logs if total_logs > 0 else 0
            }
            for field, count in field_counts.items()
        }
        
        return {
            'object_type': object_type,
            'action': action,
            'sample_size': total_logs,
            'unique_fields': len(field_counts),
            'field_coverage': field_coverage,
            'most_common_fields': sorted(
                field_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]
        }


# ============================================================
# 便捷函数
# ============================================================

def create_verifier(data_source=None) -> AuditLogVerifier:
    """创建审计日志验证器"""
    return AuditLogVerifier(data_source)


def quick_verify(log: Dict[str, Any]) -> Dict[str, Any]:
    """快速验证单条日志"""
    verifier = AuditLogVerifier()
    result = verifier.verify(log)
    return result.to_dict()
