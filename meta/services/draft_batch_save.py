# -*- coding: utf-8 -*-
"""
BO 业务 Action: batch_save (草稿批量保存)
==========================================

从前端 useMetaList.saveDraftValues (80 行) 迁移的业务 Action。
统一处理草稿中的"创建新行"和"更新已有行"。

**核心特性**:
- 接收 {object_type, drafts: [{row_id, is_new, fields}]}
- 自动识别 is_new, 走 bo.create() 或 bo.update()
- 每个操作走完整 18 拦截器链 (审计/权限/级联/通知)
- 事务: 全部成功才返回 success, 任一失败回滚
- 返回 {created: [], updated: [], failures: []}

**业务规则** (从 useMetaList.saveDraftValues 提取):
- is_new 以 row_id 以 "__new_" 开头识别
- 过滤未变更字段 (无变化的行不提交)
- 保留 *_id 字段 (FK 引用)
- code 字段在新建时保留用户输入
"""
import logging
from typing import Any, Dict, List

from flask import g

logger = logging.getLogger(__name__)


def _get_bo_framework():
    from meta.core.bo_framework import bo_framework
    return bo_framework


def _set_user_context():
    from meta.services.auth_middleware import get_current_user
    from flask import request
    current_user = get_current_user()
    bo = _get_bo_framework()
    bo.set_user_context(
        user_id=current_user.get('user_id'),
        user_name=current_user.get('display_name', current_user.get('username', 'unknown')),
        ip_address=request.remote_addr,
    )


