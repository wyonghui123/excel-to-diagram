# -*- coding: utf-8 -*-
"""
DeepMutationEngine（QE-M7-2026-06-v2）

[M7.3 2026-06-05] 深度写入引擎（Insert + Update + Delete）。

继承自 DeepInsertEngine（M5.6），扩展：
- deep_update：嵌套子操作（create / update / delete）
- deep_delete：级联删除

设计：
- 复用 bo_framework.create/update/delete（M5.3 包装）
- 复用 M5.6 嵌套识别（in_transaction 跳过内层）
- 复用 M5.5 UnitOfWork 失败回滚
- API 端点 meta/api/manage_api.py
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from meta.core.action_context import ActionResult
from meta.core.action_constants import CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE

logger = logging.getLogger(__name__)


class DeepMutationEngine:
    """深度写入引擎。"""

    def __init__(self, deep_insert_engine=None, bo_framework=None):
        from meta.core.deep_insert_engine import DeepInsertEngine
        from meta.core.bo_framework import bo_framework as default_bf
        self._insert_engine = deep_insert_engine or DeepInsertEngine()
        self._bo_framework = bo_framework or default_bf

    # ============================================================
    # Deep Insert（已存在，包装）
    # ============================================================
    def deep_insert(
        self,
        object_type: str,
        payload: Dict,
        data_source=None,
    ) -> ActionResult:
        """M5.6 已实现。"""
        return self._insert_engine.execute(
            object_type, payload, data_source
        )

    # ============================================================
    # Deep Update（新增）
    # ============================================================
    def deep_update(
        self,
        object_type: str,
        filter_clause: Dict,
        patch_data: Dict,
        options: Optional[Dict] = None,
        data_source=None,
    ) -> ActionResult:
        """[M7.3] 深度更新。

        Args:
            object_type: 主实体类型
            filter_clause: 主对象过滤（如 {'id': 100}）
            patch_data: 主对象 patch + 嵌套子操作
                {
                    'status': 'paid',  # 主对象 patch
                    'items': [  # 嵌套子操作（列表）
                        {'update': {'id': 1, 'quantity': 5}},
                        {'create': {'product_id': 10, 'quantity': 1}},
                        {'delete': {'id': 3}},
                    ],
                }
            options: {'transaction_mode': 'all_or_nothing' / 'independent'}

        Returns:
            ActionResult {success, data: {affected, parent_id}, errors}
        """
        options = options or {}
        transaction_mode = options.get('transaction_mode', 'all_or_nothing')

        if transaction_mode == 'all_or_nothing':
            return self._update_with_txn(
                object_type, filter_clause, patch_data, data_source
            )
        return self._update_without_txn(
            object_type, filter_clause, patch_data, data_source
        )

    def _update_with_txn(
        self,
        object_type: str,
        filter_clause: Dict,
        patch_data: Dict,
        data_source,
    ) -> ActionResult:
        """带事务的 deep_update。"""
        ds = data_source or self._bo_framework._data_source
        affected_ids: List[int] = []
        try:
            # 用 bo_framework 现有 transaction（生成 transaction_id）
            with self._bo_framework.transaction() as txn_ctx:
                self._do_update_steps(
                    object_type, filter_clause, patch_data,
                    ds, affected_ids,
                )
            return ActionResult(
                success=True,
                data={
                    'affected': affected_ids,
                    'parent_id': affected_ids[0] if affected_ids else None,
                    'transaction_id': txn_ctx.transaction_id,
                },
                message=f'deep update completed: {len(affected_ids)} affected',
            )
        except Exception as e:
            logger.error(
                f"[DeepMutation.M7.3] deep_update rolled back: {e}",
                exc_info=True,
            )
            return ActionResult(
                success=False,
                message=f'deep update failed (rolled back): {e}',
                data={'rolled_back': True},
                errors=[str(e)],
            )

    def _update_without_txn(
        self,
        object_type: str,
        filter_clause: Dict,
        patch_data: Dict,
        data_source,
    ) -> ActionResult:
        """不带事务的 deep_update（独立模式）。"""
        ds = data_source or self._bo_framework._data_source
        affected_ids: List[int] = []
        errors: List[str] = []
        for op_step in self._iter_update_steps(
            object_type, filter_clause, patch_data, affected_ids,
        ):
            try:
                self._exec_single_step(op_step, ds, affected_ids)
            except Exception as e:
                errors.append(f'{op_step["action"]}: {e}')
        return ActionResult(
            success=not errors,
            data={'affected': affected_ids, 'mode': 'independent'},
            errors=errors,
            message=f'deep update (independent) done, {len(errors)} errors',
        )

    def _do_update_steps(
        self,
        object_type: str,
        filter_clause: Dict,
        patch_data: Dict,
        ds,
        affected_ids: List[int],
    ) -> None:
        """执行所有 update 步骤（事务内）。"""
        for step in self._iter_update_steps(
            object_type, filter_clause, patch_data, affected_ids,
        ):
            self._exec_single_step(step, ds, affected_ids)

    def _iter_update_steps(
        self,
        object_type: str,
        filter_clause: Dict,
        patch_data: Dict,
        affected_ids: List[int],
    ):
        """生成所有 update 步骤。"""
        # 1. 主对象 update（提取非嵌套字段）
        parent_patch = {
            k: v for k, v in patch_data.items()
            if not isinstance(v, list)
        }
        if parent_patch:
            obj_id = filter_clause.get('id')
            if obj_id is None:
                raise ValueError("deep_update requires 'id' in filter_clause")
            yield {
                'action': 'update',
                'entity_type': object_type,
                'id': obj_id,
                'data': parent_patch,
            }
        # 2. 嵌套子操作
        for key, value in patch_data.items():
            if not isinstance(value, list):
                continue
            for child_op in value:
                if 'update' in child_op:
                    yield {
                        'action': 'update',
                        'entity_type': self._infer_child_type(object_type, key),
                        'id': child_op['update'].get('id'),
                        'data': child_op['update'],
                    }
                elif 'create' in child_op:
                    child_data = dict(child_op['create'])
                    fk = self._infer_fk(object_type, key)
                    child_data[fk] = affected_ids[0] if affected_ids else filter_clause.get('id')
                    yield {
                        'action': 'create',
                        'entity_type': self._infer_child_type(object_type, key),
                        'data': child_data,
                    }
                elif 'delete' in child_op:
                    yield {
                        'action': 'delete',
                        'entity_type': self._infer_child_type(object_type, key),
                        'id': child_op['delete'].get('id'),
                    }

    def _exec_single_step(self, step: Dict, ds, affected_ids: List[int]) -> None:
        """执行单个 update 步骤。"""
        action = step['action']
        if action == 'update':
            result = self._bo_framework.update(
                step['entity_type'],
                step['id'],
                step['data'],
            )
            if not result.success:
                raise RuntimeError(
                    f"update {step['entity_type']}[{step['id']}] failed: {result.message}"
                )
        elif action == 'create':
            result = self._bo_framework.create(
                step['entity_type'],
                step['data'],
            )
            if not result.success:
                raise RuntimeError(
                    f"create {step['entity_type']} failed: {result.message}"
                )
            if result.data and 'id' in result.data:
                affected_ids.append(result.data['id'])
        elif action == 'delete':
            result = self._bo_framework.delete(
                step['entity_type'],
                step['id'],
            )
            if not result.success:
                raise RuntimeError(
                    f"delete {step['entity_type']}[{step['id']}] failed: {result.message}"
                )

    # ============================================================
    # Deep Delete（新增）
    # ============================================================
    def deep_delete(
        self,
        object_type: str,
        filter_clause: Dict,
        cascade: bool = False,
        options: Optional[Dict] = None,
        data_source=None,
    ) -> ActionResult:
        """[M7.3] 深度删除（可选级联）。

        Args:
            object_type: 主实体类型
            filter_clause: 主对象过滤
            cascade: 是否级联删除关联
        """
        options = options or {}
        transaction_mode = options.get('transaction_mode', 'all_or_nothing')
        if transaction_mode == 'all_or_nothing':
            return self._delete_with_txn(
                object_type, filter_clause, cascade, data_source,
            )
        return self._delete_without_txn(
            object_type, filter_clause, cascade, data_source,
        )

    def _delete_with_txn(
        self,
        object_type: str,
        filter_clause: Dict,
        cascade: bool,
        data_source,
    ) -> ActionResult:
        ds = data_source or self._bo_framework._data_source
        deleted_ids: List[int] = []
        try:
            with self._bo_framework.transaction() as txn_ctx:
                # 1. 查 ids
                if 'id' in filter_clause:
                    ids = [filter_clause['id']]
                else:
                    ids = self._find_ids(object_type, filter_clause, ds)
                # 2. cascade
                if cascade:
                    for child_type in self._get_child_types(object_type):
                        self._cascade_delete_children(
                            object_type, ids, child_type, ds, deleted_ids,
                        )
                # 3. 删主对象
                for id_ in ids:
                    result = self._bo_framework.delete(object_type, id_)
                    if result.success:
                        deleted_ids.append(id_)
            return ActionResult(
                success=True,
                data={
                    'deleted_ids': deleted_ids,
                    'cascade': cascade,
                    'transaction_id': txn_ctx.transaction_id,
                },
                message=f'deep delete completed: {len(deleted_ids)} records',
            )
        except Exception as e:
            logger.error(
                f"[DeepMutation.M7.3] deep_delete rolled back: {e}",
                exc_info=True,
            )
            return ActionResult(
                success=False,
                message=f'deep delete failed (rolled back): {e}',
                data={'rolled_back': True},
                errors=[str(e)],
            )

    def _delete_without_txn(
        self,
        object_type: str,
        filter_clause: Dict,
        cascade: bool,
        data_source,
    ) -> ActionResult:
        ds = data_source or self._bo_framework._data_source
        deleted_ids: List[int] = []
        errors: List[str] = []
        try:
            if 'id' in filter_clause:
                ids = [filter_clause['id']]
            else:
                ids = self._find_ids(object_type, filter_clause, ds)
            if cascade:
                for child_type in self._get_child_types(object_type):
                    self._cascade_delete_children(
                        object_type, ids, child_type, ds, deleted_ids,
                    )
            for id_ in ids:
                result = self._bo_framework.delete(object_type, id_)
                if result.success:
                    deleted_ids.append(id_)
                else:
                    errors.append(f'{object_type}[{id_}]: {result.message}')
        except Exception as e:
            errors.append(str(e))
        return ActionResult(
            success=not errors,
            data={'deleted_ids': deleted_ids, 'mode': 'independent'},
            errors=errors,
        )

    def _find_ids(self, object_type: str, filter_clause: Dict, ds) -> List[int]:
        """根据 filter 查 ids。"""
        from meta.core.models import registry
        meta = registry.get(object_type)
        if not meta:
            return []
        table = meta.table_name
        wheres = []
        params: List[Any] = []
        for k, v in filter_clause.items():
            wheres.append(f'{k} = ?')
            params.append(v)
        where_clause = ' AND '.join(wheres) if wheres else '1=1'
        cursor = ds.execute(
            f'SELECT id FROM {table} WHERE {where_clause}', tuple(params)
        )
        rows = cursor.fetchall()
        ids: List[int] = []
        for row in rows:
            if isinstance(row, dict):
                ids.append(row.get('id'))
            else:
                ids.append(row[0])
        return [i for i in ids if isinstance(i, int)]

    def _cascade_delete_children(
        self,
        parent_type: str,
        parent_ids: List[int],
        child_type: str,
        ds,
        deleted_ids: List[int],
    ) -> None:
        """级联删除子对象。"""
        fk = self._infer_fk(parent_type, child_type)
        if not fk or not parent_ids:
            return
        placeholders = ', '.join('?' * len(parent_ids))
        cursor = ds.execute(
            f'SELECT id FROM {child_type} WHERE {fk} IN ({placeholders})',
            tuple(parent_ids),
        )
        rows = cursor.fetchall()
        child_ids: List[int] = []
        for row in rows:
            if isinstance(row, dict):
                child_ids.append(row.get('id'))
            else:
                child_ids.append(row[0])
        for child_id in child_ids:
            result = self._bo_framework.delete(child_type, child_id)
            if result.success:
                deleted_ids.append(child_id)

    # ============================================================
    # 类型推断（简化版，v1 已有更复杂逻辑）
    # ============================================================
    def _infer_child_type(self, parent_type: str, key: str) -> str:
        """推断子实体类型。

        简化：直接用 key 作为 entity_type（已复数化）。
        实际可从 meta.associations 查。
        """
        return key

    def _infer_fk(self, parent_type: str, child_key: str) -> str:
        """推断子表外键字段名。"""
        # 简化：<parent_type>_id
        return f'{parent_type}_id'

    def _get_child_types(self, parent_type: str) -> List[str]:
        """获取 parent_type 的所有子类型（从 metadata）。"""
        try:
            from meta.core.models import registry
            meta = registry.get(parent_type)
            if not meta:
                return []
            assocs = getattr(meta, 'associations', []) or []
            return [
                getattr(a, 'target_entity', '') or getattr(a, 'name', '')
                for a in assocs
                if getattr(a, 'type', '') in ('one_to_many', 'many_to_many')
            ]
        except Exception:
            return []


# 全局默认实例
_default_engine: Optional[DeepMutationEngine] = None


def get_deep_mutation_engine() -> DeepMutationEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = DeepMutationEngine()
    return _default_engine
