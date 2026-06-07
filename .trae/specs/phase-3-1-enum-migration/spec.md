# Phase 3.1: 枚举对象迁移到 BO Framework v2 API

> **开始日期**: 2026-05-11
> **计划周期**: Week 1-2 (约10个工作日)
> **状态**: 📋 规划中

---

## 一、背景与目标

### 1.1 项目背景

当前枚举对象使用独立的 `enum_api.py`（约860行代码）实现，与BO Framework的v2 API模式不一致。Phase 3.1的目标是将枚举对象（enum_type和enum_value）迁移到统一的BO Framework，实现：

- 统一的API模式（v2 API）
- 元数据驱动的配置（YAML）
- 拦截器化的业务逻辑
- 审计日志自动记录

### 1.2 现状分析

#### 数据库表结构

**enum_types 表**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(200) | 主键，业务编码 |
| name | VARCHAR(200) | 显示名称 |
| category | VARCHAR(200) | 分类：system/business |
| mutability | VARCHAR(200) | 可维护性：locked/extensible/fully_editable |
| dimension_schema | TEXT | 维度定义JSON |
| description | TEXT | 描述 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

**enum_values 表**：
| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| enum_type_id | VARCHAR(200) | 所属枚举类型ID |
| code | VARCHAR(200) | 枚举值编码 |
| name | VARCHAR(200) | 显示名称 |
| name_en | VARCHAR(200) | 英文名称 |
| dimensions | TEXT | 维度值JSON |
| sort_order | INTEGER | 排序 |
| is_active | INTEGER | 是否启用 |
| is_system | INTEGER | 是否系统预置 |
| parent_code | VARCHAR(200) | 父级编码 |
| metadata | TEXT | 扩展元数据 |

#### 数据统计

| 指标 | 数量 |
|------|------|
| 枚举类型总数 | 29 |
| 枚举值总数 | 121 |
| 系统枚举类型 | 16 |
| 系统枚举值 | 112 |
| 业务枚举类型 | 13 |
| 业务枚举值 | 9 |

#### enum_api.py 特殊业务逻辑

| 功能 | 当前实现 | BO Framework支持 | 迁移策略 |
|------|---------|----------------|---------|
| 系统枚举不可修改/删除 | 硬编码检查 | ⚠️ 需新增拦截器 | 创建EnumProtectionInterceptor |
| 锁定枚举不可操作 | 硬编码检查 | ⚠️ 需新增拦截器 | 创建EnumProtectionInterceptor |
| 系统预置值不可删除 | 硬编码检查 | ⚠️ 需新增拦截器 | 创建EnumProtectionInterceptor |
| 维度过滤查询 | 自定义SQL | ⚠️ 需扩展拦截器 | 创建DimensionFilterInterceptor |
| 枚举值计数 | 应用层计算 | ✅ 已支持 | 迁移computed到YAML |
| 维度数量计算 | 应用层计算 | ✅ 已支持 | 迁移computed到YAML |
| 变更历史查询 | 独立API | ✅ 已支持 | 通过audit_aspect |
| 审计日志 | 独立实现 | ✅ 已支持 | 通过AuditInterceptor |

---

## 二、架构设计

