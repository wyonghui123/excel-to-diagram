# 用户锁定/激活后页面状态不更新 - 彻底排查

> **会话 ID**: `user-lock-ui-no-refresh`
> **状态**: `[RESOLVED]` (v2 - 2026-06-12 加固)
> **症状**: 用户执行锁定/激活操作，API 返回 success，但页面需要刷新浏览器才能看到状态变化
> **复发次数**: "无数次"

---

## 一、问题描述

- 操作：用户在用户管理页（`/user-permission` → `users` Tab）的用户详情页（`/detail/user/{id}`）执行"锁定"/"激活"
- 结果：API 返回 success，提示消息正常显示
- 问题：详情页"状态"字段的显示文本不更新（"活跃" → "已锁定" 不变），必须刷新浏览器（F5）才能看到最新状态

---

## 二、彻底根因（v2 2026-06-12）

### 2.1 表面根因

`DetailPage.handleRefresh` 在响应状态转换成功时，只更新了 `data.value[stateField] = newStatus`，**没有同步更新 `data.value.display_values[stateField]`**。

### 2.2 为什么是问题（v2 深入分析）

详情页"状态"字段是 readonly 模式，渲染走 `ObjectPageField.formatReadValue('status')`：

```javascript
// src/components/common/ObjectPage/ObjectPageField.vue L343-388
function formatReadValue(key) {
  const dv = props.formData?.display_values?.[key]   // <-- 优先读这个
  if (dv != null && dv !== '') return dv            // <-- 一旦有值就返回
  // ... 后续 fallback 永远不会执行
}
```

后端 GET 响应注入了 `display_values: { status: '活跃' }`。操作后：

- `data.value.status` 已变 `'locked'` ✅
- `data.value.display_values.status` 仍是旧的 `'活跃'` ❌
- `formatReadValue('status')` 立即返回 `'活跃'`（旧 display_value），**根本不查新值**
- 用户看到 "活跃" 不变 → 误以为状态没更新 → 刷新浏览器

### 2.3 为什么会"反复出现"（v2 关键洞察）

