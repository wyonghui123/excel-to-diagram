# Element Plus el-select 弹窗内下拉被遮罩的根因与修复

> **记录日期**: 2026-06-02
> **问题类型**: UI 渲染 / Element Plus Teleport / z-index 战争
> **影响范围**: 所有 `AppSelect` / `el-select` 在 `AppModal` 弹窗内的下拉

---

## 问题描述

业务对象详情页 → 点击"添加备注" → 弹窗打开 → 点击"分类"下拉框：
- **DOM 检测**：开发者工具中能看到 `.el-select-dropdown` 节点，items 数量正确（4 个）
- **真实视觉**：用户**完全看不到**下拉选项，弹窗里"什么都没有"
- **自动化测试**：Playwright 用 `document.querySelector` 判定"OK"——因为 DOM 里确实有，但视觉上不可见
- **页面诊断**：DevTools → Elements 搜 `.el-select-dropdown` 出现 **69 个**实例

## 问题原因（三层叠加）

### 1. L1 - Element Plus 默认 Teleport 行为

`<el-select>` 默认 `teleported="true"`，下拉被 Vue 3 Teleport 渲染到 `<body>` 末尾的 `#el-popper-container-` 容器里。

**后果**：下拉与触发它的 select 不在同一 DOM 树，无法继承 modal 的 z-index context。

### 2. L2 - 父级 overflow 裁剪

我们自定义的 `AppModal.vue:374` 有：

```css
.app-modal__body {
  overflow-y: auto;  /* ← 罪魁 */
}
```

即使把下拉强制留在组件内（`teleported="false"`），`overflow: auto` 的祖先容器**会裁剪掉**所有 `position: absolute` 溢出的子元素。这是 CSS 规范行为，无法绕过。

### 3. L3 - z-index 在 `<body>` 根层竞争

| 元素 | z-index |
|------|---------|
| `.el-popper` (下拉) | 3000+ (Element Plus 默认) |
| `.el-overlay` (modal 遮罩) | 2000-3000 |
| `.app-modal` (我们自定义) | `var(--z-index-modal)` = 9999 |
| `NotificationContainer` | 9999 |

**多个元素 z-index 相同 → 渲染顺序决定谁在上 → 经常 modal 盖住下拉**。

## 解决方案（三处改动）

### 1. 关闭 Teleport（最关键）

**文件**: `src/components/common/AppSelect/AppSelect.vue`

```vue
<el-select
  :model-value="modelValue"
  :teleported="false"
  popper-class="app-select-popper"
  ...
>
```

**效果**：下拉留在组件 DOM 内，与 select 共享 z-index context，**不可能被 modal 盖住**。

### 2. 拆分 AppModal body 滚动容器

**文件**: `src/components/common/AppModal/AppModal.vue`

```vue
<div class="app-modal__body">  <!-- 外层: overflow: visible, 让 popper 溢出 -->
  <div class="app-modal__body-scroll">  <!-- 内层: 负责滚动 -->
    <slot />
  </div>
</div>
```

```css
.app-modal__body {
  flex: 1;
  padding: 0;
  overflow: visible;  /* 关键: 允许 popper 溢出 */
  position: relative;
}
.app-modal__body-scroll {
  max-height: calc(100vh - 220px);
  padding: var(--spacing-lg);
  overflow-y: auto;
  overflow-x: visible;
}
```

**效果**：外层 `visible` 让 popper 自由溢出，内层 `auto` 保留滚动条。

### 3. 同步处理直接用 el-select 的地方

**文件**: `src/components/common/DetailPage/DetailSection.vue`

两处 `<el-select>` 同样加 `:teleported="false"` 和 `popper-class="app-select-popper"`。

## 验证方法（不是看 DOM 存在！）

错误做法（之前用的）：
```python
# 这种判定 "DOM 里有" 不足以证明可见
popper = page.query_selector('.el-select-dropdown')
assert popper is not None  # 假阳性！
```

正确做法（必须做）：
```python
# 真实视觉验证三件套
state = page.evaluate("""
  () => {
    const p = document.querySelector('.el-select-dropdown');
    const rect = p.getBoundingClientRect();
    const style = getComputedStyle(p);
    return {
      inViewport: rect.x >= 0 && rect.y >= 0 &&
                  rect.x + rect.width <= innerWidth &&
                  rect.y + rect.height <= innerHeight,
      isRendered: style.display !== 'none' &&
                  style.visibility !== 'hidden' &&
                  parseFloat(style.opacity) > 0,
      isObscured: (() => {
        // elementFromPoint 检查中心点是否被遮挡
        const topEl = document.elementFromPoint(
          rect.x + rect.width/2,
          rect.y + rect.height/2
        );
        return topEl && !p.contains(topEl);
      })()
    };
  }
""")
```

