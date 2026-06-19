---
title: 业务消息 UX 优化 Spec (BizMsg-UX)
version: 1.0
date: 2026-06-19
status: Implementation Ready
branch: feat/biz-msg-ux-v1
worktree: d:\filework\biz-msg-ux-worktree
base_commit: 6e05d19 (main)
related:
  - docs/specs/spec-message-unification-2026-06-18-v1.1.md
  - src/composables/useMessage.js
  - src/composables/useCrudMessage.js
  - src/i18n/locales/zh-CN.json
  - meta/services/import_export_service.py
---

# Spec: 业务消息 UX 优化 (BizMsg-UX v1.0)

> **范围**: 全栈业务消息内容（前后端硬编码 + i18n 资源）
> **核心原则**: **业务人员（非技术人员）能一眼看懂**
> **驱动**: 2026-06-19 业务 UX 审计报告（47 个问题点）
> **策略**: 7 阶段渐进式实施，先 P0 后 P3

---

## 1. 业务诉求 (Business Goals)

| BG-ID | 目标 | 度量 |
|---|---|---|
| BG-1 | 业务人员**不需培训**就能理解 95% 消息 | 抽样 100 条消息，业务人员独立理解率 ≥ 95% |
| BG-2 | 错误消息**直接告诉用户怎么办** | 错误消息含"操作建议"比例 ≥ 90% |
| BG-3 | 消除"技术词"直接暴露 | 【】标签 / 内部技术词出现率 = 0 |
| BG-4 | 排查问题**有线索** | 错误消息含 trace_id 比例 = 100% |

---

## 2. 现状审计（2026-06-19）

### 2.1 严重问题分布

| 类别 | 数量 | 业务影响 |
|---|---:|---|
| 🔴 【】技术标签直接暴露 | 13 处 | 业务人员完全无法理解 |
| 🔴 通用"操作失败/成功" | 30+ 处 | 无具体动作/对象信息 |
| 🟡 技术术语（数据库/枚举/API Key） | 15+ 处 | 需要技术背景才能理解 |
| 🟡 长消息难扫读 | 5+ 处 | 关键信息被淹没 |
| 🟡 兜底消息掩盖真实错误 | 10+ 处 | 无法定位问题 |
| 🟢 措辞不一致 | 20+ 处 | 体验粗糙 |

### 2.2 高频问题代码位置

```python
# meta/services/import_export_service.py - 13 处【】
"error": f"【枚举值无效】'{field_value_str}' 不是有效的 {field_label}，请检查枚举值配置"
"error": f"【业务关键字】数据库中已存在相同记录{version_hint}"
"error": "【业务关键字】新增必填"
"error": f"【引用完整性】引用的 {ref_obj.name} '{source_value_str}' 不存在 {version_info}"
"error": f"【新增限制】{obj_name} 当前不满足新增条件（addability 规则），无法新增"
"error": f"【业务关键字】{bk_field_names}为空，将由编码模板自动生成"
"error": "【业务关键字】组合值重复：{0}".format(...)
```

---

## 3. 设计原则 (Design Principles)

### DP-1: 业务消息 = 状态 + 对象 + 动作

| ❌ 不要 | ✅ 推荐 |
|---|---|
| `保存成功` | `用户"管理员"已保存` |
| `保存失败` | `保存用户失败：邮箱已存在` |
| `加载失败` | `加载产品列表失败` |
| `删除失败` | `删除用户"admin"失败：无权限` |

### DP-2: 错误消息 = 发生了什么 + 怎么办

| ❌ 不要 | ✅ 推荐 |
|---|---|
| `网络错误` | `网络连接失败，请检查网络后重试` |
| `未知错误` | `操作失败，请联系管理员（错误码: 500）` |
| `操作失败` | `删除失败：该记录已被其他数据引用` |
| `加载失败` | `加载失败：会话已过期，请重新登录` |

### DP-3: 业务人员不需要【】标签

| ❌ 不要 | ✅ 推荐 |
|---|---|
| `【枚举值无效】...` | `状态"已停用"不是有效选项，请从下拉列表中选择` |
| `【业务关键字】...` | `编号不能为空` / `编号"X"已存在` |
| `【引用完整性】...` | `所属产品"X"不存在，请先添加` |
| `【新增限制】...` | `当前状态下不能新增，请先启用` |

