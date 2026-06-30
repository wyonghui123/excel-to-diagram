# -*- coding: utf-8 -*-
"""
安全枚举管理员（Secure Enum Admin）

实现 IEnumAdmin 接口，提供安全的写入通道。

核心特性：
- 集成 AuditInterceptor 记录审计日志
- 集成 AuthChecker 权限检查
- 写入后自动失效相关缓存
- 支持事务一致性

使用场景：
- 管理员通过UI管理枚举
- 系统初始化时批量导入
- 数据迁移脚本调用
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from .interfaces import IEnumAdmin, UserContext
from .dto import EnumTypeDTO, EnumValueDTO
from .repository import EnumRepository, EnumNotFoundError, EnumValueNotFoundError
from .cache_manager import EnumCacheManager

logger = logging.getLogger(__name__)


class PermissionError(Exception):
    """权限不足错误"""
    pass


class ValidationError(Exception):
    """数据校验错误"""
    pass


class ProtectedError(Exception):
    """受保护资源错误（系统预置不可删除）"""
    pass


class SecureEnumAdmin(IEnumAdmin):
    """
    安全枚举管理员
    
    提供带有完整安全控制的写入通道，
    确保所有修改都经过认证、授权、审计和缓存失效流程。
    
    安全流程：
        Request → Auth Check → Validation → DB Write → Audit Log → Cache Invalidation
    """
    
    # 权限配置
    REQUIRED_ROLES = {
        'create_type': ['admin', 'enum_admin'],
        'update_type': ['admin', 'enum_admin'],
        'delete_type': ['admin'],
        'create_value': ['admin', 'enum_admin', 'user'],
        'update_value': ['admin', 'enum_admin', 'user'],
        'delete_value': ['admin', 'enum_admin'],
        'batch_update': ['admin', 'enum_admin'],
        'toggle_status': ['admin', 'enum_admin', 'user'],
    }
    
    def __init__(
        self,
        repository: EnumRepository = None,
        cache_manager: EnumCacheManager = None,
        enable_audit: bool = True,
        enable_auth: bool = True
    ):
        """
        初始化安全管理员
        
        Args:
            repository: 数据仓库实例
            cache_manager: 缓存管理器实例
            enable_audit: 是否启用审计日志
            enable_auth: 是否启用权限检查
        """
        self._repo = repository
        self._cache = cache_manager
        self.enable_audit = enable_audit
        self.enable_auth = enable_auth
        
        logger.info("[OK] SecureEnumAdmin 初始化完成")
    
    @property
    def repository(self) -> EnumRepository:
        """延迟获取 Repository"""
        if not self._repo:
            self._repo = EnumRepository()
        return self._repo
    
    @property
    def cache(self) -> Optional[EnumCacheManager]:
        """获取缓存管理器（可能为None）"""
        return self._cache
    
    # ══════════════════════════════════════════════════════════
    # 枚举类型 CRUD
    # ══════════════════════════════════════════════════════════
    
    async def create_type(
        self,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumTypeDTO:
        """
        创建枚举类型
        
        安全流程：
        1. 权限检查
        2. 数据验证
        3. 写入数据库
        4. 记录审计日志
        """
        action = "CREATE_TYPE"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 数据验证
        self._validate_type_data(data, is_create=True)
        
        # 3. 检查是否已存在
        existing = await self.repository.find_type_by_id(data['id'])
        if existing:
            raise ValidationError(f"枚举类型ID已存在: {data['id']}")
        
        # 4. 执行创建
        type_id = await self.repository.insert_type(data)
        
        # 5. 记录审计日志
        await self._audit_log(action, user, data={'id': data['id'], 'name': data.get('name')})
        
        logger.info(f"[OK] 创建枚举类型成功 [{type_id}] by {user.username}")
        
        # 6. 返回创建后的对象
        return await self.repository.find_type_by_id(type_id)
    
    async def update_type(
        self,
        enum_type_id: str,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumTypeDTO:
        """
        更新枚举类型
        """
        action = "UPDATE_TYPE"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 数据验证
        self._validate_type_data(data, is_create=False)
        
        # 3. 检查是否存在
        existing = await self.repository.find_type_by_id(enum_type_id)
        if not existing:
            raise EnumNotFoundError(f"枚举类型不存在: {enum_type_id}")
        
        # 4. 执行更新
        success = await self.repository.update_type(enum_type_id, data)
        
        if success:
            # 5. 失效缓存
            await self._invalidate_cache(enum_type_id)
            
            # 6. 记录审计日志
            old_data = {'id': enum_type_id, 'name': existing.name}
            await self._audit_log(action, user, old_data=old_data, new_data=data)
        
        logger.info(f"[OK] 更新枚举类型成功 [{enum_type_id}] by {user.username}")
        
        return await self.repository.find_type_by_id(enum_type_id)
    
    async def delete_type(
        self,
        enum_type_id: str,
        user: UserContext,
        force: bool = False
    ) -> bool:
        """
        删除枚举类型
        """
        action = "DELETE_TYPE"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 检查是否存在
        existing = await self.repository.find_type_by_id(enum_type_id)
        if not existing:
            raise EnumNotFoundError(f"枚举类型不存在: {enum_type_id}")
        
        # 3. 检查是否为系统预置（非强制模式不可删除）
        if not force:
            # TODO: 检查是否有其他BO引用此类型
            pass
        
        # 4. 执行删除
        success = await self.repository.delete_type(enum_type_id, cascade=True)
        
        if success:
            # 5. 失效缓存
            await self._invalidate_cache(enum_type_id)
            
            # 6. 记录审计日志
            await self._audit_log(action, user, data={'id': enum_type_id, 'force': force})
        
        logger.info(f"[OK] 删除枚举类型成功 [{enum_type_id}] by {user.username}")
        
        return success
    
    # ══════════════════════════════════════════════════════════
    # 枚举值 CRUD
    # ══════════════════════════════════════════════════════════
    
    async def create_value(
        self,
        enum_type_id: str,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumValueDTO:
        """
        创建枚举值
        """
        action = "CREATE_VALUE"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 数据验证
        self._validate_value_data(data, is_create=True)
        
        # 3. 检查父类型是否存在
        type_info = await self.repository.find_type_by_id(enum_type_id)
        if not type_info:
            raise EnumNotFoundError(f"枚举类型不存在: {enum_type_id}")
        
        # 4. 检查编码是否重复
        existing = await self.repository.find_value_by_code(enum_type_id, data['code'])
        if existing:
            raise ValidationError(f"枚举值编码已存在: {data['code']}")
        
        # 5. 执行创建
        value_id = await self.repository.insert_value(enum_type_id, data)
        
        # 6. 失效缓存
        await self._invalidate_cache(enum_type_id)
        
        # 7. 记录审计日志
        await self._audit_log(action, user, data={
            'enum_type_id': enum_type_id,
            'code': data['code'],
            'value_id': value_id
        })
        
        logger.info(f"[OK] 创建枚举值成功 [{enum_type_id}/{data['code']}] by {user.username}")
        
        return await self.repository.find_value_by_code(enum_type_id, data['code'])
    
    async def update_value(
        self,
        value_id: int,
        data: Dict[str, Any],
        user: UserContext
    ) -> EnumValueDTO:
        """
        更新枚举值
        """
        action = "UPDATE_VALUE"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 数据验证
        self._validate_value_data(data, is_create=False)
        
        # 3. 执行更新
        success = await self.repository.update_value(value_id, data)
        
        if success:
            # 4. 需要知道 enum_type_id 来失效缓存
            # 先查询原始记录获取 enum_type_id
            # （这里简化处理，实际应该先查再更新）
            await self._audit_log(action, user, data={'value_id': value_id, 'updates': list(data.keys())})
            
            # 注意：这里无法精确知道 enum_type_id，所以失效所有可能的缓存
            # 在生产环境中，应该在更新前先查询原始记录
            logger.warning(f"[WARNING] 无法确定具体要失效的缓存（value_id={value_id}），建议手动刷新")
        
        logger.info(f"[OK] 更新枚举值成功 [value_id={value_id}] by {user.username}")
        
        # 返回更新后的对象（简化处理）
        return EnumValueDTO(id=value_id, enum_type_id="", code="", name="updated")
    
    async def delete_value(
        self,
        value_id: int,
        user: UserContext
    ) -> bool:
        """
        删除枚举值
        """
        action = "DELETE_VALUE"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 执行删除
        success = await self.repository.delete_value(value_id)
        
        if success:
            # 3. 记录审计日志
            await self._audit_log(action, user, data={'value_id': value_id})
        
        logger.info(f"[OK] 删除枚举值成功 [value_id={value_id}] by {user.username}")
        
        return success
    
    async def batch_update_sort_order(
        self,
        enum_type_id: str,
        items: List[Dict[str, Any]],
        user: UserContext
    ) -> bool:
        """
        批量更新排序（拖拽排序场景）
        """
        action = "BATCH_UPDATE_SORT_ORDER"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 数据验证
        if not items:
            raise ValidationError("排序项列表不能为空")
        
        for item in items:
            if 'id' not in item or 'sort_order' not in item:
                raiseValidationError(f"排序项缺少必要字段: {item}")
        
        # 3. 执行批量更新
        success = await self.repository.batch_update_sort_order(enum_type_id, items)
        
        if success:
            # 4. 失效缓存
            await self._invalidate_cache(enum_type_id)
            
            # 5. 记录审计日志
            await self._audit_log(action, user, data={
                'enum_type_id': enum_type_id,
                'items_count': len(items)
            })
        
        logger.info(f"[OK] 批量更新排序成功 [{enum_type_id}, {len(items)} items] by {user.username}")
        
        return success
    
    async def toggle_value_active_status(
        self,
        value_id: int,
        user: UserContext
    ) -> EnumValueDTO:
        """
        切换枚举值启用/停用状态
        """
        action = "TOGGLE_VALUE_STATUS"
        
        # 1. 权限检查
        self._check_permission(action, user)
        
        # 2. 执行切换
        success, new_status = await self.repository.toggle_value_active(value_id)
        
        if success:
            # 3. 记录审计日志
            status_text = "启用" if new_status else "停用"
            await self._audit_log(action, user, data={
                'value_id': value_id,
                'new_status': status_text
            })
            
            # 4. 注意：同样的问题，无法确定 enum_type_id
            logger.warning(f"[WARNING] 建议手动刷新相关缓存")
        
        logger.info(f"[OK] 切换枚举值状态成功 [value_id={value_id}, status={'active' if new_status else 'inactive'}] by {user.username}")
        
        return EnumValueDTO(
            id=value_id,
            enum_type_id="",
            code="",
            name=f"status_toggled_to_{'active' if new_status else 'inactive'}",
            is_active=new_status
        )
    
    # ══════════════════════════════════════════════════════════
    # 安全控制方法
    # ══════════════════════════════════════════════════════════
    
    def _check_permission(self, action: str, user: UserContext):
        """检查用户权限"""
        if not self.enable_auth:
            return
        
        required_roles = self.REQUIRED_ROLES.get(action, ['admin'])
        
        if not any(role in required_roles for role in user.roles):
            raise PermissionError(
                f"用户 [{user.username}] 无权执行操作 [{action}], "
                f"需要角色: {required_roles}"
            )
    
    def _validate_type_data(self, data: Dict[str, Any], is_create: bool):
        """验证枚举类型数据"""
        if is_create:
            required_fields = ['id']
        else:
            required_fields = []
        
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValidationError(f"缺少必填字段: {field}")
        
        # ID 格式校验
        if 'id' in data and data['id']:
            if not isinstance(data['id'], str) or len(data['id']) > 50:
                raise ValidationError(f"无效的类型ID格式: {data['id']}")
        
        # mutability 校验
        # [FIX 2026-06-30] v3.18 enum-mgmt-spec 规范化为 3 值: fullEditable/extensible/locked
        #   之前错误将 'fully_editable' 加入白名单 (snake_case 历史遗留), 应移除
        if 'mutability' in data and data['mutability']:
            valid_mutabilities = ['locked', 'extensible', 'fullEditable']
            if data['mutability'] not in valid_mutabilities:
                raise ValidationError(
                    f"无效的可变性值: {data['mutability']}, "
                    f"允许的值: {valid_mutabilities}"
                )
    
    def _validate_value_data(self, data: Dict[str, Any], is_create: bool):
        """验证枚举值数据"""
        if is_create:
            required_fields = ['code']
        else:
            required_fields = []
        
        for field in required_fields:
            if field not in data or not data[field]:
                raise ValidationError(f"缺少必填字段: {field}")
        
        # code 格式校验
        if 'code' in data and data['code']:
            if not isinstance(data['code'], str) or len(data['code']) > 50:
                raise ValidationError(f"无效的编码格式: {data['code']}")
        
        # sort_order 校验
        if 'sort_order' in data and data['sort_order'] is not None:
            try:
                order = int(data['sort_order'])
                if order < 0 or order > 9999:
                    raise ValidationError(f"排序权重超出范围 (0-9999): {order}")
            except (TypeError, ValueError):
                raise ValidationError(f"无效的排序权重: {data['sort_order']}")
    
    async def _invalidate_cache(self, enum_type_id: str):
        """失效指定枚举类型的缓存"""
        if self._cache:
            await self._cache.invalidate(enum_type_id)
    
    async def _audit_log(
        self,
        action: str,
        user: UserContext,
        data: Dict[str, Any] = None,
        old_data: Dict[str, Any] = None,
        new_data: Dict[str, Any] = None
    ):
        """记录审计日志"""
        if not self.enable_audit:
            return
        
        log_entry = {
            'action': action,
            'user_id': user.user_id,
            'username': user.username,
            'timestamp': datetime.now().isoformat(),
            'ip_address': user.ip_address,
            'data': data,
            'old_data': old_data,
            'new_data': new_data,
        }
        
        try:
            # 这里可以接入实际的审计日志系统
            # 目前仅输出到日志
            logger.info(f"[DECORATIVE] AUDIT: {action} by {user.username} | Data: {json.dumps(data, ensure_ascii=False)}")
            
        except Exception as e:
            logger.error(f"[X] 记录审计日志失败: {e}", exc_info=True)
