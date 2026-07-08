# -*- coding: utf-8 -*-
"""
FieldPolicyValidationInterceptor - FieldPolicy 验证拦截器

在 API Service 层独立做 FieldPolicy validation，防止恶意请求绕过前端直接调用 API。

功能：
1. 创建前验证 - 验证创建操作中的字段是否符合 FieldPolicy
2. 更新前验证 - 验证更新操作中的字段是否符合 FieldPolicy
3. mutability 验证 - 验证操作是否符合对象的 mutability 限制
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass

from meta.services.field_policy_engine import FieldPolicyEngine, PolicyContext, ObjectContext

logger = logging.getLogger(__name__)


@dataclass
class ValidationError:
    """验证错误"""
    field_id: str
    field_name: str
    message: str
    error_code: str = "FIELD_POLICY_VIOLATION"


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    errors: List[ValidationError] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def add_error(self, error: ValidationError):
        self.errors.append(error)
        self.valid = False
    
    def get_error_message(self) -> str:
        if not self.errors:
            return ""
        return "; ".join([e.message for e in self.errors])


class FieldPolicyValidationInterceptor:
    """FieldPolicy 验证拦截器"""
    
    def __init__(self, meta_object=None, data_source=None):
        self.meta_object = meta_object
        self.data_source = data_source
        self.engine = FieldPolicyEngine(meta_object, data_source)
    
    def validate_create(
        self,
        data: Dict[str, Any],
        user_context: Optional[Dict] = None
    ) -> ValidationResult:
        """
        创建前验证
        
        Args:
            data: 创建的数据
            user_context: 用户上下文
            
        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult(valid=True)
        
        # 构建上下文
        context = self._build_context(data, 'create', user_context)
        
        # 检查对象级别权限
        if not self._check_object_create_permission(context):
            result.add_error(ValidationError(
                field_id="",
                field_name="",
                message="当前对象不允许创建操作",
                error_code="OBJECT_NOT_CREATABLE"
            ))
            return result
        
        # 验证每个字段
        # [FIX 2026-06-09] 修复新建用户保存报错：
        # 创建上下文中非可编辑字段（ui.editable: false 或系统字段）由后端自动管理
        # （如 must_change_password 由 action_executor 根据是否生成临时密码自动设置，
        # created_at 由 _prepare_data 自动填充）。前端表单可能因 schema 默认值附带
        # 这些字段，校验时应跳过，避免阻断合法创建请求。
        for field_id, value in data.items():
            if not self._is_data_field(field_id, value):
                continue

            if not self.engine.determine_editable(field_id, context):
                # 非可编辑字段在 CREATE 上下文中由后端自动管理，跳过校验
                continue

            field_error = self._validate_field_editable(field_id, context)
            if field_error:
                result.add_error(field_error)

        return result

    def validate_update(
        self,
        object_id: Any,
        data: Dict[str, Any],
        user_context: Optional[Dict] = None
    ) -> ValidationResult:
        """
        更新前验证
        
        Args:
            object_id: 对象 ID
            data: 更新的数据
            user_context: 用户上下文
            
        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult(valid=True)
        
        # 加载旧数据
        old_data = self._load_old_data(object_id)
        is_new = old_data is None
        
        if is_new:
            # 如果旧数据不存在，视为创建操作
            return self.validate_create(data, user_context)
        
        # 构建上下文
        context = self._build_context(data, 'update', user_context, old_data)
        
        # 检查对象级别权限
        if not self._check_object_update_permission(context, old_data):
            result.add_error(ValidationError(
                field_id="",
                field_name="",
                message="当前对象不允许更新操作",
                error_code="OBJECT_NOT_UPDATABLE"
            ))
            return result
        
        # 验证每个字段
        for field_id, value in data.items():
            if not self._is_data_field(field_id, value):
                continue
            
            field_error = self._validate_field_editable(field_id, context)
            if field_error:
                result.add_error(field_error)
        
        return result
    
    def validate_delete(
        self,
        object_id: Any,
        user_context: Optional[Dict] = None
    ) -> ValidationResult:
        """
        删除前验证
        
        Args:
            object_id: 对象 ID
            user_context: 用户上下文
            
        Returns:
            ValidationResult: 验证结果
        """
        result = ValidationResult(valid=True)
        
        # 加载旧数据
        old_data = self._load_old_data(object_id)
        if not old_data:
            result.add_error(ValidationError(
                field_id="",
                field_name="",
                message="对象不存在",
                error_code="OBJECT_NOT_FOUND"
            ))
            return result
        
        # 构建上下文
        context = self._build_context(old_data, 'delete', user_context, old_data)
        
        # 检查对象级别权限
        if not self._check_object_delete_permission(context, old_data):
            result.add_error(ValidationError(
                field_id="",
                field_name="",
                message="当前对象不允许删除操作",
                error_code="OBJECT_NOT_DELETABLE"
            ))
        
        return result
    
    def _build_context(
        self,
        data: Dict[str, Any],
        action: str,
        user_context: Optional[Dict],
        old_data: Optional[Dict] = None
    ) -> PolicyContext:
        """构建策略上下文"""
        # 构建行数据
        row_data = {}
        if old_data:
            row_data.update(old_data)
        row_data.update(data)
        
        # 判断是否新行
        is_new = old_data is None
        row_data['is_new'] = is_new
        
        # 构建对象上下文
        object_ctx = None
        if self.meta_object:
            semantics = getattr(self.meta_object, 'semantics', None)
            mutability = None
            if semantics:
                if isinstance(semantics, dict):
                    mutability = semantics.get('mutability')
                else:
                    mutability = getattr(semantics, 'mutability', None)
            
            object_ctx = ObjectContext(
                mutability=mutability,
                object_type=getattr(self.meta_object, 'id', None)
            )
        
        return PolicyContext(
            row=row_data,
            object_context=object_ctx,
            action=action
        )
    
    def _validate_field_editable(
        self,
        field_id: str,
        context: PolicyContext
    ) -> Optional[ValidationError]:
        """验证字段是否可编辑"""
        if self.engine.determine_editable(field_id, context):
            return None
        
        field = self._get_field(field_id)
        field_name = getattr(field, 'name', field_id) if field else field_id
        
        # 生成错误消息
        if context.object_context and context.object_context.mutability == 'locked':
            message = f"字段 '{field_name}' 不可修改（对象已锁定）"
        elif self.engine._is_system_field(field_id):
            message = f"系统字段 '{field_name}' 不可修改"
        else:
            message = f"字段 '{field_name}' 在当前上下文中不可编辑"
        
        return ValidationError(
            field_id=field_id,
            field_name=field_name,
            message=message,
            error_code="FIELD_NOT_EDITABLE"
        )
    
    def _check_object_create_permission(
        self,
        context: PolicyContext
    ) -> bool:
        """检查对象创建权限"""
        if not context.object_context:
            return True
        
        mutability = context.object_context.mutability
        if mutability == 'locked':
            return False
        
        return True
    
    def _check_object_update_permission(
        self,
        context: PolicyContext,
        old_data: Dict
    ) -> bool:
        """检查对象更新权限"""
        if not context.object_context:
            return True
        
        mutability = context.object_context.mutability
        
        if mutability == 'locked':
            return False
        
        if mutability == 'extensible':
            is_system = old_data.get('is_system', False)
            return not is_system
        
        return True
    
    def _check_object_delete_permission(
        self,
        context: PolicyContext,
        old_data: Dict
    ) -> bool:
        """检查对象删除权限"""
        if not context.object_context:
            return True
        
        mutability = context.object_context.mutability
        
        if mutability == 'locked':
            return False
        
        if mutability == 'extensible':
            is_system = old_data.get('is_system', False)
            return not is_system
        
        return True
    
    def _is_data_field(self, field_id: str, value: Any) -> bool:
        """判断是否是数据字段（排除元字段）"""
        meta_fields = {'_type', '_action', '_source'}
        return field_id not in meta_fields and not field_id.startswith('_')
    
    def _get_field(self, field_id: str):
        """获取字段定义"""
        if not self.meta_object:
            return None
        
        fields = getattr(self.meta_object, 'fields', [])
        for field in fields:
            if getattr(field, 'id', None) == field_id:
                return field
        return None
    
    def _load_old_data(self, object_id: Any) -> Optional[Dict]:
        """加载旧数据"""
        if not self.data_source or object_id is None:
            return None
        
        try:
            return self.data_source.load(object_id)
        except Exception:
            return None


def create_validation_interceptor(meta_object=None, data_source=None) -> FieldPolicyValidationInterceptor:
    """
    工厂函数：创建验证拦截器
    
    Args:
        meta_object: 元数据对象
        data_source: 数据源（用于加载旧数据）
        
    Returns:
        FieldPolicyValidationInterceptor: 验证拦截器实例
    """
    return FieldPolicyValidationInterceptor(meta_object, data_source)
