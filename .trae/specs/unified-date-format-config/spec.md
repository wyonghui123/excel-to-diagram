# Spec: 统一日期格式配置

> **版本**: v1.2.0
> **创建日期**: 2026-05-24
> **更新日期**: 2026-05-24
> **状态**: Draft
> **优先级**: P1

---

## 1. Background & Objectives

### 1.1 Background

当前系统存在以下问题：

1. **日期格式硬编码**：`formatDate` 函数固定使用 `YYYY-MM-DD HH:mm:ss` 格式，不支持国际化
2. **缺少用户偏好机制**：用户无法自定义日期显示格式、时区等偏好设置
3. **时区处理不正确**：使用服务器时区，跨时区用户看到的时间可能不正确
4. **与业界最佳实践存在差距**：Stripe、Wise、Atlassian 等头部产品都支持用户偏好配置

### 1.2 Business Objectives

- 提供符合国际化标准的日期格式配置能力
- 支持用户个性化偏好设置，提升用户体验
- 建立可扩展的用户偏好配置框架，为后续功能奠定基础

### 1.3 User / Stakeholder (涉众) Objectives

- **最终用户**：能够根据自己的习惯设置日期格式和时区
- **系统管理员**：能够配置系统默认的日期格式
- **开发者**：使用统一的日期格式化 API，无需关心底层配置

---

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence (Source)        |
| ----------------------- | ---------- | ------------------------ |
| Business                | Yes        | 国际化产品需求            |
| User/Stakeholder (涉众) | Yes        | 用户偏好设置              |
| Solution                | Yes        | 四层配置架构设计          |
| Functional              | Yes        | 日期格式化、配置管理      |
| Nonfunctional           | Yes        | 性能、兼容性              |
| External Interface      | Yes        | 前端 API、后端 API        |
| Transition              | Yes        | 现有代码迁移              |

---

## 3. 架构设计：四层配置模型与数据模型决策

### 3.1 四层配置架构

根据 `research-yaml-config-boundary.md` 研究报告，配置应分为四层：

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: YAML 层（元模型定义）                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 定义：字段结构、类型、约束、引擎机制                        │ │
│  │ 特点：Git 版本控制、部署变更                               │ │
│  │ 例子：user.yaml（身份 + 偏好字段）                        │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  Layer 2: 业务配置层（Config Values / DB）                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 定义：系统默认值、租户级配置                               │ │
│  │ 特点：Web UI 变更、热加载、环境间可不同                    │ │
│  │ 例子：enum_value, menu, role_permission                  │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  Layer 3: Personalization 层（个性化配置）                   │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 定义：用户个性化配置，可保存多份、可共享                   │ │
│  │ 特点：1:N 关系、shareable、独立模型                       │ │
│  │ 例子：filter_variant（筛选条件预设）                       │ │
│  └─────────────────────────────────────────────────────────┘ │
│                                                             │
│  Layer 4: 个人 Preference 层（用户偏好）                      │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │ 定义：用户个人偏好，1:1，仅影响自己                        │ │
│  │ 特点：1:1 关系、不共享、合入用户模型                      │ │
│  │ 例子：locale, timezone, date_style ← 本 Spec 范围         │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 核心设计决策：user_preference 合入 user.yaml

**决策**：日期格式偏好字段直接添加到 `user.yaml` 的 `users` 表中，不创建独立的 `user_preference.yaml`。

**判据**：关系类型是决定"合并还是独立"的核心因素。

```
user_preference  vs  filter_variant:

user_preference           filter_variant
  user ←1:1→ pref          user ←1:N→ variants
  永远只有一份              可以有多个
  永远不共享                可以 is_shared=true
  → 合入 user.yaml         → 必须独立模型
```

**业界验证**：

| 产品 | 偏好字段存储位置 | 是否独立表 |
|------|-----------------|:---:|
| **GitHub** | users 表（locale, timezone） | ❌ |
| **GitLab** | users 表（preferred_language, timezone） | ❌ |
| **Django** | User model（language, timezone） | ❌ |
| **SAP Fiori** | 独立表（历史原因，数据量大） | ⚠️ |