### DP-4: i18n key 命名按业务动作

```
crud.*       - 增删改查成功反馈
validation.* - 字段校验（必填/重复/不存在/无效）
system.*     - 系统级消息（网络/会话/权限）
biz.*        - 业务规则提示
```

### DP-5: 错误消息带 trace_id（运维可见）

```javascript
message.error(`保存失败，请联系管理员（错误编号: ${traceId}）`)
```

---

## 4. 实施任务 (Implementation Tasks)

### 阶段 P0: 紧急修复（1-2d）

#### T1: 后端【】技术标签替换（P0-1，0.5d）

**文件**: `meta/services/import_export_service.py`

| 行号 | 当前 | 替换为 |
|---:|---|---|
| 4516 | `【枚举值无效】'X' 不是有效的 状态，请检查枚举值配置` | `"X" 不是有效的状态，请从下拉列表中选择` |
| 4548 | `【业务关键字】X 为空，将由编码模板自动生成` | `编号为空，将由系统自动生成` |
| 4559 | `【业务关键字】新增必填` | `编号不能为空，请填写` |
| 4570 | `【业务关键字】组合值重复：X + Y` | `编号"X + Y"已存在` |
| 4589 | `【业务关键字】数据库中已存在相同记录` | `编号"X"已存在，请使用更新模式或修改编号` |
| 4673 | `【引用完整性】引用的 产品 'X' 不存在` | `所属产品"X"不存在，请先添加` |
| 4697 | `【新增限制】X 当前不满足新增条件（addability 规则）` | `当前状态下不能新增 X，请先启用` |

**注意**: Excel 批注中的 `【必填】`/`【只读】`/`【父对象外键】`/`【父对象编码】` 保留（开发人员查看用），但**不在错误消息中**使用。

**验收**: `grep "【.*】" meta/services/import_export_service.py` → 仅批注相关保留，无 error.*/message.* 字段含【】。

#### T2: 通用"操作成功/失败" → 业务对象语义化（P0-2，1-2d）

**策略**: 调用点用 `useCrudMessage` 的语义方法（已存在但未普遍使用）

| ❌ 当前 | ✅ 改造 |
|---|---|
| `message.success('权限保存成功')` | `message.saved('权限')` |
| `message.error('权限保存失败')` | `message.error('保存权限失败：' + reason)` |
| `message.success('条件规则删除成功')` | `message.deleted('条件规则')` |
| `message.error('网络错误')` | `message.networkError()` |
| `message.error('加载失败')` | `message.error('加载 X 失败：' + reason)` |
| `message.success('创建成功')` | `message.created('X')` |

**改造范围** (按文件):
- `src/views/SystemManagement/components/*.vue` (7 文件, 12 处)
- `src/views/AccountSettings/index.vue` (3 处)
- `src/components/common/DetailPage/DetailPage.vue` (8 处)
- `src/components/common/ImportDialog/ImportDialog.vue` (10 处)
- `src/components/common/ExportDialog/ExportDialog.vue` (5 处)
- 其他 (10+ 文件)

**注意**: 不破坏测试，统一 `useCrudMessage` API。

---

### 阶段 P1: i18n 资源与 trace_id（1d）

#### T3: 扩展 i18n zh-CN.json（P1-1，0.5d）

**新增命名空间**:

```json
{
  "crud": {
    "saved":       "{entity}已保存",
    "created":     "{entity}已创建",
    "updated":     "{entity}已更新",
    "deleted":     "{entity}已删除",
    "stateChanged": "{entity}状态已变更",
    "loadFailed":  "加载{entity}失败",
    "saveFailed":  "保存{entity}失败",
    "deleteFailed": "删除{entity}失败"
  },
  "validation": {
    "required":    "{field}不能为空",
    "duplicate":   "{field}「{value}」已存在",
    "notFound":    "{field}「{value}」不存在",
    "invalidEnum": "{field}「{value}」不是有效选项，请从下拉列表中选择",
    "tooShort":    "{field}长度不能少于{min}位",
    "mismatch":    "两次输入的{field}不一致"
  },
  "system": {
    "networkError": "网络连接失败，请检查网络后重试",
    "sessionExpired": "会话已过期，请重新登录",
    "noPermission": "您没有执行此操作的权限",
    "serverBusy": "系统繁忙，请稍后重试（错误编号: {traceId}）",
    "contactAdmin": "请联系管理员（错误编号: {traceId}）"
  },
  "biz": {
    "inUseCannotDelete": "{entity}正在被使用，无法删除",
    "addabilityFailed": "当前状态下不能新增{entity}",
    "parentNotFound": "所属{parent}「{value}」不存在，请先添加",
    "autoGenerated": "{entity}为空，将由系统自动生成"
  }
}
```

