# -*- coding: utf-8 -*-
"""读面字段脱敏（P2）验收测试 (2026-10-29)

依据: docs/superpowers/specs/2026-10-29-pii-field-level-security-spec.md §5 (P2)
覆盖:
  A. 服务层: field_masking_service 的分类与脱敏规则
     - secret (LOG_REDACT_IDS)          -> [REDACTED]
     - restricted + 手机号             -> 138****8000
     - restricted + 邮箱               -> a***@domain
     - restricted + 其余（哈希/历史）   -> [REDACTED]
     - 非敏感字段 / 空值               -> 原值
     - 未知对象类型 / 入参不被修改      -> no-op / 副本
     - change_history 命中字段同样脱敏
  B. 接口层: admin 身份 GET /api/v2/bo/user/<id> 与列表读
     - 响应中不存在 60 字符以上 PBKDF2 哈希
     - password_hash / password_history 命中即已替换（非明文）

背景: UI 把 password_hash / password_history 藏起来（ui.visible=False），
     但读接口此前原样直出 —— 「看不到」不等于「拿不到」。

测试隔离: 不直接读写 architecture.db；临时用户经 API 创建，测试后删除。
"""
import json
import os
import re
import sys
from types import SimpleNamespace

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from meta.services.field_masking_service import (  # noqa: E402
    REDACTED, _classify_field, mask_record, mask_records,
)

# PBKDF2 / 长十六进制哈希形态
_HASH_RE = re.compile(r'^(?:pbkdf2[:$].{40,}|[0-9a-fA-F]{60,})$')


# ────────────────────────────────────────
# 辅助
# ────────────────────────────────────────
def _field(field_id, sensitivity=''):
    """构造最小 MetaField 替身（分类只依赖 id / db_column / semantics.sensitivity）"""
    return SimpleNamespace(
        id=field_id,
        db_column=field_id,
        semantics=SimpleNamespace(sensitivity=sensitivity),
    )


def _iter_strings(node):
    """递归收集 JSON 结构中的所有字符串值"""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _iter_strings(value)


def _assert_no_plain_hash(payload):
    """断言响应中不含明文密码哈希（含 JSON 数组里内嵌的哈希）"""
    for text in _iter_strings(payload):
        stripped = text.strip()
        assert not _HASH_RE.match(stripped), f'读面泄漏明文哈希: {stripped[:20]}...'
        for token in re.split(r'[^0-9a-zA-Z:$]+', stripped):
            assert not _HASH_RE.match(token), f'读面泄漏明文哈希: {stripped[:20]}...'


@pytest.fixture(scope='module', autouse=True)
def _ensure_schema_registry():
    """确保元模型已注册（mask_record 依赖 registry.get(object_type)）"""
    from meta.core.models import registry
    from meta.core.yaml_loader import get_yaml_schema_dir, register_from_directory

    if not getattr(registry, '_objects', None):
        register_from_directory(get_yaml_schema_dir())
    yield


# ────────────────────────────────────────
# A. 服务层：字段分类
# ────────────────────────────────────────
class TestClassifyField:
    """_classify_field 的分类口径（secret 优先于 sensitivity）"""

    @pytest.mark.unit
    def test_log_redact_id_is_secret(self):
        assert _classify_field(_field('password')) == 'secret'

    @pytest.mark.unit
    def test_restricted_phone(self):
        assert _classify_field(_field('mobile', 'restricted')) == 'restricted_phone'

    @pytest.mark.unit
    def test_restricted_email(self):
        assert _classify_field(_field('email', 'restricted')) == 'restricted_email'

    @pytest.mark.unit
    def test_restricted_generic(self):
        assert _classify_field(_field('password_hash', 'restricted')) == 'restricted'

    @pytest.mark.unit
    def test_unmarked_field_not_masked(self):
        assert _classify_field(_field('username')) is None

    @pytest.mark.unit
    def test_internal_sensitivity_not_masked(self):
        """internal 不是读面脱敏对象（仅 restricted / secret 脱敏）"""
        assert _classify_field(_field('must_change_password', 'internal')) is None


