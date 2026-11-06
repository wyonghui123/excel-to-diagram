# -*- coding: utf-8 -*-
"""
字段策略引擎

提供字段级别的访问控制策略评估能力，包括：
1. 字段可编辑性策略
2. 字段可见性策略
3. 字段必填性策略

支持基于用户上下文、对象上下文和行数据的动态策略评估。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

# [S7.2 2026-11-06] 修既有缺陷：_evaluate_expression 一直在用 safe_evaluate 但从未 import，
# NameError 被 except Exception 吞掉 → 所有 when_expr 恒为 False。
from meta.core.safe_expr_evaluator import safe_evaluate


@dataclass
class ObjectContext:
    """对象上下文"""
    mutability: Optional[str] = None
    object_type: Optional[str] = None


@dataclass
class UserContext:
    """用户上下文"""
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)


@dataclass
class PolicyContext:
    """策略评估上下文"""
    row: Optional[Dict[str, Any]] = None
    object_context: Optional[ObjectContext] = None
    user_context: Optional[UserContext] = None
    action: str = 'read'
    # [S1 2026-11-06] 当前对象状态值（取自 state_field）；用于状态×字段矩阵求值。
    state: Optional[str] = None


@dataclass
class PolicyRule:
    """策略规则"""
    when_expr: Optional[str] = None
    value: Any = None
    default: bool = False


@dataclass
class EditablePolicy:
    """可编辑策略"""
    determination: List[PolicyRule] = field(default_factory=list)
    default: bool = True


@dataclass
class VisiblePolicy:
    """可见性策略"""
    determination: List[PolicyRule] = field(default_factory=list)
    default: bool = True


@dataclass
class RequiredPolicy:
    """必填性策略"""
    determination: List[PolicyRule] = field(default_factory=list)
    default: bool = False


@dataclass
class FieldPolicy:
    """字段策略声明"""
    editable: Optional[EditablePolicy] = None
    visible: Optional[VisiblePolicy] = None
    required: Optional[RequiredPolicy] = None


class FieldPolicyEngine:
    """字段策略引擎"""
    
    SYSTEM_FIELDS = {
        'created_at', 'updated_at', 'created_by', 'updated_by',
        'created_date', 'updated_date', 'created_user', 'updated_user',
        'is_system', 'system_flag', 'readonly',
        'id', '_id', 'tenant_id'
    }
    
    def __init__(self, meta_object=None, data_source=None):
        self.meta_object = meta_object
        self.data_source = data_source
        self._field_policies: Dict[str, FieldPolicy] = {}
        # [S7.2 2026-11-06] YAML `field_policies:` 声明的对象级策略（含角色 when_expr）；
        # 与 _field_policies（运行时注册）分开：前者在状态矩阵之前求值，后者保持在矩阵之后。
        self._role_policies: Dict[str, FieldPolicy] = {}
        self._load_role_policies()

    def _load_role_policies(self) -> None:
        """从 MetaObject.field_policies 装载对象级字段策略声明。"""
        raw = getattr(self.meta_object, 'field_policies', None)
        if not isinstance(raw, dict):
            return
        for field_id, spec in raw.items():
            if not isinstance(spec, dict):
                continue
            self._role_policies[str(field_id)] = FieldPolicy(
                editable=self._parse_policy_kind(spec.get('editable'), True),
                visible=self._parse_policy_kind(spec.get('visible'), True),
                required=self._parse_policy_kind(spec.get('required'), False),
            )

    @staticmethod
    def _parse_policy_kind(raw, default: bool):
        """把 YAML 的 editable/visible/required 段解析为 *Policy。"""
        if raw is None:
            return None
        if isinstance(raw, list):
            determination_raw, default_value = raw, default
        elif isinstance(raw, dict):
            determination_raw = raw.get('determination') or []
            default_value = bool(raw.get('default', default))
        else:
            return None
        determination = []
        for item in determination_raw:
            if not isinstance(item, dict):
                continue
            determination.append(PolicyRule(
                when_expr=item.get('when') or item.get('when_expr'),
                value=item.get('value'),
                default=bool(item.get('default', False)),
            ))
        if not determination:
            return None
        return EditablePolicy(determination=determination, default=default_value) \
            if default is True else RequiredPolicy(determination=determination, default=default_value)

    def _role_policy(
        self,
        field_id: str,
        kind: str,
        context: Optional[PolicyContext]
    ) -> Optional[bool]:
        """[S7.2] 角色/字段级前置规则：命中返回布尔，未命中返回 None（视为无意见）。"""
        policy = self._role_policies.get(field_id)
        if policy is None:
            return None
        kind_policy = getattr(policy, kind, None)
        if kind_policy is None:
            return None
        for rule in kind_policy.determination:
            if rule.default:
                continue
            if rule.when_expr and self._evaluate_rule(rule, context):
                return bool(rule.value)
        return None
    
    def _is_system_field(self, field_id: str) -> bool:
        """检查是否是系统字段"""
        return field_id.lower() in self.SYSTEM_FIELDS
    
    def _get_field(self, field_id: str):
        """获取字段定义"""
        if not self.meta_object:
            return None
        for field in getattr(self.meta_object, 'fields', []):
            if field.id == field_id:
                return field
        return None
    
    def _is_immutable(self, field) -> bool:
        """检查字段是否标记为 immutable"""
        if not field:
            return False
        semantics = getattr(field, 'semantics', None)
        if not semantics:
            return False
        if isinstance(semantics, dict):
            return semantics.get('immutable', False)
        return getattr(semantics, 'immutable', False)
    
    def _state_policy(self, field_id: str, context: Optional[PolicyContext]) -> Optional[str]:
        """[S1] 返回状态矩阵对该字段的强制策略：hidden / readonly / required；否则 None。

        优先级：hidden > readonly > required（hidden 与 readonly 都禁止写入，
        hidden 更强；required 只在字段可写时才有意义）。
        """
        if not context or not context.state or not self.meta_object:
            return None
        policies = getattr(self.meta_object, 'state_field_policies', None) or {}
        policy = policies.get(context.state)
        if not policy:
            # [S7.4 2026-11-06] 未显式声明时，由 document_profile 推导过账只读兜底。
            try:
                from meta.services.document_invariants import derive_default_state_policy
                derived = derive_default_state_policy(
                    getattr(self.meta_object, 'id', '') or '').get(context.state) or {}
            except Exception:
                derived = {}
            if field_id in (derived.get('readonly') or []):
                return 'readonly'
            return None
        for kind in ('hidden', 'readonly', 'required'):
            if field_id in (getattr(policy, kind, None) or []):
                return kind
        return None

    def is_field_editable(
        self,
        field_id: str,
        context: Optional[PolicyContext] = None
    ) -> bool:
        """
        判断字段是否可编辑
        
        判断优先级：
        1. 系统字段 → 不可编辑
        2. immutable 语义 → 创建时可编辑，更新时不可编辑
        3. ui.editable 显式配置 → 使用配置值
        4. 动态策略规则 → 按规则评估
        5. mutability 逻辑 → 根据对象类型评估
        6. 默认值 → 可编辑
        
        Args:
            field_id: 字段标识
            context: 策略评估上下文
            
        Returns:
            bool: 字段是否可编辑
        """
        if self._is_system_field(field_id):
            return False

        # [S7.2] 角色/对象级字段策略优先（命中即短路；未命中 = 无意见，继续走状态矩阵）。
        _role = self._role_policy(field_id, 'editable', context)
        if _role is not None:
            return _role

        # [S1] 状态×字段矩阵优先（命中即短路），对标 SAP 状态参数文件的字段选择控制。
        if self._state_policy(field_id, context) in ('hidden', 'readonly'):
            return False

        field_def = self._get_field(field_id)
        if self._is_immutable(field_def):
            if context and context.action == 'create':
                return True
            return False
        
        if field_def:
            ui = getattr(field_def, 'ui', None)
            if ui and hasattr(ui, 'editable') and ui.editable is not None:
                return ui.editable
        
        if field_id in self._field_policies:
            policy = self._field_policies[field_id]
            if policy.editable:
                return self._evaluate_editable_policy(policy.editable, context)
        
        if context and context.object_context:
            return self._evaluate_mutability(field_def, context)
        
        if field_def:
            return self._is_field_editable_by_definition(field_def)
        
        return True
    
    def is_field_visible(
        self,
        field_id: str,
        context: Optional[PolicyContext] = None
    ) -> bool:
        """判断字段是否可见"""
        if self._is_system_field(field_id):
            return False

        # [S7.2] 角色/对象级可见性策略优先。
        _role = self._role_policy(field_id, 'visible', context)
        if _role is not None:
            return _role

        # [S1] 状态矩阵 hidden 优先。
        if self._state_policy(field_id, context) == 'hidden':
            return False
        
        if field_id in self._field_policies:
            policy = self._field_policies[field_id]
            if policy.visible:
                return self._evaluate_visible_policy(policy.visible, context)
        
        return True
    
    def is_field_required(
        self,
        field_id: str,
        context: Optional[PolicyContext] = None
    ) -> bool:
        """判断字段是否必填"""
        # [S7.2] 角色/对象级必填策略优先。
        _role = self._role_policy(field_id, 'required', context)
        if _role is not None:
            return _role

        # [S1] 状态矩阵：required 直接为真；hidden 时不要求必填。
        _state_kind = self._state_policy(field_id, context)
        if _state_kind == 'required':
            return True
        if _state_kind == 'hidden':
            return False

        if field_id in self._field_policies:
            policy = self._field_policies[field_id]
            if policy.required:
                return self._evaluate_required_policy(policy.required, context)
        
        field_def = self._get_field(field_id)
        if field_def:
            return self._is_field_required_by_definition(field_def)
        
        return False
    
    def _is_field_editable_by_definition(self, field) -> bool:
        """根据字段定义判断是否可编辑"""
        semantics = getattr(field, 'semantics', None)
        if not semantics:
            return True
        
        if isinstance(semantics, dict):
            if semantics.get('readonly'):
                return False
            if semantics.get('immutable'):
                return False
        
        return not getattr(semantics, 'readonly', False) and not getattr(semantics, 'immutable', False)
    
    def _is_field_required_by_definition(self, field) -> bool:
        """根据字段定义判断是否必填"""
        constraints = getattr(field, 'constraints', None)
        if constraints:
            if isinstance(constraints, dict):
                if constraints.get('required', False):
                    return True
            elif getattr(constraints, 'required', False):
                return True
            # [DECORATIVE] [NEW] v1.2 / FR-4.3: 条件必填 → 保守策略返回 True（UI 显示星号）
            if self._has_conditional_required(constraints):
                return True
        return False

    @staticmethod
    def _has_conditional_required(constraints) -> bool:
        """[DECORATIVE] [NEW] v1.2 / FR-4.3: 检查 constraints 是否声明了 conditional_required

        保守策略：只要有 conditional_required 规则就返回 True，UI 显示星号。
        实际校验由后端 ConstraintEngine 兜底。
        """
        if isinstance(constraints, list):
            return any(
                isinstance(c, dict) and c.get('type') == 'conditional_required'
                for c in constraints
            )
        if isinstance(constraints, dict):
            return constraints.get('type') == 'conditional_required'
        return False
    
    def _evaluate_editable_policy(
        self,
        policy: EditablePolicy,
        context: Optional[PolicyContext]
    ) -> bool:
        """评估可编辑策略"""
        if not policy.determination:
            return policy.default
        
        for rule in policy.determination:
            if rule.default:
                continue
            if self._evaluate_rule(rule, context):
                return rule.value
        
        default_rule = next((r for r in policy.determination if r.default), None)
        return default_rule.value if default_rule else policy.default
    
    def _evaluate_visible_policy(
        self,
        policy: VisiblePolicy,
        context: Optional[PolicyContext]
    ) -> bool:
        """评估可见性策略"""
        if not policy.determination:
            return policy.default
        
        for rule in policy.determination:
            if rule.default:
                continue
            if self._evaluate_rule(rule, context):
                return rule.value
        
        default_rule = next((r for r in policy.determination if r.default), None)
        return default_rule.value if default_rule else policy.default
    
    def _evaluate_required_policy(
        self,
        policy: RequiredPolicy,
        context: Optional[PolicyContext]
    ) -> bool:
        """评估必填性策略"""
        if not policy.determination:
            return policy.default
        
        for rule in policy.determination:
            if rule.default:
                continue
            if self._evaluate_rule(rule, context):
                return rule.value
        
        default_rule = next((r for r in policy.determination if r.default), None)
        return default_rule.value if default_rule else policy.default
    
    def _evaluate_rule(
        self,
        rule: PolicyRule,
        context: Optional[PolicyContext]
    ) -> bool:
        """评估单条策略规则"""
        if not rule.when_expr:
            return True
        
        try:
            return self._evaluate_expression(rule.when_expr, context)
        except Exception:
            return False
    
    def _evaluate_expression(
        self,
        expr: str,
        context: Optional[PolicyContext]
    ) -> bool:
        """评估条件表达式"""
        if not context:
            return False
        
        try:
            local_vars = {
                'row': context.row or {},
                'object': context.object_context,
                'user': context.user_context,
                'action': context.action
            }
            
            result = safe_evaluate(expr, local_vars)
            return bool(result)
        except Exception:
            return False
    
    def register_field_policy(self, field_id: str, policy: FieldPolicy):
        """注册字段策略"""
        self._field_policies[field_id] = policy
    
    def get_field_policy(self, field_id: str) -> Optional[FieldPolicy]:
        """获取字段策略"""
        return self._field_policies.get(field_id)
    
    def clear_policies(self):
        """清除所有已注册的策略"""
        self._field_policies.clear()
    
    def determine_editable(
        self,
        field_id: str,
        context: Optional[PolicyContext] = None
    ) -> bool:
        """
        判定字段是否可编辑（兼容性别名）
        
        这是 is_field_editable 的别名，提供与规范一致的 API。
        
        判断优先级：
        1. 系统字段 → 不可编辑
        2. immutable 语义 → 创建时可编辑，更新时不可编辑
        3. ui.editable 显式配置 → 使用配置值
        4. 动态策略规则 → 按规则评估
        5. mutability 逻辑 → 根据对象类型评估
        6. 默认值 → 可编辑
        
        Args:
            field_id: 字段标识
            context: 策略评估上下文
            
        Returns:
            bool: 字段是否可编辑
        """
        return self.is_field_editable(field_id, context)
    
    def determine_visible(
        self,
        field_id: str,
        context: Optional[PolicyContext] = None
    ) -> bool:
        """
        判定字段是否可见（兼容性别名）
        
        Args:
            field_id: 字段标识
            context: 策略评估上下文
            
        Returns:
            bool: 字段是否可见
        """
        return self.is_field_visible(field_id, context)
    
    def determine_required(
        self,
        field_id: str,
        context: Optional[PolicyContext] = None
    ) -> bool:
        """
        判定字段是否必填（兼容性别名）
        
        Args:
            field_id: 字段标识
            context: 策略评估上下文
            
        Returns:
            bool: 字段是否必填
        """
        return self.is_field_required(field_id, context)
    
    def _evaluate_mutability(self, field, context: PolicyContext) -> bool:
        """
        评估 mutability determination
        
        mutability 控制对象级别的新增和修改权限：
        - locked: 完全锁定，所有字段不可编辑
        - fullEditable: 完全可编辑，所有字段可编辑
        - extensible: 可扩展，非系统字段可编辑
        
        Args:
            field: 字段定义对象
            context: 策略评估上下文
            
        Returns:
            bool: 字段是否可编辑
        """
        if not context or not context.object_context:
            return True
        
        mutability = context.object_context.mutability
        if not mutability:
            return True
        
        if mutability == 'locked':
            return False
        elif mutability == 'fullEditable':
            return True
        elif mutability == 'extensible':
            is_system = getattr(field, 'is_system', None)
            if is_system is None and field:
                row = context.row or {}
                is_system = row.get('is_system', False)
            return not is_system
        
        return True
    
    def is_row_editable(self, context: PolicyContext) -> bool:
        """
        判断整行是否可编辑
        
        基于 mutability 和 action 判断整行的编辑权限。
        
        Args:
            context: 策略评估上下文
            
        Returns:
            bool: 行是否可编辑
        """
        if not context or not context.object_context:
            return True
        
        mutability = context.object_context.mutability
        action = context.action
        
        if mutability == 'locked':
            return False
        
        if mutability == 'fullEditable':
            return True
        
        if mutability == 'extensible':
            if action == 'create':
                return True
            row = context.row or {}
            return not row.get('is_system', False)
        
        return True
    
    def get_editable_fields(
        self,
        field_ids: List[str],
        context: Optional[PolicyContext] = None
    ) -> List[str]:
        """
        获取可编辑的字段列表
        
        Args:
            field_ids: 字段标识列表
            context: 策略评估上下文
            
        Returns:
            List[str]: 可编辑的字段标识列表
        """
        return [
            fid for fid in field_ids
            if self.determine_editable(fid, context)
        ]
    
    def get_readonly_fields(
        self,
        field_ids: List[str],
        context: Optional[PolicyContext] = None
    ) -> List[str]:
        """
        获取只读的字段列表
        
        Args:
            field_ids: 字段标识列表
            context: 策略评估上下文
            
        Returns:
            List[str]: 只读的字段标识列表
        """
        return [
            fid for fid in field_ids
            if not self.determine_editable(fid, context)
        ]
