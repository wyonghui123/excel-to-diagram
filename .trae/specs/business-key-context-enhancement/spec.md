# Spec: Business Key 上下文增强

## 1. 背景与目标

### 1.1 背景

当前架构数据管理系统的 business_key 设计存在以下问题：
- 各对象的 business_key 仅包含 `code` 字段，不包含 product_code 和 version_code
- 不同产品/版本中相同 code 的对象无法唯一标识
- 导入时仅按 code 查重，可能覆盖其他版本的数据
- 导出文件缺少 product_code/version_code，无法跨环境迁移数据

### 1.2 业务目标

- 确保数据在产品+版本上下文中的唯一性
- 支持跨环境数据迁移（开发→测试→生产）
- 用户界面和 Excel 模板保持不变（无感知）
- 符合 SAP One Model 的 business_key 设计原则

### 1.3 设计原则

1. **用户无感知**：product_code 和 version_code 作为隐藏的业务键，用户界面和 Excel 模板不变
2. **元数据驱动**：business_key 定义由元模型驱动
3. **向后兼容**：现有数据和功能不受影响
4. **SAP One Model 参考**：参考 SAP CDS View 的 business_key 设计

## 2. 需求类型概览

| 类型 | 适用 | 证据（来源） |
|------|------|--------------|
| 业务 | 是 | 数据唯一性保证、跨环境迁移 |
| 用户/涉众 | 是 | 架构师、数据管理员使用场景 |
| 解决方案 | 是 | 元数据驱动的 business_key 增强 |
| 功能 | 是 | 导入导出自动处理上下文 |
| 非功能 | 是 | 数据一致性、性能 |
| 外部接口 | 是 | API接口、Excel文件格式 |

## 3. 功能需求

### FR-001: Business Key 元数据定义

- **描述**: 所有架构对象的 business_key 必须包含 product_code 和 version_code
- **验收标准**:
  - Product: business_key = code
  - Version: business_key = product_code + code
  - Domain/SubDomain/ServiceModule/BusinessObject: business_key = product_code + version_code + code
  - Relationship: business_key = product_code + version_code + source_code + target_code + relation_code
- **优先级**: Must
- **来源**: SAP One Model 设计原则

### FR-002: 导出自动注入上下文

- **描述**: 导出时自动注入 product_code 和 version_code（隐藏列或元数据 Sheet）
- **验收标准**:
  - 导出 Excel 包含 product_code 和 version_code 信息
  - 用户在数据 Sheet 中不可见 product_code 和 version_code 列
  - 元数据 Sheet 记录 product_code、version_code、导出时间等信息
- **优先级**: Must
- **来源**: 用户无感知原则

### FR-003: 导入自动解析上下文

- **描述**: 导入时自动根据 product_code 和 version_code 匹配 version_id
- **验收标准**:
  - 从元数据 Sheet 读取 product_code 和 version_code
  - 根据 product_code + version_code 解析 version_id
  - 自动注入 version_id 到每条记录
- **优先级**: Must
- **来源**: 用户无感知原则

### FR-004: 导入唯一性校验增强

- **描述**: 导入时按完整 business_key（含 product_code + version_code）查重
- **验收标准**:
  - 查重时考虑 product_code + version_code + code 组合
  - 不同版本的同 code 对象视为不同记录
  - 冲突时正确执行 upsert 操作
- **优先级**: Must
- **来源**: 数据唯一性保证

### FR-005: Excel 模板不变

- **描述**: 导入模板保持不变，用户无需填写 product_code 和 version_code
- **验收标准**:
  - 模板下载接口返回的 Excel 不包含 product_code 和 version_code 列
  - 用户按原有方式填写数据
  - 导入时自动从上下文获取 product_code 和 version_code
- **优先级**: Must
- **来源**: 用户无感知原则

### FR-006: UI 界面不变

- **描述**: 前端界面保持不变，用户无需感知 product_code 和 version_code
- **验收标准**:
  - 列表页面不显示 product_code 和 version_code 列
  - 创建/编辑表单不包含 product_code 和 version_code 字段
  - 用户按原有方式操作
- **优先级**: Must
- **来源**: 用户无感知原则

## 4. 非功能需求

