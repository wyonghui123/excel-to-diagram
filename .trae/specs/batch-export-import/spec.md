# Spec: 批量导出导入功能

## 1. 背景与目标

### 1.1 背景

当前架构数据管理系统的导入导出功能仅为占位实现，无法满足实际业务需求：
- 无法批量导出数据用于备份、迁移或分析
- 无法批量导入数据，只能逐条手动创建
- 跨环境数据同步困难
- 层级关联数据无法整体迁移

### 1.2 业务目标

- 支持批量导出架构数据，便于数据备份、迁移和分析
- 支持批量导入架构数据，提高数据录入效率
- 支持跨环境数据同步
- 遵循元数据模型驱动原则，导出导入逻辑由元模型定义

### 1.3 设计原则

1. **元数据驱动优先**：所有导入导出行为由元模型定义驱动
2. **渐进式增强**：分阶段实施，确保每一步可验证
3. **架构兼容性**：确保元模型扩展向后兼容，为未来Agent化预留空间

## 2. 需求类型概览

| 类型 | 适用 | 证据（来源） |
| --- | --- | --- |
| 业务 | 是 | 用户需求：批量数据迁移、备份 |
| 用户/涉众 | 是 | 架构师、数据管理员使用场景 |
| 解决方案 | 是 | 元数据驱动的导入导出服务 |
| 功能 | 是 | Spec功能需求章节 |
| 非功能 | 是 | 性能、安全性要求 |
| 外部接口 | 是 | API接口、Excel文件格式 |
| 过渡 | 是 | 数据迁移、兼容性处理 |

## 3. 功能需求

### FR-001: 单对象类型导出

- **描述**: 系统必须支持导出单个对象类型的所有数据到Excel文件
- **验收标准**:
  - 用户可选择导出当前列表视图中的对象类型
  - 导出文件包含该对象类型的所有字段（根据元模型定义）
  - 导出文件包含层级路径列
  - 导出文件包含层级ID列
  - 支持按筛选条件导出
- **优先级**: Must
- **来源**: 用户需求分析

### FR-002: 级联导出

- **描述**: 系统必须支持级联导出，即导出某个对象时自动包含其所有子级对象
- **验收标准**:
  - 导出产品时，自动包含版本、领域、子领域、服务模块、业务对象、关系
  - 导出版本时，自动包含领域、子领域、服务模块、业务对象、关系
  - 导出领域时，自动包含子领域、服务模块、业务对象、关系
  - 每种对象类型使用独立的Sheet
  - 导出文件包含元数据Sheet
- **优先级**: Must
- **来源**: 用户需求分析

### FR-003: Excel文件格式规范

- **描述**: 导出的Excel文件必须遵循统一的格式规范
- **验收标准**:
  - 第一行为表头，使用元模型定义的字段名称
  - 层级信息作为多列分别展示
  - 包含层级路径列（完整路径）
  - 包含层级ID列（用于导入时关联）
- **优先级**: Must
- **来源**: 用户确认

### FR-004: 单对象类型导入

- **描述**: 系统必须支持从Excel文件导入单个对象类型的数据
- **验收标准**:
  - 用户上传Excel文件后，系统自动识别Sheet对应的对象类型
  - 支持字段自动映射（根据元模型定义的字段名称、ID、别名）
  - 导入前显示预览和校验结果
  - 导入完成后显示结果统计
- **优先级**: Must
- **来源**: 用户需求分析

### FR-005: 级联导入

- **描述**: 系统必须支持从包含多个Sheet的Excel文件级联导入数据
- **验收标准**:
  - 自动识别Excel中的多个Sheet
  - 按层级顺序导入（根据parent_object关系自动排序）
  - 自动处理层级关联
  - 导入失败时提供详细错误信息
- **优先级**: Must
- **来源**: 用户需求分析

### FR-006: 导入冲突处理（Upsert）

- **描述**: 导入时遇到数据冲突必须采用Upsert策略
- **验收标准**:
  - 根据业务键（business_key）字段判断是否存在
  - 存在则更新记录，不存在则插入新记录
  - 更新时保留未导入字段的原始值
- **优先级**: Must
- **来源**: 用户确认

### FR-007: 导入预览和校验

- **描述**: 导入前必须提供数据预览和校验功能
- **验收标准**:
  - 显示即将导入的数据预览
  - 校验必填字段是否填写
  - 校验字段类型是否正确
  - 校验外键关联是否存在
  - 显示校验结果统计和详细错误列表