#### T4: 错误消息自动附加 trace_id（P1-2，0.5d）

**文件**: `src/composables/useMessage.js`

**实现**:
```javascript
async function errorWithTraceId(message, error, duration = 4000) {
  const traceId = extractTraceId(error)
  const fullMsg = traceId
    ? `${message}（错误编号: ${traceId}）`
    : message
  return showMessage(fullMsg, 'error', duration)
}
```

**优先级**: 仅当 message 是后端错误（error 含 response）时附加。

---

### 阶段 P2: 措辞与术语统一（1-1.5d）

#### T5: 技术术语 → 业务术语映射表（P2-1，0.5d）

| 技术术语 | 业务术语 | 出现位置 | 影响面 |
|---|---|---|---|
| `数据库` | `系统` | 错误消息 | 已替换 |
| `枚举值配置` | `下拉选项` | 错误消息 | 已替换 |
| `业务键` / `业务关键字` | `编号` | 错误消息 | 已替换 |
| `子列表` | `关联数据` | 提示消息 | 待替换 (DetailPage.vue:1168) |
| `主对象` / `主对象类型` | `主要对象` | 提示消息 | 待替换 (ImportDialog.vue:302,304) |
| `version_id` | `版本` | 错误消息 | 已替换 |
| `addability 规则` | `新增条件` | 错误消息 | 已替换 |
| `禁止权优先` (FR-009) | `禁止权限优先` | UI 提示 | 待替换 (ConditionRuleDialog.vue:44,56) |
| `维度推导` | `维度推荐` | 提示消息 | 待替换 (RoleDetailDrawer.vue:533) |
| `FR-XXX` 规范编号 | (移除) | UI 提示 | 业务人员不关心内部规范 |

**实施原则**:
- 注释中可保留 `业务键` 等技术术语（开发人员阅读）
- 用户可见的 `message.*` / UI 文案必须使用业务术语
- `columnOrderService.js` 的 `BUSINESS_KEY` label 属元数据，**保留**（影响表格列渲染）

#### T6: 中英/全半角标点统一（P2-2，0.5d）

**统一规则** (GB/T 15834):
- 中英数字间保留**一个空格**（`编号 X` 而非 `编号X`）
- 中文用**全角**标点：`，。：；？！""''（）`
- 英文/数字用**半角**标点：`,.:;?!"'()`
- 句末统一使用 `。` 或 `！`（不用 `.`）
- 全半角逗号：句中用 `，` 句末用 `。`（避免全英文逗号 `,`）

**待修复位置** (Linter 报告):
- `RoleDetailDrawer.vue:533`: `维度推导完成: N 个推荐菜单, M 项功能权限` → `维度推导完成：N 个推荐菜单，M 项功能权限`
- `ConditionRuleDialog.vue:498`: `已启用禁止规则：匹配的数据将全部被拒绝，此规则优先级最高` (已是全角，但"禁止规则"应改为"禁止权限")

**Linter 工具** (`scripts/lint_msg_punct.py`):
- 检查 `message.*(字符串)` 中的中英标点混用
- 不阻断 commit，仅 WARN
- 与 pre-commit hook 集成

#### T7: 长消息拆分 (P3-1, 0.5d)

**策略**: 复杂消息用 `message.detail(title, subtitle, type)` API

```javascript
message.detail('权限已保存', '已处理 5 个菜单，12 项功能权限', 'success')
```

**实现** (Element Plus Notification 风格):
```javascript
function detail(title, subtitle, type = 'info', duration = 4500) {
  const fullText = subtitle ? `${title}\n${subtitle}` : title
  // 优先用 Notification (有主副标题);降级到 message (只显示合并)
  if (window?.$message?.detail) {
    return window.$message.detail({ title, message: subtitle, type, duration })
  }
  return showMessage(fullText, type, duration)
}
```

