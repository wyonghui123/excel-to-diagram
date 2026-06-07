# P0-2 元模型设计改进 Backlog

> **关联分析**: [SAP Business Key/Parent Key 数据模型分析报告](../analysis/P0-2-SAP-DataModel-Analysis.md)
> 
> **创建日期**: 2026-04-29
> **优先级**: P0 (高)
> **状态**: 待开发

---

## 一、问题概述

### 1.1 核心问题

当前系统的元模型设计在父对象关联方面存在不足，导致：
- 导入时需要用户提供父对象的**技术ID**而非**业务编码**
- 验证失败时错误提示不够友好
- 跨环境数据迁移需要重新映射ID

### 1.2 根因分析

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            根因分析图                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  问题表现                                                                    │
│  ├── 导入失败：VALIDATION_FAILED - 关联的子领域不能为空                       │
│  ├── 用户困惑：需要知道 sub_domain_id=123 而非 sub_domain_code="PROCUREMENT" │
│  └── 迁移困难：不同环境ID不一致，需要重新映射                                 │
│                                                                              │
│  根因                                                                        │
│  ├── Schema 层：父键字段缺少 resolve_from_field 和 resolve_to_object 语义   │
│  ├── Schema 层：缺少父对象业务键虚拟字段（如 sub_domain_code）               │
│  ├── 服务层：导入时未自动从业务键解析到技术ID                                 │
│  └── 服务层：验证错误提示不够详细                                           │
│                                                                              │
│  参考 SAP 设计                                                               │
│  ├── @ObjectModel.foreignKey.association 注解                               │
│  ├── 业务键优先原则（Business Key First）                                    │
│  └── 声明式外键解析                                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 二、Backlog 总览

