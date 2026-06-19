# Spec: Tab 持久化绑定用户（跨用户隔离）

## 1. Background & Objectives

### 1.1 Background

`tabStore` 用 `localStorage` 持久化所有打开的顶部 tab（包括 `tabs` 和 `activeTabId`），key 为 `'tab-store'`。这导致两个用户体验问题：

- **跨会话残留**：浏览器关闭重开 → tabs 还在（用户感知：上次开过什么 tab 还在）
- **跨用户泄漏**：用户 A 登录后开 tabs → 登出 → 用户 B 登录 → B 看到 A 的 tabs
  - **安全风险**：tabs 中可能含敏感路径（`/system/user`、`/system/audit`）和调试参数
  - 严重时，B 误以为 A 的 tab 是自己的（数据上下文错乱）

### 1.2 Business Objectives

- 防止 tab 状态跨用户泄漏（**安全**）
- 浏览器关闭重开仍保留当前用户的 tab（**体验**）
- 用户切换时自动清空 tab（**正确性**）

### 1.3 Root Cause

`tabStore.persist` 在 `tabStore.ts:173-208`：
```ts
persist: {
  key: 'tab-store',
  storage: localStorage,  // [FR-016] 跨标签页共享
  pick: ['tabs', 'activeTabId'],
  serializer: { serialize, deserialize },
}
```

**问题**：
1. `serializer` 不绑定 user_id
2. `localStorage` 跨浏览器会话、跨用户保留
3. in-memory state 不感知 user 变化

**已有迁移脚本 `tabStoreLocalToSession.js`**，但**生产代码未 import**（仅 test 引用），属于死代码。

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|------|-----------|----------|
| Business | Yes | 用户反馈：tab 跨用户泄漏、跨会话残留 |
| Security | Yes | tabs 跨用户泄漏 → 敏感路径暴露 |
| Solution | Yes | serializer 绑定 user_id + watch auth.user |
| Functional | Yes | FR-001 ~ FR-004 |
| Nonfunctional | Yes | NFR-001 ~ NFR-003 |

## 3. Functional Requirements

### FR-001: serialize 绑定 user_id
- `serializer.serialize` 在序列化时附加 `_userId: <auth.user.id>` 字段
- 优先级：必填
- **不能引入循环依赖**（tabStore → authStore 单向，authStore 不 import tabStore）

### FR-002: deserialize 校验 user_id
- `serializer.deserialize` 解析时检查 `_userId`：
  - **匹配当前 user.id** → 保留 tabs
  - **不匹配**（含 `_userId: null` vs 当前 `id`，或反之）→ 返回 `{ tabs: [], activeTabId: null }`
  - **解析失败**（legacy 数据无 `_userId`）→ 升级为**当前 user**（不破坏向后兼容）
- 优先级：必填

### FR-003: in-memory user 变化清空
- tabStore 内部 `watch(() => useAuthStore().user?.id, (newId, oldId) => { ... })`
- 当 user.id 变化（登录/登出/切换）→ 清空 `tabs` 和 `activeTabId`
- watch 必须在 hydrate 之后才注册（避免初始化时 user 还没就绪导致误清空）
- 优先级：必填

### FR-004: 死代码清理
- `src/stores/migration/tabStoreLocalToSession.js` 现在已无意义（sessionStorage 路径不再使用）
- **删除该文件**（保留 `src/stores/migration/` 目录的 `__init__.py` 等其他文件）
- 优先级：推荐

## 4. Nonfunctional Requirements

### NFR-001: 性能
- `serialize/deserialize` 是 O(tabs.length)，不引入额外循环
- watch 仅在 user.id 变化时触发，不影响 tab 切换性能

### NFR-002: 兼容性
- 现有 `serializer.serialize/deserialize` 行为完全保留（label 过滤、__pending__ 清理）
- legacy localStorage 数据（无 `_userId`）正常升级

### NFR-003: 可观测性
- 跨用户清空时输出 `console.debug('[tabStore] user changed, clearing tabs:', { oldId, newId })`
- trace_id: 在跨用户清空时输出 `traceId = uuid32()` 便于排查

### NFR-004: 错误码
- 不新增错误码（serializer 失败已 try/catch）

## 5. Solution Design

### 5.1 代码改动

**文件 1: `src/stores/tabStore.ts`**

