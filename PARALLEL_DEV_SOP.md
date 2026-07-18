# PARALLEL_DEV_SOP.md - 并行 BUG 修复标准化流程 (v3.3)

> 撰写: 2026-07-04 10:25
> 升级: v3.2 → v3.3 (自验证 + PM Gate + Integration 按需)
> 基于: v3.2 试跑反馈 + PM 批准 "自验证 + PM 签字" 模型
> 适用范围: `excel-to-diagram` 项目并行 BUG 修复
> 状态: **TRIAL_RUNNING_V33** (5 个 BUG 或 2 周后复盘, 从 v3.3 生效起重新计数)

---

## 0. v3.3 关键改动 (与 v3.2 对比)

| 改动 | v3.2 | v3.3 |
|------|------|------|
| 阶段数 | 8 | **6** |
| Integration | 常开 (3007/3018) | **按需** (仅当 Agent 触及同一模块时激活) |
| Agent 验证 | worktree 单测 + integration E2E | **真实服务自验证** (后端 + 前端 + API 冒烟) |
| PM 验证 | 隐含在阶段 6f | **显式 PM_VERIFIED 门控** |
| HANDOVER | 无自验证证据要求 | **必须包含 SELF_VERIFY_RESULTS** |
| 自验证工具 | 无 | **_wt_service.py + self_verify.py** |
| Agent 等待时间 | 等待 Integration ready | **零等待** (自己启停服务) |

**核心哲学变化**: Integration 不再常开。每个 Agent 在自己的 worktree 中用真实服务自验证, PM 做最终人工验证。Integration 仅在多 Agent 触及同一模块时按需激活。

---

## 1. 试跑期定义 v3.3

| 维度 | 值 |
|------|-----|
| **试跑期长度** | **5 个 BUG 或 2 周** (从 v3.3 生效起重新计数) |
| **试跑期并行** | **允许多 Agent 并行** (PM 决策, 默认 1-2 个 Agent 并行) |
| **Integration** | **按需** (仅当 2+ Agent 触及同一模块时激活, 详见 §14) |
| **自验证** | **强制** (每个 Agent 必须用真实服务自验证, 详见 §13) |
| **PM 签字** | **强制** (PM_VERIFIED 门控, 无签字不算完成) |
| **试跑起算** | 2026-07-04 (v3.2 原始起算日, v3.3 是延续而非重启) |
| **v3.3 计数重置** | 5 个 BUG 或 2 周从 v3.3 生效起算 |
| **试跑结束** | 5 个 BUG 跑完 + 复盘 PM 决策 |

### 1.1 v3.3 基础设施约束 (继承自 v3.2, 仍需遵守)

| # | 约束 | 解决方案 |
|---|------|----------|
| **C1** | **P0 DB 锁禁止同 DB 多实例** | 自验证 worktree 必用独立 DB = `cp release DB → worktree DB` |
| **C2** | **`vite preview` 不启用 server.proxy** | worktree 前端必跑 **`vite dev`** (有 proxy) |
| **C3** | **`vite.config.js` 写死 port 3006 + proxy 3011** | worktree 的 `vite.config.js` 必改端口 + proxy |
| **C4** | **HMR 端口冲突** | `--strictPort` + 不同端口 |

---

## 2. 资源所有权 v3.3

