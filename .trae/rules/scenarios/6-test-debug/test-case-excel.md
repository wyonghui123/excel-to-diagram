---
alwaysApply: false
description: "Excel 文件测试规范：三层架构 + openpyxl 回读 + 样式常量"
globs: "meta/tests/**/*,tests/**/*"
---

# Excel 文件测试规范

> **拆分自** `test-case-standards.md` v1.1
> **本文件覆盖**：§8 Excel 文件测试规范（全部 9 个小节）
> **其他章节**：[test-case-design.md](./test-case-design.md)（§1-4）/ [test-case-runtime.md](./test-case-runtime.md)（§5-7）/ [test-case-checklist.md](./test-case-checklist.md)（§9-10）

---

> **[IMPORTANT]** Excel 导入导出是本项目的核心功能。纯 API 测试（只验证状态码和 JSON 响应）
> **无法覆盖** Excel 文件本身的格式、样式、数据验证、注释等特性。
> 必须使用 openpyxl 回读验证导出文件的实际内容。

## 8.1 三层测试架构

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: API Round-trip（端到端）                  │  ← 少量，验证集成
│  Export → Download → Modify → Upload → Verify       │
├─────────────────────────────────────────────────────┤
│  Layer 2: Excel File Content（文件级）              │  ← 核心，验证 Excel 特性
│  Service 生成 WB → openpyxl 回读验证                 │
├─────────────────────────────────────────────────────┤
│  Layer 1: Unit Tests（单元）                        │  ← 已有，验证业务逻辑
│  _classify_field / _is_field_editable / etc          │
└─────────────────────────────────────────────────────┘
```

| 层级 | 测试方式 | 速度 | 稳定性 | 覆盖范围 |
|------|---------|------|--------|---------|
| Layer 1 | 直接调用方法 | 快 | 高 | 业务逻辑 |
| Layer 2 | Service + openpyxl 回读 | 快 | 高 | Excel 特性 |
| Layer 3 | API 导出→导入→查询 | 慢 | 中 | 端到端集成 |

## 8.2 为什么 API 测试不够

| 场景 | API 测试 | Excel 文件级测试 |
|------|:--------:|:----------------:|
| 导出数据值错误 | [OK] | [OK] |
| 导入后数据未更新 | [OK] | [OK] |
| 单元格填充色错误（灰 vs 绿） | [X] | [OK] |
| 数据验证下拉缺失/内容错误 | [X] | [OK] |
| 表头注释缺失/内容错误 | [X] | [OK] |
| 列宽溢出或为 0 | [X] | [OK] |
| 新增空行缺失或样式错误 | [X] | [OK] |
| 工作表保护配置错误 | [X] | [OK] |

**核心原则：Excel 文件本身就是用户界面，必须验证文件内容。**

## 8.3 Excel 文件级测试编写模式

### 模式 A：服务层 + openpyxl 回读（推荐，Layer 2）

```python
class TestExcelFileContent:
    @pytest.fixture(autouse=True)
    def _setup_service(self):
        from meta.core.datasource import get_data_source
        from meta.services.manage_service import ManageService
        from meta.services.query_service import QueryService
        from meta.services.import_export_service import ImportExportService
        ds = get_data_source('sqlite', database=get_test_db_path())
        self.ie_service = ImportExportService(
            ds, ManageService(ds), QueryService(ds)
        )

    def _make_child_sheet_wb(self, child_type='annotation', data=None):
        from meta.core.models import registry
        from openpyxl import Workbook
        child_meta = registry.get(child_type)
        if data is None:
            data = [{'id': 1, 'target_type': 'domain', ...}]
        wb = Workbook()
        wb.remove(wb.active)
        sheets_info = []
        self.ie_service._write_child_sheet(
            wb, child_type, child_meta, data, sheets_info
        )
        return wb, child_meta

    def test_header_style(self):
        wb, _ = self._make_child_sheet_wb()
        ws = wb.worksheets[0]
        header = ws.cell(row=1, column=1)
        assert header.fill.start_color.rgb == "004472C4"
        assert header.font.bold is True
```

**优点**：纯内存操作，不写磁盘，速度快，调试方便。

### 模式 B：API 导出 + openpyxl 回读（Layer 3）

```python
def _do_export(client, headers, object_type, scope='cascade'):
    resp = client.post('/api/v1/export', ...)
    data = json.loads(resp.data)
    file_path = data.get('data', {}).get('file_path')
    from openpyxl import load_workbook
    wb = load_workbook(file_path)
    return file_path, wb
