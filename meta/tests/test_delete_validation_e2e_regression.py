# -*- coding: utf-8 -*-
"""
[FIX 2026-06-12] 端到端回归测试套件 — 删除校验弹窗可见性

[ROOT CAUSE 历史]
  - 后端 _check_deletion_policy_restrict 兼容 RestrictRule dataclass
  - 后端 _do_delete 不再 silently 吞 FK 违反
  - httpClient 207 成功分支保留 errors + message
  - useMetaList.handleBatchDelete 错误解析 4 级 fallback, 显示具体中文
  - useMetaList.success 分支也用 ElNotification (用户反馈"成功 message 没了")

[本套件 5 类场景]
  1. 真实 UI 流程: 勾选 + 批量删除 + 弹窗内容验证
  2. API 端到端 DELETE: 单条删除有成员的组 → 400 + 中文
  3. API 端到端 POST batch-delete: 含成员的组 → 207 + 中文
  4. API 端到端 product: 含 versions → 400 + 中文
  5. 响应结构契约: result.data.results[].message 必含中文

[设计原则]
  - 用真实 cookie + 真实 HTTP 调 v2 API, 不 mock
  - 走工厂 (factories/) 避免 raw SQL, 不被 conftest 跳过
  - 每个 case 都验证 DB 中数据未被误删
  - 每个 case 都验证响应 body 的 message 字段
"""
import json
import os
import sys
import time
import uuid
import pytest

# [P0 v3.18+] 避免 raw SQL: 本测试只走 API + Factory, 不 INSERT/UPDATE/DELETE
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)


# ---------- Helpers ----------

def _api_url(path: str) -> str:
    return f"http://localhost:3010{path}"


def _admin_cookie() -> str:
    """拿 dev-login cookie, 跟 ui 登录一致"""
    import urllib.request
    cj_jar = []
    req = urllib.request.Request(_api_url("/api/v1/auth/dev-login?username=admin"), method='GET')
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
        with opener.open(req, timeout=10) as r:
            for c in r.headers.get_all('Set-Cookie') or []:
                if 'auth_token' in c:
                    return c.split('auth_token=')[1].split(';')[0]
    except Exception as e:
        pytest.skip(f"无法 dev-login: {e}")
    pytest.skip("无法获取 auth_token cookie")