| 资源 | 拥有者 | 用户访问 |
|------|--------|----------|
| `D:\filework\excel-to-diagram\` (feat 分支) | Agent (R/W) | 0 |
| `D:\filework\worktrees/release-prep\` (release) | 协调智能体 (R/W) | 0 |
| 主 release DB | 协调智能体 (R/W) | 间接 |
| 主 3006 vite preview | 协调智能体 (R/W) | **用户** |
| 主 3011 waitress_server.py | 协调智能体 (R/W) | 间接 |
| 各 BUG worktree (强隔离) | Agent (R/W) | 0 |
| 各 BUG tmp.db | Agent (R/W) | 0 |
| **自验证服务端口** (Agent 临时) | Agent (启停) | 0 |
| **Integration worktree** (按需) | 协调智能体 (R/W) | 0 |
| **Integration 3007/3018** (按需) | 协调智能体 (R/W) | 0 |
| HANDOVER 文档 | Agent → 协调 → PM | PM |

---

## 3. 标准流程 v3.3 (6 阶段, 自验证 + PM Gate + Integration 按需)

```
[PM]                    [开发智能体]              [协调智能体]
  │                         │                        │
  ├── 1. 分配 BUG ────────►│                        │
  │   (含是否需Integration) │                        │
  │                         │                        │
  │                         ├── 2. worktree + 实现    │
  │                         │                        │
  │                         ├── 3. 自验证 (真实服务)   ← 核心变化!
  │                         │   a. _wt_service.py start-be <wt-name>
  │                         │   b. _wt_service.py start-fe <wt-name>
  │                         │   c. self_verify.py smoke <wt-name>
  │                         │   d. _wt_service.py stop <wt-name>
  │                         │   e. 输出 SELF_VERIFY_RESULTS
  │                         │                        │
  │                         ├── 4. commit + HANDOVER ─►│
  │                         │   (附 SELF_VERIFY_RESULTS)
  │                         │                        │
  │                         │                        ├── 5. cherry-pick 到 release-prep
  │                         │                        │   + 重启 3006/3011
  │                         │                        │
  │  ├── 6. PM 验证 ◄──────│────────────────────────│
  │  │   PM_VERIFIED 签字   │                        │
  │  │                      │                        │
  │  └── 部署               │                        │
```

### 阶段 1: PM 分配 BUG

PM 分配 BUG, 在 HANDOVER 模板中标注:
- `SOP_VERSION: v3.3`
- `RISK: LOW / MEDIUM / HIGH / URGENT`
- `INTEGRATION_NEEDED: YES / NO` (PM 根据 §14 决策树判断)
- `depends_on: V###` (如有依赖)

### 阶段 2: worktree + 实现

Agent 在自己的 worktree 中:
1. 创建/进入 worktree: `D:\filework\worktrees\<wt-name>`
2. 基于 release-prep 创建 feat 分支
3. 实现代码改动
4. 编写/更新单元测试
5. 确保单元测试 PASS

**退出条件**: 代码实现完成 + 单元测试 100% PASS

### 阶段 3: 自验证 (核心变化!)

Agent 在 worktree 中用真实服务自验证:

```
3a. 启动后端
    python scripts/_wt_service.py start-be <wt-name>

3b. 启动前端 (如有前端改动)
    python scripts/_wt_service.py start-fe <wt-name>

3c. 运行冒烟测试
    python scripts/self_verify.py smoke <wt-name>

3d. 停止服务
    python scripts/_wt_service.py stop <wt-name>

3e. 生成 SELF_VERIFY_RESULTS
    python scripts/self_verify.py report <wt-name>
```

**快捷命令** (自动化 3a-3e):
```bash
python scripts/self_verify.py run <wt-name>
```

**快速迭代** (仅 healthz, 用于开发中快速检查):
```bash
python scripts/self_verify.py quick <wt-name>
```

**退出条件**: 自验证 ALL PASS + SELF_VERIFY_RESULTS 已生成

### 阶段 4: commit + HANDOVER

Agent:
1. commit + push feat 分支
2. 填写 HANDOVER 文档, **必须包含 SELF_VERIFY_RESULTS** (见 §13)
3. 通知协调智能体

**退出条件**: commit + push 成功, HANDOVER 包含 SELF_VERIFY_RESULTS

**铁律**: HANDOVER 不含 SELF_VERIFY_RESULTS = 无效。协调智能体直接 reject。

### 阶段 5: 协调智能体 cherry-pick + 重启

协调智能体:
1. review HANDOVER + SELF_VERIFY_RESULTS
2. cherry-pick 到 release-prep (按 depends_on 拓扑序)
3. (后端) restart 3011
4. (前端) npm run build + restart 3006
5. (DB) ALTER (HIGH 风险)
6. 基础冒烟: `curl http://localhost:3011/api/v1/health` + `curl http://localhost:3006`

**退出条件**: cherry-pick + 重启成功 + 基础冒烟 PASS

### 阶段 6: PM 验证 (PM_VERIFIED 门控)

PM 在 3006/3011 上进行人工业务流验证:
1. PM 验证 BUG 修复是否生效
2. PM 验证相关业务流是否正常
3. PM 签字 `PM_VERIFIED: YES` + 验证备注
4. 标 HANDOVER STATUS: DEPLOYED

**退出条件**: PM_VERIFIED 已签字

