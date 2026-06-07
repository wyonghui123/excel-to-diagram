# Spec: 权限体系自动化测试框架

---

## 1. 背景与目标

### 1.1 背景

当前系统实现了完整的 RBAC 权限体系，覆盖：
- **菜单权限**：不同角色看到不同菜单项（前端 Vue + Pinia AuthStore）
- **功能权限**：基于角色-权限的 API 端点访问控制（`PermissionService.check_permission_unified`）
- **数据权限**：实例级（`DataPermissionInterceptor` SQL 注入） + 条件型（`ConditionPermissionService`）

但自动化测试覆盖不足：
- 现有 `test_auth_permission.py` 主要覆盖认证流程，未系统化测试授权矩阵
- 现有 `test_permission_unified_semantic.py` 覆盖统一语义权限，但未包含数据权限
- 缺少菜单权限的 UI 层测试
- 缺少越权测试（IDOR / 垂直越权）
- 缺少权限包的测试

架构已稳定（`user → user_group → role` 单一模型），现在需要补齐权限测试体系。

### 1.2 业务目标

- **安全回归保障**：任何权限变更后，自动化测试能在 5 分钟内给出完整回归结果
- **可审计性**：权限矩阵本身可作为权限审计文档，QA/Security 可直接阅读
- **零配置运行**：测试脚本自动创建所需数据，不依赖预置环境

### 1.3 用户/涉众目标

| 涉众 | 目标 |
|------|------|
| 开发者 | 修改权限逻辑后 `python test.py --file` 快速验证 |
| QA | 可阅读权限矩阵 DSL，确认覆盖完整 |
| 安全审计 | 越权测试覆盖率可量化报告 |

---

## 2. 需求类型概览

| 类型 | 适用 | 依据 |
|------|------|------|
| 业务需求 | 是 | 权限回归保障、可审计性 |
| 用户/涉众需求 | 是 | 开发者/QA/安全审计角色 |
| 解决方案需求 | 是 | 权限矩阵 + 数据范围验证器 |
| 功能需求 | 是 | FR-001 ~ FR-012 |
| 非功能需求 | 是 | NFR-001 ~ NFR-003 |
| 外部接口需求 | 是 | MCP Playwright 集成 |
| 迁移需求 | 否 | 新建设施，无迁移 |

---

## 3. 功能需求

### 3.1 菜单权限测试（MCP / E2E 层）

#### FR-001: 多角色菜单可见性验证

- **描述**: 系统 MUST 支持以不同角色登录后，验证前端菜单树的可见性
- **验收标准**:
  - admin 角色看到完整菜单（所有菜单项）
  - viewer 角色只看到 viewer 权限范围内的菜单项
  - 未登录用户看到登录页而非菜单
  - 验证方式：MCP Playwright 截图 + DOM 断言
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 用户确认 - 菜单权限需要前端 UI 验证

#### FR-002: 路由守卫验证

- **描述**: 系统 MUST 验证低权限用户直接输入高权限 URL 时被路由守卫拦截
- **验收标准**:
  - viewer 直接访问 `/admin` 被重定向
  - viewer 直接访问无权限对象详情页被拒绝
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业最佳实践 - 防止 URL 直接访问绕过权限

### 3.2 功能权限测试（API 集成测试层）

#### FR-003: 权限矩阵声明式定义

- **描述**: 系统 MUST 提供声明式权限矩阵 DSL，格式为 `[method, endpoint, {role: expected_status}]`
- **验收标准**:
  - 矩阵作为 Python 数据结构定义，非技术角色可读
  - 矩阵覆盖所有 BO API 端点类型（product, version, domain, business_object, relationship, user, role, user_group）
  - 矩阵包含匿名用户、viewer、editor、admin 四种角色的预期结果
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业最佳实践 - 声明式权限矩阵

#### FR-004: 权限矩阵参数化测试

- **描述**: 系统 MUST 将权限矩阵展开为 pytest 参数化测试，每个 `[角色, 端点, 方法]` 组合生成独立测试用例
- **验收标准**:
  - 每个组合执行真实 HTTP 请求（非 mock）
  - 验证状态码与矩阵预期一致
  - 失败时输出清晰的错误信息：`{role} {method} {endpoint} → expected {expected}, got {actual}`
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业最佳实践 - 参数化权限测试

#### FR-005: 正负向双重覆盖