```

**注意**：API 响应的 `data` 字段可能是 dict 也可能是 list，必须加 `isinstance` 防御：

```python
result_data = result.get('data', {})
if not isinstance(result_data, dict):
    result_data = {}
```

## 8.4 Excel 特性验证清单

| # | 特性 | openpyxl API | 验证难度 |
|---|------|-------------|---------|
| 1 | Sheet 名称 | `wb.sheetnames` | 简单 |
| 2 | 单元格值 | `ws.cell(row, col).value` | 简单 |
| 3 | 填充色 | `cell.fill.start_color.rgb` | 简单 |
| 4 | 字体 | `cell.font.bold`, `cell.font.color.rgb` | 简单 |
| 5 | 对齐 | `cell.alignment.horizontal` | 简单 |
| 6 | 边框 | `cell.border.left.style` | 简单 |
| 7 | 数据验证 | `ws.data_validations.dataValidation` | 中等 |
| 8 | 注释 | `cell.comment.text` | 简单 |
| 9 | 列宽 | `ws.column_dimensions[col].width` | 简单 |
| 10 | 工作表保护 | `ws.protection.sheet` | 简单 |
| 11 | 单元格保护 | `cell.protection.locked` | 简单 |

## 8.5 Excel 文件 fixture 规范

```python
# [OK] 使用 tmp_path 自动清理
@pytest.fixture
def temp_excel_dir(tmp_path):
    excel_dir = tmp_path / "excel_test"
    excel_dir.mkdir()
    yield excel_dir
    # tmp_path 自动清理，无需手动删除

# [X] 禁止：硬编码路径
excel_path = "C:/Users/test/test.xlsx"  # 跨机器不兼容

# [X] 禁止：不清理的临时文件
tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
# ... 忘记 os.unlink(tmp.name)
```

## 8.6 Excel 测试数据隔离

```python
# [OK] 每个测试创建独立的 Workbook
def test_something(self):
    wb, _ = self._make_child_sheet_wb(data=[...])
    # wb 是独立的，不影响其他测试

# [X] 禁止：测试间共享同一个 Workbook 对象
shared_wb = Workbook()  # module 级别共享，写入操作互相污染
```

## 8.7 openpyxl 颜色值注意事项

openpyxl 的 `start_color.rgb` 返回 **8 位字符串**（前两位是 alpha 通道），例如：
- `#4472C4` → `"004472C4"`
- `#E0E0E0` → `"00E0E0E0"`
- `#E6F7E6` → `"00E6F7E6"`
- `#FFFFFF` → `"00FFFFFF"`

断言时应使用 `endswith()` 或比较后 6 位：

```python
# [OK] 使用 endswith 避免前缀问题
assert fill_rgb.endswith("E0E0E0")

# [OK] 或比较完整值（含 alpha）
assert fill_rgb == "00E0E0E0"

# [X] 禁止：直接用 CSS 颜色比较
assert fill_rgb == "#E0E0E0"  # 格式不匹配，永远失败
```

## 8.8 Excel Design System 样式常量

所有 Excel 样式常量定义在 `ExcelDesignSystem` 类中（`meta/services/excel_design_system.py`）：

| 常量 | 颜色值 | 用途 |
|------|--------|------|
| `READONLY_FILL` | `#E0E0E0` 灰色 | 只读字段 |
| `REQUIRED_FILL` | `#FFF2CC` 浅黄 | 必填字段 |
| `BUSINESS_KEY_FILL` | `#E6F7E6` 浅绿 | 业务键/父对象外键 |
| `HEADER_FILL` | `#1565C0` 蓝色 | 表头 |
| `HEADER_FONT` | 白色粗体 | 表头文字 |
| `THIN_BORDER` | `#E0E0E0` 细线 | 所有单元格 |

测试中应引用这些常量而非硬编码颜色值：

```python
from meta.services.excel_design_system import ExcelDesignSystem as ds
assert cell.fill.start_color.rgb == ds.READONLY_FILL.start_color.rgb
```

## 8.9 API 响应防御性解析

导入/查询 API 的响应结构不稳定，`data` 字段可能是 dict 或 list。**所有 API 响应解析必须加 isinstance 防御**：

```python
# [OK] 防御性解析
result = json.loads(resp.data)
if not isinstance(result, dict):
    result = {}
result_data = result.get('data', {})
if not isinstance(result_data, dict):
    result_data = {}
items = result_data.get('items', [])

# [X] 危险：链式 .get() 不加类型检查
items = json.loads(resp.data).get('data', {}).get('items', [])
# 如果 data 是 list，.get() 会抛 AttributeError: 'list' object has no attribute 'get'
```

---

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 test-case-standards.md §8 拆出 |