**铁律**: 无 PM_VERIFIED = 未完成。即使自验证 ALL PASS, 也必须 PM 签字。

### 阶段 6→7 衔接: PM 通知 + 部署触发 (v3.3 新增)

```
阶段 6 PM_VERIFIED=YES
    │
    ├── 协调智能体更新 .agent-status.json:
    │   v33_pipeline.deploy_pending.pending = true
    │   v33_pipeline.deploy_pending.bugs = ["V###"]
    │   v33_pipeline.deploy_pending.pm_verified_at = <timestamp>
    │   v33_pipeline.pm_review_pending.pending = false
    │
    ├── 协调智能体触发部署 (2 种模式):
    │   ├── 日常模式: python tools/staging_deploy_orchestrator.py
    │   └── 热修模式: DEPLOY_MODE=hotfix python tools/staging_deploy_orchestrator.py
    │
    ├── 部署成功后:
    │   v33_pipeline.deploy_pending.pending = false
    │   v33_pipeline.deploy_pending.last_deployed = <timestamp>
    │   HANDOVER STATUS: DEPLOYED
    │
    └── 部署失败:
        v33_pipeline.deploy_pending.pending = true (保持)
        协调智能体告警 PM, 等待人工介入
```

**PM 通知机制** (3 层):
1. `.agent-status.json` 的 `pm_review_pending` 字段 (PM 会话启动时检查)
2. `.coord/events.jsonl` 追加事件 (Agent 启动时读最近 N 条)
3. 协调智能体在 PM 会话中口头报告 "有 N 个 BUG 待 PM 验证"

**部署触发铁律**:
- 无 PM_VERIFIED = 不许部署
- 部署前必须确认 `.agent-status.json` 的 `deploy_pending.pm_verified_at` 已填
- 部署后必须更新 `deploy_pending.last_deployed` + HANDOVER STATUS: DEPLOYED

---

## 4. 阶段门 v3.3

| 阶段转换 | 退出条件 |
|----------|----------|
| 2 → 3 | 代码实现完成 |
| **3 → 4** | **自验证 ALL PASS + SELF_VERIFY_RESULTS 已生成** |
| 4 → 5 | commit + push 成功, HANDOVER 包含 SELF_VERIFY_RESULTS |
| 5 → 6 | 协调智能体 cherry-pick + 重启 3006/3011 成功 |
| **6 → 7 (部署)** | **PM_VERIFIED 已签字 + deploy_pending 已更新** |
| 7 → 完成 | staging 部署成功 + last_deployed 已更新 |

---

## 5. 验证责任分层 v3.3

| 层级 | 验证内容 | 谁做 | 在哪 |
|------|----------|------|------|
| **L0: 自验证** | API 冒烟 + 前端渲染 + 单元测试 | **Agent** | worktree (分配端口上的真实服务) |
| **L1: PM Gate** | 人工业务流验证 | **PM** | release-prep 3006/3011 |
| **L2: Integration** (按需) | 跨 Agent 兼容性 | Agent | 3007/3018 |

**L0 + L1 分层防御**:
- L0 自验证: 保证代码基本可运行 (API 通、页面可渲染、单测 PASS)
- L1 PM Gate: 保证业务逻辑正确 (自验证可能假阳性, PM 人工兜底)
- L2 Integration: 保证跨 Agent 兼容性 (仅在需要时激活)

---

## 6. 风险等级 v3.3

| 等级 | 触发条件 | 流程 |
|------|----------|------|
| **LOW** | 文案 / UI / 显示 / 字段映射 | worktree 自验证 + cherry-pick + PM 验证 |
| **MEDIUM** | API 行为变更 / 跨对象 | 同上, 协调智能体加强 review |
| **HIGH** | DB schema / 鉴权 / 性能 | 同上, 协调智能体必 review dry-run + 必 ALTER |
| **URGENT** | 生产事故 | 立即 cherry-pick, 跳过自验证, 直接 PM 验证 |

---

## 7. 并行策略 v3.3 (含 Integration 决策)

