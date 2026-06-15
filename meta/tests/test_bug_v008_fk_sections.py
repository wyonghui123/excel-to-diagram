# -*- coding: utf-8 -*-
"""
[FIX 2026-06-14] BUG-V008 验证:
1) relationship 列表 UIConfig 包含 FK 链路列 (源/目标的 domain/sub_domain/service_module name)
2) relationship 列表 API 返回上述字段值 (后端 redundancy engine 已填充)
3) sub_domain 详情页 child_sections 包含 annotation (供外层 ObjectDetailPage 渲染)
4) DetailPage 在 standalone=true 时不重复创建 child_sections section
"""

import pytest
import requests
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

from meta.services.auth_provider import UserInfo

pytestmark = pytest.mark.integration

BASE_URL = os.environ.get('TEST_API_URL', 'http://localhost:3010')


def _server_check():
    # / 返回 500, 用更可靠的健康检查端点
    try:
        r = requests.get(f'http://127.0.0.1:3010/api/v2/ui-config/relationship', timeout=2)
        return r.status_code in (200, 401, 403)  # 401/403 表示服务在线
    except Exception:
        return False


_SERVER_AVAILABLE = _server_check()
_skip_reason = "Server not running on port 3010"
skipif_no_server = pytest.mark.skipif(not _SERVER_AVAILABLE, reason=_skip_reason)


def _dev_login():
    """通过 dev-login 端点获取 cookie auth_token"""
    s = requests.Session()
    r = s.post(f'{BASE_URL}/api/v2/auth/dev-login', json={'username': 'admin'}, timeout=10)
    if r.status_code == 200:
        return s
    pytest.skip(f"dev-login failed: {r.status_code} {r.text[:200]}")


@skipif_no_server
def test_relationship_ui_config_has_fk_columns():
    """验证: relationship UIConfig list.columns 包含 6 个 FK 链路列"""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/relationship', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    list_cfg = cfg.get('ui_view_config', {}).get('list', {})
    cols = list_cfg.get('columns', [])
    col_keys = [c.get('key') for c in cols]
    expected = [
        'source_domain_name',
        'source_sub_domain_name',
        'source_service_module_name',
        'target_domain_name',
        'target_sub_domain_name',
        'target_service_module_name',
    ]
    missing = [k for k in expected if k not in col_keys]
    assert not missing, f"relationship.list.columns 缺少: {missing} (实际: {col_keys})"


@skipif_no_server
def test_relationship_list_returns_fk_fields():
    """验证: relationship 列表 API 返回 FK 链路字段 (后端 redundancy engine 填充)"""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/bo/relationships?page_size=5', timeout=10)
    assert r.status_code == 200, f"list 失败: {r.status_code} {r.text[:300]}"
    data = r.json().get('data', [])
    if not data:
        pytest.skip("无关系数据, 跳过字段值验证")
    item = data[0]
    # 至少校验字段存在 (值可能为 null, 但字段 key 应在响应中)
    fk_keys = [
        'source_domain_name', 'source_sub_domain_name', 'source_service_module_name',
        'target_domain_name', 'target_sub_domain_name', 'target_service_module_name',
    ]
    for k in fk_keys:
        assert k in item, f"响应中缺少字段: {k} (keys: {list(item.keys())})"


@skipif_no_server
def test_sub_domain_ui_config_has_annotation_child_section():
    """验证: sub_domain UIConfig child_sections 包含 annotation"""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/sub_domain', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    child_sections = cfg.get('ui_view_config', {}).get('child_sections', [])
    keys = [cs.get('child_object') for cs in child_sections]
    assert 'annotation' in keys, f"sub_domain.child_sections 缺少 annotation: {keys}"


@skipif_no_server
def test_relationship_ui_config_has_annotation_child_section():
    """验证: relationship UIConfig child_sections 包含 annotation"""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/relationship', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    child_sections = cfg.get('ui_view_config', {}).get('child_sections', [])
    keys = [cs.get('child_object') for cs in child_sections]
    assert 'annotation' in keys, f"relationship.child_sections 缺少 annotation: {keys}"


@skipif_no_server
def test_business_object_list_has_all_fk_columns():
    """[FIX 2026-06-14] BUG-V008 扩展: business_object 列表补 version_name 后,
    所有 4 个 FK 链路 *_name 列都必须在 ui_view_config.list.columns 中."""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/business_object', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    cols = cfg.get('ui_view_config', {}).get('list', {}).get('columns', [])
    col_keys = [c.get('key') for c in cols]
    expected = ['service_module_name', 'sub_domain_name', 'domain_name', 'version_name']
    missing = [k for k in expected if k not in col_keys]
    assert not missing, f"business_object.list.columns 缺少: {missing} (实际: {col_keys})"


@skipif_no_server
def test_version_list_has_product_name_column():
    """[FIX 2026-06-14] BUG-V008 扩展: version 列表补 product_name 列."""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/version', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    cols = cfg.get('ui_view_config', {}).get('list', {}).get('columns', [])
    col_keys = [c.get('key') for c in cols]
    assert 'product_name' in col_keys, f"version.list.columns 缺少 product_name: {col_keys}"


@skipif_no_server
def test_domain_list_has_version_name_column():
    """[FIX 2026-06-14] BUG-V008 扩展: domain 列表补 version_name 列."""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/domain', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    cols = cfg.get('ui_view_config', {}).get('list', {}).get('columns', [])
    col_keys = [c.get('key') for c in cols]
    assert 'version_name' in col_keys, f"domain.list.columns 缺少 version_name: {col_keys}"


@skipif_no_server
def test_sub_domain_list_has_version_name_column():
    """[FIX 2026-06-14] BUG-V008 扩展: sub_domain 列表补 version_name 列."""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/sub_domain', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    cols = cfg.get('ui_view_config', {}).get('list', {}).get('columns', [])
    col_keys = [c.get('key') for c in cols]
    assert 'version_name' in col_keys, f"sub_domain.list.columns 缺少 version_name: {col_keys}"


@skipif_no_server
def test_service_module_list_has_version_name_column():
    """[FIX 2026-06-14] BUG-V008 扩展: service_module 列表补 version_name 列."""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/service_module', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    cols = cfg.get('ui_view_config', {}).get('list', {}).get('columns', [])
    col_keys = [c.get('key') for c in cols]
    assert 'version_name' in col_keys, f"service_module.list.columns 缺少 version_name: {col_keys}"


@skipif_no_server
def test_relationship_list_has_version_name_column():
    """[FIX 2026-06-14] BUG-V008 扩展: relationship 列表补 version_name 列."""
    s = _dev_login()
    r = s.get(f'{BASE_URL}/api/v2/ui-config/relationship', timeout=10)
    assert r.status_code == 200, f"getUIConfig 失败: {r.status_code} {r.text[:300]}"
    cfg = r.json().get('data') or r.json()
    cols = cfg.get('ui_view_config', {}).get('list', {}).get('columns', [])
    col_keys = [c.get('key') for c in cols]
    assert 'version_name' in col_keys, f"relationship.list.columns 缺少 version_name: {col_keys}"


if __name__ == '__main__':
    import subprocess
    sys.exit(subprocess.call([sys.executable, '-m', 'pytest', __file__, '-v']))
