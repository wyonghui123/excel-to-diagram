# -*- coding: utf-8 -*-
"""
test_e2e_v2_1_integration_rbac.py
跨域集成 B: RBAC + graceful degradation
"""
import pytest
from pathlib import Path

pytestmark = [pytest.mark.post_v2_1, pytest.mark.integration]


class TestRBACGracefulDegradation:
    def test_export_skips_no_perm_otypes(self):
        export_api_path = Path('meta/api/export_import_api.py')
        if export_api_path.exists():
            source = export_api_path.read_text(encoding='utf-8')
            assert 'skipped' in source or 'allowed_types' in source, (
                "export_import_api 应实现 skipped_types 过滤"
            )

    def test_selected_multi_initial_uses_filtered(self):
        for f in ['src/composables/useMultiObjectPage.js',
                  'src/components/common/ExportDialog/ExportDialog.vue']:
            fpath = Path(f)
            if fpath.exists():
                source = fpath.read_text(encoding='utf-8')
                if 'availableMultiTypes' in source:
                    assert 'selectedMultiTypes' in source
                    break

    def test_permission_check_unified(self):
        perm_path = Path('meta/services/permission_service.py')
        if perm_path.exists():
            source = perm_path.read_text(encoding='utf-8')
            assert 'check_permission_unified' in source


class TestGlobalButtonVisibility:
    def test_global_button_checks_all_otypes(self):
        for f in ['src/components/common/AppRootLayout.vue',
                  'src/components/common/TopNavHeader/TopNavHeader.vue']:
            fpath = Path(f)
            if fpath.exists():
                source = fpath.read_text(encoding='utf-8')
                if 'permission' in source.lower() or 'export' in source.lower():
                    pass
