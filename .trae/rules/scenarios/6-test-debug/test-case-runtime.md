---
alwaysApply: false
description: "测试运行时安全：共享 App/Client + Registry + 缓存 + 并发"
globs: "meta/tests/**/*,tests/**/*"
---

# 测试运行时安全

> **拆分自** `test-case-standards.md` v1.1
> **本文件覆盖**：§5 共享 App/Client + §6 Registry 与缓存 + §7 并发安全
> **其他章节**：[test-case-design.md](./test-case-design.md)（§1-4）/ [test-case-excel.md](./test-case-excel.md)（§8）/ [test-case-checklist.md](./test-case-checklist.md)（§9-10）

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

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-09-02 | 拆分 | 从 test-case-standards.md §5-7 拆出 |