# Phase 3.1: 枚举对象迁移 - 任务拆解

> **开始日期**: 2026-05-11
> **计划周期**: Week 1-2 (约10个工作日)
> **状态**: 📋 规划中

---

## 任务总览

| 阶段 | 任务数 | 预计工时 |
|------|--------|----------|
| Phase 3.1.1: EnumProtectionInterceptor | 5 | 2天 |
| Phase 3.1.2: enum_type.yaml 增强 | 4 | 2天 |
| Phase 3.1.3: enum_value.yaml 增强 | 4 | 1天 |
| Phase 3.1.4: v2 API 路由 | 6 | 2天 |
| Phase 3.1.5: 维度过滤扩展 | 3 | 1天 |
| Phase 3.1.6: 端到端测试 | 4 | 2天 |
| **Phase 3.1.7: 前端适配** | **4** | **2天** |
| **总计** | **30** | **12天** |

---

## Phase 3.1.1: EnumProtectionInterceptor 创建

### 任务 1.1: 创建拦截器文件

**文件**: `meta/core/interceptors/enum_protection_interceptor.py`

**任务描述**:
- 创建 EnumProtectionInterceptor 类
- 实现 priority 属性（返回35）
- 实现 before_action 方法
- 实现 _validate_update 方法
- 实现 _validate_delete 方法
- 实现辅助方法（_is_enum_type_locked, _has_enum_values, _get_parent_enum_type）

**验收标准**:
- [ ] 文件创建成功
- [ ] 类结构正确
- [ ] 方法签名正确

**依赖**: 无

---

### 任务 1.2: 实现系统枚举保护

**任务描述**:
- enum_type.category = 'system' 时阻止 update
- enum_type.category = 'system' 时阻止 delete
- enum_type 删除时检查是否有枚举值

**代码片段**:
```python
def _validate_enum_type_update(self, context: ActionContext) -> None:
    if context.old_data.get('category') == 'system':
        context.result = ActionResult(
            success=False,
            message="系统枚举不可修改",
            error_code="ENUM_IMMUTABLE"
        )

def _validate_enum_type_delete(self, context: ActionContext) -> None:
    if context.old_data.get('category') == 'system':
        context.result = ActionResult(
            success=False,
            message="系统枚举不可删除",
            error_code="ENUM_IMMUTABLE"
        )
    if self._has_enum_values(context):
        context.result = ActionResult(
            success=False,
            message="该枚举类型下有枚举值，无法删除",
            error_code="HAS_VALUES"
        )
```

**验收标准**:
- [ ] 系统枚举修改返回错误
- [ ] 系统枚举删除返回错误
- [ ] 有值的枚举类型删除返回错误

**依赖**: 任务 1.1

---

### 任务 1.3: 实现锁定枚举保护

**任务描述**:
- enum_value 所属 enum_type.mutability = 'locked' 时阻止 update
- enum_value 所属 enum_type.mutability = 'locked' 时阻止 delete

**代码片段**:
```python
def _validate_enum_value_update(self, context: ActionContext) -> None:
    enum_type_id = context.params.get('enum_type_id') or context.old_data.get('enum_type_id')
    if self._is_enum_type_locked(context, enum_type_id):
        context.result = ActionResult(
            success=False,
            message="该枚举类型已锁定，不可修改值",
            error_code="ENUM_LOCKED"
        )

def _validate_enum_value_delete(self, context: ActionContext) -> None:
    enum_type_id = context.old_data.get('enum_type_id')
    if self._is_enum_type_locked(context, enum_type_id):
        context.result = ActionResult(
            success=False,
            message="该枚举类型已锁定，不可删除值",
            error_code="ENUM_LOCKED"
        )
```

**验收标准**:
- [ ] 锁定枚举的值修改返回错误
- [ ] 锁定枚举的值删除返回错误

**依赖**: 任务 1.1

---

### 任务 1.4: 实现系统预置值保护

**任务描述**:
- enum_value.is_system = 1 时阻止 delete

