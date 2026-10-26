---
description: Trae SOLO Spec 模式使用指南 - 涉及 3 阶段文档生成(SPEC/TASKS/CHECKLIST)、系统级重构、复杂任务规划时加载。封装 spec.md/tasks.md/checklist.md 模板 + 与项目已有 spec 流程关系。
globs: ["**/.trae/specs/**", "**/spec.md", "**/tasks.md", "**/checklist.md"]
version: "0.1.0"
author: "AI"
last_updated: "2026-09-02"
---

# Trae SOLO Spec 模式使用指南 (v5.4)

> **官方定义**（来自 [docs.trae.cn/ide/solo-coder](https://docs.trae.cn/ide/solo-coder)）：
> Spec 模式面向更复杂的系统级任务。SOLO Agent 会根据你的需求生成完整的三阶段文档组。

---

## 1. Spec 模式启用

```
对话输入框 → 输入 / → 模式选择列表 → /Spec
```

**前置条件**：已切换至 SOLO 模式（左上角模式切换按钮）。

---

## 2. 三阶段文档结构

```
项目根目录/.trae/specs/<task-name>/
├── spec.md          # 第 1 阶段：大纲
├── tasks.md         # 第 2 阶段：任务列表
└── checklist.md     # 第 3 阶段：验收清单
```

### 2.1 spec.md（大纲）

包含：
- 项目背景与目标
- 范围与非范围（in/out of scope）
- 架构决策
- 模块划分
- 数据模型
- API 设计
- 风险评估

### 2.2 tasks.md（任务列表）

包含：
- 拆解的可执行任务
- 每个任务的依赖关系
- 优先级与预估工时
- 责任人/Agent 分配

### 2.3 checklist.md（验收清单）

包含：
- 功能验收项
- 非功能验收项（NFR）
- 边界条件
- 回归测试要求
- 上线/部署标准

---

## 3. 5 类适用场景

| 场景 | 原因 |
|------|------|
| **从零搭建新系统/模块** | 需求范围大、架构决策多，必须先对齐大纲 |
| **大规模重构** | 架构级 / 技术栈迁移，涉及大量文件和模块依赖 |
| **多人协作项目** | Spec 文档作为单一事实来源（SSOT）|
| **高质量/高稳定性项目** | 核心业务/支付/安全模块，需详尽验收清单 |
| **需长期维护的项目** | Spec 文档留存为项目知识资产 |

---

## 4. 与本项目 v5.0 spec/rf c 流程的关系

### 4.1 现状（v5.0）

项目已有 spec-rfc Skill（`spec/rfc`），用于多步骤任务的实现规划：
- 使用 Spec 模式生成 3 阶段文档
- 已用于 v4.0 worktree 治理、v5.0 服务治理等多个 spec

### 4.2 关系

| 维度 | Trae SOLO Spec | 项目 spec/rf c Skill |
|------|---------------|---------------------|
| **文档位置** | `.trae/specs/<task>/` | `excel-to-diagram/spec/rf c/` |
| **生成方式** | SOLO Agent 自动 | AI 通过 spec-rfc Skill |
| **3 阶段结构** | ✅ spec.md/tasks.md/checklist.md | ✅ 同样结构 |
| **版本控制** | 长期保留（项目知识资产）| 长期保留 |

**结论**：两者结构兼容，可共用模板。

### 4.3 推荐升级

未来 spec 文档可考虑：
1. **统一目录**：Trae SOLO 自动生成到 `.trae/specs/`，项目 spec-rfc 生成到 `spec/rfc/`
2. **统一模板**：项目 spec-rfc Skill 可复用 Trae SOLO 的模板
3. **互通**：Trae SOLO 生成的 spec 可通过 `git mv` 移到 `spec/rfc/`，反之亦可

---

## 5. 何时使用 Spec vs Plan

### 5.1 Plan 模式

- **适用**：中小型功能开发、模块级重构
- **生成**：一份规划文档
- **确认后**：SOLO Agent 一一执行

### 5.2 Spec 模式

- **适用**：复杂系统级任务（见第 3 节）
- **生成**：3 阶段文档组（spec.md/tasks.md/checklist.md）
- **确认后**：按 tasks.md 自动推进，checklist.md 状态自动更新

---

## 6. 关键决策点

### 6.1 何时开始 Spec

在以下情况启动 Spec 模式：
- 需求涉及 ≥ 3 个文件模块
- 涉及架构决策或技术栈选择
- 涉及多人/多 Agent 协作
- 涉及破坏性变更

### 6.2 何时跳过 Spec

- Bug 修复（单文件 ≤ 50 行改动）
- 简单的样式调整
- 单测补充
- 文档更新

### 6.3 文档编辑权限

首次创建后，SOLO Agent 会暂停执行并等待确认。在此阶段你可以：
- ✅ 直接编辑文档
- ✅ 用自然语言告诉 SOLO Agent 修改需求
- ❌ 不要跳过确认直接执行（可能导致偏离预期）

---

## 7. 实操流程

### 7.1 启动

```
1. 切换 SOLO 模式
2. 对话输入 /Spec
3. 描述需求（如"实现用户权限矩阵 v2.0"）
4. SOLO Agent 生成 3 阶段文档
5. 审查文档（手动编辑或对话修改）
6. 确认执行
```

### 7.2 跟踪

- 任务执行进度：在对话面板查看
- checklist 状态：自动更新
- 中途修改：可发送修改需求，SOLO Agent 调整文档后继续

### 7.3 收尾

- 3 阶段文档入仓（Git 版本控制）
- 标记为 SSOT
- 后续维护时引用

---

## 8. 参考

- [docs.trae.cn/ide/solo-coder](https://docs.trae.cn/ide/solo-coder) —— SOLO Agent
- [docs.trae.cn/ide/solo-mode](https://docs.trae.cn/ide/solo-mode) —— SOLO 模式概览
- v5.4 深度研究：[2026-09-02-trae-ide-v5.4-deep-research.md](../../../excel-to-diagram/docs/governance/2026-09-02-trae-ide-v5.4-deep-research.md)
- spec-rfc Skill：`excel-to-diagram/.trae/skills/spec-rfc/SKILL.md`（如存在）