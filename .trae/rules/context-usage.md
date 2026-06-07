# Context 使用规则

> 最后更新: 2026-06-07 | 状态: 活跃
> [WARNING] **重要**: 本规则指导 AI 如何有效利用项目 context，避免信息遗漏和过载

---

## 规则 1：决策检查（必须执行）

在实现涉及以下领域的功能时，**必须先查看相关 ADR**：

| 任务类型 | 必须查看的 ADR | 原因 |
|---------|---------------|------|
| Mermaid 图表生成 | [ADR-001](../context/decisions/adr-001-mermaid.md) | 了解 Mermaid 的选择理由和限制 |
| 布局引擎相关 | ADR-002 | ELK 和 Dagre 方向映射不同 |
| 图表导出功能 | ADR-001 | 了解导出能力和限制 |
| **元模型/Schema变更** | [meta-model-schema-sync.md](./meta-model-schema-sync.md) | 了解元模型驱动Schema更新流程 |

**执行步骤**:
1. 查看 ADR 索引：`.trae/context/decisions/README.md`
2. 根据任务类型找到相关 ADR
3. 阅读详情文件
4. 确保实现符合决策要求

---

## 规则 1.1：UI规范检查（必须执行）

**涉及前端UI开发时，必须执行以下检查：**

### 检查清单

| 检查项 | 规范来源 | 执行步骤 |
|--------|---------|---------|
| Tab导航样式 | [ui-design-standards.md](../context/developer/ui-design-standards.md) | 确认使用底部指示线 |
| 侧边导航样式 | 同上 | 确认使用左侧指示线 |
| 文本颜色使用 | 同上 | 确认使用正确的颜色变量 |
| 滚动条样式 | 同上 | 确认使用浏览器默认 |
| 组件复用 | 同上 | 检查是否有现有组件可复用 |

### 执行步骤

1. **查看UI规范文档**
   ```bash
   # 快速参考
   读取 .trae/context/developer/ui-design-standards.md
   
   # 详细规范
   读取 docs/UI_COMPONENT_GUIDELINES.md
   ```

2. **检查可用组件**
   ```bash
   读取 src/components/common/index.js
   # 确认以下组件可用：
   # - AppTabs (Tab导航)
   # - AppSideNav (侧边导航)
   # - AuditLog (变更日志)
   # - MetaTable (数据表格)
   # - MetaForm (表单组件)
   # - MetaDialog (表单对话框)
   # - MasterDetailLayout (左右布局) [NEW]
   # - Pagination (分页组件) [NEW]
   # - Drawer (抽屉组件) [NEW]
   ```

3. **开发完成后自检**
   - [ ] Tab是否使用底部指示线？
   - [ ] 侧边导航是否使用左侧指示线？
   - [ ] 是否使用了设计令牌？
   - [ ] 是否避免了全局自定义滚动条？
   - [ ] 组件复用是否最大化？

### 新增功能检查

| 需求 | 使用组件/属性 | 说明 |
|------|-------------|------|
| 表格多选 | MetaTable `selectable` | 行选择功能 |
| 表格分页 | MetaTable `pagination` | 完整分页器 |
| 表单条件显示 | MetaForm `fieldVisibility` | 字段动态显示 |
| 表单字段联动 | MetaForm `fieldDependencies` | 字段互相影响 |
| 选择器分组 | AppSelect 分组选项 | 选项分类显示 |
| Tab溢出处理 | AppTabs `overflowMode` | 下拉菜单/滚动 |
| 侧边导航折叠 | AppSideNav `collapsible` | 可折叠导航 |
| 密码显示切换 | AppInput `showPasswordToggle` | 密码可见切换 |
| 左右布局 | MasterDetailLayout | 主从页面布局 |
| 抽屉弹窗 | Drawer | 右侧滑出面板 |
| 独立分页 | Pagination | 分页组件 |

---

## 规则 2：经验查阅（推荐执行）

遇到以下问题时，**先查阅经验记录**：

| 问题类型 | 经验文档位置 | 关键点 |
|---------|-------------|--------|
| EdgeLabel 样式问题 | `docs/lessons-learned/mermaid/edgeLabel-styling.md` | SVG rect 控制 |
| 布局方向问题 | `docs/lessons-learned/layout/direction-fix.md` | 引擎差异处理 |
| 分组标题显示 | `docs/lessons-learned/layout/group-title.md` | 子图方向配置 |
| 颜色分组问题 | `docs/lessons-learned/layout/color-grouping.md` | GroupModel 管理 |
| **理解业务模型** | `meta/schemas/README.md` | YAML 元模型定义 |

**执行步骤**:
1. 查看 `docs/lessons-learned/README.md` 索引
2. 找到相关主题的经验文档
3. 参考历史解决方案
4. 避免重复踩坑

---

## 规则 3：任务聚焦与角色Context加载

开始新任务时，根据任务类型自动激活对应角色并加载专属Context：

### 角色Context加载规则

| 任务类型 | 激活角色 | 加载Context | 首选Skill |
|---------|---------|------------|----------|
| 需求分析、产品方向、UX设计、竞品调研 | PM | `.trae/context/pm/` | brainstorming |
| 架构设计、技术选型、元模型变更 | Architect | `.trae/context/architect/` | writing-plans |
| 功能实现、Bug修复、代码重构 | Developer | `.trae/context/developer/` | test-driven-development |
| 代码审查、测试验证、验收 | QA/Reviewer | `.trae/context/reviewer/` | verification-before-completion |
| 部署、发布、运维 | DevOps | `.trae/memory/` | devops-deploy-sop |

