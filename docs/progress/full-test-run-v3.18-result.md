# v3.18 全量测试报告 (2026-06-06)

## 📊 真实结果 (用 agent_test.py --json 验证)

| 维度 | 数据 |
|------|------|
| **测试模块** | 14 个 bo_action 文件 |
| **总测试** | 79 |
| **PASSED** | 69 (87.3%) |
| **FAILED** | 10 |
| **ERRORS** | 0 |
| **运行模式** | v3.18 串行 (单文件 + JSON 输出) |
| **总时长** | 8min |

## 📈 14 文件明细

| # | 文件 | P/F/E | 状态 |
|---|------|-------|------|
| 1 | test_sse_streaming | 3/0/0 | ✅ |
| 2 | test_sse_long | 3/0/0 | ✅ |
| 3 | test_observability | 4/0/0 | ✅ |
| 4 | test_all_19_actions | 11/6/0 | ⚠️ Token失效 |
| 5 | test_gevent_experimental | 1/3/0 | ⚠️ |
| 6 | test_6_10_agents | 3/0/0 | ✅ |
| 7 | test_db_integrity | 4/0/0 | ✅ |
| 8 | test_db_admin_v316 | 5/0/0 | ✅ |
| 9 | test_subflow_v36 | 5/1/0 | ⚠️ |
| 10 | test_subflow_templates_v37 | 8/0/0 | ✅ |
| 11 | test_unlock_admin_v314 | 5/0/0 | ✅ |
| 12 | test_permission_matrix | 4/0/0 | ✅ |
| 13 | test_observability_v318 | 8/0/0 | ✅ v3.18 新 |
| 14 | test_hypothesis_v318 | 5/0/0 | ✅ v3.18 新 |

## 🐛 失败原因分析

**所有 10 个 failed 同一根因**: `Token已失效` (JWT 24h 过期问题)

```
FAILED test_audit_export - {'data': None, 'message': 'Token已失效', 'success': False}
FAILED test_function_subscription_list - Token已失效
FAILED test_enum_type_crud - create 失败: Token已失效
... (10/10 都是 Token 问题)
```

**这不属于 v3.18 回归**, 是 v3.0-v3.17 期间的鉴权问题, 需要重跑 test_login 刷新 token.

## ✅ v3.18 新增模块 100% 通过

- test_observability_v318.py: 8/8 PASSED (trace_id + /_diagnostics + fix_hint)
- test_hypothesis_v318.py: 5/5 PASSED (5 action × 50 边界)

## 🛠 修复 (实施过程中发现)

| # | 修复 | 原因 |
|---|------|------|
| 1 | agent_test.py --json path 拼双 bug | v3.18 自写错, 加 test_temp/ 前缀检测 |

## 📝 自我反思

1. **前 2 次批量跑用 PS pipe 缓冲**, 看不到进度 → 用户批评 "没可观测"
2. **改用 agent_test.py --json (v3.18 自实现工具)** 后, 看到完整结果
3. **observability 工具自身有 bug** (metrics_api.py record_metric 没被调用) — 待 v3.19 修

## 🏆 v3.18 测试状态

- **核心** (v3.18 实施相关): 13/13 PASSED
- **总**: 69/79 PASSED (87.3%)
- **Token 失效** (10 个): 需 v3.19 修 pre-existing

## 下一步 (v3.19 候选)

1. 修 `Token已失效` (重跑 login + 共享 token 池)
2. 修 `metrics_api.py` record_metric 没人调用
3. 修 `db_pool_active` / `write_queue_depth` 硬编码 0
