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
| 2026-07-13 15:30 | AI Assistant | **3 个 P0 小步完成** (V007.49-B):<br/>- `5e750ba` fix(tools): rebuild_zip.py V007.49-B 自动同步 meta/ + git HEAD 对账<br/>- `3e3c202` fix(tools): rebuild_zip.py ROOT 自适应 (deploy_bundle 路径下向上 2 层)<br/>- `a6aaee0` feat(core_service): /api/upload 增加契约校验 (verified_size + md5)<br/>- `71db29b` feat(tools): post_deploy_check.py - 3 层对账 (HEAD vs bundle vs zip vs remote)<br/>首次 post_deploy_check.py 运行发现 deploy_bundle/ vs git HEAD 3 文件 drift |
| 2026-07-13 14:00 | AI Assistant | **基础设施深度分析** + 新增长期 TODO (本文 L8-L13) |
| 2026-07-13 11:30 | AI Assistant | **第二次部署完成** - deploy-v20260713_002 (BUG-V061 修复版) - AM-ROLE 角色删除 28 条引用清空验证成功 |
| 2026-07-13 11:30 | AI Assistant | **部署完成** - deploy-v20260713_001 已发布到生产 v20260712_001 → v20260713_001。<br/>- Phase 1.5 自动触发: menu_permissions +0/~7, menus +0/~7 (bo_bindings)<br/>- 业务验证: arch-data 32 perms, SCMEDIT 拥有 relationship:create<br/>- 监控: 13/13 services UP, 8/8 ops_scheduler tasks OK, disk_check 100/100 |
| 2026-07-12 | AI Assistant | 创建（基于 BUG-V056/V060 复盘） |

---

## L8: 上传契约与"假成功"防护 (工作日: 0.5-1d)

> **状态**: ✅ P0 部分已实现 (a6aaee0)

| 子任务 | 工作量 | 优先级 | 状态 |
|--------|--------|--------|------|
| 8.1 core_service /api/upload 增加 verified_size + md5 字段 | 0.5d | P0 | ✅ DONE (a6aaee0) |
| 8.2 observability /api/upload_multi 假成功 bug 修复 | 0.5d | P0 | TODO |
| 8.3 所有上传路径统一契约 (write → read-back → compare) | 1d | P1 | TODO |
| 8.4 upload 客户端工具校验返回值 (verified_size == size) | 0.5d | P1 | TODO |

**修复 bug**: observability:9201 /api/upload_multi 返回 200 success 但实际未写盘

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
| 11.3 危险操作 (DELETE) 二次确认 header | 0.5d | P0 | 误删 AM-ROLE 角色事件 |
| 11.4 软删除优先 (deleted_at 列), 关键实体可恢复 | 1d | P1 | 数据恢复靠手工 SQL |

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

| 子任务 | 工作量 | 优先级 | 触发原因 |
|--------|--------|--------|----------|
| 13.1 /api/db/restore/entity 单实体恢复 (role / user / group) | 1d | P0 | 误删 AM-ROLE 靠手工 SQL 恢复 |
| 13.2 /api/db/restore/relation 关联表恢复 (role_permissions / role_menu_permissions 等) | 0.5d | P0 | 同上 |
| 13.3 /api/db/list_backups 返回所有可用 backup 时间点 | 0.25d | P1 | 当前 ls 手工 |
| 13.4 自动 backup 命名 (按时间 + 业务动作触发) | 0.25d | P2 | 当前命名 architecture_YYYYMMDD_HHMMSS.db.gz |

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

## 跟踪 / 提醒

- [ ] 每月回顾进度 (推荐在月度 ops 会议)
- [ ] 每次类似 bug 复盘后, 检查是否需要新增 L 条目
- [ ] 标注 P0/L1 = 季度计划, P2/L2-3 = 半年计划, L4-7 = 明年计划
- [ ] **新增长期**: L8-L14 来自 2026-07-13 部署事件复盘, 建议下次 sprint 评估

---