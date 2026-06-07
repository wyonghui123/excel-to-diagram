# 测试用例编写规范

> **版本** v1.1 | **生效日期** 2026-06-02
> 
> 本文档基于 2026-05-31 全量测试修复经验 + 2026-06-02 Excel 文件测试规范补充。
> 新增测试用例、修改现有测试、或排查测试失败时，**必须**参考本文档。

---

## 目录

1. [核心原则](#1-核心原则)
2. [全局状态隔离](#2-全局状态隔离)
3. [Fixture 编写规范](#3-fixture-编写规范)
4. [测试数据管理](#4-测试数据管理)
5. [共享 App/Client 使用规范](#5-共享-appclient-使用规范)
6. [Registry 与缓存安全](#6-registry-与缓存安全)
7. [并发安全](#7-并发安全)
8. [Excel 文件测试规范](#8-excel-文件测试规范)
9. [反模式清单](#9-反模式清单)
10. [检查清单（新增/修改测试时）](#10-检查清单)

---

## 1. 核心原则

### 1.1 测试独立性（Test Independence）

> **每个测试必须能够独立运行，不依赖其他测试的执行顺序。**

- [OK] 任意单个测试可以在任意顺序下通过
- [OK] 同一文件内所有测试按任意顺序排列都能通过
- [OK] 与任意其他测试文件组合运行都能通过
- [X] 单独运行通过，但放在 suite 中失败 -> **测试污染，必须修复**

**验证方法：**
```bash
# 验证单个测试
python -m pytest <file>::<class>::<test> -xvs -n0

# 验证测试间无顺序依赖（使用 pytest-randomly 或手动反转）
python -m pytest <file> -xvs -n0 --random-order

# 验证跨文件无污染
python -m pytest <file1> <file2> -xvs -n0
```

### 1.2 测试隔离（Test Isolation）

> **每个测试的状态变更不得泄漏到其他测试。**

- 修改全局状态必须在 teardown 中恢复
- 创建的数据必须在 teardown 中清理
- 修改的配置必须在 teardown 中还原

### 1.3 可重复性（Reproducibility）

> **同样的输入必须产生同样的输出，无论运行多少次。**

- 使用确定性数据（避免依赖 `time.time()`、随机数种子等）
- 数据库状态通过快照机制保证一致

---

## 2. 全局状态隔离

### 2.1 问题回顾

本次测试修复中，**92% 以上的失败**都源于全局状态污染：

| 问题类型 | 影响范围 | 根因 |
|---------|---------|------|
| Registry 被清空 | 50+ 测试失败 | `clean_registry` fixture teardown 未恢复 |
| Cookie 泄露 | 10+ 测试失败 | `_SHARED_CLIENT._cookies` 未清理 |
| 共享 App 状态污染 | 4-6 测试失败 | session-scoped shared_app 状态累积 |
| 缓存与状态不一致 | 20+ 测试失败 | `_dir_registry_cache` 不知道 registry 被清空 |

### 2.2 规则：autouse fixture 必须完整恢复

```python
# [OK] 正确：保存原始状态，teardown 中恢复
@pytest.fixture(autouse=True)
def clean_registry():
    from meta.core.models import registry
    saved = dict(registry._objects)      # 1. 保存
    registry._objects.clear()            # 2. 清理
    yield                                # 3. 运行测试
    registry._objects = saved            # 4. 恢复

# [X] 错误：只清理不恢复
@pytest.fixture(autouse=True)
def clean_registry():
    from meta.core.models import registry
    registry._objects.clear()            # 清理了但没恢复
    yield                               # 后续测试拿到空 registry！
```

### 2.3 规则：缓存必须感知底层状态变化

```python
# [OK] 正确：返回缓存前验证底层状态
if canonical_dir in _dir_registry_cache:
    if registry._objects:                # 验证 registry 非空
        return _dir_registry_cache[canonical_dir]
    # registry 为空 -> 缓存失效，重新注册

# [X] 错误：盲目返回缓存
if canonical_dir in _dir_registry_cache:
    return _dir_registry_cache[canonical_dir]  # registry 可能已被清空！
```

### 2.4 规则：HTTP Client 状态必须清理

```python
# [OK] 正确：每次使用前清理 cookie
def get_shared_app():
    global _SHARED_APP, _SHARED_CLIENT
    if _SHARED_APP is None:
        _SHARED_APP = create_app()
        _SHARED_APP.config['TESTING'] = True
        _SHARED_CLIENT = _SHARED_APP.test_client()
    _SHARED_CLIENT._cookies.clear()      # 关键：清除跨 test class 的 cookie
    return _SHARED_APP, _SHARED_CLIENT
```

---

## 3. Fixture 编写规范

### 3.1 Scope 选择指南

| Scope | 适用场景 | 风险 | 建议 |
|-------|---------|------|------|
| `function` | 每个测试独立状态 | 低 | **默认选择** |
| `class` | 同一 class 内共享 | 中 | class 内测试有严格顺序时可用 |
| `module` | 同一文件内共享 | 中 | 确保所有测试使用相同初始状态 |
| `session` | 全局共享 | **高** | 仅用于真正的只读资源 |

### 3.2 Session-Scope Fixture 专项规范

> **[WARNING] session-scope fixture 是本项目测试污染的第一大来源。**

```python
# [X] 危险：session-scope 共享可变状态
@pytest.fixture(scope="session")
def shared_client(shared_app):
    return shared_app.test_client()      # 所有测试共享同一个 client
                                         # cookie、header 等状态会累积

# [OK] 安全：session-scope 仅用于不可变资源
@pytest.fixture(scope="session")
def db_schema_path():
    return Path(__file__).parent / "schema.sql"  # 只读路径，无状态

# [OK] 安全：session-scope + 每次使用时重置状态
@pytest.fixture(scope="session")
def shared_client(shared_app):
    client = shared_app.test_client()
    yield client
    # 但注意：yield 只在 session 结束时执行一次
    # 状态污染仍可能发生在 yield 之前
```

### 3.3 Fixture 依赖链规则

```python
# [X] 危险：依赖链中有可变 session-scope fixture
@pytest.fixture(scope="function")
def my_test(shared_client):           # shared_client 是 session-scope
    client = shared_client            # 拿到了被其他测试污染的 client
    ...

# [OK] 安全：使用 function-scope wrapper 隔离
@pytest.fixture(scope="function")
def clean_client(shared_app):
    client = shared_app.test_client()   # 每次创建新 client
    client._cookies.clear()
    yield client
```

### 3.4 禁止在 fixture 中修改全局配置（不恢复）

```python
# [X] 错误
@pytest.fixture(autouse=True)
def set_test_mode():
    os.environ['SOME_CONFIG'] = 'test'   # 修改了环境变量
    yield                                # 没有恢复！

# [OK] 正确
@pytest.fixture(autouse=True)
def set_test_mode():
    old_value = os.environ.get('SOME_CONFIG')
    os.environ['SOME_CONFIG'] = 'test'
    yield
    if old_value is None:
        del os.environ['SOME_CONFIG']
    else:
        os.environ['SOME_CONFIG'] = old_value
```

---

## 4. 测试数据管理

### 4.1 唯一标识符生成

```python
# [OK] 使用 os.urandom 生成唯一后缀
import os
suffix = os.urandom(4).hex()
username = f'test_user_{suffix}'

# [OK] 使用 uuid
import uuid
username = f'test_user_{uuid.uuid4().hex[:8]}'

# [X] 避免硬编码（容易与其他测试冲突）
username = 'test_user_1'              # 可能与其他测试冲突
```

### 4.2 数据清理策略

```python
class TestExample:
    @classmethod
    def setup_class(cls):
        cls._created = []              # 追踪创建的资源

    def _create_user(self, name):
        resp = self.client.post('/api/v2/bo/user', ...)
        uid = resp.json['data']['id']
        self._created.append(('user', uid))  # 记录
        return uid

    @classmethod
    def teardown_class(cls):
        for obj_type, obj_id in reversed(cls._created):  # 逆序删除
            try:
                cls.client.delete(f'/api/v2/bo/{obj_type}/{obj_id}',
                                  headers=cls.h)
            except Exception:
                pass  # 静默处理（资源可能已被测试删除）
```

### 4.3 数据库测试安全

```python
# [OK] 使用 TESTING 环境变量保护生产数据
if os.environ.get('TESTING') != 'true':
    yield   # 非测试环境不执行修改
    return

# 测试环境的数据库操作...
```

---

## 5. 共享 App/Client 使用规范

### 5.1 两种使用方式对比

| 方式 | 适用场景 | 隔离性 | 性能 |
|------|---------|--------|------|
| `get_shared_app()` | class 级别独立测试 | **完全隔离**（每次新实例） | 较慢 |
| `shared_client` fixture | 轻量单元测试 | 共享（有污染风险） | **快** |

### 5.2 选择指南

```python
# 使用 get_shared_app() 的场景（推荐大多数情况）：
# - 测试需要独立的数据库状态
# - 测试会修改全局配置
# - 测试涉及用户认证/会话
class TestComplexScenario:
    @classmethod
    def setup_class(cls):
        from meta.tests.conftest import get_shared_app
        cls.app, cls.client = get_shared_app()   # 独立实例

# 使用 shared_client fixture 的场景（仅限简单查询）：
# - 只读查询测试
# - 不修改任何全局状态
def test_simple_query(shared_client):
    resp = shared_client.get('/api/v2/health')
    assert resp.status_code == 200
```

### 5.3 HTTP 状态隔离

> **每次使用 client 前必须假设它可能被之前的测试污染。**

```python
# [OK] 在每个测试方法开始前重置
def test_something(self):
    self.client._cookies.clear()       # 清除 cookie
    # 或重建 client
    self.client = self.app.test_client()
```

---

## 6. Registry 与缓存安全

### 6.1 问题回顾

本项目的 `MetaObjectRegistry` 是一个全局单例 (`registry = MetaObjectRegistry()`)，被所有测试共享。任意测试修改它都会影响后续测试。

### 6.2 规则：修改 Registry 必须恢复

```python
# [OK] 测试中临时注册对象，测试后清理
def test_with_custom_object():
    from meta.core.models import registry, MetaObject
    
    original_ids = set(registry._objects.keys())
    
    custom = MetaObject(id="temp_test_obj", ...)
    registry.register(custom)
    
    yield  # 运行测试
    
    # 清理：只删除本测试注册的
    for obj_id in list(registry._objects.keys()):
        if obj_id not in original_ids:
            del registry._objects[obj_id]

# [X] 危险：清空 registry 不恢复
def test_clean_slate():
    registry._objects.clear()           # 所有后续测试都找不到 object！
    ...
```

### 6.3 规则：缓存失效策略

任何修改了被缓存数据源的代码，必须同时通知缓存层：

```python
# 方案 A：修改时主动清除缓存
def clear_registry():
    global _dir_registry_cache
    registry._objects.clear()
    _dir_registry_cache.clear()           # 同步清除缓存

# 方案 B：读取时验证缓存有效性（已实施）
if canonical_dir in _dir_registry_cache:
    if not registry._objects:             # 缓存可能失效
        _dir_registry_cache.clear()
    else:
        return _dir_registry_cache[canonical_dir]
```

---

## 7. 并发安全

### 7.1 测试必须能够在串行和并行模式下都通过

```bash
# 串行验证（地面真相）
python d:\filework\test.py --failed       # -n0 串行

# 并行验证
python d:\filework\test.py --all --force  # -n4 并行
```

### 7.2 并发假失败的识别

| 现象 | 判断 |
|------|------|
| `--all` 失败，`--failed` 通过 | **并发假失败**，不需修复代码 |
| `--all` 失败，`--failed` 也失败 | **真实错误**，必须修复 |
| 单独运行通过，suite 中失败 | **测试污染**，必须修复测试 |

### 7.3 并行安全的数据库操作

```python
# [OK] 使用唯一表名避免冲突
table_name = f'test_data_{uuid.uuid4().hex[:8]}'

# [OK] 使用唯一 ID 避免冲突
record_id = f'rec_{os.urandom(8).hex()}'

# [X] 危险：硬编码表名/ID
table_name = 'test_data'              # 并行时与其他 worker 冲突
```

---

## 8. Excel 文件测试规范

> **[IMPORTANT]** Excel 导入导出是本项目的核心功能。纯 API 测试（只验证状态码和 JSON 响应）
> **无法覆盖** Excel 文件本身的格式、样式、数据验证、注释等特性。
> 必须使用 openpyxl 回读验证导出文件的实际内容。

### 8.1 三层测试架构

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

### 8.2 为什么 API 测试不够

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

### 8.3 Excel 文件级测试编写模式

#### 模式 A：服务层 + openpyxl 回读（推荐，Layer 2）

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

#### 模式 B：API 导出 + openpyxl 回读（Layer 3）

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

### 8.4 Excel 特性验证清单

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

### 8.5 Excel 文件 fixture 规范

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

### 8.6 Excel 测试数据隔离

```python
# [OK] 每个测试创建独立的 Workbook
def test_something(self):
    wb, _ = self._make_child_sheet_wb(data=[...])
    # wb 是独立的，不影响其他测试

# [X] 禁止：测试间共享同一个 Workbook 对象
shared_wb = Workbook()  # module 级别共享，写入操作互相污染
```

### 8.7 openpyxl 颜色值注意事项

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

### 8.8 Excel Design System 样式常量

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

### 8.9 API 响应防御性解析

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

## 9. 反模式清单

以下是本次测试修复中发现的**具体反模式**，新增测试时必须避免：

| # | 反模式 | 后果 | 修复方式 |
|---|--------|------|---------|
| 1 | `autouse` fixture teardown 不恢复状态 | 后续测试大面积失败 | 保存原始状态并恢复 |
| 2 | 缓存层不感知底层状态变化 | 返回失效数据 | 读取缓存前验证数据源 |
| 3 | session-scope client 不清理 cookie | 认证状态泄露 | 每次使用前 `_cookies.clear()` |
| 4 | 修改 `registry._objects` 不清除缓存 | 缓存与实际状态不一致 | 同步清除缓存或验证 |
| 5 | `setup_class` 中硬编码 `TESTING` 设置 | 非测试环境风险 | 使用 `get_shared_app()` 统一管理 |
| 6 | 测试间共享可变全局变量 | 测试顺序依赖 | 每个 test class 独立初始化 |
| 7 | `teardown` 中不清理创建的数据 | 数据累积，测试冲突 | 追踪并清理所有创建的资源 |
| 8 | 依赖 `--all` 的并行执行顺序 | 结果不稳定 | 确保串行和并行都通过 |
| 9 | 只验证 API 状态码，不验证 Excel 文件内容 | "假通过"：样式/验证/注释错误未被发现 | 用 openpyxl 回读验证 |
| 10 | API 响应链式 `.get()` 不加 isinstance 检查 | `AttributeError: 'list' object has no attribute 'get'` | 每层 `.get()` 前检查类型 |
| 11 | 硬编码 openpyxl 颜色值（如 `"#E0E0E0"`） | 断言永远失败（openpyxl 返回 8 位 `"00E0E0E0"`） | 用 `endswith()` 或引用 `ExcelDesignSystem` 常量 |
| 12 | 测试间共享同一个 Workbook 对象 | 写入操作互相污染 | 每个测试创建独立 Workbook |
| 13 | 临时 Excel 文件不清理 | 磁盘空间泄漏 | 使用 `tmp_path` 或 `try/finally + os.unlink` |

---

## 10. 检查清单

### 新增测试时

- [ ] 测试能独立运行吗？（`python -m pytest <test> -xvs -n0`）
- [ ] 与同文件其他测试无顺序依赖？（随机顺序运行验证）
- [ ] 与项目其他测试文件无污染？（随机组合验证）
- [ ] 创建的数据在 teardown 中清理了吗？
- [ ] 修改的全局状态在 teardown 中恢复了吗？
- [ ] 使用了唯一标识符吗？（非硬编码 ID/name）
- [ ] 依赖 session-scope fixture 时考虑了状态污染吗？
- [ ] **涉及 Excel 导入导出？→ 是否用 openpyxl 验证了文件内容？**
- [ ] **API 响应解析是否加了 isinstance 防御？**

### 修改现有测试时

- [ ] 修改前运行了 `--all --force` 建立基线吗？
- [ ] 修改后运行了 `--failed` 确认修复了吗？
- [ ] 确认修复没有引入新的污染吗？（`--all --force` 最终验证）
- [ ] 更新了 `test_confirmed_issues.json` 中的问题状态吗？

### 排查测试失败时

- [ ] 单独运行这个测试能通过吗？
- [ ] 与其他失败测试一起运行能通过吗？
- [ ] 失败的测试有什么共同的 fixture 依赖？
- [ ] 是否有 autouse fixture 可能泄漏状态？
- [ ] 是否有 session-scope fixture 可能累积状态？
- [ ] **`AttributeError: 'list' object has no attribute 'get'`？→ 检查 API 响应 isinstance 防御**

---

## 附录 A：本次修复记录

| 日期 | 问题 | 文件 | 修复 | 类型 |
|------|------|------|------|------|
| 2026-05-31 | Cookie 泄露 | `conftest.py` | `get_shared_app()` 中添加 `_cookies.clear()` | 状态隔离 |
| 2026-05-31 | Registry 清空不恢复 | `test_hierarchy_bo.py` | `clean_registry` fixture 保存/恢复 `_objects` | 状态恢复 |
| 2026-05-31 | 缓存与状态不一致 | `yaml_loader.py` | 缓存返回前检查 `registry._objects` 非空 | 缓存安全 |
| 2026-05-31 | 测试顺序污染 | 多个文件 | 识别为基础设施问题，非代码缺陷 | 诊断方法 |

## 附录 B：快速诊断命令

```bash
# 确认真实错误（排除并发假失败）
python d:\filework\test.py --all --force    # 全量并行基线
python d:\filework\test.py --failed         # 串行确认（地面真相）

# 验证测试独立性
python -m pytest <file1> <file2> -xvs -n0   # 跨文件组合测试

# 查看当前问题状态
python d:\filework\test.py --status

# 查看结构化问题详情
python -c "import json; d=json.load(open('d:/filework/test_confirmed_issues.json')); \
  [print(f'{i[\"test\"]}: {i.get(\"error_message\",\"\")[:100]}') for i in d.get('confirmed_failed',[])]"
```