### 2.1 目标架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        API 层 (bo_api.py)                        │
├─────────────────────────────────────────────────────────────────┤
│  POST   /api/v2/bo/enum_type         - 创建枚举类型              │
│  GET    /api/v2/bo/enum_type         - 查询枚举类型列表           │
│  GET    /api/v2/bo/enum_type/:id     - 获取枚举类型详情          │
│  PUT    /api/v2/bo/enum_type/:id      - 更新枚举类型              │
│  DELETE /api/v2/bo/enum_type/:id      - 删除枚举类型              │
│  GET    /api/v2/bo/enum_type/:id/values - 查询枚举值列表          │
│  POST   /api/v2/bo/enum_type/:id/values - 创建枚举值              │
│  GET    /api/v2/bo/enum_value/:id    - 获取枚举值详情            │
│  PUT    /api/v2/bo/enum_value/:id    - 更新枚举值                │
│  DELETE /api/v2/bo/enum_value/:id    - 删除枚举值                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     拦截器链 (Interceptor Chain)                   │
├─────────────────────────────────────────────────────────────────┤
│  Priority 10:  ContextInterceptor    - 上下文初始化              │
│  Priority 20:  LockInterceptor      - 分布式锁                   │
│  Priority 30:  DataPermissionInterceptor - 数据权限过滤            │
│  Priority 35:  EnumProtectionInterceptor - 枚举保护（新增）       │
│  Priority 45:  HierarchyValidationInterceptor - 层级校验          │
│  Priority 50:  QueryInterceptor    - 查询增强                    │
│  Priority 60:  CascadeInterceptor   - 级联操作                   │
│  Priority 80:  [保留]             - 枚举维度过滤（新增）         │
│  Priority 90:  AuditInterceptor    - 审计日志                   │
│  Priority 95:  PersistenceInterceptor - 持久化                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      BO Framework Core                          │
├─────────────────────────────────────────────────────────────────┤
│  ConstraintEngine - 约束引擎（支持unique/immutable/no_delete）    │
│  AssociationEngine - 关联引擎（支持m2m/reference/composition）   │
│  DeepInsertEngine - 深度插入引擎                                  │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      YAML 元数据配置                              │
├─────────────────────────────────────────────────────────────────┤
│  enum_type.yaml  - 枚举类型元模型                                 │
│  enum_value.yaml - 枚举值元模型                                  │
│  aspects.yaml    - Aspect定义（audit_aspect）                   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 新增组件

#### EnumProtectionInterceptor

```python
# 优先级: 35
# 功能:
# 1. 系统枚举不可修改/删除（category = 'system'）
# 2. 锁定枚举不可添加/修改/删除值（mutability = 'locked'）
# 3. 系统预置值不可删除（is_system = 1）
```

#### DimensionFilterInterceptor（扩展QueryInterceptor）

```python
# 功能:
# 1. 支持维度字段过滤
# 2. 自动解析 dimensions JSON 字段
# 3. 支持多维度组合过滤
```

---

## 三、详细设计

### 3.1 enum_type.yaml 增强

**文件位置**: `meta/schemas/enum_type.yaml`

**新增配置**：

```yaml
# ────────────────────────────────────────────
# Aspect 引用
# ────────────────────────────────────────────
aspects: [audit_aspect]

# ────────────────────────────────────────────
# 导入导出配置
# ────────────────────────────────────────────
import_export:
  import_enabled: true
  export_enabled: true
  cascade_export: false              # 枚举类型是叶子节点
  cascade_import: false
  conflict_strategy: upsert
  conflict_key: id

# ────────────────────────────────────────────
# 审计配置
# ────────────────────────────────────────────
audit:
  enabled: true
  strategy: changed_only             # 只记录变化的字段

# ────────────────────────────────────────────
# 校验规则
# ────────────────────────────────────────────
validations:
  - id: system_immutable
    name: 系统枚举不可修改
    type: immutable_condition
    condition: "category == 'system'"
    message: 系统枚举不可修改
    severity: error
    applies_to: [update, delete]

  - id: system_no_delete
    name: 系统枚举不可删除
    type: no_delete_condition
    condition: "category == 'system'"
    message: 系统枚举不可删除
    severity: error
    applies_to: [delete]

# ────────────────────────────────────────────
# 计算字段
# ────────────────────────────────────────────
computed_fields:
  - id: value_count
    name: 值数量
    type: count_children
    target: enum_value
    filter: enum_type_id
    storage: virtual

  - id: dimension_count
    name: 维度数
    type: json_array_length
    field: dimension_schema
    storage: virtual
```

### 3.2 enum_value.yaml 增强

**文件位置**: `meta/schemas/enum_value.yaml`

**新增配置**：

