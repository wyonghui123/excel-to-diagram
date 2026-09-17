# 中长期改进方案 TODO

> 最后更新: 2026-07-13 | 来源: BUG-V056/V060 复盘 + 20260713 部署记录
> 关联文档: [DEPLOY_CHECKLIST.md](../DEPLOY_CHECKLIST.md), [DEPLOY_SOP_V2.md](../DEPLOY_SOP_V2.md)

> **本文档仅作为未来 roadmap 跟踪**，不要求立即执行。每项标注预估工作量和优先级。

---

## 部署记录: 2026-07-13 (deploy-v20260713_001)

### Commit 清单 (6 commits, 本地领先 origin 6)

| Commit | 作者 | 说明 | 影响范围 |
|--------|------|------|----------|
| `7e31be0` | 智能体2 | fix(fe): BUG-V062 save() 传递 source='manual' 权限 | 前端 useMenuPermission.ts |
| `0ee90da` | 智能体2 | docs: HANDOFF V20260712_004 补充 BUG-V062 | 文档 |
| `eb918eb` | 智能体2 | test(role-delete): BUG-V061 一致测试完整代码 | 测试 |
| `e9e433d` | 智能体1 | feat(help): P3 简化帮助中心 + 公开 URL 入口 | 前端 (16 files, +1193/-2587) |
| `3bcbd24` | 智能体1 | feat(help): 公开 URL 场景素材 (mp4 + png) | 静态资源 (4 media files, 67MB) |
| `2782a0b` | 协调智能体 | fix+feat: P0 init_menu_permissions 增量 UPSERT + log_service v4.11 | 后端 init_menu_permissions.py + log_service.py |

### 部署包内容

- **deploy-v20260713_001.zip** (78.5MB, 659 files)
- 前端: 包含帮助中心简化 + BUG-V062 权限修复 + 公开 URL 入口
- 后端: P0 init_menu_permissions.py 增量更新 + log_service v4.11 + sql_connection_pool 同步

### 额外需部署到生产服务器的运维工具

| 文件 | 用途 | 部署路径 |
|------|------|----------|
| `tools/verify_deployment.py` | 部署后自动验证 (5 项检查) | /opt/app/shared/ |
| `tools/ops_scheduler_v1.1.py` | ops_scheduler 升级版 | /opt/app/shared/ |
| `monitor_prod.py` | 生产监控脚本 (8 项检查) | /opt/app/shared/ |

### 遗漏检查结果

- [OK] 5 个 agent commit 全部包含
- [OK] P0 init_menu_permissions 增量更新已包含
- [OK] log_service v4.11 已包含
- [OK] deploy_bundle/meta/core/sql_connection_pool.py 已同步
- [WARN] 本地有未提交的 dev config 变更 (meta/server.py 3011->5000, package.json, vite.config.js) - 仅影响本地开发，不影响生产
- [OK] 前端已重新构建 (2m 11s, 117 files)

---

## L1: 部署自动化平台 (工作日: 3-5d)

**目标**: 消灭"手动 rsync / upload_multi" 流程

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 1.1 部署工单系统 (类似 Jira/ServiceNow) | 2d | 高 |
| 1.2 部署执行器 (read-only → staging → prod pipeline) | 1d | 高 |
| 1.3 自动回滚机制 (基于 health_supervisor 监控) | 1d | 中 |
| 1.4 部署历史 / audit log | 0.5d | 中 |

**收益**:
- 部署有据可查
- 失败自动回滚
- 减少人工操作失误

---

## L2: 数据迁移版本管理 (工作日: 2-3d)

**目标**: 像代码一样管理 schema / 静态数据变更

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 2.1 migration 框架 (类似 Alembic / Flyway) | 2d | 高 |
| 2.2 schema_version 表 + 自动 baseline | 0.5d | 高 |
| 2.3 init_*.py 改造为可回滚的 migration | 0.5d | 中 |
| 2.4 dry-run 模式 (生产前预演) | 0.5d | 低 |

**收益**:
- 不再"部署后才知 DB 状态"
- 可回滚的数据库变更
- 历史清晰可追溯

