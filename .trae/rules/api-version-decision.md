# API 版本决策规则 (v1/v2)

> **AI Agent 开发新功能或修改 API 时必须遵循的版本决策规则。**
>
> **目的**: 消除 v1/v2 接口区分不清导致的混淆和效率问题。
>
> **版本**: v1.0 | **更新**: 2026-07-21

---

## 一、核心原则

| 原则 | 说明 |
|------|------|
| **v1 只维护，不新增** | v1 端点只能维护现状或迁移到 v2，禁止在 v1 新增功能 |
| **v2 是默认选择** | 新功能默认用 v2，除非有明确理由用 v1 |
| **状态必须标记** | v1 端点必须用 `_deprecation.py` 装饰器标记状态 |
| **响应格式统一** | v1 和 v2 都必须遵循 `_response_contract.py` 契约 |

---

## 二、版本决策树

开发新功能时，按以下决策树选择 API 版本：

```
1. 实体是否在 BOFramework YAML schema 中？
   ├── 是 → 用 v2 (/api/v2/bo/{entity})
   └── 否 → 继续

2. 操作是否是标准 CRUD（增删改查）？
   ├── 是 → 用 v2（如果实体有 YAML schema）
   │       或评审新增 YAML schema
   └── 否 → 继续

3. 是否是领域专用操作？
   （如 auth/login, export_import, audit, enum, filter_variant）
   ├── 是 → 用 v1（这些领域无 v2 对应）
   └── 否 → 评审

4. 评审标准：
   - 是否需要与其他 v2 实体关联？ → 优先 v2
   - 是否是临时性/实验性功能？ → 可用 v1
   - 是否需要向后兼容？ → 评估迁移成本
```

---

## 三、禁止行为

| # | 禁止 | 正确做法 |
|---|------|---------|
| 1 | 新功能用 v1 做 CRUD | 用 v2（如需新增实体，先加 YAML schema） |
| 2 | 同一 service 文件混用 v1/v2 做同类操作 | 统一到一个版本 |
| 3 | v1 端点新增功能（只能维护或迁移） | 新功能加到 v2 |
| 4 | 前端直接硬编码 `/api/v1/` 或 `/api/v2/` | 用 `apiV1`/`apiV2` 命名空间 |
| 5 | v2 接口内部回调 v1 逻辑 | 下沉到 service 层，v1/v2 共享 |
| 6 | v1 列表返回数组格式 | 用 `ok_list()` 统一分页格式 |
| 7 | v1 端点无废弃标记 | 用 `@v1_deprecated` 或 `@v1_sunset` 标记 |

---

## 四、v1 端点废弃状态规范

### 4.1 四种状态

| 状态 | HTTP | 装饰器 | 含义 |
|------|------|--------|------|
| **ACTIVE** | 200 | 无（默认） | 正常使用 |
| **DEPRECATED** | 200 + `_deprecated: true` | `@v1_deprecated(migrated_to=...)` | 可用但警告，前端应迁移 |
| **SUNSET** | 410 Gone | `@v1_sunset(migrated_to=...)` | 已迁移，前端不应再调用 |
| **REMOVED** | 404 | `@v1_removed()` | 已删除 |

### 4.2 使用示例

```python
from meta.api._deprecation import v1_deprecated, v1_sunset, v1_removed

# DEPRECATED: 仍可用，但前端应迁移
@role_bp.route('/<int:role_id>/logs')
@v1_deprecated(migrated_to='/api/v2/bo/role/<int:role_id>/logs')
def get_role_logs(role_id):
    ...

# SUNSET: 返回 410，前端不能再调用
@role_bp.route('/permissions')
@v1_sunset(migrated_to='/api/v2/bo/permission')
def list_permissions():
    ...

# REMOVED: 返回 404
@role_bp.route('/old-endpoint')
@v1_removed()
def old_endpoint():
    ...
```

### 4.3 迁移流程

```
ACTIVE → DEPRECATED（标记 + 文档）→ SUNSET（返回 410）→ REMOVED（删除路由）
```

- **ACTIVE → DEPRECATED**: 前端有迁移路径后标记
- **DEPRECATED → SUNSET**: sunset_at 日期到达或前端已迁移完成
- **SUNSET → REMOVED**: 一段时间后无报错即可删除

---

## 五、响应格式契约

### 5.1 统一格式

```python
from meta.api._response_contract import ok, ok_list, ok_message, error_response

# 单条
return ok(item)
# {success: true, data: {...}}

# 列表（统一分页格式）
return ok_list(items, total=100, page=1, page_size=20)
# {success: true, data: {items: [...], total, page, page_size}}

# 仅消息
return ok_message('删除成功')
# {success: true, message: '删除成功'}

# 错误
return error_response('资源不存在', code='NOT_FOUND', status=404)
# {success: false, message: '资源不存在', code: 'NOT_FOUND'}
```