- **优先级**: Should
- **来源**: 行业最佳实践

## 4. 非功能需求

### NFR-001: 性能

- **描述**: 导入导出操作应在合理时间内完成
- **度量**: 
  - 单对象类型导出（1000条记录）< 5秒
  - 级联导出（完整产品）< 30秒
  - 单对象类型导入（1000条记录）< 10秒
- **优先级**: Should

### NFR-002: 可靠性

- **描述**: 导入操作应保证数据一致性
- **度量**: 
  - 导入失败时自动回滚
  - 级联导入使用事务保证一致性
- **优先级**: Must

## 5. 外部接口需求

### IF-001: 导出API

- **类型**: API
- **端点**: `POST /api/v1/export`
- **请求体**:
```json
{
  "object_type": "domain",
  "scope": "single|cascade",
  "filters": {"version_id": 1},
  "options": {
    "include_hierarchy_path": true,
    "include_hierarchy_ids": true
  }
}
```

### IF-002: 导入API

- **类型**: API
- **端点**: `POST /api/v1/import`
- **请求**: multipart/form-data
  - file: Excel文件
  - mode: preview|execute
  - conflict_strategy: upsert|skip|replace

### IF-003: 导入模板API

- **类型**: API
- **端点**: `GET /api/v1/import/template/{object_type}`

## 6. 约束与假设

### 6.1 技术约束

- 使用openpyxl库处理Excel文件
- 导出文件格式为.xlsx（Excel 2007+）
- 单次导入数据量不超过10000行

### 6.2 假设

- 用户熟悉Excel操作
- 导入数据已按层级顺序排列（级联导入时）

## 7. 优先级与里程碑

| ID | 需求 | 优先级 | 原因 |
| --- | --- | --- | --- |
| FR-001 | 单对象类型导出 | Must | 核心功能 |
| FR-002 | 级联导出 | Must | 核心功能 |
| FR-003 | Excel格式规范 | Must | 基础规范 |
| FR-004 | 单对象类型导入 | Must | 核心功能 |
| FR-005 | 级联导入 | Must | 核心功能 |
| FR-006 | Upsert冲突处理 | Must | 用户确认 |
| FR-007 | 导入预览校验 | Should | 用户体验 |

## 8. 技术设计（RFC）

### 8.1 元模型扩展

#### 8.1.1 扩展SemanticAnnotation

```python
@dataclass
class SemanticAnnotation:
    """语义标注"""
    meaning: str = ""
    business_key: bool = False
    display_name: bool = False
    pattern: str = ""
    examples: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)
    category: str = ""
    hierarchy_level: int = 0
    custom: Dict[str, Any] = field(default_factory=dict)
    
    # 新增：导入导出相关
    data_category: str = ""           # text | code | date | number | timestamp
    import_visible: bool = True       # 导入时是否可见
    export_visible: bool = True       # 导出时是否可见
    import_order: int = 100           # 导出列顺序
```

#### 8.1.2 新增ImportExportConfig

```python
@dataclass
class ImportExportConfig:
    """导入导出配置"""
    import_enabled: bool = True
    export_enabled: bool = True
    cascade_export: bool = True
    cascade_import: bool = True
    conflict_strategy: str = "upsert"
    conflict_key: str = ""
    description_for_agent: str = ""
```

#### 8.1.3 新增DataCategory枚举

```python
class DataCategory(Enum):
    """数据类别"""
    TEXT = "text"
    CODE = "code"
    DATE = "date"
    TIMESTAMP = "timestamp"
    NUMBER = "number"
    AMOUNT = "amount"
    BOOLEAN = "boolean"
```

### 8.2 服务层扩展

#### 8.2.1 导出服务扩展

```python
class ImportExportService:
    def export_cascade(self, object_type: str, filters: dict, options: dict) -> str:
        """级联导出"""
        # 1. 确定导出对象类型列表
        object_types = self._get_cascade_object_types(object_type)
        
        # 2. 按层级排序
        ordered_types = self._sort_by_hierarchy(object_types)
        
        # 3. 查询数据并添加层级信息
        sheets = []
        for ot in ordered_types:
            data = self._query_with_hierarchy(ot, filters)
            sheets.append(self._build_sheet(ot, data, options))
        
        # 4. 生成Excel
        return self._generate_excel(sheets, options)
```

#### 8.2.2 导入服务扩展

