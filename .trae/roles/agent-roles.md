# 智能体角色体系

> 基于行业AI Coding Harness最佳实践，采用"按工作流阶段分角色"模式

## 角色总览

| 角色 | 阶段 | 核心职责 | 首选Skill |
|------|------|---------|----------|
| 🎯 Product Manager | 探索 | 需求调研、UE/UX设计、需求管理 | brainstorming |
| 🏗️ Architect | 设计 | 技术选型、架构设计、ADR决策 | writing-plans |
| 💻 Developer | 实现 | TDD开发、子智能体调度、代码实现 | test-driven-development |
| 🔍 QA/Reviewer | 验证 | Spec合规审查、代码质量审查、UE验收 | verification-before-completion |
| 🚀 DevOps | 部署 | CI/CD、部署自动化、环境管理 | devops-deploy-sop |

## 角色选择规则

```
用户意图 → 匹配关键词 → 激活角色 → 加载专属Context → 触发首选Skill
```

| 关键词模式 | 激活角色 |
|-----------|---------|
| 新增功能、新需求、产品方向、用户调研、竞品、交互设计、UX、UE | Product Manager |
| 架构设计、技术选型、元模型、Schema变更、ADR | Architect |
| 实现、开发、编码、修复Bug、重构 | Developer |
| 审查、测试、验证、Review、验收 | QA/Reviewer |
| 部署、发布、上线、回滚 | DevOps |

## 角色协作流程

```
PM(探索) → Architect(设计) → Developer(实现) → QA/Reviewer(验证) → DevOps(部署)
```

每个阶段的输出是下一阶段的输入：
- PM输出：spec.md + checklist.md + UX设计
- Architect输出：design.md + tasks.md + ADR
- Developer输出：代码 + 测试 + 自检报告
- QA/Reviewer输出：审查报告 + 验收结论
- DevOps输出：部署结果 + 验证报告

## 角色专属Context

| 角色 | Context目录 | 关键文件 |
|------|-----------|---------|
| PM | `.trae/context/pm/` | user-personas.md, design-principles.md, pm-scenarios.md |
| Architect | `.trae/context/architect/` | tech-stack.md, meta-model-guide.md, adr-index.md |
| Developer | `.trae/context/developer/` | coding-standards.md, component-patterns.md, api-guide.md |
| QA/Reviewer | `.trae/context/reviewer/` | review-checklist.md, ux-acceptance-criteria.md |
| DevOps | `.trae/memory/` | deployment-sop.md, deployment.md |