**为什么不创建独立的 user_preference.yaml**：

| 维度 | 独立 user_preference.yaml | 合入 user.yaml |
|------|--------------------------|----------------|
| 关系 | 1:1 | 1:1 |
| 查询 | 需 join user_preferences | 直接查 users |
| 复杂度 | 多一个模型、表、API | 更简单 |
| 扩展性 | 各有优劣 | 偏好字段少时更简洁 |
| 与 filter_variant 对比 | 不可比（1:1 vs 1:N） | 不可比（1:1 vs 1:N） |

**Layer 1 和 Layer 4 的共同点**：两者的 Schema 都定义在 YAML 中，数据都通过 API/UI 变更，都是 1:1 关系。它们的区别体现在变更方式上（管理员改身份 vs 用户改偏好），但不体现在表结构上。

### 3.3 最终数据模型

```
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  user.yaml                     filter_variant.yaml       │
│  ┌──────────────────────┐      ┌────────────────────┐   │
│  │ Layer 1 + Layer 4    │      │ Layer 3            │   │
│  │                      │      │                    │   │
│  │ 身份字段:            │      │ id                 │   │
│  │   username           │      │ user_id (FK→user)  │   │
│  │   email              │      │ name               │   │
│  │   password_hash      │      │ filters (JSON)     │   │
│  │   ...                │      │ is_shared          │   │
│  │                      │      │ is_default         │   │
│  │ 偏好字段（新增）:     │      │ ...                │   │
│  │   locale             │      └────────────────────┘   │
│  │   timezone           │           ↑                   │
│  │   date_style         │      user ←1:N→ variants     │
│  │   time_style         │                               │
│  │   hour_cycle         │                               │
│  └──────────────────────┘                               │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

---

## 4. Functional Requirements

### FR-001: 用户偏好配置字段

- **Description**: 在 user.yaml 中新增偏好配置字段
- **Acceptance Criteria**:
  - 在 `user.yaml` 中新增 locale, timezone, date_style, time_style, hour_cycle 字段
  - 每个字段有合理的默认值（locale: zh-CN, timezone: Asia/Shanghai, date_style: medium, time_style: short, hour_cycle: 24）
  - 运行 Schema 同步，users 表新增对应列
  - 现有用户自动填充默认值
- **Priority**: Must
- **Type Mapping**: Solution/Functional
- **Source**: 四层配置架构 + 业界实践（GitHub/GitLab）

### FR-002: 用户偏好 Pinia Store

- **Description**: 前端必须提供 Pinia Store 管理用户偏好状态
- **Acceptance Criteria**:
  - 创建 `useUserPreferencesStore`
  - 支持获取和更新用户偏好
  - 支持本地缓存（localStorage）
  - 与后端 API 同步
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 前端状态管理设计

### FR-003: 配置分层优先级

- **Description**: 日期格式配置必须遵循分层优先级机制
- **Acceptance Criteria**:
  - 优先级从高到低：用户偏好 > 语言默认 > 系统默认
  - 用户未设置时，使用语言默认配置
  - 语言默认配置基于 CLDR（Unicode 通用区域数据仓库）
  - 支持配置回退机制（fallback）
- **Priority**: Must
- **Type Mapping**: Solution
- **Source**: 国际化 SaaS 架构设计

### FR-004: 前端日期格式化服务

- **Description**: 前端必须提供统一的日期格式化服务
- **Acceptance Criteria**:
  - 创建 `DateFormatService` 服务类
  - 使用浏览器原生 `Intl.DateTimeFormat` API 进行格式化
  - 支持传入选项覆盖用户偏好
  - 提供 `format()`, `formatDate()`, `formatTime()` 方法
  - 替换现有的 `formatDate` 硬编码函数
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 前端架构设计

### FR-005: 后端日期格式化服务

- **Description**: 后端必须提供日期格式化服务，支持时区转换
- **Acceptance Criteria**:
  - 创建 `DateFormatService` Python 服务类
  - 支持 UTC 存储转换为用户时区显示
  - 支持配置合并（用户 > 语言 > 系统）
  - 提供格式化方法和时区转换方法
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 后端架构设计

### FR-006: 用户设置界面

- **Description**: 在账户设置页面新增"偏好设置"Tab
- **Acceptance Criteria**:
  - 在 `AccountSettings/index.vue` 新增"偏好设置"Tab
  - 提供语言区域选择（下拉框）
  - 提供时区选择（可搜索下拉框，列出 IANA 时区）
  - 提供日期格式长度选择（单选按钮组）
  - 提供时间格式长度选择（单选按钮组）
  - 提供时间制式选择（12/24 小时制）
  - 提供实时预览功能
  - 通过 `/api/v1/users/me` 接口保存
- **Priority**: Should
- **Type Mapping**: User/Stakeholder (涉众)
- **Source**: 用户体验设计

### FR-007: 语言默认配置

- **Description**: 系统必须为每种支持的语言提供默认日期格式配置
- **Acceptance Criteria**:
  - 在 `config/locales/{locale}.yaml` 或语言配置中定义日期格式
  - 中文（zh-CN）默认：YYYY年MM月DD日，24小时制
  - 英式英语（en-GB）默认：DD/MM/YYYY，24小时制
  - 美式英语（en-US）默认：MM/DD/YYYY，12小时制
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: CLDR 标准

### FR-008: 时区自动检测

- **Description**: 首次登录时自动检测用户时区
- **Acceptance Criteria**:
  - 使用 `Intl.DateTimeFormat().resolvedOptions().timeZone` 检测
  - 首次登录时自动设置检测到的时区
  - 用户可手动覆盖
- **Priority**: Should
- **Type Mapping**: User/Stakeholder (涉众)
- **Source**: 用户体验最佳实践

---

## 5. Nonfunctional Requirements

### NFR-001: 性能

- **Description**: 日期格式化操作必须在 1ms 内完成
- **Measurement**: 单次格式化调用耗时 < 1ms
- **Priority**: Must
- **Source**: 用户体验要求

### NFR-002: 兼容性

- **Description**: 前端必须兼容主流浏览器
- **Measurement**: 支持 Chrome 90+, Firefox 90+, Safari 14+, Edge 90+
- **Priority**: Must
- **Source**: 浏览器市场份额

### NFR-003: 可扩展性

- **Description**: 未来可在 user.yaml 中新增偏好字段
- **Measurement**: 新增偏好字段只需修改 user.yaml，运行 Schema 同步即可
- **Priority**: Should
- **Source**: 未来功能规划

### NFR-004: 无障碍性

- **Description**: 设置界面必须支持无障碍访问
- **Measurement**: 所有表单元素有正确的 label 和 aria 属性
- **Priority**: Should
- **Source**: 无障碍标准

---

## 6. External Interface Requirements

### IF-001: 前端日期格式化 API

- **Type**: JavaScript API
- **Endpoint / Entry**: `DateFormatService.format(date, options)`
- **Request/Response / Interaction**:
  ```javascript
  import { dateFormatService } from '@/services/DateFormatService'
  
  // 基本用法
  const formatted = dateFormatService.format(new Date())
  // 输出: "2025-05-24 14:30" (根据用户配置)
  
  // 覆盖选项
  const fullDate = dateFormatService.format(new Date(), {
    dateStyle: 'full',
    timeStyle: 'long'
  })
  // 输出: "2025年5月24日 星期六 14:30:00"
  
  // 仅日期
  const dateOnly = dateFormatService.formatDate(new Date())
  // 输出: "2025-05-24"
  
  // 仅时间
  const timeOnly = dateFormatService.formatTime(new Date())
  // 输出: "14:30"
  ```
- **Error Handling**: 无效日期返回 `-` 或原始值
- **Source**: 前端 API 设计

### IF-002: 用户偏好 API

- **Type**: REST API（复用现有用户 API）
- **Endpoint / Entry**: 
  - `GET /api/v1/users/me` - 获取当前用户（含偏好字段）
  - `PATCH /api/v1/users/me` - 更新当前用户偏好
- **Request/Response / Interaction**:
  ```json
  // GET /api/v1/users/me Response（新增偏好字段）
  {
    "success": true,
    "data": {
      "id": 1,
      "username": "admin",
      "display_name": "管理员",
      "locale": "zh-CN",
      "timezone": "Asia/Shanghai",
      "date_style": "medium",
      "time_style": "short",
      "hour_cycle": 24
    }
  }
  
  // PATCH /api/v1/users/me Request
  {
    "date_style": "long",
    "timezone": "America/New_York"
  }
  
  // PATCH Response
  {
    "success": true,
    "message": "用户信息已更新"
  }
  ```
- **Error Handling**: 
  - 400: 无效参数
  - 401: 未认证
- **Source**: 后端 API 设计（复用现有 `/api/v1/users/me`）

### IF-003: 用户设置界面入口

- **Type**: UI
- **Endpoint / Entry**: `/account-settings` 页面的"偏好设置"Tab
- **Interaction**: 
  - 用户通过右上角 UserMenu → "账户设置" → "偏好设置" Tab
- **Source**: UI 设计

---

## 7. Transition Requirements

### TR-001: 现有代码迁移

- **Description**: 将现有硬编码的 `formatDate` 函数迁移到新服务
- **Strategy**:
  1. 创建新的 `DateFormatService`
  2. 保留旧 `formatDate` 函数作为兼容层，内部调用新服务
  3. 逐步替换所有调用点（优先替换高频使用点）
  4. 最终移除旧函数（标记为 deprecated）
- **Rollback Plan**: 保留旧函数，可随时回退
- **Source**: 代码迁移计划

### TR-002: 数据库字段添加

- **Description**: 在 users 表中新增偏好字段
- **Strategy**:
  1. 在 `user.yaml` 中新增 5 个偏好字段
  2. 运行 Schema 同步，数据库表新增对应列
  3. 现有用户自动填充默认值
  4. 验证数据完整性
- **Rollback Plan**: 删除新增列
- **Source**: 数据库迁移

### TR-003: 前端组件更新

- **Description**: 更新使用日期格式化的组件
- **Strategy**:
  1. 更新 `MetaListPage` 组件使用新服务
  2. 更新 `useMetaList.js` 中的 `formatDate` 函数
  3. 更新其他使用日期格式化的组件
- **Rollback Plan**: 保留旧函数，组件可回退
- **Source**: 前端迁移

---

## 8. Constraints & Assumptions

### 8.1 Technical Constraints

- 前端使用浏览器原生 `Intl.DateTimeFormat` API，不引入第三方日期库
- 后端使用 Python 标准库 `datetime` 和 `pytz`
- 偏好字段存储在 users 表中（与用户身份信息一起）
- 数据存储始终使用 UTC，显示时转换为用户时区

### 8.2 Business Constraints

- 用户偏好配置仅影响显示，不影响数据存储
- 时区配置仅影响当前用户，不影响其他用户
- 不支持租户级配置（Phase 2 考虑）

### 8.3 Assumptions

- 用户浏览器支持 `Intl.DateTimeFormat` API（主流浏览器均支持）
- 用户知道自己的时区，或允许系统自动检测

---

## 9. Priorities & Milestone Suggestions

| ID     | Requirement | Priority | Reason   |
| ------ | ----------- | -------- | -------- |
| FR-001 | 用户偏好配置字段 | Must | 基础设施 |
| FR-002 | 用户偏好 Pinia Store | Must | 状态管理 |
| FR-003 | 配置分层优先级 | Must | 架构设计 |
| FR-004 | 前端格式化服务 | Must | 用户可见 |
| FR-005 | 后端格式化服务 | Must | 数据处理 |
| FR-006 | 用户设置界面 | Should | 用户体验 |
| FR-007 | 语言默认配置 | Must | 国际化基础 |
| FR-008 | 时区自动检测 | Should | 用户体验 |

### Suggested Milestones

- **Milestone 1 (P0)**: 核心能力
  - user.yaml 新增偏好字段 + 数据库迁移
  - 前后端格式化服务
  - Pinia Store
  - 语言默认配置

- **Milestone 2 (P1)**: 完整体验
  - 用户设置界面（AccountSettings 新增"偏好设置"Tab）
  - 时区自动检测
  - 代码迁移完成

---

## 10. Change / Design Proposal (RFC)

### 10.1 As-Is Analysis

**Current Architecture**:

```
当前日期格式化流程：

