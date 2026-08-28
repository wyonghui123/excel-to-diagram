# 反勾选菜单保存 bug —— 探针假阳性导致"修复成功"误判

> **记录日期**: 2026-08-28
> **痛点来源**: BUG-V072 修复过程中，第一版探针报告"修复成功"，实际 DB 仍包含被反勾选项；用户实测仍失败
> **核心教训**: **Vue 组件 + Playwright 探针：必须用真实 UI 点击路径触发状态变更，不能直接修改组件 setupState / props.modelValue**

---

## 铁律 1：探针中所有"用户操作"必须走真实 UI 路径，不能绕过组件直接改 props/setupState

### 错误做法（第一版探针）

```python
# ❌ 致命错误：直接修改组件内部 props.modelValue，跳过 MenuPermissionMatrix 的 toggle 逻辑
page.evaluate("""
    () => {
        const m = window.__mpms?.[0]
        const mv = m.props.modelValue
        const up = mv.find(x => x.menu_code === 'user-permission')
        if (up) up.assigned = false   // ← 直接改属性，不触发任何 useMenuPermission 状态更新
    }
""")
```

**为什么错**：

1. `useMenuPermission.isDirty` 只在 `selectAll()` / `clearAll()` / `applyDerived()` 三个函数内部调 `refreshIsDirty()`
2. **MenuPermissionMatrix 的 toggle 函数**直接修改 `node.menu.assigned = assigned` 后只 `emit('update:modelValue', menus.value)`，**从不调 refreshIsDirty()**
3. 所以从 props 层面改 `assigned` 能让 UI 显示对，但 useMenuPermission 的内部状态完全没动 → `isDirty` 还是 false → `hasPendingChanges` 还是 false → `flushOnExit` 分支根本走不到
4. 探针报告"flushOnExit 触发"是**另一个 props.flushOnExit 导致的巧合**，不是真正修复有效

### 正确做法（必须用真实 UI 点击）

```python
# ✅ 真实 UI 点击 checkbox（Element Plus 的 label-click 会触发 toggle）
page.evaluate("""
    () => {
        const cards = [...document.querySelectorAll('.menu-permission-matrix .menu-card')]
        for (const c of cards) {
            if (/用户.*权限/.test(c.textContent || '')) {
                const cb = c.querySelector('input[type=checkbox]')
                cb?.click()    // ← 走真实事件链：MenuPermissionMatrix.toggle → 改 menu.assigned → emit('update:modelValue')
                break
            }
        }
    }
""")
```

**为什么对**：Element Plus 的 checkbox click 会触发 native change event → MenuPermissionMatrix 内的 `@change="(val) => toggle(node, val)"` → 走真实的 toggle 路径。

---

## 铁律 2：探针监控必须**完整覆盖**保存按钮链路，不能"看到 PUT 就认为保存生效"

### 反勾选 bug 的真实链路

```
用户操作: 编辑 → 勾选/反勾选 → 点 ObjectPage 保存按钮
预期行为: PUT /api/v1/roles/12666/menu-permissions 携带新的 menu_codes
实际行为（bug）: PUT /api/v2/bo/role/12666 只更新 role 基本信息，权限完全丢失
                → 刷新后 menu 从 DB 重读回来仍是勾选态
                → 用户看到"反勾选保存后又勾回"
```

### 错误做法（只看 fetch 抓取）

```python
# ❌ 致命错误：抓到了 PUT 就认为保存生效
fl = page.evaluate("() => window.__fl")
# 但这里抓到的 PUT /api/v2/bo/role/12666 只是基本信息保存，
# 不是 menu-permissions 保存。用户感知到的"反勾选丢失"完全没体现
```

### 正确做法（多维度交叉验证）

```python
# ✅ 同时验证：
# 1. PUT 路径必须是 /api/v1/roles/.../menu-permissions（不是 /api/v2/bo/role/...）
# 2. PUT body 必须包含 menu_codes 字段，且值与 DB 终态一致
# 3. DB 终态（直接读 SQLite）必须与 UI 终态一致
# 4. 刷新页面后 modelValue 必须保留改动
```

**DB 终态直接验证** 是最强证据：

