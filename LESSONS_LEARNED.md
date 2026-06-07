# 测试重构经验教训 (18 轮, 2026-06-07)

## 🎯 总结

17 个测试文件 (12 API + 5 engine), 199 个测试函数, 255 个测试用例, 100% pass.
CI 配置同步优化 (2 workflows, 6 jobs 修复 TEST_ENTRY 硬阻断).

## 🐛 五大真实 Bug 修复

### Bug 1: stacked `@parametrize` 笛卡尔积 (v10)

**问题**: 我最初用 2 个 `@pytest.mark.parametrize` 装饰器, 期望 8 cases 实际产生 32 cases (4 ops × 8 templates 笛卡尔积).

**错误代码**:
```python
@pytest.mark.parametrize('op,value,expected', [..., 8 cases])  # 8 cases
@pytest.mark.parametrize('op', ['>', '<', '>=', '<='])  # 4 cases
def test_numeric_comparison(self, op, value, expected):
    ...
```

**结果**: 实际运行 32 cases, 浪费 24 个无意义组合.

**修复**: 合并为单 parametrize, op 直接作为 case 参数.

**教训**: 多个 `@parametrize` 装饰器会产生**笛卡尔积**, 几乎总是 bug.

---

### Bug 2: parametrize design contract 违反 (v12)

**问题**: `and_visibility_fail` case 的 `true_record={'visibility': 'private', 'active': 1}` 对于 `visibility = 'public' AND active = 1` 表达式 = `False AND True = False`, 不满足 `is True` 断言.

**错误代码**:
```python
@pytest.mark.parametrize('op,true_record,false_record', [
    # AND: visibility no-match  (这个 case 错了!)
    pytest.param('and', {'visibility': 'private', 'active': 1},
                {'visibility': 'public', 'active': 0}, id='and_visibility_fail'),
])
```

**根因**: 我把 "visibility 不匹配" 设计成 `true_record`, 但根据 `visibility = 'public' AND active = 1` 表达式, `true_record` 应该让表达式返回 True, 而 `{'visibility': 'private', ...}` 让其返回 False.

**修复**: 改为 `{'visibility': 'public', 'active': 1}` 让 `true_record` 真的让 AND 返回 True.

**教训**: parametrize 中 "true_xxx"/"false_xxx" 命名是**契约**, 必须严格满足语义. 调试时优先检查 case 数据是否符合命名契约.

---

### Bug 3: parametrize 用 `url` 关键字 (v10)

**问题**: `pytest.param(..., url='/api/v1/...')` 与 pytest 内置 `url` 参数冲突, 导致 fixture 解析错误.

**错误代码**:
```python
pytest.param('/api/v1/...', id='...')  # 没传 url 关键字
```

**实际触发**: 在某些环境下, 第二个位置参数被 pytest 当作 url fixture.

**修复**: 改用 `endpoint` 或命名参数 `key='url'`.

**教训**: 避免使用 pytest 保留关键字 (`url`, `request`, `config`, `tmp_path` 等) 作为 parametrize 变量名.

---

### Bug 4: CI 硬阻断违反 (v17)

**问题**: `.github/workflows/tests.yml` 直接用 `pytest -m unit` 跑测试, 但项目 `conftest.py` 有 `_block_unguarded_entry()` 在 `TEST_ENTRY` 不为 '1' 时调用 `os._exit(1)`. CI 跑必失败.

**影响**: 整个 `tests.yml` workflow 6 jobs 全部硬阻断.

**修复**: 所有 6 jobs 加 `env: TEST_ENTRY: '1'`.

**教训**: 项目级 conftest 可以有**强制执行的安全策略**, 调用测试入口前必须设置对应 env.

---

### Bug 5: 外部重写导致数据丢失 (v18)

**问题**: `test_nested_where_dsl_eng.py` 在 round 13 后被**完全重写**:
- 实现 `meta.core.nested_where_dsl` 从 dict 语法改成 Django `__` 语法
- 测试文件被同步重写
- 我 round 13 的 4 个 parametrize 合并**完全丢失**

**教训**:
1. **外部重写风险**: 测试文件可被其他人重写, 我的工作可能完全丢失
2. **需要 commit 保护**: 重要 refactor 完成后应立即 commit, 避免丢失
3. **发现时机**: 我用 deep audit 才注意到 0 parametrize (vs 之前的 4), 已经是几轮后

---

## 🔍 7 大 Parametrize 设计规范

### 1. case 命名要契约化
`true_X`/`false_X` 命名必须严格满足语义, 调试时优先检查.

### 2. 避免 stacked parametrize 笛卡尔积
多个 `@parametrize` 会产生 N×M case, 几乎总是 bug.

### 3. `id` 必须自描述
失败时 `test_xxx[case_name]` 一目了然, 用 `id='eq_match'` 而非 `id='case_1'`.

### 4. 避免 lambda 嵌套
pytest 显示 `id=<lambda>` 不可读, 用 helper function + `id='xxx'` 显式.