---

## L3: 配置中心 (工作日: 2d)

**目标**: 消除"代码硬编码" 类问题 (本次 bug-V060 的根因)

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 3.1 配置中心 (类似 Nacos / Consul) | 1d | 高 |
| 3.2 业务规则外置 (filter order, scope mode 等) | 0.5d | 高 |
| 3.3 实时生效 (不重启即可调参) | 0.5d | 中 |

**收益**:
- 改业务规则不需要部署代码
- 不同环境不同配置
- 配置变更可审计

---

## L4: 监控 / 告警增强 (工作日: 1-2d)

**目标**: 部署后立即发现问题

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 4.1 部署后 5 分钟黄金窗口自动烟测 | 0.5d | 高 |
| 4.2 权限 4xx/5xx 异常率告警 | 0.5d | 中 |
| 4.3 "DB 数据 vs 代码声明" 一致性告警 | 0.5d | 中 |
| 4.4 前端 hash 与后端版本不匹配告警 | 0.5d | 低 |

**收益**:
- 部署后用户还没发现问题，我们先发现
- 长期看，能定位"哪些部署引入回归"

---

## L5: 测试覆盖 (工作日: 5-7d)

**目标**: 类似 bug 不再通过人工测试发现

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 5.1 init_menu_permissions 的单元测试 (UPSERT 场景) | 0.5d | 高 |
| 5.2 数据权限拦截器的集成测试 (BUG-V055~V060 全部) | 2d | 高 |
| 5.3 部署 E2E 测试 (PlaywrightCLI) | 1d | 中 |
| 5.4 权限矩阵全量回归 | 2d | 中 |
| 5.5 数据库迁移的快照测试 | 1d | 低 |

**收益**:
- 一旦未来回归，会被自动捕获
- 减少手动测试

---

## L6: 文档与培训 (工作日: 2-3d)

**目标**: 团队认知一致

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 6.1 完整 OPS_MANUAL.md v2 (基于真实教训) | 1d | 高 |
| 6.2 部署视频教程 | 1d | 中 |
| 6.3 故障复盘 wiki 模板 | 0.5d | 中 |
| 6.4 新人 onboarding 文档 | 0.5d | 中 |

---

## L7: 架构演进 (工作日: 5-10d)

**目标**: 长远避免类似架构问题

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 7.1 拆开"代码逻辑"和"业务规则"分层 | 3d | 中 |
| 7.2 业务规则 DSL (类似 SAP BRFplus) | 5d | 低 |
| 7.3 多租户隔离层 (sub_domain/team/scene) | 3d | 中 |

---

## 跟踪 / 提醒

