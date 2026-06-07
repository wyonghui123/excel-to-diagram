# 元模型外键解析改进 Spec

## Why

当前系统的元模型设计在父对象关联方面存在不足，导致：
1. **导入时需要用户提供父对象的技术ID而非业务编码** - 用户需要知道 `sub_domain_id=123` 而非 `sub_domain_code="PROCUREMENT"`
2. **验证失败时错误提示不够友好** - 用户无法快速定位问题
3. **跨环境数据迁移需要重新映射ID** - 不同环境ID不一致

这是核心功能改进，影响整个系统的数据导入导出流程。

## What Changes

### Schema 层改进
- 为所有父键字段添加 `resolve_from_field` 和 `resolve_to_object` 语义
- 新增父对象业务键虚拟字段（如 `sub_domain_code`、`service_module_code` 等）
- 配置导入导出可见性

### 服务层改进
- `action_executor.py` 新增外键解析方法 `_resolve_foreign_keys`
- 创建/更新时自动从业务键解析到技术ID
- 提供友好的错误提示

### 导入导出改进
- 增强导入验证的错误提示
- 支持检测父对象是否在当前导入批次中
- 提供解决建议（hint）

### UI 层改进
- 支持通过业务键快速选择父对象
- 新增业务键解析 API 接口

### 自动化测试
- 单元测试覆盖外键解析功能
- 集成测试覆盖导入导出场景
- E2E 测试覆盖完整流程

## Impact

### 受影响的文件

| 文件 | 变更类型 | 变更内容 |
|------|----------|----------|
| `meta/schemas/domain.yaml` | 修改 | 添加 version_code 虚拟字段，version_id 添加 resolve_from_field |
| `meta/schemas/sub_domain.yaml` | 修改 | 添加 domain_code 虚拟字段，domain_id 添加 resolve_from_field |
| `meta/schemas/service_module.yaml` | 修改 | 添加 sub_domain_code 虚拟字段，sub_domain_id 添加 resolve_from_field |
| `meta/schemas/business_object.yaml` | 修改 | 添加 service_module_code 虚拟字段，service_module_id 添加 resolve_from_field |
| `meta/core/action_executor.py` | 修改 | 新增 _resolve_foreign_keys 方法 |
| `meta/services/import_export_service.py` | 修改 | 增强错误提示，支持批次检测 |
| `meta/api/manage_api.py` | 修改 | 新增业务键解析 API |
| `meta/tests/test_foreign_key_resolution.py` | 新增 | 单元测试 |
| `meta/tests/test_import_with_parent_resolution.py` | 新增 | 集成测试 |

### 不受影响的部分

| 部分 | 原因 |
|------|------|
| 数据库结构 | 新增字段为虚拟字段，不存储 |
| 现有数据 | 外键ID已存在，通过解析可获取业务键 |
| 前端 UI | 可选改进，不影响现有功能 |

## ADDED Requirements

### Requirement: FR-001 父对象业务键虚拟字段

系统 SHALL 为所有层级对象提供父对象业务键虚拟字段，用于导入导出和快速输入。

#### Scenario: 服务模块导入使用子领域编码

- **WHEN** 用户导入服务模块数据，Excel 中包含 `sub_domain_code` 列
- **THEN** 系统自动根据 `sub_domain_code` 解析 `sub_domain_id`
- **AND** 如果解析成功，创建/更新操作正常执行
- **AND** 如果解析失败，返回友好的错误提示

#### Scenario: 业务对象创建使用服务模块编码

- **WHEN** 用户通过 API 创建业务对象，传入 `service_module_code` 而非 `service_module_id`
- **THEN** 系统自动解析 `service_module_id`
- **AND** 创建操作正常执行

### Requirement: FR-002 外键自动解析

系统 SHALL 在 CRUD 操作中自动解析外键，从业务键到技术ID。

#### Scenario: 创建时自动解析父对象

- **WHEN** 用户创建子领域，传入 `domain_code="FINANCE"` 而非 `domain_id`
- **THEN** 系统自动查找 `domain.code="FINANCE"` 的记录
- **AND** 将 `domain_id` 设置为该记录的 ID
- **AND** 如果找不到，返回错误提示 "父对象 领域 的业务键 'FINANCE' 不存在"

#### Scenario: 更新时允许切换父对象

- **WHEN** 用户更新服务模块，传入新的 `sub_domain_code`
- **THEN** 系统自动解析新的 `sub_domain_id`
- **AND** 更新操作正常执行

### Requirement: FR-003 导入验证增强

系统 SHALL 在导入验证时提供友好的错误提示。

#### Scenario: 父对象不存在

- **WHEN** 导入数据中引用了不存在的父对象业务键
- **THEN** 错误提示包含具体的父对象名称和业务键
- **AND** 错误提示包含解决建议（hint）

#### Scenario: 父对象在当前批次中

- **WHEN** 导入数据中引用的父对象在当前导入批次中但尚未导入
- **THEN** 错误提示建议调整 Sheet 顺序

### Requirement: FR-004 UI 业务键快速输入

系统 SHALL 在表单中支持通过业务键快速选择父对象。

#### Scenario: 输入业务键自动解析

- **WHEN** 用户在表单中输入父对象业务键
- **THEN** 系统自动解析并填充技术ID
- **AND** 如果解析失败，显示友好错误提示

### Requirement: FR-005 自动化测试覆盖

系统 SHALL 提供完整的自动化测试覆盖。

#### Scenario: 单元测试通过

- **WHEN** 运行 `python meta/tests/run_all_tests.py`
- **THEN** 所有测试通过
- **AND** 外键解析相关测试覆盖核心场景