| 场景 | PM 策略 | Integration? |
|------|--------|-------------|
| **2 个 BUG 同一文件** | **串行** (避免冲突) | No |
| **2 个 BUG 不同文件, 不同模块** | **并行** | **No** (默认) |
| **2 个 BUG 不同文件, 同一模块** | **并行** | **Yes** (按需) |
| **2 个 BUG 其中一个改共享 API** | **并行** | **Yes** |
| **2 个 BUG 互相依赖** | **串行** (A 必须先 DEPLOYED) | No |
| **3+ BUG 并行** | **PM 严格 review** | Likely Yes |

**默认: 不需要 Integration** (独立功能 + 独立模块)

---

## 8. 试跑期 KPI 监控 v3.3

### 8.1 指标 1: 用户感知 (关键, 触发升级)

| 指标 | 阈值 (任一触发升 v3.4) | 测量 |
|------|------------------------|------|
| **3006 重启报错率** | > 5% | 协调智能体看 waitress stderr 5xx |
| **cherry-pick 后 3006 即时失败** | > 0 次/3 BUG | 协调智能体立刻冒烟 |
| **用户报告 3006 出问题** | > 1 次/周 | PM 数 |

### 8.2 指标 2: Agent 行为 (违规, 触发升级)

| 指标 | 阈值 | 测量 |
|------|------|------|
| **Agent 直接动 release DB** | > 0 | 协调智能体 HANDOVER 标 `RELEASE_DB_VIOLATION` |
| **Agent 误用 3006/3011 验证** | > 0 | 协调智能体监控 access log |
| **Agent 改坏需要 git revert** | > 0 / 5 BUG | 协调智能体 git revert 数 |
| **HANDOVER 缺 SELF_VERIFY_RESULTS** | > 0 | 协调智能体 reject 数 |

### 8.3 指标 3: 自验证质量 (v3.3 新, 核心)

| 指标 | 目标 | 测量 |
|------|------|------|
| **自验证首次通过率** | > 95% | Agent 提交 HANDOVER 时自验证 PASS / 总提交 |
| **自验证逃避率** (弱 SELF_VERIFY_RESULTS) | < 10% | 协调智能体抽检发现无实质验证 / 总 HANDOVER |
| **PM 驳回率** (自验证 PASS 但 PM reject) | < 15% | PM reject 数 / 总 PM 验证数 |

### 8.4 指标 4: 时间效率

| 指标 | 期望 | 测量 |
|------|------|------|
| **BUG 报告 → 用户看到** (单 BUG) | < 30 分钟 (LOW) | HANDOVER 时间 |
| **2 BUG 并行总耗时** | < 单 BUG 2 倍 (理想 1.5x) | 对比串行耗时 |
| **协调智能体阶段 5 耗时** | < 10 分钟 (2 BUG 一起) | cherry-pick + 重启 |
| **3006 总断连时间** | < 60s/周 (1 次批量重启) | 累加 |
| **Agent 自验证耗时** | < 5 分钟 (含启停服务) | self_verify.py 计时 |

### 8.5 KPI 记录位置

每个 BUG 跑完, 协调智能体在 HANDOVER 末尾追加:

```markdown
## 11. v3.3 试跑期 KPI (本次 BUG)
- 3006 重启报错率: 0/3 = 0% PASS
- cherry-pick 后即时冒烟: PASS
- 用户报告: 0
- Agent 违规: 0
- 协调智能体阶段 5 耗时: 8 分钟 (批量 2 BUG)
- 3006 断连时间: 35s
- 自验证首次通过率: PASS
- 自验证耗时: 3 分钟
- PM 验证结果: PM_VERIFIED=YES
- Integration 是否启用: NO (独立模块)
```

---

## 9. 试跑退出决策树 v3.3

```
5 个 BUG 跑完 (或 2 周到)
    │
    ├── 指标 1 (用户感知) 触发 ──────────► 升级 v3.4 (加限制)
    │
    ├── 指标 2 (Agent 行为) 触发 ────────► 升级 v3.4 (加严)
    │
    ├── 指标 3 (自验证质量) 逃避率 > 30% ──► 升级 v3.4 (自验证加严, 加抽检)
    │
    ├── 指标 3 (自验证质量) PM 驳回率 > 30% ─► 升级 v3.4 (自验证标准提高)
    │
    ├── 指标 4 (时间) 优于 v3.2 ─────────► v3.3 升为正式 SOP
    │
    └── 综合: 0 红旗 + 时间好 + 自验证质量好 ──► v3.3 升为正式
```

---

## 10. 已知风险 + 对策 v3.3