- [ ] 每月回顾进度 (推荐在月度 ops 会议)
- [ ] 每次类似 bug 复盘后, 检查是否需要新增 L 条目
- [ ] 标注 P0/L1 = 季度计划, P2/L2-3 = 半年计划, L4-7 = 明年计划

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-13 16:40 | 协调智能体 | **审计恢复方向确认 + multipart 污染修复 + P0 升级** (TODO_LONGTERM.md v2)<br/>- 创建 `docs/HANDOFF_object_recovery.md` 接手文档 (L13 阶段 1-3)<br/>- 实测: AM-ROLE audit_logs 主实体 100% 完整, 关联 26/28 (缺 2)<br/>- 实测: 4 个 audit 缺口 (role_menu + role_dim_scope 完全无 audit)<br/>- **L8.5 紧急 P0 (新)**: multipart 污染 bug, 影响今天 4 个文件 (2 zip + monitor_prod.py + verify_deployment.py)<br/>- 临时修复 3 个文件 (移除 multipart 头), v002 zip 清理后 82286200 字节<br/>- **L11.3 升级**: DELETE 二次确认 + L13 强绑定<br/>- **新增 L15 (监控) L16 (SSH) L17 (部署前检查)**<br/>- L8.2 observability /api/upload_multi 待二次确认 (可能与 L8.5 是同一个 bug) |
| 2026-07-13 15:30 | AI Assistant | **3 个 P0 小步完成** (V007.49-B):<br/>- `5e750ba` fix(tools): rebuild_zip.py V007.49-B 自动同步 meta/ + git HEAD 对账<br/>- `3e3c202` fix(tools): rebuild_zip.py ROOT 自适应 (deploy_bundle 路径下向上 2 层)<br/>- `a6aaee0` feat(core_service): /api/upload 增加契约校验 (verified_size + md5)<br/>- `71db29b` feat(tools): post_deploy_check.py - 3 层对账 (HEAD vs bundle vs zip vs remote)<br/>首次 post_deploy_check.py 运行发现 deploy_bundle/ vs git HEAD 3 文件 drift |
| 2026-07-13 14:00 | AI Assistant | **基础设施深度分析** + 新增长期 TODO (本文 L8-L13) |
| 2026-07-13 11:30 | AI Assistant | **第二次部署完成** - deploy-v20260713_002 (BUG-V061 修复版) - AM-ROLE 角色删除 28 条引用清空验证成功 |
| 2026-07-13 11:30 | AI Assistant | **部署完成** - deploy-v20260713_001 已发布到生产 v20260712_001 → v20260713_001。<br/>- Phase 1.5 自动触发: menu_permissions +0/~7, menus +0/~7 (bo_bindings)<br/>- 业务验证: arch-data 32 perms, SCMEDIT 拥有 relationship:create<br/>- 监控: 13/13 services UP, 8/8 ops_scheduler tasks OK, disk_check 100/100 |
| 2026-07-12 | AI Assistant | 创建（基于 BUG-V056/V060 复盘） |

---

## L8: 上传契约与"假成功"防护 (工作日: 0.5-1d)

> **状态**: ✅ P0 部分已实现 (a6aaee0) | ⚠️ **新发现 P0: multipart 污染**

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 8.1 core_service /api/upload 增加 verified_size + md5 字段 | 0.5d | P0 | ✅ DONE (a6aaee0) |
| ~~8.2 observability /api/upload_multi 假成功 bug 修复~~ | 0.5d | ~~P0~~ | ❌ 误诊, **已重新归类 L8.7** |
| 8.3 所有上传路径统一契约 (write → read-back → compare) | 1d | P1 | TODO |
| 8.4 upload 客户端工具校验返回值 (verified_size == size) | 0.5d | P1 | TODO |
| **8.5 multipart 污染 bug 修复 (客户端发 multipart, server 不解析直接写入)** | 1d | **P0** | **TODO 紧急** |
| 8.6 修复工具 `unzip_safe` (检测 zip 头是否被污染) | 0.5d | P1 | TODO |
| **8.7 systemd PrivateTmp 隔离导致"假成功"修复 (重新归类自 L8.2)** | 1d | **P0** | **TODO 紧急** |
| 8.8 所有服务加 `/api/isolation_check` 端点 (验证 PrivateTmp 状态) | 0.5d | P1 | TODO |

**L8.2 → L8.7 重新归类说明 (2026-07-13 19:05 实测确认)**:
- ❌ **原 L8.2 误诊**: "observability /api/upload_multi 报告 200 但实际未写盘"
- ✅ **真正根因**: **systemd PrivateTmp 隔离**
  - 13 个 yonaa 服务都用 `PrivateTmp=yes` (systemd 隔离 `/tmp`)
  - 上传写到 `/tmp/systemd-private-<UUID>-<service>.service-XXX/tmp/`
  - 外部 `ls /tmp/` 看不到, 看起来"假成功"
  - **服务重启时隔离区清空** → 文件消失
- **实测证据** (今天 19:07):
  - 上传 `/tmp/immediate_test_1.txt` 返回 200 + contract=ok
  - 外部 `ls /tmp/immediate_test_1.txt` → 不存在
  - 内部实际路径: `/tmp/systemd-private-52d13d07be9c4e9aa3dc3381cb306d02-core_service.service-VurR9W/tmp/immediate_test_1.txt`
  - **所以不是"假成功"而是"在隔离区成功"**
