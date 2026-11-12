# -*- coding: utf-8 -*-
"""preview 服务与权限预览聚合契约测试。

[TEST-EFF P2-1] 由两个 <=2 用例的小文件合并而来，减少逐文件启动开销：
- test_preview_service_init.py
- test_permission_preview.py
"""
import pytest

from meta.services.org_service import OrgService


def test_preview_service_module_imports():
    """preview_service 模块应能正常导入"""
    from meta.services import preview_service
    assert preview_service is not None


def test_preview_service_has_aggregate_annotations():
    """preview_service 应包含 aggregate_annotations_for_targets 函数"""
    from meta.services.preview_service import aggregate_annotations_for_targets
    assert callable(aggregate_annotations_for_targets)


def test_has_get_permission_preview():
    """契约：聚合内核方法存在且可调用"""
    svc = OrgService.__new__(OrgService)
    assert hasattr(svc, 'get_permission_preview')
    assert callable(svc.get_permission_preview)


def test_ancestor_chain_shape():
    """契约：_ancestor_chain 返回 [本org, 父, 祖父...]，relation/depth 正确"""
    class FakeDS:
        class Cursor:
            def __init__(self, rows):
                self._rows = rows
                self.description = [( 'id', ), ( 'name', ), ( 'parent_id', )]
            def fetchall(self):
                rows = []
                for r in self._rows:
                    rows.append((r['id'], r['name'], r['parent_id'])) if isinstance(r, dict) else None
                return self._rows
            def fetchone(self):
                return None
        def execute(self, sql, params=None):
            if sql.startswith('SELECT id, name, parent_id'):
                # 构造 orgs: 1->2->3(顶层). parent_id 查询返回父记录
                pass
            return self.Cursor([])

    svc = OrgService.__new__(OrgService)
    svc.ds = FakeDS()

    # 桩 get_all_ancestor_orgs：org5 的祖先为 [3, 1]（父3，祖父1）
    svc.get_all_ancestor_orgs = lambda org_id: [3, 1] if org_id == 5 else []
    chain = svc._ancestor_chain(5)
    assert [n['org_id'] for n in chain] == [5, 3, 1]
    assert chain[0]['relation'] == 'direct'
    assert chain[0]['depth'] == 0
    assert chain[1]['relation'] == 'inherited'
    assert chain[1]['depth'] == 1
    assert chain[2]['depth'] == 2
