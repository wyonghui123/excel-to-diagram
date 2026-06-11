"""关系范围类型 (category_type) sorting + filtering 测试

v1.4 P2 (2026-06-10) - 验证关系上 category_type 字段:
  1. sorting 按 enum sort_order 排序 (cross_domain=1 → same_module=4)
  2. filtering 下拉从 /api/v1/enums/hierarchy_scope_type/options 加载 4 个选项
  3. 过滤单个 category_type 生效 (单数/复数参数)
  4. 复数 category_types 支持逗号分隔 (?category_types=a,b)
  5. 排序 + 过滤组合使用

测试入口: python d:\\filework\\test.py --single meta/tests/test_relationship_scope_type.py
"""
import pytest
import requests
import sys
import os
from urllib.parse import urlencode

# admin_token fixture 在项目根 tests/fixtures/ (跨目录)
_HERE = os.path.dirname(os.path.abspath(__file__))           # .../meta/tests
_META_DIR = os.path.dirname(_HERE)                            # .../meta
_PROJECT_ROOT = os.path.dirname(_META_DIR)                    # d:/filework/excel-to-diagram
_FIXTURES_DIR = os.path.join(_PROJECT_ROOT, 'tests', 'fixtures')
sys.path.insert(0, _FIXTURES_DIR)

from admin_token import get_admin_cookie  # noqa: E402

BASE_URL = os.environ.get('TEST_API_URL', 'http://localhost:3010')


def _server_check():
    """检查后端 server 是否可访问: 探测 /api/v1/auth/dev-login 端点 (不依赖 cookie)"""
    try:
        r = requests.get(f'{BASE_URL}/api/v1/auth/dev-login?username=admin', timeout=2)
        return r.status_code == 200
    except Exception:
        return False


_SERVER_AVAILABLE = _server_check()
pytestmark = pytest.mark.integration


# ────────────────────────────────────────────
# Fixture: 登录 admin 获取 cookie
# ────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    """复用 admin cookie, 整个模块只登录 1 次"""
    if not _SERVER_AVAILABLE:
        pytest.skip("Backend not running")
    session = requests.Session()
    cookie = get_admin_cookie()
    if cookie:
        # [FIX 2026-06-10] get_admin_cookie() 返回 "auth_token=xxx" 形式 (整条 Set-Cookie 拆 ; 后的首段)
        # requests.cookies.set(name, value) 的 value 必须是裸值, 不能含 "auth_token=" 前缀
        token = cookie.split('=', 1)[1] if cookie.startswith('auth_token=') else cookie
        session.cookies.set('auth_token', token)
    # 验证 cookie 有效
    r = session.get(f'{BASE_URL}/api/v1/relationships?pageSize=1')
    if r.status_code != 200:
        pytest.skip(f"Cookie invalid, status={r.status_code}: {r.text[:200]}")
    return session


# ────────────────────────────────────────────
# 1. Enum options (filter dropdown 数据源)
# ────────────────────────────────────────────
class TestEnumOptionsForHierarchyScope:
    """验证 /api/v1/enums/hierarchy_scope_type/options 返回 4 个 sort_order 选项"""

    def test_options_returns_4_entries(self, admin_session):
        """filtering 下拉应返回 4 个关系范围类型"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/enums/hierarchy_scope_type/options',
            params={'is_active': 'true', 'pageSize': '1000'},
        )
        assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
        data = r.json()
        assert data.get('success') is True
        values = data.get('data', [])
        assert len(values) == 4, f"Expected 4 enum values, got {len(values)}"

    def test_options_sort_order_matches_yaml(self, admin_session):
        """sort_order 应与 hierarchies.yaml 中 hierarchy_scopes 顺序一致:
        1 cross_domain
        2 same_domain_cross_subdomain
        3 same_subdomain_cross_module
        4 same_module
        """
        r = admin_session.get(
            f'{BASE_URL}/api/v1/enums/hierarchy_scope_type/options',
            params={'is_active': 'true', 'pageSize': '1000'},
        )
        values = r.json().get('data', [])
        codes = [v.get('code') for v in values]
        assert codes == [
            'cross_domain',
            'same_domain_cross_subdomain',
            'same_subdomain_cross_module',
            'same_module',
        ], f"Order mismatch: {codes}"

    def test_options_have_code_and_name(self, admin_session):
        """每个 option 必须有 code (前端 value) 和 name (前端 label)"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/enums/hierarchy_scope_type/options',
            params={'is_active': 'true', 'pageSize': '1000'},
        )
        values = r.json().get('data', [])
        for v in values:
            assert v.get('code'), f"Missing code: {v}"
            assert v.get('name'), f"Missing name: {v}"