# ────────────────────────────────────────
# A. 服务层：单条脱敏
# ────────────────────────────────────────
class TestMaskRecord:
    """mask_record 对真实 schema 字段的脱敏结果"""

    @pytest.mark.unit
    def test_secret_redacted(self):
        masked = mask_record('user', {'username': 'alice', 'password': 'P@ssw0rd'})
        assert masked['password'] == REDACTED
        assert masked['username'] == 'alice'

    @pytest.mark.unit
    def test_restricted_hash_redacted(self):
        masked = mask_record('user', {'password_hash': 'a' * 80})
        assert masked['password_hash'] == REDACTED

    @pytest.mark.unit
    def test_restricted_history_redacted(self):
        """password_history 是 JSON 数组字符串，不能原样直出"""
        raw = json.dumps(['a' * 80, 'b' * 80])
        masked = mask_record('user', {'password_history': raw})
        assert masked['password_history'] == REDACTED

    @pytest.mark.unit
    def test_non_sensitive_preserved(self):
        record = {'username': 'alice', 'display_name': 'Alice', 'must_change_password': 1}
        masked = mask_record('user', record)
        assert masked['username'] == 'alice'
        assert masked['display_name'] == 'Alice'
        assert masked['must_change_password'] == 1

    @pytest.mark.unit
    def test_empty_values_kept(self):
        """空值保持原样：不制造额外信息"""
        masked = mask_record('user', {'password_hash': '', 'password_history': None})
        assert masked['password_hash'] == ''
        assert masked['password_history'] is None

    @pytest.mark.unit
    def test_person_profile_phone_masked(self):
        masked = mask_record('person_profile', {'id': 1, 'party_id': 100,
                                                'mobile': '13800138000'})
        assert masked['mobile'] == '138****8000'
        assert masked['party_id'] == 100

    @pytest.mark.unit
    def test_person_profile_email_masked(self):
        masked = mask_record('person_profile', {'email': 'alice@example.com'})
        assert masked['email'] == 'a***@example.com'

    @pytest.mark.unit
    def test_input_not_mutated(self):
        """返回副本，不修改入参"""
        raw_hash = 'a' * 80
        record = {'password_hash': raw_hash, 'username': 'alice'}
        masked = mask_record('user', record)
        assert masked is not record
        assert record['password_hash'] == raw_hash
        assert masked['password_hash'] == REDACTED

    @pytest.mark.unit
    def test_unknown_object_type_is_noop(self):
        record = {'password_hash': 'a' * 80}
        assert mask_record('not_a_real_object', record) == record

    @pytest.mark.unit
    def test_empty_record_is_noop(self):
        assert mask_record('user', {}) == {}


# ────────────────────────────────────────
# A. 服务层：变更历史
# ────────────────────────────────────────
class TestChangeHistory:
    """change_history 携带旧/新值，命中字段同样脱敏"""

    @pytest.mark.unit
    def test_matched_field_values_masked(self):
        record = {
            'username': 'alice',
            'change_history': [
                {'field_name': 'password_hash', 'old_value': 'a' * 80, 'new_value': 'b' * 80},
                {'field_name': 'username', 'old_value': 'old', 'new_value': 'alice'},
            ],
        }
        masked = mask_record('user', record)
        history = masked['change_history']
        assert history[0]['old_value'] == REDACTED
        assert history[0]['new_value'] == REDACTED
        assert history[1]['old_value'] == 'old'
        assert history[1]['new_value'] == 'alice'
        # 入参未被修改
        assert record['change_history'][0]['old_value'] == 'a' * 80

    @pytest.mark.unit
    def test_non_dict_entry_preserved(self):
        record = {'change_history': ['raw-entry', None]}
        masked = mask_record('user', record)
        assert masked['change_history'] == ['raw-entry', None]


