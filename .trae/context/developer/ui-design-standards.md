# UI设计规范

> 本文档为 Developer 角色提供UI设计规范指导，涉及前端UI开发时必须查阅。

## 核心原则

### 必须遵守

| 原则 | 说明 | 违反后果 |
|------|------|---------|
| 使用设计令牌 | 所有颜色、间距、字体使用CSS变量 | 样式不统一，难以维护 |
| 组件复用 | 优先使用 `AppTabs`、`AppSideNav`、`AuditLog` | 代码重复，风格不统一 |
| 消息通知 | 使用 `useMessage()` 而非 `alert()` | 用户体验差 |
| Tab样式 | 使用底部指示线而非填充背景 | 不符合yonDesign规范 |
| 导航样式 | 使用左侧指示线而非背景填充 | 不符合yonDesign规范 |

## 快速参考

### 设计令牌

```scss
// 颜色
--color-primary: #ea580c;           // 主色
--color-text-primary: #333333;      // 主要文本
--color-text-secondary: #666666;     // 次要文本
--color-text-tertiary: #999999;      // 辅助文本

// 间距
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-md: 16px;
--spacing-lg: 24px;

// 字体
--font-size-xs: 12px;
--font-size-sm: 13px;
--font-size-md: 14px;
```

### 常用组件导入

```javascript
import { AppTabs, AppSideNav, AuditLog } from '@/components/common'
```

## Tab导航规范

### ✅ 正确做法

```vue
<nav class="tabs">
  <button class="tab tab--active">标签1</button>
  <button class="tab">标签2</button>
</nav>

<style scoped>
.tabs { display: flex; border-bottom: 1px solid var(--color-border); }
.tab {
  padding: var(--spacing-md) 0;
  color: var(--color-text-secondary);
  border: none;
  border-bottom: 2px solid transparent;
}
.tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}
</style>
```

### ❌ 错误做法

```vue
<!-- ❌ 使用 AppButton 作为 Tab -->
<AppButton variant="primary">标签</AppButton>

<!-- ❌ 使用填充背景 -->
.tab--active {
  background: var(--color-primary);
  color: white;
}
```

## 侧边导航规范

### ✅ 正确做法

```vue
<aside class="sidebar">
  <button class="nav-item nav-item--active">菜单1</button>
  <button class="nav-item">菜单2</button>
</aside>

<style scoped>
.sidebar { width: 200px; border-right: 1px solid var(--color-border); }
.nav-item {
  border-left: 2px solid transparent;
  color: var(--color-text-secondary);
}
.nav-item--active {
  border-left-color: var(--color-primary);
  color: var(--color-primary);
}
</style>
```

### ❌ 错误做法

```vue
<!-- ❌ 使用背景填充 -->
.nav-item--active {
  background: var(--color-primary-bg);
}
```

## 文本颜色规范

| 元素 | 正确颜色 | 错误颜色 |
|------|---------|---------|
| 表格内容 | `--color-text-primary` | `--color-text-tertiary` |
| 表格表头 | `--color-text-secondary` | `--color-text-primary` |
| 辅助说明 | `--color-text-tertiary` | `--color-text-primary` |

```scss
// ✅ 正确
.data-table td { color: var(--color-text-primary); }
.data-table th { color: var(--color-text-secondary); }

// ❌ 错误 - 对比度不足，可能产生删除线视觉效果
.data-table td { color: var(--color-text-tertiary); }
```

## 滚动条规范

### ✅ 正确做法

```scss
.content { overflow-y: auto; }  // 使用浏览器默认
```

### ❌ 错误做法

```scss
// ❌ 全局自定义滚动条
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-thumb { background: var(--color-primary); }

// ❌ 在 mixins.scss 中定义全局滚动条样式
@mixin scrollbar { ... }
```

## 消息通知规范

```javascript
import { useMessage } from '@/composables/useMessage'
const message = useMessage()

// ✅ 正确
message.success('操作成功')
message.error('保存失败: 网络错误')

// ❌ 错误
alert('操作成功')  // 禁止使用
```

## 组件复用检查清单

开发新UI前，先检查是否已有可复用组件：

| 需求 | 已有组件 | 文档位置 |
|------|---------|---------|
| Tab导航 | `AppTabs` | `src/components/common/AppTabs/` |
| 侧边导航 | `AppSideNav` | `src/components/common/AppSideNav/` |
| 日志展示 | `AuditLog` | `src/components/common/AuditLog/` |
| 按钮 | `AppButton` | `src/components/common/AppButton/` |
| 表格 | `MetaTable` | `src/components/common/MetaTable.vue` |

## 完整规范文档

详细规范和代码示例见：
- [UI_COMPONENT_GUIDELINES.md](../../../docs/UI_COMPONENT_GUIDELINES.md)
- [YONYOU_DESIGN.md](../../../src/styles/YONYOU_DESIGN.md)
- [retrospectives/2026-06-04-ui-color-issues.md](../../../docs/retrospectives/2026-06-04-ui-color-issues.md) — 颜色规范缺陷复盘

---

## 状态色彩语义（重要！必须遵守）

> 2026-06-04 复盘新增：本章节是历史最容易踩坑的地方。

### 核心原则

