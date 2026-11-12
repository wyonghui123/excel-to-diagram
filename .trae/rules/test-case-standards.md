---
alwaysApply: false
description: "测试用例编写规范：命名、结构、断言标准"
globs: "meta/tests/**/*,tests/**/*"
---

# 测试用例编写规范

> v1.2 | 新增/改测试、排查失败必读。演进：v1.1 加 Excel(§8)，v1.2 拆 4 子文件。

## 1. 核心原则

- **独立性**：任意单测/顺序/跨文件组合都须通过；单跑过、suite 挂 = 污染，必修。
- **隔离**：全局状态、创建的数据、配置，teardown 恢复/清理/还原。
- **可重复**：确定性数据（不用 `time.time()`、随机种子）；DB 一致性靠快照。

验证：`python d:\filework\test.py --single <path::func>`；跨文件组合 `python d:\filework\test.py --file <file1>,<file2>`（无顺序依赖、无跨文件污染）。

## 2. 全局状态隔离

92%+ 失败源于：`clean_registry` teardown 未恢复（50+）、`_SHARED_CLIENT._cookies` 未清（10+）、session-scope `shared_app` 累积（4-6）、`_dir_registry_cache` 与 registry 不一致（20+）。

**autouse fixture 四步：保存 → 清理 → yield → 恢复**

```python
@pytest.fixture(autouse=True)
def clean_registry():
    from meta.core.models import registry
    saved = dict(registry._objects)   # 1. 保存
    registry._objects.clear()         # 2. 清理
    yield                             # 3. 运行测试
    registry._objects = saved         # 4. 恢复
```

只 clear 不恢复 = 后续测试拿到空 registry（禁止）。

- **缓存感知底层**：返回 `_dir_registry_cache[canonical_dir]` 前校验 `registry._objects` 非空，为空则失效重注册；禁止盲目返回。
- **client 清理**：`get_shared_app()` 内每次使用前 `_SHARED_CLIENT._cookies.clear()`（清跨 test class cookie）。

## 3. Fixture 编写规范

- **作用域**：`function` 默认；`class`/`module` 仅初始状态严格一致时用；`session` 高风险，仅只读资源。
- **session-scope 是污染第一大来源**：禁共享可变状态（`shared_client` 累积 cookie/header）；只读安全（`db_schema_path` → `Path(__file__).parent / "schema.sql"`）；yield 清理只在 session 末执行一次，yield 前污染仍发生。
- **依赖注入**：function 级测试不得直接依赖 session-scope 可变 fixture（拿到的是被污染的 client），用 function-scope wrapper 隔离：

```python
@pytest.fixture(scope="function")
def clean_client(shared_app):
    client = shared_app.test_client()   # 每次创建新 client
    client._cookies.clear()
    yield client
```

- **禁止在 fixture 里做不可回滚的写库操作、或改配置不还原**（含环境变量）：`old_value = os.environ.get('SOME_CONFIG')` → 设测试值 → yield → 按 `old_value` 还原或 `del`。

## 4. 测试数据管理

- **唯一标识**：`os.urandom(4).hex()` → `f'test_user_{suffix}'`，或 `uuid.uuid4().hex[:8]`；禁硬编码 `'test_user_1'`。
- **创建即登记、逆序清理**：`setup_class` 建 `cls._created = []`；`_create_user` 追加 `('user', uid)`；`teardown_class` 用 `reversed(cls._created)` 删，`except Exception: pass`。
- **DB 隔离**：`get_test_db_path()` 独立测试库；一致性靠 `test.py` 自动快照；禁直读写 `meta/architecture.db`（DB 操作走 `batch_save`）；写库前 `TESTING` 保护（`!= 'true'` → `yield` 后 return）。
- **禁止依赖执行顺序**：串行（-n0）与并行（-n4）都须通过。

## 5. 共享 App/Client

- `get_shared_app()`：每 class 独立实例、完全隔离、较慢 —— 默认推荐（需独立 DB / 改全局配置 / 认证会话）；`shared_client` fixture 共享、快但可能污染 —— 仅只读查询（`client.get('/api/v2/health')`）。
- 用法：`from meta.tests.conftest import get_shared_app`，`cls.app, cls.client = get_shared_app()`；用前假设已污染：`self.client._cookies.clear()` 或重建 `self.app.test_client()`。

## 6. Registry 与缓存

`registry = MetaObjectRegistry()` 全局单例，全测试共享。

- 临时注册只删本测试新增：记 `original_ids = set(registry._objects.keys())`，`yield` 后删不在其中的 key；禁 `registry._objects.clear()` 不恢复。
- 改缓存数据源必须通知缓存层：方案 A 修改时同步 `_dir_registry_cache.clear()`；方案 B（已实施）读取时校验 `registry._objects`，为空则清缓存。

## 7. 并发安全

- 串行地面真相 `python d:\filework\test.py --failed`（-n0）；并行 `python d:\filework\test.py --all --force`（-n4）。
- 判定：`--all` 挂 + `--failed` 过 = 并发假失败（不改码）；都挂 = 真实错误；单跑过 + suite 挂 = 污染。
- 并行安全：唯一表名 `f'test_data_{uuid.uuid4().hex[:8]}'`、唯一 ID `f'rec_{os.urandom(8).hex()}'`；禁 `'test_data'`。

## 8. Excel 文件测试规范

API 测试覆盖不了格式、样式、数据验证、注释 —— **Excel 文件本身就是用户界面**，必须 openpyxl 回读。

