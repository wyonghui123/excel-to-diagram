# 💡 经验记录索引

> **最后更新**: 2026-04-08  
> **维护者**: 开发团队

---

## 📋 经验分类

### [Mermaid 相关经验](./mermaid/)

Mermaid 图表生成、样式、渲染相关问题的解决方案

| 文档 | 问题 | 解决方案 | 关键点 |
|------|------|---------|--------|
| [edgeLabel-styling.md](./mermaid/edgeLabel-styling.md) | EdgeLabel 白色背景问题 | CSS + JavaScript 混合方案 | foreignObject + HTML 样式 |
| [layout-direction-fix.md](./mermaid/layout-direction-fix.md) | 布局方向颠倒问题 | 引擎特定方向转换 | ELK vs Dagre 差异 |

### [布局相关经验](./layout/)

布局引擎、分组、方向相关问题的解决方案

| 文档 | 问题 | 解决方案 | 关键点 |
|------|------|---------|--------|
| [group-title.md](./layout/group-title.md) | 分组标题显示问题 | 子图方向配置 | subGraphTitleMargin |
| [color-grouping.md](./layout/color-grouping.md) | 颜色分组管理 | GroupModel 管理 | 颜色映射策略 |

### [Element Plus 相关经验](./element-plus/)

Element Plus UI 组件库的踩坑与解决方案

| 文档 | 问题 | 解决方案 | 关键点 |
|------|------|---------|--------|
| [dropdown-modal-occlusion.md](./element-plus/dropdown-modal-occlusion.md) | 弹窗内下拉被遮罩看不到 | `:teleported="false"` + 父级 `overflow: visible` | Teleport + z-index 战争 |

### [调试经验](./debugging/)

常见问题的调试方法和技巧

| 文档 | 问题类型 | 调试方法 | 关键工具 |
|------|---------|---------|---------|
| [mermaid-debugging.md](./debugging/mermaid-debugging.md) | Mermaid 渲染问题 | DOM 结构分析 | console.log + DevTools |

---

## 🔍 按问题类型查找

| 遇到的问题 | 查看哪个文档 |
|-----------|-------------|
| EdgeLabel 有白色背景 | [mermaid/edgeLabel-styling.md](./mermaid/edgeLabel-styling.md) |
| 布局方向颠倒 | [mermaid/layout-direction-fix.md](./mermaid/layout-direction-fix.md) |
| 分组标题不显示 | [layout/group-title.md](./layout/group-title.md) |
| 颜色分组问题 | [layout/color-grouping.md](./layout/color-grouping.md) |
| Mermaid 渲染异常 | [debugging/mermaid-debugging.md](./debugging/mermaid-debugging.md) |
| 弹窗内下拉被遮罩看不到 | [element-plus/dropdown-modal-occlusion.md](./element-plus/dropdown-modal-occlusion.md) |
| 测试"通过"但实际 UI 不可见 | [testing/testability-iron-rules.md](./testing/testability-iron-rules.md) |

---

## 📝 经验记录规范

### 文档结构

每个经验记录应包含：

```markdown
# [问题标题]

## 问题描述
[清晰描述问题现象]

## 问题原因
[分析问题根本原因]

## 解决方案
[详细的解决方案步骤]

## 代码示例
[关键代码片段]

## 经验总结
[总结关键经验和注意事项]

## 相关文档
[关联的 ADR 或其他文档]

## 相关代码
[关联的代码文件]
```

### 命名规范

- 使用小写字母和连字符：`edgeLabel-styling.md`
- 使用描述性名称：`layout-direction-fix.md`
- 包含问题类型：`mermaid-xxx.md`, `layout-xxx.md`

---

## 🔄 维护规则

1. **新增经验**: 解决新问题后，立即记录到相应分类目录
2. **更新索引**: 新增文档后，更新本 README.md 的索引
3. **定期审查**: 每月检查经验记录，归档过时内容
4. **关联 ADR**: 如有重要决策，同步创建或更新 ADR

---

## 📚 相关链接

- [架构决策记录 (ADR)](../../.trae/context/decisions/README.md)
- [工程规范](../../.trae/rules/engineering-guidelines.md)
- [Context 使用规则](../../.trae/rules/context-usage.md)
- [文档中心](../README.md)

---

**最后更新**: 2026-04-08