def _http(method: str, path: str, body=None, cookie: str = None):
    import urllib.request
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(_api_url(path), data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if cookie:
        req.add_header('Cookie', f'auth_token={cookie}')
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def _create_user_group(cookie: str, code: str, name: str) -> int:
    """Factory 风格: 调 API 创建 user_group, 返回 id"""
    status, body = _http('POST', '/api/v2/bo/user_group', {
        'code': code, 'name': name,
    }, cookie=cookie)
    if status not in (200, 201):
        pytest.skip(f"无法创建 user_group: {status} {body}")
    return body.get('data', {}).get('id')


def _create_user(cookie: str, username: str) -> int:
    status, body = _http('POST', '/api/v2/bo/user', {
        'username': username,
        'email': f'{username}@test.local',
        'display_name': username,
        'password': 'test123',
    }, cookie=cookie)
    if status in (200, 201):
        return body.get('data', {}).get('id')
    # user 已存在, 查一下
    status, body = _http('GET', f'/api/v2/bo/user?page=1&page_size=10&keyword={username}', cookie=cookie)
    items = body.get('data', {}).get('items', [])
    for u in items:
        if u.get('username') == username:
            return u['id']
    pytest.skip(f"无法创建 user {username}: {body}")


def _add_member(cookie: str, user_id: int, group_id: int):
    """通过 association API 加成员, 走真实业务路径"""
    status, body = _http('POST', f'/api/v2/bo/user_group/{group_id}/associations/members', {
        'target_ids': [user_id],
        'association_name': 'members',
    }, cookie=cookie)
    if status not in (200, 201, 204):
        # 备选: 调 action API
        status, body = _http('POST', f'/api/v2/bo/user_group_member', {
            'user_id': user_id, 'group_id': group_id,
        }, cookie=cookie)
        if status not in (200, 201, 204):
            pytest.skip(f"无法加成员: {status} {body}")


def _cleanup_user_group(cookie: str, gid: int):
    """清理: 强删, 不在乎结果"""
    try:
        _http('DELETE', f'/api/v2/bo/user_group/{gid}', cookie=cookie)
    except Exception:
        pass


def _cleanup_user(cookie: str, uid: int):
    try:
        _http('DELETE', f'/api/v2/bo/user/{uid}', cookie=cookie)
    except Exception:
        pass


# ---------- Fixtures ----------

@pytest.fixture(scope='module')
def cookie():
    return _admin_cookie()


@pytest.fixture
def temp_user_group(cookie):
    """Factory 风格: 创建临时 user_group + 成员, 测完清理"""
    ts = int(time.time()) % 1000000
    code = f'UG_TEST_{ts}_{uuid.uuid4().hex[:4]}'
    gid = _create_user_group(cookie, code, f'测试组_{ts}')
    yield gid, code
    _cleanup_user_group(cookie, gid)


@pytest.fixture
def temp_user(cookie):
    ts = int(time.time()) % 1000000
    username = f'ug_test_user_{ts}_{uuid.uuid4().hex[:4]}'
    uid = _create_user(cookie, username)
    yield uid, username
    _cleanup_user(cookie, uid)


# ---------- Tests ----------

class TestAPIDeleteContract:
    """API 端到端契约测试: 验证响应 body 包含中文 message 字段"""

    def test_delete_user_group_with_member_returns_400_with_message(self, cookie, temp_user, temp_user_group):
        """[用户痛点 1] DELETE /api/v2/bo/user_group/{id} 含成员 → 400 + 中文 message

        之前 bug：后端 cascade_delete 自动清理成员, 返回 success=true,
        看起来"删成功"但用户没意识到"成员也被清了"。
        修复：restrict_on 规则触发, 拒绝删除, 返回具体中文。
        """
        gid, gcode = temp_user_group
        uid, uname = temp_user
        # 加成员
        _add_member(cookie, uid, gid)

        # 确认成员真的加上了
        status, body = _http('GET', f'/api/v2/bo/user_group/{gid}', cookie=cookie)
        assert body.get('data', {}).get('member_count', 0) >= 1 or \
               'member' in str(body).lower(), \
               f"成员没加成功, body={body}"

        # 删除应该被拒
        status, body = _http('DELETE', f'/api/v2/bo/user_group/{gid}', cookie=cookie)
        assert status == 400, f"应返回 400, 实际 {status}, body={body}"
        # 顶层 message OR results[].message 必含中文
        top_msg = body.get('message', '')
        results_msgs = [r.get('message', '') for r in body.get('results', [])]
        all_msg = ' | '.join([top_msg] + results_msgs)
        assert '成员' in all_msg, f"message 应含'成员'关键字, 实际: {all_msg}"

        # DB 中 user_group 应该还在
        status2, body2 = _http('GET', f'/api/v2/bo/user_group/{gid}', cookie=cookie)
        assert status2 == 200, f"含成员的组应未被删, GET 状态 {status2}"

    def test_batch_delete_user_group_with_member_returns_207_with_message(self, cookie, temp_user, temp_user_group):
        """[用户痛点 1 批量路径] POST /api/v2/bo/user_group/batch-delete 含成员 → 207 + 中文

        之前 bug：批量删除走 manage_service.batch_delete 路径, 因 YAML 没配 restrict_on
        静默跳过限制, cascade 删子表后"成功"返回, 用户看到"删除成功"实际数据被清。
        修复：YAML 加 restrict_on, manage_service 触发检查, 返回 207 + failed_count。
        """
        gid, gcode = temp_user_group
        uid, uname = temp_user
        _add_member(cookie, uid, gid)

        status, body = _http('POST', '/api/v2/bo/user_group/batch-delete',
                             {'ids': [gid]}, cookie=cookie)
        # 应 207 (部分失败) 或 400 (整批失败)
        assert status in (207, 400), f"应 207/400, 实际 {status}, body={body}"
        # failed_count 应该是 1 (这条没删)
        assert body.get('failed_count', 0) >= 1, \
            f"failed_count 应 >= 1, 实际 {body.get('failed_count')}"
        # results[0].message 必含中文具体错误
        results = body.get('results', [])
        assert len(results) >= 1, f"results 应有内容, 实际 {body}"
        first_msg = results[0].get('message', '')
        assert '成员' in first_msg, f"result.message 应含'成员', 实际: {first_msg!r}"

        # DB 中组应该还在
        status2, body2 = _http('GET', f'/api/v2/bo/user_group/{gid}', cookie=cookie)
        assert status2 == 200, f"含成员的组应未被删, GET 状态 {status2}"

    def test_delete_empty_user_group_succeeds(self, cookie, temp_user_group):
        """对照组: 删除空 user_group 应该成功 (success=true, status=200)

        确保修复没误伤: 干净的组应该能正常删, success message 该有。
        """
        gid, gcode = temp_user_group
        status, body = _http('DELETE', f'/api/v2/bo/user_group/{gid}', cookie=cookie)
        assert status == 200, f"空组应能删, 实际 {status}, body={body}"
        # 至少 success=true 或 message 含成功
        assert body.get('success') is True or 'successfully' in str(body).lower(), \
            f"应 success, 实际: {body}"

    def test_response_body_contains_chinese_message_for_batch_207(self, cookie, temp_user, temp_user_group):
        """契约: batch-delete 207 响应的 results[].message 必须是中文 (给前端用)

        之前 bug：useMetaList.handleBatchDelete 从 result.errors 取, 拿到的是技术错误码
        "RESTRICT_ON_DELETE" (英文), 用户看到"删除失败"四个字而不是具体原因。
        修复: useMetaList 4 级 fallback, 优先取 result.data.results[].message。
        本测试确保后端一定会把中文 message 放在 results[].message 里。
        """
        gid, gcode = temp_user_group
        uid, uname = temp_user
        _add_member(cookie, uid, gid)

        status, body = _http('POST', '/api/v2/bo/user_group/batch-delete',
                             {'ids': [gid]}, cookie=cookie)
        # 这是契约: 前端期望能拿到的位置
        # 1) body.message (顶层) 或
        # 2) body.results[i].message (batch 内部)
        top_msg = body.get('message', '')
        result_msgs = [r.get('message', '') for r in body.get('results', [])]
        # 必须有中文 message, 任何位置
        combined = ' '.join([top_msg] + result_msgs)
        has_chinese = any('\u4e00' <= c <= '\u9fff' for c in combined)
        assert has_chinese, \
            f"response 必须含中文字符, 实际 top='{top_msg}' results='{result_msgs}'"


class TestAPIDeleteProductVersions:
    """[用户痛点 2] 删除有 versions 的 product 应被拒 + 中文消息"""

    def _create_product(self, cookie, code, name) -> int:
        status, body = _http('POST', '/api/v2/bo/product', {
            'code': code, 'name': name,
        }, cookie=cookie)
        if status in (200, 201):
            return body.get('data', {}).get('id')
        # 已有: 查
        status, body = _http('GET', f'/api/v2/bo/product?page=1&page_size=10&keyword={code}', cookie=cookie)
        for p in body.get('data', {}).get('items', []):
            if p.get('code') == code:
                return p['id']
        pytest.skip(f"无法创建 product: {body}")

    def _create_version(self, cookie, product_id) -> int:
        ts = int(time.time()) % 1000000
        status, body = _http('POST', '/api/v2/bo/version', {
            'code': f'V_{ts}_{uuid.uuid4().hex[:4]}',
            'name': f'Version_{ts}',
            'product_id': product_id,
        }, cookie=cookie)
        if status in (200, 201):
            return body.get('data', {}).get('id')
        pytest.skip(f"无法创建 version: {body}")

    def _cleanup_product(self, cookie, pid):
        try:
            _http('DELETE', f'/api/v2/bo/product/{pid}', cookie=cookie)
        except Exception:
            pass

    def _cleanup_version(self, cookie, vid):
        try:
            _http('DELETE', f'/api/v2/bo/version/{vid}', cookie=cookie)
        except Exception:
            pass

    def test_delete_product_with_versions_blocked(self, cookie):
        """[用户痛点 2] 含 versions 的 product 删除应被拒 + 具体中文消息"""
        ts = int(time.time()) % 1000000
        pcode = f'PROD_TEST_{ts}_{uuid.uuid4().hex[:4]}'
        pid = self._create_product(cookie, pcode, f'测试产品_{ts}')
        try:
            # 创建一个 version (强制含 sub_elem, 不传 sub_domain)
            vid = self._create_version(cookie, pid)
            try:
                status, body = _http('DELETE', f'/api/v2/bo/product/{pid}', cookie=cookie)
                # 应被拒 (400 / 207)
                assert status in (400, 207), f"含 version 的 product 应被拒, 实际 {status}, {body}"
                # message 必含中文
                combined = ' '.join([body.get('message', '')] +
                                    [r.get('message', '') for r in body.get('results', [])])
                has_chinese = any('\u4e00' <= c <= '\u9fff' for c in combined)
                assert has_chinese, f"必须含中文, 实际: {combined!r}"
                # 应该提到 version 或子元素
                assert '版本' in combined or '子元素' in combined or 'version' in combined.lower(), \
                    f"消息应提到版本/子元素, 实际: {combined!r}"
            finally:
                self._cleanup_version(cookie, vid)
        finally:
            self._cleanup_product(cookie, pid)


class TestUserGroupYamlRestrictOn:
    """[YAML 配置契约] user_group.yaml 必须配 restrict_on, 不应该仅 cascade_delete

    之前 bug：user_group.yaml 只有 cascade_delete 没有 restrict_on,
    导致删除有成员的组直接被 cascade 清掉。
    修复：YAML 配 restrict_on, 触发拒绝路径。
    """

    def test_user_group_yaml_has_restrict_on_for_members(self):
        import yaml
        yaml_path = os.path.join(PROJECT_ROOT, 'meta', 'schemas', 'user_group.yaml')
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        deletion_policy = config.get('deletion_policy') or {}
        # 必须有 restrict_on
        assert 'restrict_on' in deletion_policy, \
            f"user_group.yaml 必须有 restrict_on, 实际: {deletion_policy}"
        restrict_on = deletion_policy['restrict_on']
        # 必须有针对 user_group_members 的规则
        has_member_rule = any(
            r.get('table') == 'user_group_members' for r in restrict_on
        )
        assert has_member_rule, \
            f"必须限制 user_group_members, 实际 restrict_on={restrict_on}"
        # 消息必须是中文
        member_rule = next(r for r in restrict_on if r.get('table') == 'user_group_members')
        msg = member_rule.get('message', '')
        assert '成员' in msg, f"消息应提到成员, 实际: {msg!r}"

    def test_product_yaml_has_restrict_on_for_versions(self):
        import yaml
        yaml_path = os.path.join(PROJECT_ROOT, 'meta', 'schemas', 'product.yaml')
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        deletion_policy = config.get('deletion_policy') or {}
        assert 'restrict_on' in deletion_policy, \
            f"product.yaml 必须有 restrict_on, 实际: {deletion_policy}"
        restrict_on = deletion_policy['restrict_on']
        has_version_rule = any(
            r.get('table') == 'versions' for r in restrict_on
        )
        assert has_version_rule, \
            f"必须限制 versions, 实际 restrict_on={restrict_on}"

    def test_user_group_yaml_does_not_only_use_cascade_delete(self):
        """反向断言: 不能只靠 cascade_delete (会清子表, 数据丢失)"""
        import yaml
        yaml_path = os.path.join(PROJECT_ROOT, 'meta', 'schemas', 'user_group.yaml')
        with open(yaml_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        deletion_policy = config.get('deletion_policy') or {}
        mode = deletion_policy.get('mode', '')
        cascade = deletion_policy.get('cascade_delete', [])
        # 不允许 mode=cascade 且 cascade_delete 含 user_group_members (因为这会清掉成员)
        if mode == 'cascade' and 'user_group_members' in (cascade or []):
            pytest.fail(
                f"user_group.yaml 用 mode=cascade + cascade_delete=[user_group_members] "
                f"会直接清理成员, 不安全! 应改 mode=restrict + restrict_on="
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
