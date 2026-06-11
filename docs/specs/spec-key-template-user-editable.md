# Spec: KeyTemplate — `user_editable` 配置项设计

> **版本**: v1.1
> **日期**: 2026-06-11
> **状态**: ✅ Approved by user（已确认分阶段实施）
> **关联 Spec**: [spec-key-template.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-key-template.md) v1.1
> **作者**: AI Agent

---

## 目录

1. [背景与动机](#1-背景与动机)
2. [现状分析](#2-现状分析)
3. [核心设计决策](#3-核心设计决策)
4. [Schema 扩展](#4-schema-扩展)
5. [后端实现](#5-后端实现)
6. [前端实现](#6-前端实现)
7. [导入导出 Excel 模板联动](#7-导入导出-excel-模板联动)
8. [迁移与兼容](#8-迁移与兼容)
9. [测试矩阵](#9-测试矩阵)
10. [分阶段实施计划](#10-分阶段实施计划)
11. [未决问题（TODO）](#11-未决问题todo)

---

## 0. 实施范围说明（2026-06-11 用户确认）

**当前阶段仅实现 `auto_or_manual` 模式**：

| 对象 | 当前阶段（v1.1）| 后续阶段（v1.2+）|
|------|------------------|-------------------|
| `relationship` | ✅ `auto_or_manual` | 后续可切到 `auto_only` |
| `business_object` | ✅ `auto_or_manual` | 后续可切到 `auto_only` |
| `auto_only` 实现 | ❌ **本阶段不实现**，留 TODO | v1.2: Schema 接受但前端不区分；v1.3: 拦截器严格化 |
| `manual_only` 模式 | ❌ 本阶段不实现（默认走 auto）| v1.2+ |

---

## 1. 背景与动机

### 1.1 当前痛点

KeyTemplate 当前对 `code` 字段的处理方式是 **silent auto-generation**：

```python
# meta/core/interceptors/key_template_interceptor.py:39-85
def before_action(self, context: ActionContext) -> None:
    ...
    code_value = params.get('code', '')
    if code_value and str(code_value).strip():
        return  # 用户传了就用用户的（但 schema 不允许空但拦截器会填）
    # 自动生成...
```

| 场景 | 现状 | 用户期望 |
|------|------|---------|
| 业务对象关系 `BO_SUPPLIER-BO_LOCATION-01`已存在，用户填 `A-B-99` | 拦截器跳过→存了 `A-B-99` | ✅ 接受 |
| 用户故意留空希望系统自增 `02` | 拦截器生成 `02` | ✅ 接受 |
| 用户不想填但 Excel 模板说"必填" | 用户懵了，瞎填 | ❌ 错误体验 |
| 管理员想严格管控，禁止手工码 | 无开关 | ❌ 无解 |

### 1.2 头部产品参考

| 产品 | 配置方式 | 默认行为 |
|------|---------|---------|
| **SAP** | Number Range + 内部/外部编码开关 | 可指定 `external` 强制只读 |
| **Salesforce** | Auto Number 字段类型（创建后不可改） | 不可手工，但 `code` 非必填字段 |
| **ServiceNow** | Number Maintenance + 手动覆盖开关 | 可配置 `allow_manual_override` |
| **Odoo** | Sequence + `use_python`（自定义前缀） | 默认 auto，但允许 `prefix` 字段被覆盖 |

**共同模式**：schema 层有一个 **mode 开关**，决定是否允许人工覆盖。

### 1.3 目标

引入 `key_template.user_editable` 配置项，让管理员在 schema 层声明：

- **是否**允许人工指定 `code`（bool）
- **优先级**：auto 优先 vs manual 优先
- **校验策略**：用户输入后如何校验（宽松/严格）

---

## 2. 现状分析

### 2.1 已有的"半支持"机制

| 位置 | 实现 | 局限 |
|------|------|------|
| 前端 `formDirtyFields.has('code')` | 用户编辑过 code → 不覆盖 | 仅前端，后端不感知 |
| 后端 `if code_value: return` | 用户传了 code → 用用户的 | 但 schema 没说"是否允许" |
| UI `ui.editable` | 字段是否可编辑 | 与 key_template 解耦 |

### 2.2 缺失点

1. **Schema 层无声明** — 管理员无法配置"是否允许手工码"
2. **后端无拦截** — 拦截器对所有手动值都接受
3. **Excel 模板无说明** — 用户不知道是否可填
4. **前端 UI 无差异化** — 禁止手动时 input 仍是可编辑的

---

## 3. 核心设计决策

### 3.1 配置项：`user_editable`

**位置**：`key_template` block 顶层

**类型**：`enum`，三个值（本阶段仅实现 `auto_or_manual`）：

| 值 | 含义 | 状态 | 适用对象 |
|----|------|------|---------|
| `auto_only` | code 只读，强制系统生成 | 📋 v1.2+ | 暂不适用 |
| **`auto_or_manual`** | **code 可填可空，填了用用户的，空了系统生成** | ✅ **v1.1 实现** | **`relationship`、`business_object`** |
| `manual_only` | code 必填，不自动生成 | 📋 v1.2+ | 暂不适用 |

### 3.2 默认值推断（本阶段）

| 条件 | 默认 `user_editable` |
|------|----------------------|
| `key_template.enabled = true` | `auto_or_manual` |
| `key_template.enabled = false` 或未配置 | `manual_only` (本阶段按 auto 处理，但 UI 无提示) |

### 3.3 优先级：auto 优先 vs manual 优先

**决策**：**auto 优先**（用户已确认）

| 行为 | 说明 |
|------|------|
| 表单打开 | auto-preview 触发，系统生成 `BO_SUPPLIER-BO_LOCATION-02` 并填入 code 字段 |
| 用户不动 | 保存时使用自动生成值 |
| 用户手改 code 为 `X` | 保存时使用 `X`（formDirtyFields 保护自动覆盖不再触发） |
| 用户清空 code | 重新触发 auto-preview |

### 3.4 校验策略

**决策**：**宽松校验**（用户已确认）

- 只校验 `code != ''` 和 `code` 在表中唯一
- **不**校验是否符合 `pattern`（允许用户自创编码如 `INTERNAL-001`）
- **不**校验 `parent_field` 部分是否匹配（如 source_code）
- 唯一约束由现有 UNIQUE INDEX 保证

### 3.5 本阶段最小变更

**核心原则**：本阶段**只解决"UI 告诉用户可以手填"的问题**，不动拦截器的核心行为。拦截器已支持"用户传了就用用户的"的逻辑（无需修改），只需：

1. Schema 加 `user_editable: auto_or_manual` 声明
2. preview API 返回该字段
3. 前端 UI 在 code input 显示"可填可空"提示
4. Excel 模板说明 sheet 展示规则
5. Excel code 列差异化底色 + comment

---

## 4. Schema 扩展

### 4.1 YAML 配置示例

```yaml
# Relationship: 强制 auto（避免 unique constraint 冲突）
key_template:
  enabled: true
  user_editable: auto_only      # ← NEW
  auto_suggest: true
  pattern: "{source_code}-{target_code}-{SEQ:2}"
  # ...

# Business Object: 兼容模式（迁移期）
key_template:
  enabled: true
  user_editable: auto_or_manual  # ← NEW
  auto_suggest: true
  pattern: "{service_module_code}{SEQ:2}"
  # ...

# Domain: 手动模式（无 key_template）
# 无 key_template block，默认 manual_only
domain:
  fields:
    - id: code
      business_key: true
      # 默认 user_editable: manual_only
```

### 4.2 dataclass 扩展

```python
# meta/core/key_template_engine.py
@dataclass
class KeyTemplateConfig:
    object_id: str
    enabled: bool = False
    user_editable: str = "auto_only"  # ← NEW: auto_only | auto_or_manual | manual_only
    auto_suggest: bool = True
    pattern: str = ""
    # ...
```

### 4.3 校验

```python
VALID_USER_EDITABLE_MODES = frozenset({"auto_only", "auto_or_manual", "manual_only"})

@dataclass
class KeyTemplateConfig:
    def __post_init__(self):
        if self.user_editable not in VALID_USER_EDITABLE_MODES:
            raise ValueError(
                f"Invalid user_editable: {self.user_editable}. "
                f"Must be one of {VALID_USER_EDITABLE_MODES}"
            )
```

---

## 5. 后端实现

### 5.1 `KeyTemplateConfig` dataclass — 新增字段

```python
# meta/core/key_template_engine.py
@dataclass
class KeyTemplateConfig:
    object_id: str
    enabled: bool = False
    user_editable: str = "auto_or_manual"  # ← NEW: 默认 auto_or_manual
    auto_suggest: bool = True
    pattern: str = ""
    # ...

VALID_USER_EDITABLE_MODES = frozenset({"auto_only", "auto_or_manual", "manual_only"})

    def __post_init__(self):
        if self.user_editable not in VALID_USER_EDITABLE_MODES:
            raise ValueError(
                f"Invalid user_editable: {self.user_editable}. "
                f"Must be one of {VALID_USER_EDITABLE_MODES}"
            )
```

### 5.2 `KeyTemplateInterceptor.before_action` — 最小改动

**本阶段拦截器逻辑不变**。现有的"用户传了就用用户的"逻辑已经正确：

```python
# meta/core/interceptors/key_template_interceptor.py
def before_action(self, context: ActionContext) -> None:
    # ... (原逻辑)
    code_value = params.get('code', '')
    if code_value and str(code_value).strip():
        return  # ← 已正确：用户传了就用用户的
    # ... auto 生成逻辑
```

**本阶段仅加日志**（便于追踪）：

```python
if code_value and str(code_value).strip():
    logger.info(
        f"[KeyTemplateInterceptor] Using user-supplied code '{code_value}' "
        f"(user_editable=auto_or_manual, v1.1)"
    )
    return
```

### 5.3 preview API — 返回 user_editable 信息

```python
# meta/api/key_template_api.py
# preview 响应中增加 user_editable 字段
return jsonify({
    'success': True,
    'data': {
        'code': code,
        'generated': generate,
        'object_type': object_type,
        'user_editable': config.user_editable,  # ← NEW
        'pattern': config.pattern,              # ← NEW（便于前端展示）
        'preview': config.preview,              # ← NEW
    }
})
```

前端根据 `user_editable` 决定 code input placeholder 和提示文案。

### 5.4 重复 code 错误处理 — 已优化 ✅

**已有**：`uidx_relationships_code` 等 UNIQUE INDEX 已保证唯一性。

**最近修复**（2026-06-11 Bug E）：拦截器现在会同步 `relation_type` → `relation_code`，避免 UNIQUE 误冲突。

---

## 6. 前端实现

### 6.1 `keyTemplateService.js` — 暴露 user_editable

```javascript
// src/services/keyTemplateService.js
export async function fetchKeyTemplateConfig(objectType) {
  // 调用 GET /api/v2/key-template/config/{object_type}
  // 返回 { enabled, user_editable, pattern, preview, ... }
}
```

### 6.2 `ObjectPageShell.vue` — code input 差异化提示

```vue
<!-- src/components/common/ObjectPage/ObjectPageField.vue -->
<el-input
  v-model="formData.code"
  :placeholder="ktConfig?.user_editable === 'auto_or_manual'
    ? '可填可空；留空由系统自动生成'
    : '由系统自动生成'"
>
  <template #append>
    <el-tag v-if="ktConfig?.user_editable === 'auto_or_manual'" size="small" type="info">
      可手动
    </el-tag>
  </template>
</el-input>
```

### 6.3 用户编辑保护 — 已实现 ✅

`useKeyTemplateFormSync.js` 的 `markFieldDirty('code')` 已保护用户手动值不被覆盖，**无需改动**。

### 6.4 Excel 模板 — code 列差异化底色

```vue
<!-- meta/services/excel_design_system.py -->
AUTO_GEN_OR_MANUAL_FILL = PatternFill(
    start_color="E1F5FE",  # 浅蓝
    end_color="E1F5FE",
    fill_type="solid"
)
```

```python
# meta/services/import_export_service.py
if user_editable == 'auto_or_manual':
    classifications[code_idx] = 'auto_or_manual'  # 浅蓝（区别于黄"必填"）
    comment_parts.append("【自动生成 / 可手动】留空由系统生成，填写则使用填入值")
```

---

## 7. 导入导出 Excel 模板联动

### 7.1 code 列差异化底色 + comment

```python
# meta/services/import_export_service.py - _get_export_headers_with_editable

# NEW: 读取 key_template config
kt_config = getattr(meta_obj, 'key_template', None) or {}
user_editable = kt_config.get('user_editable', 'manual_only')

# 找到 code 字段
code_field_idx = next((i for i, f in enumerate(passed_fields)
                      if getattr(f.semantics, 'business_key', False)), None)

if code_field_idx is not None:
    if user_editable == 'auto_only':
        comment_parts.append("【自动生成】留空即可，系统根据上方父对象字段自动生成；编辑模式只读")
        classifications[code_field_idx] = 'auto_only'  # 浅蓝灰
    elif user_editable == 'auto_or_manual':
        comment_parts.append("【自动生成 / 可手动】留空由系统生成；填值则使用填入值（唯一性校验）")
        classifications[code_field_idx] = 'auto_or_manual'
    # manual_only 保持原"业务关键字"提示
```

### 7.2 新增色 `AUTO_GEN_FILL`

```python
# meta/services/excel_design_system.py
AUTO_GEN_COLOR = "ECEFF1"           # 浅蓝灰
AUTO_GEN_FILL = PatternFill(start_color=AUTO_GEN_COLOR, end_color=AUTO_GEN_COLOR, fill_type="solid")
```

### 7.3 说明 sheet 新增"自动编码规则"区（参考前一份 report）

```python
# _write_meta_sheet_operations 中按对象遍历
for obj_with_tmpl in objects_with_templates:
    kt = obj_with_tmpl.key_template
    ws_meta.cell(row=row, column=1, value=f"【自动编码规则】({obj_with_tmpl.name})").font = LABEL_FONT
    ws_meta.cell(row=row, column=2, value=f"格式: {kt['pattern']}").font = VALUE_FONT
    ws_meta.cell(row=row+1, column=1, value="  模式").font = LABEL_FONT
    ws_meta.cell(row=row+1, column=2, value=USER_EDITABLE_DESC[kt['user_editable']]).font = VALUE_FONT
    ws_meta.cell(row=row+2, column=1, value="  示例").font = LABEL_FONT
    ws_meta.cell(row=row+2, column=2, value=kt['preview']).font = VALUE_FONT
    row += 4
```

`USER_EDITABLE_DESC` 映射：

```python
USER_EDITABLE_DESC = {
    'auto_only': '强制自动：code 列必须留空，系统生成',
    'auto_or_manual': '自动优先：留空由系统生成，填写则使用填入值',
    'manual_only': '纯手动：code 必须由用户填写',
}
```

---

## 8. 迁移与兼容

### 8.1 现有对象的默认配置（本阶段）

| 对象 | 现状 | 本阶段（v1.1）| 后续阶段 |
|------|------|---------------|---------|
| `relationship` | `key_template.enabled=true` | `user_editable: auto_or_manual` | v1.3: 可改 `auto_only` |
| `business_object` | `key_template.enabled=true` | `user_editable: auto_or_manual` | v1.3: 可改 `auto_only` |
| 其他对象 | 无 key_template | 无变化 | - |

### 8.2 YAML 修改

```yaml
# meta/schemas/relationship.yaml
key_template:
  enabled: true
  user_editable: auto_or_manual   # ← NEW: 显式声明
  auto_suggest: true
  # ... 其余不变
```

```yaml
# meta/schemas/business_object.yaml
key_template:
  enabled: true
  user_editable: auto_or_manual   # ← NEW: 显式声明
  auto_suggest: true
  # ... 其余不变
```

### 8.3 兼容性保证

- **向后兼容**：未声明 `user_editable` 时，按 `enabled` 推断（`enabled=true` → `auto_or_manual`）
- **无破坏性**：本阶段拦截器逻辑不变，已有的手动 / 自动行为继续工作
- **现有数据不受影响**

### 8.3 配置缺失的回退

```python
# meta/core/key_template_engine.py - KeyTemplateConfig.from_dict
if not data.get('user_editable'):
    if data.get('enabled'):
        # 启用了 key_template → 默认 auto_or_manual（本阶段唯一支持的模式）
        data['user_editable'] = 'auto_or_manual'
    else:
        data['user_editable'] = 'auto_or_manual'  # 仍 default，UI 无提示
```

---

## 9. 测试矩阵

### 9.1 后端 pytest（本阶段）

```python
def test_user_editable_default_is_auto_or_manual():
    """未声明 user_editable 时，默认 auto_or_manual"""

def test_user_editable_validates_enum():
    """非法 user_editable 值抛 ValueError"""

def test_auto_or_manual_uses_user_code_when_provided():
    """auto_or_manual + user_code 非空 → 使用 user_code"""

def test_auto_or_manual_generates_when_empty():
    """auto_or_manual + user_code 空 → 自动生成"""

def test_preview_returns_user_editable_and_pattern():
    """preview API 返回 user_editable / pattern / preview"""
```

### 9.2 前端 E2E（Playwright）

```javascript
test('auto_or_manual: code placeholder 显示 "可填可空"')
test('auto_or_manual: 右下角显示 "可手动" 标签')
test('auto_or_manual: 填写 code 后不触发自动覆盖')
test('auto_or_manual: 清空 code 后重新触发自动生成')
test('Excel 模板说明 sheet 包含 "自动编码规则" 区')
test('Excel code 列底色 = 浅蓝（区别于黄色必填）')
```

### 9.3 回归（必须全部通过）

- 现有 relationship 测试全部通过
- 现有 BO 测试全部通过
- 现有手动编码对象（product/version/domain）测试全部通过
- 之前的 Bug E 修复（relation_type ↔ relation_code 同步）保持工作

---

## 10. 分阶段实施计划（v1.1 本阶段）

### Phase 1（v1.1 — 当前阶段，本 Spec 范围）

| 任务 | 工时 | 文件 |
|------|------|------|
| 1. KeyTemplateConfig dataclass 加 `user_editable` 字段 + 校验 | 0.5h | `meta/core/key_template_engine.py` |
| 2. 拦截器加 INFO 日志（不改逻辑）| 0.25h | `meta/core/interceptors/key_template_interceptor.py` |
| 3. preview API 返回 `user_editable` / `pattern` / `preview` | 0.5h | `meta/api/key_template_api.py` |
| 4. yaml schema 加 `user_editable: auto_or_manual` | 0.25h | `meta/schemas/relationship.yaml`, `business_object.yaml` |
| 5. 前端 `fetchKeyTemplateConfig` service | 0.5h | `src/services/keyTemplateService.js` |
| 6. `ObjectPageField` code input 提示 + placeholder | 1h | `src/components/common/ObjectPage/*.vue` |
| 7. Excel 模板说明 sheet 加"自动编码规则"区 | 1.5h | `meta/services/import_export_service.py` |
| 8. Excel code 列差异化底色 + comment | 1h | `meta/services/import_export_service.py` + `excel_design_system.py` |
| 9. 后端 pytest（5 个用例）+ 前端 E2E（6 个用例）| 2h | `meta/tests/`, `e2e/features/` |
| **v1.1 总计** | **7.5h** | - |

### Phase 2（v1.2 — 后续）

- 实施 `manual_only` 模式（适用于无 key_template 的手动对象）
- 拦截器根据 `user_editable` 决定是否生成

### Phase 3（v1.3 — 后续）

- 实施 `auto_only` 模式（用于严格管控的关系对象）
- 拦截器忽略用户 code，强制 auto
- 前端 code input 完全 disabled

---

## 11. 未决问题（TODO）

> 以下问题**当前不做决策**，记录为 TODO，留待后续讨论：

### TODO-1：是否需要 `auto_or_manual` 之外的"半手动"模式？

如 `manual_with_auto_fallback`：用户填了就用用户的，没填但其他必填字段已填，由系统生成。
- 决策：**当前不实现**，避免模式过多导致用户混淆。

### TODO-2：v1.3 `auto_only` 模式下，code input 是否完全 disabled？

- **预定决策**：disabled（只读）。理由：用户无法绕过，简洁。
- **替代方案**：enabled 但强制 readonly（用户可看到但不能改）。
- 待 v1.3 PR review 时决定。

### TODO-3：v1.2 `manual_only` 模式下，code 是否仍要遵循 `pattern` 正则？

- **预定决策**：宽松校验（只校验非空 + 唯一）。
- **反方**：宽松可能导致编码格式混乱。
- **折衷**：可在 `key_template` 加 `enforce_pattern_on_manual: false`（默认）让管理员自行开启严格模式。

### TODO-4：v1.3 导入 Excel 时，如何处理 `auto_only` 对象的 code 列？

- **场景**：模板中 code 列被禁用（disabled），但用户仍可能粘贴值。
- **预定决策**：拦截器忽略用户传的 code，自动生成。
- **待确认**：是否需要在前端 import parser 加 warning 提示？

### TODO-5：Excel 模板说明 sheet 是否需要按对象 sheet 分区显示 key_template 规则？

- **当前决策**：是（按对象 sheet 分组）
- **替代**：顶部"全局自动编码规则"区
- 待 UX 评审决定。

### TODO-6：`user_editable` 字段名是否合理？

- 候选：`user_editable` / `mode` / `code_policy` / `entry_mode`
- **当前决策**：`user_editable`（最直接）
- 待命名规范审查决定。

### TODO-7（v1.1 范围）：拦截器只加日志还是显式处理 user_editable？

**问题**：当前拦截器逻辑已经正确（用户传了 → 用用户的；空 → auto 生成）。`auto_or_manual` 与现状一致。

- **当前决策**：仅加 INFO 日志标识"使用了用户传入的 code"，不动核心逻辑。
- **替代**：显式 if/else 分支（更清晰但冗余）。
- 决策已定：保持现状 + 加日志。

---

## 12. 文档同步

| 文档 | 改动 |
|------|------|
| `docs/specs/spec-key-template.md` | 在第 4 章增加 `user_editable` 描述（后续 PR 同步）|
| `meta/schemas/relationship.yaml` | 加 `user_editable: auto_or_manual` |
| `meta/schemas/business_object.yaml` | 加 `user_editable: auto_or_manual` |
| `meta/core/key_template_engine.py` | dataclass 加字段 + 校验 |
| `docs/research/key_template_in_import_export.xlsx.note` | 引用本 spec 作为解决报告 |

---

## 13. 后续 Spec 依赖

- **v1.1（本 Spec）**: **auto_or_manual 模式** — 解决 UI 认知问题
- v1.2 (future): **manual_only 模式** — 适用于 product/version 等纯手动对象
- v1.3 (future): **auto_only 模式** — 严格管控的关系对象
- v1.4 (future): **跨版本迁移工具** — 导入时手动 code 转 auto 生成
- v1.5 (future): **管理员 UI** — 可视化配置 key_template，无需手写 YAML

---

> **审核签字**: _____________________ **日期**: _____________