- **描述**: 每个端点 × 每个角色 × 每个方法的测试必须同时验证"允许"和"禁止"两种场景
- **验收标准**:
  - 有权限的用户能成功操作（200/201）
  - 无权限的用户被拒绝（403 Forbidden）
  - 未登录用户被拒绝（401 Unauthorized）
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业最佳实践 - Default Deny 原则

#### FR-006: 权限分配链路测试

- **描述**: 系统 MUST 验证 `user → user_group → role → permissions` 完整链路
- **验收标准**:
  - 创建 user、user_group、role、permission 四层对象
  - 验证 role 获取正确的 permissions
  - 验证 user 通过 user_group 继承正确的 permissions
  - 验证移除 user_group 关联后权限消失
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 架构决策 - 单一用户组模型

### 3.3 数据权限测试（API 集成测试层）

#### FR-007: 实例级数据隔离（行级安全）

- **描述**: 系统 MUST 验证 DataPermissionInterceptor 正确过滤数据，不同角色看到不同范围的数据
- **验收标准**:
  - admin 看到全部数据
  - viewer 只能看到授权的数据范围
  - 两个 viewer 用户各自创建的数据互相不可见
  - 列表查询的数量、分页、搜索均符合数据范围
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业最佳实践 - 行级安全测试

#### FR-008: 水平越权检测（IDOR）

- **描述**: 系统 MUST 验证用户 A 无法通过修改资源 ID 访问用户 B 的资源
- **验收标准**:
  - 用户A创建BO → 用户B尝试 GET/PUT/DELETE 该BO → 返回 403 或 404
  - 用户A创建关系 → 用户B尝试修改该关系 → 返回 403
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业最佳实践 - IDOR 防护测试

#### FR-009: 垂直越权检测

- **描述**: 系统 MUST 验证普通用户无法通过修改请求参数执行管理员操作
- **验收标准**:
  - viewer 尝试 POST 创建对象 → 403
  - editor 尝试 DELETE 对象 → 403（如 editor 无删除权限）
  - 尝试在请求体中注入 role_id 等权限字段 → 拒绝或忽略
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 行业最佳实践 - 垂直越权防护测试

#### FR-010: 条件型数据权限

- **描述**: 系统 MUST 验证 `ConditionPermissionService` 基于规则的条件过滤正确生效
- **验收标准**:
  - 创建条件规则（如 "只看到自己创建的BO"）
  - 验证查询结果只包含符合条件的数据
  - 验证规则更新后过滤结果正确变化
  - 验证 "拒绝规则"（is_denied）优先级高于允许规则
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 用户确认 - 条件型数据权限是基础核心功能

### 3.4 测试基础设施

#### FR-011: 自动数据工厂

- **描述**: 系统 MUST 提供自动数据工厂，测试脚本自行创建/清理测试数据
- **验收标准**:
  - `create_test_user(role_name)` 创建带完整权限链路的测试用户
  - `create_test_resource()` 创建带标准配置的测试资源
  - 所有测试数据在 teardown 中自动清理
  - 测试不依赖预置数据库状态
- **优先级**: Must
- **类型映射**: 功能需求
- **来源**: 用户确认 - 测试脚本创建临时数据

#### FR-012: 权限测试报告

- **描述**: 系统 MUST 生成权限覆盖报告，清晰的通过/失败统计
- **验收标准**:
  - 报告包含：角色覆盖矩阵、端点覆盖矩阵、数据权限覆盖矩阵
  - 失败用例输出详细上下文（角色、端点、预期/实际状态码）
- **优先级**: Should
- **类型映射**: 功能需求
- **来源**: 质量属性 - 可观测性

---

## 4. 非功能需求

### NFR-001: 性能

- **描述**: 权限矩阵完整测试（~200个用例）在串行模式下应在 3 分钟内完成
- **度量**: 单次测试运行时间
- **优先级**: Should

### NFR-002: 可靠性

- **描述**: 测试不依赖外部状态，可重复运行
- **度量**: 连续 10 次运行结果一致（无 flaky 测试）
- **优先级**: Must

### NFR-003: 隔离性

- **描述**: 每个测试类的数据不互相干扰
- **度量**: 测试运行顺序不影响结果
- **优先级**: Must

---

## 5. 外部接口需求

### IF-001: MCP Playwright 集成（菜单权限测试）

- **类型**: 外部工具集成
- **入口**: MCP Playwright Agent（已有）
- **交互**:
  - 调用 `browser_create_instance` 创建浏览器
  - 调用 `browser_navigate` 导航到登录页
  - 模拟不同角色登录
  - 验证菜单项可见性（DOM 断言 + 截图）