**代码片段**:
```python
def _validate_enum_value_delete(self, context: ActionContext) -> None:
    # 系统预置值保护
    if context.old_data.get('is_system') == 1:
        context.result = ActionResult(
            success=False,
            message="系统预置值不可删除",
            error_code="SYSTEM_VALUE_IMMUTABLE"
        )
        return

    # 锁定枚举保护
    enum_type_id = context.old_data.get('enum_type_id')
    if self._is_enum_type_locked(context, enum_type_id):
        context.result = ActionResult(
            success=False,
            message="该枚举类型已锁定，不可删除值",
            error_code="ENUM_LOCKED"
        )
```

**验收标准**:
- [ ] 系统预置值删除返回错误

**依赖**: 任务 1.1

---

### 任务 1.5: 注册拦截器到 BOFramework

**任务描述**:
- 在 `meta/core/bo_framework.py` 中导入 EnumProtectionInterceptor
- 在 BOFramework.__init__ 中注册拦截器

**代码片段**:
```python
# bo_framework.py
from meta.core.interceptors.enum_protection_interceptor import EnumProtectionInterceptor

class BOFramework:
    def __init__(self, data_source=None):
        # ... 现有代码 ...
        self.register_interceptor(EnumProtectionInterceptor())
```

**验收标准**:
- [ ] 拦截器正确注册
- [ ] 优先级正确（35）

**依赖**: 任务 1.1-1.4

---

## Phase 3.1.2: enum_type.yaml 增强

### 任务 2.1: 添加 aspects 引用

**文件**: `meta/schemas/enum_type.yaml`

**任务描述**:
- 添加 `aspects: [audit_aspect]`

**验收标准**:
- [ ] YAML 语法正确
- [ ] 通过 schema 验证

---

### 任务 2.2: 添加 import_export 配置

**任务描述**:
添加以下配置：
```yaml
import_export:
  import_enabled: true
  export_enabled: true
  cascade_export: false
  cascade_import: false
  conflict_strategy: upsert
  conflict_key: id
```

**验收标准**:
- [ ] 配置添加成功
- [ ] YAML 语法正确

**依赖**: 无

---

### 任务 2.3: 添加 audit 配置

**任务描述**:
添加以下配置：
```yaml
audit:
  enabled: true
  strategy: changed_only
```

**验收标准**:
- [ ] 配置添加成功
- [ ] 审计日志正确记录

**依赖**: 无

---

### 任务 2.4: 添加 validations 约束

**任务描述**:
添加以下校验规则：
```yaml
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
```

**验收标准**:
- [ ] 校验规则添加成功
- [ ] 系统枚举保护生效

**依赖**: 任务 1.2

---

## Phase 3.1.3: enum_value.yaml 增强

### 任务 3.1: 添加 aspects 引用

**文件**: `meta/schemas/enum_value.yaml`

**任务描述**:
- 添加 `aspects: [audit_aspect]`

**验收标准**:
- [ ] YAML 语法正确
- [ ] 通过 schema 验证

---

### 任务 3.2: 添加 import_export 配置

**任务描述**:
添加以下配置：
```yaml
import_export:
  import_enabled: true
  export_enabled: true
  cascade_export: false
  cascade_import: false
  conflict_strategy: upsert
  conflict_key: "enum_type_id,code"
```

**验收标准**:
- [ ] 配置添加成功
- [ ] YAML 语法正确

**依赖**: 无

---

### 任务 3.3: 添加 audit 配置

**任务描述**:
添加以下配置：
```yaml
audit:
  enabled: true
  strategy: changed_only
```

**验收标准**:
- [ ] 配置添加成功
- [ ] 审计日志正确记录

**依赖**: 无

---

### 任务 3.4: 添加 validations 约束

**任务描述**:
添加以下校验规则：
```yaml
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
```

**验收标准**:
- [ ] 校验规则添加成功
- [ ] 锁定枚举保护生效
- [ ] 系统值保护生效

**依赖**: 任务 1.3, 1.4

---

## Phase 3.1.4: v2 API 路由

### 任务 4.1: 创建枚举类型 API 路由

**文件**: `meta/api/bo_api.py`

**任务描述**:
添加以下路由：
- `POST /api/v2/bo/enum_type` - 创建枚举类型
- `GET /api/v2/bo/enum_type` - 查询枚举类型列表
- `GET /api/v2/bo/enum_type/:id` - 获取枚举类型详情
- `PUT /api/v2/bo/enum_type/:id` - 更新枚举类型
- `DELETE /api/v2/bo/enum_type/:id` - 删除枚举类型

