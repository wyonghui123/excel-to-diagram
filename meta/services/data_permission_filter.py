# -*- coding: utf-8 -*-
"""
数据权限过滤服务

在查询层注入数据权限条件，实现透明过滤
"""

import logging
from typing import List, Dict, Any, Optional
from meta.core.query_builder import QueryCondition, QueryOperator
from meta.services.data_permission_service import DataPermissionService

logger = logging.getLogger(__name__)


class DataPermissionFilter:
    def __init__(self, data_source):
        self.ds = data_source
        self.perm_service = DataPermissionService(data_source)

    def apply_filter(self, object_type: str, user_id: int,
                     conditions: List[QueryCondition]) -> List[QueryCondition]:
        from meta.services.auth_middleware import is_admin, get_current_user

        current_user = get_current_user()

        if is_admin():
            return conditions

        try:
            allowed_ids = self.perm_service.get_allowed_resource_ids(user_id, object_type)
        except Exception as e:
            logger.error(f"[DataPermFilter] get_allowed_resource_ids failed for "
                         f"user_id={user_id} object_type={object_type}: {e}")
            # 异常时返回永假条件，防止数据泄露
            conditions.append(QueryCondition(
                field='id', operator=QueryOperator.EQ, value=-1
            ))
            return conditions

        if not allowed_ids:
            # 没有数据权限配置，允许所有
            return conditions

        if len(allowed_ids) == 1:
            conditions.append(QueryCondition(
                field='id', operator=QueryOperator.EQ, value=allowed_ids[0]
            ))
        else:
            conditions.append(QueryCondition(
                field='id', operator=QueryOperator.IN, values=allowed_ids
            ))

        return conditions

    def get_relationship_filter(self, user_id: int) -> Dict[str, Any]:
        allowed_bos = self.perm_service.get_allowed_business_object_ids(user_id)

        if not allowed_bos:
            return {'allowed_bo_ids': [], 'has_permission': False}

        return {
            'allowed_bo_ids': allowed_bos,
            'has_permission': True
        }

    def mask_business_object(self, bo: Dict[str, Any], has_permission: bool) -> Dict[str, Any]:
        if has_permission:
            return bo

        return {
            'id': bo.get('id'),
            'code': bo.get('code'),
            'name': bo.get('name'),
            'service_module_name': bo.get('service_module_name'),
            'sub_domain_name': bo.get('sub_domain_name'),
            'domain_name': bo.get('domain_name'),
            '_permission': 'none',
            '_masked': True
        }

    def check_relationship_visibility(self, relationship: Dict[str, Any],
                                       allowed_bo_ids: List[int]) -> str:
        source_visible = relationship.get('source_bo_id') in allowed_bo_ids
        target_visible = relationship.get('target_bo_id') in allowed_bo_ids

        if source_visible and target_visible:
            return 'full'
        elif source_visible:
            return 'source'
        elif target_visible:
            return 'target'
        else:
            return 'none'
