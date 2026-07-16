# AGENT_INFRA.md

> **目标读者**: AI Agent (主入口)
> **最后更新**: 2026-07-16
> **本文件用途**: AI Agent 5 分钟接手本项目, 知道: 这是什么、怎么部署、怎么远端操作、找哪个文档、**怎么监控告警**
> **详细规范**: 见下方 §0 索引

---

## 0. 文档索引 (1 张表)

| 场景 | 文档 | 行数 | 用途 |
|------|------|------|------|
| **总入口** | [DEPLOY_INFRASTRUCTURE.md](file:///d:/filework/release-prep-worktree/DEPLOY_INFRASTRUCTURE.md) | 331 | 7 章节, 18 工具, 7 端口 — **永远先看这** |
| **部署节奏** | [docs/DEPLOY_RHYTHM.md](file:///d:/filework/release-prep-worktree/docs/DEPLOY_RHYTHM.md) | 220 | **daily 21:00 / hotfix 立即** — 何时用哪个 |
| **远端操作速查** | 本文件 §1 | — | 5 个 Python 函数 / 5 行 CLI / **回归测试 §1.4** |
| **回归测试** | [docs/REGRESSION_TEST_SUITE.md](file:///d:/filework/release-prep-worktree/docs/REGRESSION_TEST_SUITE.md) | 250+ | 9 个 sqlite io error 场景 — staging 自动化 |
| **告警与监控** | [docs/INCIDENT_ALERT_SETUP.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_ALERT_SETUP.md) | — | **9 项分层监控 + 飞书告警 (V007.58~V007.61)** |
| **5min 监控速查** | [docs/MONITORING_QUICK_REFERENCE.md](file:///d:/filework/release-prep-worktree/docs/MONITORING_QUICK_REFERENCE.md) | 198 | **Agent 速查首选: 架构 / 9 项 / 端点 / 命令 / 故障排查 (V007.58~V007.63)** |
| **事故响应** | [docs/INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_RESPONSE_RUNBOOK.md) | 7 类事故 | 收到告警后怎么办 (含 V007.61 用户异常) |
| **运维手册** | [docs/OPS_MANUAL.md](file:///d:/filework/release-prep-worktree/docs/OPS_MANUAL.md) | — | 运维日常操作 (含监控章节) |
| **Migration 操作** | [docs/MIGRATION_GUIDE.md](file:///d:/filework/release-prep-worktree/docs/MIGRATION_GUIDE.md) | 200+ | migration 创建/运行/lint 实战 |
| **Migration 设计依据** | [docs/MIGRATION_SPEC.md](file:///d:/filework/release-prep-worktree/docs/MIGRATION_SPEC.md) | 1711 | 完整设计 spec (历史 design, 不必读) |
| **staging 操作** | [docs/STAGING_GUIDE.md](file:///d:/filework/release-prep-worktree/docs/STAGING_GUIDE.md) | 200+ | staging 部署/排错 |
| **部署规范** | [docs/DEPLOYMENT_STANDARDS.md](file:///d:/filework/release-prep-worktree/docs/DEPLOYMENT_STANDARDS.md) | 587 | 编码/部署/审计规范 |
| **完整索引** | [docs/INDEX.md](file:///d:/filework/release-prep-worktree/docs/INDEX.md) | (待建) | 全部 docs/ 分类 |

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

**速查首选**: [MONITORING_QUICK_REFERENCE.md](file:///d:/filework/release-prep-worktree/docs/MONITORING_QUICK_REFERENCE.md)
**配置细节**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_ALERT_SETUP.md)
**应急处理**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9

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

> 📖 **[docs/MONITORING_QUICK_REFERENCE.md](file:///d:/filework/release-prep-worktree/docs/MONITORING_QUICK_REFERENCE.md)** (V007.58~V007.63 完整版, 日常运维速查)

- **告警配置**: [INCIDENT_ALERT_SETUP.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_ALERT_SETUP.md) (V007.58~V007.63 升级摘要 + 飞书 App Bot 申请 7 步)
- **事故响应**: [INCIDENT_RESPONSE_RUNBOOK.md](file:///d:/filework/release-prep-worktree/docs/INCIDENT_RESPONSE_RUNBOOK.md) §9 (log_service 死了 / OOM / 磁盘满 怎么处理 + 告警项→应急处理对照)
- **运维命令**: [OPS_MANUAL.md](file:///d:/filework/release-prep-worktree/docs/OPS_MANUAL.md) §十一 (告警与监控 + 故障排查速查)

**30 秒速记**:
- 飞书收到红色卡片 + @全体 = **告警** → 查 §9.5 告警项→应急处理对照
- 飞书收到蓝色卡片 = **恢复** 或 **心跳 (每 30min 一次)**
- 什么消息都没收到 = 监控自己挂了 (盲区) → 查 `alert_monitor_v0760.log`

---

## 5. deploy_bundle/ 是什么 (V045 起的发布物目录, 57 commits)

**TL;DR**: 这是"部署脚本 + 代码包"打包好的目录, 让你**用 MobaXterm 拖到远端 /tmp/ 直接跑 deploy.sh**。**是发布物, 不是源代码仓库**, 但因为要支持"git checkout 任意历史版本重新部署", 所以入 git 管理。

### 5.1 文件清单 (10 项)

| 文件 | 角色 | 是源代码? | git 跟踪? |
|------|------|------|------|
| `deploy.sh` | 部署入口 (含 precheck + smoke) | ✅ 是 | ✅ 必须 |
| `precheck.sh` | 部署前 7 项检查 | ✅ 是 | ✅ 必须 |
| `smoke_test.sh` | 部署后 5 项真实功能测试 | ✅ 是 | ✅ 必须 |
| `rollback.sh` | 通用回滚 | ✅ 是 | ✅ 必须 |
| `diagnose.sh` | 部署后诊断 | ✅ 是 | ✅ 必须 |
| `unified_server.py` | 远端统一服务入口 | ✅ 是 | ✅ 必须 |
| `lib/common.sh` | shell 共享库 | ✅ 是 | ✅ 必须 |
| `README.txt` | 部署工作流文档 | ✅ 是 | ✅ 必须 |
| `deploy-v20260707_002.zip` | **本次发布的代码快照 (zip ~30MB)** | ❌ 是构建产物 | ⚠️ 应该 `.gitignore` + git-lfs |
| `meta/ tools/ docs/ scripts/` (zip 内) | 源码副本 | ✅ 但**跟根目录重复** | ⚠️ 重复了, 用 rebuild_zip.py 自动同步 |

### 5.2 怎么用 (V045 起的工作流)

```bash
# 1. MobaXterm SFTP 拖 deploy_bundle/ 到远端 /tmp/
# 2. 在远端跑:
bash /tmp/deploy_bundle/deploy.sh --version v20260707_002 --port 5001
# 3. 出问题:
bash /tmp/deploy_bundle/rollback.sh --to <v> --port <p>
```

### 5.3 git 跟踪的合理性

- ✅ 部署脚本 (`deploy.sh` / `precheck.sh` / `smoke_test.sh` / `rollback.sh` / `diagnose.sh` / `unified_server.py` / `lib/common.sh` / `README.txt`) **必须 git 跟踪** —— 因为改完要回滚到历史版本
- ✅ 已有 commit 8bfcbff `同步 deploy_bundle/deploy.sh 跟 tools/deploy.sh` 证实需要双向同步
- ⚠️ zip 文件 (30MB) 应该用 **git-lfs** 或放独立 release 仓库
- ⚠️ 源码副本 (meta/ tools/ docs/ scripts/) 应该**不重复 commit**, 用 `rebuild_zip.py` 从根目录自动打包

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

**TL;DR**: **现在主要是 "hash-driven full" (按需全量), L17 真 delta 刚接入 (V007.67, 2 天前) 还没成为主流**。

### 6.1 两种模式澄清

| 模式 | 含义 | 工具/脚本 | 状态 |
|------|------|----------|------|
| **"全量" (full)** | 整个 zip 解压覆盖 yonaa | `deploy.sh` PHASE 0.5 默认 | **当前主流** |
| **"按需全量" (hash-driven full)** | 解压前比较 zip 跟 yonaa 的 11 个关键文件 hash, 不一致才解压 | `deploy.sh` PHASE 0.5 (line 178-224) | **生产实际跑的** |
| **"真 delta" (true delta)** | 只复制"上次以来变了"的文件, 不动其他 | `smart_extract.sh` + `sha256_compare.sh` (L17) | **代码有, deploy.sh 没集成** |

### 6.2 deploy.sh 现在的实际逻辑 (PHASE 0.5)

```bash
# deploy.sh line 175-224: PHASE 0.5 触发条件
NEED_UNZIP=false
# 1. 远端没部署过 → 解压
if [ ! -d "$SERVER_DIR" ]; then NEED_UNZIP=true
elif [ ! -d "$DEPLOYMENTS_DIR/frontend_dist_files" ]; then NEED_UNZIP=true
fi
# 2. 4 个 server 类关键文件 hash 不一致 → 解压 (V007.35)
for CRITICAL_FILE in meta/server.py meta/core/datasource.py \
                     meta/core/sql_adapters.py meta/core/sql_connection_pool.py; do
    ZIP_MD5=$(unzip -p "$ZIP_PATH" "$CRITICAL_FILE" | md5sum)
    ROOT_MD5=$(md5sum "$DEPLOYMENTS_DIR/$CRITICAL_FILE")
    [ "$ZIP_MD5" != "$ROOT_MD5" ] && NEED_UNZIP=true
done
# 3. 7 个 V007.46+ 关键文件 hash 不一致 → 解压 (V007.46 BUG-FIX)
for CRITICAL_FILE in meta/core/safe_connect.py meta/core/db_health_monitor.py \
                     meta/services/audit_service.py ...; do
    [ hash 不一致 ] && NEED_UNZIP=true
done
# 4. 触发则: unzip -o $ZIP_PATH -d $DEPLOYMENTS_DIR/ (全量解压)
```

**核心**: deploy.sh 跟"真 delta"无关, 是个 **"11 文件 hash 守卫的全量解压器"**。

### 6.3 L17 真 delta 部署: V007.67 (2026-07-14) 才接入

| commit | 内容 | 时间 |
|--------|------|------|
| 941b850 | `feat(deploy): smart_extract.sh + sha256_compare.sh for delta extract [L17]` | V007.48+ |
| 53c5962 | `feat(deploy): deploy.sh PHASE 0.5 集成 smart_extract delta 模式 [L17]` | V007.48+ |
| 2bd689b | `feat(tools): rebuild_zip.py 支持 --delta 模式 + manifest_utils [L17]` | V007.49+ |
| b257078 | `feat(tools): verify_delta_manifest 全量 sha256 验证 [L17]` | V007.49+ |
| 0b7c540 | `deploy(delta): prod delta deploy 基础施设 (L17) [V007.67 2026-07-14]` | **V007.67 (2 天前)** |
| dabe721 | `L13.3+L14.3+L17+L8.6: deploy infra todo 推进` | 持续 |

**L17 = "Layer 17 = 智能 delta 部署"** — 是**完整子项目**, 至少 9 commits.

**`rebuild_zip.py --delta` 模式** (line 558-561): 用 `manifest_utils.build_delta_zip`, 只打包从 `--prev-manifest` 以来变了的文件。

### 6.4 实际状态: 还没成为主流

- **`smart_extract.sh` 在 deploy_bundle/ 不存在** (worktree 检查) —— 之前写过后又移走
- `deploy.sh` PHASE 0.5 仍是 hash-driven full, 没用 smart_extract
- `deploy_history.sh` 没有 delta/full 标记
- 0b7c540 是 **"基础施设"** 接入, 还没常态化用

**Agent 实际跑部署**:
- 平时发版: `python tools/rebuild_zip.py --version v2026xxxx_xxx` (生成全量 zip) → MobaXterm 拖过去 → `bash deploy.sh` (PHASE 0.5 自动判定要不要解压)
- 关键文件 hash 都没变 → **skip unzip, 5s 走完** (但 zip 还是有 30MB, 网络费)
- 改了关键文件 → **触发全量解压** (跟 V045 起的"偶尔 full"语义对齐)

**这才是**用户口中"主要 delta, 偶尔 full"的实际实现方式 —— "**按需全量**"。

### 6.5 L17 delta 真正启用后是什么体验 (待 V007.68+)

```bash
# 平时发版:
python tools/rebuild_zip.py --version v2026xxxx_xxx --delta \
    --prev-manifest shared/MANIFEST.prev
# → 生成的 zip 只含 "上次以来变了" 的文件 (KB 级, 不是 30MB)
# → MobaXterm 拖过去
bash deploy.sh
# → smart_extract.sh: 只覆盖变了文件 (秒级)
# → 99% 部署只动几 KB, 1% 重大重构才触 full
```

### 6.6 Agent 决策

| 任务 | 应该用 |
|------|-------|
| **现在发版 (V007.67 前)** | `rebuild_zip.py` (全量) + `deploy.sh` (自动按需解压) — 已经是事实上的"delta 体验" |
| **未来 L17 完整启用** | `rebuild_zip.py --delta --prev-manifest` + `smart_extract.sh` |
| **手动强全量** | `bash deploy.sh --force-unzip` (跳过 hash 判定) |

**记忆点**: 跟用户/Agent 沟通时, 描述成 **"按需全量 (hash-driven full), L17 真 delta 待 V007.68+"** 比 "delta 为主 full 偶尔" 更准确。

---

**维护**: AGENT 接手时, **5 分钟读本文件 → 30 秒跑 capability_probe → 5 分钟读 DEPLOY_INFRASTRUCTURE §0+§1 → 3 分钟读 [MONITORING_QUICK_REFERENCE.md](file:///d:/filework/release-prep-worktree/docs/MONITORING_QUICK_REFERENCE.md)** = 完全 ready.
