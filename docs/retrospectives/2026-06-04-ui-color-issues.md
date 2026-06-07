# 角色权限页面 UI 颜色问题复盘

> 日期: 2026-06-04
> 影响范围: 角色详情页（功能权限配置 + 详细权限列表）
> 严重程度: 中-高（视觉体验问题，但未影响功能）

---

## 一、问题回顾

用户在功能权限页面的截图反馈了**两个相关问题**：

| # | 问题 | 截图证据 |
|---|------|---------|
| 1 | 页面"花花绿绿"，颜色没有遵循 YonDesign 规范 | 4 个动作分组（查看/编辑/管理/standalone）使用 4 种不同颜色 |
| 2 | 排除和选中视觉上不易区分；BO 权限有绿色背景 | 激活（淡 Orange 50）与排除（淡 Orange 50）色相接近 |

---

## 二、根本原因分析

### 2.1 直接原因

`MenuPermissionMatrix.vue` 中硬编码了 4 种不同颜色（蓝/紫/橙/青）来区分不同的动作分组：

```scss
&.group-view.is-active       { background: rgba(24,144,255,0.1);  color: #1890ff; } // 蓝
&.group-edit.is-active       { background: rgba(124,58,237,0.1);  color: #7c3aed; } // 紫
&.group-manage.is-active     { background: rgba(250,140,22,0.1);  color: #fa8c16; } // 橙
&.group-standalone.is-active { background: rgba(19,194,194,0.1);  color: #13c2c2; } // 青
```

这是从早期 demo 阶段延续下来的"花哨"风格，没有考虑 YonDesign 规范。

### 2.2 深层原因

#### (1) 缺少"状态-色彩"语义规范

`ui-design-standards.md` 只列出了**调色板**（主色、文本色、间距），但**没有规定**：
- "激活/未激活"用什么颜色？
- "成功/警告/错误"如何应用？
- "自动/包含/排除"标签应该如何配色？

导致开发者**只能凭直觉**决定每个状态用什么颜色，结果五花八门。

#### (2) 设计令牌 vs 硬编码的边界未明确

规范提到"所有颜色使用 CSS 变量"，但**缺少自动检查**。本次扫描发现：
- 93 个 Vue 文件存在硬编码颜色（`#fff`/`#1890ff` 等）
- 大量 `rgba(...)` 直接写在样式里
- 没有 CI/ESLint 拦截

#### (3) 修复时缺少"全场景一致性"思维

第一次修复时只考虑了"按钮"区域，但**没考虑与"详细权限"区域的一致性**。用户提出后才意识到需要用 SCSS `%placeholder` 抽出共享样式。

#### (4) 反复修改，多次返工

| 轮次 | 改动 | 用户反馈 |
|------|------|---------|
| 1 | 4 种颜色 → 1 种主色 | "花花绿绿"未解决 |
| 2 | 主色 + 区分 dashed 边框 | "排除和选中无法区分" |
| 3 | 灰色 source 标签 | "包含不要变，要主色" |
| 4 | 抽出 `%source-tag-base` 共享样式 | ✅ 通过 |

**如果一开始就参考 YonDesign 规范，这 4 轮返工完全可以避免。**

---

## 三、UI 规范缺口分析

### 3.1 当前规范覆盖情况

| 维度 | 规范 | 状态 |
|------|------|------|
| 设计令牌（颜色/间距/字体） | ✅ 已列 | 充分 |
| 组件复用清单 | ✅ 已列 | 充分 |
| Tab 导航样式 | ✅ 已列 | 充分 |
| 侧边导航样式 | ✅ 已列 | 充分 |
| 文本颜色（主/次/辅） | ✅ 已列 | 充分 |
| 消息通知 | ✅ 已列 | 充分 |
| **状态色彩语义** | ❌ 缺失 | **缺口** |
| **按钮激活/未激活** | ❌ 缺失 | **缺口** |
| **标签/Badge 配色** | ❌ 缺失 | **缺口** |
| **行/列表的状态色** | ❌ 缺失 | **缺口** |
| **可访问性（对比度）** | ❌ 缺失 | **缺口** |
| **暗色模式应用** | ❌ 简略 | **缺口** |
| **硬编码颜色检测** | ❌ 缺失 | **缺口** |

### 3.2 缺失内容详述

#### 缺口 1：状态色彩语义

> 哪些颜色代表"成功/警告/错误/信息/中性"？什么时候用？

| 状态 | 应使用 | 不应使用 |
|------|--------|---------|
| 成功/已授予 | `--color-success` (Green 500) | 不要用主色 |
| 警告/提示 | `--color-warning` (Amber 500) | 不要用主色 |
| 错误/排除/拒绝 | `--color-error` (Orange 700) | 不要用蓝色/红色 |
| 信息/中性 | `--color-text-secondary` | 不要用主色 |
| 主动选择/激活 | `--color-primary` (Orange 600) | 不要用绿/蓝/紫 |

#### 缺口 2：按钮状态规范

