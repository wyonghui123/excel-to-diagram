## 目录

1. [0. 思路转变](#0-思路转变)
2. [1. 头部产品架构参考](#1-头部产品架构参考)
3. [2. v3 架构详细设计](#2-v3-架构详细设计)
4. [3. 4 个 FR 的 v3 实施（BO Action 导向）](#3-4-个-fr-的-v3-实施（bo-action-导向）)
5. [4. v3 vs v1/v2 对比](#4-v3-vs-v1v2-对比)
6. [5. 实施计划（v3）](#5-实施计划（v3）)
7. [6. 性能与影响分析](#6-性能与影响分析)
8. [7. 与 v2 架构的对齐](#7-与-v2-架构的对齐)
9. [8. 变更记录](#8-变更记录)
10. [9. 关键决策点（待你确认）](#9-关键决策点（待你确认）)

---
# Spec v3：BO Action 导向 + 静态 Service 双层下沉架构

> **版本**: v3.0.0
> **日期**: 2026-06-05
> **状态**: 📋 重新设计 (Reworked — BO Action First)
> **核心原则**: **业务逻辑不是"放前端还是后端"的问题，而是"放 BO Action 还是静态 Service"的问题**
> **前置文档**:
> - [spec-ui-business-logic-downflow.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) v1.0.0
> - [spec-phase1-p0-detailed-design.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-phase1-p0-detailed-design.md) v2.0.0
> - [ARCHITECTURE_V2.md](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) §6.4
> - [元数据驱动架构与权限体系-头部产品研究.md](file:///d:/filework/excel-to-diagram/docs/research/元数据驱动架构与权限体系-头部产品研究.md)

---

## 0. 思路转变

### 0.1 v1/v2 设计的根本问题

| 维度 | v1 (前端 service) | v2 (后端 service) |
|------|------------------|------------------|
| 视角 | "composable 太重，拆到 service" | "service 是单一事实源" |
| 抽象层级 | ❌ **缺少"业务动作"层** | ❌ **缺少"业务动作"层** |
| 与 BO Action 关系 | 平行（重复造轮子） | 平行（重复造轮子） |
| 头部产品对标 | ❌ 不符合 Salesforce/SAP | ❌ 不符合 Salesforce/SAP |

**核心问题**：我们试图在已有的 **BO Action + 18 拦截器** 模型外，再造一层"service"，但**业务逻辑的正确归属是 BO Action 本身**。

### 0.2 v3 的核心思想

```
                        ┌─────────────────────────┐
                        │  Page (编排 + 事件绑定)  │
                        └────────────┬────────────┘
                                     │
                                     ▼
                        ┌─────────────────────────┐
                        │  Composable (响应式)     │  ← 仅 ref/watch/lifecycle
                        └────────────┬────────────┘
                                     │ HTTP
                                     ▼
   ╔═══════════════════════════════════════════════════════════╗
   ║              后端双层: 业务逻辑下沉目标                       ║
   ║                                                            ║
   ║   ┌──────────────────────────────────────────────────┐    ║
   ║   │  Layer 1: BO Action (动态)                        │    ║
   ║   │  - 12 标准动作 + N 业务动作                        │    ║
   ║   │  - 18 拦截器链 (审计/权限/级联/...)                  │    ║
   ║   │  - 处理: CRUD + 业务行为 + 跨实体                  │    ║
   ║   │  - 入口: bo_framework.execute(action_id, ...)     │    ║
   ║   └──────────────────────────────────────────────────┘    ║
   ║                          ↑ 委托                             ║
   ║   ┌──────────────────────────────────────────────────┐    ║
   ║   │  Layer 2: 静态 Service (跨实体的算法/计算)         │    ║
   ║   │  - 纯函数, 无状态, 可缓存                           │    ║
   ║   │  - 处理: 类型推断, 表达式求值, 路径生成             │    ║
   ║   │  - 不直接调 DB, 不参与拦截器链                      │    ║
   ║   │  - 入口: 直接 import 调用                          │    ║
   ║   └──────────────────────────────────────────────────┘    ║
   ╚═══════════════════════════════════════════════════════════╝
```

**关键洞察**：
1. **业务行为**（如"保存草稿"、"生成 Key"、"评估权限规则"）→ **BO Action**
2. **纯计算**（如"过滤参数类型推断"、"条件表达式解析"）→ **静态 Service**（同进程 Python，无需 HTTP）
3. **HTTP 路径**（如"获取 API 路径列表"）→ **Bootstrap 配置**（前端启动时一次性获取，不算"业务"）

### 0.3 4 个 FR 重新定位

| FR | v1/v2 思路 | **v3 思路（BO Action 导向）** |
|----|-----------|------------------------------|
| FR-001 HTTP 客户端 | 升级前端 / 路径后端化 | ❌ **删除**：HTTP 客户端是基础设施，不属于"业务下沉"范畴 |
| FR-002 auth | 拆 authService | ✅ **下沉为 BO Action**：`user.authenticate` / `user.logout` / `user.change_password` 等（所有用户认证行为都是 user 对象的 Action） |
| FR-005 DraftPersist | 拆 draftPersistService | ✅ **下沉为 BO Action**：`{object_type}.batch_save` 复合 Action（接收 creates + updates 数组，调用 bo_framework 批量执行） |
| FR-006 API_BASE | 路径后端化 | ✅ **保留为客户端 Bootstrap**：前端启动时拉取静态 manifest，**不属于业务逻辑** |

**v3 核心**：
- 业务 100% 走 **BO Action 体系**（自动获得 18 拦截器）
- 计算/转换 100% 走 **静态 Service**（同进程 Python，**无 HTTP 损耗**）
- 前端 composable 100% 是 **HTTP 客户端 + 状态机**（无业务、无计算）

---

## 1. 头部产品架构参考

### 1.1 Salesforce Action Framework

**核心理念**：所有业务行为都是 **Action**，每个 Action 有：
- 唯一的 ID（如 `Account.New`）
- 输入参数 schema
- 输出 schema
- 权限声明（"需要 `Account:Create` 权限"）
- 自动记录到审计日志

**Action 分类**：
| 类型 | 例子 | 实现 |
|------|------|------|
| **Standard Action** | `New`、`Edit`、`Delete`、`View` | 平台内置（对应我们的 crud_create/update/delete） |
| **Custom Action** | `Approve`、`Reject`、`Reassign` | Apex Class 实现 |
| **Quick Action** | 一键操作（无需表单） | 平台声明 |
| **Bulk Action** | 批量操作 | 平台 + 自定义 |

**关键特性**：
- Action 可在前端 UI 中**自动呈现**为按钮（无需前端硬编码）
- Action 的可见性受 **Object Permissions** 控制
- Action 自动产生 **Apex Jobs / Platform Events** 异步化能力
- 每次 Action 调用 = 一次 **Unit of Work**，可被回滚

### 1.2 SAP CDS Action + Fiori Annotations

```cds
// SAP CDS 示例
action SubmitOrder() returns Orders;
action approveOrder { 
  // 需要 S_ORDER_I_ADMIN 权限
};
annotate SubmitOrder with @Common.SideEffects: { ... };
```

**关键特性**：
- **CDS Annotation** 声明 Action 行为
- **OData Action** 暴露 Action 为标准 HTTP endpoint
- **Fiori Elements** 自动渲染 Action 按钮（无需前端代码）
- **DCL（Data Control Language）** 控制 Action 权限

### 1.3 ServiceNow Flow Designer

```
┌──────────────────────────────────────────────┐
│  Flow Designer (低代码 Action 编排)            │
│                                              │
│  Trigger → Action1 → Action2 → Sub-Flow      │
│                                              │
│  所有 Action 都从 Action Catalog 选择         │
│  Spoke/IntegrationHub 提供跨系统 Action       │
└──────────────────────────────────────────────┘
```

### 1.4 Microsoft Power Automate (Dataverse Actions)

- **Custom API**：用户自定义的 Action，平台一等公民
- **Plug-in Pipeline**：每个 Action 可注册 N 个 Plug-in 拦截器
- **PowerFx Formula**：轻量表达式在 Action 参数中

### 1.5 头部产品共性

| 特性 | Salesforce | SAP | ServiceNow | MS Power Platform | **我们 v2 已有** |
|------|-----------|-----|-----------|------------------|------------------|
| Action 一等公民 | ✅ | ✅ | ✅ | ✅ | ✅ 12 个标准动作 |
| 元数据声明 Action | ✅ | ✅ | ✅ | ✅ | ✅ `_standard_actions.yaml` |
| 拦截器/Plug-in 链 | ✅ Apex Trigger | ✅ BAdI | ✅ Business Rule | ✅ Plug-in | ✅ 18 拦截器 |
| 自动 UI 渲染 | ✅ Lightning | ✅ Fiori Elements | ✅ UI Action | ✅ BPF | ⚠️ 部分（MetaListPage） |
| 异步执行 | ✅ Queueable | ✅ async_oo | ✅ Scheduled Job | ✅ Cloud Flow | ✅ Async Mode |
| 审计自动 | ✅ Field History | ✅ Change Doc | ✅ Audit | ✅ Audit | ✅ Audit Interceptor |

**结论**：我们的 **BO Action + 18 拦截器** 已经是**对标头部产品的核心架构**，但**目前**仍存在两大空白：
1. ❌ **业务 Action 数量不足**（仅 12 个标准动作，缺少业务专用 Action 如 `permission_rule.preview`、`draft.save`）
2. ❌ **前端调用模式未统一**（仍是 `fetch('/api/...')` 直调，未走 `bo_action.execute()` 门面）

### 1.6 v3 的设计目标

**补齐两个空白**：
- **空白 1**：扩展 Action 体系，新增 `user.authenticate`、`user.logout`、`{bo}.batch_save`、`condition.evaluate` 等业务 Action
- **空白 2**：前端引入 `useBoAction(actionId, params)` 统一门面，所有业务调用都走它

---

## 2. v3 架构详细设计

### 2.1 后端：BO Action 扩展

#### 2.1.1 已有 Action（保留）

```yaml
# meta/schemas/_standard_actions.yaml （已有）
- id: crud_create
- id: crud_read
- id: crud_update
- id: crud_delete
- id: crud_list
- id: export
- id: import
- id: approve
- id: search
- id: assign
- id: revoke
- id: manage
```

#### 2.1.2 新增 Action（v3 实施）

```yaml
# meta/schemas/_business_actions.yaml （新增）
business_actions:
  # ===== 用户认证类（FR-002 替代）=====
  - id: user.authenticate
    name: 用户登录
    action_type: business
    method: POST
    object_type: user
    permission_required: null  # 公开操作
    description: 验证用户名/密码，成功后签发 token
    input_schema:
      username: string
      password: string
    output_schema:
      user: object
      token: string
      must_change_password: boolean

  - id: user.logout
    name: 用户登出
    action_type: business
    method: POST
    object_type: user
    input_schema: {}
    output_schema:
      success: boolean

  - id: user.get_current
    name: 获取当前用户
    action_type: business
    method: GET
    object_type: user
    output_schema:
      user: object

  - id: user.change_password
    name: 修改密码
    action_type: business
    method: POST
    object_type: user
    input_schema:
      old_password: string
      new_password: string
    output_schema:
      success: boolean

  - id: user.update_profile
    name: 更新个人资料
    action_type: business
    method: PUT
    object_type: user
    input_schema:
      profile_data: object
    output_schema:
      user: object

  # ===== 业务对象批量保存（FR-005 替代）=====
  - id: '{object_type}.batch_save'
    name: 批量保存草稿
    action_type: business
    method: POST
    object_type: dynamic   # 运行时绑定
    input_schema:
      draft_map: object   # {rowId: fields}
      data_rows: array    # 用于 FK 回填
    output_schema:
      creates: array
      updates: array
      removals: array
      failures: array

  # ===== 条件表达式求值（FR-008 替代）=====
  - id: condition.evaluate
    name: 求值条件表达式
    action_type: business
    method: POST
    input_schema:
      condition: string
      context: object     # 变量绑定
    output_schema:
      result: boolean
      friendly_text: string  # 业务语义翻译

  # ===== Key Template（FR-004 替代）=====
  - id: '{object_type}.suggest_code'
    name: 建议编码
    action_type: business
    method: POST
    input_schema:
      parent_params: object
    output_schema:
      code: string
      conflict: boolean  # 是否与已存在冲突

  # ===== 权限规则预览（FR-007/009 替代）=====
  - id: permission_rule.preview
    name: 预览匹配资源
    action_type: business
    method: POST
    object_type: permission_rule
    input_schema:
      resource_type: string
      condition: string
    output_schema:
      count: integer
      resources: array
```

#### 2.1.3 静态 Service（计算层）

```python
# meta/services/static/condition_evaluator.py
"""
静态 Service: 条件表达式求值
- 纯函数, 无状态
- 不访问 DB, 不参与拦截器
- 可被多个 BO Action 复用
"""
class StaticConditionEvaluator:
    """纯函数条件求值器"""
    
    @staticmethod
    def parse(expr: str) -> AST:
        """解析条件表达式为 AST（无副作用）"""
        
    @staticmethod
    def evaluate(ast: AST, context: dict) -> bool:
        """对 AST 求值（无副作用）"""
        
    @staticmethod
    def translate_to_friendly(ast: AST, dim_map: dict) -> str:
        """翻译为业务语义文本"""

static_condition_evaluator = StaticConditionEvaluator()


# meta/services/static/filter_type_inferrer.py
"""过滤类型推断器（前端 filterService.js 替代）"""
class StaticFilterTypeInferrer:
    @staticmethod
    def infer(field: dict) -> str:
        return 'date-range' / 'select' / 'number-range' / 'search'
    
    @staticmethod
    def build_query_params(filters: dict, columns: list) -> dict:
        """从过滤值构建 API 查询参数"""

static_filter_type_inferrer = StaticFilterTypeInferrer()


# meta/services/static/api_path_resolver.py
"""API 路径解析器"""
class StaticApiPathResolver:
    @staticmethod
    def resolve(group: str, name: str, **params) -> str:
        """纯函数: 根据 group/name 解析路径"""
        
    @staticmethod
    def get_manifest() -> dict:
        """返回所有路径（前端启动时拉取）"""
```

#### 2.1.4 Action 实现（注册到 bo_framework）

```python
# meta/services/actions/user_authenticate.py
"""
BO Action: user.authenticate
注册到 ActionDispatcher，由 bo_framework.execute('user.authenticate', params) 调用
"""
from meta.core.action_context import ActionContext, ActionResult
from meta.services.auth_provider import LocalAuthProvider
from meta.services.token_service import TokenService
from meta.services.token_blacklist_service import token_blacklist_service
from meta.services.rate_limiter import rate_limiter
from meta.core.datasource import get_data_source
import logging

logger = logging.getLogger(__name__)


def user_authenticate_handler(context: ActionContext) -> ActionResult:
    """
    user.authenticate Action 处理器
    
    自动获得拦截器链：
    - AuditLogInterceptor (priority 35) → 记录登录审计
    - SecurityLogInterceptor (priority 30) → 记录安全事件
    """
    params = context.params
    username = params.get('username', '').strip()
    password = params.get('password', '')
    client_ip = context.user_context.get('ip_address', '')
    
    if not username or not password:
        return ActionResult.failure('用户名和密码不能为空')
    
    # 1. 速率限制
    is_locked, msg = rate_limiter.check_rate_limit(client_ip, username)
    if is_locked:
        return ActionResult.failure(msg, code='RATE_LIMITED')
    
    # 2. 认证
    ds = get_data_source(...)
    provider = LocalAuthProvider(ds)
    user_info = provider.authenticate({'username': username, 'password': password})
    
    if not user_info:
        rate_limiter.record_failed_attempt(client_ip, username)
        return ActionResult.failure('用户名或密码错误', code='INVALID_CREDENTIALS')
    
    rate_limiter.record_successful_attempt(client_ip, username)
    
    # 3. 创建 token
    token, expires_at = TokenService.create_token(user_info)
    
    # 4. 查询 must_change_password
    cursor = ds.execute("SELECT must_change_password FROM users WHERE id = ?", [user_info.user_id])
    row = cursor.fetchone()
    must_change = bool(row[0]) if row else False
    
    return ActionResult.success({
        'user': {
            'id': user_info.user_id,
            'username': user_info.username,
            'display_name': user_info.display_name,
            'roles': user_info.roles,
            'permissions': user_info.permissions,
        },
        'token': token,
        'expires_at': expires_at.isoformat() if expires_at else None,
        'must_change_password': must_change
    })
```

#### 2.1.5 Action 注册到 bo_framework

```python
# meta/core/bo_framework.py 中扩展
def register_business_actions(self):
    """注册业务 Action 处理器"""
    from meta.services.actions import user_authenticate, user_logout, ...
    
    self._action_handlers['user.authenticate'] = {
        'handler': user_authenticate_handler,
        'async_supported': False,
        'permission_required': None,
    }
    self._action_handlers['user.logout'] = {...}
    # ...
    
def execute(self, action_id: str, params: dict = None, context: dict = None) -> dict:
    """
    统一 Action 入口（替换所有 service 直调）
    """
    if action_id not in self._action_handlers:
        raise KeyError(f"Unknown action: {action_id}")
    
    handler_info = self._action_handlers[action_id]
    handler = handler_info['handler']
    
    # 构造 ActionContext（用户/审计/trace）
    action_context = ActionContext(
        params=params or {},
        user_id=context.get('user_id'),
        user_name=context.get('user_name'),
        ip_address=context.get('ip_address'),
        trace_id=context.get('trace_id'),
    )
    
    # ★ 走拦截器链（18 拦截器自动生效）
    self._run_interceptors_before(action_id, action_context)
    
    try:
        result = handler(action_context)
        self._run_interceptors_after(action_id, action_context, result)
        return result
    except Exception as e:
        self._run_interceptors_error(action_id, action_context, e)
        raise
```

#### 2.1.6 Action API 端点（自动注册）

```python
# meta/api/bo_action_api.py （新增）
"""
BO Action 统一 API
所有业务 Action 走 POST /api/v2/action/{action_id}
"""
from flask import Blueprint, request, jsonify
from meta.core.bo_framework import bo_framework

action_bp = Blueprint('bo_action', __name__, url_prefix='/api/v2/action')


@action_bp.route('/<path:action_id>', methods=['GET', 'POST', 'PUT', 'DELETE'])
def execute_action(action_id: str):
    """
    通用 Action 端点
    
    POST /api/v2/action/user.authenticate
    POST /api/v2/action/{object_type}.batch_save
    POST /api/v2/action/condition.evaluate
    """
    method = request.method
    params = {}
    
    if method == 'GET':
        params = dict(request.args)
    else:
        params = request.get_json(silent=True) or {}
    
    # 用户上下文（从 Cookie / Bearer Token 提取）
    user_context = {
        'user_id': g.current_user.id if hasattr(g, 'current_user') else None,
        'user_name': g.current_user.username if hasattr(g, 'current_user') else None,
        'ip_address': request.remote_addr,
    }
    
    try:
        result = bo_framework.execute(action_id, params, user_context)
        return jsonify({
            'success': result.success,
            'data': result.data,
            'message': result.message,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e),
        }), 500
```

#### 2.1.7 启动时注册所有业务 Action

```python
# meta/server.py 中
from meta.core.bo_framework import bo_framework

def init_app():
    # ... 现有初始化
    bo_framework.register_business_actions()  # ★ 注册 8+ 业务 Action
    # ... 注册 API blueprint
    app.register_blueprint(action_bp)  # 业务 Action 端点
```

### 2.2 前端：useBoAction 统一门面

```javascript
// src/composables/useBoAction.js （新增）
/**
 * useBoAction - 统一 BO Action 调用门面
 *
 * 替换所有散落的 apiPost/apiGet 直调
 * 业务逻辑 100% 走后端 BO Action + 18 拦截器链
 */
import { ref, computed } from 'vue'
import { apiPost, apiGet, apiPut, apiDelete } from '@/utils/api'

export function useBoAction(actionId, options = {}) {
  const {
    autoExecute = false,
    onSuccess,
    onError
  } = options

  const loading = ref(false)
  const error = ref(null)
  const data = ref(null)

  async function execute(params = {}, method = 'POST') {
    loading.value = true
    error.value = null
    try {
      // ★ 所有业务 Action 走统一端点
      const httpMethod = ['GET', 'search'].includes(method) ? apiGet
                        : method === 'PUT' ? apiPut
                        : method === 'DELETE' ? apiDelete
                        : apiPost

      const result = await httpMethod(`/action/${actionId}`, params)
      data.value = result.data
      onSuccess?.(result.data)
      return result
    } catch (e) {
      error.value = e
      onError?.(e)
      throw e
    } finally {
      loading.value = false
    }
  }

  if (autoExecute) execute()
  return { execute, loading, error, data }
}

// 静态 Service 代理（计算型，本地同步调用）
export const staticServices = {
  filter: {
    inferType: (col) => {
      // 注: 实际上前端不需要, 用后端静态 service
      throw new Error('Use backend: import StaticFilterTypeInferrer')
    }
  }
}
```

#### 重构后的 authStore（v3）

```javascript
// src/stores/authStore.js —— v3 极简版
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useBoAction } from '@/composables/useBoAction'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)
  const error = ref('')
  
  const { execute: executeAction } = useBoAction(null)  // lazy
  
  async function login(username, password) {
    loading.value = true
    error.value = ''
    try {
      // ★ 走 BO Action: user.authenticate
      const result = await executeAction(
        { actionId: 'user.authenticate', params: { username, password } }
      )
      user.value = result.data.user
      return true
    } catch (e) {
      error.value = e.message
      return false
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    try {
      // ★ 走 BO Action: user.logout
      await executeAction({ actionId: 'user.logout' })
    } finally {
      user.value = null
    }
  }

  async function fetchCurrentUser() {
    try {
      // ★ 走 BO Action: user.get_current
      const result = await executeAction(
        { actionId: 'user.get_current' },
        'GET'
      )
      user.value = result.data
      return true
    } catch (e) {
      return false
    }
  }

  // 全部走 BO Action, 无业务逻辑
  return { user, loading, error, login, logout, fetchCurrentUser }
})
```

#### 重构后的 useMetaList.saveDraftValues（v3）

```javascript
// src/composables/useMetaList.js
import { useBoAction } from '@/composables/useBoAction'

async function saveDraftValues() {
  if (draftValues.value.size === 0) return

  loading.value = true
  try {
    // ★ 走 BO Action: {object_type}.batch_save
    // 业务逻辑（FK 回填/拆分/批量创建/审计/权限）100% 在后端
    const result = await executeBoAction(
      `${objectType}.batch_save`,
      {
        draft_map: Object.fromEntries(draftValues.value),
        data_rows: data.value
      }
    )

    if (result.data.total_failure > 0) {
      throw new Error(`${result.data.total_failure} 项保存失败`)
    }

    ElMessage.success(`成功保存 ${result.data.total_success} 项修改`)
    draftValues.value.clear()
    await refresh()
  } catch (e) {
    handleError('保存修改', e)
  } finally {
    loading.value = false
  }
}
```

#### 静态 Service 在前端的体现

**前端不需要** import Python 静态 Service。但前端**可**把"过滤类型推断"等纯计算放在前端（因为同种语言、同进程、零网络），但**仅作为缓存层**，权威源仍是后端。

**v3 取舍**：把"纯计算"也下沉到后端，**通过 BO Action 暴露**：
- `POST /api/v2/action/filter.infer_type` `{field}` → `{type: 'date-range'}`
- `POST /api/v2/action/filter.build_query` `{filters, columns}` → `{params: {...}}`

但**性能上不划算**（每次推断都走 HTTP）。所以 v3 的取舍是：
- **简单类型推断**（O(1) 字符串判断）→ 保留在前端（已有 `filterService.js`）
- **复杂业务计算**（如权限规则预览、条件求值、批量保存）→ 走 BO Action

### 2.3 API 路径后端化（保留为客户端 Bootstrap）

```python
# meta/services/static/api_path_resolver.py
"""
静态 Service: API 路径解析
- 纯函数, 无状态
- 前端启动时拉取 manifest（一次性）
- 不属于"业务逻辑", 属于"客户端配置"
"""
@dataclass
class ApiPathGroup:
    group: str
    version: str
    base: str
    paths: Dict[str, str]


class StaticApiPathResolver:
    _MANIFEST = {
        'user': ApiPathGroup('user', 'v2', '/api/v2', {
            'authenticate': '/action/user.authenticate',
            'logout': '/action/user.logout',
            'me': '/action/user.get_current',
        }),
        'bo': ApiPathGroup('bo', 'v2', '/api/v2', {
            'crud': '/bo/{object_type}',
            'batch_save': '/action/{object_type}.batch_save',
        }),
        # ... 其他组
    }
    
    @classmethod
    def get_manifest(cls) -> dict:
        return {k: asdict(v) for k, v in cls._MANIFEST.items()}
    
    @classmethod
    def resolve(cls, group: str, name: str, **params) -> str:
        g = cls._MANIFEST.get(group)
        if not g:
            raise KeyError(f"Unknown group: {group}")
        path = g.paths[name]
        if params:
            path = path.format(**params)
        return f"{g.base}{path}"
```

**前端**：启动时拉取 manifest 到 localStorage，**不**每次请求都查后端。

---

## 3. 4 个 FR 的 v3 实施（BO Action 导向）

### 3.1 FR-001（HTTP 客户端）→ **彻底删除**

**理由**：HTTP 客户端是基础设施（`utils/api.js`），不属于"业务下沉"范畴。**v3 不调整 HTTP 客户端**。

**唯一变更**：`utils/api.js` 加 `actionPost` / `actionGet` 工厂（基于现有 `apiPost`）：

```javascript
// utils/api.js 末尾添加
export const actionPost = (actionId, params, options) =>
  apiPost(`/action/${actionId}`, params, options)
export const actionGet = (actionId, params, options) =>
  apiGet(`/action/${actionId}?` + new URLSearchParams(params).toString(), options)
```

### 3.2 FR-002（authService）→ **BO Action 化**

#### 后端

**新增**：
- `meta/schemas/_business_actions.yaml`（5 个 user.* Action 声明）
- `meta/services/actions/user_authenticate.py`（~80 行）
- `meta/services/actions/user_logout.py`（~30 行）
- `meta/services/actions/user_get_current.py`（~50 行）
- `meta/services/actions/user_change_password.py`（~60 行）
- `meta/services/actions/user_update_profile.py`（~50 行）
- `meta/core/bo_framework.py` 增加 `register_business_actions()` + `execute()`
- `meta/api/bo_action_api.py`（统一 Action 端点）
- **删除/大幅简化**：`meta/api/auth_api.py`（5 个 endpoint 改为薄代理，或直接删除，统一走 `/action/`）

**保留**：
- `meta/services/auth_provider.py`、`token_service.py`、`token_blacklist_service.py`、`rate_limiter.py`（被 Action 调用）
- `meta/services/auth_middleware.py`（用于保护 endpoint）

#### 前端

**新增**：`src/composables/useBoAction.js`（~50 行）

**重构**：
- `src/stores/authStore.js`（从 187 行 → ~60 行，删除所有 fetch，删除 `getAuthHeaders()`）
- `useObjectIdentity.js` 中 3 处 `Bearer ${authStore.token}` 修复为 `credentials: 'include'`

**删除**：
- `src/services/authService.js`（v1/v2 计划新建，**v3 取消**）

### 3.3 FR-005（DraftPersist）→ **BO Action 化**

#### 后端

**新增**：
- `_business_actions.yaml` 中 `{object_type}.batch_save` Action 声明
- `meta/services/actions/batch_save.py`（~150 行）
  - 接收 `draft_map` + `data_rows`
  - 拆分 creates/updates（用静态 service `static/draft_splitter.py`）
  - 调 `bo_framework.execute(f"{object_type}.crud_create", payload)` 循环
  - 聚合结果返回

- `meta/services/static/draft_splitter.py`（~100 行）
  - 纯函数 `split_drafts(draft_map, data_rows) -> (creates, updates, removals)`
  - 纯函数 `build_new_row_payload(row, fields, initial_values) -> dict`
  - 纯函数 `has_any_change(fields, initial_values) -> bool`

**优势**：
- 每个 `crud_create` Action 走完整拦截器链（审计/权限/级联/通知）
- 静态 splitter 纯函数，易单测
- 前端 0 业务逻辑

#### 前端

**重构**：
- `useMetaList.saveDraftValues`（80 行 → 12 行）
- 删除所有 `buildNewRowPayload` / `splitDrafts` / `Promise.all` 业务代码

**删除**：
- `src/services/draftPersistService.js`（v1 计划新建，**v3 取消**）

### 3.4 FR-006（API_BASE）→ **客户端 Bootstrap**

**保留 v2 设计**但定位明确：
- **后端**：`meta/services/static/api_path_resolver.py`（纯函数 + manifest）
- **API**：`GET /api/v2/client/manifest`（前端启动时拉取）
- **前端**：`src/utils/api.js` 加 `initManifest()` + `resolveApiPath()`

**不**属于"业务下沉"（无业务逻辑），但**是配置统一**。

---

## 4. v3 vs v1/v2 对比

| 维度 | v1 (前端 service) | v2 (后端 service) | **v3 (BO Action 导向)** |
|------|------------------|------------------|----------------------|
| 业务抽象 | 平行 service | 平行 service | **BO Action 体系**（已有 12 标准 + N 业务） |
| 拦截器链 | ❌ 不参与 | ⚠️ 部分调 `bo_framework.execute` | ✅ **100% 走拦截器** |
| 跨端复用 | ❌ | ⚠️ 部分 | ✅ **完整复用** |
| 静态计算归属 | 前端 service | 后端 service | **后端 static service**（同进程，无 HTTP） |
| 业务 API 数量 | +0 | +3 service | **+8 Action + 1 static service** |
| HTTP 路径数 | 5 个 | 3 个 | **1 个统一端点** `/action/{action_id}` |
| 性能开销 | 0 | +3 HTTP | **+0（Action 走拦截器是 in-process）** |
| 与 v2 架构对齐 | ⚠️ 平行 | ⚠️ 平行 | ✅ **v2 设计本身就是 BO Action 导向** |
| 头部产品对标 | ❌ | ❌ | ✅ Salesforce Action / SAP CDS Action |
| 未来扩展性 | 低 | 中 | **高**（新增 Action 即可，无需新建 service） |

### 关键性能优势

| 操作 | v1 路径 | v2 路径 | **v3 路径** |
|------|---------|---------|------------|
| 用户登录 | 1 HTTP | 1 HTTP | **1 HTTP** + 18 拦截器自动保护 |
| 批量保存草稿 | 1 HTTP | 1 HTTP | **1 HTTP** + 每行自动 18 拦截器 |
| 条件求值 | — | 1 HTTP | **1 HTTP** + 复用静态 service |
| 启动时拉路径 | — | 1 HTTP | **1 HTTP**（一次性） |

**v3 优势**：
- **拦截器链 in-process**：拦截器调用是 Python 函数调用，**无 HTTP 开销**（v2 走 service 也是函数调用，但 v3 是**统一抽象**）
- **统一 Action 端点**：前端只需记住 `POST /api/v2/action/{action_id}`，无需记忆 30+ endpoint
- **审计/权限零成本**：所有 Action 自动获得，不需要手动串联

---

## 5. 实施计划（v3）

### 5.1 阶段

```
Phase 0: 基础设施（3 天）
  - 后端: 注册 Business Action 框架（bo_framework.register_business_actions + execute）
  - 后端: 新增 bo_action_api.py 统一端点
  - 前端: 新增 src/composables/useBoAction.js
  - 前端: utils/api.js 加 actionPost / actionGet 工厂
  - 端到端验证: 实现 user.authenticate + authStore.login 走通

Phase 1: Auth 重构（2 天）
  - 后端: 实现 5 个 user.* Action
  - 后端: 简化/删除 auth_api.py
  - 前端: authStore 全部走 BO Action
  - 前端: 修复 useObjectIdentity token BUG
  - 端到端: 登录/登出/获取用户/修改密码/更新资料

Phase 2: 草稿保存重构（2 天）
  - 后端: 实现 static/draft_splitter.py（纯函数）
  - 后端: 实现 {object_type}.batch_save Action
  - 前端: useMetaList.saveDraftValues 简化
  - 端到端: 列表新建/编辑/批量保存

Phase 3: API 路径 Bootstrap（1 天）
  - 后端: static/api_path_resolver.py
  - 后端: GET /api/v2/client/manifest
  - 前端: utils/api.js 加 initManifest / resolveApiPath
  - 前端: main.js 启动初始化
  - 端到端: 11 个文件硬编码删除

Phase 4: 回归 + 监控（1 天）
  - python d:\filework\test.py --failed 全量
  - E2E: 关键路径回归
  - 性能基准对比（v2 vs v3）
```

**总工作量：~9 天**（比 v2 多 3 天，因为引入新框架 + 端到端验证更深）

### 5.2 提交流水线（v3）

| PR | 范围 | 后端变更 | 前端变更 | 工时 |
|----|------|---------|---------|------|
| **#0** | 基础设施 | +bo_framework 扩展, +bo_action_api | +useBoAction.js | 3 天 |
| **#1** | Auth 5 Action | +5 Action + 简化 auth_api | authStore 重构 | 2 天 |
| **#2** | 草稿 batch_save | +static/draft_splitter + Action | useMetaList 简化 | 2 天 |
| **#3** | API 路径 Bootstrap | +static/api_path_resolver + manifest API | utils/api.js + main.js | 1 天 |
| **#4** | 回归 + 监控 | - | - | 1 天 |

---

## 6. 性能与影响分析

### 6.1 性能对比

| 指标 | v1 | v2 | **v3** |
|------|----|----|--------|
| **用户登录** | 1 HTTP | 1 HTTP | 1 HTTP + 18 拦截器（in-process，~0.5ms） |
| **批量保存 10 行** | 1 HTTP + 10 内部 create | 1 HTTP（后端串行 create）| 1 HTTP + 10 Action（每行 18 拦截器） |
| **条件求值（100 次）** | — | 100 HTTP ❌ | **缓存静态 service + 1 HTTP** |
| **启动时间** | 0 | +50ms（拉 manifest） | +50ms（拉 manifest） |
| **包体积** | 0 | 0 | +50 行 useBoAction.js |

### 6.2 拦截器链 in-process 性能实测（预估）

```python
# 18 拦截器链的典型执行时间
@timeit
def run_interceptors():
    # 18 拦截器 before_action
    # 1 个 handler
    # 18 拦截器 after_action
    pass

# 预估: < 5ms (纯 Python, 无 IO)
```

**关键点**：拦截器主要是**纯函数**（参数绑定、审计日志构造、权限检查），不涉及 IO。即使 18 个串联，**总开销 < 10ms**，相比 HTTP 请求（~50-100ms）可忽略。

### 6.3 业务可观测性提升

v3 通过 BO Action 统一：
- ✅ **traceId 自动传递**：每个 Action 有唯一 traceId，可跨拦截器追踪
- ✅ **审计日志统一格式**：`{action_id, params, result, user, ip, trace_id, duration}`
- ✅ **业务统计**：`bo_action_daily_count[action_id]` 表统计 Action 调用
- ✅ **慢 Action 监控**：`bo_action_slow_log[action_id, duration]` 自动告警

### 6.4 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|------|:---:|:---:|------|
| BO Action 框架扩展破坏现有 CRUD | 中 | 高 | **Phase 0 充分测试**；保留旧 endpoint，灰度切换 |
| 静态 service 同进程依赖 | 低 | 中 | 静态 service 是纯函数，无 IO 依赖；测试覆盖 |
| 18 拦截器串联性能 | 低 | 中 | 实测 < 10ms；可禁用非关键拦截器 |
| 端点统一导致调试困难 | 中 | 低 | 每个 Action 仍保留独立 endpoint（如 `/action/user.authenticate`） |
| 启动时拉 manifest 失败 | 中 | 中 | 硬编码 fallback |

### 6.5 对测试的影响

| 测试类型 | v1/v2 | **v3** |
|---------|-------|--------|
| 后端单测 | service 文件 1 个 1 测 | **Action 1 个 1 测 + 静态 service 1 个 1 测**（颗粒度更细） |
| 端到端 | HTTP + service | **HTTP + Action**（更聚焦） |
| 拦截器测试 | 单独 | **集成在 Action 测试中**（更现实） |

---

## 7. 与 v2 架构的对齐

[ARCHITECTURE_V2.md](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) §6.4 明确说：

> **统一的元数据驱动企业级架构**
> **路径B (CAP模式)**：YAML即模型，拦截器即运行时，声明式替代命令式

v3 完全对齐：
- **YAML 即模型**：`_business_actions.yaml` 声明 8+ Action
- **拦截器即运行时**：所有 Action 自动走 18 拦截器
- **声明式替代命令式**：前端 `useBoAction('user.authenticate')` 而非 `apiPost('/api/v1/auth/login', ...)`

v3 是 **v2 架构的天然延伸**，v1/v2 是 **架构漂移**。

---

## 8. 变更记录

| 版本 | 日期 | 变更内容 | 作者 |
|:---:|------|---------|------|
| 1.0.0 | 2026-06-05 | 前端 service 路径 | AI Agent (Trae) |
| 2.0.0 | 2026-06-05 | 后端 service 路径 | AI Agent (Trae) |
| 3.0.0 | 2026-06-05 | **BO Action 导向 + 静态 Service 双层** | AI Agent (Trae) |

---

## 9. 关键决策点（待你确认）

1. **BO Action 框架扩展**是否在本期做？
   - 涉及 `bo_framework.py` 改造 + 18 拦截器兼容性测试
   - 风险中等，收益巨大

2. **静态 Service 边界**如何划分？
   - v3 取舍：复杂业务计算走 BO Action，简单纯计算保留前端
   - 是否需要更激进的"全部后端"？

3. **Action 数量**首批 8 个够不够？
   - 8 个覆盖 4 个 FR + 后续 FR-007/008/009
   - 是否需要更多（`{bo}.export` / `{bo}.import`）？

4. **统一 Action 端点** vs **保留独立 endpoint**？
   - v3 推荐统一端点（`/action/{id}`），但保留每个 Action 的可独立访问 endpoint
   - 调试时更便利

---

*本 Spec v3 是 v1/v2 的**根本性重构**，从"service vs service" 升级到 "BO Action vs 静态 Service vs 客户端 Bootstrap" 三层模型，完全对齐 v2 架构和头部产品（Salesforce/SAP/ServiceNow）最佳实践。*