- **错误处理**: MCP 会话超时时自动重试
- **来源**: 用户确认 - 菜单权限使用 MCP

### IF-002: 权限测试脚本入口

- **类型**: CLI 入口
- **入口**: `python test.py --file test_helpers/scripts/test_permission_system.py`
- **交互**: 遵循现有 `test.py` 规范，支持 `--file` 参数
- **来源**: 项目规范 - pytest 铁律

---

## 6. 迁移需求

不适用。这是新建设施，无迁移需求。

---

## 7. 约束与假设

### 7.1 技术约束

- 必须遵循 pytest 铁律：通过 `python test.py --file` 入口运行
- 菜单测试使用已有 MCP 基础设施（无需重新部署）

### 7.2 业务约束

- 权限模型已确定为 `user → user_group → role` 单一模型
- 权限包（permission_bundle）测试列入待议，不在本次范围

### 7.3 假设

- 前端服务正常运行（通过 service_manager 管理）— 已验证
- MCP Playwright 工具可用 — 已验证
- 测试用角色配置与实际生产角色配置一致 — 由权限矩阵 DSL 保证

---

## 8. 优先级与里程碑建议

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-003 | 权限矩阵 DSL | Must | 基础设施，后续依赖 |
| FR-011 | 自动数据工厂 | Must | 基础设施，后续依赖 |
| FR-004 | 权限矩阵参数化测试 | Must | 核心交付 |
| FR-005 | 正负向双重覆盖 | Must | 核心交付 |
| FR-006 | 权限分配链路 | Must | 核心交付 |
| FR-007 | 实例级数据隔离 | Must | 核心交付 |
| FR-008 | 水平越权 IDOR | Must | 核心交付 |
| FR-009 | 垂直越权 | Must | 核心交付 |
| FR-010 | 条件型数据权限 | Must | 核心交付 |
| FR-001 | 菜单可见性 MCP | Must | 核心交付 |
| FR-002 | 路由守卫 | Must | 核心交付 |
| FR-012 | 权限测试报告 | Should | 质量提升 |

**建议里程碑：**

| 里程碑 | 范围 | 产出 |
|--------|------|------|
| M1 - 基础设施 | FR-003, FR-011 | 权限矩阵 DSL + 数据工厂 |
| M2 - 功能权限 | FR-004, FR-005, FR-006 | 功能权限矩阵全覆盖 |
| M3 - 数据权限 | FR-007, FR-008, FR-009, FR-010 | 数据权限 + 越权测试 |
| M4 - 菜单权限 | FR-001, FR-002 | MCP 菜单可见性测试 |
| M5 - 报告 | FR-012 | 权限测试覆盖率报告 |

---

## 9. 变更/设计方案 (RFC)

### 9.1 As-Is 分析

**当前权限体系架构：**

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Vue + Pinia)                     │
│  AuthStore: userInfo.roles/permissions → 菜单 + 按钮     │
├─────────────────────────────────────────────────────────┤
│                    后端 API 层                            │
│  auth_api.py: 登录/登出/SSO                               │
│  role_api.py: 角色 CRUD + 用户分配（通过用户组）           │
│  user_api.py: 用户角色管理（通过用户组）                   │
│  bo_api.py: BO CRUD（权限拦截）                           │
├─────────────────────────────────────────────────────────┤
│                    权限服务层                              │
│  permission_service.py: 功能权限（user→group→role）       │
│  data_permission_service.py: 实例级数据权限               │
│  condition_permission_service.py: 条件型数据权限          │
│  DataPermissionInterceptor: SQL 注入过滤                  │
│  StandardActionLoader: 统一语义动作                       │
├─────────────────────────────────────────────────────────┤
│                    数据层                                  │
│  users → user_group_members → user_groups → group_roles  │
│  → roles → role_permissions → permissions                │
│  user_data_permissions / permission_rules                 │
└─────────────────────────────────────────────────────────┘
```

**当前测试覆盖：**

| 测试文件 | 覆盖范围 | 缺口 |
|----------|---------|------|
| `test_auth_permission.py` | 认证流程 | 未覆盖授权矩阵 |
| `test_permission_unified_semantic.py` | 统一语义权限 | 未覆盖数据权限 |
| `test_data_permission*.py` | 数据权限基础 | 未覆盖越权检测 |
| 无 | 菜单权限 | 完全缺失 |

### 9.2 目标状态

**新增测试基础设施：**

```
test_helpers/
├── scripts/
│   └── test_permission_system.py    # 主入口
├── permission_matrix.py             # 权限矩阵 DSL
├── permission_fixtures.py           # 测试数据工厂
└── permission_verifier.py           # 权限验证器
```

**测试分层架构：**

```
┌──────────────────────────────────────────┐
│  MCP 层 (菜单权限)                         │
│  ├── 多角色登录 → 验证菜单可见性            │
│  └── 路由守卫 → 验证直接 URL 访问拦截       │
├──────────────────────────────────────────┤
│  API 集成层 (功能 + 数据权限)              │
│  ├── 权限矩阵: [role×endpoint×method]      │
│  ├── 权限链路: user→group→role 完整链路    │
│  ├── 数据权限: 行级安全 + IDOR + 垂直越权  │
│  └── 条件权限: 规则过滤 + deny 优先级      │
├──────────────────────────────────────────┤
│  基础设施层                                │
│  ├── 自动数据工厂: create_test_user/resource│
│  └── 权限验证器: 结果比对 + 报告生成        │
└──────────────────────────────────────────┘
```

**关键变更：**

1. 新增 `permission_matrix.py` — 声明式权限矩阵，作为测试和文档的单一数据源
2. 新增 `permission_fixtures.py` — 测试数据工厂，自动创建/清理
3. 新增 `test_permission_system.py` — 主测试入口，整合所有权限测试
4. MCP 菜单测试 — 利用已有 MCP 基础设施验证前端菜单

### 9.3 详细设计

#### 9.3.1 权限矩阵 DSL 设计

```python
# permission_matrix.py