### NFR-001: 数据一致性

- **描述**: business_key 唯一性必须得到保证
- **度量**: 
  - 同一 product + version 下不允许重复 code
  - 导入时正确识别冲突记录
- **优先级**: Must

### NFR-002: 性能

- **描述**: business_key 查询性能不应显著下降
- **度量**: 
  - 按 business_key 查询响应时间 < 100ms
  - 导入时唯一性校验不显著增加导入时间
- **优先级**: Should

## 5. 技术设计

### 5.1 元数据模型扩展

#### 5.1.1 字段定义（以 domain.yaml 为例）

```yaml
fields:
  - id: product_code
    name: 产品编码
    type: string
    description: 所属产品编码
    semantics:
      meaning: 产品编码，用于跨环境数据迁移
      business_key: true
      import_order: 0
      virtual: true           # 虚拟字段，不存储在数据库
      export_visible: false   # 导出不可见（隐藏列）
      import_visible: false   # 导入不可见
    ui:
      visible: false          # UI 不可见
      
  - id: version_code
    name: 版本编码
    type: string
    description: 所属版本编码
    semantics:
      meaning: 版本编码，用于跨环境数据迁移
      business_key: true
      import_order: 1
      virtual: true
      export_visible: false
      import_visible: false
    ui:
      visible: false
      
  - id: code
    name: 编码
    type: string
    db_column: code
    required: true
    description: 领域编码
    semantics:
      meaning: 领域的唯一标识编码
      business_key: true
      import_order: 2
      display_name: true
    ui:
      title: 编码
      width: 15
```

#### 5.1.2 SemanticAnnotation 扩展

```python
@dataclass
class SemanticAnnotation:
    """语义标注"""
    meaning: str = ""
    business_key: bool = False
    display_name: bool = False
    # ... other fields ...
    import_order: int = 100           # 导出列顺序
    virtual: bool = False             # 虚拟字段，不存储在数据库（借鉴 SAP CDS View）
```

### 5.2 导出服务变更

#### 5.2.1 元数据 Sheet 设计

```
Sheet 名称: 元数据
| 字段 | 值 |
|------|-----|
| product_code | ERP |
| product_name | ERP系统 |
| version_code | v1.0 |
| version_name | 1.0版本 |
| version_id | 2 |
| export_time | 2026-04-23 19:30:00 |
| export_user | admin |
```

#### 5.2.2 导出流程

```python
def export_selected_types(self, object_types, filters, options):
    # 1. 获取 product_code 和 version_code
    product_code, version_code = self._get_product_version_codes(filters)
    
    # 2. 创建元数据 Sheet
    ws_meta = wb.create_sheet(title="元数据")
    ws_meta['A1'] = 'product_code'
    ws_meta['B1'] = product_code
    ws_meta['A2'] = 'version_code'
    ws_meta['B2'] = version_code
    # ...
    
    # 3. 导出各对象类型数据
    for object_type in object_types:
        data = self._query_with_hierarchy(object_type, filters, options)
        # 数据中自动包含 product_code, version_code（隐藏列）
```

#### 5.2.3 _get_product_version_codes 方法实现

```python
def _get_product_version_codes(self, filters: Optional[Dict[str, Any]]) -> tuple:
    """根据 filters 中的 version_id 获取 product_code 和 version_code
    
    Args:
        filters: 包含 version_id 的过滤条件
        
    Returns:
        tuple: (product_code, version_code)
    """
    if not filters:
        return ('', '')
    
    version_id = filters.get('version_id')
    if not version_id:
        return ('', '')
    
    try:
        query = """
            SELECT p.code as product_code, v.code as version_code
            FROM versions v
            LEFT JOIN products p ON v.product_id = p.id
            WHERE v.id = ?
            LIMIT 1
        """
        cursor = self.data_source.execute(query, (version_id,))
        row = cursor.fetchone()
        if row:
            return (row[0] or '', row[1] or '')
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to get product/version codes: {e}")
    
    return ('', '')
```

### 5.3 导入服务变更

#### 5.3.1 导入流程