- **修复方案**:
  - **方案 A** (推荐, 0.5d): 关闭 core_service / log_service / observability 的 `PrivateTmp=yes`, 让 `/tmp` 共享
  - **方案 B** (备选, 1d): 上传时强制写到 `/opt/app/tmp/` (非隔离目录)
  - **方案 C** (治标, 0.1d): 文档说明 `/tmp` 是隔离的, 部署脚本需 `--no-isolation` 启动
- **影响范围**:
  - ✅ 之前所有"假成功"上传实际**都成功写盘了** (在隔离区), 部署可能正常
  - ⚠️ 但**部署工具的逻辑有 bug** — 因为上传后没在隔离区 unzip, 可能 unzip 的是旧版
  - 这解释了为什么有些部署"看起来成功但代码没更新"

**L8.5 详细说明 (2026-07-13 16:30 实测)**:
- **bug 描述**: 客户端发 `multipart/form-data` body, server `/api/upload` 只读 `Content-Length` 字节直接写入文件，**不解析 multipart boundary**。结果: 文件被 multipart 头污染 (如 `--CoreUploadBoundary777\r\n...`)
- **影响** (本次部署事件):
  - `/opt/app/deploy-v20260713_002.zip` 被污染 149 字节 (今天 11:30 部署的 BUG-V061 修复版本!)
  - `/opt/app/deploy-v20260713_007.zip` 被污染 149 字节 (新打包的 V007.49-B 修复版本)
  - `/opt/app/shared/monitor_prod.py` 被污染 140 字节 (生产监控工具!)
  - `/opt/app/shared/verify_deployment.py` 被污染 145 字节 (部署验证工具!)
- **已临时修复** (2026-07-13 16:35 协调智能体): 3 个关键文件已 `unzip_safe` 清理, v002 zip 清理后大小 82286200 字节 (移除 149 字节 multipart 头)
- **根本修复** (开发智能体):
  - **客户端**: 改用 `Content-Type: application/octet-stream`, body 是 raw file content
  - **server 端**: 检测 multipart boundary, 解析 `Content-Disposition: form-data; filename=...`, **只写 boundary 后的数据**
  - **向后兼容**: raw body (无 boundary) 仍直接写入
- **L8.6 unzip_safe 工具**: 上传后立即检测文件 magic number (zip: `PK\x03\x04`, .py: `"""` or `import` 等), 不匹配则拒收或自动剥离
- **L8.6.1**: 部署前自动检查所有 zip/py 文件 magic number, 部署历史 zip 也清理 (今天已清理 001/002/007)

---

## L9: rebuild_zip.py ROOT 自适应 + meta/ 同步 (工作日: 0.5d)

> **状态**: ✅ P0 部分已实现 (5e750ba + 3e3c202)

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 9.1 ROOT 自适应 (deploy_bundle/tools/ 路径下向上 2 层) | 0.1d | P0 | ✅ DONE (3e3c202) |
| 9.2 同步 meta/ 关键文件 (action_executor / init_menu_permissions / server) | 0.2d | P0 | ✅ DONE (5e750ba) |
| 9.3 完成后对账 (deploy_bundle/ vs git HEAD) | 0.1d | P0 | ✅ DONE (5e750ba) |
| 9.4 自动 rebuild 后重建 deploy_bundle 副本 | 0.1d | P1 | TODO |

**修复 bug**: rebuild_zip.py 只同步 tools/ 不同步 meta/, BUG-V061 漏部署根因

---

## L10: post_deploy_check.py 三层对账 (工作日: 1d)

> **状态**: ✅ P0 已实现 (71db29b)

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 10.1 L1: git HEAD vs deploy_bundle/ | 0.2d | P0 | ✅ DONE |
| 10.2 L2: deploy_bundle/ vs zip | 0.2d | P0 | ✅ DONE |
| 10.3 L3: zip vs /opt/app/deployments/ (远程) | 0.3d | P0 | ✅ DONE |
| 10.4 部署前自动跑 (在 deploy.sh 末尾调用) | 0.2d | P1 | TODO |
| 10.5 部署后 5 分钟自动跑 + 不通过告警 | 0.5d | P1 | TODO |

**修复 bug**: 用户测试 BUG-V061 时才发现漏部署, 应在部署时自动发现

