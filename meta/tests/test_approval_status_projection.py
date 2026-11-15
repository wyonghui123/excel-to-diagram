# -*- coding: utf-8 -*-
"""审批投影纪律：`approval_status` 是单据侧只读投影，不得参与审批引擎判定。

spec-approval-workflow-2026-11-15 §3.3（D-AP-05）：
审批引擎（策略求值 / 任务创建 / 决策-生效）**不得读** `approval_status`，
否则「是否要审批 / 命中哪条策略」会从 tasks + approval_policies 漂移回单据缓存列。

实现方式：tokenize 只扫可执行代码里的 NAME token（注释、字符串、SQL 文本、
字典键 ``'approval_status': ...`` 均不计），因此「写投影」不受限，只禁「读判定」。
"""
import tokenize
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 审批引擎模块（判定链路），白名单外的新增模块需在此显式登记
_ENGINE_MODULES = (
    'meta/core/approval_meta_loader.py',
    'meta/core/decision_effect.py',
    'meta/services/approval_task_service.py',
    'meta/services/document_approval_service.py',
)

_FORBIDDEN_NAME = 'approval_status'


def _code_names(path: Path):
    with path.open('rb') as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            yield token


@pytest.mark.parametrize('module', _ENGINE_MODULES)
def test_approval_engine_does_not_read_approval_status(module):
    path = _PROJECT_ROOT / module
    assert path.exists(), f'审批引擎模块不存在: {module}'

    offenders = [
        token.start[0] for token in _code_names(path)
        if token.type == tokenize.NAME and token.string == _FORBIDDEN_NAME
    ]
    assert not offenders, (
        f'{module} 在可执行代码中读取了 {_FORBIDDEN_NAME}（行 {offenders}）；'
        '审批判定必须走 tasks / approval_policies，不得依赖单据侧投影列'
    )