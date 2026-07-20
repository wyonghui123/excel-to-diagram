# AGENT_INFRA_DETAILED.md — AGENT_INFRA 扩展详细文档

> **这是 AGENT_INFRA.md 的扩展文档 (原 §0.9-§7)。**
> **5 分钟入口见 [AGENT_INFRA.md](AGENT_INFRA.md)。**
> **Agent 启动时无需读此文件**, 仅在需要深入某个主题时查阅.

---

## 0.9. 基础设施清单 SOP (V007.86h 新增)  [!] 必读

> **重要**: Dev Agent 是基础设施的一部分 (V007.86f 用户提问). 每次 Agent 启动 / 接手任务,
> **必读** `infra_manifest.json`, 知道"基础设施 = N 个组件" + 每个组件的 script / 任务名 / 日志路径.
> 不读 manifest = Agent 失忆 (V007.76 教训) + 不知道哪些组件该管.

### 0.9.1 infra_manifest.json 是什么 (Layer 4)

**位置**: `D:\filework\worktrees\release-prep\infra_manifest.json`

**作用**:
- 列所有基础设施组件 (alert_monitor / alert_monitor_health / auto_heal / agent_health)
- 每个组件的: script 路径 / 计划任务名 / 间隔 / 日志 / 状态 / 依赖
- Agent 启动必读, 跟 V007.80 §0.6 身份检查 SOP 配合

**结构**:
```json
{
  "version": "v007.86h",
  "worktree": {"root": "D:\\...", "branch": "release/...", "expected_head_at_v007.86h": "a6e2bcc"},
  "components": {
    "alert_monitor": {
      "script": "tools/alert_monitor_v0760.py",
      "task_name": "\\yonaa_alert_monitor",
      "interval_sec": 300,
      ...
    },
    "alert_monitor_health": {...},
    "auto_heal": {...},
    "agent_health": {...}
  },
  "alerts": {"im_type": "lark_app", ...},
  "remote_services": {"log_service_prod": "172.20.59.7:9101", ...}
}
```

### 0.9.2 check_agent_health.py 是什么 (Layer 3)

**位置**: `tools/check_agent_health.py`

**作用**:
- 5 分钟跑一次 (新计划任务 `\yonaa_agent_health`)
- 检查 Agent 自身健康 (5 项, 失败 -> 飞书告警)

**5 项检查**:
1. **git_clean**: 无未提交改动 > 30 min
2. **git_synced**: 不比 origin 早 > 24h (ahead of origin 是正常的, behind 才异常)
3. **plan_tasks_healthy**: 4 个 yonaa_* 计划任务都 exit 0/1 (或 267011 = 没跑过)
4. **manifest_in_sync**: infra_manifest.json 里的 script 路径都存在
5. **agent_identity**: V007.80 §0.6 身份检查 (worktree 存在 + HEAD SHA 有效 + 最近 3 commits)

### 0.9.3 Agent 启动 SOP (V007.86h 强制)

**Agent 启动 / 接手任务** 必跑 3 步:

```bash
# 1. 读 manifest
cat infra_manifest.json | head -50

# 2. 验证 worktree 跟 manifest 一致
git -C <worktree> rev-parse HEAD   # 应该等于 manifest.worktree.expected_head_at_v007.86h
git -C <worktree> branch --show-current   # 应该等于 manifest.worktree.branch

# 3. 跑 agent_health 检查
py tools/check_agent_health.py --no-alert
# 期望: 5 项全 OK
```

**异常处理**:
- HEAD 不对 -> 拉最新 (`git pull --rebase`)
- 5 项 FAIL -> 飞书查告警 / 修 component
- worktree 错 -> 切到 manifest.worktree.root

### 0.9.4 V007.86h 4 个计划任务 (V007.86e style, 无 cmd 弹窗)

| 任务 | 用途 | 间隔 | 跑的命令 |
|------|------|------|----------|
| `\yonaa_alert_monitor` | 远程服务监控 | 5 min | pythonw.exe alert_monitor_v0760.py --check-now |
| `\yonaa_alert_monitor_health` | 心跳检查 (Layer 1) | 5 min | pythonw.exe check_alert_monitor_health.py --no-alert |
| `\yonaa_auto_heal` | 任务自愈 (Layer 2) | 5 min | pythonw.exe auto_heal_scheduler.py --no-alert |
| `\yonaa_agent_health` | Agent 健康 (Layer 3) | 5 min | pythonw.exe check_agent_health.py --no-alert |

**每个任务都用 V007.86e style (pythonw.exe direct, no .bat wrapper, no cmd window popup)**.

### 0.9.5 V007.86h 跟 V007.86 治理的完整链路