# ────────────────────────────────────────────
# 2. Sorting
# ────────────────────────────────────────────
class TestSortByCategoryType:
    """验证 sort_by=category_type 按 enum sort_order 升序/降序"""

    def _fetch_all_sorted(self, admin_session, sort_order):
        """拉取所有数据 (按 category_type 排序), 返回 category_type 序列"""
        all_types = []
        page = 1
        page_size = 50
        while True:
            r = admin_session.get(
                f'{BASE_URL}/api/v1/relationships',
                params={
                    'sort_by': 'category_type',
                    'sort_order': sort_order,
                    'page': page,
                    'pageSize': page_size,
                },
            )
            assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
            data = r.json()
            assert data.get('success') is True
            items = data.get('data', [])
            all_types.extend([i.get('category_type') for i in items])
            total = data.get('total', 0)
            if len(all_types) >= total or not items:
                break
            page += 1
        return all_types

    def test_sort_asc_orders_by_enum_sort_order(self, admin_session):
        """升序: cross_domain (1) → same_domain (2) → same_subdomain (3) → same_module (4)"""
        types = self._fetch_all_sorted(admin_session, 'asc')
        if len(types) < 2:
            pytest.skip("Not enough relationships to verify sort order")
        # 把 sort_order 映射到 index
        order_map = {
            'cross_domain': 1,
            'same_domain_cross_subdomain': 2,
            'same_subdomain_cross_module': 3,
            'same_module': 4,
        }
        indices = [order_map.get(t, 999) for t in types]
        assert indices == sorted(indices), (
            f"asc sort failed: indices={indices}\ntypes={types}"
        )

    def test_sort_desc_orders_reverse_enum_sort_order(self, admin_session):
        """降序: same_module (4) → same_subdomain (3) → same_domain (2) → cross_domain (1)"""
        types = self._fetch_all_sorted(admin_session, 'desc')
        if len(types) < 2:
            pytest.skip("Not enough relationships to verify sort order")
        order_map = {
            'cross_domain': 1,
            'same_domain_cross_subdomain': 2,
            'same_subdomain_cross_module': 3,
            'same_module': 4,
        }
        indices = [order_map.get(t, 999) for t in types]
        assert indices == sorted(indices, reverse=True), (
            f"desc sort failed: indices={indices}\ntypes={types}"
        )

    def test_sort_by_category_label_also_works(self, admin_session):
        """sort_by=category_label 也能成功 (按中文 label 排序)"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={'sort_by': 'category_label', 'sort_order': 'asc', 'pageSize': 5},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get('success') is True, f"Error: {data.get('message')}"

    def test_sort_by_category_label_asc_follows_sort_order(self, admin_session):
        """[FIX 2026-06-11] category_label 排序也应遵循 enum sort_order, 不按 Chinese collation.

        修复前: 同 < 跨, 所以 '同子领域跨服务模块' 排在 '跨领域' 前面, 破坏 sort_order
        修复后: SQL 统一用 idx, category_label 在 enrichment 阶段填充, 顺序一致
        """
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={'sort_by': 'category_label', 'sort_order': 'asc', 'pageSize': 200},
        )
        assert r.status_code == 200
        items = r.json().get('data', [])
        if len(items) < 2:
            pytest.skip("Not enough relationships to verify sort order")
        order_map = {
            'cross_domain': 1,
            'same_domain_cross_subdomain': 2,
            'same_subdomain_cross_module': 3,
            'same_module': 4,
        }
        indices = [order_map.get(it.get('category_type'), 999) for it in items]
        assert indices == sorted(indices), (
            f"category_label ASC should follow enum sort_order (idx), "
            f"not Chinese collation. indices={indices}"
        )

    def test_sort_by_category_label_desc_follows_reverse_sort_order(self, admin_session):
        """[FIX 2026-06-11] category_label DESC 排序遵循反向 enum sort_order"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={'sort_by': 'category_label', 'sort_order': 'desc', 'pageSize': 200},
        )
        assert r.status_code == 200
        items = r.json().get('data', [])
        if len(items) < 2:
            pytest.skip("Not enough relationships to verify sort order")
        order_map = {
            'cross_domain': 1,
            'same_domain_cross_subdomain': 2,
            'same_subdomain_cross_module': 3,
            'same_module': 4,
        }
        indices = [order_map.get(it.get('category_type'), 999) for it in items]
        assert indices == sorted(indices, reverse=True), (
            f"category_label DESC should follow reverse enum sort_order, "
            f"indices={indices}"
        )