```yaml
# ────────────────────────────────────────────
# Aspect 引用
# ────────────────────────────────────────────
aspects: [audit_aspect]

# ────────────────────────────────────────────
# 导入导出配置
# ────────────────────────────────────────────
import_export:
  import_enabled: true
  export_enabled: true
  cascade_export: false
  cascade_import: false
  conflict_strategy: upsert
  conflict_key: "enum_type_id,code"

# ────────────────────────────────────────────
# 审计配置
# ────────────────────────────────────────────
audit:
  enabled: true
  strategy: changed_only

# ────────────────────────────────────────────
# 校验规则
# ────────────────────────────────────────────
validations:
  - id: locked_enum_no_modify
    name: 锁定枚举不可修改值
    type: immutable_condition
    condition: |
      parent_type = get_parent_enum_type(enum_type_id)
      parent_type.mutability == 'locked'
    message: 该枚举类型已锁定，不可修改值
    severity: error
    applies_to: [update]

  - id: locked_enum_no_delete
    name: 锁定枚举不可删除值
    type: no_delete_condition
    condition: |
      parent_type = get_parent_enum_type(enum_type_id)
      parent_type.mutability == 'locked'
    message: 该枚举类型已锁定，不可删除值
    severity: error
    applies_to: [delete]

  - id: system_value_no_delete
    name: 系统预置值不可删除
    type: no_delete_condition
    condition: "is_system == 1"
    message: 系统预置值不可删除
    severity: error
    applies_to: [delete]

# ────────────────────────────────────────────
# 维度过滤配置
# ────────────────────────────────────────────
dimensions:
  enabled: true
  storage_field: dimensions
  type: json
  filter_mode: json_extract
```

### 3.3 新增拦截器设计

#### EnumProtectionInterceptor

```python
# meta/core/interceptors/enum_protection_interceptor.py

class EnumProtectionInterceptor(Interceptor):
    """
    枚举保护拦截器

    优先级: 35

    功能:
    1. 系统枚举不可修改/删除
    2. 锁定枚举不可添加/修改/删除值
    3. 系统预置值不可删除
    """

    @property
    def priority(self) -> int:
        return 35

    def before_action(self, context: ActionContext) -> None:
        if context.object_type not in ('enum_type', 'enum_value'):
            return

        if context.is_update_action:
            self._validate_update(context)
        elif context.is_delete_action:
            self._validate_delete(context)

    def _validate_update(self, context: ActionContext) -> None:
        if context.object_type == 'enum_type':
            # 检查是否为系统枚举
            if context.old_data.get('category') == 'system':
                context.result = ActionResult(
                    success=False,
                    message="系统枚举不可修改"
                )

        elif context.object_type == 'enum_value':
            # 检查父枚举是否为锁定状态
            enum_type_id = context.params.get('enum_type_id') or context.old_data.get('enum_type_id')
            if self._is_enum_type_locked(context, enum_type_id):
                context.result = ActionResult(
                    success=False,
                    message="该枚举类型已锁定，不可修改值"
                )

    def _validate_delete(self, context: ActionContext) -> None:
        if context.object_type == 'enum_type':
            if context.old_data.get('category') == 'system':
                context.result = ActionResult(
                    success=False,
                    message="系统枚举不可删除"
                )

            # 检查是否有枚举值
            if self._has_enum_values(context):
                context.result = ActionResult(
                    success=False,
                    message="该枚举类型下有枚举值，无法删除"
                )

        elif context.object_type == 'enum_value':
            # 检查是否为系统预置值
            if context.old_data.get('is_system') == 1:
                context.result = ActionResult(
                    success=False,
                    message="系统预置值不可删除"
                )

            # 检查父枚举是否为锁定状态
            enum_type_id = context.old_data.get('enum_type_id')
            if self._is_enum_type_locked(context, enum_type_id):
                context.result = ActionResult(
                    success=False,
                    message="该枚举类型已锁定，不可删除值"
                )
```

#### DimensionFilterInterceptor（扩展PersistenceInterceptor）