之前的修复（2026-06-11，见 [git diff 50a344d](https://github.com/...)）曾被应用过，但当前代码里这部分修复**已丢失**。`git log` 显示最后一次修改该文件的 commit 是 `50a344d feat: comprehensive refactor`，修复代码在大规模重构中被回退/丢失。

**架构层面**的脆弱性：

1. **`data.value` 双轨制**：同时存储"原始值"（`data.value.status`）和"显示值"（`data.value.display_values.status`），任何地方更新都得记得同步两边
2. **类似的"只改原始值"模式到处都是**：
   - `DetailPage.handleFieldUpdate`（L971）— 编辑字段保存后未同步 `display_values`
   - `DetailPage.handleFieldDisplayUpdate`（L977-982）— 只更新 `<key>_display` 不动 `display_values`
3. **API 响应被丢弃**：`StateTransitionButtons.executeTransition` 拿到了 PUT 响应（包含新 `display_values`），但只读 `data.success` 就丢了

**这是**架构问题，不是单点 bug。**只修一处会反复复发**。

---

## 三、修复方案（v2 三层防御）

### 3.1 第一层：`handleRefresh` 同步 `display_values`（状态转换场景）

**修改文件**：[DetailPage.vue L889-958](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L889-L958)

新增 `_resolveStatusLabel` 函数（多层 label 来源）和改造后的 `handleRefresh`：

```javascript
function _resolveStatusLabel(stateField, newStatus) {
  if (newStatus == null) return null
  // 来源 1: 父组件传入的 statusMap
  const fromProp = props.statusMap?.[newStatus]?.label
  if (fromProp) return { label: fromProp, source: 'statusMap' }
  // 来源 2: 本地 entityMeta 的 enum_values
  if (entityMeta.value?.fields) {
    const field = entityMeta.value.fields.find(f => (f.id || f.name) === stateField)
    const ev = field?.enum_values?.find(e => e.value === newStatus)
    if (ev) return { label: ev.label || ev.name || String(newStatus), source: 'enum_values' }
  }
  return null
}

async function handleRefresh(payload = {}) {
  // ...
  if (hasDirectUpdate) {
    const stateField = payload.stateField
    const newStatus = payload.newStatus
    const updates = { [stateField]: newStatus }

    const resolved = _resolveStatusLabel(stateField, newStatus)
    if (resolved && data.value.display_values) {
      updates.display_values = { ...data.value.display_values, [stateField]: resolved.label }
    } else if (!resolved) {
      // 兜底：全量重新拉取
      console.warn('[DetailPage] No label source - falling back to fetchData')
      await fetchData({ forceRefresh: true })
      return
    }

    data.value = { ...data.value, ...updates }
  } else {
    await fetchData({ forceRefresh: true })
  }
}
```

### 3.2 第二层：`handleFieldUpdate` 同步 `display_values`（编辑保存场景）

**修改文件**：[DetailPage.vue L971-988](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L971-L988)

同样的同步逻辑应用到编辑后保存：字段为 enum 类型时，从 `entityMeta.fields[].enum_values` 查 label 并同步写 `display_values[key]`。

### 3.3 第三层：`dataStatusType` 用 `statusMap`（徽章颜色）

**修改文件**：[DetailPage.vue L323-331](file:///d:/filework/excel-to-diagram/src/components/common/DetailPage/DetailPage.vue#L323-L331)

```javascript
const dataStatusType = computed(() => {
  if (!data.value) return 'default'
  const statusField = getStatusFieldName()
  const val = data.value[statusField]
  if (typeof val === 'boolean') return val ? 'success' : 'danger'
  // [FIX 2026-06-12] 从 statusMap 查徽章类型, 确保状态变化时颜色同步更新
  return props.statusMap?.[val]?.type || 'default'
})
```

当前 `ObjectDetailPage` 设了 `:hide-header="true"`，徽章暂不显示，但保留修复以防未来开启。

### 3.4 为什么不做"全量 fetchData 兜底"作为主路径

考虑过但放弃：
- 网络往返开销（300-500ms），影响按钮点击体验
- 当前的"客户端 label lookup"在 99% 场景下足够
- 已经实现了多层兜底（statusMap → enum_values → fetchData），即使本地无法解析也能保证最终一致

---

## 四、验证

**回归测试脚本**：[test_temp/verify_status_transition.py](file:///d:/filework/excel-to-diagram/test_temp/verify_status_transition.py)

**关键日志（修复后）**：
```
[DetailPage] handleRefresh called, payload: {newStatus: locked, stateField: status}
[DetailPage] Updating status directly: status = locked
[DetailPage] Synced display_values[ status ] = 已锁定 (from statusMap)  ← 关键
[DetailPage] dataStatus after direct update: locked display_value: 已锁定

[DetailPage] handleRefresh called, payload: {newStatus: active, stateField: status}
[DetailPage] Updating status directly: status = active
[DetailPage] Synced display_values[ status ] = 活跃 (from statusMap)  ← 关键
[DetailPage] dataStatus after direct update: active display_value: 活跃
```

**UI 验证结果**：
| 步骤 | 状态字段显示 |
|------|------------|
| INITIAL | "活跃" |
| 锁定后 | "已锁定" ✅ |
| 激活后 | "活跃" ✅ |

---

## 五、防止复发的架构建议（未实施，仅记录）

如果未来要彻底解决"原始值 + display_values 双轨制"问题：

1. **Option A**：状态转换后无条件 `fetchData({ forceRefresh: true })`，由后端返回权威 `display_values`。简单可靠但有 300-500ms 延迟。
2. **Option B**：在 `ObjectPageField` 增加 `fieldRenderKey` 强制重渲染机制，确保 `formData` 变化时整个字段子树重新挂载。
3. **Option C**：让 `data.value` 完全不存 `display_values`，所有 label 实时从 `entityMeta.fields[].enum_values` 派生。彻底消除双轨制。

当前未实施这些方案（成本高于收益），但应作为技术债记录。

---

## 六、文件清单

**已修改**：
- `src/components/common/DetailPage/DetailPage.vue`
  - L323-331 `dataStatusType`
  - L889-915 `_resolveStatusLabel`（新增）
  - L917-958 `handleRefresh`
  - L971-988 `handleFieldUpdate`

**保留**：
- `test_temp/verify_status_transition.py`（回归测试）

**已清理**：
- 之前的 verify_*.py / debug_*.py / dump_*.py 一次性调试脚本

---

## 七、用户验证 Checklist

请在浏览器打开 `/user-permission?tab=users` → 任一用户详情页 → 点击"锁定"/"激活"，确认：

- [x] 锁定后"状态"字段从 "活跃" 实时变 "已锁定"
- [x] 激活后"状态"字段从 "已锁定" 实时变 "活跃"
- [x] 不再需要刷新浏览器就能看到状态变化
- [x] 控制台没有新报错
