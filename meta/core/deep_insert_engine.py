# -*- coding: utf-8 -*-
import logging
from typing import Dict, Any, List, Optional

from meta.core.action_context import ActionResult
from meta.core.models import registry

logger = logging.getLogger(__name__)


class DeepInsertEngine:
    """
    深度插入引擎

    支持一次请求创建/更新父对象和多个子对象，自动推断外键字段。
    事务性保证：所有操作在同一事务中执行，任一失败则全部回滚。

    外键推断优先级：
    1. 子对象元模型中 semantics.parent_key = true 的字段
    2. 命名约定: {parent_type}_id
    3. 通用字段: parent_id
    """

    def execute(self, object_type: str, params: Dict[str, Any], data_source) -> ActionResult:
        parent_data = params.get('parent', {})
        children_data = params.get('children', params.get('_children', {}))
        options = params.get('options', {})

        if not parent_data and '_children' not in params:
            parent_data = {k: v for k, v in params.items() if not k.startswith('_')}
            children_data = params.get('_children', {})

        meta_obj = registry.get(object_type)
        if not meta_obj:
            return ActionResult(success=False, message=f"Unknown object type: {object_type}")

        transaction_mode = options.get('transaction_mode', 'all_or_nothing')

        if transaction_mode == 'all_or_nothing':
            return self._execute_with_transaction(object_type, parent_data, children_data, data_source, options)
        else:
            return self._execute_without_transaction(object_type, parent_data, children_data, data_source, options)

    def _execute_with_transaction(self, object_type: str, parent_data: Dict,
                                   children_data: Dict, data_source, options: Dict) -> ActionResult:
        from meta.core.bo_framework import bo_framework

        created_parent = None
        created_children: Dict[str, List] = {}
        rolled_back = False

        # [M5.6 2026-06-05] 嵌套识别：若调用方已在事务中（如 UnifiedMutationFacade 包了外层），
        # 不再嵌套开事务，直接执行（让外层统一提交/回滚）
        already_in_txn = bool(data_source.in_transaction)

        if already_in_txn:
            logger.info(
                f"[DeepInsert.M5.6] caller already in transaction, skipping nested BEGIN "
                f"(entity={object_type})"
            )
            return self._execute_steps_no_nested_txn(
                object_type, parent_data, children_data, data_source, options
            )

        try:
            with data_source.transaction():
                parent_result = self._create_or_update_parent(object_type, parent_data, data_source)
                if not parent_result.success:
                    raise _DeepInsertError(f"创建父对象失败: {parent_result.message}",
                                           stage='parent', detail=parent_result.message)

                parent_id = parent_result.data.get('id')
                if not parent_id:
                    raise _DeepInsertError("Parent created but no ID returned",
                                           stage='parent', detail='no_id')

                created_parent = parent_result.data

                for child_type, child_list in children_data.items():
                    child_meta = registry.get(child_type)
                    if not child_meta:
                        raise _DeepInsertError(f"Unknown child type: {child_type}",
                                               stage=f'children.{child_type}', detail='unknown_type')

                    fk_field = self._infer_fk_field(object_type, child_type, child_meta)
                    created_children[child_type] = []

                    for i, child_item in enumerate(child_list):
                        if fk_field:
                            child_item[fk_field] = parent_id

                        child_result = self._create_or_update_child(child_type, child_item, data_source)
                        if not child_result.success:
                            raise _DeepInsertError(
                                f"{child_type}[{i}]: {child_result.message}",
                                stage=f'children.{child_type}[{i}]',
                                detail=child_result.message
                            )
                        created_children[child_type].append(child_result.data)

        except _DeepInsertError as e:
            rolled_back = True
            logger.warning(f"[DeepInsert] Transaction rolled back: {e.message}")
            return ActionResult(
                success=False,
                message=f"操作失败，已回滚所有操作: {e.message}",
                data={
                    'rolled_back': True,
                    'failed_at': e.stage,
                    'reason': e.detail,
                    'parent': None,
                    'children': {},
                },
                errors=[e.message],
            )
        except Exception as e:
            rolled_back = True
            logger.error(f"[DeepInsert] Unexpected error, transaction rolled back: {e}")
            return ActionResult(
                success=False,
                message=f"操作失败，已回滚所有操作: {str(e)}",
                data={
                    'rolled_back': True,
                    'parent': None,
                    'children': {},
                },
                errors=[str(e)],
            )

        result_data = {
            'parent': created_parent,
            'children': created_children,
        }

        return ActionResult(
            success=True,
            data=result_data,
            message=f"Deep insert completed: 1 {object_type} + {sum(len(v) for v in created_children.values())} children",
        )

    def _execute_steps_no_nested_txn(self, object_type: str, parent_data: Dict,
                                      children_data: Dict, data_source, options: Dict) -> ActionResult:
        """[M5.6 2026-06-05] 不嵌套事务路径。

        调用方（UnifiedMutationFacade）已在事务中时调用。
        - 不开新事务
        - 失败抛 _DeepInsertError，让外层（MutationFacade）的 with 块自动 rollback
        """
        from meta.core.bo_framework import bo_framework

        created_parent = None
        created_children: Dict[str, List] = {}

        try:
            parent_result = self._create_or_update_parent(object_type, parent_data, data_source)
            if not parent_result.success:
                raise _DeepInsertError(
                    f"创建父对象失败: {parent_result.message}",
                    stage='parent',
                    detail=parent_result.message,
                )

            parent_id = parent_result.data.get('id')
            if not parent_id:
                raise _DeepInsertError(
                    "Parent created but no ID returned",
                    stage='parent',
                    detail='no_id',
                )

            created_parent = parent_result.data

            for child_type, child_list in children_data.items():
                child_meta = registry.get(child_type)
                if not child_meta:
                    raise _DeepInsertError(
                        f"Unknown child type: {child_type}",
                        stage=f'children.{child_type}',
                        detail='unknown_type',
                    )

                fk_field = self._infer_fk_field(object_type, child_type, child_meta)
                created_children[child_type] = []

                for i, child_item in enumerate(child_list):
                    if fk_field:
                        child_item[fk_field] = parent_id

                    child_result = self._create_or_update_child(child_type, child_item, data_source)
                    if not child_result.success:
                        raise _DeepInsertError(
                            f"{child_type}[{i}]: {child_result.message}",
                            stage=f'children.{child_type}[{i}]',
                            detail=child_result.message,
                        )
                    created_children[child_type].append(child_result.data)

        except _DeepInsertError as e:
            # 抛出让 MutationFacade 外层捕获并整体回滚
            logger.warning(
                f"[DeepInsert.M5.6] no-nested-txn path: failure propagated to outer txn: {e}"
            )
            raise

        result_data = {
            'parent': created_parent,
            'children': created_children,
        }

        return ActionResult(
            success=True,
            data=result_data,
            message=f"Deep insert (no nested txn) completed: 1 {object_type} + {sum(len(v) for v in created_children.values())} children",
        )

    def _execute_without_transaction(self, object_type: str, parent_data: Dict,
                                      children_data: Dict, data_source, options: Dict) -> ActionResult:
        parent_result = self._create_or_update_parent(object_type, parent_data, data_source)
        if not parent_result.success:
            return parent_result

        parent_id = parent_result.data.get('id')
        if not parent_id:
            return ActionResult(
                success=False,
                message="Parent created but no ID returned",
                data=parent_result.data,
            )

        created_children: Dict[str, List] = {}
        errors: List[str] = []

        for child_type, child_list in children_data.items():
            child_meta = registry.get(child_type)
            if not child_meta:
                errors.append(f"Unknown child type: {child_type}")
                continue

            fk_field = self._infer_fk_field(object_type, child_type, child_meta)
            created_children[child_type] = []

            for i, child_item in enumerate(child_list):
                if fk_field:
                    child_item[fk_field] = parent_id

                child_result = self._create_or_update_child(child_type, child_item, data_source)
                if child_result.success:
                    created_children[child_type].append(child_result.data)
                else:
                    errors.append(f"{child_type}[{i}]: {child_result.message}")

        result_data = {
            'parent': parent_result.data,
            'children': created_children,
        }

        if errors:
            return ActionResult(
                success=True,
                data=result_data,
                message=f"Parent created, {len(errors)} children failed: {'; '.join(errors[:3])}",
                errors=errors,
            )

        return ActionResult(
            success=True,
            data=result_data,
            message=f"Deep insert completed: 1 {object_type} + {sum(len(v) for v in created_children.values())} children",
        )

    def _create_or_update_parent(self, object_type: str, data: Dict, data_source) -> ActionResult:
        from meta.core.bo_framework import bo_framework

        if data.get('id'):
            return bo_framework.update(object_type, data['id'], data)
        return bo_framework.create(object_type, data)

    def _create_or_update_child(self, child_type: str, data: Dict, data_source) -> ActionResult:
        from meta.core.bo_framework import bo_framework

        if data.get('id'):
            return bo_framework.update(child_type, data['id'], data)
        return bo_framework.create(child_type, data)

    def _infer_fk_field(self, parent_type: str, child_type: str, child_meta) -> Optional[str]:
        for f in child_meta.fields:
            semantics = getattr(f, 'semantics', None)
            if semantics:
                if isinstance(semantics, dict):
                    if semantics.get('parent_key'):
                        return f.id
                elif hasattr(semantics, 'parent_key') and semantics.parent_key:
                    return f.id

        for f in child_meta.fields:
            if f.id == f"{parent_type}_id" or f.id == "parent_id":
                return f.id

        return f"{parent_type}_id"


class _DeepInsertError(Exception):
    def __init__(self, message: str, stage: str = '', detail: str = ''):
        super().__init__(message)
        self.message = message
        self.stage = stage
        self.detail = detail