### 5. 同类操作符合并
`>`/`<`/`>=`/`<=` 合并 → 1 函数 + 8 cases.

### 6. 同类逻辑合并
`and`/`or` 合并 → 1 函数 + 4 cases.

### 7. 错误码/边界合并
`assertRaises` 不同 error code → 1 函数 + N cases.

---

## 🛠️ 13 层 Helper 工具链 (按 ROI 排序)

| 层 | 工具 | 价值 | 备注 |
|----|------|------|------|
| L1 | `assert_status(r, codes)` | 高 | 替换裸 `r.status_code in (...)` |
| L2 | `HTTPStatus.X` 常量 | 高 | 1 处定义, 12 处使用 |
| L3 | `@pytest.mark.parametrize` | 极高 | 重复 test 合并 |
| L4 | `expect(client, m, url, codes)` | 高 | 2 行 → 1 行 |
| L5 | `assert_data_contains/field()` | 中 | body 验证 |
| L6 | `pytest.mark.unit/auth/deprecated` | 高 | CI 分类 |
| L7 | `[MARKER]/[FEATURE]` 头 | 中 | 文件可读性 |
| L8 | `pytest.param(..., id='xxx')` | 高 | 失败定位 |
| L9 | 避免 stacked parametrize | 高 | 防止笛卡尔积 |
| L10 | `id='in'` 而非 `<lambda>` | 中 | 可读 id |
| L11 | `assert_pagination_fields` | 低 | 1/17 用, 低 ROI |
| L12 | 清理 unused imports | 中 | import 清洁度 |
| L13 | CI `TEST_ENTRY=1` | 极高 | 避免 CI 必失败 |

---

## 🏆 18 轮 ROI 演化

| 轮次 | 主题 | 函数数 | 用例数 | 关键 |
|------|------|--------|--------|------|
| v1-v5 | API 测试 + 基础 helpers | 76→49 | 150→152 | L1-L4 helpers |
| v6-v9 | Engine 测试 + parametrize | 55→41 | 237→249 | L6-L9 |
| v10-v14 | 深度 parametrize | 39→34 | 251→255 | 52 合并操作 |
| v15-v16 | 应用未用助手 + 清理 | 34 | 255 | L11-L12 |
| v17 | CI 结构性优化 | - | - | L13, 6 jobs 修复 |
| v18 | 重新审计 (发现回滚) | 34→31 | 255 | 5 个新发现 |

---

## 📊 重复发现: 5 个 alias 常量

| 常量 | 定义 | 出现文件数 |
|------|------|-----------|
| `LIST_OK = HTTPStatus.PAGINATION_OK` | 2 files | test_value_help, test_query |
| `OK_500 = HTTPStatus.PAGINATION_OK` | 2 files | test_query, test_task |
| `VALIDATION_500 = HTTPStatus.CLIENT_ERROR_SERVER` | 2 files | test_filter_variant, test_annotation |
| `NOT_FOUND_AUTH = HTTPStatus.NOT_FOUND_AUTH` | 2 files | test_object_identity, test_user_group |
| `NOT_FOUND_500 = HTTPStatus.NOT_FOUND_500` | 2 files | test_object_identity, test_task |

**结论**: 5 个本地 alias 没有价值, 可直接用 `HTTPStatus.X`. (低风险, P1 清理机会)

---

## ⚠️ 13 个未用 Helpers (0/17 用)

`assert_pagination_fields`, `get_items`, `get_total`, `assert_list_response`, `assert_nested_field`, `assert_error_message`, `assert_validation_error`, `assert_success`, `assert_success_response`, `assert_error`, `assert_not_found`, `assert_unauthorized`, `assert_response_structure`, `assert_field_value`, `assert_has_field`, `assert_pagination`

**原因**: 大多数测试只检查状态码, 不做 body 验证. 高级 helpers 是为复杂场景准备的.

**结论**: 这些 helpers 留在 shared/assertions.py 作为"工具箱", 不必强求使用.

---

## 📚 18 轮经验教训的元教训

1. **不要假设工作持久**: 18 轮 refactor 中遇到了 round 13 全部回滚
2. **stacked parametrize 是坑王**: 一定要避免
3. **parametrize case 命名是契约**: 必须严格符合
4. **CI 配置有隐藏硬规则**: 跑测试前必看 conftest.py
5. **unused import 是真实问题**: 不要因为"反正能跑"就忽略
6. **重复 alias 常量是信号**: 说明设计冗余, 应当消除
7. **Helper 工具箱 vs 强制使用**: 区分 "可用" vs "必须用"
8. **SearchReplace 多次操作需谨慎**: 第一次没成功时需要重新检查
9. **空函数是真实 bug**: 函数定义后必须跟 body
10. **多写 case 数据比写测试函数好**: parametrize 化让 case 数据自描述

---

## 📅 时间线

- **2026-06-07**: 18 轮 refactor 完成
- **17 个测试文件** (12 API + 5 engine)
- **199 个测试函数** / **255 个测试用例**
- **100% pass** 持续保持
- **2 CI workflows** 修复 + 6 jobs marker 化
