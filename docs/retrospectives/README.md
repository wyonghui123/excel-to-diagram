# Retrospectives 索引

> **项目** excel-to-diagram  
> **目的** 沉淀 bug 修复 / 测试方法论 / 架构决策 的复盘文档  
> **命名** `YYYY-MM-DD-<topic>.md` (按时间倒序)

---

## 2026-09

| 日期 | 主题 | 文档 | 核心要点 |
|------|------|------|---------|
| 09-13 | **staging 部署拓扑通用化 (DeployTarget + PathResolver)** | [2026-09-13-deploy-topology-generalization.md](2026-09-13-deploy-topology-generalization.md) | 同一类问题 (symlink+namespace 双发) 发生 ≥5 次 → 三层抽象 (DeployTarget / PathResolver / ResourceType) + 声明式 YAML 配置 + introspect 验证 |
| 09-05 | **staging `meta` 包影子树** | [2026-09-05-staging-meta-shadow-tree.md](2026-09-05-staging-meta-shadow-tree.md) | "部署成功但代码从未被加载" / 双树审计 / `check_meta_import_origin.py` 门禁工具 / §14 后续补注 (9-13 deploy_topology 是其延续) |
| 09-05 | **env port 漂移** | [2026-09-05-env-port-drift.md](2026-09-05-env-port-drift.md) | port-isolation / 环境间端口漂移排查 |
| 09-05 | **org parent tree searchhelp** | [2026-09-05-org-parent-tree-searchhelp.md](2026-09-05-org-parent-tree-searchhelp.md) | org 父树搜索助手实现细节 |
| 09-04 | **level switch render overlay** | [2026-09-04-level-switch-render-overlay.md](2026-09-04-level-switch-render-overlay.md) | 层级切换渲染叠加 |
| 09-04 | **legend hide expand level reset** | [2026-09-04-legend-hide-expand-level-reset.md](2026-09-04-legend-hide-expand-level-reset.md) | 图例隐藏/展开/层级重置 |
| 09-03 | **prod 8081 outage self-inflicted** | [2026-09-03-prod-8081-outage-self-inflicted.md](2026-09-03-prod-8081-outage-self-inflicted.md) | 自身引起的 prod 8081 故障 |
| 09-03 | **staging frontend stale dist** | [2026-09-03-staging-frontend-stale-dist.md](2026-09-03-staging-frontend-stale-dist.md) | staging 前端 dist 陈旧 |

---

## 2026-06

| 日期 | 主题 | 文档 | 核心要点 |
|------|------|------|---------|
| 06-15 | **Mermaid 测试方法论 + 基础设施提案** | [2026-06-15-mermaid-test-methodology.md](2026-06-15-mermaid-test-methodology.md) | 三层坐标互转 / 6 个脚本演进的胜与痛 / 4 层基础设施提案 (`meta/tests/mermaid/`) / 8 条硬约束 |
| 06-15 | **SVG edge label 居中问题 (v40.6→v40.8)** | [2026-06-15-svg-edge-label-centering.md](2026-06-15-svg-edge-label-centering.md) | xMidYMid slice 陷阱 / viewport 像素 ≠ SVG 单位 / 5 条铁律 |
| 06-12 | **step scope summary relation count fix** | [2026-06-12-step-scope-summary-relation-count-fix.md](2026-06-12-step-scope-summary-relation-count-fix.md) | step 范围汇总关联计数修复 |
| 06-11 | **Edge label 截断问题** | [2026-06-11-edge-label-truncation.md](2026-06-11-edge-label-truncation.md) | 历史, edge label 截断 |

---

## 2026-08

| 日期 | 主题 | 文档 | 核心要点 |
|------|------|------|---------|
| 08-29 | **(最终回归报告)** | [final-regression-report-2026-08-29.md](../refactor/final-regression-report-2026-08-29.md) | 最终回归报告 |
| 08-29 | **(二次评审)** | [second-review-2026-08-29.md](../refactor/second-review-2026-08-29.md) | 二次评审 |
| 08-26 | **condition rule builder layout stale build** | [2026-08-26-condition-rule-builder-layout-stale-build.md](2026-08-26-condition-rule-builder-layout-stale-build.md) | 条件规则构建器布局陈旧 |
| 08-21 | **hide full render elkgroup pollution** | [2026-08-21-hide-full-render-elkgroup-pollution.md](2026-08-21-hide-full-render-elkgroup-pollution.md) | 隐藏完整渲染 ELK 组污染 |