## MODIFIED Requirements

### Requirement: SemanticAnnotation 扩展

`SemanticAnnotation` 类已包含 `resolve_from_field` 和 `resolve_to_object` 字段，需要确保正确解析和使用。

**当前定义**:
```python
resolve_from_field: str = ""      # 从哪个字段解析本字段的值（字段ID）
resolve_to_object: str = ""       # 解析到哪个对象类型（对象ID）
```

**使用说明**:
- `resolve_from_field`: 指定业务键字段ID（如 `sub_domain_code`）
- `resolve_to_object`: 指定目标对象类型（如 `sub_domain`）

## REMOVED Requirements

无移除的需求。

## 技术设计

### 1. Schema 层改进

#### 1.1 service_module.yaml 修改示例

```yaml
fields:
  # 新增：父对象业务键虚拟字段
  - id: sub_domain_code
    name: 子领域编码
    type: string
    storage: virtual
    description: 所属子领域编码（用于导入导出和快速输入）
    semantics:
      meaning: 子领域的业务键，用于导入导出
      business_key: false
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
      resolve_from_field: sub_domain_code
      resolve_to_object: sub_domain
```

### 2. 服务层改进

#### 2.1 action_executor.py 新增方法

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
    for field in meta_object.fields:
        resolve_from = getattr(field.semantics, 'resolve_from_field', None)
        resolve_to = getattr(field.semantics, 'resolve_to_object', None)
        
        if resolve_from and resolve_to:
            current_value = data.get(field.id)
            source_value = data.get(resolve_from)
            
            if (current_value is None or current_value == '') and source_value:
                parent_record = self._find_by_key(
                    resolve_to, 'code', source_value, data.get('version_id')
                )
                
                if parent_record:
                    data[field.id] = parent_record.get('id')
                else:
                    ref_obj = registry.get(resolve_to)
                    obj_name = ref_obj.name if ref_obj else resolve_to
                    version_info = f"(版本ID: {data.get('version_id')})" if data.get('version_id') else ""
                    raise ValueError(
                        f"父对象 {obj_name} 的业务键 '{source_value}' 不存在 {version_info}。"
                        f"请先创建 {obj_name} 或检查业务键是否正确。"
                    )
    
    return data
```

### 3. 导入导出改进

#### 3.1 错误提示增强

```python
def _validate_parent_reference(self, obj: MetaObject, field, parent_code: str, 
                               version_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """验证父对象引用，提供友好的错误提示"""
    resolve_to = getattr(field.semantics, 'resolve_to_object', None)
    if not resolve_to:
        return None
    
    parent_obj = registry.get(resolve_to)
    if not parent_obj:
        return None
    
    ref_record = self._find_by_key(resolve_to, 'code', parent_code, version_id)
    
    if not ref_record:
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
```

### 4. 测试设计

#### 4.1 单元测试

```python
class TestForeignKeyResolution:
    """测试外键解析功能"""
    
    def test_resolve_parent_by_business_key(self):
        """测试通过业务键解析父对象"""
        # 创建父对象
        # 创建子对象，使用父对象业务键
        # 验证创建成功，domain_id 已自动解析
    
    def test_resolve_parent_not_found(self):
        """测试父对象不存在时的错误处理"""
        # 创建子对象，使用不存在的业务键
        # 验证返回友好的错误信息
    
    def test_resolve_with_version_isolation(self):
        """测试版本隔离下的外键解析"""
        # 在不同版本创建相同业务键的父对象
        # 验证解析时版本隔离正确
```

## 风险与缓解措施

| 风险 | 影响 | 可能性 | 缓解措施 |
|------|------|--------|----------|
| Schema 变更导致现有数据不兼容 | 高 | 中 | 使用 virtual 字段，不影响数据库结构 |
| 外键解析性能问题 | 中 | 中 | 添加缓存机制，批量解析时优化查询 |
| UI 改动引入回归问题 | 中 | 低 | 充分测试，保持向后兼容 |
| 导入顺序依赖导致失败 | 中 | 高 | 改进错误提示，支持延迟绑定（未来） |

## 实施步骤

### Phase 1: Schema 层改进
1. 修改 domain.yaml 添加 version_code 字段
2. 修改 sub_domain.yaml 添加 domain_code 字段
3. 修改 service_module.yaml 添加 sub_domain_code 字段
4. 修改 business_object.yaml 添加 service_module_code 字段
5. 为父键字段添加 resolve_from_field 和 resolve_to_object

### Phase 2: 服务层改进
1. 在 action_executor.py 添加 _resolve_foreign_keys 方法
2. 在 _do_create 方法中调用外键解析
3. 在 _do_update 方法中调用外键解析
4. 添加友好的错误提示

### Phase 3: 导入导出改进
1. 增强 _validate_parent_reference 方法
2. 添加 _check_in_importing_batch 方法
3. 改进错误提示格式

### Phase 4: 自动化测试
1. 创建 test_foreign_key_resolution.py 单元测试
2. 创建 test_import_with_parent_resolution.py 集成测试
3. 更新 run_all_tests.py 添加新测试模块
4. 确保所有测试通过

## 验收标准

### 功能验收
- [ ] 所有层级对象 YAML 包含父对象业务键虚拟字段
- [ ] 父键字段包含 resolve_from_field 和 resolve_to_object 语义
- [ ] 创建时自动解析外键
- [ ] 更新时允许切换父对象
- [ ] 导入验证提供友好的错误提示
- [ ] 错误提示包含解决建议（hint）

### 测试验收
- [ ] 单元测试覆盖外键解析功能
- [ ] 集成测试覆盖导入导出场景
- [ ] 所有测试通过