**验收标准**:
- [ ] 所有路由正确注册
- [ ] CRUD 操作正常

**依赖**: 任务 2.1-2.4

---

### 任务 4.2: 创建枚举值 API 路由

**文件**: `meta/api/bo_api.py`

**任务描述**:
添加以下路由：
- `GET /api/v2/bo/enum_type/:enum_type_id/values` - 查询枚举值列表
- `POST /api/v2/bo/enum_type/:enum_type_id/values` - 创建枚举值
- `GET /api/v2/bo/enum_value/:id` - 获取枚举值详情
- `PUT /api/v2/bo/enum_value/:id` - 更新枚举值
- `DELETE /api/v2/bo/enum_value/:id` - 删除枚举值

**验收标准**:
- [ ] 所有路由正确注册
- [ ] CRUD 操作正常

**依赖**: 任务 3.1-3.4

---

### 任务 4.3: 实现分页查询支持

**任务描述**:
- 支持 page, page_size 参数
- 支持 keyword 搜索
- 支持 category, mutability 过滤
- 返回 items, total, page, page_size 格式

**验收标准**:
- [ ] 分页参数正确处理
- [ ] 搜索功能正常
- [ ] 过滤功能正常

**依赖**: 任务 4.1

---

### 任务 4.4: 实现 computed 字段

**任务描述**:
- value_count: 枚举值数量
- dimension_count: 维度数量

**验收标准**:
- [ ] 计算字段正确返回
- [ ] 列表显示正常

**依赖**: 任务 4.1

---

### 任务 4.5: 实现变更历史查询

**任务描述**:
- 在 enum_type 详情中添加 change_history
- 通过 AuditInterceptor 自动记录

**验收标准**:
- [ ] 变更历史正确返回
- [ ] 审计日志正确记录

**依赖**: 任务 2.3

---

### 任务 4.6: 添加权限控制

**任务描述**:
- 创建/更新/删除需要管理员权限
- 查询需要登录权限

**验收标准**:
- [ ] 权限控制正确生效
- [ ] 未授权返回 401/403

**依赖**: 任务 4.1, 4.2

---

## Phase 3.1.5: 维度过滤扩展

### 任务 5.1: 扩展 PersistenceInterceptor

**文件**: `meta/core/interceptors/persistence_interceptor.py`

**任务描述**:
- 在 _do_list 方法中添加维度过滤逻辑
- 支持 dimensions JSON 字段过滤

**代码片段**:
```python
def _apply_dimension_filters(self, filters: Dict, dimension_filters: Dict) -> Dict:
    """应用维度过滤条件"""
    for dim_key, dim_value in dimension_filters.items():
        filters[f"json_extract(dimensions, '$.{dim_key}')"] = dim_value
    return filters
```

**验收标准**:
- [ ] 维度过滤正确应用
- [ ] 多维度组合过滤正常

**依赖**: 任务 4.2

---

### 任务 5.2: 添加维度过滤测试

**任务描述**:
- 单维度过滤测试
- 多维度组合过滤测试

**验收标准**:
- [ ] 测试通过
- [ ] 覆盖率 ≥ 80%

**依赖**: 任务 5.1

---

### 任务 5.3: 性能优化

**任务描述**:
- 如果存在性能问题，添加 JSON 索引
- 考虑添加物化视图

**验收标准**:
- [ ] 查询性能可接受
- [ ] 无明显性能问题

**依赖**: 任务 5.1, 5.2

---

## Phase 3.1.6: 端到端测试

### 任务 6.1: 单元测试

**文件**: `meta/tests/test_enum_protection_interceptor.py`

**任务描述**:
- 测试系统枚举保护（修改/删除）
- 测试锁定枚举保护（修改/删除）
- 测试系统预置值保护

**验收标准**:
- [ ] 所有测试通过
- [ ] 覆盖率 ≥ 90%

---

### 任务 6.2: 集成测试

**文件**: `meta/tests/test_enum_api_v2.py`

**任务描述**:
- 枚举类型 CRUD 测试
- 枚举值 CRUD 测试
- 维度过滤测试
- 审计日志测试

**验收标准**:
- [ ] 所有测试通过
- [ ] 功能正确