- **三层**：Layer 1 单元（`_classify_field`/`_is_field_editable`，快）→ Layer 2 文件级（Service 出 WB + openpyxl 回读，核心）→ Layer 3 API Round-trip（Export → Download → Modify → Upload → Verify，少量）；数据值错误/导入未更新两层都可测，填充色（灰 vs 绿）、数据验证下拉、表头注释、列宽为 0/溢出、新增空行样式、工作表保护只有文件级可测。
- **模式 A（推荐，纯内存）**：`TestExcelFileContent` + autouse `_setup_service`，`get_data_source('sqlite', database=get_test_db_path())` 构造 `ImportExportService(ds, ManageService(ds), QueryService(ds))`；`_make_child_sheet_wb` 调 `_write_child_sheet(wb, child_type, child_meta, data, sheets_info)`；断言 `start_color.rgb == "004472C4"`、`font.bold is True`。
- **模式 B**：`_do_export(client, headers, object_type, scope='cascade')` → `POST /api/v1/export` → `['data']['file_path']` → `load_workbook(file_path)`。
- **特性 API**：`wb.sheetnames`、`ws.cell(row, col).value`、`start_color.rgb`、`font.bold`/`font.color.rgb`、`alignment.horizontal`、`border.left.style`、`ws.data_validations.dataValidation`（中等）、`comment.text`、`column_dimensions[col].width`、`ws.protection.sheet`、`protection.locked`。
- **fixture**：`tmp_path` 自动清理（`temp_excel_dir` = `tmp_path / "excel_test"` 建目录后 yield）；禁 `"C:/Users/test/test.xlsx"`、禁 `NamedTemporaryFile(delete=False)` 忘 `os.unlink`；每测试独立 `Workbook`，禁 module 级共享。
- **颜色**：`start_color.rgb` 是 8 位（含 alpha），`#E0E0E0`→`"00E0E0E0"`、`#4472C4`→`"004472C4"`；用 `endswith("E0E0E0")` 或全值比较，禁 `== "#E0E0E0"`。
- **常量**（`meta/services/excel_design_system.py`，`as ds`）：`READONLY_FILL` #E0E0E0 / `REQUIRED_FILL` #FFF2CC / `BUSINESS_KEY_FILL` #E6F7E6 / `HEADER_FILL` #1565C0 / `HEADER_FONT` 白色粗体 / `THIN_BORDER` #E0E0E0；断言 `== ds.READONLY_FILL.start_color.rgb`。
- **响应防御**：`data` 可能 dict 或 list，每层 `.get()` 前 `isinstance`（`json.loads(resp.data)` 非 dict 置 `{}`）；链式 `.get('data', {}).get('items', [])` 抛 `AttributeError: 'list' object has no attribute 'get'`。

## 9. 反模式清单

1. `autouse` fixture teardown 不恢复状态 → 后续测试大面积失败，保存并恢复。
2. 缓存层不感知底层状态变化 → 返回失效数据，读前校验。
3. session-scope client 不清理 cookie → 认证泄露，每次 `_cookies.clear()`。
4. 改 `registry._objects` 不清缓存 → 与实际不一致，同步清缓存。
5. `setup_class` 硬编码 `TESTING` 设置 → 非测试环境风险，用 `get_shared_app()`。
6. 测试间共享可变全局变量 → 顺序依赖，每 class 独立初始化。
7. `teardown` 不清理创建的数据 → 累积冲突，追踪并清理。
8. 依赖 `--all` 并行执行顺序 → 结果不稳，串行并行都须通过。
9. 只验 API 状态码不验 Excel 内容 → 假通过，openpyxl 回读。
10. API 响应链式 `.get()` 无 isinstance → `AttributeError: 'list' object has no attribute 'get'`，每层先查类型。
11. 硬编码 openpyxl 颜色（`"#E0E0E0"`）→ 断言永败，`endswith()` 或引用 `ExcelDesignSystem` 常量。
12. 测试间共享同一 `Workbook` → 写入互相污染，每测试独立 Workbook。
13. 临时 Excel 文件不清理 → 磁盘泄漏，`tmp_path` 或 `try/finally + os.unlink`。

## 10. 命名与结构

- 目录：`meta/tests/**/*`（后端）、`tests/**/*`（前端/E2E），glob 已绑定，不另建平行目录。
- 命名沿用现有：`TestExample`（数据清理）、`TestComplexScenario`（独立 app）、`TestExcelFileContent`（Excel 文件级）；用例 `test_<验证点>`（`test_header_style`、`test_simple_query`、`test_with_custom_object`）；私有 helper 前置下划线（`_setup_service`、`_make_child_sheet_wb`、`_create_user`、`_do_export`）。

## 11. 检查清单

**新增**：[ ] 独立运行（`python d:\filework\test.py --single <test_id>`）；[ ] 同文件无顺序依赖；[ ] 跨文件无污染；[ ] teardown 清理数据、恢复状态；[ ] 唯一标识；[ ] session-scope 污染已考虑；[ ] Excel → openpyxl 回读；[ ] 响应 isinstance 防御。

**改现有测试**：[ ] 改前 `--all --force` 建基线；[ ] 改后 `--failed` 确认；[ ] `--all --force` 终验；[ ] 更新 `test_confirmed_issues.json`。

**排查失败**：[ ] 单独跑通过；[ ] 与其他失败测试同跑；[ ] 共同 fixture 依赖；[ ] autouse 是否泄漏；[ ] session-scope 是否累积；[ ] 报 `'list' object has no attribute 'get'` → 查响应 isinstance 防御。

## 附录：诊断命令

```bash
python d:\filework\test.py --all --force    # 全量并行基线
python d:\filework\test.py --failed         # 串行确认（地面真相）
python d:\filework\test.py --file <file1>,<file2>   # 跨文件组合
python d:\filework\test.py --status         # 当前问题状态
```

子文件（`scenarios/6-test-debug/`）：`test-case-design.md` / `test-case-runtime.md` / `test-case-excel.md` / `test-case-checklist.md`。