# ────────────────────────────────────────────
# 3. Filtering
# ────────────────────────────────────────────
class TestFilterByCategoryType:
    """验证 category_type 过滤 (单数/复数)"""

    def test_filter_singular_cross_domain(self, admin_session):
        """?category_type=cross_domain 应只返回跨领域"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={'category_type': 'cross_domain', 'pageSize': 50},
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get('success') is True
        items = data.get('data', [])
        for item in items:
            assert item.get('category_type') == 'cross_domain', (
                f"Filter failed: {item.get('category_type')}"
            )

    def test_filter_singular_same_module(self, admin_session):
        """?category_type=same_module 应只返回同服务模块"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={'category_type': 'same_module', 'pageSize': 50},
        )
        data = r.json()
        assert data.get('success') is True
        for item in data.get('data', []):
            assert item.get('category_type') == 'same_module'

    def test_filter_plural_comma_separated(self, admin_session):
        """?category_types=same_module,same_subdomain_cross_module
        应只返回同服务模块 + 同子领域跨服务模块 (OR 逻辑)
        """
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={
                'category_types': 'same_module,same_subdomain_cross_module',
                'pageSize': 50,
            },
        )
        data = r.json()
        assert data.get('success') is True, f"Error: {data.get('message')}"
        allowed = {'same_module', 'same_subdomain_cross_module'}
        for item in data.get('data', []):
            ct = item.get('category_type')
            assert ct in allowed, f"Unexpected category_type: {ct} (filter not applied)"

    def test_filter_plural_multi_value(self, admin_session):
        """?category_types=a&category_types=b 复数多值形式"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params=[
                ('category_types', 'same_module'),
                ('category_types', 'same_subdomain_cross_module'),
                ('pageSize', '50'),
            ],
        )
        data = r.json()
        assert data.get('success') is True
        allowed = {'same_module', 'same_subdomain_cross_module'}
        for item in data.get('data', []):
            assert item.get('category_type') in allowed

    def test_filter_total_consistency(self, admin_session):
        """过滤后 total 应等于过滤前总数减去不符合条件的记录"""
        r_all = admin_session.get(
            f'{BASE_URL}/api/v1/relationships', params={'pageSize': 1},
        )
        total_all = r_all.json().get('total', 0)

        # 单独查询每个 category_type
        per_type_totals = {}
        for ct in ['cross_domain', 'same_domain_cross_subdomain',
                   'same_subdomain_cross_module', 'same_module']:
            r = admin_session.get(
                f'{BASE_URL}/api/v1/relationships',
                params={'category_type': ct, 'pageSize': 1},
            )
            per_type_totals[ct] = r.json().get('total', 0)

        sum_per_type = sum(per_type_totals.values())
        assert sum_per_type == total_all, (
            f"Filter partition failed: total_all={total_all}, "
            f"per_type={per_type_totals}, sum={sum_per_type}"
        )


# ────────────────────────────────────────────
# 4. Combined: sort + filter
# ────────────────────────────────────────────
class TestSortAndFilterCombined:
    """验证排序 + 过滤组合"""

    def test_filter_then_sort_asc(self, admin_session):
        """filter=same_module + sort=category_type asc 仍生效"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={
                'category_type': 'same_module',
                'sort_by': 'category_type',
                'sort_order': 'asc',
                'pageSize': 50,
            },
        )
        data = r.json()
        assert data.get('success') is True
        items = data.get('data', [])
        for item in items:
            assert item.get('category_type') == 'same_module'
        # single category_type, sort trivially holds
        assert len(items) == data.get('total', 0) or len(items) == 50

    def test_filter_multi_then_sort_asc(self, admin_session):
        """filter=多个 + sort=category_type asc 应按 enum sort_order 排序"""
        r = admin_session.get(
            f'{BASE_URL}/api/v1/relationships',
            params={
                'category_types': 'cross_domain,same_module',
                'sort_by': 'category_type',
                'sort_order': 'asc',
                'pageSize': 50,
            },
        )
        data = r.json()
        assert data.get('success') is True
        items = data.get('data', [])
        order_map = {'cross_domain': 1, 'same_module': 4}
        indices = [order_map.get(i.get('category_type'), 999) for i in items]
        assert indices == sorted(indices), f"Combined sort+filter failed: {indices}"


