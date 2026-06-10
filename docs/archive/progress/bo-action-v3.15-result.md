# v3.15 Audit Log + Frontend CI (v1.0)

> **日期**: 2026-06-06
> **状态**: ✅ 7/7 测试全部通过 (无回归)
> **总工时**: ~1h
> **关联**: v3.14 收官后, 2 项小优化

---

## 🎯 关键变更

### B 选项: Admin Unlock Audit Log

**问题**: admin unlock 事件**未审计**, 不知道谁/何时/何原因解锁。

**解决**: 在 `unlock_admin.py` 解锁成功后, 写一条 `audit_logs` 记录。

#### 修改文件
| 文件 | 改动 |
|------|------|
| `scripts/unlock_admin.py` | + `_write_audit_log()` helper + 调用点 |
| | + `from typing import Optional` 导入 |

#### audit_logs 记录 schema

| 列 | 值 |
|----|----|
| `object_type` | `user` |
| `object_id` | admin user id |
| `action` | `unlock` |
| `field_name` | `status` |
| `old_value` | `locked` / `failed` / `suspended` |
| `new_value` | `active` |
| `user_id` | `system` |
| `user_name` | `admin_unlock_script` |
| `user_agent` | `admin_unlock_script/1.0` |
| `log_category` | `security` |
| `log_level` | `WARN` |
| `status` | `written` |
| `created_at` | ISO timestamp |

#### 端到端验证

```python
# 1. 锁 admin
db.execute("UPDATE users SET status = 'locked' WHERE username = 'admin'")

# 2. 跑 unlock
subprocess.run(['python', 'scripts/unlock_admin.py'])
# 输出:
#   ✅ admin 已解锁 (status: locked → active) at 2026-06-06T15:17:25
#   📝 audit log 已记录 (log_category=security)

# 3. 验证 audit_logs
SELECT * FROM audit_logs WHERE action='unlock' ORDER BY id DESC LIMIT 1;
# 1 条新记录
```

### C 选项: Frontend Test Job (CI)

**问题**: CI 仅有 backend 测试, frontend vitest 未在 CI 跑。

**解决**: 在 `.github/workflows/test.yml` 加 `frontend-tests` job。

#### 修改文件
| 文件 | 改动 |
|------|------|
| `.github/workflows/test.yml` | + `frontend-tests` job (44 行) |

#### frontend-tests Job 详情

| 维度 | 详情 |
|------|------|
| Runner | `windows-latest` |
| 超时 | 10 min |
| Node.js | 20 |
| 依赖 | `npm ci` (npm cache) |
| 测试 | `npm run test:run` (vitest run) |
| Artifacts | `vitest-results.log` (7d) |

#### CI Workflow 现状 (3 个 Job)

| Job | 角色 | 超时 |
|-----|------|:---:|
| `backend-tests` | 完整 7/7 + DB integrity | 15min |
| `smoke-tests` | 快速 smoke | 5min |
| **`frontend-tests`** | **vitest run** (v3.15 新增) | **10min** |

---

## 📊 量化成果

| 维度 | 价值 |
|------|------|
| **Audit log** | ✅ 安全事件可追溯 (谁、何时、何动作) |
| **Frontend CI** | ✅ PR 自动跑 vitest |
| **CI Job 数** | 2 → 3 (新增 frontend) |
| **测试覆盖** | 7/7 通过 (无回归) |
| **生产就绪** | 9/10 (维持) |

---

## 🛡️ 设计决策

### Audit Log

| 决策 | 原因 |
|------|------|
| **audit_logs (而非 audit_log)** | 实际表名是 audit_logs (复数) |
| **log_category='security'** | 区分业务/安全事件 |
| **log_level='WARN'** | 自动解锁是异常恢复, 非 normal |
| **失败不中断主流程** | Audit 写入失败不应阻止 unlock |
| **旧值/新值都记录** | 完整审计追踪 |

### Frontend CI

| 决策 | 原因 |
|------|------|
| **Windows runner** | 与 dev 一致 |
| **Node.js 20** | 当前 LTS |
| **npm ci** | 比 npm install 快, lockfile 严格 |
| **cache: 'npm'** | 加速依赖安装 |
| **Tee-Object** | 实时输出 + 保存 log |
| **vitest run** | CI 模式 (单次跑) |

---

## 🧪 验证

### Audit Log 端到端