| 阶段 | 版本 | 治的对象 | 链路 |
|------|------|----------|------|
| **报告** | V007.83 | 计划任务失败 | 起点 |
| **临时** | V007.86 | daemon 备份 | 临时方案 |
| **修复** | V007.86b/c/d/e | 5 阶段修复 (脚本 + 任务 + 编码 + 弹窗) | 单层 |
| **识别** | V007.86f | "Agent 是基础设施" + 4 个盲点 | meta-level |
| **P0 实施** | V007.86g | Layer 1 (心跳) + Layer 2 (自愈) | 1+2 |
| **P1 实施** | **V007.86h** | **Layer 3 (Agent 健康) + Layer 4 (manifest)** | **3+4 ← 现在** |

### 0.9.6 V007.86h 关键工具 (2 个新 + 1 个新任务)

1. `infra_manifest.json` (Layer 4): 基础设施清单
2. `tools/check_agent_health.py` (Layer 3): Agent 健康检查
3. `\yonaa_agent_health` 计划任务: 5 min 跑一次, 复用 check_agent_health.py

### 0.9.7 V007.86h 教训 (V007.86i+)

1. **infra_manifest.json 必读**: Agent 启动先读, 不知道"基础设施 = N 个组件" = Agent 失忆
2. **plan_tasks_healthy 检查**: 4 个 yonaa_* 任务都要健康, 任一失败 -> 飞书告警
3. **never_run_codes (267011)**: 任务刚创建没跑过的 placeholder, 算正常 (等首次跑)
4. **git_synced 检查**: 比 origin 早 > 24h = push 失败 / 忘记 push, 告警
5. **manifest_in_sync 检查**: script 路径不存在 = manifest 跟实际不同步, 需修

### 0.9.8 V007.86h 待用户操作 (1 分钟)

**创建 yonaa_agent_health 计划任务** (sandbox UAC 被屏蔽, 需用户跑):

```powershell
# 打开管理员 PowerShell
Start-Process "schtasks" "/Create /TN \yonaa_agent_health /XML D:\filework\worktrees\release-prep\tools\_yonaa_agent_health_v00786h.xml /F" -Verb RunAs -Wait
```

**期望**: schtasks /Query /FO LIST 显示 4 个 yonaa_* 任务.

---

## §0.12 状态源优先级与一致性 (v3.3 新增, P1-S4)

### 3 个状态源定义

| 状态源 | 路径 | 用途 | 写入方 |
|-------|------|------|-------|
| **真相源** | `.agent-status.json` 的 `v33_pipeline` | PM 通知 + 流程状态机 | 协调智能体 |
| **事件流** | `.coord/events.jsonl` | Agent 间通知 + 审计 | 所有 Agent + 协调智能体 |
| **操作日志** | `.coord/coordination.log` | 协调智能体操作审计 | 协调智能体 |

### 优先级规则

```
冲突时以 .agent-status.json 的 v33_pipeline 为准

原因:
1. v33_pipeline 是结构化状态 (字段明确)
2. v33_pipeline 有文件锁保护 (save_ports 同款 msvcrt.locking)
3. v33_pipeline 是协调智能体主动写入的 (责任明确)

events.jsonl 和 coordination.log 是 append-only, 用于:
- 通知 (events.jsonl)
- 审计 (coordination.log)
不作为状态判断的依据
```

### 写入同步规则

协调智能体在关键节点必须**同时更新** 3 个源:

| 节点 | v33_pipeline | events.jsonl | coordination.log |
|------|-------------|-------------|-----------------|
| Agent HANDOVER 就绪 | — | `HANDOVER_READY` | — |
| cherry-pick 完成 | `pm_review_pending.pending=true` | `CHERRY_PICKED` | `cherry_pick <bugs>` |
| PM 验证通过 | `deploy_pending.pending=true` + `pm_review_pending.pending=false` | `PM_VERIFIED` | — |
| 部署完成 | `deploy_pending.last_deployed=<ts>` | `DEPLOYED` | `deploy <version>` |
| 冲突检测 | — | `CONFLICT_DETECTED` | `conflict <detail>` |
| 异常恢复 | — | `RECOVERED` | `recover <wt>` |

### PM 查看状态的方式

1. **会话启动时**: 读 `.agent-status.json` 的 `v33_pipeline.pm_review_pending`
2. **准实时**: `_events.py tail` (持续监听新事件)
3. **历史查询**: `_coord_log.py recent` (最近协调操作)
4. **协调智能体报告**: 协调智能体在 PM 会话中口头报告

---

## §0.13 自验证服务保持运行 (v3.3 新增, P1-E2)

### 场景

Agent 自验证完成后, 如果协调智能体即将 cherry-pick, 可以让 Agent 的服务保持运行, 避免协调智能体重启 3006/3011 的 60s 等待。