# ────────────────────────────────────────────
# 4.5 v2 端点 (/api/v2/bo/relationship) ordering=category_label / category_type
# ────────────────────────────────────────────
class TestV2EndpointCategorySort:
    """[FIX 2026-06-11] v2 端点 ordering=category_label / category_type 必须:
    1. SQL 排序按 enum sort_order (id=29 sort_key=1, id=2-28 sort_key=3, id=1-27 sort_key=4)
    2. enrichment 后 category_label/category_type 字段必须正确填充 (不能全是 fallback '同服务模块')
    修复前 bug: compute_scope 时 source_domain_id 全是 None, 所有行 fallback 为 same_module
    """

    @pytest.mark.parametrize("sort_field", ["category_label", "category_type"])
    def test_v2_asc_actually_sorts_by_enum_order(self, admin_session, sort_field):
        """ASC: 跨领域(1) → 同子领域跨服务模块(3) → 同服务模块(4)"""
        r = admin_session.get(
            f'{BASE_URL}/api/v2/bo/relationship',
            params={'ordering': sort_field, 'page_size': 200},
        )
        assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
        body = r.json()
        items = body.get('data', {}).get('items', [])
        if len(items) < 2:
            pytest.skip("Not enough relationships to verify sort order")
        order_map = {
            'cross_domain': 1,
            'same_domain_cross_subdomain': 2,
            'same_subdomain_cross_module': 3,
            'same_module': 4,
        }
        # [FIX 2026-06-11] enrichment 后的 category_type 字段必须真实反映层级,
        # 不能全是 fallback 'same_module' (这是 fix 前的核心 bug).
        distinct = {it.get('category_type') for it in items}
        assert len(distinct) > 1, (
            f"v2 enrichment 错误: 所有 category_type 都被 fallback 为 {distinct!r}, "
            f"未根据 source/target hierarchy 计算. 这是 compute_scope 输入缺少 source_domain_id 导致的."
        )
        indices = [order_map.get(it.get('category_type'), 999) for it in items]
        assert indices == sorted(indices), (
            f"v2 {sort_field} ASC should follow enum sort_order, indices={indices}"
        )

    @pytest.mark.parametrize("sort_field", ["category_label", "category_type"])
    def test_v2_desc_actually_sorts_by_reverse_enum_order(self, admin_session, sort_field):
        """DESC: 同服务模块(4) → 同子领域跨服务模块(3) → 跨领域(1)"""
        r = admin_session.get(
            f'{BASE_URL}/api/v2/bo/relationship',
            params={'ordering': f'-{sort_field}', 'page_size': 200},
        )
        assert r.status_code == 200, f"Status {r.status_code}: {r.text[:200]}"
        body = r.json()
        items = body.get('data', {}).get('items', [])
        if len(items) < 2:
            pytest.skip("Not enough relationships to verify sort order")
        order_map = {
            'cross_domain': 1,
            'same_domain_cross_subdomain': 2,
            'same_subdomain_cross_module': 3,
            'same_module': 4,
        }
        indices = [order_map.get(it.get('category_type'), 999) for it in items]
        assert indices == sorted(indices, reverse=True), (
            f"v2 {sort_field} DESC should follow reverse enum sort_order, indices={indices}"
        )


# ────────────────────────────────────────────
# 5. UI yaml 配置 + 元数据验证
# ────────────────────────────────────────────
class TestUIViewConfig:
    """验证 relationship.yaml 中 category_type 字段已正确配置 filter/sort"""

    def test_yaml_has_filter_config_for_category_type(self):
        """ui_view_config.filter.filters 应包含 category_type"""
        import yaml
        yaml_path = os.path.join(
            _PROJECT_ROOT, 'meta', 'schemas', 'relationship.yaml'
        )
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        filters = data.get('ui_view_config', {}).get('filter', {}).get('filters', [])
        filter_keys = [f.get('key') for f in filters]
        assert 'category_type' in filter_keys, (
            f"ui_view_config.filter.filters missing category_type, got {filter_keys}"
        )

        # 找到该 filter 配置
        cat_filter = next(f for f in filters if f.get('key') == 'category_type')
        assert cat_filter.get('source') == 'enum_value'
        assert cat_filter.get('enum_type') == 'hierarchy_scope_type'

    def test_yaml_list_has_no_duplicate_scope_column(self):
        """[FIX 2026-06-10] list view 不再同时显示 category_label + category_type
        (两列展示同一枚举的不同形式, 视觉冗余). 只保留 category_label.
        """
        import yaml
        yaml_path = os.path.join(
            _PROJECT_ROOT, 'meta', 'schemas', 'relationship.yaml'
        )
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        columns = data.get('ui_view_config', {}).get('list', {}).get('columns', [])
        column_keys = [c.get('key') for c in columns]
        # category_label 保留
        assert 'category_label' in column_keys, (
            f"category_label column missing: {column_keys}"
        )
        # category_type 不再出现在 list (UI 视觉上去重)
        assert 'category_type' not in column_keys, (
            f"category_type 列应从 list 移除 (与 category_label 重复), got: {column_keys}"
        )

    def test_yaml_field_has_value_help(self):
        """category_type 字段应有 value_help 引用 hierarchy_scope_type"""
        import yaml
        yaml_path = os.path.join(
            _PROJECT_ROOT, 'meta', 'schemas', 'relationship.yaml'
        )
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        fields = data.get('fields', [])
        cat_field = next((f for f in fields if f.get('id') == 'category_type'), None)
        assert cat_field is not None
        value_help = cat_field.get('value_help', {})
        assert value_help.get('source', {}).get('enum_type_id') == 'hierarchy_scope_type'
