# -*- coding: utf-8 -*-
"""销售行类型确定测试（单据类型 × 物料组 → 行类型 / 回落默认行类型）

依据: meta/schemas/line_type_assignment.yaml 头注释「命中规则」
"""

import pytest

pytestmark = pytest.mark.unit

from meta.services.line_type_service import (
    LineTypeResolver,
    get_line_type_resolver,
)


class _FakeDS:
    def __init__(self, assignments=None, doc_types=None, raise_on_query=False):
        self.assignments = assignments or []
        self.doc_types = doc_types or []
        self.raise_on_query = raise_on_query

    def query(self, sql, params=None):
        if self.raise_on_query:
            raise RuntimeError('db down')
        if 'FROM line_type_assignments' in sql:
            return [a for a in self.assignments if a.get('status') == 'active']
        if 'FROM type_definitions' in sql:
            return [d for d in self.doc_types if d.get('status') == 'active']
        raise AssertionError(f'未预期的 SQL: {sql}')


def _assignment(id, doc_type_id=1, item_group_id=None, rank=None,
                line_type_id=10, status='active'):
    return {'id': id, 'document_type_id': doc_type_id,
            'item_group_id': item_group_id, 'specificity_rank': rank,
            'line_type_id': line_type_id, 'status': status}


def _doc_type(id=1, code='TA', default_type_id=10, status='active'):
    return {'id': id, 'code': code, 'default_type_id': default_type_id,
            'status': status}


def _resolver(assignments=None, doc_types=None, **kw):
    return LineTypeResolver(
        _FakeDS(assignments=assignments, doc_types=doc_types or [_doc_type()], **kw))


class TestResolve:
    def test_wildcard_assignment_hits(self):
        r = _resolver([_assignment(1, item_group_id=None, line_type_id=20)])
        got = r.resolve(1, item_group_id=7)
        assert got['line_type_id'] == 20
        assert got['source'] == 'assignment'
        assert got['assignment_id'] == 1

    def test_specific_item_group_wins_by_rank(self):
        r = _resolver([
            _assignment(1, item_group_id=None, rank=900, line_type_id=10),
            _assignment(2, item_group_id=7, rank=100, line_type_id=20),
        ])
        assert r.resolve(1, 7)['line_type_id'] == 20
        assert r.resolve(1, 8)['line_type_id'] == 10

    def test_missing_item_group_only_matches_wildcard(self):
        r = _resolver([
            _assignment(1, item_group_id=None, rank=900, line_type_id=10),
            _assignment(2, item_group_id=7, rank=100, line_type_id=20),
        ])
        got = r.resolve(1)
        assert got['line_type_id'] == 10
        assert got['assignment_id'] == 1

    def test_falls_back_to_doc_type_default(self):
        r = _resolver([], doc_types=[_doc_type(default_type_id=33)])
        got = r.resolve(1, 7)
        assert got['line_type_id'] == 33
        assert got['source'] == 'default'
        assert got['assignment_id'] is None

    def test_inactive_assignment_ignored(self):
        r = _resolver([_assignment(1, item_group_id=None, line_type_id=20,
                                   status='inactive')])
        assert r.resolve(1, 7)['source'] == 'default'

    def test_unknown_doc_type_returns_missing(self):
        r = _resolver([])
        got = r.resolve(99, 7)
        assert got['line_type_id'] is None
        assert got['source'] == 'missing'

    def test_inactive_doc_type_returns_missing(self):
        r = _resolver([], doc_types=[_doc_type(status='inactive')])
        assert r.resolve(1, 7)['source'] == 'missing'

    def test_no_default_and_no_assignment(self):
        r = _resolver([], doc_types=[_doc_type(default_type_id=None)])
        got = r.resolve(1, 7)
        assert got['line_type_id'] is None
        assert got['source'] == 'missing'

    def test_load_failure_is_silent(self):
        r = _resolver(raise_on_query=True)
        assert r.resolve(1, 7)['source'] == 'missing'


class TestExplain:
    def test_explain_lists_matched_candidates(self):
        r = _resolver([
            _assignment(1, item_group_id=None, rank=900, line_type_id=10),
            _assignment(2, item_group_id=7, rank=100, line_type_id=20),
            _assignment(3, item_group_id=8, rank=50, line_type_id=30),
        ])
        info = r.explain(1, 7)
        assert info['line_type_id'] == 20
        assert [c['assignment_id'] for c in info['candidates']] == [2, 1]
        assert info['default_type_id'] == 10


class TestCache:
    def test_invalidate_reloads(self):
        ds = _FakeDS(assignments=[], doc_types=[_doc_type(default_type_id=10)])
        r = LineTypeResolver(ds)
        assert r.resolve(1, 7)['line_type_id'] == 10
        ds.doc_types = [_doc_type(default_type_id=44)]
        assert r.resolve(1, 7)['line_type_id'] == 10  # 命中缓存
        r.invalidate()
        assert r.resolve(1, 7)['line_type_id'] == 44

    def test_module_level_singleton_is_stable(self):
        assert get_line_type_resolver() is get_line_type_resolver()
