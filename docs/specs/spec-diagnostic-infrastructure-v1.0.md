# Spec: AI Agent 诊断基础设施 (Diagnostic Infrastructure) v1.0

> **Date**: 2026-06-15 | **Status**: Draft for Review
> **Owner**: AI Infra (Batch2 Agent)
> **Inspired by**: 2026-06-15 排查 write_scope (H13) agent 反馈

---

## 0. TL;DR

AI agent 在排查"为什么 403 / 看不到 X" 类问题时，**反复退化到改源码 + 加 print debug + 重启 + 看 log** 的 90 年代模式。**根因不是 agent 笨**，是**项目缺少"查询型诊断"基础设施**。

本文档提出 5 个增量改进（**不动 meta/ / src/ / 现有 conftest / 现有 test.py**），把"改源码 debug" 转化为"GET 端点查问题"。

---

## 1. 问题陈述 (Problem Statement)

### 1.1 现状证据

| 数据 | 值 | 含义 |
|------|-----|------|
| `test_helpers/scripts/*.py` 数量 | **202** | 大量 1-shot "看实际值" 脚本 |
| `d:\filework\*.py` 散落脚本 | **292** | 类似 verify_X.py 散在仓库外 |
| `meta/api/diagnostics_api.py` | 已存在但 `write_scope_warnings` 字段空 | stub |
| 拦截器 `on_error` 序列化 `check_results` | 已实现 ([permission_interceptor.py:221-230](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L221-L230)) | 已有结构化数据但 agent 没用 |
| `_load_record_cached` 死代码 | [write_scope_interceptor.py:489-496](file:///d:/filework/excel-to-diagram/meta/core/interceptors/write_scope_interceptor.py#L489-L496) | `@lru_cache` + `return None` 注释自承"不能用" |

### 1.2 Agent 当前 debug 模式（反模式）

```
Agent 看到 403
  ↓
不知道 4 个 step (admin / owner / dim / visibility) 哪个不命中
  ↓
加 print debug 到 _check_target (write_scope_interceptor.py)
  ↓
改 7 行
  ↓
重启 server
  ↓
跑 e2e
  ↓
看 server log
  ↓
猜下一次改什么
```

**问题**：每次 debug 周期 10-30 分钟，**改源码 / 重启 / 看 log** 是必须的 3 步。

### 1.3 期望 debug 模式

```
Agent 看到 403
  ↓
GET /api/v1/permissions/why-blocked/product/476?as_user=3385
  ↓
拿到结构化 JSON: { owner: false, chain_root: ..., dim_scope: [...], visibility: 'private' }
  ↓
直接定位 "owner 没命中，因为 direct_owner=3385 == user_id=3385 应当命中但 _check_owner_chain 内部 if 顺序错了"
  ↓
**不动源码，不重启**
```

**节省**：每次 debug 周期降到 1-3 分钟。

---

## 2. 5 大优化 (Optimizations)

### 2.1 [P0] `why-blocked` 端点

**位置**：`meta/api/permissions_api.py` (新文件)
**路径**：`GET /api/v1/permissions/why-blocked/{object_type}/{target_id}?as_user=<id>`
**权限**：admin 限定（防止信息泄露）

**Response 格式**：
```json
{
  "success": true,
  "object_type": "product",
  "target_id": 476,
  "as_user": 3385,
  "decision": "DENY",
  "checks": {
    "admin": {
      "matched": false,
      "reason": "user_id=3385 is not admin and has no '*' permission"
    },
    "owner_chain": {
      "matched": true,                            // ← 用户期望这里命中
      "direct_owner": 3385,
      "user_id": 3385,
      "chain_root": null
    },
    "dim_scope": {
      "matched": false,
      "roles_checked": [5970, 5434],
      "matched_role": null,
      "reason": "role 5970 scope [475] does not include 476; role 5434 has empty scope"
    },
    "visibility": {
      "value": "private",
      "allow_public": false
    }
  },
  "would_allow": {
    "crud_update": true,                          // ← owner chain 命中应该放行
    "crud_delete": true,
    "associate": true
  },
  "trace_id": "req-2026-06-15-...",
  "duration_ms": 12
}
```

**实现要点**（不下场实现，只设计）：

```python
# meta/api/permissions_api.py (DRAFT - 不下文件)
from flask import Blueprint, request, jsonify, g
from meta.core.interceptors.write_scope_interceptor import WriteScopeInterceptor

bp = Blueprint('permissions_api', __name__, url_prefix='/api/v1/permissions')

@bp.route('/why-blocked/<object_type>/<int:target_id>')
@admin_required
def why_blocked(object_type, target_id):
    """Dry-run permission check - 不改任何数据"""
    as_user = request.args.get('as_user', type=int)
    if as_user is None:
        as_user = g.current_user.get('user_id')
    
    # 模拟拦截器判定 (复用 _check_target 逻辑)
    interceptor = WriteScopeInterceptor()
    record = interceptor._load_record(None, object_type, target_id)
    
    checks = {
        'admin': _check_admin(as_user),
        'owner_chain': interceptor._check_owner_chain(None, object_type, record, as_user),
        'dim_scope': interceptor._check_dim_scope(None, object_type, record, as_user),
        'visibility': interceptor._check_visibility(None, object_type, record),
    }
    
    return jsonify({
        'success': True,
        'object_type': object_type,
        'target_id': target_id,
        'as_user': as_user,
        'decision': 'ALLOW' if (
            checks['admin']['matched'] or
            checks['owner_chain']['matched'] or
            (checks['dim_scope']['matched'] and checks['visibility']['allow_public'])
        ) else 'DENY',
        'checks': checks,
        'would_allow': {
            'crud_update': ...,
            ...
        },
    })
```

**风险**：
- ⚠️ 复用 `_check_owner_chain` 等私有方法（需改为 public 或新增 `_check_owner_chain_public`）
- ⚠️ admin 限定是必须的（不能泄露其他用户的 scope 信息）
- ⚠️ `as_user` 参数需要审计日志（防止"我以 admin 身份模拟其他用户"的越权）

---

### 2.2 [P0] `diag_fixtures.py` —— 给 agent 复用的诊断 fixture

**位置**：`test_helpers/diag_fixtures.py` (新文件)
**目的**：让 agent 写测试时直接 `import` 现成 fixture，**不再写 1-shot 脚本**

```python
# test_helpers/diag_fixtures.py (DRAFT)
import pytest
import requests
from test_helpers.browser_auth_cli import PlaywrightCLI

@pytest.fixture
def why_blocked(base_url: str = 'http://localhost:3010'):
    """Dry-run permission check - 复用 2.1 端点"""
    with requests.Session() as session:
        # dev-login as admin
        session.get(f'{base_url}/api/v1/auth/dev-login?username=admin')
        
        def _why_blocked(object_type: str, target_id: int, as_user: int = None):
            params = {'as_user': as_user} if as_user else {}
            resp = session.get(
                f'{base_url}/api/v1/permissions/why-blocked/{object_type}/{target_id}',
                params=params
            )
            resp.raise_for_status()
            return resp.json()
        return _why_blocked

@pytest.fixture
def record_view(base_url: str = 'http://localhost:3010'):
    """Admin readonly record view - 替代 sqlite3 直连"""
    with requests.Session() as session:
        session.get(f'{base_url}/api/v1/auth/dev-login?username=admin')
        
        def _record_view(object_type: str, target_id: int):
            resp = session.get(
                f'{base_url}/api/v1/admin/record/{object_type}/{target_id}'
            )
            resp.raise_for_status()
            return resp.json()
        return _record_view

@pytest.fixture
def as_user(base_url: str = 'http://localhost:3010'):
    """以指定用户身份 dev-login (admin only)"""
    with requests.Session() as session:
        session.get(f'{base_url}/api/v1/auth/dev-login?username=admin')
        
        def _as_user(username: str):
            session2 = requests.Session()
            session2.get(f'{base_url}/api/v1/auth/dev-login?username={username}')
            return session2
        return _as_user
```

**使用示例**：
```python
# meta/tests/test_write_scope_debug.py (DRAFT)
def test_476_ownership(why_blocked, record_view):
    record = record_view('product', 476)
    assert record['owner_id'] == 3385
    
    result = why_blocked('product', 476, as_user=3385)
    assert result['checks']['owner_chain']['matched'] is True
    assert result['decision'] == 'ALLOW'  # owner chain 应该命中
```

**优势**：
- ✅ 复用现有 dev-login 机制
- ✅ 不直连 sqlite3（安全）
- ✅ 集成到 conftest 体系（受保护）
- ✅ agent 不再写 `verify_X.py` 1-shot 脚本

---

### 2.3 [P0] `test_lint.py` —— 反模式静态检查

**位置**：`tools/test_lint.py` (新文件，独立工具)
**目的**：agent 提交前自动检测反模式

**检查项**：

| # | 反模式 | 检测方法 | 严重度 |
|---|--------|---------|--------|
| 1 | `time.sleep(N)` 在测试中 | AST 扫描 `time.sleep` / `asyncio.sleep` | HIGH |
| 2 | `wait_for_timeout(N)` | AST 扫描 `wait_for_timeout` | HIGH |
| 3 | 硬编码产品名（如 `测试产品_XXX`） | regex 匹配 `[\u4e00-\u9fa5]+_[A-Z0-9]{6,}` | MEDIUM |
| 4 | 直连 `sqlite3.connect(...)` | AST 扫描 `sqlite3.connect` | HIGH |
| 5 | `pytest ... ` 直跑命令（绕过 test.py） | shell history grep | HIGH |
| 6 | 重复文件名前缀（`test_filter*.py` ≥ 3 个） | 目录扫描 | LOW |
| 7 | `print(...)` 在测试中 | AST 扫描 `print(` | MEDIUM |
| 8 | 没 `try/except` 的 `requests.get(...)` | AST 扫描 | LOW |

**使用方式**：
```bash
# CI / pre-commit
python tools/test_lint.py --target meta/tests/

# 输出
[HIGH] meta/tests/test_foo.py:42: time.sleep(3) -> 用 wait_for_selector
[HIGH] meta/tests/test_foo.py:78: sqlite3.connect('meta/architecture.db') -> 用 record_view fixture
[MEDIUM] meta/tests/test_foo.py:120: print('debug') -> 用 logger.debug
[OK] No critical issues found in 47 files
```

**实现要点**：
- 用 Python `ast` 模块扫描（不依赖外部 lint 工具）
- 输出 `exit code 1` 如果有 HIGH 级别问题（让 pre-commit hook 能拦下）

---

### 2.4 [P1] 诊断脚本分类法 + 命名规范

**目标**：把 202 个散落脚本**分类归档**

| 类别 | 命名规范 | 应放位置 | 生命周期 |
|------|---------|---------|---------|
| **一次性 1-shot** | `verify_<sha>.py` 或 `diag_<topic>_<date>.py` | `tools/diagnostics/archived/` | 30 天未引用 → .archived |
| **复用探测工具** | `probe_<feature>.py` | `test_helpers/probes/` | 长期保留 |
| **回归守卫** | `test_regression_<sha>.py` | `meta/tests/regression/` (受 conftest 保护) | 长期保留 |
| **健康检查** | `health_<aspect>.py` | `tools/healthcheck/` | 长期保留 |
| **业务修复** | `factory_<entity>.py` | `meta/tests/factories/` | 长期保留 |

**新增文件**：
- `docs/specs/spec-diagnostic-classification-v1.0.md`（本文档已涵盖主要部分）
- `tools/diagnostics/README.md`（落地规范）
- `tools/diagnostics/archived/.gitkeep`（占位）

**不做的**（避免干扰排查 agent）：
- ❌ **不**重命名/移动现有 202 个脚本
- ❌ **不**删除任何脚本
- ✅ 未来新写的 1-shot 脚本**用新命名规范**

---

### 2.5 [P1] 规则源收敛 —— 单一权威源

**问题**：4 个规则文件都讲"禁止直接 pytest"

**方案**：

**步骤 1**：新建 `docs/rules/TESTING_INDEX.md` 作为权威索引
```markdown
# 测试规则权威索引

## 铁律：禁止直接 pytest
- **权威源**: `.trae/rules/test_rules.md` 第 6-15 行
- **重复出现**: SESSION_REMINDER.md#1, agent-bootstrap.md, test-case-standards.md
- **优先级**: 冲突时以本索引为准

## 铁律：禁止 wait_for_timeout
- **权威源**: `.trae/rules/test-case-standards.md` 第 X 节
- **重复出现**: SESSION_REMINDER.md#10, test-script-quality-analysis.md
- ...
```

**步骤 2**：在其他 3 个文件顶部加一行：
```markdown
> [NOTE] 本文档的"禁止 pytest"规则已在 [test_rules.md](./test_rules.md) 详细描述。
> 冲突时请以 test_rules.md 为准。
```

**风险**：
- ⚠️ 修改 `.trae/rules/` 任何文件会**强制重载规则**，可能影响正在排查的 agent
- ✅ 缓解：只在文件顶部加 1 行 note，**不改规则内容**

---

## 3. 实施计划 (Implementation Plan)

### 3.1 不下场的部分（需要后续 agent 实施）

| # | 任务 | 原因 |
|---|------|------|
| 1 | `meta/api/permissions_api.py` 实现 | 涉及 `meta/`，排查 agent 在用 |
| 2 | 复用拦截器私有方法 | 涉及 `meta/core/`，排查 agent 在用 |
| 3 | 重命名/归档 202 个现有脚本 | 排查 agent 可能在用其中某些 |

### 3.2 我现在能做的（已做）

| # | 任务 | 文件 | 状态 |
|---|------|------|------|
| A | 写完整 spec | `docs/specs/spec-diagnostic-infrastructure-v1.0.md` | 进行中 |
| B | `tests/diagnostics/` 空框架 | `meta/tests/diagnostics/README.md` + `__init__.py` | 待做 |
| C | `test_lint.py` 工具 | `tools/test_lint.py` | 待做 |
| D | `diag_fixtures.py` 文档版（不下场实现） | `test_helpers/diag_fixtures_README.md` | 待做 |
| E | `TESTING_INDEX.md` | `docs/rules/TESTING_INDEX.md` | 待做 |

### 3.3 时间表

| 阶段 | 内容 | 期望时间 |
|------|------|---------|
| Phase 1 (本 spec) | 5 个文档/工具落盘 | 1-2h |
| Phase 2 (后续 agent) | why-blocked 端点 + 真实 diag_fixtures | 2-3h |
| Phase 3 (后续 agent) | 202 个脚本归档 | 半天 |
| Phase 4 (后续 agent) | `meta/tests/factories/` 工厂目录 | 3-4h |

---

## 4. 风险与缓解 (Risks)

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| 排查 agent 正在用某个 `verify_X.py` | 中 | 中 | **不重命名/移动任何现有脚本** |
| `_check_owner_chain` 改 public 后被滥用 | 低 | 高 | 仍以 `_` 前缀（"软私有"），`why-blocked` 端点有 admin 限定 |
| 规则源修改触发 agent 上下文重载 | 中 | 中 | 只加 1 行 note，不改内容 |
| test_lint.py false positive 拦截合法用例 | 中 | 中 | 启动时是 WARN 级，不阻断；3 个月后升级为 FAIL |
| diag_fixtures 与现有 conftest fixture 冲突 | 低 | 低 | 用独立前缀 `why_blocked_` / `record_view_` |

---

## 5. 度量 (Success Metrics)

| 指标 | 当前 | 目标 |
|------|------|------|
| Agent 反馈"我加 print debug"的次数 | 频繁 | 90% 减少 |
| 1-shot 脚本散落增量 | 202 | 月增 ≤ 5 |
| 排查 403 类问题平均时间 | 10-30 min | 1-3 min |
| `test_helpers/scripts/` 脚本数量 | 202 | 250（小幅增长可以接受）|
| test_lint 拦下的反模式数量 | 0 | ≥ 5/月 |

---

## 6. 后续步骤 (Next Steps)

1. **本 spec 提交到 git**（docs/specs/）
2. **本 spec 通知**排查 H13 的 agent（如果有 hook）
3. **本 spec 提交 PR 讨论**
4. **后续 agent 接手** Phase 2-4

---

## CHANGELOG

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-15 | Batch2 Agent | 初版 |
