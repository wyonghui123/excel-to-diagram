---
alwaysApply: false
description: "测试用例设计原则：核心原则 + 全局状态隔离 + Fixture + 数据管理"
globs: "meta/tests/**/*,tests/**/*"
---

# 测试用例设计原则

> **拆分自** `test-case-standards.md` v1.1（687 行 → 拆分）
> **本文件覆盖**：§1 核心原则 + §2 全局状态隔离 + §3 Fixture + §4 数据管理
> **其他章节**：[test-case-runtime.md](./test-case-runtime.md)（§5-7）/ [test-case-excel.md](./test-case-excel.md)（§8）/ [test-case-checklist.md](./test-case-checklist.md)（§9-10）

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

### 3.5 夹具必须自建运行时基础设施（用临时库直连时）

> **[!] 2026-10-22 补充：元数据对象适配类测试（`test_object_adaptation_*.py`）踩过的 2 个基础设施坑**

这类测试用 fixture 直接连**临时 sqlite 库**，不经过 server 启动流程，于是**生产环境由启动过程建立的两样东西缺失**，
表现为「所有写路径一起挂」：

| 缺失物 | 谁建立 | 缺失时的报错 | 夹具补法 |
|--------|--------|--------------|----------|
| **DB config 单例** | server 启动时 `detect_runtime_config(db_path)` | `[V007.15 L0] DB config not detected yet` | fixture 里显式调 `detect_runtime_config(db_path)` |
| **`v_audit_all` 视图** | 生产库由迁移 `v007_50_add_audit_union_view.py` 建 | `no such table: v_audit_all` | fixture 里 `CREATE VIEW v_audit_all AS SELECT * FROM audit_logs` |

**为什么第一个坑只在写路径暴露**：`bo_framework.commit` / `rollback` 内部调 `get_runtime_config()`，
而该 module-level 单例**只在 server 初始化时被赋值**——读路径不碰它，写路径一碰就报
「config not detected yet」。所以**读全过、写全挂**是这类夹具的典型症状。

```python
# [OK] 正确：夹具里补齐两样基础设施
ds = get_data_source('sqlite', database=db_path)

from meta.core.db_config_detector import detect_runtime_config
detect_runtime_config(db_path)          # ← 补 DB config 单例

ds.execute('CREATE VIEW IF NOT EXISTS v_audit_all AS SELECT * FROM audit_logs')
ds.commit()                             # ← 补审计联合视图
```

> **通用教训**：写「临时库夹具」时，把**生产环境靠启动流程建立的东西**列一遍：
> 单例（runtime config / registry / cache）、视图（v_*）、种子数据（permission_sets / menus）。
> 漏哪样，测试就在哪条路径上整片失败。

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

## CHANGELOG

| 日期 | 变更 | 内容 |
|---|---|---|
| 2026-10-22 | v1.3 | **补 §3.5 临时库夹具必须自建运行时基础设施**（DB config 单例 + `v_audit_all` 视图） |
| 2026-09-02 | 拆分 | 从 test-case-standards.md §1-4 拆出 |