```python
def import_cascade(self, file_path, mode, conflict_strategy, context):
    # 1. 从元数据 Sheet 读取 product_code, version_code
    meta = self._read_meta_sheet(file_path)
    product_code = meta.get('product_code') or context.get('product_code')
    version_code = meta.get('version_code') or context.get('version_code')
    
    # 2. 解析 version_id
    version_id = self._resolve_version_id(product_code, version_code)
    
    # 3. 注入到 context
    context['version_id'] = version_id
    context['product_code'] = product_code
    context['version_code'] = version_code
    
    # 4. 按完整 business_key 查重
    # ...
```

#### 5.3.2 _read_meta_sheet 方法实现

```python
def _read_meta_sheet(self, file_path: str) -> Dict[str, Any]:
    """读取元数据 Sheet
    
    Args:
        file_path: Excel 文件路径
        
    Returns:
        Dict: 包含 product_code, version_code 等元数据
    """
    meta = {}
    try:
        from openpyxl import load_workbook
        wb = load_workbook(file_path, read_only=True, data_only=True)
        
        if '元数据' in wb.sheetnames:
            ws = wb['元数据']
            for row in ws.iter_rows(min_row=1, max_row=20, max_col=2):
                if row[0].value and row[1].value:
                    meta[str(row[0].value)] = row[1].value
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to read meta sheet: {e}")
    
    return meta
```

#### 5.3.3 _resolve_version_id 方法实现

```python
def _resolve_version_id(self, product_code: str, version_code: str) -> Optional[int]:
    """根据 product_code 和 version_code 解析 version_id
    
    Args:
        product_code: 产品编码
        version_code: 版本编码
        
    Returns:
        version_id 或 None
    """
    if not product_code or not version_code:
        return None
    
    try:
        query = """
            SELECT v.id
            FROM versions v
            LEFT JOIN products p ON v.product_id = p.id
            WHERE p.code = ? AND v.code = ?
            LIMIT 1
        """
        cursor = self.data_source.execute(query, (product_code, version_code))
        row = cursor.fetchone()
        if row:
            return row[0]
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to resolve version_id: {e}")
    
    return None
```

#### 5.3.4 唯一性校验

```python
def _find_by_business_key(self, object_type, record, context):
    """根据完整 business_key 查找记录"""
    obj = registry.get(object_type)
    bk_fields = [f for f in obj.fields if f.semantics.business_key]
    
    conditions = ["version_id = ?"]
    params = [context.get('version_id')]
    
    for f in bk_fields:
        if f.id in ['product_code', 'version_code']:
            continue  # 虚拟字段，用 version_id 代替
        if f.id in record and record[f.id]:
            conditions.append(f"{f.id} = ?")
            params.append(record[f.id])
    
    query = f"SELECT * FROM {table} WHERE {' AND '.join(conditions)}"
    # ...
```

## 6. 影响分析

### 6.1 受影响的文件

| 文件 | 变更类型 | 变更内容 |
|------|----------|----------|
| `meta/schemas/domain.yaml` | 修改 | 添加 product_code, version_code 字段 |
| `meta/schemas/sub_domain.yaml` | 修改 | 添加 product_code, version_code 字段 |
| `meta/schemas/service_module.yaml` | 修改 | 添加 product_code, version_code 字段 |
| `meta/schemas/business_object.yaml` | 修改 | 添加 product_code, version_code 字段 |
| `meta/schemas/relationship.yaml` | 修改 | 添加 product_code, version_code 字段 |
| `meta/schemas/version.yaml` | 修改 | 添加 product_code 字段 |
| `meta/core/models.py` | 修改 | SemanticAnnotation 添加 virtual 字段 |
| `meta/core/yaml_loader.py` | 修改 | parse_semantics 解析 virtual 字段 |
| `meta/services/import_export_service.py` | 修改 | 导出注入上下文，导入解析上下文 |
| `meta/services/manage_service.py` | 修改 | 创建时校验 business_key 唯一性 |

### 6.2 不受影响的部分

| 部分 | 原因 |
|------|------|
| 前端 UI | product_code, version_code 设为 ui.visible: false |
| Excel 模板 | 设为 export_visible: false, import_visible: false |
| 数据库结构 | product_code, version_code 为虚拟字段，不存储 |
| 现有数据 | version_id 已存在，通过 JOIN 可获取 product_code, version_code |