def batch_save_handler(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    batch_save Action 处理器

    Args:
        params: {
            'object_type': str,             # BO 对象类型
            'drafts': [
                {
                    'row_id': str|int,       # 行 ID ('__new_X' = 新建)
                    'is_new': bool,          # 是否新建
                    'fields': {...},         # 变更字段
                },
                ...
            ],
        }

    Returns:
        {
            'success': True,
            'data': {
                'created': [新行 ID...],
                'updated': [更新行 ID...],
                'failures': [{row_id, message}],
            },
            'message': '成功创建 X, 更新 Y',
        }
    """
    # 鉴权
    user_info = g.current_user if hasattr(g, 'current_user') and g.current_user else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}

    object_type = params.get('object_type')
    drafts = params.get('drafts', [])

    if not object_type:
        return {'success': False, 'data': None, 'message': 'object_type 必填'}
    if not isinstance(drafts, list):
        return {'success': False, 'data': None, 'message': 'drafts 必须是数组'}
    if not drafts:
        return {'success': True, 'data': {
            'created': [], 'updated': [], 'failures': [],
        }, 'message': '没有需要保存的草稿'}

    # 设置上下文
    try:
        _set_user_context()
    except Exception:
        pass  # 上下文设置失败不应阻塞主流程

    # [v2.0 2026-06-16] FK scope 预校验 (All-or-Nothing)
    # Spec: docs/specs/spec-write-scope-policy-v2.md FR-006
    scope_violations = _pre_validate_fk_scope(object_type, drafts, user_info)
    if scope_violations:
        return {
            'success': False,
            'error_code': 'WRITE_SCOPE_VIOLATION_BATCH',
            'data': {
                'total': len(drafts),
                'failed': len(scope_violations),
                'violations': scope_violations,
                'created': [],
                'updated': [],
                'failures': [],
            },
            'message': f'批量操作中 {len(scope_violations)} 条记录超出数据权限范围',
        }

    bo = _get_bo_framework()

    created_ids: List[Any] = []
    updated_ids: List[Any] = []
    failures: List[Dict[str, Any]] = []

    # [SPR-03 2026-06-18] 共享事务包裹 (All-or-Nothing)
    # Bug: 之前 for 循环逐条调用 bo.create()/bo.update(), 每条都走
    #      bo_framework.execute() 内部自动包裹的独立事务, 中间任何一条失败
    #      已成功的前几条都已提交, 导致部分写入 + 错误提示 (用户报告:
    #      创建产品 TEST21212 + 两个重名版本, 产品 + 1 个版本已落库, 但
    #      系统提示错误, 未回滚).
    # Fix: 外层用 bo_framework.transaction() 共享一个事务; 内部 bo.create()
    #      /bo.update() 看到 self._data_source.in_transaction=True 后会
    #      跳过自己的事务包裹, 加入当前事务. 任一 draft 失败 → set_outcome(False)
    #      → __exit__ 走 rollback, 整个批次原子性得到保证.
    # Spec: docs/specs/spec-write-scope-policy-v2.md (FR-006 All-or-Nothing 扩展)
    with bo.transaction() as txn_ctx:
        for draft in drafts:
            if not isinstance(draft, dict):
                failures.append({'row_id': None, 'message': '无效的 draft 项'})
                continue

            row_id = draft.get('row_id')
            is_new = draft.get('is_new', False)
            fields = draft.get('fields', {})

            if not isinstance(fields, dict):
                failures.append({'row_id': row_id, 'message': 'fields 必须是对象'})
                continue

            try:
                if is_new:
                    # CREATE (在共享事务中, 不会单独包裹)
                    result = bo.create(object_type, fields)
                    if result.success:
                        new_id = (result.data or {}).get('id') if isinstance(result.data, dict) else None
                        created_ids.append(new_id or row_id)
                    else:
                        failures.append({
                            'row_id': row_id,
                            'message': result.message or '创建失败',
                        })
                else:
                    # UPDATE
                    if row_id is None or row_id == '':
                        failures.append({'row_id': row_id, 'message': '更新必须提供 row_id'})
                        continue
                    try:
                        row_id_int = int(row_id)
                    except (TypeError, ValueError):
                        failures.append({'row_id': row_id, 'message': f'row_id 无法转为 int: {row_id}'})
                        continue
                    result = bo.update(object_type, row_id_int, fields)
                    if result.success:
                        updated_ids.append(row_id_int)
                    else:
                        failures.append({
                            'row_id': row_id,
                            'message': result.message or '更新失败',
                        })
            except Exception as e:
                logger.exception(f"[batch_save] row {row_id} failed: {e}")
                failures.append({'row_id': row_id, 'message': str(e)})

        # 整批决策: 任一失败 → 整个事务 rollback
        if failures:
            txn_ctx.set_outcome(success=False)
            logger.warning(
                f"[batch_save] {len(failures)} failures in batch of {len(drafts)}, "
                f"rolling back shared transaction (txn_id={txn_ctx.transaction_id})"
            )
        else:
            logger.info(
                f"[batch_save] all {len(drafts)} drafts succeeded in txn_id={txn_ctx.transaction_id}"
            )

    # 事务已 commit/rollback; 整理返回值
    if failures:
        # 部分失败: 共享事务已 rollback, created/updated 列表已无意义, 清空避免误导
        return {
            'success': False,
            'data': {
                'created': [],
                'updated': [],
                'failures': failures,
            },
            'message': f'{len(failures)} 项失败, 已回滚 (所有变更作废)',
        }

    return {
        'success': True,
        'data': {
            'created': created_ids,
            'updated': updated_ids,
            'failures': [],
        },
        'message': f'成功创建 {len(created_ids)} 项, 更新 {len(updated_ids)} 项',
    }


def _pre_validate_fk_scope(object_type: str, drafts: List[Dict], user_info: Dict) -> List[Dict]:
    """[v2.0 2026-06-16] FK scope 预校验 (All-or-Nothing)

    在 batch_save 执行前, 预检查所有 draft 的 FK 字段值是否在用户 dim scope 内。
    返回 violations 列表, 空 = 全部通过。

    Spec: docs/specs/spec-write-scope-policy-v2.md FR-006
    """
    from meta.services.auth_middleware import is_admin

    # admin 跳过
    if is_admin(user_info):
        return []

    user_id = user_info.get('user_id') or user_info.get('id')
    if not user_id:
        return []

    # 获取 meta_object 的 FK scope 配置
    try:
        from meta.core.bo_framework import bo_framework
        meta_obj = bo_framework._meta_registry.get_meta(object_type)
    except Exception:
        return []  # 无法获取 meta, 跳过

    if not meta_obj:
        return []

    # 收集 enforce/or_bypass/inherit 字段
    enforce_fields = []
    bypass_groups: Dict[str, List[Dict]] = {}
    inherit_fields = []

    for field_def in getattr(meta_obj, 'fields', []):
        vh = field_def.get('value_help') if isinstance(field_def, dict) else None
        if not vh:
            continue
        source = vh.source if hasattr(vh, 'source') else vh.get('source') if isinstance(vh, dict) else None
        if not source:
            continue

        if hasattr(source, 'write_scope_policy'):
            policy = source.write_scope_policy
            scope_group = getattr(source, 'scope_group', None)
            scope_inherit_from = getattr(source, 'scope_inherit_from', None)
            target_bo = getattr(source, 'target_bo', '')
        elif isinstance(source, dict):
            policy = source.get('write_scope_policy', 'none')
            scope_group = source.get('scope_group')
            scope_inherit_from = source.get('scope_inherit_from')
            target_bo = source.get('target_bo', '')
        else:
            continue

        field_id = field_def.get('id') if isinstance(field_def, dict) else getattr(field_def, 'id', '')

        if policy == 'enforce':
            enforce_fields.append({'field_id': field_id, 'target_bo': target_bo, 'policy': 'enforce'})
        elif policy == 'inherit':
            inherit_fields.append({
                'field_id': field_id, 'target_bo': target_bo, 'policy': 'inherit',
                'scope_inherit_from': scope_inherit_from,
            })
        elif policy == 'or_bypass':
            group = scope_group or field_id
            bypass_groups.setdefault(group, []).append({
                'field_id': field_id, 'target_bo': target_bo, 'policy': 'or_bypass',
                'scope_group': group,
            })

    if not enforce_fields and not inherit_fields and not bypass_groups:
        return []  # 无需校验

    # 获取 WSI 实例 (复用 _is_fk_value_in_scope 逻辑)
    from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor
    wsi = WriteScopeInterceptor()
    try:
        data_source = bo_framework._meta_registry.get_data_source(object_type)
    except Exception:
        return []

    # 逐条校验
    violations = []
    for row_idx, draft in enumerate(drafts):
        fields = draft.get('fields', {})

        # 校验 enforce 字段
        for fi in enforce_fields:
            fk_value = fields.get(fi['field_id'])
            if fk_value is None:
                continue
            if not wsi._is_fk_value_in_scope(user_id, fi['target_bo'], fk_value, data_source):
                violations.append({
                    'row': row_idx,
                    'row_id': draft.get('row_id'),
                    'field': fi['field_id'],
                    'value': fk_value,
                    'scope_policy': fi['policy'],
                })

        # 校验 inherit 字段
        for inh in inherit_fields:
            fk_value = fields.get(inh['field_id'])
            if fk_value is None:
                continue
            parent_field_id = inh['scope_inherit_from']
            parent_fk_value = fields.get(parent_field_id)
            if parent_fk_value is not None:
                # 检查 FK 值是否属于父字段值的子集
                table_name = _get_table_name_for_bo(inh['target_bo'])
                try:
                    cursor = data_source.execute(
                        f"SELECT {parent_field_id} FROM {table_name} WHERE id = ?",
                        [fk_value]
                    )
                    row = cursor.fetchone()
                    if row and row[0] == parent_fk_value:
                        # FK 值属于父字段子集, 但仍需检查 FK 值本身在 scope 内
                        if wsi._is_fk_value_in_scope(user_id, inh['target_bo'], fk_value, data_source):
                            continue  # 通过
                except Exception:
                    pass
            # 退化为 enforce
            if not wsi._is_fk_value_in_scope(user_id, inh['target_bo'], fk_value, data_source, cache):
                violations.append({
                    'row': row_idx,
                    'row_id': draft.get('row_id'),
                    'field': inh['field_id'],
                    'value': fk_value,
                    'scope_policy': 'inherit',
                })

        # 校验 or_bypass 字段组
        for group_name, group_fields in bypass_groups.items():
            any_in_scope = False
            for fi in group_fields:
                fk_value = fields.get(fi['field_id'])
                if fk_value is None:
                    continue
                if wsi._is_fk_value_in_scope(user_id, fi['target_bo'], fk_value, data_source):
                    any_in_scope = True
                    break
            if not any_in_scope:
                for fi in group_fields:
                    fk_value = fields.get(fi['field_id'])
                    if fk_value is not None:
                        violations.append({
                            'row': row_idx,
                            'row_id': draft.get('row_id'),
                            'field': fi['field_id'],
                            'value': fk_value,
                            'scope_policy': 'or_bypass',
                            'scope_group': group_name,
                        })

    return violations


def _get_table_name_for_bo(object_type: str) -> str:
    """获取 BO 类型对应的表名"""
    _TABLE_NAME_MAP = {
        'business_object': 'business_objects',
        'service_module': 'service_modules',
        'sub_domain': 'sub_domains',
        'domain': 'domains',
        'version': 'versions',
        'product': 'products',
        'relationship': 'relationship',
    }
    return _TABLE_NAME_MAP.get(object_type, f"{object_type}s")
