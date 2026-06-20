# Spec: DetailPage onActivated forceRefresh (cache 绕过)

## 1. Background

方案 A (`feat-tab-user-binding-2026-06-19`) + bfcache 兜底 fetch (`467dcb8`) 已上线, 用户仍然报告详情页字段空:

- 关闭浏览器重开 → `/detail/enum_type/annotation_category` → 字段 `category/maintainability/description` 显示 `-`
- 整个刷新 (Ctrl+Shift+R) → 字段正常显示 `业务/fully_editable/AnnotationCategory`

我之前 (commit `467dcb8`) 加的 onActivated 兜底 fetch 走 `fetchData()` (无 forceRefresh), 命中 baseService 5 分钟 cache, 返回 stale data (没有 display_values).

## 2. Root Cause Analysis

[DetailPage.vue:1066-1112](file:///d:/filework/agent-detail-force-refresh/src/components/common/DetailPage/DetailPage.vue#L1066-L1112) `fetchData`:

```js
async function fetchData(options = {}) {
  ...
  const result = await boService.read(props.objectType, props.id, options)
  if (result.success) {
    data.value = result.data   // 完全覆盖
  }
}
```

[boCrudService.js:19-31](file:///d:/filework/agent-detail-force-refresh/src/services/bo/boCrudService.js#L19-L31):

```js
async read(objectType, id, options = {}) {
  const cacheKey = this._getCacheKey(objectType, 'read', id)
  if (!options.forceRefresh) {
    const cached = this._getCached(cacheKey)
    if (cached) return cached     // 5 min TTL
  }
  const result = await this._request('GET', `/bo/${objectType}/${id}`)
  ...
}
```

[DetailSection.vue:406-415](file:///d:/filework/agent-detail-force-refresh/src/components/common/DetailPage/DetailSection.vue#L406-L415) `getFieldDisplayValue`:

```js
if (props.data?.display_values?.[field.id] !== undefined) {
  return props.data.display_values[field.id]   // 后端解析的显示值
}
const value = getFieldValue(field)
if (value === null || value === undefined || value === '') {
  return '-'                                    // 没 display_values → 显示 -
}
```

**触发链**:
1. 用户首次访问 → fetchData → cache miss → 后端返回完整 `data + display_values` → UI 显示 `业务/fully_editable/AnnotationCategory`
2. baseService 缓存 result 5 分钟 (cacheKey = `enum_type:read:annotation_category`)
3. 5 分钟内 bfcache 恢复 → onActivated 触发 → fetchData() (无 forceRefresh) → 命中 cache → 返回**之前**的完整 data ✅ (这种情况正常)
4. 但如果**用户第一次访问时数据不完整** (比如刚登录, 某些字段为 null), cache 存的就是不完整的 → onActivated 兜底 fetch 拿到 cache → UI 显示 `-`

更可能: **baseService cache 是 in-memory (line 25 super(100, 5*60*1000))**, 重启后端进程后 cache 清空, 但前端 fetch **没**感知 cache 清空, 5 分钟内继续返回 stale.

**或者**: 用户**强制刷新** (Ctrl+Shift+R) → cache miss → 后端返回**最新** data → UI 正常.
用户**关闭重开** (bfcache) → 命中 cache → 返回**老的** data → UI 异常.

## 3. Functional Requirements

### FR-001: onActivated 兜底 fetch 用 forceRefresh 绕过 cache
[DetailPage.vue:947-959](file:///d:/filework/agent-detail-force-refresh/src/components/common/DetailPage/DetailPage.vue#L947-L959) 改:
```js
onActivated(() => {
  if (coordinatorRefreshKey.value) {
    console.debug(...)
  }
  // [FIX 2026-06-20] bfcache 兜底 fetch + forceRefresh 绕过 baseService 5 分钟 cache
  //   原 BUG: fetchData() 走 cache, 命中 stale data (可能不完整 display_values)
  //   修复: forceRefresh=true 强制后端 fresh fetch
  //   守护: data 不为 null (in-app 切走切回) → 不重复 fetch
  if (data.value === null && props.id && props.mode !== 'add' && props.id !== 'new') {
    const traceId = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID().replace(/-/g, '')
      : `t-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    console.debug(`[DetailPage] onActivated force-refresh fetch, id: ${props.id}, trace_id=${traceId}`)
    fetchData({ forceRefresh: true })  // [FIX] 绕过 cache
  }
})
```

## 4. Nonfunctional Requirements

### NFR-001: in-app 切走切回仍保留滚动位置
- 守护 `data.value === null` 保持不变
- in-app 切走切回 (data 不为 null) → 不 fetch → 保留滚动 ✅

### NFR-002: race condition 防护
- 已有 `loading.value` 状态 (line 1081), fetchData 串行执行
- 不引入新的并发风险

### NFR-003: 性能
- forceRefresh=true 每次都调后端, 5 分钟内可能多 1 次请求
- 但只在 bfcache 恢复时触发, 频率低
- 性能影响可接受

## 5. Solution Design

### 5.1 关键设计点

1. **`fetchData({ forceRefresh: true })`** 而不是 `fetchData()`:
   - 强制 baseService 不走 cache
   - 调后端 fresh fetch
   - 返回**最新** data (含 display_values)

2. **保持 `data.value === null` 守护**:
   - in-app 切走切回 data 不为 null → 不 fetch → 保留滚动位置
   - bfcache 恢复 data 仍可能为 null (Vue 3 keep-alive + bfcache 行为依赖浏览器)

### 5.2 不改的东西

- **不改 onMounted** fetch (line 917): 首次 mount cache 必然 miss, forceRefresh 不必要
- **不改 watch** (line 1050): 切走切回场景, data 已有, 不 fetch
- **不改 baseService cache** (5 min TTL): 全局优化, 不在本次范围

## 6. Acceptance Criteria

### AC-001: 详情页 bfcache 恢复后字段完整
- 用户访问 `/detail/enum_type/annotation_category` → 字段显示
- 关闭浏览器重开 (bfcache 恢复) → 字段**仍**完整显示 (业务/fully_editable/AnnotationCategory)
- console 应看到 `[DetailPage] onActivated force-refresh fetch, id: annotation_category, trace_id=...`

### AC-002: in-app 切走切回仍保留滚动
- 用户在详情页 → app 顶部 tab 切到别的 → 切回
- console **不**看到 force-refresh log (data 不为 null)
- 滚动位置保留

### AC-003: 强制刷新仍正常
- Ctrl+Shift+R → 重新 mount → fetchData (无 forceRefresh) → cache miss (重启) → fresh fetch → 字段正常

## 7. Out of Scope

- baseService cache TTL 调整 (5 min 合理)
- 其他 detail page 缓存策略
- 后端 display_values 计算逻辑

## 8. References

- `src/components/common/DetailPage/DetailPage.vue:947-959` - onActivated
- `src/components/common/DetailPage/DetailPage.vue:903-919` - onMounted
- `src/services/bo/boCrudService.js:19-31` - read cache
- `src/services/baseService.js:54-64` - _request
- `src/components/common/DetailPage/DetailSection.vue:406-415` - getFieldDisplayValue

## 9. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| 性能: 每次 bfcache 多 1 次后端请求 | Low | 频率低, 可接受 |
| 启动后端 cache miss, 第一次 fetch 慢 | Low | 现有 loading 状态可处理 |
| forceRefresh 误用破坏其他场景 | Low | 仅在 onActivated 触发, 范围小 |

## 10. Worktree / Branch

- Worktree: `d:\filework\agent-detail-force-refresh`
- Branch: `fix-detail-force-refresh-2026-06-19`
- Base: `main` @ `30a8fda`
- Worktree L1-5 状态: 完整合规
- **不**在主工作树 merge (L2 规范, 由 Coordinator merge)

---

_本 spec 标记 spec_id = `detail-bfcache-force-refresh-v1`, 创建于 2026-06-20_