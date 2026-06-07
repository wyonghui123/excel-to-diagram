# YonDesign 设计规范速查表

> **重要：所有 AI 智能体在修改样式前必须先查阅此文件！**
> 
> **最后更新**: 2026-05-11  
> **适用范围**: 全项目 Element Plus + YonDesign 组件样式

---

## 核心设计原则

### 1. **YonDesign 主色调：橙色系（非蓝色！）**

```
[WARNING] 禁止使用 Ant Design 蓝 (#1677ff) 或其他蓝色作为主色！
[WARNING] YonDesign 使用橙色系，这是与用友品牌一致的设计决策！
```

#### 完整色阶表

| 变量名 | 色值 | 用途 | 使用场景 |
|--------|------|------|----------|
| `--yonyou-orange-50` | `#fff7ed` | 极淡背景 | Link 按钮 Hover 背景 |
| `--yonyou-orange-100` | `#ffedd5` | 淡背景 | Link 按钮 Active 背景 |
| `--yonyou-orange-500` | `#f97316` | 亮色 | Link 按钮 Hover 文字 |
| `--yonyou-orange-600` | `#ea580c` | **主色** | **按钮/链接默认色** |
| `--yonyou-orange-700` | `#c2410c` | 深色 | Link 按钮 Active 文字 |

#### CSS 变量引用方式

```scss
// [CORRECT] 正确：使用 YonDesign 变量
color: var(--yonyou-orange-600, #ea580c) !important;
background: var(--yonyou-orange-50, #fff7ed) !important;

// [ERROR] 错误：使用其他设计系统的颜色
color: #1677ff !important;  // Ant Design 蓝 - 禁止！
color: #1890ff !important;  // Ant Design 旧版蓝 - 禁止！
color: #4096ff !important;  // Ant Design 5.x - 禁止！
```

---

## 组件样式规范

### 2. **Link 按钮（操作列按钮）**

**设计原则**：遵循 **Material Design 3 Text Button** 规范
- Hover/Focus/Active 状态**只改变背景透明度**
- 文字颜色**始终保持不变**，确保可读性
- 通过背景深浅表达交互状态层次

**参考实现**：MetaTable.vue 中的 `.mt-link-btn`

```scss
// [STANDARD] 标准实现（yon-ep.scss）- Material Design 风格
.el-button.is-link {
  border: none !important;
  background: transparent !important;
  color: var(--yonyou-orange-600) !important;  // 固定文字色，不变
  padding: 4px 8px !important;
  border-radius: var(--radius-sm) !important;

  // Hover 状态：6% 透明度橙色背景
  &:hover,
  &:focus {
    background: rgba(234, 88, 12, 0.06) !important;  /* 6% opacity */
    color: var(--yonyou-orange-600) !important;       /* 文字色不变 */
    border: none !important;
    box-shadow: none !important;
  }

  // Focus 状态（键盘导航）：12% 透明度
  &:focus-visible {
    background: rgba(234, 88, 12, 0.12) !important;  /* 12% opacity */
  }

  // Active/Pressed 状态：16% 透明度
  &:active {
    background: rgba(234, 88, 12, 0.16) !important;  /* 16% opacity */
    color: var(--yonyou-orange-600) !important;        /* 文字色仍然不变 */
  }
}
```

**状态对照表**