---

## L11: 部署溯源与审计 (工作日: 1-2d)

| 子任务 | 工作量 | 优先级 | 触发原因 |
|--------|--------|--------|----------|
| 11.1 部署完成后写入 `/opt/app/deployments/LAST_DEPLOY.json` (含 deploy_id, who, when, commit_list, zip_md5) | 0.5d | P1 | 事后无法追溯"当前在跑什么" |
| 11.2 core_service 接收 X-Agent-Id header, 写入 audit_log | 0.5d | P1 | 多 AI 操作责任不清 |
| **11.3 危险操作 (DELETE) 二次确认 header** | 0.5d | **P0 升级** | 误删 AM-ROLE 角色事件 (今天 16:01) |
| 11.4 软删除优先 (deleted_at 列), 关键实体可恢复 | 1d | P1 | 数据恢复靠手工 SQL (已由 L13 替代) |

**L11.3 紧急性升级理由** (2026-07-13):
- AM-ROLE 删除测试事件中, 二次确认可阻止 AI 在 16:01 重复删除已恢复的角色
- L13 接手文档 (HANDOFF_object_recovery.md) 应与 L11.3 强绑定: 恢复前必须强制 X-Confirm-Delete (避免误恢复)

---

## L12: 远程 Shell 能力增强 (工作日: 2-3d)

| 子任务 | 工作量 | 优先级 | 触发原因 |
|--------|--------|--------|----------|
| 12.1 SSH 持续失败的根因调查 + 修复 | 1d | P0 | 整个部署靠 HTTP exec 兜底 |
| 12.2 /api/exec 支持 shell session (cd X && Y) | 1d | P1 | 每条命令都要发完整 bash 脚本 |
| 12.3 /api/exec 命令白名单 + 审计 | 0.5d | P1 | 当前能 rm -rf / |
| 12.4 /api/upload 路径白名单精简 | 0.5d | P2 | 当前过宽 |

---

## L13: 数据库子集 PIT 恢复 (工作日: 2d)

> **状态**: 🎯 接手文档已就绪, 待开发智能体执行
> **接手文档**: `docs/HANDOFF_object_recovery.md` (2026-07-13 创建)
> **实测基础**: AM-ROLE id=1201 删除事件 + audit_logs 完整快照

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 13.1 audit_logs 缺口补全 (role_menu + role_dim_scope + role_permissions 2 条) | 0.5d | P0 | TODO (接手文档阶段 1) |
| 13.2 audit_recovery.py 通用恢复框架 (find/preview/restore API) | 1d | P0 | TODO (接手文档阶段 2) |
| 13.3 HTTP API 集成 (dbops_service 加 3 端点) | 0.5d | P0 | TODO (接手文档阶段 3) |
| 13.4 audit_coverage_check.py 自动覆盖率检测 (CI 用) | 0.5d | P1 | TODO |
| 13.5 admin UI (Vue 审计恢复页面) | 1d | P2 | TODO (接手文档阶段 4) |

**实测数据** (2026-07-13 16:35):
- AM-ROLE 主实体恢复: ✅ 100% 完整
- role_permissions 恢复: ⚠️ 26/28 (缺 2 条待查)
- role_menu_permissions 恢复: ❌ 0% (audit 缺口)
- role_dimension_scopes 恢复: ❌ 0% (audit 缺口)

**触发原因**:
- 误删 AM-ROLE 角色 2026-07-13 16:01, 靠 backup 整库恢复
- audit_logs 实际已经有 95% 完整快照, 仅需补 4 个缺口 + 写 1 个恢复框架

**关联**: L11.3 (恢复前必须 confirm) + L8.5 (audit 缺口补全时上传不要用 multipart)

---

## L14: deploy_service 新建 (工作日: 3-5d)

> **架构铁律**: core_service 已 500 行, 不能再加新端点