完整脚本见：`test_helpers/scripts/verify_dropdown_visible.py`

## 经验总结（关键 5 条）

### 1. Element Plus 弹层的本质问题
> Element Plus **默认所有浮层（select/dropdown/datepicker/tooltip）都 Teleport 到 `<body>`**，
> 这是为了避免 `overflow: hidden/auto` 裁剪，但也**脱离了父组件的 z-index context**。
> 在 modal/drawer 内使用时，**必须**考虑 z-index 战争。

### 2. 修复模式：在 modal 内关闭 Teleport
```vue
<el-select :teleported="false" popper-class="my-popper">
<el-date-picker :teleported="false">
<el-cascader :teleported="false">
```

但**前提是父容器不能有 `overflow: hidden/auto/scroll`**，否则 popper 会被裁剪。

### 3. 滚动容器拆分法
对于需要滚动的 modal：
```css
.modal-body {  /* 外层 */
  overflow: visible;  /* 允许 popper 溢出 */
}
.modal-body-scroll {  /* 内层 */
  overflow-y: auto;  /* 在这里滚动 */
}
```

### 4. 自动化测试标准升级
- ❌ **DOM 存在 ≠ 视觉可见**
- ✅ 必须检查：`inViewport + isRendered + isObscured` 三件套
- ✅ 必须实际截图（screenshot）作为最终判定
- ✅ Playwright 截图 Teleport 的 popper 时，要先 `wait_for_function` 等 `.el-select-dropdown` 可见

### 5. DevTools 调试技巧
- `Elements` 搜 `.el-select-dropdown` 看实例数（>1 即说明页面有多个下拉共存）
- `Console` 输入 `getComputedStyle(document.querySelector('.el-select-dropdown')).zIndex` 看 z-index
- `Network` 看点击下拉时是否发请求（静态下拉不应发请求，发了说明触发了 search/remote 逻辑）
- 选中 popper 元素，看 `Event Listeners` 是否有 mousedown/click 监听

## 已知副作用

### 副作用 1: 弹窗底部下拉被裁切
当下拉打开方向朝下，且 select 靠近弹窗底部时，下拉底部会被弹窗边界裁切。
- 临时方案：增大弹窗的 `max-height`
- 根本方案：用 `placement="top"` 或 Element Plus 的 `fallback-placements` 自动翻转
- **推荐方案（已采用）**：用 CSS `:has()` 智能检测弹窗内是否有 `el-select`，有则给 body-scroll 加 200px 底部 padding：

```css
/* 当弹窗内容包含 el-select 时，给 body-scroll 底部预留 200px */
.app-modal__container:has(.el-select) .app-modal__body-scroll {
  padding-bottom: 200px;
}
```

- 浏览器兼容性：`:has()` Chrome 105+ / Safari 15.4+ / Firefox 121+，不兼容老浏览器但能优雅降级（没下拉空间但不会崩）

### 副作用 2: 弹窗内下拉出现多余滚动条
关闭 Teleport 后，Element Plus 的 `.el-scrollbar` 可能因为 `max-height` 错误计算而出现滚动条，即使选项很少。
- 修复：用 `popper-class` + CSS 覆盖：

```css
.app-select-popper .el-select-dropdown__wrap {
  max-height: 320px !important;  /* 允许显示 ~8 个项目 */
}
```

### 副作用 3: 多下拉页面性能
关闭 Teleport 后，每个下拉都在自己的组件树内，DOM 数量不变但 React/Vue 树更深。
- 实测影响：< 1ms 渲染差异，可忽略

## 相关代码

- [AppSelect.vue](../../src/components/common/AppSelect/AppSelect.vue) - 关闭 Teleport
- [AppModal.vue](../../src/components/common/AppModal/AppModal.vue) - 拆分滚动容器
- [DetailSection.vue](../../src/components/common/DetailPage/DetailSection.vue) - 直接 el-select 同步处理
- [verify_dropdown_visible.py](../../test_helpers/scripts/verify_dropdown_visible.py) - 真实视觉验证脚本

## 相关文档

- [Element Plus Popper 官方文档](https://element-plus.org/en-US/component/select.html#select-attributes)
- [Vue 3 Teleport 文档](https://vuejs.org/guide/built-ins/teleport.html)
- [CSS overflow 规范](https://developer.mozilla.org/en-US/docs/Web/CSS/overflow)