# ── 角色定义 ──
# 每个角色对应一组权限编码（符合 StandardActionLoader 格式）
TEST_ROLES = {
    'viewer': {
        'display_name': '查看者',
        'group_name': 'test_group_viewer',
        'permissions': [
            'product:read', 'version:read', 'domain:read',
            'business_object:read', 'relationship:read',
        ],
    },
    'editor': {
        'display_name': '编辑者',
        'group_name': 'test_group_editor',
        'permissions': [
            'product:read', 'product:create', 'product:update',
            'version:read', 'version:create', 'version:update',
            'domain:read', 'domain:create', 'domain:update',
            'business_object:read', 'business_object:create', 'business_object:update',
            'relationship:read', 'relationship:create',
        ],
    },
    'admin': {
        'display_name': '管理员',
        'group_name': 'test_group_admin',
        'permissions': ['*'],
    },
}

# ── 功能权限矩阵 ──
# 格式: (method, endpoint_fragment, body_generator, role_expectations)
FUNC_PERMISSION_MATRIX = [
    # 产品线
    ('GET',    'product',           None,  {'anonymous': 401, 'viewer': 200, 'editor': 200, 'admin': 200}),
    ('POST',   'product',           lambda: {'code': f'PERM_TEST_PROD_{int(time.time())}', 'name': '权限测试产品'},  
                                           {'anonymous': 401, 'viewer': 403, 'editor': 200, 'admin': 200}),
    ('PUT',    'product/{id}',      lambda: {'name': '权限测试产品(改)'},
                                           {'anonymous': 401, 'viewer': 403, 'editor': 200, 'admin': 200}),
    ('DELETE', 'product/{id}',      None,  {'anonymous': 401, 'viewer': 403, 'editor': 403, 'admin': 200}),

    # 版本
    ('GET',    'version',           None,  {'anonymous': 401, 'viewer': 200, 'editor': 200, 'admin': 200}),
    ('POST',   'version',           lambda product_id: {'product_id': product_id, 'code': f'PERM_TEST_VER_{int(time.time())}', 'name': '权限测试版本'},
                                           {'anonymous': 401, 'viewer': 403, 'editor': 200, 'admin': 200}),
    ...

    # 用户管理 (admin only)
    ('GET',    'user',              None,  {'anonymous': 401, 'viewer': 403, 'editor': 403, 'admin': 200}),
    ('POST',   'user',              lambda: {'username': f'permtest_{int(time.time())}', 'password': 'Test@123', 'display_name': '权限测试用户'},
                                           {'anonymous': 401, 'viewer': 403, 'editor': 403, 'admin': 200}),
    ...
]
```

#### 9.3.2 测试数据工厂设计

```python
# permission_fixtures.py

