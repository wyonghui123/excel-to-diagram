---
alwaysApply: false
description: "并行开发SOP v3.3 - 自验证+PM Gate模型 (指针文件)"
globs: "PARALLEL_DEV_SOP*,DEPLOY_HANDOVER*,scripts/self_verify*,scripts/_wt_service*,scripts/_wt_lifecycle*,scripts/_events*,scripts/_coord_log*,scripts/_config_backup*,scripts/_session_cleanup*,scripts/_sync_scripts*"
---

# 并行开发 SOP v3.3 (指针文件)

> **本文件是指针文件，引导 Agent 找到完整的 SOP 文档和工具。**
> **完整文档不在 .trae/rules/ 中，而是在 worktree 目录下。**

## 核心文档位置

| 文档 | 完整路径 | 用途 |
|------|---------|------|
| **PARALLEL_DEV_SOP v3.3** | `D:/filework/worktrees/agent-v061-staging/PARALLEL_DEV_SOP.md` | 6阶段并行开发流程 |
| **AGENT_INFRA §0.10** | `D:/filework/worktrees/release-prep/docs/AGENT_INFRA.md` §0.10 | 自验证5步SOP |
| **AGENT_INFRA §0.11** | 同上 §0.11 | Integration按需决策树 |
| **AGENT_INFRA §0.12** | 同上 §0.12 | 状态源优先级 (3源+写入同步) |
| **AGENT_INFRA §0.13** | 同上 §0.13 | --keep-running 服务保持 |
| **AGENT_INFRA §0.8.8** | 同上 §0.8.8 | v33_pipeline 状态机 |
| **AGENT_INFRA §0.8.9** | 同上 §0.8.9 | 阶段6→7衔接 (PM通知+部署触发) |
| **AGENT_INFRA §0.8.10** | 同上 §0.8.10 | 10层端口防护体系 |
| **AGENT_INFRA §7** | 同上 §7 | **部署打包智能体专属指南** |

## v3.3 核心变更 (vs v3.2)

| 维度 | v3.2 | v3.3 |
|------|------|------|
| 阶段数 | 8 | **6** |
| Integration | 常开 (3007/3018) | **按需** (仅Agent碰同模块) |
| Agent验证 | 单测 + Integration E2E | **自验证(真实服务) + PM Gate** |
| HANDOVER | 无自验证证据 | **必须附 SELF_VERIFY_RESULTS** |
| PM验证 | 隐含 | **显式 PM_VERIFIED 签字** |
| 部署智能体 | 无专属规范 | **AGENT_INFRA §7 专属指南** |

## v3.3 工具清单 (13个)

| 工具 | 位置 | 命令数 | 用途 |
|------|------|--------|------|
| `_wt_service.py` | `scripts/` | 8 | worktree服务启停+reconcile+watchdog+force-stop+recover |
| `self_verify.py` | `scripts/` | 4 | 自验证自动化 (run/smoke/report/quick) + --keep-running |
| `_wt_lifecycle.py` | `scripts/` | 5 | worktree生命周期 (list/create/remove/gc/health) |
| `_events.py` | `scripts/` | 4 | Agent事件通知 (log/recent/since/tail) |
| `_coord_log.py` | `scripts/` | 4 | 协调操作审计 (log/recent/search/audit) |
| `_config_backup.py` | `scripts/` | 6 | 配置备份/恢复 (backup/restore/list/verify/backup-all/verify-all) |
| `_session_cleanup.py` | `scripts/` | 4 | 会话清理hook (register/cleanup/cleanup-all/status) |
| `_sync_scripts.py` | `scripts/` | 3 | 脚本一键同步 (list/sync/diff) |
| `_coord_commit_guard.py` | `scripts/` | 2 | HANDOVER检查 (check-handover + check-self-verify) |
| `_ports_sync.py` | `scripts/` | 2 | 端口分配+stale清理 |
| `vite.config.js` | 根目录 | — | VITE_PORT + BACKEND_PORT 环境变量 |
| `paths.json` | `.coord/` | — | 路径配置 (单一真相源) |
| `ports.json` | `.coord/` | — | 端口注册表 (reserved/persistent/allocated) |

## 6阶段流程速查

```
1. PM分配BUG (含是否需Integration)
2. worktree + 实现
3. 自验证 (真实服务) ← v3.3核心变更
4. commit + HANDOVER (附SELF_VERIFY_RESULTS)
5. 协调智能体cherry-pick + 重启3006/3011
6. PM验证 + PM_VERIFIED签字 → 部署
```

## 铁律

- **HANDOVER无SELF_VERIFY_RESULTS = 无效**
- **无PM_VERIFIED = 未完成**
- **默认不需要Integration** (仅Agent碰同模块时启用)
- **verify_deploy_bundle 6/6 PASS 才许上传** (部署智能体)
- **无PM_VERIFIED不许部署** (部署智能体)