```python
# 在 PersistenceInterceptor._do_list 中扩展维度过滤

def _do_list(self, context: ActionContext, registry: ActionRegistry) -> ActionResult:
    # ... 现有逻辑 ...

    # 维度过滤支持
    if context.object_type == 'enum_value':
        dimension_filters = self._extract_dimension_filters(context.params)
        if dimension_filters:
            filters = self._apply_dimension_filters(filters, dimension_filters)

    # ... 继续现有逻辑 ...

def _extract_dimension_filters(self, params: Dict) -> Dict:
    """提取维度过滤参数"""
    reserved = {'page', 'pageSize', 'keyword', 'is_active', 'search'}
    return {k: v for k, v in params.items() if k not in reserved}

def _apply_dimension_filters(self, filters: Dict, dimension_filters: Dict) -> Dict:
    """应用维度过滤条件"""
    for dim_key, dim_value in dimension_filters.items():
        filters[f"dimensions__json_extract__{dim_key}"] = dim_value
    return filters
```

---

## 四、前端适配设计

### 4.1 现有前端组件

| 页面 | 文件 | 说明 | 优先级 |
|------|------|------|--------|
| 枚举类型管理 | EnumTypeManagement.vue | 列表、筛选、变更历史 | 🔴 高 |
| 枚举值管理 | EnumValueManagement.vue | 列表、筛选、变更历史 | 🔴 高 |
| 枚举类型创建 | EnumTypeCreate.vue | 新建表单 | 🔴 高 |
| 枚举值表单 | EnumValueFormDialog.vue | 新建/编辑表单 | 🔴 高 |

### 4.2 API 调用差异

| 差异点 | v1 API | v2 API |
|--------|--------|--------|
| **路径** | `/api/v1/enum-types` | `/api/v2/bo/enum_type` |
| **返回格式** | `{success, data, total}` | `{success, data: {items, total, page, page_size}}` |

### 4.3 需要修改的文件

#### EnumTypeManagement.vue
```javascript
// 修改前 (第293行)
const resp = await fetch(`${API_BASE}/enum-types?${params}`, ...)

// 修改后
const resp = await fetch(`${API_BASE}/v2/bo/enum_type?${params}`, ...)
```

**适配点**：
1. API路径从 `/api/v1/enum-types` 改为 `/api/v2/bo/enum_type`
2. 返回格式适配：`data.data` → `data.items`
3. 字段映射：`dimension_count` 使用 computed 字段

#### EnumValueManagement.vue
```javascript
// 修改前
const resp = await fetch(`${API_BASE}/enum-types/${enumTypeId}/values`, ...)

// 修改后
const resp = await fetch(`${API_BASE}/v2/bo/enum_value?enum_type_id=${enumTypeId}`, ...)
```

**适配点**：
1. API路径从 `/api/v1/enum-types/:id/values` 改为 `/api/v2/bo/enum_value`
2. 枚举值列表通过 `enum_type_id` 参数过滤
3. 维度过滤通过 URL 参数传递

#### EnumTypeCreate.vue
```javascript
// 修改前
const resp = await fetch(`${API_BASE}/enum-types`, {
  method: 'POST',
  body: JSON.stringify(data)
})

// 修改后
const resp = await fetch(`${API_BASE}/v2/bo/enum_type`, {
  method: 'POST',
  body: JSON.stringify(data)
})
```

#### EnumValueFormDialog.vue
```javascript
// 修改前
const resp = await fetch(`${API_BASE}/enum-types/${enumTypeId}/values`, {
  method: 'POST',
  body: JSON.stringify(data)
})

// 修改后
const resp = await fetch(`${API_BASE}/v2/bo/enum_value`, {
  method: 'POST',
  body: JSON.stringify({...data, enum_type_id: enumTypeId})
})
```

### 4.4 前端组件复用

