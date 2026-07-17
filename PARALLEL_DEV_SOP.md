# PARALLEL_DEV_SOP.md - 并行 BUG 修复标准化流程 (v3.2)

> 撰写: 2026-07-04 10:25
> 升级: v3.1 → v3.2 (并行试跑: 启用 integration, 允许多 Agent 并行)
> 基于: PM 提案 "想试一下并行开发, 试跑这个流程" + 跨 Agent 同步问题
> 适用范围: `excel-to-diagram` 项目并行 BUG 修复
> 状态: **TRIAL_RUNNING_PARALLEL** (并行试跑期, 5 个 BUG 或 2 周后复盘)

---

## 0. v3.2 关键改动 (与 v3.1 对比)

| 改动 | v3.1 | v3.2 |
|------|------|------|
| integration 状态 | **0** (LOW/MEDIUM) | **1** (全部启用) |
| 多 Agent 并行 | **禁** (试跑期) | **允** (PM 决策) |
| Agent 验证环境 | worktree 单测 + (HIGH) integration | **worktree 单测 + integration 3007/3018 (全部风险)** |
| 协调智能体 E2E | 协调跑 3006/3011 真实 E2E | 协调跑 3006/3011 + 3007/3018 真实 E2E |
| Agent 在 3006/3011 E2E | **违规** (MAIN_PORT_VIOLATION) | **违规** (不变) |

**核心洞察**: 并行**必然**需要 integration. v3.1 试串行, v3.2 试并行.

---

## 1. 试跑期定义 v3.2 (并行)

| 维度 | 值 |
|------|-----|
| **试跑期长度** | **5 个 BUG 或 2 周** (同 v3.1) |
| **试跑期并行** | **允许多 Agent 并行** (PM 决策, 默认 1-2 个 Agent 并行) |
| **integration 状态** | **常开** (3007/3018 长期运行, 协调智能体维护) |
| **试跑起算** | 2026-07-04 10:25 (v3.2 文档生效) |
| **试跑结束** | 5 个 BUG 跑完 + 复盘 PM 决策 |

### 1.1 integration 基础设施约束 (PM 验证后新增, 重要!)

> **2026-07-04 PM 验证发现**: integration 3007/3018 基础设施**部分支持**, 必须遵守 4 个约束:

| # | 约束 | 解决方案 |
|---|------|----------|
| **C1** | **P0 DB 锁禁止同 DB 多实例** (`waitress_server.py:104-106` 启动失败) | **integration 必用独立 DB** = `cp release DB → integration DB` (不能 symlink, 不能共享) |
| **C2** | **`vite preview` 不启用 server.proxy** (production 模式) | integration 必跑 **`vite dev --port 3007`** (有 proxy), 不能用 `vite preview` |
| **C3** | **`vite.config.js` 写死 port 3006 + proxy 3011** | integration worktree 的 `vite.config.js` 必改 `port: 3007` + `proxy /api → 3018` |
| **C4** | **HMR 端口冲突 (默认 24678)** | `--strictPort` + 不同端口, 不会冲突 |

**integration worktree 准备清单 (协调智能体, 阶段 4 前必做)**:
1. 创建 `D:/filework/worktrees/integration` (git worktree, 独立目录)
2. 修改 `vite.config.js`: `server.port = 3007` + `proxy /api → 3018` + `proxy /socket.io → 3018`
3. `cp D:/filework/worktrees/release-prep/meta/architecture.db D:/filework/worktrees/integration/meta/architecture.db`
4. 启 integration 后端: `AGENT_PORT=3018 python waitress_server.py` (cwd=worktrees/integration)
5. 启 integration 前端: `npx vite dev --port 3007` (cwd=worktrees/integration)
6. 验证: `curl http://localhost:3018/api/v1/health` + `curl http://localhost:3007` (代理到 3018)

---

## 2. 资源所有权 v3.2 (并行 + integration 启用)