```ts
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import useAuthStore from './authStore'  // 1. 引入 auth store

// ... 已有 state 和 actions ...

}, {
  persist: {
    key: 'tab-store',
    storage: localStorage,
    pick: ['tabs', 'activeTabId'],
    serializer: {
      serialize: (value) => {
        const auth = useAuthStore()  // pinia 自动 hydrate
        const tabs = value.tabs?.map(...) || []
        return JSON.stringify({
          ...value,
          tabs,
          _userId: auth.user?.id ?? null,  // 2. 附加 user_id
        })
      },
      deserialize: (value) => {
        try {
          const parsed = JSON.parse(value)
          const auth = useAuthStore()
          const currentUserId = auth.user?.id ?? null
          const persistedUserId = parsed._userId ?? null
          
          // 3. 跨用户检测
          if (persistedUserId !== null && persistedUserId !== currentUserId) {
            console.debug(`[tabStore] user mismatch, clearing tabs: persisted=${persistedUserId}, current=${currentUserId}`)
            return { tabs: [], activeTabId: null }
          }
          // 4. legacy 升级: _userId 为 null 但当前 user 已就绪 → 升级
          //    （不破坏老用户数据）
          
          // 已有 __pending__ 清理
          if (parsed.tabs) { ... }
          return parsed
        } catch (_) {
          return { tabs: [], activeTabId: null }
        }
      }
    }
  }
})

// 5. in-memory user 变化清空
useTabStore.$subscribe  // 不好用，因为 auth.user 变化不触发 tabStore mutation
// 改用：
const authStore = useAuthStore()
watch(
  () => authStore.user?.id,
  (newId, oldId) => {
    const currentStore = useTabStore()
    if (oldId !== undefined && newId !== oldId) {
      console.debug(`[tabStore] user changed, clearing tabs: ${oldId} -> ${newId}`)
      currentStore.tabs = []
      currentStore.activeTabId = null
    }
  }
)
```

### 5.2 关键设计点

1. **单向依赖**：tabStore → authStore，authStore **不** import tabStore（避免循环）
2. **serializer 内 useAuthStore()**：pinia 自动按需 hydrate，不要求调用顺序
3. **legacy 升级**：`_userId: null` 且当前 user.id 有值时，**保留** tabs（不破坏老用户）
4. **in-memory watch**：用 Vue 的 `watch` 而非 pinia 的 `$subscribe`，因为 auth 变化不触发 tabStore mutation

### 5.3 死代码清理

- 删除 `src/stores/migration/tabStoreLocalToSession.js`
- 保留目录结构

## 6. Acceptance Criteria

### AC-001: 跨用户隔离
- 用户A登录 → 开 `/system/audit` tab
- 用户A登出 → 用户B登录
- 期望：B 看不到 A 的 `/system/audit` tab
- 验证：浏览器 console 有 `[tabStore] user mismatch, clearing tabs: ...`

### AC-002: 同用户保留
- 用户A登录 → 开 `/system/audit` tab
- 浏览器关闭 → 重开
- 期望：A 重新登录后看到 `/system/audit` tab
- 验证：console 无清空日志

### AC-003: in-memory 切换
- 用户A登录（开多个 tab）→ 不关浏览器
- 用户A登出 → 用户B登录（同浏览器）
- 期望：B 看不到 A 的 tabs（in-memory 已清空）
- 验证：console 有 `[tabStore] user changed, clearing tabs: A -> B`

### AC-004: legacy 兼容
- 清空 localStorage，模拟 legacy 数据
- 用户A登录 → 开 tab → 关闭浏览器
- 重开浏览器 → 登录 A → 看到 tab（升级路径正常）
- 验证：localStorage['tab-store']._userId === A 的 id

## 7. Out of Scope

- tab 历史上限（如保留最近 N 个）：不在本 spec 范围
- tab 跨设备同步：需要后端支持，不在本 spec
- 移除 FR-016 的 localStorage 路径：保留，便于用户主动分享 tab（不推荐）

## 8. References

- `src/stores/tabStore.ts:170-208` - 现有 persist 配置
- `src/stores/authStore.js:181-185` - auth 持久化（user 字段）
- `src/stores/migration/tabStoreLocalToSession.js` - 待删除的死代码
- 头部产品方案：Chrome（Profile 隔离）、VSCode（workspaceStorage）、Slack（DB + cache）

## 9. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| 循环依赖 | High | 严格 tabStore → authStore 单向 |
| hydrate 时机错误 | Medium | 依赖 pinia 自动按需 hydrate，测试覆盖 |
| legacy 数据丢失 | Medium | `_userId: null` 走升级路径，不清空 |
| user.id 类型不一致 | Low | 用 `===` 严格比较，nullable 统一处理 |
| watch 在 hydrate 之前触发 | Low | 用 `oldId !== undefined` 守护初次 |

## 10. Worktree / Branch

- Worktree: `d:\filework\agent-edit-tab-fix`
- Branch: `feat-tab-user-binding-2026-06-19`
- Base: `main` @ `6e42db5`
- Worktree L1-5 状态：完整合规

---

_本 spec 标记 spec_id = `tab-user-binding-v1`, 创建于 2026-06-19_
