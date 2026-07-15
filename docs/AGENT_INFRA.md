# AGENT_INFRA.md

> **目标读者**: AI Agent (主入口)
> **最后更新**: 2026-07-15
> **本文件用途**: AI Agent 5 分钟接手本项目, 知道: 这是什么、怎么部署、怎么远端操作、找哪个文档
> **详细规范**: 见下方 §0 索引

---

## 0. 文档索引 (1 张表)

| 场景 | 文档 | 行数 | 用途 |
|------|------|------|------|
| **总入口** | [DEPLOY_INFRASTRUCTURE.md](file:///d:/filework/release-prep-worktree/DEPLOY_INFRASTRUCTURE.md) | 331 | 7 章节, 18 工具, 7 端口 — **永远先看这** |
| **部署节奏** | [docs/DEPLOY_RHYTHM.md](file:///d:/filework/release-prep-worktree/docs/DEPLOY_RHYTHM.md) | 220 | **daily 21:00 / hotfix 立即** — 何时用哪个 |
| **远端操作速查** | 本文件 §1 | — | 5 个 Python 函数 / 5 行 CLI / **回归测试 §1.4** |
| **回归测试** | [docs/REGRESSION_TEST_SUITE.md](file:///d:/filework/release-prep-worktree/docs/REGRESSION_TEST_SUITE.md) | 250+ | 9 个 sqlite io error 场景 — staging 自动化 |
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

### 1.5 1 个公式: Token

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

## 3. 关键事实 (2026-07-15 当前)

| 项 | 状态 |
|---|------|
| **prod DB** | 18 migration SUCCESS, **0 FAILED** ✅ |
| **staging DB** | 18 migration SUCCESS, **0 FAILED** ✅ |
| **migration lint** | **0 FAIL**, 8 WARN, exit 0 ✅ |
| **migration runner** | idempotent (重复列自动跳过) ✅ |
| **9101/19101 log_service** | **alive (10+ 端点, V007.55 systemd 守护 + V007.57 nobody 用户, 进程死后 5s 自动重启, HIPS 不杀)** ✅ |
| **本会话 commit 数** | 6 (80e5498 → 366cb85) + 文档 + log_service 启停工具 |

---

**维护**: AGENT 接手时, **5 分钟读本文件 → 30 秒跑 capability_probe → 5 分钟读 DEPLOY_INFRASTRUCTURE §0+§1** = 完全 ready。
