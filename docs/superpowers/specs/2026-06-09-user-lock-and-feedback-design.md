# User Lock & Save Feedback Design (2026-06-09)

> **Status**: Draft (awaiting user review)
> **Author**: AI Assistant
> **Scope**: User/Profile lock flow + 全项目 save/CRUD 反馈消息统一

## 1. Background & Problem

### 1.1 当前问题

| 问题 | 位置 | 表现 |
|------|------|------|
| 修改 display_name 后界面给人"被锁定"的错觉 | `EditProfileDialog.vue` / `AccountSettingsDialog.vue` | 保存成功有 `message.success('已更新')`，但页面无明显视觉变化 → 用户误以为操作没生效/账号异常 |
| admin 修改用户时可绕过 state_transition rule 直接 `status='locked'` | `meta/api/user_api.py:473` | `for field in ['email', 'display_name', 'status']` 接受 status 字段，导致状态变更走普通 PUT |
| State transition 反馈用 `ElMessage` | `StateTransitionButton(s).vue` | `ElMessage.success` 在 high-z modal (z-index > 2200) 场景下被遮挡，用户看不见 |
| 全项目 ElMessage vs useMessage 混用 | 散落多处 | 新人不知道用哪个，文案五花八门（"已保存"/"保存成功"/"更新成功"都并存） |

### 1.2 验证：display_name 不会触发 status='locked'

- `meta/api/user_api.py:402-403` `update_user_self` 只接受 `display_name/email/locale/timezone/date_style/time_style/hour_cycle`，**根本不接受 status**
- 所以 `bo.update('user', user_id, {display_name: ...})` 不可能改 status
- rate_limiter (登录失败锁定) 是按 `username` 维度，不受 display_name 影响
- **结论**：用户看到的"被锁定"是 UI 反馈缺失导致的主观误解，不是真实锁定

## 2. Design Goals

1. **G1**: 修改 display_name 后用户立即看到成功反馈，且顶部菜单/头像首字母实时同步
2. **G2**: 后端 status 字段只能通过 `state_transition` action 修改，普通 PUT 一律拒绝
3. **G3**: 全项目 save/CRUD 操作必须有成功反馈，且统一用 `useMessage` (NotificationContainer, z-index 1700)
4. **G4**: ESLint 硬规则禁止 `ElMessage` 直接调用，防止后续回归
5. **G5**: 反馈文案集中管理，便于未来 i18n

## 3. Architecture

### 3.1 New Composable: `useCrudMessage`

**位置**: `src/composables/useCrudMessage.js`

```javascript
import { useMessage } from './useMessage'

/**
 * CRUD 操作语义化反馈
 *
 * 设计目标：
 * - 调用点简洁: message.saved('用户') vs message.success('用户保存成功')
 * - 文案集中: 未来 i18n 零成本
 * - 错误信息自动从 err.response.data.message 提取
 */
export function useCrudMessage() {
  const message = useMessage()

  return {
    // ===== 成功反馈 =====
    /** 保存成功: 显示"用户保存成功" */
    saved: (entity = '数据') => message.success(`${entity}保存成功`),
    /** 创建成功: 显示"用户创建成功" */
    created: (entity = '数据') => message.success(`${entity}创建成功`),
    /** 更新成功: 显示"用户更新成功" */
    updated: (entity = '数据') => message.success(`${entity}更新成功`),
    /** 删除成功: 显示"用户删除成功" */
    deleted: (entity = '数据') => message.success(`${entity}删除成功`),
    /** 状态变更成功: 显示"用户已锁定" */
    stateChanged: (action, entity = '用户') => message.success(`${entity}已${action}`),
    /** 偏好设置保存成功: 显示"偏好设置已保存" */
    preferencesSaved: () => message.success('偏好设置已保存'),
    /** 密码修改成功: 显示"密码修改成功" */
    passwordChanged: () => message.success('密码修改成功'),
    /** 个人信息更新成功: 显示"个人信息已更新" */
    profileUpdated: () => message.success('个人信息已更新'),

    // ===== 错误反馈 =====
    /** 通用错误: 优先用 err.response.data.message, 否则用 err.message */
    error: (defaultMsg = '操作失败', err = null) => {
      const msg = err?.response?.data?.message || err?.message || defaultMsg
      message.error(msg)
    },
    /** 网络错误 */
    networkError: () => message.error('网络错误，请稍后重试'),

    // ===== 透传 (向后兼容) =====
    success: (msg) => message.success(msg),
    warning: (msg) => message.warning(msg),
    info: (msg) => message.info(msg),
    confirm: (opts) => message.confirm(opts),
  }
}
```

**文案集中管理**: 文案先硬编码（中英对齐），后续接 i18n 时只需替换为 `t('crud.saved', { entity })`。

### 3.2 New Composable: `useUserProfileSync`