```python
import sqlite3
def db_state():
    con = sqlite3.connect('meta/architecture.db')
    rows = [r[0] for r in con.execute(
        "SELECT menu_code FROM role_menu_permissions WHERE role_id=? ORDER BY menu_code",
        (ROLE_ID,)).fetchall()]
    con.close()
    return rows

# 反勾选前
assert 'user-permission' in db_state()
# ... 跑保存流程 ...
# 反勾选后
assert 'user-permission' not in db_state(), f"DB 仍有 user-permission: {db_state()}"
```

---

## 铁律 3：探针不要 reload 页面（除非必要），否则会清掉调试标记

### 错误做法

```python
# ❌ 在保存链路中途 reload 页面 → window.__watchTrigger 被清空
page.reload(wait_until='domcontentloaded')
# 后续检查 window.__watchTrigger 时读到的全是 null
# 误判 "watch 没触发"
```

### 正确做法

调试标记用组件实例的 ref 或 vue devtools，不依赖 window 临时变量。

如果必须用 window 标记，**reload 前先把标记 dump 到 console.log**，并 `page.on('console', ...)` 收集。

---

## 铁律 4：hasPendingChanges 等响应式计算属性不能依赖"未被显式维护"的内部 ref

### BUG-V072 根因

```typescript
// useMenuPermission.ts 内部
const isDirty = ref(false)
function refreshIsDirty() {
    isDirty.value = JSON.stringify(menus.value) !== JSON.stringify(menusSnapshot)
}

// 但 refreshIsDirty 只在 selectAll/clearAll/applyDerived 三个函数内调用
// MenuPermissionMatrix 的 toggle 直接改 menu.assigned，从不调 refreshIsDirty
// → isDirty 永远是 false
```

### 修复（PermissionConfigPanel.vue）

**不要依赖 useMenuPermission.isDirty**，**直接对比 menus 与 editSnapshot**：

```typescript
const menuAssignedDirtyVsSnapshot = computed(() => {
    if (!editSnapshot) return false
    const cur = menus.value || []
    const snap = editSnapshot || []
    if (cur.length !== snap.length) return true
    for (let i = 0; i < cur.length; i++) {
        if (!!cur[i]?.assigned !== !!snap[i]?.assigned) return true
    }
    return false
})

const hasPendingChanges = computed(
    () => menuIsDirty.value || menuAssignedDirtyVsSnapshot.value
        || scopeIsDirty.value || (matrixChanges.value && matrixChanges.value.length > 0),
)
```

**关键**：`editSnapshot` 是模块级 `let`，在 `watch(isEditing, ..., {immediate: false})` 退出分支时由父组件（ObjectPage）通过 `props.editing` 控制 —— 进编辑时拍 snapshot，退出编辑时与 snapshot 对比。

---

## 经验总结

1. **Vue 组件 + Playwright 探针**：所有"用户操作"必须走真实 UI 事件链（click、change、input），不能直接改组件 setupState / props。
2. **多维度交叉验证**：UI 状态 + DB 状态 + 网络请求三者必须一致，缺一不可。
3. **响应式状态依赖最小化**：`hasPendingChanges` 这种"全局 dirty 标志"应该直接基于"对比源数据 + 初始快照"，不应依赖某个 composable 内部的"是否主动通知"机制。
4. **不要在保存链路中途 reload 页面**：会清掉调试标记，污染探针结果。
5. **诚实报告 bug 状态**：探针没看到预期现象就报"没复现"，不要凑合说"修复成功"。用户实测发现 bug 时立即重新设计探针，不要死守第一版结论。

---

## 相关代码

- 探针 v4（真实 UI 路径）：[test_helpers/_probe_real_repro.py](file:///d:/filework/excel-to-diagram/test_helpers/_probe_real_repro.py)
- 探针 v3（假阳性版本，已废弃）：[test_helpers/_probe_save_full.py](file:///d:/filework/excel-to-diagram/test_helpers/_probe_save_full.py)
- 修复位置：[src/views/SystemManagement/components/PermissionConfigPanel.vue](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/components/PermissionConfigPanel.vue#L246-L268)
- 调用入口：[src/views/ObjectDetailPage.vue](file:///d:/filework/excel-to-diagram/src/views/ObjectDetailPage.vue#L65-L72)

---

**最后更新**: 2026-08-28