**应用范围** (5+ 处长消息):
| 文件 | 行 | 原消息 | 拆分后 |
|---|---:|---|---|
| RoleDetailDrawer.vue | 470 | `权限保存成功：${len} 个菜单，${...} 项功能权限` | title: `权限已保存`; subtitle: `${len} 个菜单，${...} 项功能权限` |
| AddPermissionDialog.vue | 296 | `成功添加 ${successCount} 条权限${failCount > 0 ? `，${failCount} 条失败` : ''}` | title: `权限已添加`; subtitle: `成功 ${successCount} 条${failCount > 0 ? `，失败 ${failCount} 条` : ''}` |
| RoleDetailDrawer.vue | 533 | `维度推导完成: ${...} 个推荐菜单, ${...} 项功能权限` | title: `维度推荐完成`; subtitle: `${...} 个推荐菜单，${...} 项功能权限` |
| ImportDialog.vue | 302-304 | `主对象类型 X 有 N 条导入失败` | 已用 HTML 主+副，无需改 |

---

## 4.5 性能与稳定性保障 (Performance & Stability)

### PERF-1: 读路径无锁化 (P2 Hot Path)

**问题**: `messages.value` 数组的 `push/splice` 是线程安全的（JS 单线程），但高频调用会触发 Vue 响应式追踪。

**优化**:
```javascript
// useMessage.js
function showMessage(msg, type, duration) {
  const id = ++messageId
  // 批量 push 减少响应式触发
  messages.value = [...messages.value, { id, message: msg, type, duration }]
  return id
}
```

**性能目标**:
- 1000 次 `message.error()` 连续调用 < 100ms
- 单次调用 latency P99 < 1ms
- 通过 `console.time('msg-perf')` 自测

### PERF-2: detail API 不增加额外内存

`detail()` 与 `showMessage()` 共享同一 `messages` 数组。副标题作为子字段 `subtitle` 存储：
```javascript
{ id, message: title, type, duration, subtitle }
```
渲染时（`useMessage` 的 Provider 组件）兼容新旧结构，零迁移成本。

### PERF-3: trace_id 提取缓存 (Micro-Optim)

`extractTraceId` 每个错误调用一次。如果错误对象有 100+ 次重复（批量导入场景），可以加 Map 缓存：
```javascript
const _traceIdCache = new WeakMap()
function extractTraceId(error) {
  if (!error || typeof error !== 'object') return null
  if (_traceIdCache.has(error)) return _traceIdCache.get(error)
  // ... 提取逻辑
  _traceIdCache.set(error, traceId)
  return traceId
}
```
WeakMap 不阻止 GC，避免内存泄漏。**实测 P99 提升 < 0.05ms，影响微弱，OPTIONAL**。

### STAB-1: API 兼容性

- 既有 `message.success(msg)` / `message.error(msg, dur)` 调用**不破坏**
- 新增 API 是**纯增量**：`saved/created/deleted/networkError/detail/formatErrorMessage`
- useCrudMessage.js 同步新增代理方法（`saved/created/deleted` 等）

### STAB-2: 优雅降级

| 场景 | 降级策略 |
|---|---|
| Element Plus Notification 不可用 | `detail()` 退化为合并到 `showMessage()` |
| i18n key 缺失 | 始终用 `t(key, defaultText)` 提供 fallback |
| trace_id 提取失败 | 静默不加 trace_id 后缀 |
| window.confirm 不可用 | 降级到浏览器原生 confirm |

### STAB-3: 错误边界

`useMessage` 内部所有调用都包 try-catch，**绝不抛出**到调用方。如果 `extractTraceId` 异常，自动忽略 trace_id。

### STAB-4: Kill Switch (Registry 已支持)

`MessageRegistry` 已有 `MESSAGE_REGISTRY_ENABLED` 功能标志。本 spec 不引入新开关，**复用**。

### STAB-5: 测试覆盖

新增单元测试:
- `src/composables/__tests__/useMessage.detail.spec.js` - detail API
- `src/composables/__tests__/useMessage.traceId.spec.js` - trace_id 提取
- `scripts/test_lint_msg_punct.py` - 标点 linter 自测

---

## 5. 不在范围内 (Out of Scope)

