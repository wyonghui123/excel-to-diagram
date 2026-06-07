# 文档规范（Documentation Standards）

> 项目所有 Markdown 文档的编写规范
> 最后更新: 2026-06-07

## 1. 文档分类体系

项目文档按生命周期分为四类：

| 类别 | 目录 | 用途 | 命名规范 |
|------|------|------|---------|
| **核心架构** | `docs/` 顶层 + `architecture/` | 长期维护的架构文档 | 全大写下划线（ARCHITECTURE_V2.md），允许历史命名 |
| **设计规范** | `specs/`, `architecture/02-04` | RFC、设计规范、契约 | 小写中划线（spec-key-template.md） |
| **进度报告** | `progress/` | 历史进度报告 | 小写中划线，**历史报告归档** |
| **复盘** | `retrospectives/` | bug 复盘、问题总结 | 日期前缀（2026-06-04-*.md） |

## 2. 命名规范

### 2.1 推荐风格（小写中划线）

```
# 推荐 ✅
spec-key-template.md
fix-permission-bug.md
2026-06-04-ui-color-issues.md
page-type-matrix.md
yaml-child-list-config-example.md

# 避免 ❌
Spec_权限体系元数据驱动化.md   # 中英混合
需求文档.md                      # 全中文
FIX_UPDATED_AT_SSOT_P4.md      # 全大写（仅历史报告）
AI-CODING-E2E-DEEP-DIVE.md     # 全大写中划线
```

### 2.2 特殊场景

| 场景 | 命名 | 示例 |
|------|------|------|
| 复盘 | `YYYY-MM-DD-{topic}.md` | `2026-06-04-relation-scope-tree-bug.md` |
| 进度报告 | `bo-action-v{version}-result.md` | `bo-action-v3.18-result.md` |
| 编号子文档 | `{NN}-{topic}.md`（NN 两位） | `01-principles.md` |
| 索引 | `README.md` 或 `INDEX.md` | `docs/README.md` |
| 专题索引 | `{TOPIC}_INDEX.md` | `PERMISSION_SYSTEM_INDEX.md` |

## 3. Frontmatter（元数据）

所有新文档必须包含 frontmatter：

```markdown
---
title: 文档标题
version: 3.0.2
date: 2026-06-07
status: 活跃 | 冻结 | 归档 | 废弃
audience: AI Agent | 开发者 | 架构师 | 全员
---

# 文档标题
...
```

### 3.1 status 字段

| 状态 | 含义 | 行动 |
|------|------|------|
| **活跃** | 持续更新 | 跟代码同步 |
| **冻结** | 不再更新但可读 | 不修改 |
| **归档** | 历史快照 | 移至 `archive/` |
| **废弃** | 已被替代 | 在文档头部加废弃说明 |

## 4. 文档结构

### 4.1 主架构文档

主架构文档（ARCHITECTURE_V2.md）必须包含：

1. 标题 + 版本 + 日期
2. **目录**（12 章以上必备）
3. 分章节（## 二级标题）
4. 子章节（### 三级标题）
5. 文档历史（CHANGELOG）
6. 维护说明

### 4.2 单章节规范

```markdown
### 4.1 子章节标题

**目的**：一句话说明本节目标

**代码位置**：[path/to/file.py](file:///d:/filework/excel-to-diagram/path/to/file.py)

**实现**：
```python
def example():
    pass
```

**API 对照**：

| API | 用途 |
|-----|------|
| `api1()` | 说明 |
```

## 5. 引用规范

### 5.1 代码引用

使用 `file:///` 协议 + 行号：

```markdown
[function_name](file:///d:/filework/excel-to-diagram/path/to/file.py#L100-L120)
[bo_action.py](file:///d:/filework/excel-to-diagram/meta/core/bo_action.py)
```

### 5.2 文档引用

使用相对路径或 `file:///`：

```markdown
[规范文档](./specs/spec-key-template.md)
[外部规范](file:///d:/filework/excel-to-diagram/docs/specs/spec-key-template.md)
```

### 5.3 章节锚点

```markdown
[§5 后端架构详解](#五-后端架构详解)
```

## 6. 内容规则

### 6.1 必做 ✅

- 代码示例使用 `markdown code block` + 语言标签
- 表格使用 `|` 对齐
- 关键数据加粗（**重点**）
- 长文档添加目录

### 6.2 禁止 ❌

- 大段纯文本（无结构）
- 截图代替文字（不可索引）
- 与代码不同步的接口示例
- 包含敏感信息（密钥、密码、token）

## 7. 文档生命周期

### 7.1 创建

1. 选择合适的分类目录
2. 添加 frontmatter
3. 遵守命名规范
4. 更新相关索引（README、专题 INDEX）

### 7.2 维护

1. 与代码同步更新
2. 在文档头部维护版本号
3. 重大变更记录在 CHANGELOG

### 7.3 归档

归档条件：
- 内容已被新文档替代
- 是历史快照（如 v3.6 进度报告）
- 修复完成报告（迁移完成、bug 修复等）

归档操作：
1. 移至 `archive/{原分类}/`
2. 文件名保留原样
3. 在文档头部加：`> **归档**: {归档原因} ({归档日期})`

### 7.4 废弃

废弃条件：
- 内容错误且无法修复
- 已被多个新文档替代
- 完全过时

废弃操作：
1. 文档头部加：
   ```markdown
   > **⚠️ 已废弃** ({日期})
   > 替代文档：[新文档](./new-doc.md)
   > 废弃原因：{原因}
   ```
2. 不立即删除（保留 1 个版本周期）

## 8. 工具支持

### 8.1 Markdown Lint

建议使用：
- `markdownlint-cli` 统一风格
- 规则：MD013（行长 200）、MD033（无内联 HTML）、MD041（首行标题）

### 8.2 链接检查

使用 `markdown-link-check` 验证：
- 内部链接（相对路径）
- 外部链接（file:///）
- 锚点（#section）

## 9. 与代码同步

### 9.1 同步触发点

| 代码变更 | 文档变更 |
|---------|---------|
| 新增拦截器 | ARCHITECTURE_V2 §4 |
| 新增服务 | ARCHITECTURE_V2 §5 |
| 新增 composable | ARCHITECTURE_V2 §6 |
| YAML schema 变更 | architecture/02-yaml-conventions-v2.md |
| API 变更 | architecture/04-api-contracts-v2.md |

### 9.2 同步流程

1. 代码 PR 合并前
2. 检查相关文档是否需要更新
3. 文档更新与代码同步提交
4. 在 CHANGELOG 记录

## 10. 检查清单

新增/修改文档前自检：

- [ ] 命名符合规范
- [ ] 包含 frontmatter
- [ ] 包含目录（如 >5 章）
- [ ] 代码引用使用 `file:///` 协议
- [ ] 无过时信息
- [ ] 已更新相关索引
- [ ] 包含 CHANGELOG（如修改既有文档）

## 参考

- [README.md](./README.md) — 文档门户
- [PERMISSION_SYSTEM_INDEX.md](./PERMISSION_SYSTEM_INDEX.md) — 权限体系索引
- [ARCHITECTURE_V2.md](./ARCHITECTURE_V2.md) — 主架构文档
- [RULES_INDEX.md](../.trae/rules/RULES_INDEX.md) — 规范索引
