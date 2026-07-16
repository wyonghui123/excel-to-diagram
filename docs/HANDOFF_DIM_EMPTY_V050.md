# HANDOFF for V050 - 角色权限页"管理维度为空"修复

**作者**: deploy-agent (coordination)
**日期**: 2026-07-06
**部署版本**: V007.20 (已确认 yonaa 部署成功, busy_timeout=30000, skip_audit=True)
**紧急度**: **MEDIUM** (不影响登录/导入, 仅角色权限页功能异常)
**目标**: dev-agent V050 / 当前开发智能体

---

## 1. 现象

PM 在 `http://localhost:3004/system/role` (yonaa 8081) 角色权限页 → 管理维度范围面板显示：

> 暂无可用的管理维度，请先确认元数据正确加载。

**本地 `http://localhost:3007` 同样空**。**不是数据/迁移问题**（DB `products/versions/domains/sub_domains` 表正常）。

---

## 2. 定位过程（部署智能体已完成的排查）

### 2.1 排除项

- [X] 不是 migration 问题（DB 表正常，hierarchies.yaml 4 个维度定义都在）
- [X] 不是后端 blueprint 未注册（`management_dimension_bp` 在 server.py:709 注册）
- [X] 不是前端 `loadDimensions()` 调用问题（`apiV2.get('/bo/management_dimension')` 正确）

### 2.2 调用链

```
RolePermissionCenter.vue
  → DimensionScopePanel.vue:266  loadDimensions()
  → permissionService.js:153      apiV2.get('/bo/management_dimension')
  → management_dimension_api.py:357  get_dimensions()
  → engine.get_available_dimensions()
  → management_dimension_engine.py:210
  → self._load_dimension_metadata()                       ← 失败在这里
  → loop.run_until_complete(self.cache.get_or_load(...))   ← 异步执行
  → cache_manager.py:176    await self.set(key, data)
  → cache_manager.py:196    async with self._lock:        ← TypeError!
```

### 2.3 根因（已复现）

**文件**: `meta/core/enums/cache_manager.py:196` 和 `cache_manager.py:238`

**问题**: `_lock` 被声明为 `threading.Lock()`，但 `set()` / `invalidate()` 使用 `async with self._lock:`：

```python
# cache_manager.py:120-124
self._lock = threading.Lock()  # ← threading.Lock, 不是 asyncio.Lock

# cache_manager.py:196
async with self._lock:   # ← Python 3.14 严格模式抛 TypeError
    ...
```

**触发错误**:
```
TypeError: '_thread.lock' object does not support the asynchronous context manager
protocol (missed __aexit__ method) but it supports the context manager protocol.
Did you mean to use 'with'?
```

**为什么之前没暴露**：
- Python 3.13 及之前对此宽容（warning 级别）
- **Python 3.14 改为 TypeError**（本地 `python --version` = 3.14.3）
- yonaa backend 用 Python 3.14（V049 升级），所以线上也炸

**为什么 yonaa 之前 dimension 没出错**：
- V007.20 之前，dimensions 缓存命中率可能高（cache miss 时 loader 是同步 yaml 读取，不会触发 set），但**只要触发一次 cache miss + 写缓存就 100% 失败**
- V007.20 重启 backend 后清缓存，**首次访问必定 cache miss → 必现**

---

## 3. 修复方案（极小改动）

### 3.1 修改文件

`meta/core/enums/cache_manager.py`，**2 处**：

| 行号 | 当前 | 改为 |
|------|------|------|
| 196 | `async with self._lock:` | `with self._lock:` |
| 238 | `async with self._lock:` | `with self._lock:` |

**为什么这样改**：
- `_lock` 已是 `threading.Lock()`（cache_manager.py:124），`with` 语义正确
- `set()` / `invalidate()` 是 `async def`，但内部不需 event loop 跨 await 边界（短临界区），用 `threading.Lock` 同步即可
- 这与 FIX v007 注释 (cache_manager.py:121-123) 一致：*"兼容 sync + async 路径, 不需要 event loop"*

### 3.2 不需要改的内容

- [X] **不需要**改 `_lock` 改回 `asyncio.Lock()`（会触发 V007 注释里说的 RuntimeError）
- [X] **不需要**改 `_load_dimension_metadata()` 的 loop 调用方式
- [X] **不需要**改 `hierarchies.yaml`（内容正确）
- [X] **不需要**改任何 migration

### 3.3 验证方法

本地 Python 3.14 复现脚本（已删除，仅作记录）：

```python
# 修复前：抛 TypeError
python -c "
import sys; sys.path.insert(0, '.')
from meta.core.datasource import get_data_source
from meta.services.management_dimension_engine import ManagementDimensionEngine
ds = get_data_source('sqlite', database='meta/architecture.db')
engine = ManagementDimensionEngine(ds, ttl_seconds=300)
dims = engine.get_available_dimensions()
print(len(dims))  # 抛 TypeError, 不打印
"

# 修复后：打印 4
# Dimensions count: 4
#   - id=product name=产品 obj=product desc=按产品维度展示
#   - id=version name=版本 obj=version desc=按版本维度展示
#   - id=domain  name=领域 obj=domain  desc=按领域维度展示
#   - id=sub_domain name=子领域 obj=sub_domain desc=按子领域维度展示
```

**API 验证**（修复后，yonaa backend 启动后）：

```bash
# 先 dev-login
TOKEN=$(curl -s "http://localhost:3011/api/v1/auth/dev-login?username=admin" | python -c "import sys, json; print(json.load(sys.stdin)['data']['token'])")

# 调管理维度 API
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:3011/api/v2/bo/management_dimension" | python -m json.tool

# 期望：data.dimensions 是 4 个元素的数组
```

**前端验证**：

打开 `http://localhost:8081/system/role` → 任一角色 → 管理维度范围面板 → 应显示 4 个维度（产品/版本/领域/子领域）+ 提示"0/4 维度已配置"。

---

## 4. 部署影响

- **修复范围**：仅 `cache_manager.py`，2 行
- **依赖**：无
- **风险**：低（`set` / `invalidate` 改 `with` 不会引入死锁，因为都是短临界区）
- **回归测试**：建议跑 `meta/tests/test_management_dimension_api.py` + `meta/tests/test_p0_other_domains.py`

---

## 5. 交付清单（给 V050 / 开发智能体）

| 项 | 内容 |
|---|------|
| 文件 | `meta/core/enums/cache_manager.py` |
| 行 | 196, 238 |
| 改动 | `async with self._lock:` → `with self._lock:`（2 处） |
| 期望 | 角色权限页管理维度显示 4 个维度 |
| 验证命令 | 见 §3.3 |

---

## 6. 备查：相关上下文

- V007.20 部署确认：`busy_timeout=30000` + `skip_audit=True` 已在 yonaa 生效
- 角色权限页代码：`src/views/SystemManagement/components/DimensionScopePanel.vue`
- 后端 API：`meta/api/management_dimension_api.py:357-391`
- 引擎：`meta/services/management_dimension_engine.py:210-234`
- 缓存：`meta/core/enums/cache_manager.py:120-124`（lock 声明）, 196 + 238（需修复）
- hierarchies.yaml：`meta/schemas/hierarchies.yaml:385-442`（维度定义正确）

---

**部署智能体到此为止，不改后端代码。等待开发智能体确认修复并出新版本号（如 V007.21），由部署智能体重新打包上传。**