| 风险 | 对策 |
|------|------|
| **R1-R12** (同 v3.1) | (略) |
| **R15. (v3.3 新) 自验证逃避** — Agent 标 PASS 但未真实验证 | SELF_VERIFY_RESULTS 必须包含真实命令输出; 协调智能体抽检 |
| **R16. (v3.3 新) 自验证假阳性** — 服务运行但逻辑错误 | PM Gate 兜底; L0+L1 分层防御 |
| **R17. (v3.3 新) 跨 Agent 不兼容漏检** (无 Integration 时) | PM 并行策略设计上消除重叠; Integration 按需作安全网 |
| **R18. (v3.3 新) 自验证端口冲突** — 多 Agent 同时自验证 | `_wt_service.py` 自动分配端口, 基于配置映射表 |
| **R19. (v3.3 新) 自验证环境与生产不一致** | 自验证用 release DB 副本, 尽量贴近生产; PM Gate 兜底 |

---

## 11. 决策点 v3.3

| # | 决策 | PM 答 | 写入 |
|---|------|-------|------|
| D1-D21 | (同 v3.2) | (略) | (略) |
| **D22 (v3.3 新)** | **Integration 按需 vs 常开** | **按需** (PM 决策) | §1, §5, §14 |
| **D23 (v3.3 新)** | **自验证要求强度** | **真实服务 + API 冒烟** (非仅单元测试) | §3, §13 |
| **D24 (v3.3 新)** | **PM_VERIFIED 强制性** | **是** (无 PM 签字不算完成) | §3 阶段 6 |

---

## 12. 命令清单 v3.3

### 阶段 3: Agent 自验证 (在 worktree 中)

```bash
# 3a. 启动后端
python scripts/_wt_service.py start-be <wt-name>

# 3b. 启动前端 (如有前端改动)
python scripts/_wt_service.py start-fe <wt-name>

# 3c. 运行冒烟测试
python scripts/self_verify.py smoke <wt-name>

# 3d. 完整自验证 (自动化: 启动 → 冒烟 → 停止 → 报告)
python scripts/self_verify.py run <wt-name>

# 3e. 快速检查 (仅 healthz, 用于开发中快速迭代)
python scripts/self_verify.py quick <wt-name>

# 3f. 停止服务
python scripts/_wt_service.py stop <wt-name>

# 3g. 生成 SELF_VERIFY_RESULTS 报告
python scripts/self_verify.py report <wt-name>

# 3h. 查看所有 worktree 服务状态
python scripts/_wt_service.py status-all
```

### 阶段 5: 协调智能体 cherry-pick + 重启

```bash
# 5a. review HANDOVER + SELF_VERIFY_RESULTS
# (人工/半自动检查)

# 5b. 批量 cherry-pick (按 depends_on 拓扑序)
cd D:\filework\worktrees/release-prep
git cherry-pick <feat-sha-A> <feat-sha-B> ...

# 5c. 批量 restart
npm run build
Start-Process node.exe ... vite preview --port 3006
Start-Process python.exe ... waitress_server.py

# 5d. 基础冒烟
curl http://localhost:3011/api/v1/health
curl http://localhost:3006
```

### Integration (按需, 仅当 PM 决定)

```bash
# 启动 integration 服务 (协调智能体)
python scripts/_wt_service.py start-be integration
python scripts/_wt_service.py start-fe integration

# Agent 在 integration 跑跨兼容性测试
# ... 同 v3.2 阶段 5 的 E2E 流程 ...

# 停止 integration
python scripts/_wt_service.py stop integration
```

---

## 13. SELF_VERIFY_RESULTS 规范 (v3.3 新, HANDOVER 必填)

**铁律: HANDOVER 不含 SELF_VERIFY_RESULTS = 无效。协调智能体直接 reject。**

### 13.1 模板

