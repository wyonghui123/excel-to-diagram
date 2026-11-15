# -*- coding: utf-8 -*-
"""通用审批待办创建（M3 / SSOT v0.3 D-AP-02）

依据 `docs/specs/spec-purchase-order-object-model-2026-11-01.md` §6.2.2 R7 / §6.4：
  · 审批统一复用 `tasks(type='approval')`，不新建审批引擎；
  · 提交时按解析结果落一条待办；在途判重（未到终态的任务不回退）；
  · `executor_config.decision_actions` 指向 BO Action，`inputs.policy_snapshot`
    记录提交时命中的策略与步骤（R9：策略变更不回溯在途单据）。

建任务元数据唯一真源 = BO YAML ``approval:``（经 `approval_meta_loader` 读取），
本模块不再持有对象 → 表名 / 标题 / 域 / 决策动作的第二份副本。
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from meta.core.approval_meta_loader import get_approval_meta

logger = logging.getLogger(__name__)

PURCHASE_ORDER_OBJECT = 'purchase_order'

#: 审批任务的终止态（这些状态不再算在途，可重新建任务）
TASK_TERMINAL_STATUSES = ('done', 'failed', 'cancelled', 'skipped', 'dead')


class ApprovalTaskService:
    """按对象建审批待办（幂等：已有在途任务则不重复建）。"""

    def __init__(self, data_source):
        self._ds = data_source

    def create_task(self, object_type: str, record_id: Any, *,
                    policy_snapshot: Optional[Dict[str, Any]] = None,
                    actor: str = '') -> Optional[str]:
        """返回任务 id；不适用（未知对象 / 缺 id / 已有在途任务）返回 None。"""
        meta = get_approval_meta(object_type)
        actions = meta.get('decision_actions') or {}
        if not meta.get('table') or record_id in (None, '') or not actions:
            return None

        placeholders = ', '.join('?' * len(TASK_TERMINAL_STATUSES))
        active = self._ds.query(
            "SELECT id FROM tasks WHERE type = 'approval' "
            'AND doc_ref_type = ? AND doc_ref_id = ? '
            'AND status NOT IN ({0})'.format(placeholders),
            [object_type, str(record_id)] + list(TASK_TERMINAL_STATUSES),
        )
        if active:
            return None

        task_id = uuid.uuid4().hex
        id_key = meta['id_key']
        title = '{0} #{1}'.format(
            meta['title_prefix'], self._title_suffix(meta, record_id))
        inputs = {'id': record_id, id_key: record_id}
        if policy_snapshot:
            inputs['policy_snapshot'] = policy_snapshot

        row = {
            'id': task_id,
            'code': None,
            'title': title,
            'type': 'approval',
            'status': 'waiting_approval',
            'priority': 'P1',
            'app_id': meta['app_id'],
            'executor_type': 'human',
            'assign_policy': 'claim',
            'executor_candidates': json.dumps([], ensure_ascii=False),
            'executor_config': json.dumps(
                {'decision_actions': actions}, ensure_ascii=False),
            'inputs': json.dumps(inputs, ensure_ascii=False, default=str),
            'doc_ref': str(record_id),
            'doc_ref_type': object_type,
            'doc_ref_id': str(record_id),
            'created_by': actor or 'system',
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'attempt': 1,
        }
        columns = ', '.join(row.keys())
        values = ', '.join('?' * len(row))
        self._ds.execute(
            'INSERT INTO tasks ({0}) VALUES ({1})'.format(columns, values),
            list(row.values()),
        )
        logger.info('[ApprovalTask] %s id=%s 建审批任务 %s',
                    object_type, record_id, task_id)
        return task_id

    def _title_suffix(self, meta: Dict[str, Any], record_id: Any) -> str:
        field = meta.get('title_field')
        if not field:
            return str(record_id)
        rows = self._ds.query(
            'SELECT {0} AS doc_no FROM {1} WHERE id = ?'.format(
                field, meta['table']), [record_id])
        doc_no = rows[0].get('doc_no') if rows else None
        return str(doc_no or record_id)