### [OK] 必须执行

1. **识别任务类型，激活对应角色**
   - 根据上表匹配关键词
   - 声明当前角色（如"我现在以PM角色工作"）

2. **加载角色专属Context**
   - 只加载当前角色的Context目录
   - 不加载其他角色的Context

3. **确认任务相关的 spec 文件**
   - 位置：`.trae/specs/{feature}/spec.md`
   - 只加载当前功能的 spec

4. **完成后更新 checklist**
   - 位置：`.trae/specs/{feature}/checklist.md`

5. **跨角色协作时切换角色**
   - 明确声明角色切换（如"切换到QA/Reviewer角色"）
   - 加载新角色的Context
   - 卸载前一个角色的Context

### [X] 避免的行为

- 一次性加载所有角色的Context
- 在一个任务中混合多个角色的职责
- 忽略角色切换声明

---

## 规则 4：不确定性标记

当方案中包含以下不确定词汇时：

- "可能"
- "也许"
- "应该可以"
- "理论上"
- "推测"
- "大概"

**必须执行**:

1. **提供完整的测试验证步骤**
   ```markdown
   ## 验证步骤
   1. 刷新页面
   2. 检查控制台日志
   3. 截图对比预期效果
   ```

2. **说明如果测试失败的备选方案**
   ```markdown
   ## 备选方案
   如果方案 A 失败，采用方案 B：...
   ```

3. **记录已知的不确定因素**
   ```markdown
   ## 不确定因素
   - wrappingWidth 参数可能在某些情况下不生效
   - 需要测试不同浏览器兼容性
   ```

---

## 规则 5：修改前检查

修改代码前，**必须执行以下检查**：

### [OK] 检查清单

- [ ] **检查是否有相关的 ADR**
  - 查看 ADR 索引
  - 确认修改不违反决策

- [ ] **检查是否有相关的经验记录**
  - 查看 `docs/lessons-learned/`
  - 参考历史解决方案

- [ ] **确认修改不会违反关键约束**
  - 查看 `.trae/context/README.md` 中的关键约束
  - 确保符合工程规范

- [ ] **评估修改影响范围**
  - 哪些文件会受影响
  - 是否需要更新相关文档

---

## 规则 6：文档更新

完成任务后，**必须更新相关文档**：

### [NOTE] 文档更新清单

| 完成的任务类型 | 需要更新的文档 |
|--------------|---------------|
| 新增功能 | `.trae/specs/{feature}/checklist.md` |
| 修复 Bug | `docs/lessons-learned/` (记录解决方案) |
| 重要技术决策 | `.trae/context/decisions/` (新增 ADR) |
| 修改关键约束 | `.trae/context/README.md` |
| 项目结构变更 | `.trae/engineering-framework.md` |

---

## 规则 7：Context 大小控制

### [INFO] 大小限制

| 文件 | 行数限制 | 原因 |
|------|---------|------|
| `.trae/context/README.md` | < 50 行 | 核心信息，始终加载 |
| `.trae/context/decisions/README.md` | < 30 行 | 索引文件，快速定位 |
| `.trae/rules/*.md` | < 100 行 | 规范文件，避免过载 |

### [INFO] 模块化策略

如果文件超过限制：

1. **拆分为多个文件**
   - 例如：`frontend-rules.md`, `backend-rules.md`

2. **使用索引-详情分离**
   - 索引：简要概述
   - 详情：独立文件

3. **按需加载**
   - 只加载当前任务相关的部分

---

## 规则 8：问题解决流程

遇到问题时，按以下顺序执行：

```
1. 查看 ADR 索引
   ↓
2. 查看经验记录
   ↓
3. 查看相关代码
   ↓
4. 尝试解决方案
   ↓
5. 记录解决方案到经验记录
   ↓
6. 如有重要决策，创建新 ADR
```

---

## 执行示例

### 示例 1：修复布局方向问题

```
[OK] 正确流程：
1. 读取 .trae/context/README.md → 知道 ELK/Dagre 方向相反
2. 读取本规则 → 看到"布局引擎相关 → 查看 ADR-002"
3. 读取 .trae/context/decisions/adr-002-elk-direction.md → 了解具体问题
4. 读取 docs/lessons-learned/layout/direction-fix.md → 查看历史解决方案
5. 定位代码并修复
6. 更新经验记录（如有新发现）
```

### 示例 2：添加新功能

```
[OK] 正确流程：
1. 读取 .trae/context/README.md → 项目概览
2. 读取 .trae/specs/new-feature/spec.md → 功能需求
3. 读取 .trae/rules/engineering-guidelines.md → 编码规范
4. 实现功能
5. 更新 .trae/specs/new-feature/checklist.md
```

---

## 违规后果

如果不遵循这些规则：

- [X] 可能重复犯历史错误
- [X] 可能违反架构决策
- [X] 可能遗漏关键约束
- [X] 可能导致代码质量问题

---

## 维护与更新

本规则应根据项目发展持续更新：

1. **新增常见问题** → 添加到规则 2
2. **新增关键约束** → 更新规则 5
3. **优化工作流** → 更新规则 3、8
4. **定期审查** → 每月检查规则有效性

---

**最后更新**: 2026-04-08 | **修订**: 2026-06-07 (AI Assistant 修复 emoji 违规 + 添加版本元数据)