### 用法

```bash
# 自验证完成后保持服务运行 (不调用 stop)
python scripts/self_verify.py run <wt-name> --keep-running

# 协调智能体 cherry-pick 后, Agent 手动停止服务
python scripts/_wt_service.py stop <wt-name>
```

### 何时用 --keep-running

| 场景 | 是否保持运行 |
|------|-------------|
| Agent 即将提交 HANDOVER, 协调智能体马上 cherry-pick | 是 |
| Agent 还要继续改代码 | 否 |
| Agent 要切换到其他任务 | 否 |
| HIGH 风险变更, 需要 PM 立即验证 | 是 |

### 铁律

- `--keep-running` 的服务必须注册到 `_session_cleanup.py` (防止孤儿)
- 协调智能体 cherry-pick 前必须检查 Agent 服务是否在运行
- 最多保持 30 分钟, 超时由 watchdog 自动清理

---  [!] 必读

> **背景**: PARALLEL_DEV_SOP v3.3 将 Integration 从常开改为按需, Agent 必须在自己 worktree 内完成真实服务自验证.
> **适用**: 所有开发智能体, 在提交 HANDOVER 前必须完成.
> **工具**: `_wt_service.py` (启停服务) + `self_verify.py` (自动化冒烟)

### 0.10.1 5 步自验证 SOP (强制)

```bash
# 每次 BUG 修复完成后, HANDOVER 前必跑 (5 步, 5 分钟内)

# Step 1: 启后端 (分配端口, 从 ports.json 自动读取)
python scripts/_wt_service.py start-be <wt-name>

# Step 2: 启前端 (如有前端改动)
python scripts/_wt_service.py start-fe <wt-name>

# Step 3: 跑冒烟测试
python scripts/self_verify.py smoke <wt-name>

# Step 4: 关服务
python scripts/_wt_service.py stop <wt-name>

# Step 5: 生成 SELF_VERIFY_RESULTS
python scripts/self_verify.py report <wt-name>
```

### 0.10.2 一键自验证 (替代 5 步)

```bash
# 自动: 启服务 → 冒烟 → 关服务 → 输出报告
python scripts/self_verify.py run <wt-name>
```

### 0.10.3 自验证退出条件

| 条件 | 必须 |
|------|------|
| 后端 /api/v1/health 返回 200 | **是** |
| BUG 相关 API 返回正确结果 | **是** |
| 前端页面可访问 (如有前端改动) | **是** |
| 单元测试 PASS (如有相关测试) | 建议 |
| **SELF_VERIFY_RESULTS 已生成** | **是** |

**无 SELF_VERIFY_RESULTS 的 HANDOVER = 无效, 协调智能体拒绝.**

### 0.10.4 自验证环境参数

| 项 | 来源 | 默认 |
|----|------|------|
| 后端端口 | `ports.json` allocated.backend_port | 按 owner 匹配 |
| 前端端口 | `ports.json` allocated.frontend_port | backend_port - 4 |
| DB | worktree 自己的 `meta/architecture.db` | 已有 |
| 启动超时 | `paths.json` self_verify.backend_startup_timeout | 60s |

### 0.10.5 自验证失败处理

| 失败 | 行动 |
|------|------|
| 后端启动失败 | 检查端口是否被占, 检查 waitress_server.py 日志 |
| API 返回非 200 | 检查代码逻辑, 修复后重跑 |
| 前端启动失败 | 检查 VITE_PORT 是否被占, 检查 npm install |
| 无法生成 SELF_VERIFY_RESULTS | 检查 self_verify.py 是否存在 |

---

## 0.11. Integration 按需决策 (v3.3 新增)

> **v3.3 核心变更**: Integration 不再常开, 仅在特定条件下按需启用.
> **默认**: 不需要 Integration — Agent 自验证 + PM 验证即可.

### 0.11.1 Integration 启用条件 (满足任一即启用)

| # | 条件 | 原因 |
|---|------|------|
| 1 | 2+ Agent 修改同一模块的不同文件 | 跨 Agent 兼容性风险 |
| 2 | 1 Agent 修改了共享 API 接口 (其他 Agent 依赖) | 接口变更影响 |
| 3 | 3+ Agent 同时提交 HANDOVER | 批量合并风险 |
| 4 | PM 人工判断需要 | 安全网 |

### 0.11.2 Integration 不需要的场景 (默认)

- Agent 修复独立模块的 BUG (不同文件, 不同模块)
- Agent 之间无代码依赖
- PM 分配时明确标注"无需 Integration"

### 0.11.3 Integration 启停命令 (按需)

