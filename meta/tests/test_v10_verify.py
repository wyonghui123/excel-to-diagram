# -*- coding: utf-8 -*-
"""V10 版本可见性验证（原一次性 ad-hoc 脚本，2026-11-07 转为正式测试）

原始脚本在模块级直接发 HTTP 请求，被 pytest 收集时若 3010 无服务会直接抛
`ConnectionRefusedError`，产生 collection error 污染全量结果。
现改为 requires_server 标记的集成测试：服务不可达时 skip。
"""
import pytest
import requests

from meta.tests.shared.fixtures import backend_base_url

_BASE = backend_base_url()


@pytest.mark.integration
@pytest.mark.requires_server
def test_v10_visible_in_version_list():
    s = requests.Session()
    try:
        login = s.get(
            _BASE + '/api/v1/auth/dev-login?username=TEST333',
            allow_redirects=True, timeout=5,
        )
    except requests.exceptions.RequestException as exc:
        pytest.skip('需要 3010 后端服务：%s' % exc)
    assert login.status_code == 200

    list_resp = s.get(_BASE + '/api/v1/versions?page_size=50', timeout=10)
    assert list_resp.status_code == 200
    items = (list_resp.json().get('data') or {}).get('items') or []
    names = {v.get('name') for v in items}
    assert 'V10' in names, 'V10 未出现在版本列表（返回 %d 条：%s）' % (
        len(items), sorted(n for n in names if n)[:10])