---

## 按主题分类

### 🐛 Bug 复盘
- [2026-09-13-deploy-topology-generalization.md](2026-09-13-deploy-topology-generalization.md) — 部署拓扑通用化 (双发反复栽)
- [2026-09-05-staging-meta-shadow-tree.md](2026-09-05-staging-meta-shadow-tree.md) — meta 包影子树
- [2026-09-05-env-port-drift.md](2026-09-05-env-port-drift.md) — port 漂移
- [2026-09-05-org-parent-tree-searchhelp.md](2026-09-05-org-parent-tree-searchhelp.md) — org 父树搜索
- [2026-09-04-level-switch-render-overlay.md](2026-09-04-level-switch-render-overlay.md) — 层级渲染叠加
- [2026-09-04-legend-hide-expand-level-reset.md](2026-09-04-legend-hide-expand-level-reset.md) — 图例隐藏/展开
- [2026-09-03-prod-8081-outage-self-inflicted.md](2026-09-03-prod-8081-outage-self-inflicted.md) — prod 8081 自身故障
- [2026-09-03-staging-frontend-stale-dist.md](2026-09-03-staging-frontend-stale-dist.md) — staging dist 陈旧
- [2026-08-26-condition-rule-builder-layout-stale-build.md](2026-08-26-condition-rule-builder-layout-stale-build.md) — 布局陈旧
- [2026-08-21-hide-full-render-elkgroup-pollution.md](2026-08-21-hide-full-render-elkgroup-pollution.md) — ELK 污染
- [2026-06-15-svg-edge-label-centering.md](2026-06-15-svg-edge-label-centering.md) — 居中问题
- [2026-06-12-step-scope-summary-relation-count-fix.md](2026-06-12-step-scope-summary-relation-count-fix.md) — 计数修复
- [2026-06-11-edge-label-truncation.md](2026-06-11-edge-label-truncation.md) — 截断问题

### 🔧 测试方法论
- [2026-06-15-mermaid-test-methodology.md](2026-06-15-mermaid-test-methodology.md) — Mermaid 图 AI 自动化测试

### 📐 架构决策
- [2026-09-13-deploy-topology-generalization.md](2026-09-13-deploy-topology-generalization.md) — DeployTarget + PathResolver + ResourceType 三层抽象
- [2026-09-05-staging-meta-shadow-tree.md](2026-09-05-staging-meta-shadow-tree.md) — meta 包解析路径真相

---

## 模板

新复盘文档应包含:
1. **TL;DR** — 1 段话讲清问题、根因、修复、结果
2. **问题时间线** — 关键事件按时间排序
3. **根因技术细节** — 适合有技术背景的人看
4. **修复代码** — 文件:行号 + 代码片段
5. **调试方法论** — 什么有效, 什么无效
6. **测试缺口 & 改进** — 防止类似问题再发
7. **经验教训** — 跨项目适用的铁律
8. **行动项** — 立即/短期/长期
9. **相关文件清单** — 改动 + 调试脚本 + 数据快照
10. **(可选) 后续补注** — 后续工作追加 (如本文 §14)

---

## 家族反复发生索引

> 反复栽在同一类问题上的家族 — 见各复盘的 "家族盘点" 章节

| 家族 | 主要复盘 | 通用化方案 |
|---|---|---|
| **路径解析 / 双发 / meta 影子** | [9-05](2026-09-05-staging-meta-shadow-tree.md), [9-13](2026-09-13-deploy-topology-generalization.md) | [deploy_topology 框架 + deploy_upload.py CLI](../staging-runbook.md#34-通用部署拓扑-deploy_uploadpy--2026-09-13-推荐) |
| **dist 陈旧 / 旧 dist 跑着** | [9-03 staging-frontend-stale-dist](2026-09-03-staging-frontend-stale-dist.md) | "三条铁律" + md5 != loaded |