## 7. 实施步骤

### Phase 1: 元数据模型变更 ✅ 已完成

1. ✅ 修改 `version.yaml` 添加 product_code 字段
2. ✅ 修改各架构对象 YAML 添加 product_code, version_code 字段
3. ✅ 设置 `business_key: true`, `virtual: true`, `export_visible: false`
4. ✅ 修改 `models.py` 添加 `virtual` 字段到 SemanticAnnotation
5. ✅ 修改 `yaml_loader.py` 解析 `virtual` 字段

### Phase 2: 导出服务变更 ✅ 已完成

1. ✅ 添加 `_get_product_version_codes` 方法
2. ✅ 创建元数据 Sheet
3. ✅ 数据 enrichment 时注入 product_code, version_code

### Phase 3: 导入服务变更 ✅ 已完成

1. ✅ 添加 `_read_meta_sheet` 方法
2. ✅ 添加 `_resolve_version_id` 方法
3. ✅ 修改 `_find_by_business_key` 方法

### Phase 4: 测试验证 🔄 进行中

1. ✅ 单元测试：business_key 字段定义正确
2. ✅ 单元测试：`_get_product_version_codes` 方法正确
3. 🔄 单元测试：`_resolve_version_id` 方法正确
4. 🔄 单元测试：`_find_by_business_key` 方法正确
5. 🔄 集成测试：导出包含元数据 Sheet
6. 🔄 集成测试：导入正确解析 version_id
7. 🔄 集成测试：导入唯一性校验正确
8. 🔄 E2E 测试：完整导出导入流程正确
9. 🔄 E2E 测试：跨版本数据不冲突

## 8. 测试用例详情

### 8.1 TestBusinessKeyContext 测试类

| 测试用例 | 描述 | 状态 |
|---------|------|------|
| test_01_domain_has_product_code_field | 验证 domain 包含 product_code 字段 | ✅ 通过 |
| test_02_domain_has_version_code_field | 验证 domain 包含 version_code 字段 | ✅ 通过 |
| test_03_business_key_import_order | 验证 business_key 字段顺序正确 | 🔄 待验证 |
| test_04_export_has_meta_sheet | 验证导出包含元数据 Sheet | ✅ 通过 |
| test_05_meta_sheet_has_context | 验证元数据 Sheet 包含上下文信息 | ✅ 通过 |
| test_06_get_product_version_codes_method | 验证 _get_product_version_codes 方法 | ✅ 通过 |
| test_07_all_objects_have_context_fields | 验证所有对象都有上下文字段 | ✅ 通过 |

### 8.2 已知问题

#### 问题 1: test_03_business_key_import_order 测试失败

**现象**: 测试期望 business_key 字段顺序为 `['product_code', 'version_code', 'code']`，但实际得到 `['version_code', 'code', 'product_code']`

**原因分析**: 可能是 pytest 测试环境中的 registry 缓存问题，直接运行 Python 脚本时顺序正确

**解决方案**: 
1. 在测试前强制重新加载 YAML 文件
2. 或在测试中显式调用 `registry.reload()`

## 9. TBD 列表

| ID | 项目 | 缺失信息 | 下一步 |
|------|------|----------|--------|
| TBD-1 | 数据库索引 | 是否需要添加 (version_id, code) 复合索引 | 建议添加以提高查询性能 |
| TBD-2 | 批量导入性能 | 大数据量导入时唯一性校验性能 | 可考虑批量查询优化 |
| TBD-3 | 测试缓存问题 | pytest 测试环境 registry 缓存 | 需要在测试中强制重新加载 |

## 10. 验收标准

### 10.1 功能验收

- [ ] 所有架构对象 YAML 包含 product_code 和 version_code 字段
- [ ] 字段属性正确：business_key=true, virtual=true, export_visible=false
- [ ] 导出 Excel 包含元数据 Sheet
- [ ] 元数据 Sheet 包含 product_code, version_code, version_id
- [ ] 导入时正确解析 version_id
- [ ] 不同版本的同 code 对象不冲突

### 10.2 非功能验收

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] E2E 测试通过
- [ ] 用户界面无变化
- [ ] Excel 模板无变化
