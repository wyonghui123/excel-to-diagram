# 🆕 v3.14: CI/CD 配置

> **日期**: 2026-06-06
> **状态**: ✅ CI workflow 已配置

---

## 📁 文件结构

```
.github/
└── workflows/
    └── test.yml              # 🆕 v3.14: CI workflow
```

---

## 🚦 触发条件

| 触发 | 分支 |
|------|------|
| `push` | `main`, `develop`, `v3.*` |
| `pull_request` | `main` |
| `workflow_dispatch` | 手动触发 |

---

## 🧪 Job 详情

### 1. `backend-tests` (主)
- **Runner**: `windows-latest`
- **超时**: 15 min
- **Python**: 3.14 (与 dev 一致)
- **依赖**: `waitress`, `gevent`, `pytest`
- **测试**: `python tests/conftest.py` (7/7 模块)
- **额外验证**: DB integrity
- **Artifacrs**: `test-results.log` + `server.log`

### 2. `smoke-tests` (快速)
- **Runner**: `windows-latest`
- **超时**: 5 min
- **测试**: `bash scripts/run_smoke.sh`
- **适用**: PR 快速反馈

---

## 📊 7/7 测试模块 (从 conftest.py)

| # | 模块 | 文件 |
|---|------|------|
| 1 | P0-1 SSE 真流式 | `tests/e2e/test_sse_streaming.py` |
| 2 | P0-2 6-10 agents 并发 | `tests/load/test_6_10_agents.py` |
| 3 | P1-3 19 Action 回归 | `tests/e2e/test_all_19_actions.py` |
| 4 | P2-4 DB 完整性 | `tests/integration/test_db_integrity.py` |
| 5 | P2-5 可观测性 | `tests/e2e/test_observability.py` |
| 6 | P3-6 SSE 长连接 | `tests/e2e/test_sse_long.py` |
| 7 | v3.10 Gevent experimental | `tests/e2e/test_gevent_experimental.py` |

---

## 🔧 本地测试

```bash
# 1. 启动 server (后台)
python waitress_server.py &

# 2. 等 10s
sleep 10

# 3. 跑 7/7 测试
python tests/conftest.py

# 4. 验证 DB integrity
python -c "import sqlite3; print(sqlite3.connect('meta/architecture.db').execute('PRAGMA integrity_check').fetchone()[0])"

# 5. 关 server
pkill -f waitress_server.py
```

或一键:

```bash
bash scripts/run_all_tests.sh
```

---

## 🛡️ 设计决策

| 决策 | 原因 |
|------|------|
| **Windows runner** | 与 dev 环境一致, gevent / Windows 兼容可发现 |
| **Python 3.14** | 与 dev 一致 (3.14 + gevent 26.5 socket 兼容) |
| **2 个 job** | 主 (15min) + 快速 (5min) |
| **Artifacrs** | 失败时下载 logs 调试 |
| **concurrency** | 同 ref 重复跑自动取消 |
| **Test DB 独立** | 避免污染生产 (TEST_DB_PATH) |

---

## 🚧 未来改进

| 项 | 描述 |
|----|------|
| **多 Python 版本** | 加 3.12 / 3.13 matrix |
| **Linux runner** | 加 ubuntu-latest (gevent 真并发) |
| **Frontend tests** | 加 vitest job |
| **Lint** | 加 ruff + eslint |
| **Coverage** | 加 pytest-cov 报告 |

---

## 关联文档

| 文档 | 关系 |
|------|------|
| [bo-action-v3.14-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.14-result.md) | 进度档 |
| [admin-unlock.md](file:///d:/filework/excel-to-diagram/docs/admin-unlock.md) | B 选项 (admin unlock) |