class PermissionTestFixture:
    """自动管理权限测试数据的工厂类"""
    
    def __init__(self, base_url: str = 'http://localhost:3010'):
        self.base_url_bo = f'{base_url}/api/v2/bo'
        self.base_url_auth = f'{base_url}/api/v1'
        self.session = requests.Session()
        self.created = defaultdict(list)  # 跟踪创建的资源
    
    def setup_permission_chain(self, role_name: str, permissions: List[str]) -> Dict:
        """创建完整的权限链路并返回认证信息"""
        # 1. 创建 permissions
        # 2. 创建 role + 绑定 permissions  
        # 3. 创建 user_group + 绑定 role
        # 4. 创建 user + 绑定 user_group
        # 5. 登录获取 token
        return {
            'user_id': user_id,
            'username': username,
            'token': token,
            'role_name': role_name,
        }
    
    def create_test_resource(self, resource_type: str, **kwargs) -> int:
        """创建测试资源并记录 ID"""
        ...
    
    def cleanup(self):
        """逆序清理所有创建的资源"""
        ...
```

#### 9.3.3 测试主流程

```python
# test_permission_system.py

class PermissionSystemTest:
    
    def run_all_tests(self):
        """主测试入口"""
        # Phase 1: 基础设施
        self.test_setup_fixtures()          # 创建权限链路
        self.test_cleanup_teardown()        # 验证清理机制
        
        # Phase 2: 功能权限矩阵
        self.test_functional_permission_matrix()  # 参数化全覆盖
        
        # Phase 3: 数据权限
        self.test_data_isolation()          # 实例级隔离
        self.test_idor_horizontal()         # 水平越权
        self.test_vertical_escalation()     # 垂直越权
        self.test_condition_permission()    # 条件型数据权限
        
        # Phase 4: 权限链路
        self.test_permission_chain_flow()   # 完整链路验证
        self.test_permission_removal()      # 权限移除验证
```

#### 9.3.4 MCP 菜单权限测试设计

```
测试场景：
1. [admin 登录] → 验证所有菜单项可见
2. [viewer 登录] → 验证只看到 viewer 权限范围内的菜单
3. [viewer 直接访问 /admin URL] → 验证被路由守卫拦截
4. [未登录访问] → 验证显示登录页

技术方案：
- 使用已有 MCP Playwright Agent
- browser_navigate → 登录 → browser_get_markdown 获取菜单结构
- 比对预期菜单项与实际菜单项
```

### 9.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| **A: 全 API 级测试** | 速度快、覆盖全 | 看不到前端菜单渲染 | 用于功能+数据权限 |
| **B: 全 Playwright E2E** | UI 全覆盖 | 慢（10x+）、维护成本高 | 仅用于菜单权限 |
| **C: 混合方案（API+MCP）** | 平衡速度与覆盖 | 需维护两套测试 | ✅ **选定** |
| **D: 只测正向（不测403）** | 用例少 | 不能证明权限真正生效 | ❌ 拒绝 |

### 9.5 实施与迁移计划

**实施顺序：**

1. **基础设施**（permission_matrix.py + permission_fixtures.py）
2. **功能权限矩阵测试**（permission_matrix 参数化测试）
3. **权限链路测试**（user→group→role 完整链路）
4. **数据权限测试**（行级安全 + IDOR + 垂直越权）
5. **条件型数据权限测试**（规则过滤）
6. **MCP 菜单权限测试**（前后端配合）

**风险缓解：**

| 风险 | 缓解策略 |
|------|---------|
| MCP 不稳定导致菜单测试 flaky | 重试机制 + fallback 截图 |
| 权限矩阵维护成本高 | DSL 设计为可读性强 + 自动端点发现 |
| 测试数据残留 | 工厂类 track 所有创建资源 + teardown 清理 |

**测试策略：**

| 层级 | 工具 | 覆盖 |
|------|------|------|
| 功能权限 | pytest + requests | 权限矩阵全覆盖 |
| 数据权限 | pytest + requests | 行级安全 + 越权 |
| 菜单权限 | MCP Playwright | 关键角色菜单 + 路由守卫 |

**回滚计划：**
- 新增文件，不影响现有代码
- 如测试不稳定，可注释掉 MCP 菜单测试，功能+数据权限测试独立运行

---

## 10. TBD 列表

| ID | 事项 | 缺失信息 | 下一步 |
|----|------|---------|--------|
| TBD-1 | 权限包测试 | permission_bundle 的合并/覆盖逻辑测试范围 | 待议，列入后续迭代 |
| TBD-2 | 权限矩阵端点自动发现 | 是否从 OpenAPI 路由自动生成端点列表 | 先手工维护矩阵，后续评估自动化 |

---

_Spec + RFC 包含 10 个章节，最后一章为 "TBD 列表"，内容完整。_