### 5.2 旧端点迁移

旧 v1 端点返回数组格式的，逐步用 `ok_list()` 包装：

```python
# Before（旧）
return jsonify({'success': True, 'data': items})

# After（新）
from meta.api._response_contract import ok_list
return ok_list(items, total=len(items))
```

---

## 六、前端调用规范

### 6.1 必须使用 apiV1/apiV2 命名空间

```javascript
import { apiV1, apiV2 } from '@/utils/httpClient'

// [OK] 正确
const r = await apiV1.get('/auth/me')
const r = await apiV2.get('/bo/role')

// [X] 错误：硬编码路径
const r = await axios.get('/api/v1/auth/me')
const r = await fetch('/api/v2/bo/role')
```

### 6.2 ESLint 规则（建议配置）

```javascript
'no-restricted-syntax': ['error', {
  selector: "Literal[value=/^\\/api\\/v[12]\\//]",
  message: '禁止硬编码 /api/v1/ 或 /api/v2/ 路径，必须使用 apiV1 或 apiV2 命名空间'
}]
```

例外文件：测试文件（`__tests__`）、`httpClient.js` 本身。

### 6.3 列表响应处理

```javascript
// [OK] 统一处理（v1 旧端点迁移后也用此格式）
const r = await apiV2.get('/bo/role')
const items = r.data.data.items
const total = r.data.data.total

// [X] 兼容写法（迁移完成后应删除）
const items = r.data.data?.items || r.data.data
```

---

## 七、扫描与监控

### 7.1 生成端点状态清单

```bash
python scripts/audit_v1_endpoints.py
```

输出：
- `docs/api_v1_status.md` - 人类可读报告
- `docs/api_v1_status.json` - 结构化数据

### 7.2 状态分布目标

| 阶段 | ACTIVE | DEPRECATED | SUNSET | REMOVED |
|------|--------|------------|--------|---------|
| 当前（2026-07-21） | 190 | 22 | 58 | 0 |
| 2026-09 目标 | <200 | ~50 | ~20 | 0 |
| 2026-12 目标 | <100 | ~100 | ~50 | ~20 |
| 2027-03 目标 | <50（仅领域专用） | <50 | ~100 | ~70 |

### 7.3 前端迁移进度

> 最近扫描时间: 2026-07-21

| 指标 | 数量 | 说明 |
|------|------|------|
| `apiV1.*` 调用 | 164 次 / 23 文件 | v1 命名空间调用 |
| `apiV2.*` 调用 | 49 次 / 18 文件 | v2 命名空间调用 |
| v1:v2 比例 | 77% : 23% | 前端仍以 v1 为主 |
| 硬编码 `/api/v1/` 或 `/api/v2/` | 32 文件 | 部分为测试/meta 文件（已豁免），其余需迁移 |

仅用 apiV1 的 service 文件：authService, annotationService, auditLogService, enumService, filterVariantService, objectTypeService, filterService, keyTemplateService, relationClassifier, graphqlClient
同时用 apiV1+apiV2 的 service 文件：permissionService (22v1/6v2), associationService (0v1/11v2), hierarchyService (1v1/3v2), archDataConverter (0v1/1v2)

---

## 八、相关文件索引

| 文件 | 用途 |
|------|------|
| [meta/api/_deprecation.py](../../meta/api/_deprecation.py) | v1 废弃状态装饰器 |
| [meta/api/_response_contract.py](../../meta/api/_response_contract.py) | 响应格式契约 |
| [scripts/audit_v1_endpoints.py](../../scripts/audit_v1_endpoints.py) | v1 端点状态扫描脚本 |
| [docs/api_v1_status.md](../../docs/api_v1_status.md) | v1 端点状态清单（自动生成） |
| [docs/api_v1_status.json](../../docs/api_v1_status.json) | 结构化端点数据 |
| [src/utils/httpClient.js](../../src/utils/httpClient.js) | 前端 apiV1/apiV2 命名空间 |
| [meta/api/v2_API_README.md](../../meta/api/v2_API_README.md) | v2 API 文档 |

---

## 九、检查清单

开发新功能或修改 API 前，确认以下事项：

- [ ] 已阅读本规则
- [ ] 已按决策树选择正确的 API 版本
- [ ] v1 端点已用 `_deprecation.py` 装饰器标记状态
- [ ] 响应格式遵循 `_response_contract.py` 契约
- [ ] 前端使用 `apiV1`/`apiV2` 命名空间，未硬编码路径
- [ ] 已运行 `python scripts/audit_v1_endpoints.py` 更新清单
- [ ] 如新增 v2 端点，已更新 `docs/api_v1_status.md` 中的 v2 清单

---

## 十、CHANGELOG

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-07-21 | 创建本规则 | AI Assistant |
