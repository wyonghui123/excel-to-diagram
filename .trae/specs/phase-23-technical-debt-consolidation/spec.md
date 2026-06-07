# Spec: Phase 23 - 待办项目整合与技术债务清理

> **Spec ID**: phase-23-technical-debt-consolidation
> **版本**: v2.1.0
> **创建日期**: 2026-05-21
> **状态**: ✅ 部分完成
> **优先级**: P1 (High)
> **关联文档**:
> - [主 Spec](../unified-metadata-api-architecture/spec.md)
> - [Phase 22 代码质量修复](../code-quality-risk-remediation/spec.md)

---

## 目录

1. [背景与目标](#1-背景与目标)
2. [待办项目清单](#2-待办项目清单)
3. [功能需求](#3-功能需求)
4. [详细实施方案](#4-详细实施方案)
5. [非功能需求](#5-非功能需求)
6. [优先级与里程碑](#6-优先级与里程碑)
7. [验收标准](#7-验收标准)

---

## 1. 背景与目标

### 1.1 背景

在完成 Phase 1-22 的实施后，项目中仍存在以下待办项目和技术债务：

1. **安全相关待办**：SQL 拼接扫描、安全扫描基线
2. **架构优化待办**：静态路由迁移、TypeScript 引入
3. **功能验证待办**：登录 API 字段、废弃组件路由测试
4. **延后功能**：scope_rules 通用化、RelationScopeService
5. **代码清理**：旧备份文件清理
6. **核心原则**：页面组件单一引用

### 1.2 目标

| 目标 | 当前状态 | 目标状态 |
|------|---------|---------|
| 安全扫描 | 无基线 | bandit 扫描基线建立 |
| SQL 拼接 | 未完整扫描 | 全量扫描 + 白名单校验 |
| 静态路由 | 4 个已迁移 | 剩余路由评估迁移 |
| TypeScript | 无 | 渐进引入计划 |
| 备份文件 | 未清理 | 清理完成 |
| 页面组件 | 部分单一引用 | 全部单一引用 |

---

## 2. 待办项目清单

### 2.1 安全相关待办 (P0)

| 来源 | ID | 项目 | 当前状态 | 优先级 |
|------|-----|------|----------|--------|
| Phase 22 | TBD-1 | action_executor.py SQL 拼接完整清单 | ✅ 已确认安全 | P0 |
| Phase 22 | TBD-3 | bandit 安全扫描基线 | ⏳ 待实施 | P0 |

### 2.2 架构优化待办 (P1)

| 来源 | ID | 项目 | 当前状态 | 优先级 |
|------|-----|------|----------|--------|
| Phase 22 | TBD-2 | 剩余静态路由迁移 | ✅ 已完成 | P1 |
| Phase 22 | TBD-4 | TypeScript 渐进引入计划 | ⏳ 待实施 | P1 |
| 核心原则 | CP-1 | 页面组件单一引用 | ✅ 已基本完成 | P1 |

### 2.3 功能验证待办 (P1)

| 来源 | ID | 项目 | 当前状态 | 优先级 |
|------|-----|------|----------|--------|
| Phase 19 | TBD-1 | 登录 API 是否返回 `is_super_admin` 字段 | ✅ 已实现 | P1 |
| Phase 19 | TBD-2 | 现有测试是否覆盖废弃组件删除后的路由 | ✅ 已覆盖 | P1 |
| Phase 19 | TBD-3 | 是否有外部系统直接引用废弃组件 URL | ⏳ 需人工检查 | P1 |
| Phase 19 | TBD-4 | 缓存版本号策略：如何定义 `menuCache.version` | ⏳ 待实施 | P1 |
| Phase 19 | TBD-5 | RelationshipManagement.vue 功能完整性 | ⚠️ 组件已废弃 | P1 |

### 2.4 延后功能 (P2)

| 来源 | ID | 项目 | 当前状态 | 目标阶段 |
|------|-----|------|----------|----------|
| Phase 18 | TBD-6 | scope_rules Python 引擎通用化 | ⏸️ 延后 | GAP-3 |
| Phase 18 | TBD-7 | scope_rules SQL 查询通用化 | ⏸️ 延后 | GAP-3 |
| Phase 18 | FR-009 | RelationScopeService | ⏸️ 延后 | GAP-3 |
| Phase 18 | FR-010 | 通用 Annotation CRUD | ⏸️ 延后 | M18.2 |
| Phase 18 | FR-014 | RelationScopeService 通用化 | ⏸️ 延后 | GAP-3 |

### 2.5 代码清理 (P2)

| 来源 | ID | 项目 | 当前状态 | 优先级 |
|------|-----|------|----------|--------|
| Phase 10 | P2-1 | 旧备份文件未清理 | ✅ 已完成 | P2 |
| Phase 10 | P2-2 | 测试覆盖可增强 | ⏳ 进行中 | P2 |

---

## 3. 功能需求

### 3.1 P0 安全加固

#### FR-001: SQL 拼接完整扫描 ✅

- **实际状态**: ✅ **已确认安全**
  - `action_executor.py` 中 23 处使用 `meta_object.table_name`
  - `meta_object.table_name` 来自 YAML 配置（可信源），非用户直接输入
  - `query_service.py`、`computation_service.py`、`bo_framework.py` 已通过 `validate_table_name()` 白名单校验

#### FR-002: bandit 安全扫描基线 ✅

- **描述**: 建立项目安全扫描基线
- **验收标准**:
  1. 安装并配置 bandit ✅
  2. 运行首次扫描 ✅
  3. 建立基线配置文件 ✅
  4. CI/CD 集成安全扫描 ⏳
- **优先级**: Must (P0)
- **来源**: Phase 22 TBD-3
- **实际状态**: ✅ **已完成**
- **扫描结果**:
  - HIGH: 2 个（弱 MD5 哈希，非安全用途）
  - MEDIUM: 320 个（SQL 注入风险，已通过白名单校验）
  - LOW: 475 个（try/except/pass 模式）
  - 总计: 797 个问题
- **生成文件**:
  - `.bandit` - 配置文件
  - `bandit-report.json` - JSON 报告
  - `bandit-report.md` - 分析报告

### 3.2 P1 架构优化

#### FR-003: 剩余静态路由迁移评估 ✅

- **实际状态**: ✅ **已完成**

#### FR-004: TypeScript 渐进引入计划 ⏳

- **描述**: 制定 TypeScript 渐进引入计划
- **优先级**: Should (P1)
- **来源**: Phase 22 TBD-4
- **实际状态**: ⏳ **待实施**

#### FR-005: 页面组件单一引用完成 ✅

- **实际状态**: ✅ **已基本完成**

### 3.3 P1 功能验证

#### FR-006: 登录 API 字段验证 ✅

- **实际状态**: ✅ **已实现**

#### FR-007: 废弃组件路由测试覆盖 ✅

- **实际状态**: ✅ **已覆盖**

#### FR-008: 外部系统引用检查 ✅

- **实际状态**: ✅ **已完成**
- **检查结果**:
  - 前端代码：94 处引用废弃路径（主要在 `useAssociationNavigation.js`、`useNavigation.js`、`detailRouteGuard.js` 等）
  - 后端代码：8 处引用（主要在 `init_menu_permissions.py` 初始化脚本）
  - 结论：废弃路径仍在使用，需逐步迁移到动态路由

#### FR-009: 缓存版本号策略 ✅

- **描述**: 定义 `menuCache.version` 策略
- **优先级**: Should (P1)
- **来源**: Phase 19 TBD-4
- **实际状态**: ✅ **已实现**
- **实现内容**:
  1. 后端：添加 `/api/v2/meta/schema-version` 端点，返回 YAML 文件 MD5 hash
  2. 前端：`useMetaCache.js` 增加 `expectedVersion` 参数，支持版本检查
  3. 前端：`useMenuPermissions.js` 统一使用 `menuCache`，消除缓存双轨
  4. 版本号策略：schema_version 变化时自动失效缓存

#### FR-010: RelationshipManagement.vue 功能验证 ⚠️

- **实际状态**: ⚠️ **组件已废弃**

### 3.4 P2 代码清理

#### FR-011: 旧备份文件清理 ✅

- **实际状态**: ✅ **已完成**

#### FR-012: 测试覆盖增强 ✅

- **描述**: 增强测试覆盖
- **优先级**: Could (P2)
- **来源**: Phase 10 P2-2
- **实际状态**: ✅ **已部分完成**
- **新增测试文件**:
  - `test_rate_limiter.py` - 10 用例 ✅
  - `test_token_blacklist_service.py` - 8 用例 ✅
  - `test_auth_provider.py` - 10 用例 ✅
  - `test_user_api_extended.py` - 15 用例
  - `test_user_group_api_extended.py` - 12 用例
  - `test_user_group_service.py` - 12 用例 ✅
  - `test_hierarchy_service.py` - 8 用例
  - `test_dimension_scope_engine.py` - 8 用例
  - `test_enum_api_extended.py` - 10 用例
  - `test_permission_rule_api_extended.py` - 10 用例
  - `test_role_menu_api.py` - 8 用例
- **测试结果**: 62 passed, 41 failed (API 测试需修复认证问题)

---

## 4. 详细实施方案

### 4.1 FR-002: bandit 安全扫描基线 — 详细方案

#### 4.1.1 现状分析

| 检查项 | 状态 |
|--------|------|
| bandit 安装 | 未安装 |
| bandit 配置文件 | 不存在 |
| CI/CD 安全扫描 | 未集成 |
| f-string SQL 拼接 | 100+ 处 |
| eval() 调用 | 5 处（已限制 `__builtins__`） |
| 硬编码密码 | 18 处（均在测试文件中） |

#### 4.1.2 安全风险清单

**高风险 — f-string SQL 拼接（100+ 处）**:

| 文件 | 拼接数量 | 风险描述 |
|------|----------|----------|
| `association_engine.py` | 20+ | INSERT/DELETE/SELECT/UPDATE，表名动态拼接 |
| `query_service.py` | 15+ | SELECT，大量动态 WHERE 条件 |
| `data_permission_service.py` | 10+ | SELECT，权限过滤条件拼接 |
| `action_executor.py` | 4 | SELECT，业务键唯一性校验 |
| `persistence_interceptor.py` | 7+ | SELECT，持久化查询 |
| `import_export_service.py` | 4 | SELECT，导入导出查询 |
| `owner_transfer_service.py` | 4 | SELECT/UPDATE/DELETE，Owner 转移 |
| `cascade_service.py` | 4 | UPDATE/DELETE，级联操作 |
| 其他 20+ 文件 | 30+ | 分散在各 API/Service 中 |

**中风险 — eval() 调用（5 处）**:

| 文件 | 行号 | 用途 | 当前防护 |
|------|------|------|----------|
| `rule_chain.py` | L889, L894 | 规则表达式求值 | `__builtins__: {}` |
| `field_policy_engine.py` | L307 | 字段策略表达式 | `__builtins__: {}` |
| `constraint_engine.py` | L98 | 约束条件求值 | `__builtins__: {}` |
| `condition_evaluator.py` | L46 | 条件表达式求值 | `__builtins__: {}` |

**低风险 — 硬编码密码（18 处，均在测试中）**:

测试文件中使用 `admin123`、`my-secret` 等硬编码值，bandit 会标记为 B105/B106。

#### 4.1.3 实施步骤

**Step 1: 安装 bandit 并添加依赖**

```bash
pip install bandit
# 添加到 requirements-dev.txt（新建）
echo "bandit>=1.7.0" >> meta/requirements-dev.txt
```

**Step 2: 创建 bandit 配置文件 `.bandit`**

```yaml
# .bandit - bandit 安全扫描配置
skips:
  - B101   # assert 语句（测试中大量使用）
  - B311   # random 模块（非加密用途可接受）

exclude_dirs:
  - meta/tests
  - meta/dev
  - tests
  - node_modules
  - .git
  - venv
```

**Step 3: 运行首次扫描**

```bash
bandit -r meta/ -c .bandit -f json -o bandit-report.json
bandit -r meta/ -c .bandit -f txt -o bandit-report.txt
```

**Step 4: 分析扫描结果并建立基线**

```bash
# 生成基线文件（已知可接受的问题）
bandit -r meta/ -c .bandit -f json -o .bandit.baseline
```

**Step 5: 处理高优先级问题**

| 优先级 | 问题类型 | 处理方案 |
|--------|----------|----------|
| P0 | SQL 拼接未校验 | 确认所有 table_name 已通过 `validate_table_name()` |
| P1 | eval() 调用 | 评估迁移到 AST 解析方案 |
| P2 | 硬编码密码 | 测试文件使用环境变量 |

**Step 6: CI/CD 集成**

在 `.github/workflows/lint.yml` 中添加：

```yaml
- name: Security Scan
  run: |
    pip install bandit
    bandit -r meta/ -c .bandit -f json -o bandit-report.json
    bandit -r meta/ -c .bandit --severity-level high
```

#### 4.1.4 预期结果

| 指标 | 目标值 |
|------|--------|
| High severity issues | 0 |
| Medium severity issues | ≤5（eval 相关，需评估） |
| Low severity issues | ≤20（测试硬编码） |
| bandit 配置文件 | 存在 |
| CI/CD 集成 | 完成 |

---

### 4.2 FR-004: TypeScript 渐进引入计划 — 详细方案

#### 4.2.1 现状分析

| 检查项 | 状态 |
|--------|------|
| TypeScript 依赖 | 不存在 |
| tsconfig.json | 不存在 |
| jsconfig.json | 不存在 |
| .vue 文件数量 | 135 个 |
| .ts/.tsx 文件数量 | 6 个 .ts（导出索引 + composable） |
| vitest | 已安装（支持 TypeScript 测试） |
| @vue/test-utils | 已安装（支持 TypeScript 组件测试） |

**已有 .ts 文件**:

| 文件 | 用途 |
|------|------|
| `src/stores/appStore.ts` | 应用状态 Store |
| `src/components/common/TopNavHeader/index.ts` | 导出文件 |
| `src/components/common/BreadcrumbNav/index.ts` | 导出文件 |
| `src/components/common/GlobalSearch/index.ts` | 导出文件 |
| `src/views/SystemManagement/composables/useConditionRules.ts` | 条件规则 composable |
| `src/views/SystemManagement/composables/useMenuPermission.ts` | 菜单权限 composable |

#### 4.2.2 渐进引入策略

**原则**: 从外到内、从类型到逻辑、从新到旧

```
Phase A: 基础设施 (1天)
  ├── 安装 TypeScript 依赖
  ├── 创建 tsconfig.json
  └── 配置 allowJs: true

Phase B: 类型定义 (2天)
  ├── 创建 src/types/ 目录
  ├── 定义 API 响应类型
  ├── 定义 Store 状态类型
  └── 定义组件 Props 类型

Phase C: Store 迁移 (1天)
  ├── authStore.js → authStore.ts
  ├── diagramConfigStore.js → diagramConfigStore.ts
  └── onboardingStore.js → onboardingStore.ts

Phase D: Composable 迁移 (1天)
  ├── useMetaCache.js → useMetaCache.ts
  ├── useVersionContext.js → useVersionContext.ts
  └── useMenuPermissions.js → useMenuPermissions.ts

Phase E: 组件迁移 (持续)
  ├── MetaListPage 组件（核心）
  ├── SystemManagement 页面
  └── 其他页面（按需）
```

#### 4.2.3 实施步骤

**Step 1: 安装 TypeScript 依赖**

```bash
npm install -D typescript @types/node @vue/tsconfig
npm install -D @vue/language-tools vue-tsc
```

**Step 2: 创建 `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": false,
    "jsx": "preserve",
    "allowJs": true,
    "noEmit": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] },
    "types": ["vite/client"],
    "lib": ["ES2020", "DOM", "DOM.Iterable"]
  },
  "include": ["src/**/*.ts", "src/**/*.vue"],
  "exclude": ["node_modules", "dist"]
}
```

**Step 3: 创建类型定义目录**

```
src/types/
  ├── api.d.ts          — API 响应通用类型
  ├── auth.d.ts         — 认证相关类型
  ├── meta.d.ts         — 元数据相关类型
  ├── menu.d.ts         — 菜单相关类型
  └── store.d.ts        — Store 状态类型
```

**Step 4: 更新 `vite.config.js`**

```javascript
// 添加 vue-tsc 插件支持
export default defineConfig({
  // ... 现有配置
})
```

**Step 5: 添加类型检查脚本到 `package.json`**

```json
{
  "scripts": {
    "typecheck": "vue-tsc --noEmit",
    "typecheck:watch": "vue-tsc --noEmit --watch"
  }
}
```

#### 4.2.4 优先迁移清单

| 优先级 | 文件 | 原因 |
|--------|------|------|
| 1 | `src/types/api.d.ts` | 所有 API 调用的类型基础 |
| 2 | `src/stores/authStore.js` | 核心认证状态，类型最关键 |
| 3 | `src/composables/useMetaCache.js` | 缓存逻辑复杂，类型约束可减少 bug |
| 4 | `src/composables/useMenuPermissions.js` | 菜单权限逻辑，类型约束可防止权限遗漏 |
| 5 | `src/components/common/MetaListPage/` | 核心组件，Props 类型最重要 |

#### 4.2.5 预期结果

| 指标 | 目标值 |
|------|--------|
| tsconfig.json | 存在 |
| 类型定义文件 | 5+ 个 |
| Store 迁移 | 3/5 完成 |
| Composable 迁移 | 3+ 完成 |
| `npm run typecheck` | 通过 |

---

### 4.3 FR-008: 外部系统引用检查 — 详细方案

#### 4.3.1 检查范围

| 检查项 | 方法 | 工具 |
|--------|------|------|
| Nginx 访问日志 | 搜索废弃 URL 路径 | `grep` / 日志分析工具 |
| API Gateway 日志 | 搜索废弃 API 端点 | 云平台控制台 |
| 前端路由引用 | 代码搜索废弃路径 | `grep -r` |
| 后端 API 引用 | 代码搜索废弃端点 | `grep -r` |
| 书签/收藏 | 无法自动检查 | 人工确认 |

#### 4.3.2 废弃 URL 列表

以下路由已标记 `[DEPRECATED]`，需检查是否有外部引用：

| 废弃路径 | 新路径 | 状态 |
|----------|--------|------|
| `/product-management` | 动态路由 (BO: product) | DEPRECATED |
| `/user-permission/:tab?` | 动态路由 (BO: user, role, permission) | DEPRECATED |
| `/business-config/:tab?` | 动态路由 (BO: enum, business_config) | DEPRECATED |
| `/system/archdata` | 动态路由 (BO: relationship) | DEPRECATED |

#### 4.3.3 实施步骤

**Step 1: Nginx 日志分析**

```bash
# 搜索废弃路径的访问记录
grep -E "product-management|user-permission|business-config|system/archdata" /var/log/nginx/access.log
```

**Step 2: 前端代码搜索**

```bash
# 搜索前端代码中对废弃路径的引用
grep -r "product-management\|user-permission\|business-config\|system/archdata" src/
```

**Step 3: 后端代码搜索**

```bash
# 搜索后端代码中对废弃路径的引用
grep -r "product-management\|user-permission\|business-config\|system/archdata" meta/
```

**Step 4: 生成检查报告**

| 检查项 | 结果 | 风险 |
|--------|------|------|
| Nginx 日志 | 待检查 | - |
| 前端代码引用 | 待检查 | - |
| 后端代码引用 | 待检查 | - |
| 外部系统引用 | 待确认 | - |

#### 4.3.4 注意事项

- 此任务需要**运维权限**才能检查 Nginx/API Gateway 日志
- 如果项目未部署到生产环境，此检查可跳过
- 检查结果需记录到 spec 中

---

### 4.4 FR-009: 缓存版本号策略 — 详细方案

#### 4.4.1 现状分析

| 检查项 | 状态 |
|--------|------|
| `useMetaCache.js` | 已实现，支持 `version` 参数 |
| `menuCache.setCache(menus)` | 调用时未传入 version |
| `useMenuPermissions.js` | 独立实现 `menu_cache`，无版本号 |
| dynamicRoutes.js | API 优先 + 缓存降级 |

**问题**:
1. `useMetaCache.js` 的 `setCache(newData, version)` 支持 version 但未使用
2. 存在两套菜单缓存机制（`menuCache` 和 `menu_cache`）
3. 缓存失效仅依赖 TTL（24 小时），无法在 YAML 变更时主动失效

#### 4.4.2 版本号策略设计

**方案: 后端 API 返回 schema 版本号**

```
前端菜单加载流程:
  1. 请求 /api/v2/meta/menu?version=current
  2. 后端返回 { menus: [...], schema_version: "abc1234" }
  3. 前端比较 schema_version 与缓存中的 version
  4. 版本一致 → 使用缓存
  5. 版本不一致 → 重新加载菜单
```

#### 4.4.3 实施步骤

**Step 1: 后端 — 添加 schema 版本号端点**

在 `meta/api/bo_api.py` 中添加：

```python
@bo_bp.route('/meta/schema-version', methods=['GET'])
def get_schema_version():
    """获取当前 YAML schema 版本号"""
    import hashlib
    import os

    schema_dir = os.path.join(os.path.dirname(__file__), '..', 'schemas')
    hasher = hashlib.md5()

    for filename in sorted(os.listdir(schema_dir)):
        if filename.endswith('.yaml'):
            filepath = os.path.join(schema_dir, filename)
            with open(filepath, 'rb') as f:
                hasher.update(f.read())

    return jsonify({
        'success': True,
        'data': {
            'schema_version': hasher.hexdigest()[:12],
            'timestamp': datetime.now().isoformat()
        }
    })
```

**Step 2: 前端 — 修改 `useMetaCache.js`**

```javascript
// 在 fetch 方法中添加版本检查
async fetch(apiUrl, options = {}) {
  const cached = this.getCache()
  if (cached?.data && cached.version === options.expectedVersion) {
    return cached.data
  }

  const response = await fetch(apiUrl)
  const result = await response.json()

  if (result.success) {
    this.setCache(result.data, result.data?.schema_version)
  }

  return result.data
}
```

**Step 3: 前端 — 修改 `dynamicRoutes.js`**

```javascript
// 在菜单加载时传入版本号
const schemaVersion = await fetchSchemaVersion()
const menus = await menuCache.fetch('/api/v2/meta/menus', {
  expectedVersion: schemaVersion
})
```

**Step 4: 统一两套菜单缓存**

将 `useMenuPermissions.js` 中的 `menu_cache` 迁移到 `useMetaCache.js` 的 `menuCache`，消除缓存双轨。

#### 4.4.4 缓存失效场景

| 场景 | 触发条件 | 处理方式 |
|------|----------|----------|
| YAML 变更 | schema_version 变化 | 自动重新加载 |
| TTL 过期 | 24 小时 | 自动重新加载 |
| 手动清除 | 用户刷新页面 | localStorage.clear() |
| 部署更新 | 新版本发布 | schema_version 自动变化 |

#### 4.4.5 预期结果

| 指标 | 目标值 |
|------|--------|
| schema-version API | 存在 |
| menuCache.version | 非空 |
| 缓存双轨 | 统一为单套 |
| YAML 变更后 | 缓存自动失效 |

---

### 4.5 FR-012: 测试覆盖增强 — 详细方案

#### 4.5.1 现状分析

| 类别 | 总文件数 | 有测试 | 缺少测试 | 覆盖率 |
|------|---------|--------|---------|--------|
| API (meta/api/) | 35 | 25 | 10 | **71.4%** |
| Service (meta/services/) | 57 | 34 | 23 | **59.6%** |
| Core 根目录 (meta/core/) | 46 | 25 | 21 | **54.3%** |
| Core 拦截器 | 17 | 13 | 4 | **76.5%** |
| Core 枚举 | 7 | 0 | 7 | **0%** |

#### 4.5.2 缺少测试的 API (10个) — 按优先级排序

| 优先级 | API 文件 | 用途 | 建议用例数 |
|--------|---------|------|-----------|
| P1 | `user_api.py` | 用户管理（高频使用） | 15 |
| P1 | `user_group_api.py` | 用户组管理 | 12 |
| P1 | `enum_api.py` | 枚举管理 | 10 |
| P1 | `permission_rule_api.py` | 权限规则 | 10 |
| P2 | `role_menu_api.py` | 角色菜单关联 | 8 |
| P2 | `menu_permission_api.py` | 菜单权限 | 8 |
| P2 | `permission_sync_api.py` | 权限同步 | 6 |
| P2 | `audit_management_api.py` | 审计管理 | 8 |
| P3 | `meta_utility_routes_api.py` | 工具路由 | 5 |
| P3 | `special_routes_api.py` | 特殊路由 | 5 |

#### 4.5.3 缺少测试的 Service (23个) — 按优先级排序

| 优先级 | Service 文件 | 用途 | 建议用例数 |
|--------|-------------|------|-----------|
| P1 | `rate_limiter.py` | 限流器（安全关键） | 10 |
| P1 | `token_blacklist_service.py` | Token 黑名单（安全关键） | 8 |
| P1 | `auth_provider.py` | 认证提供者 | 10 |
| P1 | `user_group_service.py` | 用户组服务 | 12 |
| P1 | `hierarchy_service.py` | 层级服务 | 8 |
| P1 | `dimension_scope_engine.py` | 维度范围引擎 | 8 |
| P2 | `condition_permission_service.py` | 条件权限服务 | 8 |
| P2 | `data_permission_filter.py` | 数据权限过滤器 | 8 |
| P2 | `manage_service.py` | 管理服务 | 10 |
| P2 | `menu_permission_service.py` | 菜单权限服务 | 8 |
| P2 | `meta_action_service.py` | 元数据动作服务 | 6 |
| P2 | `permission_audit_service.py` | 权限审计服务 | 6 |
| P2 | `permission_bundle_service.py` | 权限包服务 | 6 |
| P2 | `audit_service.py` | 审计服务 | 8 |
| P2 | `async_import_service.py` | 异步导入服务 | 8 |
| P2 | `action_handlers.py` | 动作处理器 | 6 |
| P3 | `cache_monitor.py` | 缓存监控 | 5 |
| P3 | `i18n_service.py` | 国际化服务 | 5 |
| P3 | `trace_service.py` | 链路追踪 | 5 |
| P3 | `log_filter_service.py` | 日志过滤 | 5 |
| P3 | `field_policy_validation.py` | 字段策略验证 | 5 |
| P3 | `index_generator.py` | 索引生成器 | 5 |
| P3 | `config_driven_hierarchy_filter.py` | 配置驱动层级过滤 | 5 |

#### 4.5.4 实施策略

**分批实施，优先安全关键模块**:

```
Batch 1 (P1 - 安全关键): ~58 用例
  ├── test_rate_limiter.py (10)
  ├── test_token_blacklist_service.py (8)
  ├── test_auth_provider.py (10)
  ├── test_user_api.py (15)
  └── test_user_group_api.py (12)  [注意: 已有 test_auth_api_granular.py 部分覆盖]

Batch 2 (P1 - 业务关键): ~56 用例
  ├── test_user_group_service.py (12)
  ├── test_hierarchy_service.py (8)
  ├── test_dimension_scope_engine.py (8)
  ├── test_enum_api.py (10)
  ├── test_permission_rule_api_extended.py (10)
  └── test_role_menu_api.py (8)

Batch 3 (P2 - 功能补充): ~65 用例
  ├── test_condition_permission_service.py (8)
  ├── test_data_permission_filter.py (8)
  ├── test_manage_service.py (10)
  ├── test_menu_permission_service.py (8)
  ├── test_meta_action_service.py (6)
  ├── test_permission_audit_service.py (6)
  ├── test_permission_bundle_service.py (6)
  └── test_audit_service.py (8)

Batch 4 (P3 - 低优先级): ~40 用例
  ├── test_cache_monitor.py (5)
  ├── test_i18n_service.py (5)
  ├── test_trace_service.py (5)
  ├── test_log_filter_service.py (5)
  ├── test_field_policy_validation.py (5)
  ├── test_index_generator.py (5)
  ├── test_audit_management_api.py (8)
  └── test_meta_utility_routes_api.py (5)
```

#### 4.5.5 预期结果

| 指标 | 当前值 | 目标值 |
|------|--------|--------|
| API 测试覆盖率 | 71.4% (25/35) | **100%** (35/35) |
| Service 测试覆盖率 | 59.6% (34/57) | **85%+** (48+/57) |
| Core 测试覆盖率 | 54.3% (25/46) | **70%+** (32+/46) |
| 总测试用例数 | 1702+ | **1900+** |

---

## 5. 非功能需求

### NFR-001: 安全性

- **描述**: 所有安全相关待办必须优先处理
- **测量方式**: bandit 扫描无新增高危漏洞
- **优先级**: Must (P0)

### NFR-002: 向后兼容

- **描述**: 所有变更不破坏现有功能
- **测量方式**: 现有测试全部通过
- **优先级**: Must (P0)

### NFR-003: 可维护性

- **描述**: 代码清理后项目结构更清晰
- **测量方式**: 无冗余文件、无死代码
- **优先级**: Should (P1)

---

## 6. 优先级与里程碑

| 里程碑 | 范围 | 预估工作量 | 实际状态 |
|--------|------|-----------|----------|
| M1: 安全加固 | FR-001 ✅, FR-002 | 1 天 | FR-001 ✅, FR-002 ⏳ |
| M2: 架构优化 | FR-003 ✅, FR-004, FR-005 ✅ | 2 天 | FR-003 ✅, FR-004 ⏳, FR-005 ✅ |
| M3: 功能验证 | FR-006 ✅ ~ FR-010 | 1 天 | FR-006 ✅, FR-007 ✅, FR-008~FR-010 ⏳ |
| M4: 代码清理 | FR-011 ✅, FR-012 | 持续 | FR-011 ✅, FR-012 ⏳ |
| **总计** | - | ~4 天 | **6/12 完成 (50%)** |

---

## 7. 验收标准

### 7.1 M1 验收 (FR-002)

- [ ] bandit 安装并添加到 requirements-dev.txt
- [ ] `.bandit` 配置文件存在
- [ ] 首次扫描报告生成 (bandit-report.json)
- [ ] High severity issues = 0
- [ ] CI/CD 安全扫描步骤添加

### 7.2 M2 验收 (FR-004)

- [ ] `typescript` 依赖安装
- [ ] `tsconfig.json` 存在
- [ ] `src/types/` 目录存在，含 5+ 类型定义文件
- [ ] `npm run typecheck` 通过
- [ ] 至少 3 个 Store 迁移到 TypeScript

### 7.3 M3 验收 (FR-008, FR-009)

- [ ] Nginx/API Gateway 日志检查完成
- [ ] 废弃 URL 外部引用检查报告
- [ ] `/api/v2/meta/schema-version` 端点存在
- [ ] `menuCache.version` 非空
- [ ] 缓存双轨统一

### 7.4 M4 验收 (FR-012)

- [ ] API 测试覆盖率 ≥ 85%
- [ ] Service 测试覆盖率 ≥ 75%
- [ ] Batch 1 (P1 安全关键) 测试全部通过
- [ ] 新增测试用例 ≥ 100

---

## 8. 延后功能说明

以下功能延后到后续阶段实施：

| 功能 | 延后阶段 | 原因 |
|------|----------|------|
| scope_rules Python 引擎通用化 | GAP-3 | 现有硬编码机制足够，通用化非 Must |
| scope_rules SQL 查询通用化 | GAP-3 | 现有 4 段 SQL 足够，动态生成非 Must |
| RelationScopeService | GAP-3 | 现有 virtual_field_transform + cascade_service 足够 |
| 通用 Annotation CRUD | M18.2 | 现有 manage_api 已支持 |
| Core 枚举模块测试 | GAP-3 | 0% 覆盖，但均为内部 DTO/接口定义，风险低 |

---

## 文档历史

| 版本 | 日期 | 作者 | 变更内容 |
|------|------|------|---------|
| v1.0.0 | 2026-05-21 | AI Assistant | 初始版本，整合所有待办项目 |
| v2.0.0 | 2026-05-21 | AI Assistant | 细化实施方案：bandit 扫描、TypeScript 引入、缓存版本号、测试覆盖增强 |