后端存储 → ISO 8601 字符串 → 前端硬编码格式化 → 显示
     │                              │
     └─ datetime.now().isoformat()  └─ formatDate(date, 'YYYY-MM-DD HH:mm:ss')
```

**Current Issues**:

1. 格式硬编码，无法国际化
2. 无用户偏好配置机制
3. 时区使用服务器时区，不正确
4. 无配置优先级机制

**Relevant Code Paths**:

- `src/composables/useMetaList.js` - formatDate 函数
- `meta/services/i18n_service.py` - 多语言服务（可扩展）
- `meta/schemas/user.yaml` - 用户模型（新增偏好字段的目标文件）
- `meta/schemas/filter_variant.yaml` - 参考设计（Layer 3 独立模型）
- `src/views/AccountSettings/index.vue` - 账户设置页面

### 10.2 Target State

**Proposed Architecture**:

```
┌─────────────────────────────────────────────────────────────┐
│                    四层配置架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  user.yaml（Layer 1 + Layer 4 合并）                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 身份字段:  username, email, password_hash, ...       │  │
│  │ 偏好字段:  locale, timezone, date_style,             │  │
│  │            time_style, hour_cycle  ← 本 Spec 新增    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  filter_variant.yaml（Layer 3 独立）                        │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ user_id, name, filters (JSON), is_shared, is_default │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  前端流程:                                                  │
│  UTC 时间 → DateFormatService.format()                      │
│           ↓                                                 │
│  Intl.DateTimeFormat(locale, mergedOptions)                 │
│           ↓                                                 │
│  本地化显示                                                  │
│                                                             │
│  后端流程:                                                  │
│  数据存储 → UTC → API 返回 → 前端格式化                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Key Changes**:

