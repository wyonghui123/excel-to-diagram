# F001: Stale Loader — server 加载老代码

## 一句话定义

部署后, Python server **仍在加载旧版本代码**, 而**新上传的代码未生效**。

## 症状 (Symptoms)

| # | 症状 | 排查难度 |
|---|---|---|
| S1 | HTTP 200/401 但业务行为不对 (e.g. crud 返回 `instance_scope` 而非 `object`) | 高 — 看起来服务在线 |
| S2 | 改完代码后行为不变 | 中 — 易归咎于"代码没改" |
| S3 | 重启 server 后行为仍不变 | 高 — 重启是最后防线,失效时无招 |
| S4 | 重启后服务监听端口消失 | 低 — 易发现,但根因往往在更深层 |
| S5 | `ModuleNotFoundError` 但本地文件确实存在 | 中 — 走 namespace package 解析错误路径 |

## 根因层 (Root Cause Layers)

家族有 6 个已知根因层, 单次事故可能涉及多个:

### L1: 部署时 symlink 错指
- 模式: `deploy/meta` symlink 指向 `current/` 而非 `current/meta/`
- 结果: server 看到的 meta 路径是快照根目录, 找不到 `meta/__init__.py`, 走 namespace package fallback
- 触发: pack/sync 时把 `deploy_root` 错填为 snapshot 根 (`/opt/app/staging/deploy/current`) 而非版本目录

### L2: Python loader 走 namespace package 绕过 symlink
- 模式: 即使 `deploy/meta` 错指, namespace package 机制让 Python **仍能 import** 老代码 (走另一条 sys.path)
- 结果: 看起来 server 启动正常, 但加载的是旧版本
- 隐蔽性: 极 — import 不报错, 只是版本错

### L3: 部署后无"实际加载路径 vs 部署路径"自动验证
- 模式: 部署流程只验证 `HTTP 200` 或 `endpoint 已注册`, **不验证实际加载的 Python 模块来自新代码**
- 结果: S1-S3 所有症状都溜过门禁
- 这是 L1+L2 能生效的**关键放大器**: 没有人自动检查, 出问题只能靠人直觉

### L4: 调试 print 未还原就 restart
- 模式: 调试时插入 `print()` / `traceback.format_exc()`, **未还原 commit**, 直接 `restart server`
- 结果: server 启动报 `SyntaxError` (Python 把 print 当函数调用时, 上文改动会污染语法)
- 触发: 急于验证 fix, 跳过 `git diff` 检查
- 治本: I6 invariant (git status 必 clean)

### L5: staging "补丁子集" 未全量同步
- 模式: staging 部署目录 meta/core 只有 5/186 文件 (历史遗留), server 重启偶发 `ModuleNotFoundError`
- 结果: server 启动失败, 进程死了, 但 prod 仍然健康
- 触发: staging_round.py pack 只打 `dist/`, meta/ 从未全量同步
- 治本: `deploy_upload.py sync` 子命令 (全量同步 meta/)

### L6: 多套部署工具责任不明
- 模式: `deploy_upload.py` / `staging_full_sync.py` / `prod_invariant_check.py` 三套并存, 各自管一段
- 结果: 谁负责"实际加载路径"检查? 谁负责"全量同步"? 不明确
- 治本: 工具单一来源 (`staging_full_sync.py` 已删除, 功能合并到 `deploy_upload.py sync`)

## 复发历史 (Recurrence)

| 日期 | 触发场景 | 哪些层 | 修复方式 | 治本? | 链接 |
|---|---|---|---|---|---|
| 2026-09-05 | staging 上传 round N | L2+L3 | 重启 server | ❌ 仅症状缓解 | (无 retrospective) |
| 2026-09-13 | staging 全实例级 bug | L1+L2+L3 | 修 symlink + 重启 | 部分 | (无 retrospective) |
| 2026-09-16 | staging 全实例级 bug | L1+L2+L3+L4+L5+L6 | 修 symlink + 全量 sync + invariant 门禁 + 工具合并 | ✅ | [2026-09-16 retrospective](../../retrospectives/2026-09-16-staging-deploy-meta-symlink-misroute.md) |

## 防再发 SOP (Prevention)

| # | SOP | 工具 / 命令 |
|---|---|---|
| P1 | **每次部署后跑 6 项 invariant** (I1 cmdline/cwd, I2 realpath, I3 loader __file__, I4 端口, I5 instance_scope, I6 git clean) | `python tools/prod_invariant_check.py --target staging` 或 `--target production` |
| P2 | **deploy_upload.py 末尾自动跑 invariant 门禁** (任何 upload/verify/healthcheck/sync) | `python tools/deploy_upload.py --target X upload ...` (任一子命令) |
| P3 | **跳过 I6 (git clean) 检查前必须 stash** (调试 print 验证后) | `git stash push -u -m "..."` |
| P4 | **staging meta/ 全量同步用 sync 子命令** | `python tools/deploy_upload.py --target staging sync` |
| P5 | **prod 部署前对照 origin/main diff** (确认 vendor bundle 不是 local-only) | `git fetch origin && git log --oneline origin/main..HEAD` |
| P6 | **prod 部署后 HTTP healthcheck + invariant 双确认** | `python tools/deploy_upload.py --target production healthcheck` |

### 紧急逃生

```bash
# SKIP_INVARIANT_CHECK=1 跳过门禁 (不推荐, 仅紧急逃生)
export SKIP_INVARIANT_CHECK=1
python tools/deploy_upload.py --target staging upload ...
```

## 相关工具 / 代码

### 治本工具

- `tools/prod_invariant_check.py` — 6 项 invariant 检查 (I1-I6)
- `tools/deploy_upload.py` — 部署 CLI, 末尾自动跑门禁
- `tools/lib/deploy_topology.py` — DeployTarget 抽象 (避免硬编码 staging/prod 路径)

### 业务规范

- `docs/spec.md` — Spec 21 instance_scope (crud_create=object, crud_read/update/delete=instance)
- `meta/core/standard_action_loader.py` — 决定 instance_scope 的核心加载器

### 配置

- `tools/config/deploy_topology.yaml` — staging/prod 拓扑配置
- `docs/retrospectives/2026-09-16-staging-deploy-meta-symlink-misroute.md` — 9-16 完整复盘

## 待观察 (TODO)

- [ ] **L6 工具合并后, 是否会再冒出新层面?** (例如 dev/preview 环境的拓扑)
- [ ] **I1-I6 是否覆盖所有 stale loader 变种?** (例如 lazy import, sys.path 注入, PEP 660 namespace package 变化)
- [ ] **下一个家族 F002 候选**: 部署包 zip 损坏 / MD5 不匹配
- [ ] **下一个家族 F003 候选**: Token 鉴权误拒 (admin token 用在 write endpoint, 反之亦然)

---

## 创建信息

- 创建日期: 2026-09-16
- 创建人: dev agent (V061 staging)
- 基于复盘: [2026-09-16 retrospective](../../retrospectives/2026-09-16-staging-deploy-meta-symlink-misroute.md)
- 状态: ✅ 治本 (2026-09-16 prod + staging 6/6 PASS, invariant 门禁已部署)
- commit: `ecfd630` (squash-merged via PR #3)