| 语义 | 应使用 | 用途 | 不要用 |
|------|--------|------|--------|
| **主动选择 / 激活** | `--color-primary` (Orange 600) | 用户主动授予、按钮激活状态 | ❌ 不要用绿/蓝/紫/青 |
| **成功 / 已完成** | `--color-success` (Green 500) | 流程通过、已生效 | ❌ 不要用主色 |
| **警告 / 提示** | `--color-warning` (Amber 500) | 需注意但不阻断 | ❌ 不要用主色 |
| **错误 / 排除** | `--color-error` (Orange 700) | 主动拒绝、错误状态 | ❌ 不要用红色（#ff0000） |
| **信息 / 中性** | `--color-text-secondary` | 说明性文字 | ❌ 不要用主色 |

### 业务状态映射

| 业务状态 | 背景 | 文字 | 备注 |
|---------|------|------|------|
| 自动派生 | `var(--color-bg-secondary)` | `var(--color-text-secondary)` | 灰色，不抢眼球 |
| 主动包含 | `var(--color-primary-bg)` | `var(--color-primary)` | 主色高亮 |
| 主动排除 | `var(--color-error-bg)` | `var(--color-error)` | 警示色 |
| 未分配 | `var(--color-bg-secondary)` | `var(--color-text-quaternary)` | 极浅灰 |

### 反模式（禁止）

```scss
// ❌ 错误：用 4 种不同颜色区分不同的"分组"
&.group-view.is-active       { background: #e6f7ff; color: #1890ff; }  // 蓝
&.group-edit.is-active       { background: #f9f0ff; color: #7c3aed; }  // 紫
&.group-manage.is-active     { background: #fff7e6; color: #fa8c16; }  // 橙
&.group-standalone.is-active { background: #e6fffb; color: #13c2c2; }  // 青

// ❌ 错误：硬编码颜色
background: #1890ff;
color: #ffffff;
border: 1px solid #d9d9d9;

// ❌ 错误：把主色当成功色用
&.cap-granted { background: var(--color-primary-bg); }  // 应该是 success-bg

// ❌ 错误：用纯红表示错误
color: #ff0000;
```

### 正确模式

```scss
// ✅ 正确：所有状态用主色+饱和度变体
&.is-active { background: var(--color-primary-bg); color: var(--color-primary); }
&.is-excluded { background: var(--color-error-bg); color: var(--color-error); }

// ✅ 正确：硬编码颜色必须替换为设计令牌
background: var(--color-bg-primary);
color: var(--color-text-primary);
border: 1px solid var(--color-border);

// ✅ 正确：跨组件共享样式用 SCSS %placeholder
%source-tag-base {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  &.source-include { background: var(--color-primary-bg); color: var(--color-primary); }
  &.source-exclude { background: var(--color-error-bg); color: var(--color-error); }
}
.group-source-tag { @extend %source-tag-base; }
.cap-source-tag { @extend %source-tag-base; }
```

---

## 按钮状态规范

```scss
// ✅ 默认态
.btn {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-secondary);
  color: var(--color-text-tertiary);

  &:hover { border-color: var(--color-primary); color: var(--color-primary); }
}

// ✅ 激活态
.btn.is-active {
  background: var(--color-primary-bg);
  border: 1px solid var(--color-primary);
  color: var(--color-primary);
  font-weight: 500;
}

// ✅ 排除态（视觉弱化）
.btn.is-excluded {
  background: var(--color-bg-primary);
  border: 1px dashed var(--color-border);
  color: var(--color-text-quaternary);

  .btn-label { text-decoration: line-through; text-decoration-color: var(--color-error); }
}
```

---

## 列表行/状态行规范

```scss
// ✅ 普通行
.list-item {
  border-left: 2px solid transparent;
  &:hover { background: var(--color-bg-spotlight); }
}

// ✅ 已授予行（低调表示）
.list-item.is-granted {
  border-left: 2px solid var(--color-text-quaternary);
  /* 不加背景色，避免视觉污染 */
}

// ✅ 已排除行（强调警示）
.list-item.is-excluded {
  background: var(--color-error-bg);
  border-left: 2px solid var(--color-error);
  color: var(--color-text-tertiary);
  .item-label { text-decoration: line-through; }
}
```

---

## PR Review Checklist（新增）

提交 UI 变更前请自检：

- [ ] **无硬编码颜色**：`#fff`、`#1890ff`、`rgba()` 等必须替换为 `var(--color-*)`
- [ ] **状态色彩语义正确**：激活=主色，错误=Orange 700，成功=Green，警告=Amber
- [ ] **跨区域一致**：按钮/标签/行 在同一页面多个区域保持一致
- [ ] **不依赖颜色传达信息**：用形状（dashed、删除线）、文字、位置辅助表达状态
- [ ] **暗色模式可用**：在 `@media (prefers-color-scheme: dark)` 下对比度足够
- [ ] **文字对比度 ≥ 4.5:1**（WCAG AA）

---

## 自动化检查（建议配置）

### Stylelint 规则

```json
{
  "rules": {
    "color-no-hex": [true, { "message": "请使用 design tokens 而非硬编码颜色，参考 ui-design-standards.md" }],
    "color-named": "never",
    "declaration-property-value-allowed-list": {
      "/^(color|background|background-color|border|border-color|border-top-color|border-right-color|border-bottom-color|border-left-color)$/": [
        "/^var\\(--/",
        "/^transparent$/",
        "/^inherit$/",
        "/^currentColor$/",
        "/^none$/",
        "/^unset$/"
      ]
    }
  }
}
```

### 扫描结果

> 2026-06-04 复盘扫描：`src/**/*.vue` 中存在硬编码颜色的文件 93 个
> 后续需通过 Stylelint + CI 拦截。

---

**最后更新**: 2026-06-04（新增"状态色彩语义"、"按钮/行状态规范"、"PR Review Checklist"）