```markdown
## SELF_VERIFY_RESULTS

### 后端 API 冒烟
| API | 方法 | 期望状态码 | 实际状态码 | VERDICT |
|-----|------|----------|----------|---------|
| /api/v1/health | GET | 200 | 200 | PASS |
| /api/v1/<related> | GET | 200 | 200 | PASS |

### 前端渲染验证 (如有前端改动)
| 页面 | 验证方式 | 结果 | VERDICT |
|------|---------|------|---------|
| /system/xxx | PlaywrightCLI 截图 | 正常渲染 | PASS |
| (无前端改动) | — | — | N/A |

### 单元测试
| 测试文件 | 用例数 | 通过 | 失败 | VERDICT |
|---------|-------|------|------|---------|
| test_xxx.py | 5 | 5 | 0 | PASS |

### 改动影响范围
| 修改文件 | 影响范围 | 是否影响共享 API |
|---------|---------|----------------|
| api/xxx.py | xxx接口 | 否 |

### 自验证环境
| 项 | 值 |
|----|-----|
| 后端端口 | 3013 |
| 前端端口 | 3009 |
| 验证时间 | 2026-07-17T14:30:00Z |
```

### 13.2 填写规则

1. **后端 API 冒烟**: 必须包含 `/api/v1/health` + 与本次 BUG 相关的所有 API
2. **前端渲染验证**: 如有前端改动, 必须用 PlaywrightCLI 截图验证; 无前端改动标 N/A
3. **单元测试**: 必须包含用例数 + 通过/失败数, 不可只写 PASS
4. **改动影响范围**: 必须明确标注是否影响共享 API (决定是否需要 Integration)
5. **自验证环境**: 必须记录实际使用的端口号和验证时间 (可追溯)

### 13.3 协调智能体抽检规则

协调智能体对 SELF_VERIFY_RESULTS 进行抽检:
- **100% 抽检**: HIGH/URGENT 风险的 HANDOVER
- **30% 抽检**: MEDIUM 风险的 HANDOVER
- **10% 抽检**: LOW 风险的 HANDOVER

抽检方式: 要求 Agent 提供自验证的原始命令输出 (非汇总表)。

---

## 14. Integration 按需激活条件 (v3.3 新)

### 14.1 决策树

```
PM 分配 BUG
    │
    ├── 仅 1 个 Agent? ────────────────► 不需要 Integration
    │
    ├── 2+ Agent 并行:
    │   │
    │   ├── 不同模块? ─────────────────► 不需要 Integration (默认)
    │   │
    │   ├── 同一模块, 不同文件? ────────► 需要 Integration
    │   │
    │   ├── 其中一个改共享 API? ───────► 需要 Integration
    │   │
    │   ├── 3+ Agent 同时提交? ────────► 需要 Integration
    │   │
    │   └── PM 明确要求? ─────────────► 需要 Integration
    │
    └── 默认 ─────────────────────────► 不需要 Integration
```

### 14.2 Integration 激活流程

当 PM 决定需要 Integration 时:
1. PM 在分配时标注 `INTEGRATION_NEEDED: YES`
2. 协调智能体在阶段 4 后启动 Integration worktree + 3007/3018
3. 相关 Agent 在 Integration 上跑跨兼容性 E2E
4. Integration 验证 PASS 后, 继续阶段 5

### 14.3 默认情况

**默认: 不需要 Integration。** 独立功能 + 独立模块的并行 BUG 修复, 自验证 + PM Gate 已足够。

---

## 15. _wt_service.py / self_verify.py 使用指南 (v3.3 新)

### 15.1 _wt_service.py — Worktree 服务管理

**路径**: `scripts/_wt_service.py`

**功能**: 为指定 worktree 启动/停止后端和前端服务, 自动分配端口。

| 命令 | 说明 |
|------|------|
| `start-be <wt-name>` | 启动后端服务 (自动分配端口, 拷贝 DB) |
| `start-fe <wt-name>` | 启动前端服务 (自动分配端口, 配置 proxy) |
| `stop <wt-name>` | 停止指定 worktree 的所有服务 |
| `status <wt-name>` | 查看指定 worktree 的服务状态 |
| `status-all` | 查看所有 worktree 的服务状态 |

**端口分配**: 基于配置映射表, 每个 worktree 有预分配的端口, 避免冲突。

**使用示例**:
```bash
# 启动 worktree-V050 的后端
python scripts/_wt_service.py start-be V050
# 输出: Backend started on port 3013 for worktree V050

# 启动 worktree-V050 的前端
python scripts/_wt_service.py start-fe V050
# 输出: Frontend started on port 3009 for worktree V050

# 查看状态
python scripts/_wt_service.py status V050
# 输出: V050: BE=3013(running), FE=3009(running)

# 停止
python scripts/_wt_service.py stop V050
# 输出: All services stopped for worktree V050
```