**位置**: `src/composables/useUserProfileSync.js`

```javascript
import { useAuthStore } from '@/stores/authStore'

/**
 * 用户资料同步器
 *
 * 解决问题：修改 display_name 后顶部菜单/头像首字母实时更新
 *
 * 设计：
 * - 单一真相源: authStore.user.display_name
 * - 同步成功后立即更新 authStore (其他组件 watch 到自动重渲染)
 * - 提供 reload() 强制从服务端刷新 (display_name 被 admin 改后)
 */
export function useUserProfileSync() {
  const authStore = useAuthStore()

  /** 同步到 authStore (前端乐观更新, 立即生效) */
  function sync(updates) {
    if (!authStore.user) return
    if ('display_name' in updates) {
      authStore.user.display_name = updates.display_name
    }
    if ('email' in updates) {
      authStore.user.email = updates.email
    }
  }

  /** 从服务端重载 (admin 修改后强制刷新) */
  async function reload() {
    await authStore.fetchUser?.()
  }

  return { sync, reload }
}
```

### 3.3 ESLint Hard Rule

**位置**: `.eslintrc.cjs` (或项目现有的 eslint 配置文件)

```javascript
module.exports = {
  rules: {
    'no-restricted-imports': ['error', {
      paths: [
        {
          name: 'element-plus',
          importNames: ['ElMessage', 'ElMessageBox', 'ElNotification'],
          message: '禁止直接使用 Element Plus 消息组件。请改用 useMessage/useCrudMessage composable。',
        },
      ],
      patterns: ['element-plus/message', 'element-plus/*/message*'],
    }],
  },
}
```

**降级策略**: 老代码暂留 `// eslint-disable-next-line no-restricted-imports`，在 backlog 里逐步清理。

### 3.4 Backend Hardening: `update_user` 拒绝 status

**位置**: `meta/api/user_api.py:470-486`

**改动**:
```python
# OLD
update_data = {}
for field in ['email', 'display_name', 'status']:
    if field in data:
        update_data[field] = data[field]

# NEW
update_data = {}
for field in ['email', 'display_name']:
    if field in data:
        update_data[field] = data[field]

# status 字段只能走 state_transition action, 普通 PUT 拒绝
if 'status' in data:
    return jsonify({
        'success': False,
        'message': '状态变更必须通过 state_transition 操作, 请使用相关按钮'
    }), 400
```

**配套**: 在 `meta/api/user_api.py` 顶部加注释说明 status 字段的唯一变更路径。

## 4. Component Migration Plan

### 4.1 Phase 1: PoC (核心 8 处)

| 文件 | 改动 |
|------|------|
| `src/components/EditProfileDialog.vue` | `useMessage` → `useCrudMessage` + `useUserProfileSync`，去掉 `setTimeout(close, 1000)` |
| `src/components/AccountSettingsDialog.vue` | `useMessage` → `useCrudMessage` + `useUserProfileSync` |
| `src/components/bo/StateTransitionButton.vue` | `ElMessage` → `useCrudMessage` |
| `src/components/bo/StateTransitionButtons.vue` | `ElMessage` → `useCrudMessage` |
| `meta/api/user_api.py:451-524` | `update_user` 拒绝 `status` 字段 |
| `src/composables/useCrudMessage.js` | 新建 |
| `src/composables/useUserProfileSync.js` | 新建 |
| `.eslintrc.cjs` | 新增 no-restricted-imports 规则 |

### 4.2 Phase 2: 全项目扫描

扫描所有 `.vue` 文件的 `import { ElMessage }` 调用，逐文件迁移。优先级：
1. 用户/权限相关（已涉及）
2. 系统管理（RoleDetailDrawer 已用 useMessage，可作样板）
3. 数据对象 CRUD（用 MetaListPage 的批量保存/删除）
4. 配置/枚举（低风险）

### 4.3 Phase 3: i18n 准备

文案集中在 `useCrudMessage.js`，未来替换为 `t('crud.saved', { entity })`。

## 5. Data Flow

### 5.1 display_name 修改同步流程

```
[EditProfileDialog.handleSubmit]
    ↓
[authService.updateProfile({ display_name, email })]
    ↓
[meta/api/user_api.py: PUT /api/v1/users/me]
    ↓
[bo.update('user', user_id, { display_name })]
    ↓
[DB 写入]
    ↓
[返回 { success: true, data: {...} }]
    ↓
[useUserProfileSync.sync({ display_name })]
    ↓
[authStore.user.display_name = 新值]
    ↓
[Vue reactivity: UserMenu/TopNavHeader/AvatarText 自动重渲染]
    ↓
[message.profileUpdated() toast 显示]
    ↓
[emit('close')] 立即关闭 (去掉 setTimeout)
```

### 5.2 admin 锁定用户流程（变化后）