```bash
# 启 Integration (协调智能体, 仅在需要时)
python scripts/_wt_service.py start-be integration
python scripts/_wt_service.py start-fe integration

# Agent 在 Integration 跑 E2E (同 v3.2 阶段 5)
# ...

# 关 Integration
python scripts/_wt_service.py stop integration
```

### 0.11.4 PM 分配 BUG 时的决策

```
PM 分配 BUG:
  │
  ├── Q1: 这个 BUG 与其他 Agent 的 BUG 是否碰同一模块
  │   ├── YES → 需要 Integration
  │   └── NO → 不需要 (默认)
  │
  └── Q2: 是否改了共享 API 接口
      ├── YES → 需要 Integration
      └── NO → 不需要
```

---

## 1. Agent 必知 (3 分钟读完)

### 1.1 5 个最常用工具 (直接调, 不需 SSH)

```python
import sys; sys.path.insert(0, 'tools')
from yonaa_exec import yexec, yupload, yuploaderun
from remote_capability_probe import main as probe  # 30s 扫
```

| 工具 | 一句话 | 何时用 |
|------|--------|--------|
| `remote_capability_probe.py` | 30s 扫 5 端口 × 6 secret | 第一次接入 / 排查网络 |
| `yonaa_exec.yexec(cmd, port, secret)` | 远端跑一条命令 | 90% 任务 |
| `yonaa_exec.yupload(local, remote, port)` | 上传文件 | 部署 / 改远端文件 |
| `yonaa_exec.yuploaderun(local, remote)` | 上传+执行+清理 | 跑一次性脚本 |
| `staging_deploy_orchestrator.py` | 一键 staging 部署 | 部署 staging |

### 1.2 7 个端口 (背下来)

```
9200   prod core_service     (exec + upload, secret=v007.52-core-write)
19200  staging core_service  (exec + upload, secret=v007.52-core-write, 同上)
9201   observability         (4 端点, 无 exec, secret=v007.35-infra)
9101   prod log_service      (10+ 端点, secret=v007.35-infra)
19101  staging log_service   (10+ 端点, secret=v007.35-infra)
8081   frontend (v4 unified) (用户)
3011   backend (HTTP)        (用户)
```

### 1.3 5 条核心命令 (复制粘贴就跑)

```bash
# 1. 第一次接入, 30s 验证能连
python tools/remote_capability_probe.py

# 2. 看 prod 当前状态 (含 regression 告警)
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py --check-regression" 9200

# 3. 看 prod 部署历史
python tools/yonaa_exec.py exec "ls -la /opt/app/deployments/" 9200

# 4. 跑 migration 状态
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner --status" 9200

# 5. 跑 lint (本地)
python tools/migration_lint.py
```

### 1.4 [V007.55] 回归测试 (staging chaos 演练)

```bash
# staging 跑全部 9 个 sqlite io error 场景
python tools/yonaa_exec.py exec "python3 tools/regression_test_suite.py" 19200
# 期望: 7 PASS / 0 FAIL / 2 SKIP / 9 total (R1 R9 root 防护 SKIP)

# 跑单个场景
python tools/yonaa_exec.py exec "python3 tools/regression_test_suite.py --scenario R5" 19200

# 集成到 monitor (alert-friendly)
python tools/yonaa_exec.py exec "python3 tools/monitor_migrations.py --check-regression" 19200
# 退出码 0=OK / 1=FAIL / 2=WARN

# 详见: docs/REGRESSION_TEST_SUITE.md
```

### 1.5 [V007.58~V007.63] 监控速查 (5 min 看完)

> **Agent 接手新需求前先看这**: 监控在哪、9 项怎么跑、收不到心跳怎么办

- **架构**: yonaa (9200) 上 9 项检查 + 用户异常 (backend_err / core_service_err) + 每 30min 心跳
- **log_service 9+ 业务端点**: 9101 `/api/db/health` `/api/db/can_write` `/api/disk/check` `/api/disk/errors` `/api/disk/journal_err` ...
- **手动查**: `python tools/alert_monitor_v0760.py --check-now --config tools/alert_monitor_config.json`
- **日志**: `tools/alert_monitor_v0760.log` (追加写, 任务调度每 5min)
- **任务计划**: `schtasks /Query /TN "\yonaa_alert_monitor" /V /FO LIST` (Hidden + pythonw.exe, 无弹窗)
- **心跳**: 30min 间隔, `[HEARTBEAT] lark_app: OK` 飞书, 蓝色卡片, 不 @ 全体
- **告警**: 5min 触发 (聚合去重 5min), 红色卡片, @ 全体
- **凭证**: 飞书 app secret 在 HKCU `HKCU:\Software\wyonghui_lark_app` (reg query), env 兜底

**速查首选**: [MONITORING_QUICK_REFERENCE.md](file:///d:/filework/worktrees/release-prep/docs/MONITORING_QUICK_REFERENCE.md)
**配置细节**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_ALERT_SETUP.md)
**应急处理**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9