# ────────────────────────────────────────
# A. 服务层：列表脱敏
# ────────────────────────────────────────
class TestMaskRecords:
    @pytest.mark.unit
    def test_list_masked(self):
        records = [
            {'username': 'a', 'password_hash': 'a' * 80},
            {'username': 'b', 'password_hash': 'b' * 80},
        ]
        masked = mask_records('user', records)
        assert [r['password_hash'] for r in masked] == [REDACTED, REDACTED]
        assert [r['username'] for r in masked] == ['a', 'b']
        # 入参未被修改
        assert records[0]['password_hash'] == 'a' * 80

    @pytest.mark.unit
    def test_non_dict_items_preserved(self):
        masked = mask_records('user', [{'password_hash': 'a' * 80}, None, 'raw'])
        assert masked[1] is None
        assert masked[2] == 'raw'

    @pytest.mark.unit
    def test_empty_list_noop(self):
        assert mask_records('user', []) == []


# ────────────────────────────────────────
# B. 接口层：读面不直出哈希
# ────────────────────────────────────────
@pytest.fixture(scope='class')
def app_client():
    from meta.tests.conftest import get_shared_app
    return get_shared_app()


@pytest.fixture(scope='class')
def api_headers():
    from meta.services.auth_provider import UserInfo
    from meta.services.token_service import TokenService

    user = UserInfo(
        user_id='1', username='p2_mask_test', display_name='P2 Mask Test',
        email='p2_mask@test.com', roles=['admin'], permissions=['*'],
    )
    token, _ = TokenService.create_token(user)
    return {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'X-User-Id': '1',
        'X-User-Name': 'p2_mask_test',
    }


@pytest.fixture(scope='class')
def masked_user(app_client, api_headers):
    """经 API 创建一个带密码的用户，返回 (id, username)；结束后删除"""
    _, client = app_client
    username = 'p2_mask_' + os.urandom(4).hex()
    payload = json.dumps({
        'username': username,
        'password': 'P2Mask#2026',
        'display_name': 'P2 Mask Target',
        'email': f'{username}@test.com',
    })
    resp = client.post('/api/v2/bo/user', data=payload, headers=api_headers)
    assert resp.status_code in (200, 201), f'创建用户失败: {resp.status_code} {resp.data[:200]}'
    body = json.loads(resp.data)
    assert body.get('success'), f'创建用户失败: {body.get("message")}'
    obj_id = (body.get('data') or {}).get('id')
    assert obj_id, f'创建用户未返回 id: {body}'

    yield obj_id, username

    try:
        client.delete(f'/api/v2/bo/user/{obj_id}', headers=api_headers)
    except Exception:
        pass


class TestReadApiMasking:
    """admin 身份读用户：哈希不得出现在响应中"""

    @pytest.mark.integration
    def test_single_read_no_plain_hash(self, app_client, api_headers, masked_user):
        _, client = app_client
        obj_id, _ = masked_user
        resp = client.get(f'/api/v2/bo/user/{obj_id}', headers=api_headers)
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body.get('success'), body.get('message')
        data = body['data']

        _assert_no_plain_hash(data)
        assert data.get('password_hash', REDACTED) == REDACTED
        assert data.get('password_history', REDACTED) == REDACTED

    @pytest.mark.integration
    def test_list_read_no_plain_hash(self, app_client, api_headers, masked_user):
        """列表读（query_bo）与单条读同口径"""
        _, client = app_client
        _, username = masked_user
        resp = client.get(
            f'/api/v2/bo/user?username={username}&page=1&page_size=10',
            headers=api_headers,
        )
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body.get('success'), body.get('message')

        items = body['data']['items']
        matched = [item for item in items if item.get('username') == username]
        assert len(matched) == 1, f'列表未命中目标用户: {items}'
        row = matched[0]

        _assert_no_plain_hash(row)
        assert row.get('password_hash', REDACTED) == REDACTED
        assert row.get('password_history', REDACTED) == REDACTED