| 组件 | 状态 | 可复用度 |
|------|------|---------|
| MetaTable | ✅ 完整 | ⭐⭐⭐⭐⭐ |
| MetaForm | ✅ 完整 | ⭐⭐⭐⭐⭐ |
| useMetaList | ✅ 完整 | ⭐⭐⭐⭐⭐ |
| EnumSelect | ⚠️ 需增强 | ⭐⭐⭐⭐ |
| enumService | ✅ 完整 | ⭐⭐⭐⭐⭐ |

### 4.5 错误处理

```javascript
// v2 API 错误响应格式
{
  "success": false,
  "message": "系统枚举不可修改",
  "errors": ["SYSTEM_ENUM_IMMUTABLE"]
}

// 前端错误处理
try {
  const resp = await fetch(apiUrl, options)
  const result = await resp.json()
  
  if (!result.success) {
    // 统一错误提示
    ElMessage.error(result.message)
    
    // 根据 error_code 做特殊处理
    if (result.errors?.includes('SYSTEM_ENUM_IMMUTABLE')) {
      // 系统枚举保护提示
    }
  }
} catch (error) {
  ElMessage.error('网络错误')
}
```

---

## 五、API 设计

### 5.1 v2 API 端点

#### 枚举类型 API

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| POST | `/api/v2/bo/enum_type` | 创建枚举类型 | `{id, name, category, mutability, dimension_schema, description}` |
| GET | `/api/v2/bo/enum_type` | 查询枚举类型列表 | `?page=1&page_size=20&keyword=&category=&mutability=` |
| GET | `/api/v2/bo/enum_type/:id` | 获取枚举类型详情 | - |
| PUT | `/api/v2/bo/enum_type/:id` | 更新枚举类型 | `{name, mutability, dimension_schema, description}` |
| DELETE | `/api/v2/bo/enum_type/:id` | 删除枚举类型 | - |

#### 枚举值 API

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|------------|
| GET | `/api/v2/bo/enum_type/:enum_type_id/values` | 查询枚举值列表 | `?page=1&page_size=50&keyword=&is_active=&dimension_key=value` |
| POST | `/api/v2/bo/enum_type/:enum_type_id/values` | 创建枚举值 | `{code, name, name_en, dimensions, sort_order, is_active}` |
| GET | `/api/v2/bo/enum_value/:id` | 获取枚举值详情 | - |
| PUT | `/api/v2/bo/enum_value/:id` | 更新枚举值 | `{name, name_en, dimensions, sort_order, is_active}` |
| DELETE | `/api/v2/bo/enum_value/:id` | 删除枚举值 | - |

### 4.2 API 响应格式

```json
// 成功响应
{
  "success": true,
  "data": { ... },
  "message": "操作成功"
}

// 错误响应
{
  "success": false,
  "message": "系统枚举不可修改",
  "error_code": "ENUM_IMMUTABLE"
}

// 列表响应
{
  "success": true,
  "data": {
    "items": [...],
    "total": 29,
    "page": 1,
    "page_size": 20
  }
}
```

---

## 五、测试策略

### 5.1 单元测试

| 测试对象 | 测试用例数 | 覆盖范围 |
|---------|-----------|---------|
| EnumProtectionInterceptor | 10 | 系统枚举保护、锁定枚举保护、系统值保护 |
| DimensionFilterInterceptor | 5 | 维度过滤、多维度组合 |
| enum_type.yaml | 5 | 字段定义、校验规则 |
| enum_value.yaml | 5 | 字段定义、校验规则 |

### 5.2 集成测试

| 测试场景 | 测试用例数 | 说明 |
|---------|-----------|------|
| 枚举类型 CRUD | 8 | 创建、读取、更新、删除 |
| 枚举值 CRUD | 10 | 创建、读取、更新、删除 |
| 系统枚举保护 | 4 | 修改/删除系统枚举应返回错误 |
| 锁定枚举保护 | 4 | 修改/删除锁定枚举值应返回错误 |
| 系统值保护 | 2 | 删除系统预置值应返回错误 |
| 维度过滤 | 3 | 单维度、多维度组合 |
| 审计日志 | 5 | CREATE/UPDATE/DELETE 操作审计 |