| 编号 | 任务名称 | 优先级 | 状态 | 预估工时 |
|------|----------|--------|------|----------|
| [P0-2.1](#p0-21-schema-层改进) | Schema 层改进 | P0 | 待开发 | 4h |
| [P0-2.2](#p0-22-服务层改进) | 服务层改进 | P0 | 待开发 | 6h |
| [P0-2.3](#p0-23-导入导出改进) | 导入导出改进 | P0 | 待开发 | 4h |
| [P0-2.4](#p0-24-ui-层改进) | UI 层改进 | P1 | 待开发 | 6h |
| [P0-2.5](#p0-25-测试与验证) | 测试与验证 | P1 | 待开发 | 4h |

---

## 三、详细任务分解

### P0-2.1 Schema 层改进

**目标**: 为所有父键字段添加外键解析语义和父对象业务键虚拟字段

#### 3.1.1 修改 service_module.yaml

**文件**: `meta/schemas/service_module.yaml`

**修改内容**:

```yaml
# 新增：父对象业务键虚拟字段
- id: sub_domain_code
  name: 子领域编码
  type: string
  storage: virtual
  description: 所属子领域编码（用于导入导出和快速输入）
  semantics:
    meaning: 子领域的业务键，用于导入导出
    business_key: true
    import_visible: true
    export_visible: true
    import_order: 3
    data_category: code
    virtual: true
  ui:
    visible: true
    editable: true
    widget: input
    fieldGroup: 层级归属
    fieldGroupPosition: 35
    i18n_key: service_module.field.sub_domain_code

# 修改：sub_domain_id 字段添加外键解析语义
- id: sub_domain_id
  name: 子领域
  type: integer
  db_column: sub_domain_id
  required: true
  description: 所属子领域（编辑时可切换）
  ui:
    widget: select
    relation: sub_domain
    display_field: sub_domain_name
    depends_on: domain_id
    cascade_group: hierarchy
    cascade_level: 3
  semantics:
    meaning: 关联的子领域（父对象）
    parent_key: true
    mandatory: true
    # 新增：外键解析语义
    resolve_from_field: sub_domain_code   # 从业务键解析
    resolve_to_object: sub_domain          # 解析目标对象
    # 注意：根据 SAP One Model 设计，parent_key 仅表示层级关系，不强制只读
    # 编辑时可切换到其他子领域
```

**验收标准**:
- [ ] 新增 sub_domain_code 虚拟字段
- [ ] sub_domain_id 添加 resolve_from_field 和 resolve_to_object
- [ ] 表单配置中 sub_domain_code 位于"层级归属"分组

---

#### 3.1.2 修改 business_object.yaml

**文件**: `meta/schemas/business_object.yaml`

**修改内容**:

```yaml
# 新增：父对象业务键虚拟字段
- id: service_module_code
  name: 服务模块编码
  type: string
  storage: virtual
  description: 所属服务模块编码（用于导入导出和快速输入）
  semantics:
    meaning: 服务模块的业务键，用于导入导出
    business_key: true
    import_visible: true
    export_visible: true
    import_order: 3
    data_category: code
    virtual: true
  ui:
    visible: true
    editable: true
    widget: input
    fieldGroup: 层级归属
    fieldGroupPosition: 45
    i18n_key: bo.field.service_module_code

# 修改：service_module_id 字段添加外键解析语义
- id: service_module_id
  name: 服务模块
  type: integer
  db_column: service_module_id
  required: true
  ui:
    widget: select
    relation: service_module
    display_field: service_module_name
    depends_on: sub_domain_id
    cascade_group: hierarchy
    cascade_level: 4
  semantics:
    meaning: 关联的服务模块（父对象）
    parent_key: true
    mandatory: true
    # 新增：外键解析语义
    resolve_from_field: service_module_code
    resolve_to_object: service_module
```

**验收标准**:
- [ ] 新增 service_module_code 虚拟字段
- [ ] service_module_id 添加 resolve_from_field 和 resolve_to_object

---

#### 3.1.3 修改 sub_domain.yaml

**文件**: `meta/schemas/sub_domain.yaml`

**修改内容**:

```yaml
# 新增：父对象业务键虚拟字段
- id: domain_code
  name: 领域编码
  type: string
  storage: virtual
  description: 所属领域编码（用于导入导出和快速输入）
  semantics:
    meaning: 领域的业务键，用于导入导出
    business_key: true
    import_visible: true
    export_visible: true
    import_order: 3
    data_category: code
    virtual: true
  ui:
    visible: true
    editable: true
    widget: input
    fieldGroup: 层级归属
    fieldGroupPosition: 25
    i18n_key: sub_domain.field.domain_code

# 修改：domain_id 字段添加外键解析语义
- id: domain_id
  name: 领域
  type: integer
  db_column: domain_id
  description: 所属领域
  ui:
    widget: select
    relation: domain
    display_field: domain_name
    depends_on: version_id
    cascade_group: hierarchy
    cascade_level: 2
  semantics:
    meaning: 关联的领域
    parent_key: true
    immutable: true
    # 新增：外键解析语义
    resolve_from_field: domain_code
    resolve_to_object: domain
```

**验收标准**:
- [ ] 新增 domain_code 虚拟字段
- [ ] domain_id 添加 resolve_from_field 和 resolve_to_object

---

#### 3.1.4 修改 domain.yaml

**文件**: `meta/schemas/domain.yaml`

**修改内容**:

```yaml
# 新增：父对象业务键虚拟字段
- id: version_code
  name: 版本编码
  type: string
  storage: virtual
  description: 所属版本编码（用于导入导出和快速输入）
  semantics:
    meaning: 版本的业务键，用于导入导出
    business_key: true
    import_visible: true
    export_visible: true
    import_order: 3
    data_category: code
    virtual: true
  ui:
    visible: true
    editable: true
    widget: input
    fieldGroup: 层级归属
    fieldGroupPosition: 15
    i18n_key: domain.field.version_code

# 修改：version_id 字段添加外键解析语义（如果适用）
- id: version_id
  name: 版本
  type: integer
  db_column: version_id
  required: true
  ui:
    widget: select
    relation: version
    display_field: version_name
    cascade_group: hierarchy
    cascade_level: 1
  semantics:
    meaning: 关联的产品版本
    parent_key: true
    readonly_always: true
    context_field: true
    # 新增：外键解析语义（可选，因为 version_id 通常是上下文字段）
    resolve_from_field: version_code
    resolve_to_object: version
```

**验收标准**:
- [ ] 新增 version_code 虚拟字段
- [ ] version_id 添加 resolve_from_field 和 resolve_to_object（可选）

---

### P0-2.2 服务层改进

**目标**: 在 CRUD 操作中自动解析外键，从业务键到技术ID

#### 3.2.1 修改 action_executor.py

**文件**: `meta/core/action_executor.py`

**新增方法**:

```python
def _resolve_foreign_keys(self, meta_object: MetaObject, data: Dict[str, Any]) -> Dict[str, Any]:
    """解析外键：从业务键自动解析到技术ID
    
    参考 SAP @ObjectModel.foreignKey.association 注解
    
    Args:
        meta_object: 元模型对象
        data: 数据字典
        
    Returns:
        解析后的数据字典
        
    Raises:
        ValueError: 如果父对象不存在
    """
    import logging
    logger = logging.getLogger(__name__)
    
    for field in meta_object.fields:
        resolve_from = getattr(field.semantics, 'resolve_from_field', None)
        resolve_to = getattr(field.semantics, 'resolve_to_object', None)
        
        if resolve_from and resolve_to:
            # 如果技术ID未提供，但业务键有值，则自动解析
            current_value = data.get(field.id)
            source_value = data.get(resolve_from)
            
            if (current_value is None or current_value == '') and source_value:
                logger.info(f"[FK Resolve] {meta_object.id}.{field.id}: "
                           f"从 {resolve_from}='{source_value}' 解析到 {resolve_to}")
                
                # 查找父对象
                parent_record = self._find_by_key(
                    resolve_to, 
                    'code', 
                    source_value, 
                    data.get('version_id')
                )
                
                if parent_record:
                    data[field.id] = parent_record.get('id')
                    logger.info(f"[FK Resolve] 成功: {field.id}={parent_record.get('id')}")
                else:
                    # 提供详细的错误信息
                    ref_obj = registry.get(resolve_to)
                    obj_name = ref_obj.name if ref_obj else resolve_to
                    version_info = f"(版本ID: {data.get('version_id')})" if data.get('version_id') else ""
                    raise ValueError(
                        f"父对象 {obj_name} 的业务键 '{source_value}' 不存在 {version_info}。"
                        f"请先创建 {obj_name} 或检查业务键是否正确。"
                    )
    
    return data


def _find_by_key(self, object_type: str, key_field: str, key_value: Any,
                 version_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """根据关键字段查找记录
    
    Args:
        object_type: 对象类型
        key_field: 关键字段名
        key_value: 关键字段值
        version_id: 版本ID，如果指定则只在该版本内查找
        
    Returns:
        记录字典或 None
    """
    from meta.services.query_service import QueryService, SearchRequest, QueryCondition
    
    try:
        conditions = [QueryCondition(field=key_field, operator="eq", value=key_value)]
        
        # 如果指定了版本ID，添加版本条件
        if version_id is not None:
            conditions.append(QueryCondition(field="version_id", operator="eq", value=version_id))
        
        search_request = SearchRequest(
            object_type=object_type,
            conditions=conditions,
            page=1,
            page_size=1,
        )
        
        query_service = QueryService(self.ds)
        result = query_service.search(search_request)
        return result.data[0] if result.data else None
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"_find_by_key failed: {e}")
        return None
```

**修改 _do_create 方法**:

```python
def _do_create(self, meta_object: MetaObject, params: Dict[str, Any],
               skip_rules: bool = False) -> ActionResult:
    """执行创建操作"""
    fields = meta_object.get_persistent_fields()
    data = self._prepare_data(fields, params, for_create=True)
    
    if data is None:
        return ActionResult.fail(
            error="INVALID_DATA",
            message="Failed to prepare data for create"
        )
    
    # 🔑 新增：自动解析外键
    try:
        data = self._resolve_foreign_keys(meta_object, data)
    except ValueError as e:
        return ActionResult.fail(
            error="FOREIGN_KEY_RESOLUTION_FAILED",
            message=str(e)
        )
    
    # 原有验证逻辑...
    if not skip_rules:
        validation_result = self._validate_before_create(meta_object, data)
        if validation_result:
            return validation_result
        
        # ... 后续逻辑
```

**修改 _do_update 方法**:

```python
def _do_update(self, meta_object: MetaObject, params: Dict[str, Any],
               skip_rules: bool = False) -> ActionResult:
    """执行更新操作"""
    # ... 原有逻辑
    
    data = self._prepare_data(fields, params, for_create=False)
    
    # 🔑 新增：自动解析外键（允许通过业务键修改父对象）
    try:
        data = self._resolve_foreign_keys(meta_object, data)
    except ValueError as e:
        return ActionResult.fail(
            error="FOREIGN_KEY_RESOLUTION_FAILED",
            message=str(e)
        )
    
    # ... 后续逻辑
```

**验收标准**:
- [ ] 新增 `_resolve_foreign_keys` 方法
- [ ] 新增 `_find_by_key` 辅助方法
- [ ] `_do_create` 调用外键解析
- [ ] `_do_update` 调用外键解析
- [ ] 外键解析失败时返回友好的错误信息

---

### P0-2.3 导入导出改进

**目标**: 增强导入验证的错误提示，支持更友好的父对象引用验证

#### 3.3.1 修改 import_export_service.py

**文件**: `meta/services/import_export_service.py`

**新增验证方法**:

```python
def _validate_parent_reference(self, obj: MetaObject, field, parent_code: str, 
                               version_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """验证父对象引用，提供友好的错误提示
    
    Args:
        obj: 当前对象
        field: 父键字段
        parent_code: 父对象业务键
        version_id: 版本ID
        
    Returns:
        如果验证失败返回错误信息字典，否则返回 None
    """
    import logging
    logger = logging.getLogger(__name__)
    
    resolve_to = getattr(field.semantics, 'resolve_to_object', None)
    if not resolve_to:
        return None
    
    parent_obj = registry.get(resolve_to)
    if not parent_obj:
        return None
    
    # 查找父对象
    ref_record = self._find_by_key(resolve_to, 'code', parent_code, version_id)
    
    if not ref_record:
        # 检查是否在当前导入批次中
        in_current_batch = self._check_in_importing_batch(resolve_to, parent_code)
        
        version_info = f"(版本ID: {version_id})" if version_id else ""
        
        if in_current_batch:
            return {
                "error": "PARENT_IN_LATER_BATCH",
                "message": f"父对象 {parent_obj.name} 的业务键 '{parent_code}' 在当前导入批次中，"
                          f"请确保导入顺序正确（先父对象后子对象）{version_info}",
                "hint": f"建议：调整 Excel 中的 Sheet 顺序，确保 {parent_obj.name} 在前"
            }
        else:
            return {
                "error": "PARENT_NOT_FOUND",
                "message": f"父对象 {parent_obj.name} 的业务键 '{parent_code}' 不存在 {version_info}",
                "hint": f"请先导入 {parent_obj.name} 数据，或检查业务键 '{parent_code}' 是否正确"
            }
    
    return None


def _check_in_importing_batch(self, object_type: str, business_key: str) -> bool:
    """检查对象是否在当前导入批次中
    
    Args:
        object_type: 对象类型
        business_key: 业务键值
        
    Returns:
        如果在当前批次中返回 True
    """
    # 这个方法需要在 _validate_sheets 中维护导入批次索引
    # 具体实现略
    return False
```

**修改 _validate_sheets 方法**:

在父对象引用验证部分增强错误提示：

```python
# 在 _validate_sheets 方法的引用完整性检查部分
for field in obj.fields:
    resolve_to = getattr(field.semantics, 'resolve_to_object', None)
    resolve_from = getattr(field.semantics, 'resolve_from_field', None)
    
    if resolve_to and resolve_from:
        source_value = record.get(resolve_from)
        if source_value and str(source_value).strip():
            # 🔑 使用新的验证方法
            validation_error = self._validate_parent_reference(
                obj, field, str(source_value).strip(), version_id
            )
            
            if validation_error:
                errors.append({
                    "sheet": sheet["name"],
                    "row": row_num,
                    "field": field.name or field.id,
                    "error": validation_error["message"],
                    "hint": validation_error.get("hint", "")
                })
                invalid_count += 1
```

**验收标准**:
- [ ] 新增 `_validate_parent_reference` 方法
- [ ] 导入验证错误提示包含具体的父对象名称和业务键
- [ ] 错误提示包含解决建议（hint）
- [ ] 支持检测父对象是否在当前导入批次中

---

### P0-2.4 UI 层改进

**目标**: 在表单中支持父对象业务键快速输入

#### 3.4.1 修改 DynamicForm.vue

**文件**: `src/views/ArchDataManageApp/components/DynamicForm.vue`

**新增功能**: 支持通过业务键快速选择父对象

```vue
<template>
  <!-- 在表单字段渲染部分添加业务键快速输入 -->
  <template v-if="hasBusinessKeyInput(fieldId)">
    <div class="business-key-input-group">
      <input 
        v-model="businessKeyInputs[fieldId]"
        :placeholder="`请输入${getFieldLabel(fieldId)}编码快速查找`"
        @blur="handleBusinessKeyBlur(fieldId)"
        @keyup.enter="handleBusinessKeySearch(fieldId)"
      />
      <button @click="handleBusinessKeySearch(fieldId)">查找</button>
    </div>
    <div v-if="businessKeyErrors[fieldId]" class="business-key-error">
      {{ businessKeyErrors[fieldId] }}
    </div>
  </template>
</template>

<script setup>
// 新增响应式数据
const businessKeyInputs = ref({})
const businessKeyErrors = ref({})

// 判断字段是否支持业务键快速输入
function hasBusinessKeyInput(fieldId) {
  const field = getField(fieldId)
  if (!field) return false
  
  // 有 resolve_from_field 语义的字段支持业务键输入
  return field.semantics?.resolve_from_field && 
         field.semantics?.resolve_to_object &&
         isFieldEditable(fieldId)
}

// 业务键失去焦点时自动解析
async function handleBusinessKeyBlur(fieldId) {
  const businessKey = businessKeyInputs.value[fieldId]
  if (!businessKey) return
  
  await resolveBusinessKey(fieldId, businessKey)
}

// 业务键搜索
async function handleBusinessKeySearch(fieldId) {
  const businessKey = businessKeyInputs.value[fieldId]
  if (!businessKey) {
    businessKeyErrors.value[fieldId] = '请输入业务键'
    return
  }
  
  await resolveBusinessKey(fieldId, businessKey)
}

// 解析业务键到技术ID
async function resolveBusinessKey(fieldId, businessKey) {
  const field = getField(fieldId)
  if (!field) return
  
  const resolveTo = field.semantics?.resolve_to_object
  const resolveFrom = field.semantics?.resolve_from_field
  
  if (!resolveTo || !resolveFrom) return
  
  try {
    // 调用 API 解析业务键
    const result = await api.resolveBusinessKey(resolveTo, 'code', businessKey, formData.value.version_id)
    
    if (result.success && result.data) {
      // 解析成功，设置技术ID
      formData.value[fieldId] = result.data.id
      businessKeyErrors.value[fieldId] = null
      
      // 触发级联加载
      const cascadeField = cascadeFields.value.find(cf => cf.id === fieldId)
      if (cascadeField) {
        loadCascadeOptions(fieldId, cascadeField.relation, getApiParamName(fieldId), result.data.id)
      }
    } else {
      businessKeyErrors.value[fieldId] = `未找到业务键为 "${businessKey}" 的记录`
    }
  } catch (e) {
    businessKeyErrors.value[fieldId] = `解析失败: ${e.message}`
  }
}
</script>

<style scoped>
.business-key-input-group {
  display: flex;
  gap: 8px;
}

.business-key-input-group input {
  flex: 1;
}

.business-key-input-group button {
  padding: 4px 12px;
  background: #1890ff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.business-key-error {
  color: #ff4d4f;
  font-size: 12px;
  margin-top: 4px;
}
</style>
```

#### 3.4.2 新增 API 接口

**文件**: `meta/api/manage_api.py`

**新增接口**:

```python
@manage_bp.route('/api/v1/<object_type>/resolve', methods=['GET'])
def resolve_business_key(object_type):
    """解析业务键到技术ID
    
    Query Parameters:
        key_field: 关键字段名（默认 code）
        key_value: 关键字段值
        version_id: 版本ID（可选）
        
    Returns:
        {
            "success": true,
            "data": { "id": 123, "name": "...", "code": "..." }
        }
    """
    key_field = request.args.get('key_field', 'code')
    key_value = request.args.get('key_value')
    version_id = request.args.get('version_id', type=int)
    
    if not key_value:
        return jsonify({"success": False, "error": "key_value is required"}), 400
    
    try:
        from meta.services.query_service import QueryService, SearchRequest, QueryCondition
        
        conditions = [QueryCondition(field=key_field, operator="eq", value=key_value)]
        
        if version_id is not None:
            conditions.append(QueryCondition(field="version_id", operator="eq", value=version_id))
        
        search_request = SearchRequest(
            object_type=object_type,
            conditions=conditions,
            page=1,
            page_size=1,
        )
        
        query_service = QueryService(_data_source)
        result = query_service.search(search_request)
        
        if result.data:
            return jsonify({"success": True, "data": result.data[0]})
        else:
            return jsonify({"success": False, "error": "Record not found"}), 404
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

**验收标准**:
- [ ] UI 支持业务键快速输入框
- [ ] 输入业务键后自动解析到技术ID
- [ ] 解析失败时显示友好错误提示
- [ ] 新增 `/api/v1/<object_type>/resolve` 接口

---

### P0-2.5 测试与验证

**目标**: 确保改进后的功能正常工作

#### 3.5.1 单元测试

**文件**: `meta/tests/test_foreign_key_resolution.py`

```python
import pytest
from meta.services.manage_service import ManageService, CreateRequest
from meta.core.datasource import get_data_source


class TestForeignKeyResolution:
    """测试外键解析功能"""
    
    def test_resolve_parent_by_business_key(self):
        """测试通过业务键解析父对象"""
        # 1. 创建父对象
        parent_data = {
            "code": "TEST_DOMAIN",
            "name": "测试领域",
            "version_id": 1
        }
        
        # 2. 创建子对象，使用父对象业务键
        child_data = {
            "code": "TEST_SUB",
            "name": "测试子领域",
            "domain_code": "TEST_DOMAIN",  # 使用业务键而非ID
            "version_id": 1
        }
        
        # 3. 验证创建成功
        # 4. 验证 domain_id 已自动解析
    
    def test_resolve_parent_not_found(self):
        """测试父对象不存在时的错误处理"""
        child_data = {
            "code": "TEST_SUB",
            "name": "测试子领域",
            "domain_code": "NON_EXISTENT",  # 不存在的业务键
            "version_id": 1
        }
        
        # 验证返回友好的错误信息
    
    def test_resolve_with_version_isolation(self):
        """测试版本隔离下的外键解析"""
        # 在不同版本创建相同业务键的父对象
        # 验证解析时版本隔离正确
```

#### 3.5.2 集成测试

**文件**: `meta/tests/test_import_with_parent_resolution.py`

```python
class TestImportWithParentResolution:
    """测试导入时的父对象解析"""
    
    def test_import_service_module_with_sub_domain_code(self):
        """测试导入服务模块时使用子领域编码"""
        # Excel 数据包含 sub_domain_code 而非 sub_domain_id
        # 验证导入成功
    
    def test_import_validation_error_message(self):
        """测试导入验证错误提示"""
        # 导入数据中包含不存在的父对象业务键
        # 验证错误提示包含具体的父对象名称和业务键
```

**验收标准**:
- [ ] 单元测试覆盖外键解析功能
- [ ] 集成测试覆盖导入导出场景
- [ ] 所有测试通过

---

## 四、依赖关系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            任务依赖关系图                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  P0-2.1 Schema 层改进                                                        │
│       │                                                                      │
│       ├───► P0-2.2 服务层改进                                                │
│       │           │                                                          │
│       │           ├───► P0-2.3 导入导出改进                                   │
│       │           │           │                                              │
│       │           │           └───► P0-2.5 测试与验证                         │
│       │           │                                                          │
│       │           └───► P0-2.4 UI 层改进                                     │
│       │                       │                                              │
│       │                       └───► P0-2.5 测试与验证                         │
│       │                                                                      │
│       └───► P0-2.5 测试与验证（Schema 验证）                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 五、风险与缓解措施

| 风险 | 影响 | 可能性 | 缓解措施 |
|------|------|--------|----------|
| Schema 变更导致现有数据不兼容 | 高 | 中 | 使用 virtual 字段，不影响数据库结构 |
| 外键解析性能问题 | 中 | 中 | 添加缓存机制，批量解析时优化查询 |
| UI 改动引入回归问题 | 中 | 低 | 充分测试，保持向后兼容 |
| 导入顺序依赖导致失败 | 中 | 高 | 改进错误提示，支持延迟绑定（未来） |

---

## 六、参考文档

- [SAP CDS View 官方文档](https://cap.cloud.sap/docs/cds/)
- [SAP One Model 设计指南](https://help.sap.com/docs/)
- [当前系统元模型设计文档](../meta/schemas/README.md)

---

## 七、变更记录

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|----------|------|
| 2026-04-29 | 1.0 | 初始版本 | AI助手 |