```scss
// 正确
.btn-default       { background: var(--color-bg-primary);  border: 1px solid var(--color-border); }
.btn-default:hover{ border-color: var(--color-primary); }
.btn-active        { background: var(--color-primary-bg);  border: 1px solid var(--color-primary); color: var(--color-primary); }
.btn-excluded      { background: var(--color-bg-primary);  border: 1px dashed var(--color-border); color: var(--color-text-quaternary); }
```

#### 缺口 3：标签/Badge 配色

| 语义 | 背景 | 文字 |
|------|------|------|
| 自动派生 | `--color-bg-secondary` | `--color-text-secondary` |
| 主动包含 | `--color-primary-bg` | `--color-primary` |
| 主动排除 | `--color-error-bg` | `--color-error` |
| 未分配 | `--color-bg-secondary` | `--color-text-quaternary` |

#### 缺口 4：行/列表状态

| 状态 | 表现 |
|------|------|
| 普通 | 无背景 |
| 选中/已授予 | 左侧 2px 主色或成功色边线（不加背景） |
| 排除/失败 | 浅错误色背景 + 左侧 2px 错误色边线 + 文字删除线 |

#### 缺口 5：可访问性

- 文字与背景对比度 ≥ 4.5:1 (WCAG AA)
- 不依赖颜色单独传达信息（用形状/文字辅助）

#### 缺口 6：硬编码颜色检测

- 93 个文件存在硬编码颜色 → 需要自动化拦截
- 可用 stylelint 规则 `color-no-hex` + 自定义 `declaration-property-value-allowed-list`

---

## 四、改进措施

### 4.1 立即修复（已完成）

- ✅ MenuPermissionMatrix.vue 颜色统一
- ✅ 抽出 `%source-tag-base` 共享样式
- ✅ 按钮 + 详细权限行源标签颜色一致

### 4.2 规范完善（本次任务）

- ✅ 补充"状态色彩语义"章节
- ✅ 补充"按钮/标签/行状态"配色表
- ✅ 补充"反模式示例"小节
- ✅ 补充"PR Review Checklist"

### 4.3 长期机制

| 机制 | 目的 | 优先级 |
|------|------|--------|
| Stylelint 配置 | 自动拦截硬编码颜色 | P0 |
| 设计令牌缺失告警 | 强制使用 var() | P0 |
| 视觉回归测试 | Playwright 截图对比 | P1 |
| Figma Code Sync | 设计稿即代码 | P2 |
| Code Review Checklist | PR 模板 | P0 |

### 4.4 Stylelint 规则建议

```json
{
  "rules": {
    "color-no-hex": [true, { "message": "请使用 design tokens 而非硬编码颜色，参考 ui-design-standards.md" }],
    "color-named": "never",
    "declaration-property-value-allowed-list": {
      "/^(color|background-color|border-color)$/": [
        "/^var\\(--/",
        "/^transparent$/",
        "/^inherit$/",
        "/^currentColor$/",
        "/^none$/"
      ]
    }
  }
}
```

### 4.5 Code Review Checklist（PR 模板）

```markdown
## UI 规范自检

- [ ] 没有使用硬编码颜色（#fff、#1890ff、rgba 等）
- [ ] 所有颜色使用 `var(--color-*)` 设计令牌
- [ ] 状态色彩遵循"激活=主色、错误=Orange 700、成功=Green、警告=Amber"原则
- [ ] 按钮/标签/行状态在多个区域保持一致
- [ ] 暗色模式可用（如适用）
- [ ] 文字与背景对比度 ≥ 4.5:1
```

---

## 五、经验教训

### 5.1 给开发者的教训

1. **先看规范，再写代码**：动笔前先阅读 `ui-design-standards.md` 和 `tokens-yonyou.scss`
2. **不要用颜色区分类别**：用形状（dashed、删除线）、文字（"自动"）、位置（左侧边线）表达状态
3. **修改一处必看全局**：按钮样式改了，要主动检查同页面的列表/行样式
4. **抽出共享样式**：跨组件复用样式时，用 SCSS `%placeholder` 或变量

### 5.2 给规范维护者的教训

1. **规范要给"反例"**：光说"用 CSS 变量"不够，要给"常见错误写法"
2. **规范要可执行**：列出具体的颜色映射表（什么状态用什么色）
3. **规范要可验证**：配套 Stylelint/ESLint 规则自动检查
4. **规范要持续更新**：发现新场景时及时补充

---

## 六、复盘总结

| 维度 | 评分 (1-5) |
|------|----------|
| 规范可读性 | ⭐⭐⭐ |
| 规范可执行性 | ⭐⭐ |
| 规范完整性 | ⭐⭐ |
| 修复及时性 | ⭐⭐⭐ |
| 沟通效率 | ⭐⭐⭐⭐ |
| 整体满意度 | ⭐⭐⭐ |

**核心结论**：本次问题表面是"颜色花哨"，本质是**规范只给了调色板，没给"何时用哪个"的语义映射**。已通过补充规范 + 共享样式抽离解决，但仍有 93 个文件存在硬编码颜色，需后续通过 Stylelint 等机制系统化解决。
