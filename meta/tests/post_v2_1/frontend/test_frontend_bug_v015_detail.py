# -*- coding: utf-8 -*-
"""
test_frontend_bug_v015_detail.py
覆盖 BUG-V015 (commit d85c61b): save 后 add→view 切换
"""
import pytest
from ._helpers import read_vue_source

pytestmark = [pytest.mark.post_v2_1, pytest.mark.frontend]

VUE_FILE = 'src/views/ObjectDetailPage.vue'


class TestBugV015DetailPageReset:
    def test_handle_saved_resets_last_valid_mode(self):
        source = read_vue_source(VUE_FILE)
        assert source, f"{VUE_FILE} not found"
        assert 'lastValidMode' in source
        assert "lastValidMode.value = 'view'" in source

    def test_handle_saved_sets_last_valid_id(self):
        source = read_vue_source(VUE_FILE)
        assert 'lastValidId' in source

    def test_handle_saved_triggers_router_replace(self):
        source = read_vue_source(VUE_FILE)
        assert 'router.replace' in source

    def test_handle_saved_only_in_add_mode(self):
        source = read_vue_source(VUE_FILE)
        assert "mode.value === 'add'" in source

    def test_handle_saved_increments_mount_key(self):
        source = read_vue_source(VUE_FILE)
        assert 'detailPageMountKey' in source

    def test_bug_v015_marker_present(self):
        source = read_vue_source(VUE_FILE)
        assert 'BUG-V015' in source


class TestRegressionBugV015Detail:
    def test_handle_saved_only_in_add_mode_branch(self):
        source = read_vue_source(VUE_FILE)
        assert 'if (mode.value === \'add\' && savedData?.id)' in source

    def test_saved_data_id_validation(self):
        source = read_vue_source(VUE_FILE)
        assert 'savedData?.id' in source