1. 在 `user.yaml` 中新增 5 个偏好字段
2. 运行 Schema 同步，users 表新增对应列
3. 创建前端 `DateFormatService`
4. 创建前端 `useUserPreferencesStore`
5. 创建后端 `DateFormatService`
6. 更新 `AccountSettings` 页面新增"偏好设置"Tab
7. 定义语言默认配置
8. 迁移现有 `formatDate` 调用

### 10.3 Detailed Design

#### 10.3.1 数据模型设计

**在 user.yaml 中新增偏好字段**:

```yaml
# meta/schemas/user.yaml 新增的偏好字段

fields:
  # ... 现有的身份字段 ...
  
  # ========== Layer 4: 个人偏好设置 ==========
  # 1:1 关系，合入 user.yaml 而非独立模型
  
  - id: locale
    name: 语言区域
    type: string
    db_column: locale
    default: "zh-CN"
    description: 用户语言区域设置
    enum_values:
      - value: zh-CN
        label: 中文（简体）
      - value: en-US
        label: English (US)
      - value: en-GB
        label: English (UK)
    ui:
      widget: select
      editable: true

  - id: timezone
    name: 时区
    type: string
    db_column: timezone
    default: "Asia/Shanghai"
    description: IANA 时区标识
    ui:
      widget: select
      editable: true

  - id: date_style
    name: 日期格式长度
    type: string
    db_column: date_style
    default: "medium"
    description: 日期显示格式长度
    enum_values:
      - value: full
        label: 完整
        description: 如: 2025年5月24日 星期六
      - value: long
        label: 长
        description: 如: 2025年5月24日
      - value: medium
        label: 中
        description: 如: 2025-05-24
      - value: short
        label: 短
        description: 如: 25-05-24
    ui:
      widget: radio_group
      editable: true

  - id: time_style
    name: 时间格式长度
    type: string
    db_column: time_style
    default: "short"
    description: 时间显示格式长度
    enum_values:
      - value: full
        label: 完整
        description: 如: 14:30:00 CST
      - value: long
        label: 长
        description: 如: 14:30:00
      - value: medium
        label: 中
        description: 如: 14:30:00
      - value: short
        label: 短
        description: 如: 14:30
    ui:
      widget: radio_group
      editable: true

  - id: hour_cycle
    name: 时间制式
    type: integer
    db_column: hour_cycle
    default: 24
    description: 12小时制或24小时制
    enum_values:
      - value: 12
        label: 12小时制
        description: 如: 2:30 PM
      - value: 24
        label: 24小时制
        description: 如: 14:30
    ui:
      widget: radio_group
      editable: true
```

