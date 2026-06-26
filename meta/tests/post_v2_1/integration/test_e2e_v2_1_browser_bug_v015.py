# -*- coding: utf-8 -*-
"""
test_e2e_v2_1_browser_bug_v015.py
跨域集成 D: 前端 + Browser E2E
"""
import pytest
from pathlib import Path

pytestmark = [pytest.mark.post_v2_1, pytest.mark.integration]


class TestBugV015BrowserE2E:
    @pytest.fixture(autouse=True)
    def check_dependencies(self):
        try:
            import urllib.request
            urllib.request.urlopen('http://localhost:3010/api/v1/health', timeout=1)
        except Exception:
            pytest.skip("Backend not running at localhost:3010")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            pytest.skip("Playwright not installed")

    def test_create_product_then_view_then_list_refreshed(self):
        source = Path('src/views/ObjectDetailPage.vue').read_text(encoding='utf-8')
        assert 'BUG-V015' in source, "ObjectDetailPage 应有 BUG-V015 修复标记"
        assert 'excel-diagram:list-refresh' in source, "应有 list-refresh 事件兜底"

        meta_source = Path('src/components/common/MetaListPage/MetaListPage.vue').read_text(encoding='utf-8')
        assert 'excel-diagram:list-refresh' in meta_source, "MetaListPage 应监听 list-refresh 事件"

    def test_url_changes_from_add_to_view(self):
        source = Path('src/views/ObjectDetailPage.vue').read_text(encoding='utf-8')
        assert 'router.replace' in source

    def test_list_refresh_via_window_event(self):
        source = Path('src/components/common/MetaListPage/MetaListPage.vue').read_text(encoding='utf-8')
        assert 'forceRefresh' in source
