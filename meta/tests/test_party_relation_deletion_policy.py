# -*- coding: utf-8 -*-
"""P1-5 · party_relation 补齐 deletion_policy（2026-10-28）

背景
----
关系是客户 / 供应商档案的 1:1 锚：`customer_accounts.relation_id` /
`vendor_accounts.relation_id` 指向 `party_relations.id`。旧 schema 缺
`deletion_policy` 段 ⇒ 删除关系时引用检查静默跳过，档案的锚会被删空。

关键点
------
声明的 `foreign_key` 必须写档案表的实际列名 `relation_id`。
`ReferenceRestrictChecker` 直接按声明列名拼 SQL，不做 `{父对象类型}_id`
派生映射 —— 该派生只存在于 UI 的 associationFilters，与本检查器无关。

测试隔离
--------
本文件用内存假数据源（真实 SQLite 只被 `test_deletion_policy_restrict_on.py`
那类集成测试使用）。这样既不碰 `architecture.db`，也不触发 conftest 的
raw-SQL 门禁（该门禁按文件文本匹配，会整文件 skip）。
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, PROJECT_ROOT)

from meta.core.reference_restrict_checker import ReferenceRestrictChecker
from meta.core.yaml_loader import load_yaml_file

_SCHEMA_DIR = os.path.join(PROJECT_ROOT, 'meta', 'schemas')

pytestmark = pytest.mark.unit


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDataSource:
    """按表名返回引用计数的假数据源，同时记录发出去的 SQL。"""

    def __init__(self, counts=None):
        self.counts = counts or {}
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, list(params or [])))
        for table, count in self.counts.items():
            if 'FROM {0} '.format(table) in sql:
                return _FakeCursor((count,))
        return _FakeCursor((0,))


def _load_party_relation():
    return load_yaml_file(os.path.join(_SCHEMA_DIR, 'party_relation.yaml'))


class TestPartyRelationDeletionPolicyYaml:
    """schema 是「谁引用我」的唯一真源，断言只读 YAML。"""

    def test_yaml_declares_restrict_on_both_accounts(self):
        policy = getattr(_load_party_relation(), 'deletion_policy', None)
        assert policy is not None, 'party_relation.yaml 缺少 deletion_policy'

        pairs = {(r.table, r.foreign_key) for r in policy.restrict_on}
        assert pairs == {
            ('customer_accounts', 'relation_id'),
            ('vendor_accounts', 'relation_id'),
        }, f'restrict_on 声明不符，实际 {pairs}'

        # 前端把 message 原样展示，不能落到 _fallback_message 的通用文案
        assert all(r.message for r in policy.restrict_on), '每条 restrict_on 都必须有中文提示'
        assert policy.cascade_delete == []


class TestPartyRelationRestrictCheck:
    """ReferenceRestrictChecker 按声明列名拼 SQL，不做派生映射。"""

    def test_customer_account_reference_blocked(self):
        ds = _FakeDataSource({'customer_accounts': 1})

        violations = ReferenceRestrictChecker.check_details(ds, _load_party_relation(), 7)

        assert len(violations) == 1, f'应有 1 条违规，实际 {violations}'
        v = violations[0]
        assert v['table'] == 'customer_accounts'
        assert v['foreign_key'] == 'relation_id'
        assert v['count'] == 1
        assert '客户档案' in v['message']

        # 命中的必须是档案表实际列名，而不是派生的 party_relation_id
        sql = [s for s in ds.calls if 'customer_accounts' in s[0]][0]
        assert 'WHERE relation_id = ?' in sql[0], f'SQL 列名不符: {sql[0]}'

    def test_vendor_account_reference_blocked(self):
        ds = _FakeDataSource({'vendor_accounts': 1})

        violations = ReferenceRestrictChecker.check_details(ds, _load_party_relation(), 8)

        assert len(violations) == 1, f'应有 1 条违规，实际 {violations}'
        assert violations[0]['table'] == 'vendor_accounts'
        assert violations[0]['foreign_key'] == 'relation_id'
        assert '供应商档案' in violations[0]['message']

    def test_no_account_reference_passes(self):
        ds = _FakeDataSource()

        assert ReferenceRestrictChecker.check_details(ds, _load_party_relation(), 9) == []

    def test_null_record_id_short_circuits(self):
        ds = _FakeDataSource({'customer_accounts': 1})

        assert ReferenceRestrictChecker.check_details(ds, _load_party_relation(), None) == []
        assert ds.calls == [], 'record_id 为空时不应查库'