**设计原则**：

| 判据 | user_preference (1:1) | filter_variant (1:N) |
|------|:---:|:---:|
| 关系 | 1:1 → **合入 user.yaml** | 1:N → **独立模型** |
| 是否共享 | 永不共享 | 可 `is_shared` |
| 数据量 | 每个用户 1 条 | 每个用户 N 条 |
| 查询 | 直接查 users 表 | 需要 join filter_variants |

#### 10.3.2 前端服务设计

**src/services/DateFormatService.js**:

```javascript
import { useUserPreferencesStore } from '@/stores/userPreferences'

export class DateFormatService {
  static getInstance() {
    if (!this._instance) {
      this._instance = new DateFormatService()
    }
    return this._instance
  }
  
  format(date, options = {}) {
    const pref = useUserPreferencesStore()
    const locale = options.locale || pref.locale || 'zh-CN'
    const dateStyle = options.dateStyle || pref.dateStyle || 'medium'
    const timeStyle = options.timeStyle || pref.timeStyle || 'short'
    const timeZone = options.timeZone || pref.timezone || this.detectTimezone()
    const hourCycle = options.hourCycle || pref.hourCycle || 24
    
    try {
      return new Intl.DateTimeFormat(locale, {
        dateStyle,
        timeStyle,
        timeZone,
        hourCycle: hourCycle === 24 ? 'h23' : 'h12'
      }).format(new Date(date))
    } catch {
      return '-'
    }
  }
  
  formatDate(date, options = {}) {
    return this.format(date, { ...options, timeStyle: undefined })
  }
  
  formatTime(date, options = {}) {
    return this.format(date, { ...options, dateStyle: undefined })
  }
  
  detectTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone
    } catch {
      return 'UTC'
    }
  }
}

export const dateFormatService = DateFormatService.getInstance()
```