---

### 任务 6.3: 向后兼容测试

**任务描述**:
- 测试 enum_api.py 重定向
- 验证数据一致性

**验收标准**:
- [ ] 重定向正确
- [ ] 数据一致

---

### 任务 6.4: 文档更新

**任务描述**:
- 更新 API 文档
- 更新架构文档
- 更新 README

**验收标准**:
- [ ] 文档完整
- [ ] 链接有效

---

## 任务依赖关系图

```
Phase 3.1.1: EnumProtectionInterceptor
├── 任务 1.1: 创建拦截器文件
├── 任务 1.2: 系统枚举保护 ──┬──→ 任务 2.4
├── 任务 1.3: 锁定枚举保护 ──┴──→ 任务 3.4
├── 任务 1.4: 系统值保护
└── 任务 1.5: 注册拦截器 ───────────→ Phase 3.1.4

Phase 3.1.2: enum_type.yaml
├── 任务 2.1: aspects 引用
├── 任务 2.2: import_export 配置
├── 任务 2.3: audit 配置 ────────────────→ 任务 4.5
└── 任务 2.4: validations 约束 ──────────→ 任务 4.1

Phase 3.1.3: enum_value.yaml
├── 任务 3.1: aspects 引用
├── 任务 3.2: import_export 配置
├── 任务 3.3: audit 配置
└── 任务 3.4: validations 约束 ─────────→ 任务 4.2

Phase 3.1.4: v2 API 路由
├── 任务 4.1: 枚举类型 API ─────────────→ 任务 6.1
├── 任务 4.2: 枚举值 API ───────────────→ 任务 6.1
├── 任务 4.3: 分页查询 ────────────────→ 任务 6.2
├── 任务 4.4: computed 字段
├── 任务 4.5: 变更历史
└── 任务 4.6: 权限控制 ─────────────────→ 任务 6.2

Phase 3.1.5: 维度过滤扩展
├── 任务 5.1: 扩展 PersistenceInterceptor ─→ 任务 6.2
├── 任务 5.2: 测试
└── 任务 5.3: 性能优化

Phase 3.1.6: 端到端测试
├── 任务 6.1: 单元测试
├── 任务 6.2: 集成测试
├── 任务 6.3: 向后兼容测试
└── 任务 6.4: 文档更新
```

---

## 执行顺序建议

### Week 1

**Day 1-2**:
1. 任务 1.1-1.5: EnumProtectionInterceptor

**Day 3-4**:
2. 任务 2.1-2.4: enum_type.yaml
3. 任务 3.1-3.4: enum_value.yaml

**Day 5**:
4. 任务 4.1: 枚举类型 API
5. 任务 4.2: 枚举值 API

### Week 2

**Day 6-7**:
6. 任务 4.3-4.6: API 完善
7. 任务 5.1: 维度过滤

**Day 8-9**:
8. 任务 5.2-5.3: 测试和优化
9. 任务 6.1: 单元测试

**Day 10**:
10. 任务 6.2-6.4: 集成测试和文档

**Day 11-12**:
11. 任务 7.1-7.4: 前端适配

---

## Phase 3.1.7: 前端适配

### 任务 7.1: 适配 EnumTypeManagement.vue

**文件**: `src/views/SystemManagement/EnumTypeManagement.vue`

**任务描述**:
- 修改 API 路径从 `/api/v1/enum-types` 到 `/api/v2/bo/enum_type`
- 适配返回格式：`data.data` → `data.items`
- 适配分页格式：`data.total` → `data.total`

**修改点**:
```javascript
// 第293行附近
// 修改前
const resp = await fetch(`${API_BASE}/enum-types?${params}`, ...)

// 修改后
const resp = await fetch(`${API_BASE}/v2/bo/enum_type?${params}`, ...)

// 第296行附近
// 修改前
enumTypes.value = data.data?.data || data.data || []
total.value = data.data?.total || data.total || 0

// 修改后
enumTypes.value = data.data?.items || data.data?.data || []
total.value = data.data?.total || data.total || 0
```

**验收标准**:
- [ ] 枚举类型列表正常显示
- [ ] 分页功能正常
- [ ] 筛选功能正常

**依赖**: Phase 3.1.4 完成

---

### 任务 7.2: 适配 EnumValueManagement.vue