```python
class ImportExportService:
    def import_cascade(self, file_path: str, mode: str, conflict_strategy: str) -> dict:
        """级联导入"""
        # 1. 解析Excel
        sheets = self._parse_excel(file_path)
        
        # 2. 校验数据
        validation = self._validate_sheets(sheets)
        if mode == 'preview':
            return {'preview': sheets, 'validation': validation}
        
        # 3. 按层级顺序导入
        results = {}
        for sheet in self._sort_sheets_by_hierarchy(sheets):
            results[sheet.object_type] = self._import_sheet(
                sheet, conflict_strategy
            )
        
        return {'results': results}
```

### 8.3 API端点设计

```python
# meta/api/export_import_api.py

export_import_bp = Blueprint('export_import', __name__, url_prefix='/api/v1')

@export_import_bp.route('/export', methods=['POST'])
def export_data():
    """导出数据"""
    pass

@export_import_bp.route('/export/download/<int:task_id>', methods=['GET'])
def download_export(task_id):
    """下载导出文件"""
    pass

@export_import_bp.route('/import', methods=['POST'])
def import_data():
    """导入数据"""
    pass

@export_import_bp.route('/import/template/<object_type>', methods=['GET'])
def download_template(object_type):
    """下载导入模板"""
    pass
```

### 8.4 前端组件设计

```
src/views/ArchDataManageApp/
├── components/
│   ├── ExportDialog.vue     # 导出对话框
│   └── ImportDialog.vue     # 导入对话框
├── composables/
│   └── useApi.js            # 扩展API方法
```

## 9. 实施步骤

### Step 1: 扩展元模型核心类

**文件**: `meta/core/models.py`

**变更内容**:
1. 扩展`SemanticAnnotation`添加导入导出字段
2. 新增`ImportExportConfig`数据类
3. 新增`DataCategory`枚举
4. 扩展`MetaObject`添加`import_export`字段

**安全措施**: 所有新增字段都有默认值，不影响现有代码

### Step 2: 更新YAML元模型配置

**文件**: `meta/schemas/*.yaml`

**变更内容**:
1. 在各对象YAML中添加`import_export`配置
2. 在字段定义中添加`semantics.data_category`等字段

**安全措施**: 新增配置项，不影响现有配置

### Step 3: 扩展导入导出服务

**文件**: `meta/services/import_export_service.py`

**变更内容**:
1. 添加`export_cascade`方法
2. 添加`import_cascade`方法
3. 添加`_get_cascade_object_types`方法
4. 添加`_sort_by_hierarchy`方法
5. 添加`_query_with_hierarchy`方法
6. 添加`upsert_record`方法

**安全措施**: 新增方法，不修改现有方法签名

### Step 4: 新增API端点

**文件**: `meta/api/export_import_api.py`（新建）

**变更内容**:
1. 创建新的Blueprint
2. 实现`/export`端点
3. 实现`/import`端点
4. 实现`/import/template`端点

**安全措施**: 新增文件，不影响现有API

### Step 5: 注册新API

**文件**: `meta/server.py`

**变更内容**:
1. 导入新的Blueprint
2. 注册到Flask应用

### Step 6: 创建前端导出对话框

**文件**: `src/views/ArchDataManageApp/components/ExportDialog.vue`（新建）

**变更内容**:
1. 创建导出对话框组件
2. 支持选择导出范围
3. 支持选择导出选项

### Step 7: 创建前端导入对话框

**文件**: `src/views/ArchDataManageApp/components/ImportDialog.vue`（新建）

**变更内容**:
1. 创建导入对话框组件
2. 支持文件上传
3. 支持预览校验
4. 显示导入结果

### Step 8: 扩展前端API

**文件**: `src/views/ArchDataManageApp/composables/useApi.js`

**变更内容**:
1. 添加`exportData`方法
2. 添加`importData`方法
3. 添加`downloadTemplate`方法

### Step 9: 集成到主界面

**文件**: `src/views/ArchDataManageApp/index.vue`

**变更内容**:
1. 导入新组件
2. 修改`handleExport`方法
3. 修改`handleImport`方法

### Step 10: 测试验证

1. 单元测试：导入导出服务
2. 集成测试：API端点
3. E2E测试：前端交互流程

## 10. TBD列表

| ID | 项目 | 缺失信息 | 下一步 |
| --- | --- | --- | --- |
| TBD-1 | 权限控制 | 具体哪些角色可导入导出 | 默认所有用户可导出，管理员可导入 |
| TBD-2 | 文件保留 | 导出文件保留时间 | 默认7天 |

Spec包含10个章节，最后章节是"TBD列表"，内容完整。