#### 10.3.3 前端 Pinia Store 设计

**src/stores/userPreferences.js**:

```javascript
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserPreferencesStore = defineStore('userPreferences', () => {
  const locale = ref('zh-CN')
  const timezone = ref('Asia/Shanghai')
  const dateStyle = ref('medium')
  const timeStyle = ref('short')
  const hourCycle = ref(24)
  const loaded = ref(false)
  
  async function load() {
    if (loaded.value) return
    try {
      const resp = await fetch('/api/v1/users/me', {
        headers: { 'Authorization': `Bearer ${localStorage.getItem('auth_token')}` }
      })
      const data = await resp.json()
      if (data.success && data.data) {
        locale.value = data.data.locale || 'zh-CN'
        timezone.value = data.data.timezone || 'Asia/Shanghai'
        dateStyle.value = data.data.date_style || 'medium'
        timeStyle.value = data.data.time_style || 'short'
        hourCycle.value = data.data.hour_cycle || 24
      }
      loaded.value = true
    } catch (e) {
      console.error('[UserPreferences] Load failed:', e)
    }
  }
  
  async function save(updates) {
    try {
      const resp = await fetch('/api/v1/users/me', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
        },
        body: JSON.stringify({
          locale: updates.locale,
          timezone: updates.timezone,
          date_style: updates.dateStyle,
          time_style: updates.timeStyle,
          hour_cycle: updates.hourCycle
        })
      })
      const data = await resp.json()
      if (data.success) {
        if (updates.locale) locale.value = updates.locale
        if (updates.timezone) timezone.value = updates.timezone
        if (updates.dateStyle) dateStyle.value = updates.dateStyle
        if (updates.timeStyle) timeStyle.value = updates.timeStyle
        if (updates.hourCycle) hourCycle.value = updates.hourCycle
        return true
      }
      return false
    } catch (e) {
      console.error('[UserPreferences] Save failed:', e)
      return false
    }
  }
  
  return { locale, timezone, dateStyle, timeStyle, hourCycle, loaded, load, save }
})
```