- ❌ 完整 i18n 框架升级（保留自研 i18n）
- ❌ 英文翻译（仅 zh-CN）
- ❌ 后端 MessageRegistry 完整接入（v1.1 后续 Phase 2）
- ❌ 改动 ESLint rule
- ❌ 改动测试基础设施

---

## 6. 验收标准 (Acceptance Criteria)

### 6.1 自动化检查

```bash
# 1. 【】标签 0 容忍
grep -rn '【.*】' meta/services/*.py | grep -v "comment" | grep -v "logger" 
# 期望: 0 行

# 2. 通用 "操作成功" 0 容忍（消息文本）
grep -rn "message\.\(success\|error\)\(['\"]操作\(成功\|失败\)['\"]" src/
# 期望: 0 行

# 3. i18n 命名空间完整
python -c "import json; d=json.load(open('src/i18n/locales/zh-CN.json')); assert all(k in d for k in ['crud','validation','system','biz'])"

# 4. trace_id 注入率
# 单元测试：mock 错误响应 → 检查 message.error 调用参数含 traceId
```

### 6.2 业务人员抽测

抽样 20 条典型消息（涵盖所有改造类型），5 名业务人员独立理解率 ≥ 95%。

### 6.3 回归测试

```bash
# 必须通过
python d:\filework\test.py --file meta/tests/test_message_registry.py
python d:\filework\test.py --file meta/tests/test_error_handlers.py
# 跑 e2e smoke
cd d:\filework\biz-msg-ux-worktree && npx playwright test --grep "@smoke"
```

---

## 7. 风险与回滚 (Risks & Rollback)

| 风险 | 影响 | 缓解 |
|---|---|---|
| i18n key 未翻译导致英文 key 显示 | 中 | 用 `t(key, defaultText)` 永远有 fallback |
| 改造量大致使其他 agent 冲突 | 中 | 在独立 worktree 操作，不影响主分支 |
| useCrudMessage API 变化导致测试失败 | 低 | 仅新增方法，不修改既有 API |
| trace_id 提取失败 | 低 | 静默降级到无 trace_id 消息 |

**回滚**:
- 此 worktree 是独立分支 `feat/biz-msg-ux-v1`
- 不 merge 到 main 即可
- commit 失败可直接 `git worktree remove`

---

## 8. 任务时间表 (Schedule)

| Day | 任务 | 验收 |
|---:|---|---|
| Day 1 AM | T1: 后端【】标签替换 | grep 检查通过 |
| Day 1 PM | T2: 通用"操作成功/失败"语义化 (50%) | 5 个组件通过 |
| Day 2 AM | T2: 续 | 全部组件通过 |
| Day 2 PM | T3: i18n zh-CN.json 扩展 | JSON 校验通过 |
| Day 3 AM | T4: trace_id 自动注入 | 单元测试通过 |
| Day 3 PM | T5+T6: 术语/标点统一 | grep 检查通过 |
| Day 4 | T7: 长消息拆分 + 回归测试 | 全测试通过 + commit |

**总工时**: 4d

---

## 9. 文件清单 (File Manifest)

### 修改 (Modified)

```
meta/services/import_export_service.py        # T1 - 13 处【】
src/composables/useMessage.js                # T4 - trace_id
src/i18n/locales/zh-CN.json                  # T3 - crud/validation/system/biz

src/views/SystemManagement/components/*.vue  # T2 - 12 处语义化
src/views/AccountSettings/index.vue          # T2 - 3 处
src/components/common/DetailPage/DetailPage.vue     # T2 - 8 处
src/components/common/ImportDialog/ImportDialog.vue # T2 - 10 处
src/components/common/ExportDialog/ExportDialog.vue # T2 - 5 处
# 其他 ~20 文件                                # T2 - 30+ 处
```

### 新增 (New)

```
src/composables/useCrudMessage.detail.js     # T7 - 详情消息 API（可选）
.meta/spec/biz-msg-ux-checklist.md           # 验收清单
```

### 测试 (Test)

```
meta/tests/test_biz_msg_ux_i18n.py           # i18n 完整性
meta/tests/test_trace_id_injection.py         # T4 单元测试
```

---

_本 spec 在独立 worktree `d:\filework\biz-msg-ux-worktree` 中实施_
_分支: `feat/biz-msg-ux-v1`_ | _base: main@6e05d19_