| 资源 | 拥有者 | 用户访问 |
|------|--------|----------|
| `D:\filework\excel-to-diagram\` (feat 分支) | Agent (R/W) | 0 |
| `D:\filework\worktrees/release-prep\` (release) | 协调智能体 (R/W) | 0 |
| 主 release DB | 协调智能体 (R/W) | 间接 |
| 主 3006 vite preview | 协调智能体 (R/W) | **用户** |
| 主 3011 waitress_server.py | 协调智能体 (R/W) | 间接 |
| 各 BUG worktree (强隔离) | Agent (R/W) | 0 |
| 各 BUG tmp.db | Agent (R/W) | 0 |
| **integration worktree** (新) | 协调智能体 (R/W) | 0 |
| **integration 3007 vite** (新) | 协调智能体 (R/W) | 0 (Agent 验证用) |
| **integration 3018 waitress** (新) | 协调智能体 (R/W) | 0 (Agent 验证用) |
| **integration DB** (新) | 协调智能体 (R/W) | 0 (Agent 验证用) |
| HANDOVER 文档 | Agent → 协调 | PM |

---

## 3. 标准流程 v3.2 (8 阶段, 并行 + integration, PM 提案精确化)

```
[PM]                              [开发智能体 A]    [开发智能体 B]    [协调智能体]
  │                                  │                  │                  │
  ├── 1. 分配 BUG-A + BUG-B ─────► │                  │                  │
  │   (可同时分配 2 个)              │                  │                  │
  │                                  │                  │                  │
  │                                  ├── 2A. worktree-A + Edit + 单测  │  │
  │                                  │   (并行做)        │                  │
  │                                  │                  ├── 2B. worktree-B + Edit + 单测
  │                                  │                  │   (并行做)        │
  │                                  │                  │                  │
  │                                  ├── 3A. commit + push + HANDOVER-A ──►│
  │                                  │                  │                  │
  │                                  │                  ├── 3B. commit + push + HANDOVER-B ──►│
  │                                  │                  │                  │
  │                                  │                  │                  ├── 4. 协调智能体:
  │                                  │                  │                  │   a. 启 integration worktree + 3007/3018 (常开)
  │                                  │                  │                  │   b. 通知 Agent: integration ready at 3007/3018
  │                                  │                  │                  │
  │                                  ├── 4A. Agent A 自治: cherry-pick A 到 integration 30XX
  │                                  │   (PM 提案 #2)  │                  │
  │                                  │   - 启 integration worktree (自己 pull 仓库)  │
  │                                  │   - cherry-pick A 进 integration worktree    │
  │                                  │   - 标 INTEGRATION_SHA-A in HANDOVER-A       │
  │                                  │                  │                  │
  │                                  │                  ├── 4B. Agent B 自治: cherry-pick B 到 integration 30XX
  │                                  │                  │   (PM 提案 #2)
  │                                  │                  │   - cherry-pick B 进 integration worktree
  │                                  │                  │   - 标 INTEGRATION_SHA-B in HANDOVER-B
  │                                  │                  │                  │
  │                                  ├── 5A. Agent A 在 integration 跑 E2E  │
  │                                  │   (3 步)         │                  │
  │                                  │   a. 单跑 A 验证自己 fix   │        │
  │                                  │   b. 同时跑 (A+B) 验证兼容性 │        │
  │                                  │   c. 标 E2E: PASS in HANDOVER-A  │  │
  │                                  │                  │                  │
  │                                  │                  ├── 5B. Agent B 在 integration 跑 E2E
  │                                  │                  │   (3 步)
  │                                  │                  │   a. 单跑 B 验证自己 fix
  │                                  │                  │   b. 同时跑 (A+B) 验证兼容性
  │                                  │                  │   c. 标 E2E: PASS in HANDOVER-B
  │                                  │                  │                  │
  │                                  │                  │                  ├── 6. PM 决策 + 批量 cherry-pick
  │                                  │                  │                  │   a. PM 决策: 一起 cherry-pick A + B
  │                                  │                  │                  │   b. 协调智能体批量 cherry-pick A + B (按 depends_on 拓扑序)
  │                                  │                  │                  │   c. (后端) restart 3011
  │                                  │                  │                  │   d. (前端) npm run build + restart 3006
  │                                  │                  │                  │   e. (DB) ALTER (HIGH 风险)
  │                                  │                  │                  │   f. **真实 E2E on 3006/3011 (协调智能体)**
  │                                  │                  │                  │   g. 标 HANDOVER-A 和 HANDOVER-B 均为 DEPLOYED
  │                                  │                  │                  │
  ▼                                  ▼                  ▼                  ▼
```

**v3.2 关键澄清 (PM 提案精确化, Agent 自治版)**:
- ✅ 2 Agent **各跑各的 worktree** (阶段 2A/2B) — PM 提案 #1
- ✅ Agent **各自 cherry-pick 到 integration 30XX** (阶段 4A/4B, 自治) — PM 提案 #2
- ✅ Agent **看到彼此代码** (阶段 5A-b, 5B-b 同时跑 A+B) — PM 提案 #3
- ✅ 协调智能体**批量 cherry-pick + 1 次重启 3006/3011** (阶段 6) — PM 提案 #4
- ✅ 协调智能体**统一验证 3006/3011** (阶段 6f) — PM 提案 #5
- ✅ **integration 30XX 共享** (3007/3018, 协调智能体常开) — 单一 integration 端口, 天然做回归
- ✅ **HANDOVER 标 INTEGRATION_SHA** — 协调智能体阶段 6b review SHA 一致性 (简单试跑用, 后续如需要可加严)
- ✅ **Agent 永不在 3006/3011 跑 E2E** — v3.1 铁律不变

---

## 4. 阶段门 v3.2

| 阶段 | 退出条件 |
|------|----------|
| **2 → 3** | worktree 内单元测试 100% PASS |
| **3 → 4** | commit + push 成功, HANDOVER 标 SOP_VERSION: v3.2 + RISK + depends_on |
| **4 → 5** | 协调智能体 integration 拉好 (3007/3018 ready) |
| **5 → 6** | Agent 在 integration 真实 E2E PASS, 标 E2E: PASS in HANDOVER |
| **6 → 完成** | 协调智能体 cherry-pick + 重启 + 主 3006/3011 真实 E2E PASS, 标 STATUS: DEPLOYED |

---

## 5. 关键澄清: 谁在哪跑 E2E? (PM 提案)

| 环境 | 谁跑 E2E | 步骤 | 触发 |
|------|----------|------|------|
| **worktree 30XX** | Agent | 单元测试 (无 HTTP, 纯 Python) | 阶段 2 退出前 |
| **integration 3007/3018** | **Agent** (3 步) | 5a. 单跑 A 验证自己 fix<br>5b. 同时跑 (A+B) 验证兼容性 (回归)<br>5c. 标 E2E: PASS in HANDOVER | 阶段 5 |
| **主 3006/3011** | **协调智能体** (统一验证) | 真实 E2E on 3006/3011 | 阶段 6f |

**PM 提案 vs v3.2 实际**:
- ✅ PM 提案 "Agent 跑 E2E 验证兼容性" — v3.2 阶段 5A-b/5B-b 实现
- ✅ PM 提案 "协调智能体统一验证" — v3.2 阶段 6f 实现
- ⚠️ PM 提案 "Agent 各自 cherry-pick 到 integration" — v3.2 仍由协调智能体集中拉 (避免 SHA 不一致). 如 PM 坚持, 见 §10-R14.

---

## 6. 风险等级 (v3.2 仍保留, 但 integration 启用后含义变化)

| 等级 | 触发条件 | 流程 |
|------|----------|------|
| **LOW** | 文案 / UI / 显示 / 字段映射 | worktree 单测 + integration E2E + cherry-pick + 主 3006 E2E |
| **MEDIUM** | API 行为变更 / 跨对象 | 同上, 协调智能体加强 review |
| **HIGH** | DB schema / 鉴权 / 性能 | 同上, 协调智能体必 review dry-run + 必 ALTER |
| **URGENT** | 生产事故 | 立即 cherry-pick, 跳过 integration, 直接 3006 |

**v3.2 关键变化**: LOW/MEDIUM 仍走 integration (为了并行兼容), **不是直接上 3006**!

---

## 7. 并行策略 v3.2 (PM 决策点)

| 场景 | PM 策略 | 流程 |
|------|--------|------|
| **2 个 BUG 同一文件** | **串行** (避免冲突) | 强制串行, BUG-A 跑完 1-6 阶段才接 BUG-B |
| **2 个 BUG 不同文件, LOW** | **可并行** | 协调智能体批量 cherry-pick, 1 次 3006 重启 |
| **2 个 BUG 不同文件, HIGH** | **可并行** (但有 ALTER 顺序) | 协调智能体按依赖拓扑序 ALTER |
| **2 个 BUG 互相依赖** | **串行** (A 必须先 DEPLOYED) | HANDOVER 标 `depends_on: V###` |
| **3+ BUG 并行** | **PM 严格 review** (避免一次性太多) | 协调智能体建议拆批 |
| **紧急 URGENT** | **立即 cherry-pick** | 跳过 integration, 直接 3006 |

---

## 8. 试跑期 KPI 监控 v3.2 (同 v3.1, 加并行指标)

### 8.1 指标 1: 用户感知 (关键, 触发升级)

| 指标 | 阈值 (任一触发升 v3.3) | 测量 |
|------|------------------------|------|
| **3006 重启报错率** | > 5% | 协调智能体看 waitress stderr 5xx |
| **cherry-pick 后 3006 即时失败** | > 0 次/3 BUG | 协调智能体立刻 E2E |
| **用户报告 3006 出问题** | > 1 次/周 | PM 数 |

### 8.2 指标 2: Agent 行为 (违规, 触发升级)

| 指标 | 阈值 | 测量 |
|------|------|------|
| **Agent 直接动 release DB** | > 0 | 协调智能体 HANDOVER 标 `RELEASE_DB_VIOLATION` |
| **Agent 误用 3006/3011 验证** | > 0 | 协调智能体监控 access log |
| **Agent 改坏需要 git revert** | > 0 / 5 BUG | 协调智能体 git revert 数 |

### 8.3 指标 3: 时间效率 (期望 v3.2 应优于 v3.1)

| 指标 | 期望 | 测量 |
|------|------|------|
| **BUG 报告 → 用户看到** (单 BUG) | < 30 分钟 (LOW) | HANDOVER 时间 |
| **2 BUG 并行总耗时** | < 单 BUG 2 倍 (理想 1.5x) | 比 v3.1 串行省时 |
| **协调智能体阶段 4-6 耗时** (批量 cherry-pick) | < 10 分钟 (2 BUG 一起) | cherry-pick + 重启 + E2E |
| **3006 总断连时间** | < 60s/周 (1 次批量重启) | 累加 |

### 8.4 指标 4: 并行特定 (v3.2 新)

| 指标 | 期望 | 测量 |
|------|------|------|
| **integration 验证发现冲突率** | < 10% (10 个 BUG 1 个有冲突) | Agent 标 E2E 失败的次数 |
| **协调智能体批量 cherry-pick 频率** | > 50% (避免单 cherry-pick) | 协调智能体统计 |
| **并行 BUG 实际节省时间** | > 30% | 总耗时 / (单 BUG 平均耗时) |

### 8.5 KPI 记录位置

每个 BUG 跑完, 协调智能体在 HANDOVER 末尾追加 §11:

```markdown
## 11. v3.2 试跑期 KPI (本次 BUG)
- 3006 重启报错率: 0/3 = 0% ✅
- cherry-pick 后即时 E2E: PASS ✅
- 用户报告: 0
- Agent 违规: 0
- 协调智能体阶段 6 耗时: 8 分钟 (批量 2 BUG)
- 3006 断连时间: 35s
- integration 验证: PASS (无冲突) ✅
- 并行 BUG: 1 (本 BUG 与 V### 并行)
```

---

## 9. 试跑退出决策树 v3.2

```
5 个 BUG 跑完 (或 2 周到)
    │
    ├── 指标 1 (用户感知) 触发 ──────────► 🚨 升级 v3.3 (加并行限制)
    │
    ├── 指标 2 (Agent 行为) 触发 ────────► 🚨 升级 v3.3 (加严)
    │
    ├── 指标 4 (并行冲突) > 30% ─────────► 🚨 升 v3.1 (回到串行) 或 v3.3 (加严)
    │
    ├── 指标 3 (时间) 优于 v3.1 ─────────► ✅ v3.2 升为正式 SOP
    │
    └── 综合: 0 红旗 + 时间好 ───────────► ✅ v3.2 升为正式
```

---

## 10. 已知风险 + 对策 v3.2 (12 风险 + 2 新)

| 风险 | 对策 |
|------|------|
| **R1-R12** (同 v3.1) | (略) |
| **R13. (v3.2 新) 并行 BUG 集成冲突** | integration 3007/3018 验证发现, Agent 阶段 5 标 E2E: FAIL 协调智能体 reject |
| **R14. (v3.2 新) 协调智能体 integration 没拉最新** | 协调智能体阶段 4 必跑 `git fetch + reset --hard`, 验证 SHA 一致 |

---

## 11. 决策点 v3.2

| # | 决策 | PM 答 | 写入 |
|---|------|-------|------|
| D1-D15 | (同 v3.1) | (略) | (略) |
| D16 | 试跑期长度 | 5 BUG 或 2 周 | §1 |
| D17 | KPI 监控 | 4 类 12 个指标 (含并行特定) | §8 |
| D18 | 试跑退出条件 | 3 个红旗 | §9 |
| **D19 (v3.2 新)** | **并行策略** | **PM 决策 (默认允 1-2 个)** | §7 |
| **D20 (v3.2 新)** | **integration 状态** | **常开 (3007/3018 长期运行)** | §1 |
| **D21 (v3.2 新, PM 答)** | **Agent 自治 vs 协调智能体集中** | **Agent 自治 (按 PM 提案, 简单试跑)** | §3 阶段 4A/4B |

---

## 12. 命令清单 v3.2 (新增 integration, Agent 自治版)

### 协调智能体阶段 4 命令 (只启 integration, 不拉代码)

```bash
# 阶段 4a: 启 integration worktree + 3007/3018
cd D:\filework\worktrees/integration
git fetch origin   # 拉所有分支
# (Agent 阶段 4A 各自 cherry-pick)

# 阶段 4b: 启动 integration 服务
Start-Process node.exe -ArgumentList "npx vite preview --port 3007" -WorkingDirectory "D:\filework\worktrees/integration\frontend" -PassThru
Start-Process python.exe -ArgumentList "waitress_server.py --port 3018" -WorkingDirectory "D:\filework\worktrees/integration" -PassThru

# 阶段 4c: 拷贝 release DB → integration DB
cp D:\filework\worktrees/release-prep\meta\architecture.db D:\filework\worktrees/integration\meta\architecture.db

# 阶段 4d: 通知 Agent: integration ready
echo "V### integration ready at http://localhost:3007 (Agent 自治 cherry-pick)" >> D:\filework\excel-to-diagram\DEPLOY_HANDOVER_BUG_V###.md
```

### Agent 阶段 4A/4B 命令 (自治 cherry-pick)

```bash
# Agent 阶段 4A: 自治 cherry-pick 到 integration
cd D:\filework\worktrees/integration
git fetch origin feat/annotation-category-filter
git checkout -b integration-tmp origin/feat/annotation-category-filter
git cherry-pick <feat-sha-A>
# 记录 INTEGRATION_SHA
$sha = git rev-parse HEAD
echo "INTEGRATION_SHA-A: $sha" >> D:\filework\excel-to-diagram\DEPLOY_HANDOVER_BUG_V###.md
# 重启 integration 3007/3018 (拉新代码)
# 协调智能体常开的话, 不用重启. 如果冲突, Agent 协调智能体 sync
```

### Agent 阶段 5 命令 (3 步 E2E)

```bash
# 阶段 5A-a: 单跑自己 fix
$base = "http://localhost:3007"
# 跑 V### 的 happy path
# PASS → 5A-b
# FAIL → 标 E2E: FAIL, 阶段回退

# 阶段 5A-b: 同时跑 (A+B) 验证兼容性 (回归)
# 跑 A 和 B 一起的 happy path
# 验证 V### + 并行的 BUG 没冲突
# PASS → 5A-c
# FAIL → 标 E2E: FAIL, 协调智能体 阶段 6 reject

# 阶段 5A-c: 标 E2E: PASS
# 在 HANDOVER 标 E2E: PASS in HANDOVER-A
echo "E2E: PASS (5A-a 单独, 5A-b 兼容)" >> D:\filework\excel-to-diagram\DEPLOY_HANDOVER_BUG_V###.md
```

### 协调智能体阶段 6 (批量 cherry-pick, SHA review)

```bash
# 阶段 6a: review 2 个 HANDOVER 的 INTEGRATION_SHA
# 简单: 协调智能体 不强制 review SHA 一致, 相信 Agent 自治
# (后续如需要可加严, 见 R14)

# 阶段 6b: 批量 cherry-pick (按 depends_on 拓扑序)
cd D:\filework\worktrees/release-prep
git cherry-pick <feat-sha-A> <feat-sha-B> ...   # 一次多个

# 阶段 6c: 批量 restart
npm run build
Start-Process node.exe ... vite preview --port 3006
Start-Process python.exe ... waitress_server.py

# 阶段 6d: 真实 E2E on 3006/3011 (协调智能体, 跑 2 BUG)
# 跑批量 2-3 个 BUG 的 E2E, 都 PASS 才标 DEPLOYED
```

---

## 13. v3.2 vs v3.1 总结

| 维度 | v3.1 | v3.2 |
|------|------|------|
| integration | 0 (LOW/MEDIUM) | **1 (常开)** |
| 多 Agent 并行 | 禁 | **允 (PM 决策)** |
| 协调智能体工作 | 5 阶段 | **6 阶段 (含 integration 维护)** |
| 资源 | 主 3006/3011 | 主 + integration 3007/3018 |
| HANDOVER 字段 | 14 | **15** (+ 并行 BUG 列表) |
| KPI 指标 | 3 类 9 个 | **4 类 12 个** (+ 并行特定) |
| 决策点 | D1-D18 | **D1-D20** (+ D19-D20) |
| 风险表 | R1-R12 | **R1-R14** (+ R13-R14 并行) |

---

## 14. v3.2 实际使用 (PM 提案精确化, 并行试跑期 V050+V051)

按 v3.2 跑 V050 + V051 (并行, 假设都 LOW 风险, 不同文件):

### 阶段 1: PM 分配
PM 同时分配 V050 + V051, 标 `SOP_VERSION: v3.2, RISK: LOW`, 决定并行.

### 阶段 2: 2 Agent **各跑各的 worktree** (PM 提案 #1)
- Agent A → worktree-V050, 改代码, 单测 PASS
- Agent B → worktree-V051, 改代码, 单测 PASS
- **并行做** (PM 决策)

### 阶段 3: 各自 commit + push
- Agent A commit + push + HANDOVER-V050
- Agent B commit + push + HANDOVER-V051

### 阶段 4: 协调智能体准备 integration (集中式, 避免 SHA 不一致)
- 协调智能体从 feat 拉 V050 + V051 进 integration worktree
- 启动 integration 3007/3018
- 拷贝 release DB → integration DB
- 通知 Agent: integration ready at 3007/3018

### 阶段 5: Agent **看到彼此代码**, 跑 E2E 验证兼容性 (PM 提案 #3)
- Agent A 在 integration (3007/3018) 跑 3 步:
  - 5A-a. 单跑 V050 验证自己 fix OK
  - 5A-b. 同时跑 (V050 + V051) 验证兼容性 (回归)
  - 5A-c. 标 E2E: PASS in HANDOVER-V050
- Agent B 在 integration (3007/3018) 跑 3 步:
  - 5B-a. 单跑 V051 验证自己 fix OK
  - 5B-b. 同时跑 (V050 + V051) 验证兼容性 (回归)
  - 5B-c. 标 E2E: PASS in HANDOVER-V051

### 阶段 6: 协调智能体**批量 cherry-pick + 1 次重启 + 统一验证** (PM 提案 #4+#5)
- 6a. PM 决策: 一起 cherry-pick V050 + V051
- 6b. 协调智能体批量 cherry-pick (按 depends_on 拓扑序)
- 6c. (后端) restart 3011
- 6d. (前端) npm run build + restart 3006
- 6e. (DB) ALTER (HIGH 风险, V050/V051 都 LOW 则跳过)
- 6f. **真实 E2E on 3006/3011 (协调智能体统一跑)** — 跑 2 个 BUG 的 E2E
- 6g. 标 HANDOVER-V050 和 HANDOVER-V051 均为 DEPLOYED
- 6h. 协调智能体填 §11 KPI 字段

### 关键 KPI 对比

| 维度 | v3.1 串行 | v3.2 并行 (PM 提案) |
|------|-----------|---------------------|
| 3006 重启次数 | 2 次 (V050 1次 + V051 1次) | **1 次 (批量)** |
| 3006 总断连时间 | ~60-120s | **~30-60s** (减半) |
| Agent 验证环境 | worktree 单测 | worktree 单测 + integration 真实 E2E |
| 兼容性测试 | 0 (无 integration) | **回归 (V050+V051 同时跑)** |
| 协调智能体阶段 6 耗时 | ~10 分钟 (2 次) | ~8 分钟 (1 次批量) |

---

**撰写完成时间**: 2026-07-04 10:30
**版本**: v3.2 (并行试跑期 TRIAL_RUNNING_PARALLEL)
**PM 已确认**: D1-D18 (v1-v3.1 累计) + **D19 (并行策略)** + D20 (integration 常开)
**待 PM 启动试跑**: 下 2 个 BUG (例 V050 + V051) 启动并行试跑
**待 PM 复盘**: 5 BUG 跑完或 2 周到时, 召集复盘

---

## 附录: v3.0/v3.1/v3.2 演进路径

| 版本 | 状态 | 关键特性 | 何时用 |
|------|------|----------|--------|
| v3.0 | (历史) | 5/6 阶段 + 风险等级 | 不再使用 |
| v3.1 | (试跑 1) | 串行, 0 integration, KPI 监控 | (已 pass, 试跑基本流程) |
| **v3.2** | **TRIAL_RUNNING_PARALLEL** | **并行, integration 常开, 4 类 KPI, PM 提案精确化** | **当前试跑并行能力** |
| v3.3 (未来) | 待 PM 复盘决策 | (待 5 BUG 跑完后定) | (待 PM 决策) |

---

## 附录: v3.2 关键设计决策来源

| 决策 | 来源 | 文档位置 |
|------|------|----------|
| **2 Agent 各跑 worktree** | PM 提案 #1 | §3 阶段 2A/2B |
| **Agent 看到彼此代码跑 E2E 验证兼容性** | PM 提案 #3 | §3 阶段 5A-b/5B-b |
| **协调智能体批量 cherry-pick + 1 次重启** | PM 提案 #4 | §3 阶段 6b/c/d |
| **协调智能体统一验证 3006/3011** | PM 提案 #5 | §3 阶段 6f + §5 |
| **Agent 永不在 3006/3011 跑 E2E** | v3.1 铁律 | §5 + §10 |
| **integration 30XX 共享 (3007/3018)** | v3.2 默认 (vs 各 Agent 独立端口) | §1 + §2 |
| **integration 集中拉 (vs Agent 各自 cherry-pick)** | v3.2 安全网 (vs PM 提案 #2 差异) | §3 阶段 4 |
| **风险等级** | v3.0 已设计 | §6 |
| **试跑期 5 BUG / 2 周** | v3.1 已设计 | §1 + §9 |
