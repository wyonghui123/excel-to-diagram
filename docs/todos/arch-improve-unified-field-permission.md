# TODO: 统一字段权限配置（单一配置源）

## 背景

**问题发现日期**: 2026-06-10
**版本**: v1.0.9

### 当前架构问题

`fields` 配置与 `list-view.columns` 配置是**两套独立系统**，修改一个不会自动同步另一个。`enrichColumnsWithFieldMeta` 只富化 `hidden_*` 字段到 column，**没有**富化 `editable` 和 `immutable`。

| 配置层 | editable 控制点 | hidden_in_form 控制点 |
|--------|--------------|-------------------|
| `fields` | `useFieldPolicy.isFieldEditable` | ObjectPageShell/DetailPage |
| `list-view.columns` | `useMetaList.isCellEditable` | `enrichColumnsWithFieldMeta` |
| 后端 | `_filter_immutable_fields` | `OwnerAutoPermissionInterceptor` |

### 教训

1. **`fields` vs `list-view.columns` 解耦**：inline edit 读的是 `column.editable`，不是 `fields.editable`
2. **`_display` 后缀匹配问题**：`owner_id_display` 列匹配不到 `owner_id` 字段
3. **后端类型不一致**：`SemanticAnnotation` 对象 vs dict 导致 `isinstance(sem, dict)` 静默失效
4. **前端 `hidden_in_form` 逻辑分散**：ObjectPageShell、DetailPage、useMetaList 各自判断

## TODO 任务

### 高优先级

- [ ] **[fields → columns 自动同步]**: `enrichColumnsWithFieldMeta` 在富化时同步 `editable` 和 `immutable` 从 fields 到 columns
  - 文件: `src/services/metaTransformService.js`
  - 逻辑: 当 column key 匹配到 field 时，把 field 的 `ui.editable` 和 `semantics.immutable` 同步到 column

- [ ] **[解决 `_display` 后缀匹配]**: 富化时支持 `owner_id_display` 匹配到 `owner_id` 字段
  - 文件: `src/services/metaTransformService.js` 或 `meta/core/yaml_loader.py`
  - 逻辑: 匹配时去掉 `_display`/`_name` 等后缀后再匹配

- [ ] **后端类型一致性**: `_filter_immutable_fields` 兼容 `SemanticAnnotation` 对象
  - 状态: **已完成** ✅ (v1.0.9)
  - 文件: `meta/core/interceptors/persistence_interceptor.py`

### 中优先级

- [ ] **[统一 `hidden_in_form` 逻辑]**: 抽取为 `useFieldPolicy.isFieldVisibleInForm(mode)` 统一判断
  - 文件: `src/composables/useFieldPolicy.js`
  - 当前逻辑分散在:
    - `src/components/common/ObjectPage/ObjectPageShell.vue` (L183-L187)
    - `src/components/common/DetailPage/DetailPage.vue` (L337-L338, L481-L482)
    - `src/composables/useMetaList.js` (L1406-L1408)

- [ ] **[字段可见性元数据建模]**: 后端返回统一字段元数据，前端各视图统一消费
  - 文件: `meta/api/meta_api.py`
  - 逻辑: `/api/v1/meta/{object_type}` 返回 `fields` 时包含 `view_permissions` 对象:
    ```json
    {
      "id": "owner_id",
      "ui": { "editable": false },
      "semantics": { "immutable": true },
      "view_permissions": {
        "list": { "editable": false, "visible": true },
        "form": { "editable": false, "visible": false },
        "detail": { "editable": false, "visible": true }
      }
    }
    ```

### 低优先级

- [ ] **单元测试覆盖**: `fields.editable` 变化时验证 columns 同步
  - 文件: `src/composables/__tests__/metaTransformService.spec.js`

## 相关文件

### 后端 (Python)
- `meta/core/yaml_loader.py` - YAML 解析，models 定义
- `meta/core/models_ui_config.py` - `UIListViewColumn` model (已加 hidden_in_form 字段 ✅)
- `meta/core/interceptors/persistence_interceptor.py` - `_filter_immutable_fields` (已修复 ✅)
- `meta/core/interceptors/owner_permission_interceptor.py` - `OwnerAutoPermissionInterceptor`

### 前端 (Vue/JS)
- `src/components/common/ObjectPage/ObjectPageShell.vue` - form dialog (已加 hidden_in_form+editable 判断 ✅)
- `src/components/common/DetailPage/DetailPage.vue` - detail 页面 (已加判断 ✅)
- `src/composables/useMetaList.js` - list 表格 (L1399-L1424 isCellEditable)
- `src/composables/useFieldPolicy.js` - 字段策略 (L100-180 editable 逻辑)
- `src/services/metaTransformService.js` - `enrichColumnsWithFieldMeta` (L317-L399)

### 配置
- `meta/schemas/version.yaml` - 已加 `editable: false` + `hidden_in_form: true` ✅
