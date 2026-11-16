"""审批策略快照的结构校验（G-13-6 / §9.13.3）。

背景：`tasks.inputs.policy_snapshot` 一直是「靠约定写入」的字典，缺结构约束，
策略求值侧改动字段名后历史/在途任务只能靠运行期 KeyError 暴露。
本模块只做**写入期校验**（fail-open：问题记 warning，不阻断建任务），
并给快照加 `schema_version`，以后要迁移有版本号可依。

判尺（D-AP-09）：快照是冻结事实，消费方（前端审批链、三步态）直接读；
校验只覆盖「消费方依赖的键」，不追求把整棵结构都声明成 schema。
"""

from datetime import datetime
from typing import Any, Dict, List

# 快照结构版本：新增/改名键时递增，消费方据此兼容
SNAPSHOT_SCHEMA_VERSION = 1

REQUIRED_KEYS = (
    'schema_version',
    'object_type',
    'trigger_action',
    'policy_id',
    'hit_policy',
    'amount',
    'steps',
    'conditions',
    'conditions_explain',
    'metrics',
    'resolved_at',
)

REQUIRED_STEP_KEYS = ('step_no', 'approver_type', 'approver_ref', 'approve_mode')

VALID_APPROVE_MODES = ('any', 'all', 'serial')

LIST_KEYS = ('steps', 'conditions', 'conditions_explain')


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_snapshot(snapshot: Any) -> List[str]:
    """返回问题清单（空列表 = 合法）。只读，不修改入参。"""
    if not isinstance(snapshot, dict):
        return ['快照不是字典']

    problems: List[str] = []
    for key in REQUIRED_KEYS:
        if key not in snapshot:
            problems.append(f'缺少字段 {key}')

    version = snapshot.get('schema_version')
    if version is not None and (not isinstance(version, int) or version < 1):
        problems.append(f'schema_version 非法：{version!r}')

    if 'object_type' in snapshot and not _is_non_empty_str(snapshot.get('object_type')):
        problems.append('object_type 必须是非空字符串')

    if 'hit_policy' in snapshot and not _is_non_empty_str(snapshot.get('hit_policy')):
        problems.append('hit_policy 必须是非空字符串')

    if 'amount' in snapshot and snapshot.get('amount') is not None \
            and not _is_number(snapshot.get('amount')):
        problems.append('amount 必须是数字或 None')

    for key in LIST_KEYS:
        if key in snapshot and not isinstance(snapshot.get(key), list):
            problems.append(f'{key} 必须是列表')

    if 'metrics' in snapshot and not isinstance(snapshot.get('metrics'), dict):
        problems.append('metrics 必须是字典')

    resolved_at = snapshot.get('resolved_at')
    if 'resolved_at' in snapshot:
        if not _is_non_empty_str(resolved_at):
            problems.append('resolved_at 必须是非空字符串')
        else:
            try:
                datetime.fromisoformat(resolved_at)
            except ValueError:
                problems.append(f'resolved_at 不是 ISO 时间：{resolved_at!r}')

    steps = snapshot.get('steps')
    if isinstance(steps, list):
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                problems.append(f'steps[{index}] 不是字典')
                continue
            for key in REQUIRED_STEP_KEYS:
                if key not in step:
                    problems.append(f'steps[{index}] 缺少字段 {key}')
            step_no = step.get('step_no')
            if 'step_no' in step and (not isinstance(step_no, int) or step_no < 1):
                problems.append(f'steps[{index}].step_no 必须是 ≥1 的整数')
            stage_no = step.get('stage_no')
            if stage_no is not None and (not isinstance(stage_no, int) or stage_no < 1):
                problems.append(f'steps[{index}].stage_no 必须是 ≥1 的整数')
            mode = step.get('approve_mode')
            if 'approve_mode' in step and mode not in VALID_APPROVE_MODES:
                problems.append(
                    f'steps[{index}].approve_mode 非法：{mode!r}（允许 {VALID_APPROVE_MODES}）')

    return problems


def snapshot_problems_for_log(snapshot: Any) -> str:
    """把问题清单压成一行，供 logger.warning 使用。"""
    return '；'.join(validate_snapshot(snapshot))


def build_snapshot_header() -> Dict[str, Any]:
    """写入方统一从这里取版本号，避免各处硬编码。"""
    return {'schema_version': SNAPSHOT_SCHEMA_VERSION}