| 子任务 | 工作量 | 优先级 |
|--------|--------|--------|
| 14.1 创建 deploy_service.py (9205), 独立 token + watchdog | 1d | P1 |
| 14.2 /api/deploy/start (接收 zip + commit 列表, 创建 deploy_id) | 0.5d | P1 |
| 14.3 /api/deploy/status (查询 6 状态机) | 0.5d | P1 |
| 14.4 /api/deploy/rollback (一键回滚) | 1d | P1 |
| 14.5 /api/deploy/history | 0.5d | P2 |
| 14.6 集成 post_deploy_check.py 到 /api/deploy/verify | 0.5d | P1 |

**4 问检查清单**:
- Q1 元能力？勉强算, 依赖 git/db/zip, 属于"组合能力"
- Q3 行数 < 500? 会超过, 必须独立
- Q4 独立部署? 是
- **结论**: 必须独立

---

## L15: 监控工具随架构演进 (工作日: 0.5d)

> **触发原因** (2026-07-13): `monitor_prod.py` 还在用 `/api/services/status` 端点, 但 core_service V2.0 已拆分到 config_service

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 15.1 更新 monitor_prod.py 端点列表 (core_service V2.0 + 4 问铁律) | 0.2d | P1 | TODO |
| 15.2 增加 post_deploy_check 集成 (部署后自动跑) | 0.1d | P1 | TODO |
| 15.3 增加 audit 覆盖率检查 (audit_coverage_check.py) | 0.2d | P1 | TODO |

**当前监控盲点**:
- ❌ core_service /api/services/status (404) — 已拆分, 监控没更新
- ❌ post_deploy_check 跑没跑 — 没强制集成
- ❌ audit_logs 覆盖率 — 没检查

---

## L16: SSH + 远程能力根因 (工作日: 1d)

> **触发原因** (2026-07-13): SSH 持续 Connection reset, 整个部署靠 HTTP 兜底
> **最新状态** (2026-07-13 16:35): SSH 服务正常 LISTEN 0.0.0.0:22, 客户端问题

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 16.1 Windows 端 SSH key 有效期检查 | 0.25d | P0 | TODO |
| 16.2 SSH 连接 timeout 调优 (现 ConnectTimeout=10s 太短) | 0.25d | P0 | TODO |
| 16.3 HTTP 兜底 + SSH 双通道自动切换 (log_service) | 0.5d | P1 | TODO |

**当前根因分析** (2026-07-13):
- `netstat -tln`: tcp 0.0.0.0:22 LISTEN ✓
- Windows 端 `ssh user@172.20.59.7`: Connection reset
- **可能原因**: (1) Windows SSH key 过期 (2) known_hosts 错误 (3) MTU/防火墙
- **绕过方案**: 用 log_service:9101 /api/exec 兜底 (今天已成功)

---

## L17: 部署前自动检查 (工作日: 0.5d)

> **触发原因** (2026-07-13): 今天多次部署都是"先部署, 再发现问题", 应该 deploy 前自动检查

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 17.1 部署前检查 deploy_bundle/ == git HEAD (drift detection) | 0.2d | P0 | 部分已有 (L10) |
| 17.2 部署前检查目标文件 magic number (zip: PK\x03\x04, .py: import/""") | 0.1d | P0 | TODO (新) |
| 17.3 部署前检查 zip 内必需文件清单 (MANIFEST + 关键 .py) | 0.1d | P1 | TODO |
| 17.4 部署前 dry-run (本地解压验证) | 0.1d | P1 | 已部分实现 (rebuild_zip.py) |

**今天发生的"部署后才发现"问题**:
- 16:01 AM-ROLE 删除测试才发现 BUG-V061 没部署
- 16:15 core_service 污染才发现 core_service.py 被 multipart 头破坏
- 16:25 monitor_prod.py 污染才发现

**改进**: 部署前 5 秒跑自动检查, 失败则 abort 部署并打印修复建议

---

## 跟踪 / 提醒

- [ ] 每月回顾进度 (推荐在月度 ops 会议)
- [ ] 每次类似 bug 复盘后, 检查是否需要新增 L 条目
- [ ] 标注 P0/L1 = 季度计划, P2/L2-3 = 半年计划, L4-7 = 明年计划
- [ ] **新增长期**: L8-L14 来自 2026-07-13 部署事件复盘, 建议下次 sprint 评估

---