**说明**：偏好数据通过现有的 `GET /api/v1/users/me` 获取，通过 `PATCH /api/v1/users/me` 保存。不需要新建 API。

#### 10.3.4 后端服务设计

**meta/services/date_format_service.py**:

```python
from datetime import datetime
from typing import Optional, Dict
import pytz

class DateFormatService:
    LANGUAGE_DEFAULTS = {
        'zh-CN': {'date_format': '%Y年%m月%d日', 'time_format': '%H:%M', 'hour_cycle': 24},
        'en-US': {'date_format': '%m/%d/%Y',   'time_format': '%I:%M %p', 'hour_cycle': 12},
        'en-GB': {'date_format': '%d/%m/%Y',   'time_format': '%H:%M',     'hour_cycle': 24},
    }
    
    def __init__(self, data_source, user_id: int):
        self.data_source = data_source
        self.user_id = user_id
        self._user = None
    
    def _get_user(self) -> Dict:
        if self._user is None:
            result = self.data_source.query("SELECT * FROM users WHERE id = ?", (self.user_id,))
            self._user = result[0] if result else {}
        return self._user
    
    def format_datetime(
        self, dt: datetime,
        date_style: str = 'medium', time_style: str = 'short',
        timezone: Optional[str] = None
    ) -> str:
        user = self._get_user()
        
        tz_name = timezone or user.get('timezone', 'UTC')
        try:
            tz = pytz.timezone(tz_name)
        except:
            tz = pytz.UTC
        
        if dt.tzinfo is None:
            dt = pytz.UTC.localize(dt)
        local_dt = dt.astimezone(tz)
        
        locale = user.get('locale', 'zh-CN')
        hour_cycle = user.get('hour_cycle', 24)
        
        date_fmt = self.DATE_FORMATS.get(date_style, self.DATE_FORMATS['medium'])
        time_fmt = self.TIME_FORMATS[hour_cycle].get(time_style, self.TIME_FORMATS[hour_cycle]['short'])
        
        return local_dt.strftime(f"{date_fmt} {time_fmt}")
    
    DATE_FORMATS = {
        'full': '%Y年%m月%d日 %A',
        'long': '%Y年%m月%d日',
        'medium': '%Y-%m-%d',
        'short': '%y-%m-%d'
    }
    
    TIME_FORMATS = {
        24: {
            'full': '%H:%M:%S %Z', 'long': '%H:%M:%S',
            'medium': '%H:%M:%S',  'short': '%H:%M'
        },
        12: {
            'full': '%I:%M:%S %p %Z', 'long': '%I:%M:%S %p',
            'medium': '%I:%M:%S %p',   'short': '%I:%M %p'
        }
    }
```

#### 10.3.5 用户设置界面设计

**位置**: `src/views/AccountSettings/index.vue` 新增"偏好设置"Tab