### 1.6 1 个公式: Token

```python
import hashlib, time
token = hashlib.sha256(f"v007.52-core-write:{int(time.time())//3600}".encode()).hexdigest()[:16]
```
(9201 用 `v007.35-infra`)

---

## 2. 完整文档树

```
DEPLOY_INFRASTRUCTURE.md        # ← 主入口 (总览 + 流程)
├─ §0  一图全貌                # 1分钟架构图
├─ §1  能力清单 (18 工具)        # 找工具
├─ §2  Agent 远端操作           # 5 个函数
├─ §3  部署流程                 # 3 种方式
├─ §4  回滚/监控/测试
├─ §5  路径/端口/备份
├─ §6  AI Agent 部署规范
└─ §7  版本历史

docs/
├── AGENT_INFRA.md              # ← 本文件 (5分钟速查)
├── MIGRATION_GUIDE.md          # ← migration 实战 (待建)
├── MIGRATION_SPEC.md           # 1711 行 design spec (历史 design 保留)
├── STAGING_GUIDE.md            # staging 流程 (待重写)
├── DEPLOYMENT_STANDARDS.md     # 编码/部署规范
├── INDEX.md                    # docs 完整索引 (待建)
├── ... (其他业务 spec, 150+)
```

---

## 3. 关键事实 (2026-07-16 当前)

| 项 | 状态 |
|---|------|
| **prod DB** | 18 migration SUCCESS, **0 FAILED** ✅ |
| **staging DB** | 18 migration SUCCESS, **0 FAILED** ✅ |
| **migration lint** | **0 FAIL**, 8 WARN, exit 0 ✅ |
| **migration runner** | idempotent (重复列自动跳过) ✅ |
| **9101/19101 log_service** | **alive (10+ 端点, V007.55 systemd 守护 + V007.57 nobody 用户, 进程死后 5s 自动重启, HIPS 不杀)** ✅ |
| **IM 告警链路** | **V007.61 alert_monitor_v0760.py + 飞书应用机器人 API + Windows Task Scheduler, 9 项分层监控每 5min 轮询 → 飞书 HAO 群, 推送成功 ✓** ✅ |
| **本会话 commit 数** | V007.55-V007.61 (基础设施 7 步 + 9 项监控 + 飞书集成) |

---

## 4. 告警与监控 (V007.58 ~ V007.63, 2026-07-16)

**架构一句话**: yonaa (air-gapped) ←(每 5min 轮询)← 这台 Windows PC → 飞书 HAO 群

**9 项分层监控** + log_service 9+ 业务端点 + 告警/心跳消息样例 + 全部运维命令 — 详见:

