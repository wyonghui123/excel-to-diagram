# DEPLOY_HANDOVER_BUG_V### - <一句话标题>

> **SOP_VERSION**: PARALLEL_DEV_SOP v3.2 (TRIAL_RUNNING_PARALLEL)
> **RISK**: LOW | MEDIUM | HIGH | URGENT
> **depends_on**: V### (无则填 NONE)
> **HANDOFF_FROM**: dev-agent | coordinator
> **TIMESTAMP**: 2026-MM-DD HH:MM

---

## 0. TL;DR (7 字段)

| 字段 | 值 |
|------|-----|
| BUG-ID | V### |
| 根因类型 | ENV/CONFIG / FRONTEND / BACKEND / DATA / OTHER |
| 严重度 | P1-Critical / P2-High / P3-Medium / P4-Low |
| 修复 Commit | `<hash>` (worktree-分支) |
| 集成 Commit | `<hash>` (integration-分支) |
| 验证状态 | ✅ PASS / 🟡 PENDING / ❌ FAIL |
| 主服务验证 | ⏳ 待协调智能体 |

---

## 1. 根因 (5W1H)

| 项 | 内容 |
|------|------|
| **What** | 现象：用户/PM 看到什么 |
| **Where** | 文件:行号 + 模块 |
| **When** | 触发条件 (请求路径 / 操作) |
| **Why** | 根本原因 (1-3 句) |
| **Who** | 报告人 + 影响人 |
| **How to fix** | 修复思路 (1-3 句) |

### 复现步骤

```powershell
# 1. 触发场景的完整命令
# 2. 预期 vs 实际
```

---

## 2. Fix 详情

### 2.1 改动文件清单 (spec.md 白名单)

| 文件 | 改动类型 | 行号 |
|------|----------|------|
| `path/to/file1.py` | 修改 | L### |
| `path/to/file2.vue` | 新增 | - |

### 2.2 关键代码 diff

```diff
# path/to/file1.py
- old code
+ new code
```

### 2.3 Worktree Commit

```
<commit-hash> <branch-name>
<commit message>
```

### 2.4 集成 Commit (协调智能体操作后填)

```
<commit-hash> integration/2026-MM-DD
```

---

## 3. v3.2 流程执行情况 (8 阶段)

| 阶段 | 负责方 | 状态 | 备注 |
|------|--------|------|------|
| **1. PM 分配 BUG** | PM | ✅ / 🟡 / ❌ | depends_on: V### |
| **2A. Worktree + Edit** | dev-agent | ✅ | `<branch>` |
| **3A. Commit + Push** | dev-agent | ✅ | commit `<hash>` |
| **4. Integration 启动** | coordinator | ✅ | 端口 3007/3018 |
| **4A. Cherry-pick to integration** | dev-agent | ✅ | integration commit `<hash>` |
| **5A. integration E2E 验证** | dev-agent | ✅ / 🟡 | 含 5a/5b/5c 3 步 |
| **6. Cherry-pick to release** | coordinator | ⏳ | 待协调执行 |
| **6f. 主服务 3006/3011 真实 E2E** | coordinator | ⏳ | 待协调执行 |

---

## 4. Integration 验证状态

### 4.1 单跑 A (5A-a)

| 项 | 结果 |
|------|------|
| 验证环境 | http://localhost:3007 / http://localhost:3018 |
| 自 fix 验证 | ✅ PASS / ❌ FAIL |
| 截图 | `.trae/debug/sessions/V###/single_A.png` |

### 4.2 同时跑 (A+B) 兼容性 (5A-b)

| 项 | 结果 |
|------|------|
| A 单独 | ✅ |
| A+B 同时 | ✅ / ❌ 回归 |
| depends_on 验证 | ✅ / ❌ |

### 4.3 E2E 标记 (5A-c)

- [OK] 单跑 A PASS
- [OK] (A+B) 兼容性 PASS
- [OK] 关键场景 (列 3-5 个) 全部 PASS

---

## 5. v3.2 试跑 KPI (§11 字段)

### 5.1 用户感知

| 指标 | 阈值 | 实际 | 状态 |
|------|------|------|------|
| 3006 重启报错率 | < 5% | 0% | ✅ |
| cherry-pick 后即时失败 | < 1/3 BUG | 0 | ✅ |
| 用户报告 3006 问题 | < 1/周 | 0 | ✅ |

### 5.2 Agent 行为

| 指标 | 阈值 | 实际 | 状态 |
|------|------|------|------|
| Agent 直接动 release DB | 0 | 0 | ✅ |
| Agent 误用 3006/3011 验证 | 0 | 0 | ✅ |
| Agent 改坏需 git revert | 0 | 0 | ✅ |

### 5.3 时间效率

| 指标 | 期望 | 实际 | 状态 |
|------|------|------|------|
| BUG 报告 → 用户看到 | < 30 min (LOW) | ___ min | ⏳ |
| 协调阶段 4-6 耗时 | < 10 min | ___ min | ⏳ |
| 3006 总断连时间 | < 60s/周 | ___ s | ⏳ |

### 5.4 并行特定

| 指标 | 期望 | 实际 |
|------|------|------|
| integration 验证发现冲突 | < 10% | ___% |
| 协调批量 cherry-pick 频率 | > 50% | ___% |
| 并行 BUG 实际节省时间 | > 30% | ___% |

---

## 6. 修复详细代码

### 6.1 主修复

```python
# 完整代码片段
```

### 6.2 防御性补丁 (如适用)

```python
# 防止同类问题
```

### 6.3 副作用评估

- DB 迁移: 无 / 有 (详情)
- 缓存失效: 无 / 有 (key 列表)
- API 兼容: 向后 / 破坏 (版本)

---

## 7. 待协调智能体 / PM 操作

### 7.1 协调智能体

- [ ] Cherry-pick 到 release 分支 (`integration/2026-MM-DD` → `release/2026-MM-DD`)
- [ ] Restart 3011 后端
- [ ] `npm run build` + Restart 3006 前端
- [ ] 运行 6f 主服务 E2E 验证
- [ ] 标 DEPLOYED

### 7.2 PM 决策 (如需)

- [ ] 是否升 v3.3 试跑
- [ ] 是否回滚 v3.2
- [ ] 是否调整并行策略

---

## 8. 风险与回滚

### 8.1 风险评估

| 风险 | 影响 | 缓解 |
|------|------|------|
| ___ | High/Med/Low | ___ |

### 8.2 回滚方案

```powershell
# 1. 回滚 release 分支
git revert <commit>

# 2. 重启服务
service_manager.ps1 restart 3011
service_manager.ps1 restart 3006

# 3. 验证回滚
curl http://localhost:3011/api/v1/health
```

---

## 9. 关联文档

| 文档 | 链接 |
|------|------|
| PARALLEL_DEV_SOP | `PARALLEL_DEV_SOP.md` |
| worktree 修复 commit | `<git-show-url>` |
| integration 集成 commit | `<git-show-url>` |
| 主服务验证记录 | `d:\filework\logs\backend_v3011.out` |

---

## 10. HANDOVER 状态

| 阶段 | 状态 | 时间 | 操作人 |
|------|------|------|--------|
| HANDED_OVER | 🟡 当前 | 2026-MM-DD HH:MM | dev-agent |
| DEPLOYED | ⏳ 待协调 | - | coordinator |
| VERIFIED | ⏳ 待 PM | - | PM |

---

**模板版本**: v1.0
**来源**: 基于 V043/V044 实际格式提取 (2026-07-04)
**维护**: PM
**使用**: dev-agent 第一次写 HANDOVER 时直接 cp 此模板填空
