# test_helpers/diag_fixtures.py —— 诊断 fixture 设计文档

> **Date**: 2026-06-15 | **Status**: 设计文档 (Phase 2 实施)
> **Owner**: AI Infra
> **Source**: [spec-diagnostic-infrastructure-v1.0.md](../docs/specs/spec-diagnostic-infrastructure-v1.0.md) § 2.2

---

## 目的

给 AI agent 提供"查询式诊断"的 pytest fixtures，**让 agent 不再写 1-shot `verify_X.py` 脚本**。

---

## 设计原则

1. **复用现有 dev-login 机制**（不重新造认证）
2. **依赖 Phase 1 端点**（`why-blocked`, `admin/record`）—— 没那些端点时 fixture 给出"待实施"提示
3. **不直连 sqlite3**（安全 + 一致性）
4. **集成到 conftest 体系**（受 `TEST_ENTRY=1` 保护）
5. **fail-gracefully** —— 端点不存在时 `pytest.skip` 而不是 fail

---

## API 设计 (DRAFT)

### Fixture 1: `why_blocked`

```python
@pytest.fixture
def why_blocked(base_url: str = 'http://localhost:3010'):
    """Dry-run permission check.
    
    依赖: meta/api/permissions_api.py (Phase 2 实施)
    端点: GET /api/v1/permissions/why-blocked/<type>/<id>?as_user=<id>
    """
    with requests.Session() as session:
        # dev-login as admin (假设 admin 有 'why-blocked' 权限)
        session.get(f'{base_url}/api/v1/auth/dev-login?username=admin')
        
        def _check(object_type: str, target_id: int, as_user: Optional[int] = None) -> dict:
            params = {'as_user': as_user} if as_user else {}
            try:
                resp = session.get(
                    f'{base_url}/api/v1/permissions/why-blocked/{object_type}/{target_id}',
                    params=params
                )
            except requests.ConnectionError:
                pytest.skip(f'{base_url} not reachable')
            if resp.status_code == 404:
                pytest.skip('why-blocked endpoint not implemented (Phase 2)')
            resp.raise_for_status()
            return resp.json()
        return _check
```

### Fixture 2: `record_view`

```python
@pytest.fixture
def record_view(base_url: str = 'http://localhost:3010'):
    """Admin readonly record view - 替代 sqlite3 直连.
    
    依赖: meta/api/admin_api.py (Phase 2 实施, 新建)
    端点: GET /api/v1/admin/record/<type>/<id>
    """
    with requests.Session() as session:
        session.get(f'{base_url}/api/v1/auth/dev-login?username=admin')
        
        def _view(object_type: str, target_id: int) -> dict:
            try:
                resp = session.get(
                    f'{base_url}/api/v1/admin/record/{object_type}/{target_id}'
                )
            except requests.ConnectionError:
                pytest.skip(f'{base_url} not reachable')
            if resp.status_code == 404:
                pytest.skip('admin/record endpoint not implemented (Phase 2)')
            resp.raise_for_status()
            return resp.json()
        return _view
```

### Fixture 3: `as_user`

```python
@pytest.fixture
def as_user(base_url: str = 'http://localhost:3010'):
    """以指定用户身份 dev-login (admin 限定).
    
    注意: 这个 fixture 仅用于测试 '另一个用户视角', 不应用于越权操作
    """
    with requests.Session() as admin_session:
        admin_session.get(f'{base_url}/api/v1/auth/dev-login?username=admin')
        
        def _login(username: str) -> 'requests.Session':
            user_session = requests.Session()
            user_session.get(f'{base_url}/api/v1/auth/dev-login?username={username}')
            return user_session
        return _login
```

---

## 使用示例

```python
# meta/tests/test_write_scope_debug.py (示例)
def test_476_owner_chain(why_blocked, record_view):
    # 1. 看 record 实际 owner
    record = record_view('product', 476)
    assert record['owner_id'] == 3385, f"DB owner_id is {record['owner_id']}, not 3385"
    
    # 2. 模拟 3385 用户视角下的写权限
    result = why_blocked('product', 476, as_user=3385)
    assert result['checks']['owner_chain']['matched'] is True, \
        f"owner_chain should match: {result['checks']}"
    assert result['decision'] == 'ALLOW', \
        f"Should allow owner-chain match: {result}"
```

---

## 实施依赖

| 依赖 | 状态 | 来源 |
|------|------|------|
| `meta/api/permissions_api.py` (why-blocked 端点) | **未实施** | spec § 2.1 |
| `meta/api/admin_api.py` (admin/record 端点) | **未实施** | 本文档 |
| `test_helpers/diag_fixtures.py` 真实代码 | **未实施** | 本文档 |
| `meta/tests/conftest.py` 集成 | **未实施** | 本文档 |

**当前阶段**: 本文档**不下场实施**（按用户要求"不影响正在排查的 agent"）。

---

## 不实施的影响

- ✅ 后续 agent 排查 write_scope 时, **可以参考本设计**直接实施
- ✅ 本文档**不影响运行时**
- ❌ Phase 1 端点未实施前, 任何使用本 fixture 的测试都会 `pytest.skip`

---

## 实施检查清单 (Phase 2)

- [ ] `meta/api/permissions_api.py` 实现 `why-blocked` 端点
- [ ] `meta/api/admin_api.py` 实现 `admin/record` 端点
- [ ] `test_helpers/diag_fixtures.py` 创建真实代码（用本设计）
- [ ] `meta/tests/conftest.py` 注册新 fixture（如有必要）
- [ ] 1 个示例测试 `test_diag_fixtures_e2e.py` 验证 fixture 链路
- [ ] 更新本 README 状态为 "Implemented"

---

## CHANGELOG

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-15 | Batch2 Agent | 初版设计文档 |