**文件**: `src/views/SystemManagement/EnumValueManagement.vue`

**任务描述**:
- 修改 API 路径从 `/api/v1/enum-types/:id/values` 到 `/api/v2/bo/enum_value`
- 枚举值列表通过 `enum_type_id` 参数过滤
- 适配返回格式

**修改点**:
```javascript
// 修改前
const resp = await fetch(`${API_BASE}/enum-types/${enumTypeId}/values?${params}`, ...)

// 修改后
const resp = await fetch(`${API_BASE}/v2/bo/enum_value?enum_type_id=${enumTypeId}&${params}`, ...)
```

**验收标准**:
- [ ] 枚举值列表正常显示
- [ ] 维度过滤功能正常
- [ ] 搜索功能正常

**依赖**: Phase 3.1.5 完成

---

### 任务 7.3: 适配 EnumTypeCreate.vue

**文件**: `src/views/SystemManagement/EnumTypeCreate.vue`

**任务描述**:
- 修改 API 路径从 `/api/v1/enum-types` 到 `/api/v2/bo/enum_type`
- 适配创建成功的回调处理

**修改点**:
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

**验收标准**:
- [ ] 新建枚举类型功能正常
- [ ] 表单验证正常
- [ ] 成功提示正常

**依赖**: Phase 3.1.4 完成

---

### 任务 7.4: 适配 EnumValueFormDialog.vue

**文件**: `src/views/SystemManagement/EnumValueFormDialog.vue`

**任务描述**:
- 修改 API 路径从 `/api/v1/enum-types/:id/values` 到 `/api/v2/bo/enum_value`
- 适配编辑和创建逻辑

**修改点**:
```javascript
// 创建时
const resp = await fetch(`${API_BASE}/v2/bo/enum_value`, {
  method: 'POST',
  body: JSON.stringify({...data, enum_type_id: enumTypeId})
})

// 更新时
const resp = await fetch(`${API_BASE}/v2/bo/enum_value/${valueId}`, {
  method: 'PUT',
  body: JSON.stringify(data)
})

// 删除时
const resp = await fetch(`${API_BASE}/v2/bo/enum_value/${valueId}`, {
  method: 'DELETE'
})
```

**验收标准**:
- [ ] 新建枚举值功能正常
- [ ] 编辑枚举值功能正常
- [ ] 删除枚举值功能正常

**依赖**: Phase 3.1.4 完成

---

### 任务依赖关系图（更新）

```
Phase 3.1.1: EnumProtectionInterceptor ✅
├── 任务 1.1-1.5: 创建拦截器 ✅
└── Phase 3.1.4

Phase 3.1.4: v2 API 路由 ✅
├── 任务 4.1-4.6: API路由
└── Phase 3.1.6, 3.1.7

Phase 3.1.6: 端到端测试
├── 任务 6.1: 单元测试
├── 任务 6.2: 集成测试
├── 任务 6.3: 向后兼容测试
└── 任务 6.4: 文档更新

Phase 3.1.7: 前端适配
├── 任务 7.1: EnumTypeManagement.vue ←── 依赖 3.1.4
├── 任务 7.2: EnumValueManagement.vue ←── 依赖 3.1.5
├── 任务 7.3: EnumTypeCreate.vue ←── 依赖 3.1.4
└── 任务 7.4: EnumValueFormDialog.vue ←── 依赖 3.1.4
```

---

## 执行顺序建议（更新）

### Week 1

**Day 1-2**:
1. 任务 1.1-1.5: EnumProtectionInterceptor ✅

**Day 3-4**:
2. 任务 2.1-2.4: enum_type.yaml
3. 任务 3.1-3.4: enum_value.yaml

**Day 5**:
4. 任务 4.1-4.2: v2 API 路由

### Week 2

**Day 6-7**:
5. 任务 4.3-4.6: API 完善
6. 任务 5.1: 维度过滤

**Day 8-9**:
7. 任务 5.2-5.3: 测试和优化
8. 任务 6.1: 单元测试

**Day 10**:
9. 任务 6.2-6.4: 集成测试和文档

**Day 11-12**:
10. 任务 7.1-7.4: 前端适配

---

**文档版本**: v1.1
**最后更新**: 2026-05-11
