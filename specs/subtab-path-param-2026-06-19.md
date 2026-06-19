# Spec: Subtab path param + DetailPage onActivated 兜底 fetch

## 1. Background & Objectives

### 1.1 Background

方案 A (tab persistence 绑 user_id, commit `029e98a`) 上线后, 用户报告两个新问题:

**问题 1: GenericTabContainer subtab 错位**
- URL `/user-permission?tab=roles` 进入, 期望显示"角色管理" subtab
- 实际显示"用户管理" subtab (默认第一个), 内容空白
- 现象: tabs 恢复后, subtab 切到错误的 tab

**问题 2: DetailPage 字段空**
- 关闭浏览器重开 (不强制刷新) → 进入 `/detail/enum_type/annotation_category`
- 基本信息字段 (分类/可维护性/描述) 显示 "-"
- 整个刷新 (Ctrl+Shift+R) 后 → 数据完整
- 现象: 关闭重开时, 详情页数据 fetch 没触发

### 1.2 Root Cause 分析

**问题 1 根因**: [GenericTabContainer.vue:103-114](file:///d:/filework/agent-edit-tab-fix/src/views/GenericTabContainer.vue#L103-L114) `allTabs` 优先用 API 菜单:

```js
const allTabs = computed(() => {
  if (USE_API_MENU && menuLoaded.value && apiTabs.value?.length > 0) {
    return apiTabs.value  // key = child.menu_code
  }
  return getGroupTabs(props.group)  // key = t.key (静态配置)
})
```

URL 用 query `?tab=roles` (静态 key), 但 API 菜单加载完后 `allTabs` 切换到 API 菜单 (key = 后端 menu_code), 可能与 `'roles'` 不一致, 找不到 → fallback 到默认 tab.

**问题 2 根因**: [App.vue:53-60](file:///d:/filework/agent-edit-tab-fix/src/App.vue#L53-L60) `ObjectDetail` 在 `cachedRouteNames` 中被 keep-alive 缓存. 关闭浏览器重开时, 浏览器 bfcache 恢复整页 → DetailPage **不**重新 mount → `onMounted` **不**触发 → `fetchData` **不**调 → 显示 stale data.

### 1.3 Business Objectives

- URL 完全反映 subtab 状态 (deep link 友好, 符合头部产品语义)
- 详情页关闭浏览器重开能正常 fetch 数据
- 不破坏 in-app 切走切回体验 (滚动位置、临时输入保留)

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 用户反馈 2 个 tab 相关 bug |
| Solution | Yes | path param 化 + onActivated 兜底 |
| Functional | Yes | FR-001 ~ FR-003 |
| Nonfunctional | Yes | NFR-001 ~ NFR-003 |

## 3. Functional Requirements

### FR-001: GenericTabContainer subtab 用 path param
- [GenericTabContainer.vue:151-157](file:///d:/filework/agent-edit-tab-fix/src/views/GenericTabContainer.vue#L151-L157) `handleTabChange` 改为:
  ```js
  function handleTabChange(key) {
    activeTab.value = key
    visitedTabs.add(key)
    // 改用 path param (如 /user-permission/roles), 不是 query (?tab=roles)
    if (route.params.tab !== key) {
      router.replace({ params: { ...route.params, tab: key } })
    }
  }
  ```
- 路由配置已经在 `router/modules/business.js:30` (`/user-permission/:tab?`), 兼容 path param
- `getInitialTab()` 优先用 `route.params.tab` (line 142)
- 优先级: 必填

### FR-002: DetailPage onActivated 兜底 fetch
- [DetailPage.vue:943](file:///d:/filework/agent-edit-tab-fix/src/components/common/DetailPage/DetailPage.vue#L943) `onActivated` 加 fetch 逻辑:
  ```js
  onActivated(() => {
    // bfcache / keep-alive 恢复时触发
    // - 关闭浏览器重开 (bfcache) → onMounted 不触发, 需在 onActivated 兜底 fetch
    // - in-app 切走切回 → onMounted 不重复触发, 但 data 应已存在, **不**重复 fetch
    // 区分: data 为 null → 真正首次, 需 fetch; data 已存在 → 保留 (滚动位置)
    if (data.value === null && props.id && props.mode !== 'add') {
      console.debug('[DetailPage] onActivated fetch fallback, id:', props.id)
      fetchData()
    }
  })
  ```
- 优先级: 必填
- **不**破坏 in-app 切走切回体验 (data 已存在则不 fetch)

### FR-003: 行为一致性保证
- view 模式: `onMounted` 调 fetch → `onActivated` 仅在 data=null 时 fetch
- add 模式: `onMounted` 初始化 data={} → `onActivated` **不** fetch (add 模式 data={} 不为 null)
- 优先级: 必填

## 4. Nonfunctional Requirements

### NFR-001: 性能
- `handleTabChange` 改为 path param 后, 路由更新逻辑等价 (replace 操作)
- `onActivated` 守卫只在 keep-alive 恢复时触发, 不会重复

### NFR-002: 兼容性
- **不**删除 query param 兼容路径 (防御性保留, 防止外部 deep link)
- 旧 URL `?tab=roles` 仍能工作 (getInitialTab 同时读 params 和 query)
- 旧 tabStore 持久化的 `path` 字段兼容 (path param 化后, path 形如 `/user-permission/roles`)

### NFR-003: 可观测性
- `onActivated` 兜底 fetch 时输出 `console.debug('[DetailPage] onActivated fetch fallback, ...')`
- trace_id: 不强制要求 (本 PR 是 feature, 不是 bug fix)

## 5. Solution Design

### 5.1 代码改动

**文件 1: `src/views/GenericTabContainer.vue`**

```diff
 function handleTabChange(key) {
   activeTab.value = key
   visitedTabs.add(key)
-  if (route.query.tab !== key) {
-    router.replace({ query: { ...route.query, tab: key } })
+  if (route.params.tab !== key) {
+    router.replace({ params: { ...route.params, tab: key } })
   }
 }
```

**文件 2: `src/components/common/DetailPage/DetailPage.vue`**

```diff
 onActivated(() => {
   // 原有 coordinator 逻辑
   ...
+  // [FIX 2026-06-19] bfcache 兜底 fetch
+  //   场景: 关闭浏览器重开 → bfcache 恢复 → onMounted 不触发
+  //   修复: data 为 null 时在 onActivated 调 fetch
+  //   守护: data 不为 null (in-app 切走切回) → 不重复 fetch
+  if (data.value === null && props.id && props.mode !== 'add') {
+    console.debug('[DetailPage] onActivated fetch fallback, id:', props.id, 'trace_id=', ...)
+    fetchData()
+  }
 })
```

### 5.2 关键设计点

1. **path param 化**: URL 形如 `/user-permission/roles`, deep link 友好
2. **onActivated 兜底**: 只在 bfcache 场景触发, in-app 切走切回**不**受影响
3. **query 兼容**: 旧 query 形式仍能 work (防御性保留)

## 6. Acceptance Criteria

### AC-001: subtab path param
- 用户点"角色管理" subtab → URL 变为 `/user-permission/roles`
- 用户复制 URL, 新窗口打开 → 直接显示"角色管理" subtab
- 关闭浏览器重开 → tabs 恢复 → 跳到 `/user-permission/roles` → 显示"角色管理" subtab

### AC-002: DetailPage bfcache 兜底
- 用户进入 `/detail/enum_type/annotation_category` → 字段显示
- 关闭浏览器 (不强制刷新) → 重新打开 → 字段**正常**显示 (不空)
- console 应看到 `[DetailPage] onActivated fetch fallback, id: annotation_category, ...`

### AC-003: in-app 切走切回不破坏
- 用户在详情页 → app 顶部 tab 切到"角色管理" → 切回详情页
- 滚动位置保留, **不**重新 fetch, **不**显示 loading
- console **不**看到 `onActivated fetch fallback` (因为 data 不为 null)

## 7. Out of Scope

- 删除 query param 兼容路径 (保留, 防止外部 link)
- tabStore 持久化 path 字段迁移 (无需, 旧 path 仍 work)

## 8. References

- `src/views/GenericTabContainer.vue:138-149` - getInitialTab
- `src/views/GenericTabContainer.vue:151-157` - handleTabChange
- `src/router/modules/business.js:30` - 路由配置 (/:tab?)
- `src/components/common/DetailPage/DetailPage.vue:903-919` - onMounted
- `src/components/common/DetailPage/DetailPage.vue:943-947` - onActivated
- `src/App.vue:53-60` - cachedRouteNames
- 头部产品方案: GitHub (`/repo/issues/labels`), Slack (`/channel-id`)

## 9. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| path param 化破坏 tabStore 持久化 | Medium | 旧 path 仍兼容, tabStore.tabs.path 不变 |
| onActivated 重复 fetch | High | 守护 `data.value === null` |
| query 形式 link 失效 | Low | getInitialTab 同时支持 query/params |
| bfcache 行为依赖浏览器 | Medium | 整个刷新仍 work (onMounted 路径) |

## 10. Worktree / Branch

- Worktree: `d:\filework\agent-edit-tab-fix`
- Branch: `feat-subtab-path-param-2026-06-19`
- Base: `main` @ `029e98a`
- Worktree L1-5 状态: 完整合规

---

_本 spec 标记 spec_id = `subtab-path-param-v1`, 创建于 2026-06-19_
