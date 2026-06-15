# tests/diagnostics/ —— 1-Shot 诊断脚本框架 (v1.0)

> **Date**: 2026-06-15 | **Status**: 框架占位 | **Owner**: AI Infra

---

## 用途

给 AI agent 提供 `合法的 1-shot 诊断脚本` 落地处，**替代**散落在 `test_helpers/scripts/` / `d:\filework\` / `tests/e2e/` 的零散脚本。

---

## 与其他测试目录的关系

| 目录 | 用途 | 受 conftest 保护？ | 生命周期 |
|------|------|------------------|---------|
| `tests/unit/` | 单元测试 | 是 | 长期 |
| `tests/integration/` | 集成测试 | 是 | 长期 |
| `tests/e2e/` | 端到端 | 是 | 长期 |
| **`tests/diagnostics/`** | **1-shot 诊断脚本** | **是 (本框架)** | **30 天归档** |
| `test_helpers/scripts/` | 散落旧脚本 (历史) | 否 | 永久 (不删, 不动) |

---

## 命名规范

| 前缀 | 含义 | 例子 |
|------|------|------|
| `diag_<topic>_<date>.py` | 1-shot 诊断 (30 天归档) | `diag_write_scope_20260615.py` |
| `verify_<sha>.py` | 验证某次 commit | `verify_7d0b78d.py` |
| `regression_<topic>.py` | 长期回归守卫 | `regression_write_scope_owner_chain.py` |

---

## 模板 (template)

```python
# -*- coding: utf-8 -*-
"""
[DIAGNOSTIC] <简述>
[CREATED] YYYY-MM-DD
[AUTHOR] AI Agent / 人类
[TOPIC] write_scope / data_perm / ...

[USAGE]
    # dev-login first
    python -c "import requests; requests.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')"
    # then run this
    pytest tests/diagnostics/diag_<topic>_<date>.py -v -s
"""
import pytest
import requests

BASE_URL = 'http://localhost:3010'


@pytest.fixture(scope='module')
def admin_session():
    s = requests.Session()
    s.get(f'{BASE_URL}/api/v1/auth/dev-login?username=admin')
    yield s
    s.close()


def test_diag_topic(admin_session):
    # ... 1-shot 逻辑 ...
    result = admin_session.get(f'{BASE_URL}/api/v1/...').json()
    assert result['success'] is True
```

---

## 与 conftest 的关系 (重要)

**本目录目前没自动被 conftest.py 接管**。**后续 agent 实施时**（Phase 2）需要：
1. 在 `tests/diagnostics/conftest.py` 加一个特殊 fixture（如 `auto_clean_db_state`）确保 1-shot 不污染长期数据
2. 在 `d:\filework\test.py` 加 `--diagnostics` 参数支持跑这个目录

**本占位阶段不做以上两步**（避免与排查 agent 冲突）。

---

## 当前状态

- ✅ `__init__.py` 占位
- ✅ `README.md` 规范
- ❌ 无 `conftest.py`（待 Phase 2）
- ❌ 无自动归档脚本（待 Phase 2）
- ❌ 无 pytest marker 注册（待 Phase 2）

---

## 不做的（避免干扰排查 agent）

- ❌ 不在 `d:\filework\test.py` 加参数
- ❌ 不在 `meta/tests/conftest.py` 加规则
- ❌ 不删任何 `test_helpers/scripts/` 现有脚本
- ❌ 不动 `tests/e2e/` 任何文件

---

## 后续步骤

详见 [spec-diagnostic-infrastructure-v1.0.md](../../specs/spec-diagnostic-infrastructure-v1.0.md) 的 Phase 2-4。
