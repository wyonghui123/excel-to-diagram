# -*- coding: utf-8 -*-
"""
test_frontend_bug_v015_list.py
覆盖 BUG-V015 第二个 fix: list 不刷新
"""
import pytest
from ._helpers import read_vue_source

pytestmark = [pytest.mark.post_v2_1, pytest.mark.frontend]

OBJECT_DETAIL_VUE = 'src/views/ObjectDetailPage.vue'
META_LIST_VUE = 'src/components/common/MetaListPage/MetaListPage.vue'
MO_PAGE_VUE = 'src/components/common/MultiObjectManagementPage/MultiObjectManagementPage.vue'


class TestBugV015ListRefresh:
    def test_handle_saved_calls_coordinator_refresh_all(self):
        source = read_vue_source(OBJECT_DETAIL_VUE)
        assert source, f"{OBJECT_DETAIL_VUE} not found"
        assert 'coordinator' in source
        assert 'refreshAll' in source

    def test_handle_saved_fallback_to_window_event(self):
        source = read_vue_source(OBJECT_DETAIL_VUE)
        assert "'excel-diagram:list-refresh'" in source
        assert 'dispatchEvent' in source

    def test_object_detail_page_injects_coordinator(self):
        source = read_vue_source(OBJECT_DETAIL_VUE)
        assert "inject('refreshCoordinator'" in source


class TestMetaListPageListensToWindowEvent:
    def test_meta_list_page_listens_to_list_refresh_event(self):
        source = read_vue_source(META_LIST_VUE)
        assert source, f"{META_LIST_VUE} not found"
        assert "'excel-diagram:list-refresh'" in source
        assert 'addEventListener' in source
        assert 'removeEventListener' in source

    def test_meta_list_page_calls_force_refresh_on_event(self):
        source = read_vue_source(META_LIST_VUE)
        assert source
        assert 'forceRefresh' in source


class TestRegressionBugV015List:
    def test_drawer_path_provides_coordinator(self):
        source = read_vue_source(MO_PAGE_VUE)
        assert source, f"{MO_PAGE_VUE} not found"
        assert "provide('refreshCoordinator'" in source
        assert 'setRefreshCoordinator' in source


class TestBugV015RegressionCheck:
    def test_object_detail_triggers_event_with_object_type(self):
        source = read_vue_source(OBJECT_DETAIL_VUE)
        assert source
        idx = source.find('excel-diagram:list-refresh')
        if idx > 0:
            context = source[idx:idx+500]
            assert 'objectType' in context or 'action' in context, (
                "事件应包含 objectType/action detail 供 MetaListPage 过滤"
            )
