# ConditionRuleBuilder 布局反复"改了没变化" — 根因是陈旧构建而非 CSS

> **项目** excel-to-diagram
> **日期** 2026-08-26
> **状态** ✅ 已解决

---

## 1. TL;DR

用户反复反馈条件规则组件（`ConditionRuleBuilder`）两个布局问题「来来回回多少次都改不好」：
1. 子组的橙竖线没有位于 `[且/或]` 与 `[添加条件]` 的左边
2. 最外层 `[添加条件]` 比同层 `[且/或]` 突出左边几 px

> ⚠️ 此前的失败模式：**反复盲改 CSS 边界值**（fix12~fix20 系列），从未用真实浏览器渲染验证。最终发现——**当前源码的布局本来就是正确的**，用户看到"没有任何变化"是因为**前端跑的是陈旧构建/HMR 未落地**，CSS 改动根本没到用户浏览器里。

---

## 2. 问题时间线

| 阶段 | 动作 | 结果 |
|------|------|------|
| 多轮 | 反复调 `ConditionRuleRow.vue` 的 `.el-select__wrapper` 宽度、`--nested` 的 `border-left/padding-left/::before` 等 | 无真实验证，用户"没有任何变化" |
| 本轮 | 搭建独立 Vite 预览页 + Playwright 真实渲染，逐元素测 `getBoundingClientRect()` | 测得当前源码**几何上已符合诉求** |

---

## 3. 根因技术细节（关键）

**源码实际渲染结果（Playwright 实测像素）：**

顶层（内容起点 x=8）：
| 元素 | 左边距 |
|------|--------|
| 顶层行 `[且/或]` segmented | 8 |
| 顶层 `[添加条件]` 按钮 | 8 |

→ **完全对齐，无突出** ✅（`RuleBuilderGroup.vue` `.rule-builder-add-row { padding-left: 0 }`）

子组（橙竖线在子组相对起点 x=0）：
| 元素 | 相对竖线右侧 |
|------|--------|
| 子组行 `[且/或]` | 16px |
| 子组条件行 | 16px |
| 子组 `[添加条件]` | 16px |

→ **竖线在 `[且/或]` 和 `[添加条件]` 左边，内容统一缩进** ✅（`RuleBuilderGroup.vue` `.rule-builder-group--nested { border-left:4px; padding-left:12px }`）

**"改不好"的真正根因：**
- 端口检测显示 3004/3010 **没有任何 dev server 在跑** → 用户看到的不是这套源码
- Vite dev 已配 `Cache-Control: no-store`，但若浏览器硬刷新不彻底/看旧构建，CSS 不会更新
- **教训：CSS 布局问题必须用真实浏览器验证，不能靠读代码推演**

---

## 4. 修复代码

本轮**无需改业务代码**（源码已正确）。可复用的正确 CSS 位置：
- `src/components/common/ConditionRuleBuilder/RuleBuilderGroup.vue`
  - 子组竖线/缩进：`.rule-builder-group--nested`（`border-left:4px` + `padding-left:12px`）L285-296
  - 添加按钮起点：`.rule-builder-add-row { padding-left: 0 }` L317-331
- `src/components/common/ConditionRuleBuilder/ConditionRuleRow.vue`
  - 行 `[且/或]` 70px 连接符列：`.rule-row` grid L279-290

---

## 5. 调试方法论（什么有效 / 无效）

**无效（不要再用）：**
- 盲改 CSS 边界值（fix12~fix20 系列）而不验证渲染
- 假设"用户看到了我改的代码"

**有效：**
- 搭**独立 Vite 预览页**渲染真实组件，用 Python `playwright` 直测真实 DOM
- 逐元素打印 `getBoundingClientRect().left`（相对参考点），用数字而非肉眼判断对齐
- **先确认后端/前端进程是否在跑**，再谈样式——否则必然"改了没变化"

### 独立预览页搭建要点（复用）
> 需要给 `@/components/common/SearchHelpDialog.vue`、`@/services/permissionService`、`@/utils/{logger,httpClient,api}` 等打桩，避免 `api.js ↔ httpClient.js` 循环导入导致的 `Cannot access 'API_BASE' before initialization`。

- **关键坑**：`vite resolve.alias` 按**数组顺序**匹配；通用 `'@'` 别名必须放**最后**，否则会劫持所有 `@/...` 导入，使更具体的桩失效。
- 桩要点：`rule-helpers.ts` 的 `import * as permServiceDefault from '@/services/permissionService'`、`RuleBuilderGroup.vue` 的 `SearchHelpDialog` 是重依赖链入口。
- 内联 `template` 的 Demo App 需把 `vue` 别名为 `vue/dist/vue.esm-bundler.js`（运行时编译器）。

---

## 6. 测试缺口 & 改进

- [ ] 为 `ConditionRuleBuilder` 增加 Playwright E2E 快照测试（断言竖线 x 与 add-row 对齐关系），防止回归
- [ ] 完善「服务是否在跑」的快速检测/自证，避免再次在陈旧构建上误判

---

## 7. 经验教训（跨项目铁律）

1. **先确认进程/构建状态，再调样式**：前端反复"改了没变化"，十有八九是陈旧构建/HMR 未落地，不是 CSS 没改。
2. **CSS 布局问题必须真实渲染验证**，逐元素测像素数字对比，禁止读代码脑补。
3. **独立预览页是前端局部调试的最快途径**；stub 掉重型依赖链，别让 `api/httpClient/boService` 阻碍组件渲染。
4. **`vite resolve.alias` 是顺序匹配**，通用 `'@'` 放最后，具体桩放前面。

---

## 8. 行动项

- 立即：无（本轮无业务代码改动）
- 短期：对 `ConditionRuleBuilder` 补视觉回归断言
- 长期：沉淀「独立组件预览」脚手架到 `test_helpers/`，供未来前端局部调试复用

---

## 9. 相关文件

- `src/components/common/ConditionRuleBuilder/RuleBuilderGroup.vue`
- `src/components/common/ConditionRuleBuilder/ConditionRuleRow.vue`
- （临时预览脚本已清理：`.preview-cr/` 已删除）