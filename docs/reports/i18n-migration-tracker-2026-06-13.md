# i18n 迁移跟踪报告 - 2026-06-13 (W5)

## 总览

| 指标 | 数值 | 状态 |
|------|:---:|:----:|
| 起点（PR-4.2 后） | 0 字符串 | - |
| 已迁移字符串 | **53+** | ✅ |
| 剩余硬编码（估算） | ~443 | 📋 待办 |
| 测试覆盖 | **22/22 通过** | ✅ |
| 共享 keys | **80 keys** × 2 语言 | ✅ |

## 已完成组件（3）

| 组件 | 字符串 | 测试 | 文件 |
|------|:---:|:---:|------|
| LoginPage.vue | 8 | 3/3 | [查看](file:///d:/filework/excel-to-diagram/src/components/LoginPage.vue) |
| ChangePasswordDialog.vue | 15 | 3/3 | [查看](file:///d:/filework/excel-to-diagram/src/components/ChangePasswordDialog.vue) |
| AccountSettingsDialog.vue | 30+ | 5/5 | [查看](file:///d:/filework/excel-to-diagram/src/components/AccountSettingsDialog.vue) |

## 已建立 i18n 基础设施

| 资产 | 路径 |
|------|------|
| i18n 工具 | [src/i18n/index.js](file:///d:/filework/excel-to-diagram/src/i18n/index.js) |
| zh-CN 字典（80 keys） | [src/i18n/locales/zh-CN.json](file:///d:/filework/excel-to-diagram/src/i18n/locales/zh-CN.json) |
| en-US 字典（80 keys） | [src/i18n/locales/en-US.json](file:///d:/filework/excel-to-diagram/src/i18n/locales/en-US.json) |
| 测试套件（22 测试） | [src/i18n/__tests__/index.spec.js](file:///d:/filework/excel-to-diagram/src/i18n/__tests__/index.spec.js) |

## 迁移模式（标准化）

### 模式 A：模板中的硬编码文本

**Before：**
```vue
<button>取消</button>
<label>用户名</label>
<input placeholder="请输入用户名" />
```

**After：**
```vue
<button>{{ t('common.cancel', '取消') }}</button>
<label>{{ t('auth.username', '用户名') }}</label>
<input :placeholder="t('auth.usernamePlaceholder', '请输入用户名')" />
```

### 模式 B：script 中的字符串

**Before：**
```js
const tabs = [
  { key: 'profile', label: '个人信息' },
  { key: 'security', label: '安全设置' }
]
const userRoles = computed(() => roles.length ? roles.join(', ') : '普通用户')
```

**After：**
```js
import { t } from '@/i18n'
const tabs = [
  { key: 'profile', label: t('accountSettings.tabs.profile', '个人信息') },
  { key: 'security', label: t('accountSettings.tabs.security', '安全设置') }
]
const userRoles = computed(() => roles.length ? roles.join(', ') : t('accountSettings.profile.defaultRole', '普通用户'))
```

### 模式 C：错误消息

**Before：**
```js
message.error('密码修改失败')
```

**After：**
```js
message.error(t('changePassword.failed', '密码修改失败'))
```

### 关键设计决策

1. **保留 fallback 默认值**：`t(key, defaultValue)` - 即使 i18n 文件缺失也不崩
2. **顶层默认 zh-CN**：浏览器语言检测 + localStorage 覆盖
3. **无外部依赖**：自研 ~70 行实现，避免引入 vue-i18n 增加 bundle size
4. **key 命名空间**：用模块名（如 `auth.*`, `accountSettings.*`）避免冲突

## 关键学习

### ✅ 有效模式
1. **批量扩展 locales + 组件** - 减少来回切换
2. **保留默认值** - 即使 i18n 文件不完整也不破坏生产
3. **每个组件 1 个测试文件** - 容易维护

### ⚠️ 注意事项
1. **template 插值必须用 `{{ }}` 或 `:attr=`** - 不能直接在属性值中放 `t()`
2. **script 中的 t() 调用是惰性求值** - 模块加载时执行一次，setLocale 切换不更新
   - 解决：computed 或 function 包裹（见 AccountSettingsDialog 例子）
3. **重复 key 字符串** - 抽到 const 或直接复用（changePassword.* 跨组件复用）
4. **测试需要 setLocale** - 静态测试 + 动态 mount 测试都需

## 剩余 ~443 硬编码 - 优先级建议

### 🔴 高优先级（建议下一批）
| 组件 | 字符串数 | 风险 | 建议时间 |
|------|:---:|:---:|:---:|
| ConfigApp.vue | 6 | 低（auth 类似） | 30 min |
| FeishuBotPanel.vue | 1 | 极低 | 5 min |
| ValidationPanel.vue | 1 | 低 | 5 min |
| ActionExecutor.vue | 2 | 低 | 10 min |
| AssignmentDialog.vue | 1 | 低 | 5 min |
| ArchWorkspaceNew.vue | 3 | 低 | 15 min |
| **小计** | **14** | - | **~70 min** |

### 🟡 中优先级（Q3 计划）
| 组件 | 字符串数 |
|------|:---:|
| FeishuDataImport.vue | 20+ |
| MermaidComponent.vue | 4 |
| EnumSelect.vue | 2 |
| SearchHelpDialog.vue | 1 |
| ValueHelpField.vue | 1 |

### 🟢 低优先级（无明确 i18n 价值）
- 内部 dev/debug 提示
- 罕见的边角错误消息
- 备份日期格式

## 关键 PR 总结

- **W4 PR-4.2**：自研 i18n 工具（11/11 测试）
- **W5-1**：LoginPage 迁移（3/3 测试）
- **W5-2**：ChangePasswordDialog 迁移（3/3 测试）
- **W5-3**：AccountSettingsDialog 迁移（5/5 测试）
- **本报告**：跟踪文档化

## 后续 W6+ 建议

### 立即可做（建议同一 PR）
1. ESLing `no-hardcoded-chinese` 规则 - 防止新硬编码
2. ESLint `t()` 未使用检测 - 防止 import t 但没调用
3. `package.json` 脚本：`"i18n:check"` 扫描新硬编码

### 建议每周迁移节奏
- 1 PR / 2 周
- 每 PR 3-5 个小组件
- 季度目标：迁移 50% 硬编码