**界面元素**:
- 语言区域选择（下拉框：zh-CN / en-US / en-GB）
- 时区选择（可搜索下拉框，列出常用 IANA 时区）
- 日期格式选择（单选按钮组：完整/长/中/短）
- 时间格式选择（单选按钮组：完整/长/中/短）
- 时间制式选择（单选按钮：12小时制/24小时制）
- 实时预览区域
- 保存按钮（调用 `PATCH /api/v1/users/me`）

### 10.4 Alternatives Considered

| Option   | Pros   | Cons   | Decision |
| -------- | ------ | ------ | -------- |
| 独立 user_preference.yaml | 关注点分离 | 1:1 关系不需要独立表、join 开销、与 GitHub/GitLab 不一致 | Rejected |
| **合入 user.yaml** | 简单、无 join、与业界一致 | 偏好多时 user.yaml 变长（可控） | **Selected** |
| 第三方日期库 | 功能丰富 | 增加依赖、包体积 | Rejected |
| **原生 Intl API** | 无依赖、国际化支持 | API 稍底层 | **Selected** |

### 10.5 Implementation & Migration Plan

**Implementation Order**:

1. 在 `meta/schemas/user.yaml` 中新增 5 个偏好字段
2. 运行 Schema 同步，users 表新增对应列
3. 创建后端 `meta/services/date_format_service.py`
4. 创建前端 `src/services/DateFormatService.js`
5. 创建前端 Pinia Store (`src/stores/userPreferences.js`)
6. 更新 `AccountSettings/index.vue` 新增"偏好设置"Tab
7. 定义语言默认配置
8. 迁移现有 `formatDate` 调用

**Risk Mitigation**:

- 兼容性风险：提供 `formatDate` 兼容层，逐步迁移
- 性能风险：前端使用原生 API，后端直接查 users 表无 join
- 数据风险：新增列有默认值，现有用户自动填充

**Testing Strategy**:

- 单元测试：`DateFormatService` 格式化逻辑
- 集成测试：配置优先级合并逻辑
- E2E 测试：用户设置界面交互

**Rollback Plan**:

- 保留旧 `formatDate` 函数
- users 表新增列可独立删除

---

## 11. TBD List

| ID    | Item   | Missing Information | Next Step |
| ----- | ------ | ------------------- | --------- |
| TBD-1 | 租户级配置 | Phase 2 是否需要租户级默认配置？ | 未来需求 |
| TBD-2 | 自定义格式 | 是否支持用户自定义格式字符串？ | 高级功能，暂不实现 |
| TBD-3 | 更多语言支持 | 是否需要支持更多语言？ | 按业务扩展 |
| TBD-4 | 更多偏好字段 | 未来是否需要主题、通知等？ | user.yaml 已支持扩展 |

---

## 附录 A: 与 filter_variant 的架构对比

| 维度 | user.yaml（偏好字段） | filter_variant.yaml |
|------|----------------------|---------------------|
| 架构层级 | Layer 1 + Layer 4 | Layer 3（Personalization） |
| 关系类型 | 1:1（自身） | 1:N（user_id FK） |
| 是否共享 | 永不共享 | 可 `is_shared=true` |
| 独立性 | **合入 user.yaml** | **独立 YAML + 独立表** |
| 界面对应 | AccountSettings 个人资料 | 业务界面保存筛选条件 |
| 变更频率 | 低（偶尔调整偏好） | 中（保存筛选预设） |

---

## 附录 B: CLDR 日期格式参考

| 语言 | 日期格式（medium） | 时间格式（short） | 时间制式 |
|------|-------------------|------------------|---------|
| zh-CN | 2025-05-24 | 14:30 | 24 |
| en-US | 05/24/2025 | 2:30 PM | 12 |
| en-GB | 24/05/2025 | 14:30 | 24 |
| ja-JP | 2025/05/24 | 14:30 | 24 |
| de-DE | 24.05.2025 | 14:30 | 24 |

---

**Spec 创建完成，等待确认和授权开发。**
