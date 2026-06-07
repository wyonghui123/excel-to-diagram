# 前端可测试性铁律（Testability Iron Rules）

> **记录日期**: 2026-06-02
> **痛点来源**: 一个 dropdown 视觉问题被错误判定为"OK"，导致来回处理 20+ 次
> **核心教训**: **DOM 存在 ≠ 视觉可见**

---

## 铁律 1：测试判定必须用"视觉可见"而非"DOM 存在"

### 错误做法（之前的代码）

```python
# ❌ 致命错误：DOM 存在即认为 OK
popper = page.query_selector('.el-select-dropdown')
items = popper.query_selector_all('.el-select-dropdown__item')
assert items.length > 0  # Element Plus 总是把所有 items 渲染到 DOM
```

**为什么错**：Element Plus 把所有下拉选项预先渲染到 DOM（只是用 CSS 隐藏），所以 `query_selector` 永远能找到。但这不代表用户能看见。

### 正确做法（5 步视觉验证）

```python
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True)
result = cli.assert_visible('.el-select-dropdown', screenshot_path='d:/fail.png')

assert result['ok'], f"下拉框视觉不可见: {result['reason']}"
```

**5 步检查**（由 [browser_auth_cli.py:1042](file:///d:\filework\excel-to-diagram\test_helpers\browser_auth_cli.py#L1042) 实现）：

| # | 检查项 | 检查方法 | 失败表现 |
|---|--------|---------|---------|
| 1 | `exists` | `querySelector` 找到 | "element not found in DOM" |
| 2 | `sized` | `rect.width > 0 && rect.height > 0` | 0x0 隐藏元素 |
| 3 | `notHidden` | `display/visibility/opacity` 都不是隐藏 | CSS display:none |
| 4 | `inViewport` | rect 在 viewport 内 | 弹窗在屏幕外 |
| 5 | `notObscured` | `elementFromPoint(centerX, centerY)` 是元素自己或后代 | 被 modal 盖住 |

**只有这 5 步全过才能算 OK。**

---

## 铁律 2：所有 UI 验证必须配截图

### 强制规范

```python
# ✅ 任何 UI 验证都带截图
result = cli.assert_visible('.my-element', screenshot_path='d:/test_results/step_03.png')
```

- **断言失败时**：`assert_visible` 自动截图保存到 `screenshot_path`
- **断言成功时**：在测试报告中记录可视证据
- **每一步操作后**：截图作为时间序列证据

### 反例

- ❌ "我跑了测试，OK 了"（无截图）
- ❌ "DOM 里有，应该可见"（自欺欺人）

---

## 铁律 3：禁止用 `textContent` 验证 Element Plus 下拉

**Element Plus 行为**：所有 `el-option` 都预先渲染到 DOM（即使 popper 关闭）。这意味着 `textContent` 永远有值。

```python
# ❌ 错：textContent 永远有 4 个值
options = popper.textContent  # "重要警告信息提示"
assert 'emoji' not in options  # 假通过

# ✅ 对：用 `assert_visual_contains` 检查视觉可见
result = cli.assert_visual_contains('重要')
assert result['ok']
```

---

## 铁律 4：弹层测试必须验证 z-index 实际效果

```python
# ✅ 不仅检查 zIndex 数值，还要检查实际渲染层级
top_el = page.evaluate("""
    () => {
        const popper = document.querySelector('.el-select-dropdown');
        const rect = popper.getBoundingClientRect();
        return document.elementFromPoint(rect.x + rect.width/2, rect.y + rect.height/2);
    }
""")
# top_el 必须是 popper 自己或其后代，否则被遮挡
```

---

## 铁律 5：自动化测试必须真实复现用户场景

### 反例

- ❌ Headless 模式 + 默认视口（1280x720）+ 默认字体 → 看不到真实环境问题
- ❌ 直接 `querySelector` 不模拟点击 → DOM 存在 ≠ 真实交互

### 正例

```python
# ✅ 模拟真实用户
cli.goto(real_url)
cli.wait_for_timeout(real_load_time)
cli.click(real_button)  # 真实点击，不是 evaluate
page.wait_for_timeout(animation_time)  # 等动画完成

# ✅ 多视口测试
for viewport in [(1920, 1080), (1366, 768), (375, 667)]:
    cli.set_viewport(*viewport)
    result = cli.assert_visible(...)
```

---

## 铁律 6：弹层组件审计清单（写代码前自检）

### Element Plus 弹层组件使用前自检

- [ ] 组件在 `AppModal` 弹窗内？→ 加 `:teleported="false"`
- [ ] 组件在 `el-table` 表格行内？→ 加 `:teleported="false"` 或 `popper-class` 提高 z-index
- [ ] 父容器有 `overflow: hidden/auto/scroll`？→ 弹层会被裁剪
- [ ] 同页面有 > 5 个相同弹层？→ 性能 + z-index 风险

### 自定义组件审计

- [ ] `.app-modal__body` 等滚动容器用 `overflow: visible`？→ 让 popper 溢出
- [ ] z-index 有统一规范（参考 [z-index 标准](#z-index-标准)）？
- [ ] 容器有 `position: relative/absolute/fixed`？→ 建立新的 stacking context

### 表格组件特有问题

- [ ] 表格行内用了 `el-dropdown`？→ 测试点击后 dropdown 是否真的可见
- [ ] 表格单元格用了 `el-tooltip`？→ 测试 hover 后 tooltip 是否真的可见
- [ ] 表格的 `overflow: hidden` 用于文本截断？→ tooltip 必然被裁剪

---

## z-index 标准

| 层级 | 数值 | 用途 | 组件示例 |
|------|------|------|----------|
| **基础** | 0-99 | 页面内容 | 文字、图标、按钮 |
| **悬浮** | 100-999 | hover 效果、tooltip 容器 | inline editor |
| **遮罩** | 1000 | 浮层遮罩 | filter dropdown |
| **弹窗** | 2000 | 弹层（popover、tooltip、select）| **所有 Element Plus 弹层** |
| **模态** | 3000 | Modal 容器 | el-dialog |
| **通知** | 4000 | toast / notification | el-message |
| **最大** | 9999 | 紧急浮层（TourGuide、FeatureHint）| 引导、提示 |

**核心原则**：
- ❌ 永远不要用 9999 作为常规浮层
- ❌ 永远不要用 100、1000 等"整数"——会和 Element Plus 内部值冲突
- ✅ 弹层用 2000-2999，Modal 用 3000+，通知用 4000+

---

## 已知问题清单（需要后续修复）

### 弹层遮挡

| 位置 | 组件 | 状态 |
|------|------|------|
| 任意 modal 内 | `el-select` | ✅ 已修复（AppSelect.vue） |
| 任意 modal 内 | `el-date-picker` | ⚠️ 待统一处理（4 处） |
| 任意 modal 内 | `el-cascader` | ⚠️ 待统一处理 |
| 任意 modal 内 | `el-popover` | ⚠️ 待统一处理 |
| el-table 行内 | `el-dropdown` | 🔴 高危（行操作可能完全不可见） |
| el-table 行内 | `el-tooltip` | 🔴 高危（hover 提示被裁剪） |

### 修复模板

```vue
<!-- ✅ 模板：所有 modal 内 + 表格内的弹层 -->
<el-dropdown :teleported="false" popper-class="my-popper">
  <el-button>...</el-button>
  <template #dropdown>
    <el-dropdown-menu>...</el-dropdown-menu>
  </template>
</el-dropdown>
```

```css
/* ✅ CSS 模板：z-index 标准 */
.my-popper {
  z-index: 2001 !important;  /* 比 Element Plus 默认 (3000) 略低但稳定 */
}
```

---

## 测试框架对照

| 测试方法 | DOM 存在 | 视觉可见 | 推荐使用 |
|---------|---------|---------|---------|
| `query_selector` | ✅ | ❌ | 仅在断言"DOM 已被创建"时用 |
| `textContent` 检查 | ✅ | ❌ | 仅在断言"DOM 里有此文本"时用 |
| `boundingClientRect.width > 0` | ✅ | ❌ | 仅在断言"元素有尺寸"时用 |
| **`assert_visible`** | ✅ | ✅ | **所有 UI 验证的默认方法** |
| `assert_visual_contains` | ✅ | ✅ | 检查特定文本/元素视觉可见 |
| 实际 `page.screenshot()` | ✅ | ✅ | 关键步骤必须配截图 |

---

## 实战示例

### 完整测试：弹窗内下拉视觉可见

```python
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True)

# 1. 登录
cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
cli.wait_for_timeout(1000)

# 2. 进入页面
cli.goto("http://localhost:3004/#/detail/business_object/25")
cli.wait_for_timeout(2000)
cli.screenshot("d:/test/01_detail.png")  # ✅ 步骤截图

# 3. 打开 dialog
cli.click("text=添加备注")
cli.wait_for_timeout(1500)
cli.screenshot("d:/test/02_dialog.png")

# 4. 打开下拉
result = cli.open_dropdown("[data-test-target='category-select']")
assert result['ok'], f"下拉未打开: {result.get('error')}"

# 5. ✅ 视觉验证（核心）
visibility = cli.assert_visible(
    '.el-select-dropdown',
    screenshot_path='d:/test/03_dropdown_FAIL.png'  # 失败时自动截图
)
assert visibility['ok'], f"下拉视觉不可见: {visibility['reason']}"

# 6. ✅ 文本视觉验证
for expected in ['重要', '警告', '信息', '提示']:
    result = cli.assert_visual_contains(expected)
    assert result['ok'], f"'{expected}' 视觉不可见: {result['reason']}"

# 7. 成功截图
cli.screenshot("d:/test/04_dropdown_OK.png")

print("[PASS] 全部视觉检查通过")
```

---

## 总结

> **可测试性 = 用户真实看到的东西**
> **不是 DOM 里有什么，而是用户能看到什么、点到什么、操作什么**

下次写前端测试时，**先问自己 3 个问题**：

1. 如果用户打开浏览器，**真的**能看到这个元素吗？
2. 我能 **截图证明**它可见吗？
3. 关闭测试后，**用户**会不会反馈"还是看不到"？

如果任何一题答"不确定"，**继续修复直到能 100% 证明可见**。

---

## 相关文档

- [dropdown-modal-occlusion.md](../element-plus/dropdown-modal-occlusion.md) - Element Plus 弹层在 modal 内的具体踩坑
- [assert_visible 实现](../../test_helpers/browser_auth_cli.py) - 5 步视觉验证
- [audit_all_poppers.py](../../test_helpers/scripts/audit_all_poppers.py) - 全页面弹层审计
- [verify_dropdown_visible.py](../../test_helpers/scripts/verify_dropdown_visible.py) - 真实视觉验证模板