```
[UserList 点击"锁定"按钮]
    ↓
[StateTransitionButtons executeTransition]
    ↓
[apiV2.put('/bo/user/<id>', { status: 'locked' })]
    ↓
[meta/api/bo_api.py → bo.update('user', ...)]
    ↓
[StateTransitionRule 校验: active → locked 合法]
    ↓
[DB 写入, audit log 记录]
    ↓
[返回 success]
    ↓
[useCrudMessage.stateChanged('锁定', '用户')]
    ↓
[emit('success', 'refresh')]
    ↓
[列表自动刷新]
```

注意：admin 用 PUT 接口直接传 `status` 现在会被后端拒绝（4.0 改动），必须走 state_transition 按钮。

## 6. Error Handling

### 6.1 前端错误处理

`useCrudMessage.error(defaultMsg, err)` 自动从 `err.response.data.message` 提取后端 message，避免重复。

### 6.2 后端错误处理

新加 `status` 字段拒绝逻辑：

```python
if 'status' in data:
    return jsonify({
        'success': False,
        'message': '状态变更必须通过 state_transition 操作, 请使用相关按钮',
        'error_code': 'STATUS_CHANGE_VIA_PUT_NOT_ALLOWED'
    }), 400
```

`error_code` 便于前端区分错误类型（不只是显示文案）。

## 7. Testing Strategy

### 7.1 单元测试

| 测试 | 文件 | 验证点 |
|------|------|--------|
| `useCrudMessage` 单元测试 | `src/composables/__tests__/useCrudMessage.spec.js` (新建) | 各方法正确转发，文案正确 |
| `useUserProfileSync` 单元测试 | `src/composables/__tests__/useUserProfileSync.spec.js` (新建) | sync 后 authStore 立即更新 |
| `EditProfileDialog` 同步测试 | `EditProfileDialog.spec.js` (更新) | 保存后立即触发 sync, 不用 setTimeout |
| `AccountSettingsDialog` 同步测试 | `AccountSettingsDialog.spec.js` (更新) | 同上 |
| `StateTransitionButton(s)` 测试 | `StateTransitionButton.spec.js` (更新) | 用 useCrudMessage, 不依赖 ElMessage |

### 7.2 后端测试

| 测试 | 文件 | 验证点 |
|------|------|--------|
| `update_user` 拒绝 status | `meta/tests/api/test_user_api.py` (新增) | PUT 携带 status 返回 400 |
| `update_user_self` 不接受 status | `meta/tests/api/test_user_api.py` (新增) | 同上 |

### 7.3 E2E 测试

`tests/e2e/user-profile-feedback.spec.js` (新建):
- 改 display_name → 顶部菜单立即显示新名称
- 改 display_name → 看到 toast "个人信息已更新"
- admin 锁定用户 → 看到 toast "用户已锁定" 且不被 modal 遮挡
- admin 用 PUT 直接传 status → 后端 400，前端看到 error_code

### 7.4 回归验证

- 跑现有 user/permission/profile 测试套件（不能回归）
- Lint 全项目（确保 ElMessage 被清空或加 disable 注释）

## 8. Rollout

1. **Phase 1** (PoC): 1-2 天
   - 新建 `useCrudMessage` / `useUserProfileSync`
   - 改 4 个核心组件 + 后端 status 拒绝
   - ESLint 规则加但 warning-only
   - 跑测试

2. **Phase 2** (全扫): 2-3 天
   - ESLint 规则改 error
   - 全项目扫 ElMessage 迁移
   - 跑全测试

3. **Phase 3** (i18n 准备): 后续迭代
   - 文案迁移到 i18n 资源

## 9. Risks & Mitigations

| 风险 | 缓解 |
|------|------|
| ESLint 改 error 后老代码 lint 失败阻塞 CI | Phase 1 仅 warning, Phase 2 改 error 前清空遗留 |
| `useCrudMessage` 文案与现有不一致，部分用户习惯"保存成功" vs "已保存" | 集中在 1-2 种说法，避免分散 |
| admin 误用 PUT 改 status 被拒绝，影响 admin 工作流 | 后端返回明确 error_code + message，前端可在 PermissionConfigPanel 等场景引导用 state_transition 按钮 |
| `setTimeout(close, 1000)` 去掉后 toast 可能看不清 | toast duration 3000ms 默认，足够 |

## 10. Open Questions

无遗留问题，已通过 AskUserQuestion 对齐：

1. ✅ 反馈消息统一用 `useMessage`（项目标准）
2. ✅ 显示名称立即同步顶部菜单/头像
3. ✅ 全项目规范所有 save/CRUD
4. ✅ 实施方式：useCrudMessage 封装 + ESLint 硬规则
5. ✅ 后端 status 字段只能走 state_transition

## 11. CHANGELOG

| 日期 | 版本 | 修改 |
|------|------|------|
| 2026-06-09 | v1.0 | 初稿 |