# Excel转Diagram工具 - 工程框架规范

> **文档版本**: v1.0  
> **创建日期**: 2026-04-08  
> **最后更新**: 2026-04-08  
> **维护者**: 开发团队

---

## 📋 目录

1. [设计原则](#设计原则)
2. [总体目录结构](#总体目录结构)
3. [Context分层架构](#context分层架构)
4. [工作流映射](#工作流映射)
5. [文件职责说明](#文件职责说明)
6. [分步执行计划](#分步执行计划)
7. [维护与演进](#维护与演进)

---

## 🎯 设计原则

### 核心原则

| 原则 | 说明 | 实现方式 |
|------|------|---------|
| **最小必要信息** | context/ 只包含核心信息（< 50 行） | 精简 README.md |
| **索引-详情分离** | 索引始终可见，详情按需加载 | ADR 索引 + 详情文件 |
| **规则驱动查阅** | 通过 rules/ 提示 AI 何时查阅详细信息 | context-usage.md |
| **分层加载** | 核心层 → 规范层 → 决策层 → 功能层 → 知识层 | 目录结构设计 |
| **Feature-First** | 按功能组织代码，而非按文件类型 | src/features/ 结构 |

### AI Coding 最佳实践

基于行业研究和实践总结：

1. **Spec-Driven Development**: 先写规范，再写代码
2. **Fresh Agent Context**: 每个阶段使用独立的上下文
3. **Context Engineering**: 分层管理上下文，避免信息过载
4. **ADR (Architecture Decision Records)**: 记录重要技术决策
5. **经验沉淀**: 将调试经验、解决方案分类整理

---

## 📁 总体目录结构

```
excel-to-diagram/
│
├── .trae/                              # 🤖 AI 辅助开发配置（Trae IDE）
│   ├── engineering-framework.md        # ⭐ 本文档：工程框架规范
│   │
│   ├── context/                        # Layer 0: 核心层（始终加载）
│   │   ├── README.md                   # 项目概览（< 50 行）
│   │   ├── decisions/                  # ADR 架构决策记录
│   │   │   ├── README.md               # ADR 索引（标题+状态+关键词）
│   │   │   ├── adr-001-xxx.md          # ADR 详情
│   │   │   ├── adr-002-xxx.md
│   │   │   └── template.md             # ADR 模板
│   │   └── quick-reference.md          # 快速参考（可选）
│   │
│   ├── rules/                          # Layer 1: 规范层（始终应用）
│   │   ├── engineering-guidelines.md   # 工程规范
│   │   ├── context-usage.md            # ⭐ Context 使用规则
│   │   ├── frontend-rules.md           # 前端规范（可选）
│   │   └── testing-rules.md            # 测试规范（可选）
│   │
│   ├── specs/                          # Layer 2: 功能层（按需加载）
│   │   └── {feature}/
│   │       ├── spec.md                 # 需求规格（What）
│   │       ├── design.md               # 技术设计（How）
│   │       ├── checklist.md            # 验收清单（Done criteria）
│   │       └── tasks.md                # 任务分解（Implementation steps）
│   │
│   └── skills/                         # Layer 3: 技能层（按需调用）
│       └── excel-to-diagram/
│           ├── SKILL.md
│           └── package.json
│
├── docs/                               # 📚 人类可读文档
│   ├── README.md                       # 文档导航索引
│   │
│   ├── research/                       # 🔬 研究与调研
│   │   ├── README.md                   # 研究索引
│   │   └── *.md                        # 研究文档
│   │
│   ├── design/                         # 🎨 设计文档
│   │   ├── README.md                   # 设计索引
│   │   └── *.md                        # 设计文档
│   │
│   ├── guides/                         # 📖 使用指南
│   │   ├── user-guide.md               # 用户手册
│   │   ├── deployment-guide.md         # 部署指南
│   │   └── api-reference.md            # API 参考
│   │
│   ├── testing/                        # 🧪 测试文档
│   │   ├── README.md                   # 测试索引
│   │   ├── test-plan.md                # 测试计划
│   │   ├── test-cases/                 # 测试用例
│   │   └── test-reports/               # 测试报告
│   │
│   ├── lessons-learned/                # 💡 经验记录
│   │   ├── README.md                   # 经验索引（按主题分类）
│   │   ├── mermaid/                    # Mermaid 相关经验
│   │   │   ├── edgeLabel-styling.md
│   │   │   └── layout-direction-fix.md
│   │   ├── layout/                     # 布局相关经验
│   │   └── debugging/                  # 调试经验
│   │
│   └── archive/                        # 📦 归档文档
│       ├── analysis/                   # 历史分析文档
│       └── deprecated/                 # 废弃文档
│
├── src/                                # 💻 源代码（Feature-First 组织）
│   ├── features/                       # 功能模块
│   │   ├── diagram/                    # 图表生成功能
│   │   │   ├── components/             # 图表相关组件
│   │   │   ├── composables/            # 图表相关 hooks
│   │   │   ├── services/               # 图表业务逻辑
│   │   │   ├── layouts/                # 布局算法
│   │   │   ├── syntax/                 # Mermaid 语法生成
│   │   │   └── types/                  # 类型定义
│   │   ├── upload/                     # 文件上传功能
│   │   │   ├── components/
│   │   │   └── composables/
│   │   └── annotation/                 # 标注功能
│   │       ├── components/
│   │       └── composables/
│   │
│   ├── shared/                         # 共享模块
│   │   ├── components/                 # 通用 UI 组件
│   │   │   ├── AppButton.vue
│   │   │   ├── AppHeader.vue
│   │   │   └── index.js
│   │   ├── composables/                # 通用 hooks
│   │   │   ├── useExcelParser.js
│   │   │   └── useLayoutControl.js
│   │   ├── services/                   # 通用服务
│   │   │   ├── api/
│   │   │   └── validators/
│   │   └── utils/                      # 工具函数
│   │
│   ├── views/                          # 页面组件
│   │   ├── AADiagramApp/
│   │   │   ├── components/
│   │   │   │   ├── steps/
│   │   │   │   ├── GroupItem.vue
│   │   │   │   ├── LayoutControlPanel.vue
│   │   │   │   └── LayoutSelector.vue
│   │   │   └── composables/
│   │   └── ConfigApp.vue
│   │
│   ├── assets/                         # 静态资源
│   │   ├── styles/
│   │   │   ├── index.scss
│   │   │   ├── variables.scss
│   │   │   └── mixins.scss
│   │   └── images/
│   │
│   ├── App.vue                         # 根组件
│   └── main.js                         # 入口文件
│
├── tests/                              # 🧪 测试代码
│   ├── unit/                           # 单元测试
│   ├── integration/                    # 集成测试
│   └── e2e/                            # 端到端测试
│
├── .archive/                           # 📦 历史归档（不提交到 Git）
│   └── backups/
│       └── 2026-04-08-pre-refactor/
│           └── README.md
│
├── api/                                # API 服务
│   ├── deepseek.js
│   └── zhipu.js
│
├── electron/                           # Electron 配置
│   ├── main.js
│   └── preload.js
│
├── server/                             # 后端服务
│   ├── package.json
│   └── server.js
│
├── .env.example                        # 环境变量示例
├── .gitignore
├── package.json
└── README.md                           # 项目 README
```

---

## 🏗️ Context分层架构

### 分层设计

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 0: 核心层（始终加载）                                    │
│ .trae/context/README.md                                      │
│ - 项目定位、技术栈、关键约束                                   │
│ - < 50 行，快速理解项目                                       │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: 规范层（始终应用）                                    │
│ .trae/rules/*.md                                             │
│ - 工程规范、Context 使用规则                                   │
│ - 指导 AI 行为，确保代码质量                                   │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: 决策层（索引加载，详情按需）                           │
│ .trae/context/decisions/README.md                            │
│ - ADR 索引（标题+状态+关键词）                                 │
│ - 需要时查看具体 ADR 详情                                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: 功能层（按需加载）                                    │
│ .trae/specs/{feature}/                                       │
│ - 当前功能的 spec、design、tasks                              │
│ - 聚焦当前任务，避免其他功能干扰                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: 知识层（按需查阅）                                    │
│ docs/lessons-learned/, docs/research/                        │
│ - 经验记录、详细文档、历史分析                                  │
│ - AI 需要时可以查阅，但不自动加载                               │
└─────────────────────────────────────────────────────────────┘
```

### Context 使用规则

详见 `.trae/rules/context-usage.md`，核心规则：

1. **决策检查**: 涉及特定领域时必须先查看相关 ADR
2. **经验查阅**: 遇到特定问题时先查阅经验记录
3. **任务聚焦**: 只加载当前功能的 spec
4. **不确定性标记**: 包含不确定词汇时必须提供验证步骤

---

## 🔄 工作流映射

### 完整工作流

```
Research & 需求分析
    ↓
    ├─→ .trae/specs/{feature}/spec.md          # 需求规格
    └─→ .trae/context/decisions/adr-xxx.md     # 相关决策（如有）
    
Spec 迭代
    ↓
    ├─→ .trae/specs/{feature}/spec.md          # 更新需求
    └─→ .trae/specs/{feature}/checklist.md     # 验收清单
    
Design
    ↓
    ├─→ .trae/specs/{feature}/design.md        # 技术设计
    └─→ docs/design/                           # 详细设计文档（可选）
    
统一文档
    ↓
    ├─→ docs/guides/user-guide.md              # 用户手册
    ├─→ docs/guides/api-reference.md           # API 参考
    └─→ docs/guides/deployment-guide.md        # 部署指南
    
代码开发
    ↓
    ├─→ src/features/{feature}/                # 功能代码
    ├─→ src/shared/                            # 共享代码
    └─→ .trae/rules/engineering-guidelines.md  # 遵循规范
    
测试
    ↓
    ├─→ tests/unit/                            # 单元测试
    ├─→ tests/integration/                     # 集成测试
    ├─→ docs/testing/test-plan.md              # 测试计划
    └─→ docs/testing/test-reports/             # 测试报告
    
经验记录
    ↓
    ├─→ docs/lessons-learned/{topic}/          # 经验文档
    └─→ .trae/context/decisions/adr-xxx.md     # 新增 ADR（如有重要决策）
    
备份
    ↓
    └─→ .archive/backups/{date}/               # 历史备份
```

### 文档生命周期

| 阶段 | 文档位置 | 文件类型 | 状态变化 |
|------|---------|---------|---------|
| Research | `.trae/specs/{feature}/spec.md` | spec.md | Draft → Review → Approved |
| Design | `.trae/specs/{feature}/design.md` | design.md | Draft → Review → Approved |
| Implementation | `src/features/{feature}/` | .vue, .js, .ts | Active |
| Testing | `tests/`, `docs/testing/` | test-*.js, test-report.md | Active → Completed |
| Lessons Learned | `docs/lessons-learned/` | *.md | Active → Archived |
| ADR | `.trae/context/decisions/` | adr-*.md | Proposed → Accepted → Deprecated |

---

## 📄 文件职责说明

### .trae/ 目录

| 文件/目录 | 职责 | 更新频率 | 大小限制 |
|----------|------|---------|---------|
| `context/README.md` | 项目核心信息，AI 每次都会看到 | 项目重大变更时 | < 50 行 |
| `context/decisions/README.md` | ADR 索引，快速定位决策 | 新增 ADR 时 | < 30 行 |
| `context/decisions/adr-*.md` | ADR 详情，记录重要技术决策 | 决策变更时 | 无限制 |
| `rules/engineering-guidelines.md` | 工程规范，确保代码质量 | 规范变更时 | < 100 行 |
| `rules/context-usage.md` | Context 使用规则，指导 AI 行为 | 规则变更时 | < 80 行 |
| `specs/{feature}/spec.md` | 功能需求规格 | 需求变更时 | 无限制 |
| `specs/{feature}/design.md` | 技术设计文档 | 设计变更时 | 无限制 |
| `specs/{feature}/checklist.md` | 验收清单 | 功能完成时 | 无限制 |
| `specs/{feature}/tasks.md` | 任务分解 | 任务完成时 | 无限制 |

### docs/ 目录

| 文件/目录 | 职责 | 更新频率 | 目标读者 |
|----------|------|---------|---------|
| `README.md` | 文档导航索引 | 新增文档时 | 所有人 |
| `research/` | 研究与调研文档 | 研究完成时 | 开发者 |
| `design/` | 设计文档 | 设计变更时 | 开发者、架构师 |
| `guides/` | 使用指南 | 功能变更时 | 用户、开发者 |
| `testing/` | 测试文档 | 测试完成时 | QA、开发者 |
| `lessons-learned/` | 经验记录 | 问题解决时 | 开发者 |
| `archive/` | 归档文档 | 文档废弃时 | 历史参考 |

### src/ 目录

| 目录 | 职责 | 组织方式 |
|------|------|---------|
| `features/` | 功能模块代码 | Feature-First，每个功能独立目录 |
| `shared/` | 共享代码 | 按类型组织（components/composables/services/utils） |
| `views/` | 页面组件 | 按页面组织，每个页面独立目录 |
| `assets/` | 静态资源 | 按类型组织（styles/images） |

---

## 📋 分步执行计划

### Phase 1: 清理与准备（低风险，立即执行）

**目标**: 清理废弃文件，建立基础结构

**任务清单**:
- [ ] 1.1 删除所有 `.backup` 文件
  - 删除 `src/components/MermaidComponent.vue.backup*`（8个文件）
  - 删除 `src/App.vue.backup`
  - 删除 `src/services/serviceModuleDiagramBuilder.js.backup.20260320_143000`
  
- [ ] 1.2 删除 backup 目录
  - 删除 `backup/` 目录
  - 删除 `backup_20260325_172823/` 目录
  
- [ ] 1.3 创建归档目录
  - 创建 `.archive/backups/` 目录
  - 更新 `.gitignore` 添加 `.archive/`
  
- [ ] 1.4 创建文档索引
  - 创建 `docs/README.md` 作为文档导航

**预计时间**: 15 分钟  
**风险等级**: 🟢 低

---

### Phase 2: Context 优化（低风险，立即执行）

**目标**: 优化 AI 可读的 context，建立分层架构

**任务清单**:
- [ ] 2.1 精简核心 context
  - 精简 `.trae/context/README.md` 到 < 50 行
  - 确保包含：项目定位、技术栈、关键约束、快速导航
  
- [ ] 2.2 创建 ADR 索引
  - 创建 `.trae/context/decisions/README.md`
  - 将现有 ADR 整理到索引中
  - 添加关键词映射
  
- [ ] 2.3 创建 Context 使用规则
  - 创建 `.trae/rules/context-usage.md`
  - 定义决策检查规则
  - 定义经验查阅规则
  - 定义任务聚焦规则
  
- [ ] 2.4 更新现有 ADR
  - 将 `docs/adr/` 下的 ADR 移动到 `.trae/context/decisions/`
  - 更新 ADR 格式，添加关键词

**预计时间**: 30 分钟  
**风险等级**: 🟢 低

---

### Phase 3: 文档重组（中等风险，需规划）

**目标**: 整理现有文档，建立清晰的文档结构

**任务清单**:
- [ ] 3.1 创建文档目录结构
  - 创建 `docs/research/`
  - 创建 `docs/design/`
  - 创建 `docs/guides/`
  - 创建 `docs/testing/`
  - 创建 `docs/lessons-learned/`
  - 创建 `docs/archive/`
  
- [ ] 3.2 整理经验记录
  - 合并 `docs/analysis/` 下的 edgeLabel 相关文档
  - 创建 `docs/lessons-learned/mermaid/edgeLabel-styling.md`
  - 创建 `docs/lessons-learned/layout/direction-fix.md`
  - 创建 `docs/lessons-learned/README.md` 索引
  
- [ ] 3.3 整理研究文档
  - 移动 `docs/mermaid-*.md` 到 `docs/research/`
  - 移动 `docs/ELK-NESTED-SUBGRAPH-FIX.md` 到 `docs/research/`
  - 创建 `docs/research/README.md` 索引
  
- [ ] 3.4 归档临时文档
  - 移动 `docs/analysis/` 到 `docs/archive/analysis/`
  - 移动 `docs/优化建议/` 到 `docs/archive/`
  - 移动 `docs/经验记录/` 到 `docs/lessons-learned/`（已整理的部分）

**预计时间**: 45 分钟  
**风险等级**: 🟡 中

---

### Phase 4: 代码重构（高风险，需详细规划）

**目标**: 按 Feature-First 原则重组代码

**任务清单**:
- [ ] 4.1 创建 features 目录结构
  - 创建 `src/features/diagram/`
  - 创建 `src/features/upload/`
  - 创建 `src/features/annotation/`
  
- [ ] 4.2 迁移图表功能代码
  - 移动 `src/composables/useMermaid/` 到 `src/features/diagram/`
  - 移动 `src/composables/useBlockDiagram/` 到 `src/features/diagram/`
  - 移动 `src/services/groupModel/` 到 `src/features/diagram/services/`
  - 更新所有导入路径
  
- [ ] 4.3 创建 shared 目录
  - 移动 `src/components/common/` 到 `src/shared/components/`
  - 移动 `src/composables/useExcelParser.js` 到 `src/shared/composables/`
  - 移动 `src/composables/useLayoutControl.js` 到 `src/shared/composables/`
  - 移动 `src/utils/` 到 `src/shared/utils/`
  
- [ ] 4.4 更新视图结构
  - 移动 `src/components/AADiagramApp.vue` 到 `src/views/AADiagramApp/index.vue`
  - 移动 `src/views/AADiagramApp/components/` 保持不变
  - 移动其他页面级组件到 `src/views/`
  
- [ ] 4.5 更新所有导入路径
  - 使用 IDE 的重构功能批量更新
  - 运行测试确保无破坏性变更

**预计时间**: 2-3 小时  
**风险等级**: 🔴 高  
**建议**: 创建新分支进行重构，完成后合并

---

### Phase 5: 测试与验证（必需）

**目标**: 确保重构后项目正常运行

**任务清单**:
- [ ] 5.1 运行所有测试
  - 单元测试
  - 集成测试
  - E2E 测试
  
- [ ] 5.2 手动验证核心功能
  - 文件上传
  - 图表生成
  - 布局切换
  - 颜色分组
  
- [ ] 5.3 检查 AI context 是否正常工作
  - 验证 `.trae/context/README.md` 是否被正确加载
  - 验证 ADR 索引是否可用
  - 验证规则是否生效
  
- [ ] 5.4 更新文档
  - 更新 `.trae/context/README.md` 反映新的目录结构
  - 更新 `docs/README.md` 文档导航
  - 更新项目根目录 `README.md`

**预计时间**: 1 小时  
**风险等级**: 🟡 中

---

## 🔧 维护与演进

### 文档维护规则

1. **定期审查**（每月）
   - 检查 `.trae/context/README.md` 是否需要更新
   - 检查 ADR 状态是否需要变更
   - 检查经验记录是否需要归档

2. **新增功能时**
   - 在 `.trae/specs/{feature}/` 创建规范
   - 完成后更新 `checklist.md`
   - 如有重要决策，创建新 ADR

3. **解决问题后**
   - 在 `docs/lessons-learned/` 记录经验
   - 如有通用规则，添加到 `.trae/rules/`

4. **重构时**
   - 更新本文档（`engineering-framework.md`）
   - 更新 `.trae/context/README.md`
   - 更新相关 ADR

### 版本控制

本文档使用语义化版本：

- **Major (v1.0 → v2.0)**: 结构重大变更
- **Minor (v1.0 → v1.1)**: 新增目录或规则
- **Patch (v1.0.0 → v1.0.1)**: 文档修正

### 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
|------|------|---------|--------|
| v1.0 | 2026-04-08 | 初始版本，建立工程框架规范 | 开发团队 |

---

## 📚 参考资料

### AI Coding 最佳实践

- [Spec-Driven Development](https://github.com/mkrtchian/spec-driven-dev)
- [Claude Code Best Practices](https://github.com/luiseiman/claude-kit/blob/main/docs/best-practices.md)
- [Feature-Sliced Design](https://feature-sliced.design/)
- [Architecture Decision Records](https://github.com/Alexey-Popov/awesome-ai-architect/blob/main/solution-architecture/architecture-decision-records.md)

### Vue.js 项目结构

- [Vue.js 风格指南](https://vuejs.org/style-guide/)
- [Vue 3 组合式 API](https://vuejs.org/guide/extras/composition-api-faq.html)

---

## 📞 联系方式

如有问题或建议，请联系：
- 项目维护者：开发团队
- 文档维护：开发团队

---

**最后更新**: 2026-04-08