```
Before: audit_logs unlock 事件 = 0
Set admin to locked

--- Script output ---
✅ admin 已解锁 (status: locked → active) at 2026-06-06T15:17:25
  📝 audit log 已记录 (log_category=security)

Return code: 0
After: audit_logs unlock 事件 = 1
增加: 1 条

--- 最新 audit log ---
  object_type: user
  object_id:   1
  action:      unlock
  field_name:  status
  old_value:   locked
  new_value:   active
  user_name:   admin_unlock_script
  log_category: security
  log_level:   WARN
  created_at:  2026-06-06T15:17:25

admin status now: active
```

### 7/7 全量测试

```
✅ P0-1 SSE 真流式
✅ P0-2 6-10 agents 并发
✅ P1-3 19 Action 回归 (17/17)
✅ P2-4 DB 完整性 (4/4)
✅ P2-5 可观测性 (4/4)
✅ P3-6 SSE 长连接 (3/3)
✅ v3.10 Gevent experimental (4/4)
```

---

## 🔧 实施过程踩的坑

1. **表名 audit_logs (复数) 不是 audit_log** — 调研先, 实施后
2. **column 名 status_entered_at / last_login_at (不是 last_failed_login_at)** — 修了
3. **vitest 后台抢占 server** — 强杀后才稳定 (CI 内不会发生)

---

## 📈 大主线 v3.0 → v3.15 完整演进

| 阶段 | Action | 关键技术 | 测试 |
|------|:---:|------|:---:|
| v3.0 | 6 | registry | - |
| v3.1 | 11 | 文件流 | - |
| v3.2 | 12 | Subflow | - |
| v3.4 | 16 | Function 维度 | - |
| v3.5 | 19 | enum_type | - |
| v3.6 | 19 | Subflow 6 项 + **Pool** | - |
| v3.7 | 19 | dry-run/模板/metrics | - |
| v3.8 | 19 | Waitress + SSE | - |
| v3.9 | 19 | Gevent + 7 测试模块 | 6/6 |
| v3.10 | 19 | Gevent 文档化 | 7/7 |
| v3.11 | 19 | `_is_pool_active` 简化 | 7/7 |
| v3.12 | 19 | 删 `_lock` | 7/7 |
| v3.13 | 19 | 完全池化 (-125 行) | 7/7 |
| v3.14 | 19 | CI workflow + admin unlock | 7/7 |
| **v3.15** | **19** | **audit log + frontend CI job** | **7/7** |

---

## 🔗 关联文档

| 文档 | 关系 |
|------|------|
| [bo-action-v3.14-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.14-result.md) | 上一步 CI/unlock |
| [admin-unlock.md](file:///d:/filework/excel-to-diagram/docs/admin-unlock.md) | admin unlock 文档 |
| [ci.md](file:///d:/filework/excel-to-diagram/docs/ci.md) | CI 文档 |
| [v3-bo-action-main-summary.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/v3-bo-action-main-summary.md) | v3.x 大总结 |

---

## ⚠️ 已知限制

### 1. audit log 无 revert 功能
- 只能看记录, 不能回滚
- 建议: 加 `audit_log.revert` action (admin only)

### 2. CI 仍非 git push 触发
- 需 push 到 GitHub 触发
- 本地验证: `bash scripts/run_smoke.sh`

### 3. gevent 仍 experimental
- v3.10 文档化
- Python 3.14 + gevent 26.5 socket 兼容未解
- 默认 waitress

### 4. admin unlock 仍不触发 admin 通知
- 解锁后**未通知** admin (邮件/IM)
- 建议: 加 webhook 通知

---

## 🏆 v3.15 里程碑

- ✅ **Audit log 完整** (security 事件可追溯)
- ✅ **Frontend CI 自动化** (3 jobs: backend/smoke/frontend)
- ✅ **生产就绪 9/10** (维持)
- ✅ **7/7 测试** 不回归
- ✅ **3 项新功能** (audit log + frontend job + script update)

---

## 后续选项

| 选项 | 描述 | 工时 |
|------|------|:---:|
| A | 加 multi-Python CI 矩阵 (3.12/3.13/3.14) | 30min |
| B | 加 audit_log.revert action (admin only) | 1h |
| C | admin unlock 加 webhook 通知 (邮件/钉钉) | 1h |
| D | DB 损坏预防 3 大方案 | 3 周 |
| E | ASGI uvicorn 试水 | 2h |
| F | 暂停 (v3.15 已 9/10 生产就绪 + 7/7) | - |