> 📖 **[docs/MONITORING_QUICK_REFERENCE.md](file:///d:/filework/worktrees/release-prep/docs/MONITORING_QUICK_REFERENCE.md)** (V007.58~V007.63 完整版, 日常运维速查)

- **告警配置**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_ALERT_SETUP.md) (V007.58~V007.63 升级摘要 + 飞书 App Bot 申请 7 步)
- **事故响应**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/worktrees/release-prep/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9 (log_service 死了 / OOM / 磁盘满 怎么处理 + 告警项→应急处理对照)
- **运维命令**: [OPS_MANUAL.md](file:///d:/filework/worktrees/release-prep/docs/OPS_MANUAL.md) §十一 (告警与监控 + 故障排查速查)

**30 秒速记**:
- 飞书收到红色卡片 + @全体 = **告警** → 查 §9.5 告警项→应急处理对照
- 飞书收到蓝色卡片 = **恢复** 或 **心跳 (每 30min 一次)**
- 什么消息都没收到 = 监控自己挂了 (盲区) → 查 `alert_monitor_v0760.log`

---

## 5. deploy_bundle/ 是什么 (V045 起的发布物目录, 57 commits)

### 5.0 一句话价值 (回答你之前的问题)

> **deploy_bundle 是"每个发版时的发布物快照", git 管的是"时光机"**: 让你 1 年后能 `git checkout <老 commit>` 拿回**当时**的 deploy.sh + 当时打包的 zip, 重新跑一次"那一版的部署"。

**为什么不只 git 管代码就够**? 因为**代码会变, 但"当时发布的包"不能变**:
- 今天: `meta/server.py` 50077 bytes, md5=`2e2841b7...`
- 明天改了 bug: `meta/server.py` 50100 bytes, md5=`abc...`
- **1 年后想"再跑一次今天的部署"?** 代码 HEAD 早变了, 拿不回今天这一版

`deploy_bundle/` 把"**今天发版用的全套**" 冻进 git: 当天的 deploy.sh + 当天的 zip + 当天的 MANIFEST + 当天的脚本。

### 5.1 文件清单 (10 项)

| 文件 | 角色 | 是源代码 | git 跟踪 |
|------|------|------|------|
| `deploy.sh` | 部署入口 (含 precheck + smoke) | ✅ 是 | ✅ 必须 |
| `precheck.sh` | 部署前 7 项检查 | ✅ 是 | ✅ 必须 |
| `smoke_test.sh` | 部署后 5 项真实功能测试 | ✅ 是 | ✅ 必须 |
| `rollback.sh` | 通用回滚 | ✅ 是 | ✅ 必须 |
| `diagnose.sh` | 部署后诊断 | ✅ 是 | ✅ 必须 |
| `unified_server.py` | 远端统一服务入口 | ✅ 是 | ✅ 必须 |
| `lib/common.sh` | shell 共享库 | ✅ 是 | ✅ 必须 |
| `README.txt` | 部署工作流文档 | ✅ 是 | ✅ 必须 |
| `deploy-v2026xxxx_xxx.zip` | **本次发布的代码快照 (zip ~30MB)** | ❌ 是构建产物 | ⚠️ 应该 `.gitignore` + git-lfs (但当前是入 git 的) |
| `meta/ tools/ docs/ scripts/` (zip 内) | 源码副本 | ✅ 但**跟根目录重复** | ⚠️ 重复了, 用 rebuild_zip.py 自动同步 |

### 5.2 5 个 git 管理的实际价值

| 价值 | 解释 | 重要度 |
|------|------|--------|
| **1. 历史版本可回滚** | yonaa 上 7 个版本目录 (`v20260630_003` ~ `v20260712_001`) 保留 9 天; 仓库有 57 commits, **可 `git checkout <老 commit>` 拿回历史 deploy_bundle** 拖回去 | ⭐⭐⭐ 核心 |
| **2. 部署脚本单一可信源** | 改 `tools/deploy.sh` → 必须同步 `deploy_bundle/deploy.sh`; git 强制追踪差异 (历史 commit 8bfcbff 证实) | ⭐⭐⭐ 必要 |
| **3. 完整发布包存档** | 每次发版 commit 一次 `chore(release): Vxxx 部署包 vxxx_xxx - 含 Vxxx/Vxxx fix` | ⭐⭐⭐ 核心 |
| **4. 出问题可对账** | yonaa 上某文件 hash 不对, 跟 `git show HEAD:deploy_bundle/deploy-vXXX.zip` 对账 | ⭐⭐ 重要 |
| **5. 部署文档跟代码同步** | `README.txt` 跟 `deploy.sh` 一起入 git | ⭐ 普通 |

### 5.3 怎么用 (V045 起的工作流)

```bash
# 1. MobaXterm SFTP 拖 deploy_bundle/ 到远端 /tmp/
# 2. 在远端跑:
bash /tmp/deploy_bundle/deploy.sh --version v20260707_002 --port 5001
# 3. 出问题:
bash /tmp/deploy_bundle/rollback.sh --to <v> --port <p>
```

### 5.4 源码 vs 发布物的边界

```
仓库根 (源):                       deploy_bundle/ (发布物):
  tools/deploy.sh     ──────同步──→  deploy.sh         [手动或工具同步]
  tools/precheck.sh   ──────同步──→  precheck.sh
  meta/ tools/ docs/  ────打包──→   deploy-vXXX.zip   [rebuild_zip.py]
  README.md           ──────打包──→  (zip 内 docs/)
```

**核心原则**: 仓库根是 **source of truth**, deploy_bundle/ 是 **build artifact + 部署脚本生产版本**。

### 5.5 历史 (57 commits, V045 至今)

- 起始 commit 28d132f `chore(release): V045 部署包 v20260703_004 - 含 V043/V044 fix` (2026-07-03)
- 每个发版 commit 一次 `chore(release): Vxxx 部署包 vxxx_xxx - 含 Vxxx/Vxxx fix`
- 工具: `tools/rebuild_zip.py` (V007.49-B) 自动同步 meta/ + git HEAD 对账

### 5.6 worktree 上的 600+ 文件 deleted 状态

git HEAD 上 deploy_bundle 是"**只存脚本 + zip**"模式, 但 worktree 实际有 deploy_bundle/meta/.../ 等 600+ 文件 (历史 commit 可能没把源码副本删干净)。

**不要执行 `git reset --hard`** —— 这会丢工作。  
**正确做法**: 暂不动, 跟 V046+ commit 同步后, 用 `git checkout HEAD -- deploy_bundle/` 即可清理。

---

## 6. 实际部署模式 (2026-07-16 当前)

### 6.1 直说答案 (3 句话)

| 问题 | 答案 | 证据 |
|------|------|------|
| **现在有没有采用 delta?** | **形式上没, 体验上部分有** | deploy.sh 仍是 `unzip -o` 全量 (line 229); 但 11 文件 hash 守卫让"非关键改动 5s 走完" |
| **执行上有保障吗** | **部分有, 部分没** | LF 保障 ✅, MANIFEST hash ✅, 11 文件 hash ⚠️ (不覆盖前端), deploy_history 9 天没新记录 ❌ |
| **L17 真 delta?** | **代码写了, 没集成** | smart_extract.sh 在 deploy_bundle/ 不存在; rebuild_zip.py --delta 模式不默认 |

### 6.2 部署流程真相 (拆成 3 步看)

**Step 1: 打包** (`rebuild_zip.py`)
```
python tools/rebuild_zip.py --version v2026xxxx_xxx
# 默认: 生成 30MB 全量 zip
# 加上 --delta --prev-manifest: 生成 KB 级 delta zip (有这能力, 但不用)
```

**Step 2: 传包** (MobaXterm SFTP)
```
MobaXterm 拖 deploy-v2026xxxx_xxx.zip → /tmp/
# 30MB 走 SSH, 即使只需 KB
```

**Step 3: 部署** (`deploy.sh PHASE 0.5`, line 175-224)
```bash
# 11 文件 hash 守卫:
# - 4 server 类 (server.py, datasource.py, sql_adapters.py, sql_connection_pool.py)
# - 7 V007.46+ 新增 (safe_connect.py, db_health_monitor.py, diagnostics.py, ...)

if [ "$NEED_UNZIP" = "true" ]; then
    unzip -o $ZIP_PATH -d $DEPLOYMENTS_DIR/   # 全量解压 (line 229)
fi
# 不一致才解压, 一致就 5s 跳过
```

**真相**: 体验上"平时不传代码", 但**底层仍是 unzip -o 全量能力**, **不是真 delta**。

### 6.3 L17 真 delta 是什么 (V007.67 2 天前接入, 但没成为日常)

```bash
# 真 delta 应该这样:
python tools/rebuild_zip.py --version v2026xxxx_xxx --delta \
    --prev-manifest shared/MANIFEST.prev
# → 生成 zip 只含 "上次以来变了" 的文件 (KB 级)

bash deploy.sh
# → smart_extract.sh: 只覆盖变了文件 (秒级)
# → 99% 部署只动几 KB, 1% 重大重构才触 full
```

**L17 状态**: commit 0b7c540 (V007.67, 2026-07-14) 接入基础施设; smart_extract.sh 在 deploy_bundle/ 找不到; deploy.sh 没调它。

### 6.4 实际执行保障清单

| 保障 | 状态 | 风险 |
|------|------|------|
| **打包 LF 保障** | ✅ rebuild_zip.py line 568-575 `force_lf_in_tree` | 无 |
| **MANIFEST 完整性 hash** | ✅ V007.25 加的 `manifest_sha256` | 无 |
| **远端 11 文件 hash + dist hash 校验** | ✅ deploy.sh 守卫 | 已覆盖 (V007.46 BUG-FIX 7 文件 + V007.25 BUG-FIX dist hash, line 243-263 + 279-287) |
| **deploy_history 记录** | ❌ yonaa 上 9 天没新记录 | **出事故时无审计** |
| **真 delta (KB 级)** | ❌ 未启用 | **每次都传 30MB zip, 即使 1 行改动** |

### 6.5 Agent 决策

| 任务 | 应该用 |
|------|-------|
| **现在发版 (日常)** | `rebuild_zip.py` (全量) + `deploy.sh` (按需解压) |
| **改了 frontend dist_files/ 关键 JS** | deploy.sh PHASE 0.5 else 分支 (line 276-287) 已校验 dist hash, **会触发解压** (V007.25 BUG-FIX 2026-07-04 加的) |
| **L17 真 delta 启用 (V007.68+)** | 等 commit 把 smart_extract.sh 集成到 deploy.sh 后, 用 `--delta --prev-manifest` |

---

**维护**: AGENT 接手时, **5 分钟读本文件 → 30 秒跑 capability_probe → 5 分钟读 DEPLOY_INFRASTRUCTURE §0+§1 → 3 分钟读 [MONITORING_QUICK_REFERENCE.md](file:///d:/filework/worktrees/release-prep/docs/MONITORING_QUICK_REFERENCE.md)** = 完全 ready.

---

## 7. 部署打包智能体专属指南 (v3.3 新增)

> **目标读者**: 部署打包智能体 (deploy agent)
> **工作目录**: `D:/filework/worktrees/release-prep/`
> **核心职责**: 接收协调智能体 cherry-pick → 本地验证 → 打包 → 远端部署 → 监控告警

### 7.1 部署智能体在 v3.3 流程中的位置

```
PM分配 → 开发智能体实现 → 开发智能体自验证 → commit+HANDOVER →
协调智能体cherry-pick → [部署智能体接手] → PM验证 → 部署

                                    ↑ 你在这里
```

**v3.3 关键变化**:
- Integration 不再常开, 部署智能体不需要等 Integration E2E
- 开发智能体已用 `self_verify.py` 完成真实服务自验证
- HANDOVER 必须包含 SELF_VERIFY_RESULTS (否则无效)
- PM_VERIFIED 门控: 无 PM 签字不许部署

### 7.2 部署智能体启动必读 (5 步)

```bash
# Step 1: 身份检查 (§0.6)
echo "=== 1. USER ===" && git -C "$(pwd)" config --get user.name
echo "=== 2. WORKTREE ===" && basename $(pwd)
echo "=== 3. BRANCH ===" && git -C "$(pwd)" branch --show-current

# Step 2: 读 v33_pipeline 状态
cat D:/filework/.agent-status.json | python -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('v33_pipeline',{}), indent=2))"

# Step 3: 读基础设施 manifest
cat infra_manifest.json | head -50

# Step 4: 同步最新脚本到本 worktree
python D:/filework/excel-to-diagram/scripts/_sync_scripts.py sync

# Step 5: 检查远端连通
python tools/remote_capability_probe.py
```

### 7.3 部署智能体工作流 (收到 PM_VERIFIED 后)

```bash
# 1. 确认 PM_VERIFIED
# 检查 .agent-status.json → v33_pipeline.deploy_pending.pm_verified_at 已填

# 2. 本地验证 (cherry-pick 已由协调智能体完成)
python scripts/self_verify.py smoke release-prep
# 或快速检查:
python scripts/self_verify.py quick release-prep

# 3. 打包
python tools/rebuild_zip.py --version v2026xxxx_xxx
# 验证打包质量:
python tools/verify_deploy_bundle.py  # 6/6 PASS 才许上传

# 4. 上传 + 部署
python tools/staging_deploy_orchestrator.py
# 或热修:
DEPLOY_MODE=hotfix python tools/staging_deploy_orchestrator.py

# 5. 部署后验证
python tools/yonaa_exec.py exec "curl -s http://localhost:5001/api/v1/health" 9200
python tools/yonaa_exec.py exec "python3 -m meta.core.migration_runner --status" 9200

# 6. 更新状态
# v33_pipeline.deploy_pending.last_deployed = <timestamp>
# HANDOVER STATUS: DEPLOYED
```

### 7.4 部署智能体工具速查

| 工具 | 位置 | 用途 |
|------|------|------|
| `rebuild_zip.py` | `tools/` | 打包发布 zip |
| `verify_deploy_bundle.py` | `tools/` | 验证打包质量 (6项) |
| `staging_deploy_orchestrator.py` | `tools/` | 一键 staging 部署 |
| `remote_capability_probe.py` | `tools/` | 远端连通检查 |
| `yonaa_exec.py` | `tools/` | 远端执行命令 |
| `_sync_scripts.py` | `scripts/` (主仓库) | 同步最新脚本到本 worktree |
| `self_verify.py` | `scripts/` (同步后) | 本地冒烟验证 |
| `_wt_service.py` | `scripts/` (同步后) | 服务启停 |
| `check_agent_health.py` | `tools/` | Agent 健康检查 |
| `alert_monitor_v0760.py` | `tools/` | 监控告警 |

### 7.5 部署铁律 (5 条)

1. **verify_deploy_bundle 6/6 PASS 才许上传** — CRLF/权限/垃圾/db污染等
2. **无 PM_VERIFIED 不许部署** — 检查 v33_pipeline.deploy_pending.pm_verified_at
3. **部署后必须验证** — health + migration status + 基本功能
4. **部署失败必须告警 PM** — 保持 deploy_pending.pending=true, 不自动重试
5. **脚本修改后必须同步** — `_sync_scripts.py sync` 确保本 worktree 脚本最新

### 7.6 部署智能体与协调智能体的区别

| 维度 | 协调智能体 | 部署打包智能体 |
|------|----------|-------------|
| 主要工作 | cherry-pick + 全局状态同步 | 打包 + 远端部署 + 监控 |
| 工作目录 | 全部 wt (只读) + 协调目录 | release-prep (读写) |
| 能碰的文件 | .agent-status.json, .coord/, 协调脚本 | release-prep 全部 + tools/ |
| 不能碰的 | src/ 业务代码 | 开发智能体的 worktree |
| 触发点 | Agent HANDOVER 就绪 | PM_VERIFIED 签字后 |