### 5.3 测试用例示例

```python
# test_enum_protection_interceptor.py

class TestEnumProtectionInterceptor:
    def test_system_enum_cannot_update(self):
        """系统枚举不可修改"""
        context = create_context('enum_type', 'update', {
            'category': 'system'
        })
        interceptor.before_action(context)
        assert context.result.success == False
        assert '系统枚举不可修改' in context.result.message

    def test_system_enum_cannot_delete(self):
        """系统枚举不可删除"""
        context = create_context('enum_type', 'delete', {
            'category': 'system'
        })
        interceptor.before_action(context)
        assert context.result.success == False
        assert '系统枚举不可删除' in context.result.message

    def test_locked_enum_values_cannot_modify(self):
        """锁定枚举的值不可修改"""
        context = create_context('enum_value', 'update', {
            'enum_type_id': 'locked_type',
            'code': 'VALUE1'
        })
        when(enum_type_repo).get('locked_type').then_return({
            'mutability': 'locked'
        })
        interceptor.before_action(context)
        assert context.result.success == False
        assert '已锁定' in context.result.message

    def test_system_value_cannot_delete(self):
        """系统预置值不可删除"""
        context = create_context('enum_value', 'delete', {
            'is_system': 1
        })
        interceptor.before_action(context)
        assert context.result.success == False
        assert '系统预置值不可删除' in context.result.message
```

---

## 六、迁移计划

### 6.1 阶段划分

| 阶段 | 时间 | 任务 |
|------|------|------|
| Phase 3.1.1 | Day 1-2 | 创建 EnumProtectionInterceptor |
| Phase 3.1.2 | Day 3-4 | 增强 enum_type.yaml |
| Phase 3.1.3 | Day 5 | 增强 enum_value.yaml |
| Phase 3.1.4 | Day 6-7 | 创建 v2 API 路由 |
| Phase 3.1.5 | Day 8 | 扩展维度过滤支持 |
| Phase 3.1.6 | Day 9-10 | 端到端测试 |

### 6.2 向后兼容

迁移期间保留 enum_api.py 作为兼容层：

```python
# meta/api/enum_api.py

# 添加迁移提示
@enum_bp.route('/enum-types', methods=['GET'])
def list_enum_types():
    return jsonify({
        'success': False,
        'message': '枚举API已迁移到v2，请使用 /api/v2/bo/enum_type',
        'redirect': '/api/v2/bo/enum_type'
    }), 301
```

---

## 七、风险与缓解

### 7.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 维度过滤性能 | 中 | 中 | 添加 JSON 索引优化 |
| YAML 配置冲突 | 低 | 低 | 保留原 enum_api.py，灰度切换 |
| 审计日志丢失 | 高 | 低 | 保留原审计写入，双写验证 |

### 7.2 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 前端适配工作量 | 中 | 中 | 复用现有枚举组件 |
| 系统枚举误修改 | 高 | 低 | 充分测试 + 权限控制 |

---

## 八、验收标准

### 8.1 功能指标

- [ ] EnumProtectionInterceptor 实现完整
- [ ] enum_type 100% 功能覆盖
- [ ] enum_value 100% 功能覆盖
- [ ] 维度过滤功能正常
- [ ] 审计日志正确记录

### 8.2 代码质量

- [ ] 新增代码 < 300行
- [ ] 测试覆盖率 ≥ 90%
- [ ] YAML 配置通过 schema 验证
- [ ] 无新增技术债务

### 8.3 迁移指标

- [ ] enum_api.py 代码行数减少 ≥ 500行
- [ ] 向后兼容100%保持
- [ ] API 响应格式一致

---

## 九、后续工作

Phase 3.1 完成后，预期进入：

- **Phase 3.2**: 层级对象迁移（version/domain/sub_domain/service_module/business_object）
- **Phase 3.3**: 关系对象分析
- **Phase 3.4**: manage_api 瘦身

---

**文档版本**: v1.0
**最后更新**: 2026-05-11
**负责人**: AI Assistant