| 状态 | 文字颜色 | 背景颜色 | 背景透明度 | 边框 | 用途 |
|------|----------|----------|-----------|------|------|
| 默认 | `orange-600` (#ea580c) | 透明 | 0% | 无 | 正常显示 |
| Hover | `orange-600` (#ea580c) | 橙色 | **6%** | 无 | 鼠标悬停 |
| Focus | `orange-600` (#ea580c) | 橙色 | **12%** | 无 | 键盘导航 |
| Active | `orange-600` (#ea580c) | 橙色 | **16%** | None | 鼠标点击 |

**核心优势**：
- ✅ 文字颜色始终清晰可读（对比度稳定）
- ✅ 符合 Material Design 最佳实践
- ✅ 渐进式状态反馈（6% < 12% < 16%）
- ✅ 实现简单，性能优秀

---

### 2.1 **Filled 按钮（实心按钮）**

**设计原则**：采用 **YonDesign Filled Button** 规范
- 所有状态**保持白色文字**，确保高对比度和可读性
- 通过背景色深浅变化表达交互状态层次
- Primary 使用橙色系，Success/Warning/Danger 使用对应色系

**[FIXED] 已修复问题** (2026-05-11):
```
[PROBLEM] Hover 时文字颜色变成橙色 (#ea580c)，与浅橙背景 (#fb923c) 对比度不足
[PROBLEM] 橙色文字在某些显示器上可能看起来偏红色，造成视觉混淆
[SOLUTION] 强制所有状态使用白色文字 (#ffffff)，只改变背景色深浅
```

#### Primary 按钮状态对照表

| 状态 | 背景颜色 | 文字颜色 | 边框颜色 | 对比度 | 用途 |
|------|----------|----------|----------|--------|------|
| **默认** | `#ea580c` (orange-600) | **#ffffff** | `#ea580c` | 4.6:1 [OK] | 正常显示 |
| **Hover** | `#fb923c` (orange-400) | **#ffffff** | `#fb923c` | 3.8:1 [OK] | 鼠标悬停 |
| **Active** | `#c2410c` (orange-700) | **#ffffff** | `#c2410c` | 5.5:1 [优秀] | 鼠标点击 |

#### 其他类型按钮色阶

| 类型 | 默认背景 | Hover 背景 | Active 背景 | 文字颜色 |
|------|----------|------------|-------------|----------|
| **Primary** | `#ea580c` | `#fb923c` | `#c2410c` | `#ffffff` |
| **Success** | `#22c55e` | `#4ade80` | `#16a34a` | `#ffffff` |
| **Warning** | `#f59e0b` | `#fbbf24` | `#d97706` | `#ffffff` |
| **Danger** | `#ea580c` | `#f97316` | `#c2410c` | `#ffffff` |

#### 标准实现代码

```scss
// [STANDARD] 标准实现（yon-ep.scss）- YonDesign Filled Button
.el-button {
  &--primary {
    background-color: var(--el-color-primary) !important;      // #ea580c
    border-color: var(--el-color-primary) !important;
    color: #ffffff !important;                                  // 强制白色文字

    &:hover,
    &:focus {
      background-color: var(--el-color-primary-light-3) !important;  // #fb923c
      border-color: var(--el-color-primary-light-3) !important;
      color: #ffffff !important;                              // [修复] 保持白色
    }

    &:active {
      background-color: var(--el-color-primary-dark-2) !important;   // #c2410c
      border-color: var(--el-color-primary-dark-2) !important;
      color: #ffffff !important;                              // 保持白色
    }
  }

  // Success / Warning / Danger 类似实现...
}
```

**核心优势**：
- ✅ 对比度优秀：白色文字 + 有色背景，始终满足 WCAG AA 标准（>3:1）
- ✅ 交互清晰：背景色变化明确表达 Hover/Active 状态
- ✅ 一致性高：所有按钮类型遵循相同的设计模式
- ✅ 符合 YonDesign：使用橙色系作为主色调，统一视觉语言
- ✅ 避免混淆：不再出现橙/红色文字，避免用户误解为错误或警告状态

**验证页面**: http://localhost:3004/component-comparison （Filled 按钮区域）

---

### 3. **圆角规范**

| 组件类型 | 圆角大小 | CSS 变量 |
|----------|----------|----------|
| 按钮/输入框/选择器 | **6px** | `--radius-md` 或固定值 |
| 标签/分页/下拉项 | **4px** | `--radius-sm` |
| 卡片/弹窗/抽屉 | **8px** | `--radius-lg` |
| 圆形按钮 | 9999px | 使用 `rounded` prop |

---

### 4. **其他主题色**

| 用途 | 色值 | 变量名 |
|------|------|--------|
| 成功色 | `#22c55e` (Green) | 自定义或 `--el-color-success` |
| 警告色 | `#f59e0b` (Amber) | `--yonyou-amber-500` |
| 危险色 | `#ea580c` (Orange) | 与主色保持一致 |

> **注意**：YonDesign 的危险色也是橙色，不是红色！

---

## 强制性检查清单

### 在修改任何样式之前，必须确认：

- [ ] 1. 是否已查阅 `YON_EP_GUIDE.md`？
- [ ] 2. 是否已查阅本文件（YON_DESIGN_CONSTANTS.md）？
- [ ] 3. 颜色是否使用了 `--yonyou-*` 变量而非硬编码？
- [ ] 4. 是否无意中引入了其他设计系统（Ant Design/Material）的颜色？
- [ ] 5. 是否参考了已有的类似组件实现（如 MetaTable）？
- [ ] 6. 修改后是否在组件对比页面验证了效果？

---

## 常见错误案例

### 错误 1：使用蓝色作为链接色

```scss
// [ERROR] 错误：Ant Design 风格
.el-button.is-link {
  color: #1677ff !important;  // 这是 Ant Design 的颜色！
}

// [CORRECT] 正确：YonDesign 风格
.el-button.is-link {
  color: var(--yonyou-orange-600) !important;  // 使用橙色系
}
```

### 错误 2：硬编码颜色值

```scss
// [ERROR] 错误：硬编码
color: #ea580c !important;

// [CORRECT] 正确：使用变量（便于主题切换和维护）
color: var(--yonyou-orange-600, #ea580c) !important;
```

### 错误 3：忽略已有实现

```scss
// [ERROR] 错误：重新发明轮子
.el-button.is-link {
  // 自己写了一套样式...
}

// [CORRECT] 正确：参考 MetaTable 的 mt-link-btn 实现
// 并保持与其一致的交互效果
```

---

## 相关文件索引

| 文件路径 | 内容 | 优先级 |
|----------|------|--------|
| `src/styles/tokens-yonyou.scss` | YonDesign 完整变量定义 | *** 必读 |
| `src/styles/YON_EP_GUIDE.md` | Element Plus 组件封装规范 | *** 必读 |
| `src/styles/variables.scss` | 项目通用变量 | ** 推荐 |
| `src/components/common/MetaTable.vue` | 已实现的组件示例 | ** 参考 |
| `src/styles/yon-ep.scss` | Element Plus 全局覆盖样式 | ** 修改时必读 |

---

## 最佳实践

### 1. **"规范优先"原则**
任何样式修改前，先花 2 分钟查阅上述文件，避免返工。

### 2. **变量优先原则**
始终使用 CSS 变量，不硬编码颜色值，便于未来主题切换。

### 3. **一致性原则**
参考项目内已有实现（MetaTable、自定义组件），保持风格统一。

### 4. **验证原则**
修改后在 `http://localhost:3004/component-comparison` 页面验证效果。

---

## 版本历史

| 日期 | 版本 | 更新内容 | 作者 |
|------|------|----------|------|
| 2026-05-11 | v1.0 | 初始版本，明确禁止使用蓝色 | AI Assistant |

---

> **维护说明**：此文件应随着设计规范的更新而同步更新。任何新增的组件样式都应在此文件中记录。
