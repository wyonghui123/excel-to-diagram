# 🔬 研究文档索引

> **最后更新**: 2026-04-08  
> **维护者**: 开发团队

---

## 📋 研究文档分类

### Mermaid 研究

| 文档 | 主题 | 状态 |
|------|------|------|
| [mermaid-layout-behaviors.md](./mermaid-layout-behaviors.md) | Mermaid 布局行为研究 | 已完成 |
| [mermaid-group-layout-research.md](./mermaid-group-layout-research.md) | 分组布局研究 | 已完成 |
| [mermaid-node-text-solution.md](./mermaid-node-text-solution.md) | 节点文本解决方案 | 已完成 |
| [mermaid-text-centering-debug.md](./mermaid-text-centering-debug.md) | 文本居中调试 | 已完成 |
| [mermaid-connection-highlight-guide.md](./mermaid-connection-highlight-guide.md) | 连接高亮指南 | 已完成 |
| [ELK-NESTED-SUBGRAPH-FIX.md](./ELK-NESTED-SUBGRAPH-FIX.md) | ELK 嵌套子图修复 | 已完成 |

### 布局研究

| 文档 | 主题 | 状态 |
|------|------|------|
| [layout-interaction-framework.md](./layout-interaction-framework.md) | 布局交互框架 | 已完成 |
| [groupModel-refactor-plan.md](./groupModel-refactor-plan.md) | GroupModel 重构计划 | 已完成 |

### 功能实现经验

| 文档 | 主题 | 状态 |
|------|------|------|
| [拖尾线隐藏功能实现经验总结.md](./拖尾线隐藏功能实现经验总结.md) | 拖尾线隐藏功能 | 已完成 |
| [标签虚线方案经验总结.md](./标签虚线方案经验总结.md) | 标签虚线方案 | 已完成 |
| [样式代码优化待办记录.md](./样式代码优化待办记录.md) | 样式优化 | 已完成 |
| [画布背景颜色分层方案经验总结.md](./画布背景颜色分层方案经验总结.md) | 背景颜色分层 | 已完成 |

---

## 🔍 按主题查找

| 遇到的问题 | 查看文档 |
|-----------|---------|
| Mermaid 布局问题 | [mermaid-layout-behaviors.md](./mermaid-layout-behaviors.md) |
| 分组显示问题 | [mermaid-group-layout-research.md](./mermaid-group-layout-research.md) |
| ELK 引擎问题 | [ELK-NESTED-SUBGRAPH-FIX.md](./ELK-NESTED-SUBGRAPH-FIX.md) |
| 节点文本问题 | [mermaid-node-text-solution.md](./mermaid-node-text-solution.md) |
| 连接高亮问题 | [mermaid-connection-highlight-guide.md](./mermaid-connection-highlight-guide.md) |
| 拖尾线隐藏 | [拖尾线隐藏功能实现经验总结.md](./拖尾线隐藏功能实现经验总结.md) |
| 标签虚线 | [标签虚线方案经验总结.md](./标签虚线方案经验总结.md) |

---

## 📝 研究文档规范

### 文档结构

每个研究文档应包含：

```markdown
# [研究主题]

## 研究背景
[为什么进行这项研究]

## 研究过程
[详细的调研和分析过程]

## 研究结论
[得出的结论]

## 应用建议
[如何在项目中使用研究成果]

## 参考资料
[相关的官方文档、示例等]
```

### 命名规范

- 使用小写字母和连字符
- 使用描述性名称
- 中文文档直接使用中文命名

---

## 🔄 维护规则

1. **新增研究**: 完成研究后，将文档放入 `docs/research/`
2. **更新索引**: 新增文档后，更新本 README.md 的索引
3. **定期审查**: 每季度检查研究文档，标记过时内容
4. **知识转化**: 重要的研究成果应转化为经验记录或 ADR

---

## 📚 相关链接

- [经验记录索引](../lessons-learned/README.md)
- [架构决策记录 (ADR)](../../.trae/context/decisions/README.md)
- [工程规范](../../.trae/rules/engineering-guidelines.md)
- [文档中心](../README.md)

---

**最后更新**: 2026-04-08