### 15.2 self_verify.py — 自验证工具

**路径**: `scripts/self_verify.py`

**功能**: 在 worktree 的真实服务上运行自动化验证。

| 命令 | 说明 |
|------|------|
| `run <wt-name>` | 完整自验证 (启动 → 冒烟 → 停止 → 报告) |
| `smoke <wt-name>` | 冒烟测试 (服务必须已启动) |
| `report <wt-name>` | 生成 SELF_VERIFY_RESULTS 报告 |
| `quick <wt-name>` | 快速检查 (仅 healthz, 用于开发迭代) |

**使用示例**:
```bash
# 完整自验证 (推荐, 一键完成)
python scripts/self_verify.py run V050
# 输出:
# [1/4] Starting backend... port 3013
# [2/4] Starting frontend... port 3009
# [3/4] Running smoke tests...
#   /api/v1/health ... PASS (200)
#   /api/v1/archdata ... PASS (200)
#   Frontend /system/archdata ... PASS
#   Unit tests ... 5/5 PASS
# [4/4] Stopping services...
# SELF_VERIFY_RESULTS generated: .trae/self_verify_V050.md

# 快速检查 (开发中, 仅 healthz)
python scripts/self_verify.py quick V050
# 输出: /api/v1/health ... PASS (200)

# 仅冒烟 (服务已手动启动时)
python scripts/self_verify.py smoke V050

# 生成报告 (重新生成, 不重新运行测试)
python scripts/self_verify.py report V050
```

### 15.3 自验证工作流推荐

| 场景 | 推荐命令 |
|------|---------|
| **首次完整验证** | `self_verify.py run <wt-name>` |
| **开发中快速迭代** | `_wt_service.py start-be <wt-name>` → `self_verify.py quick <wt-name>` (反复) → `_wt_service.py stop <wt-name>` |
| **修复后重新验证** | `self_verify.py run <wt-name>` |
| **仅需冒烟** | `self_verify.py smoke <wt-name>` (服务已启动) |

---

## 附录: 版本历史

| 版本 | 状态 | 关键特性 | 何时用 |
|------|------|----------|--------|
| v3.0 | (历史) | 5/6 阶段 + 风险等级 | 不再使用 |
| v3.1 | (试跑 1) | 串行, 0 integration, KPI 监控 | (已 pass, 试跑基本流程) |
| v3.2 | (试跑 2) | 并行, integration 常开, PM 提案精确化 | (已 pass, 并行能力验证) |
| **v3.3** | **TRIAL_RUNNING_V33** | **自验证 + PM Gate + Integration 按需 + SELF_VERIFY_RESULTS** | **当前** |

---

## 附录: v3.3 关键设计决策来源

| 决策 | 来源 | 文档位置 |
|------|------|----------|
| **Agent 自验证 (真实服务)** | v3.2 试跑反馈: 单测不够, 需要真实服务验证 | §3 阶段 3 |
| **PM_VERIFIED 门控** | PM 批准: 自验证可能假阳性, PM 签字兜底 | §3 阶段 6 |
| **Integration 按需** | v3.2 试跑反馈: 多数 BUG 独立模块, Integration 常开浪费 | §14 |
| **SELF_VERIFY_RESULTS 必填** | 防止自验证逃避, 提供可追溯证据 | §13 |
| **_wt_service.py + self_verify.py** | 工具化自验证流程, 减少人工操作 | §15 |
| **L0+L1+L2 分层防御** | 自验证 (L0) + PM Gate (L1) + Integration (L2) 各有侧重 | §5 |
| **Agent 零等待** | v3.2 试跑反馈: Agent 等待 Integration ready 浪费时间 | §3 |

---

**撰写完成时间**: 2026-07-17
**版本**: v3.3 (自验证 + PM Gate + Integration 按需, TRIAL_RUNNING_V33)
**PM 已确认**: D1-D21 (v1-v3.2 累计) + **D22 (Integration 按需)** + **D23 (自验证要求)** + **D24 (PM_VERIFIED 强制)**
**试跑计数**: 5 个 BUG 或 2 周从 v3.3 生效起算 (原 v3.2 起算日 2026-07-04, v3.3 是延续)
**待 PM 复盘**: 5 BUG 跑完或 2 周到时, 召集复盘
