# Spec: v3 BO Action 体系扩展 — 后续 6 个可选任务细化方案 (v1.0)

> **日期**: 2026-06-05
> **作者**: AI Agent (Trae) — 基于深入代码调研
> **状态**: 📋 方案阶段，待用户确认后进入实施
> **依赖**: [spec-p0-5-actions.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-p0-5-actions.md) 已完成 11 个 Action
> **关联主 Spec**: [spec-ui-business-logic-downflow.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-ui-business-logic-downflow.md) v2.0 (主 Spec)

---

## 📋 文档定位

**这是 v3 BO Action 主线的** 续篇**。**主 Spec (spec-ui-business-logic-downflow.md) 关注 UI 层业务逻辑下沉；本 Spec 关注后端 BO Action 体系的扩展。**

两者**互补**而非替代。

---

## 🎯 6 个任务总览

| # | 任务 | 价值 | 工时 | 风险 | 推荐实施顺序 |
|---|------|:---:|:---:|:---:|---:|
| 1 | **Subflow chain_call** | 🔴 极高 | 4h | 🟡 中 | 1️⃣ |
| 2 | **action_handlers.py 完全迁移** | 🟠 高 | 3h | 🟡 中 | 2️⃣ |
| 3 | **OpenAPI 3.0 自动生成** | 🟡 中 | 2h | 🟢 低 | 3️⃣ |
| 4 | **TypeScript types 自动生成** | 🟡 中 | 2h | 🟢 低 | 4️⃣ (配套 #3) |
| 5 | **P1 6 个 Action** | 🟡 中 | 4h | 🟢 低 | 5️⃣ (按需) |
| 6 | **send_file 崩溃根因诊断** | 🟢 低 | 1h | 🟡 中 | 6️⃣ (deferred) |

**总工时**: 12h (4-5 个工作日)

---

## 1️⃣ Subflow chain_call（ServiceNow Flow Designer 模式）

### 背景

**ServiceNow Flow Designer** 核心特性: Subflow 可嵌套、可复用。当前我们的 BO Action 都是**单步**——**复杂业务**（如用户注册）需要多个 Action 串联，前端需要 5+ 次 HTTP 调用。

### 业务用例

| 业务 | Action 链 | 当前 HTTP | 改进后 |
|------|----------|----------|--------|
| **用户注册** | `user.create` + `user.update_profile` + `subscription.create` + `notification.publish` | 4 次 | **1 次** |
| **订单审批** | `state.transition` + `audit.log` + `notification.publish` + `workflow.advance` | 4 次 | **1 次** |
| **数据导入** | `batch_save` + `aggregate.refresh` + `notification.publish` | 3 次 | **1 次** |

### 设计

#### API 契约

```http
POST /api/v2/action/_chain
Content-Type: application/json
Cookie: auth_token=...

{
  "name": "user_onboard",  // Subflow 名称 (审计用, 可选)
  "atomic": true,           // 是否原子性 (默认 false, 任一失败继续)
  "context": {              // 全局 context (传递给每个 step)
    "user_id": 123,
    "ip_address": "127.0.0.1"
  },
  "steps": [
    {
      "action_id": "user.create",
      "params": {"username": "newuser", "display_name": "New User"},
      "as": "user"  // 把这个 step 的结果保存为 alias, 后续可引用
    },
    {
      "action_id": "user.update_profile",
      "params": {
        "display_name": "Updated Name",
        "email": "newuser@example.com"
      },
      "use": {  // 引用前序 step 的结果 (jinja2 风格)
        "user_id": "$user.data.user_id"
      }
    },
    {
      "action_id": "subscription.create",
      "params": {
        "object_type": "user",
        "channel": "websocket"
      },
      "use": {
        "user_id": "$user.data.user_id"
      },
      "skip_if": "$user.success == false"  // 条件跳过
    }
  ]
}
```

#### 响应

```json
{
  "success": true,
  "data": {
    "name": "user_onboard",
    "atomic": true,
    "total_steps": 3,
    "succeeded": 3,
    "failed": 0,
    "duration_ms": 245,
    "steps": [
      {
        "step_index": 0,
        "action_id": "user.create",
        "alias": "user",
        "success": true,
        "data": {"user_id": 123},
        "duration_ms": 89
      },
      {
        "step_index": 1,
        "action_id": "user.update_profile",
        "success": true,
        "data": {"updated": ["display_name", "email"]},
        "duration_ms": 67
      },
      {
        "step_index": 2,
        "action_id": "subscription.create",
        "alias": "subscription",
        "success": true,
        "data": {"subscription_id": 456},
        "duration_ms": 89
      }
    ]
  },
  "message": "Subflow user_onboard 成功 3/3 步"
}
```

#### 关键设计

| 维度 | 设计 |
|------|------|
| **原子性** | `atomic=true` → 任一失败则回滚之前已执行的 (需 BO 支持事务) |
| **非原子** | `atomic=false` → 默认, 继续执行所有 step, 收集成功/失败 |
| **变量引用** | `$alias.data.field` Jinja2 风格 |
| **条件跳过** | `skip_if` 表达式, 失败/匹配时跳过 |
| **上下文** | 全局 context + 各 step params 合并 |
| **事务** | atomic=true 时, 用 `with ds.transaction():` 包裹 |
| **超时** | 单 step 30s, 总 5min |
| **审计** | 单独写 1 条 audit_log: action=SUBFLOW, name=xxx, steps=3 |

#### 关键实现

```python
# meta/api/bo_action_api.py 新增 /api/v2/action/_chain 端点

@bo_action_bp.route('/_chain', methods=['POST'])
def execute_subflow():
    body = g.cached_body or request.get_json(silent=True) or {}
    name = body.get('name', 'unnamed')
    atomic = body.get('atomic', False)
    steps = body.get('steps', [])
    ctx = body.get('context', {})

    if not steps:
        return jsonify({'success': False, 'data': None, 'message': 'steps 不能为空'}), 400

    # 鉴权 (同单个 Action 体系, 用 user context)
    # ...

    # 执行
    results = []
    alias_data = {}  # 保存 alias → result
    transaction_failed = False

    try:
        if atomic:
            from meta.core.datasource import get_data_source
            ds = get_data_source(...)
            ds.execute("BEGIN IMMEDIATE TRANSACTION")

        for idx, step in enumerate(steps):
            action_id = step['action_id']
            params = step.get('params', {})
            alias = step.get('as')
            use = step.get('use', {})
            skip_if = step.get('skip_if')

            # 变量替换
            params = resolve_jinja2(params, alias_data)
            if use:
                params.update(resolve_jinja2(use, alias_data))

            # 条件跳过
            if skip_if and eval_jinja2(skip_if, alias_data):
                results.append({
                    'step_index': idx, 'action_id': action_id, 'alias': alias,
                    'success': None, 'skipped': True,
                })
                continue

            # 调 Action
            step_ctx = {**ctx, 'step_index': idx}
            result = bo_action_registry.call(action_id, params, step_ctx)
            step_result = {
                'step_index': idx,
                'action_id': action_id,
                'alias': alias,
                'success': result.get('success', False),
                'data': result.get('data'),
                'message': result.get('message'),
            }
            results.append(step_result)

            # 保存 alias
            if alias and result.get('success'):
                alias_data[alias] = result

            # 原子性失败
            if atomic and not result.get('success'):
                transaction_failed = True
                break

        if atomic:
            ds = get_data_source(...)
            if transaction_failed:
                ds.execute("ROLLBACK")
            else:
                ds.execute("COMMIT")
    except Exception as e:
        logger.exception(f"[Subflow] failed: {e}")
        if atomic:
            try:
                ds.execute("ROLLBACK")
            except: pass
        return jsonify({
            'success': False, 'data': {'name': name, 'steps': results},
            'message': f'Subflow 失败: {e}',
        }), 500

    succeeded = sum(1 for r in results if r.get('success') is True)
    failed = sum(1 for r in results if r.get('success') is False)
    skipped = sum(1 for r in results if r.get('skipped'))

    return jsonify({
        'success': failed == 0,
        'data': {
            'name': name,
            'atomic': atomic,
            'total_steps': len(steps),
            'succeeded': succeeded,
            'failed': failed,
            'skipped': skipped,
            'steps': results,
        },
        'message': f'Subflow {name} {"成功" if failed == 0 else "部分失败"} {succeeded}/{len(steps)}',
    })
```

### 风险与缓解

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| 事务回滚不一致 | 🟠 高 | atomic=true 时, 每个 step 必须支持事务; 文档明示 |
| 变量引用注入 | 🟠 高 | 用 Jinja2 sandboxed 模式 |
| 性能 (5+ 步) | 🟡 中 | 单 HTTP, 比 N+1 快 10x; 总超时 5min |
| 调试困难 | 🟡 中 | 记录每步 duration_ms + step_index |

### 工时分解

| 步骤 | 工时 |
|------|:---:|
| API endpoint 骨架 + 鉴权 | 1h |
| 单步执行 + alias 收集 | 1h |
| 变量引用 (Jinja2 简化版) | 1h |
| 事务 + 回滚 (atomic) | 1h |
| 4 个 E2E 用例 | 0.5h |
| **总计** | **4h** |

### E2E 测试

| # | 场景 | 期望 |
|---|------|------|
| 1 | 单步成功 | success, succeeded=1 |
| 2 | 多步全成 (user.create + subscription.create) | success, succeeded=2 |
| 3 | 原子失败 (第 2 步失败) | 原子回滚, 第 1 步不保留 |
| 4 | 变量引用 (step2 用 step1 的 result) | params 正确替换 |
| 5 | skip_if 条件跳过 | 该 step 不执行 |
| 6 | 未登录 | 401 |
| 7 | steps=[] | "steps 不能为空" |
| 8 | 大用例 (5 步) | duration_ms < 1000 |

---

## 2️⃣ action_handlers.py 完全迁移到 bo_action_registry

### 背景

`meta/services/action_handlers.py` 是 v2 早期版本, **HANDLERS dict** 注册表已与 v3 `bo_action_registry` 重复。Round 1 实施 P0 5 个 Action 时已加 deprecated 注释, 但**未迁移**。

### 当前状态

- `action_handlers.py` 中现有 HANDLERS dict 内容
- `action_dispatcher.py` 是调用方
- 我们不知道具体多少 handler, 需要 grep 调研

### 计划

| 步骤 | 操作 | 工时 |
|------|------|:---:|
| 1 | 调研 `action_handlers.py` 当前所有 HANDLERS (grep + 列) | 0.5h |
| 2 | 调研 `action_dispatcher.py` 怎么调 (避免破坏) | 0.5h |
| 3 | 在 `bo_action_registry` 中为每个 HANDLER 创建迁移注册 | 1h |
| 4 | 兼容性层: 在 `action_handlers.py` 加转发, 仍可工作 | 0.5h |
| 5 | 验证 2 套都能工作, 删 `action_handlers.py` | 0.5h |
| **总计** | | **3h** |

### 风险

- 🟡 中: 改动 v2 体系, 可能影响 action_dispatcher 现有调用
- 缓解: 加兼容层, **不删** action_handlers.py, 测全 OK 后再删

---

## 3️⃣ OpenAPI 3.0 自动生成

### 背景

Power Platform Custom Connector / ServiceNow OpenAPI 输出是头部产品标配。当前我们已有 `_schemas` 端点 (Round 3 加的), 但**只是 JSON dump**, 不是标准 OpenAPI 3.0 spec。

### 设计

新增端点 `GET /api/v2/action/_openapi.json`, 输出标准 OpenAPI 3.0 spec。

```json
{
  "openapi": "3.0.0",
  "info": {
    "title": "BO Action API",
    "version": "v3.1",
    "description": "业务行为 API 统一端点"
  },
  "servers": [
    {"url": "http://localhost:3010"}
  ],
  "paths": {
    "/api/v2/action/user.authenticate": {
      "post": {
        "operationId": "user.authenticate",
        "summary": "用户登录认证",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/user.authenticate.input"}
            }
          }
        },
        "responses": {
          "200": {
            "content": {
              "application/json": {
                "schema": {"$ref": "#/components/schemas/user.authenticate.output"}
              }
            }
          }
        }
      }
    },
    ...
  },
  "components": {
    "schemas": {
      "user.authenticate.input": {
        "type": "object",
        "required": ["username", "password"],
        "properties": {
          "username": {"type": "string"},
          "password": {"type": "string"}
        }
      },
      "user.authenticate.output": {
        "type": "object",
        "properties": {
          "token": {"type": "string"},
          "user": {"type": "object"}
        }
      }
    }
  }
}
```

### 工时

| 步骤 | 工时 |
|------|:---:|
| 转换函数 (registry → OpenAPI 3.0) | 1h |
| 端点挂载 | 0.5h |
| 验证 11 Action 全部输出 | 0.5h |
| **总计** | **2h** |

### 价值

- ✅ 客户端可生成代码 (openapi-generator)
- ✅ 导入 Postman/Apifox 调试
- ✅ Swagger UI 文档站
- ✅ 客户端 SDK 自动生成 (Mobile/CLI)

---

## 4️⃣ TypeScript types 自动生成

### 背景

前端 `useBoAction.js` 当前 `callPost(actionId, params)` **无类型检查**——`actionId` 拼错、`params` 字段错, 只能运行时发现。

### 设计

新增 `scripts/generate_action_types.js` 脚本, 调 `_openapi.json` 后端端点, 生成 `src/composables/useBoAction.types.d.ts`:

```typescript
// 自动生成 - 不要手动修改
export type ActionId =
  | 'user.authenticate'
  | 'user.logout'
  | 'user.get_current'
  | 'user.change_password'
  | 'user.update_profile'
  | 'batch_save'
  | 'user.reset_password'
  | 'audit.retry'
  | 'audit.export'
  | 'batch_delete'
  | 'subscription.create';

export interface UserAuthenticateInput {
  username: string;
  password: string;
}

export interface UserAuthenticateOutput {
  token?: string;
  user?: object;
}

export interface ActionRegistry {
  'user.authenticate': { input: UserAuthenticateInput; output: UserAuthenticateOutput };
  'user.logout': { input: {}; output: {} };
  'user.get_current': { input: {}; output: UserGetCurrentOutput };
  // ... 11 个
}

export function callPost<T extends ActionId>(
  action_id: T,
  params: ActionRegistry[T]['input']
): Promise<{ success: boolean; data: ActionRegistry[T]['output']; message: string }>;
```

### 工时

| 步骤 | 工时 |
|------|:---:|
| 脚本骨架 (Node.js + openapi-typescript 库) | 1h |
| 11 Action 类型映射 | 0.5h |
| `useBoAction.js` 加类型注解 | 0.5h |
| **总计** | **2h** |

### 价值

- ✅ IDE 自动补全 (actionId, params 字段)
- ✅ 编译期错误 (拼错 field)
- ✅ 重构安全 (改了 input_schema, 前端立刻报错)

---

## 5️⃣ P1 6 个 Action

### 候选清单 (按调研报告优先级 P1)

| # | Action | 现有端点 | 工时 |
|---|--------|----------|:---:|
| 1 | `value_help.resolve` | `GET /api/v2/value-help/<type>/<id>/resolve` ([value_help_api.py:99](file:///d:/filework/excel-to-diagram/meta/api/value_help_api.py#L99)) | 30min |
| 2 | `aggregate.refresh` | `POST /stats/aggregates/<id>/refresh` ([stats_api.py:244](file:///d:/filework/excel-to-diagram/meta/api/stats_api.py#L244)) | 30min |
| 3 | `aggregate.query` | `POST /stats/aggregates/<id>/query` ([stats_api.py:213](file:///d:/filework/excel-to-diagram/meta/api/stats_api.py#L213)) | 30min |
| 4 | `subscription.list` | `GET /api/v1/notification/subscriptions` | 30min |
| 5 | `enum_type.create` | `POST /enum-types` ([enum_api.py](file:///d:/filework/excel-to-diagram/meta/api/enum_api.py)) | 45min |
| 6 | `enum_type.update` | `PUT /enum-types/<id>` ([enum_api.py:374](file:///d:/filework/excel-to-diagram/meta/api/enum_api.py#L374)) | 45min |
| 7 | `enum_type.delete` | `DELETE /enum-types/<id>` | 30min |

**总工时**: 4h

### 价值评估

| 维度 | 评估 |
|------|------|
| **业务高频度** | value_help.resolve (UI 表单必备), aggregate.refresh (运维) |
| **风险** | 🟢 低 — 全部是已有端点迁移 |
| **复用** | 与 P0 5 个 Action 完全同模式 |

### 实施模式

每个 Action:
1. 复制 P0 5 Action 的 handler 模式
2. 复用现有 service 或直接 SQL
3. 注册到 bo_action_registry 带 schema
4. 4-6 个 E2E 用例

---

## 6️⃣ send_file 崩溃根因诊断 (Deferred)

### 背景

Round 3 实施 audit.export 时发现 Flask `send_file(BytesIO(...))` 让 worker 进程死 (watchdog 重启掩盖)。**根因未找到**——`test_request_context` 下 send_file 正常。

### 假设清单

| # | 假设 | 验证方式 |
|---|------|----------|
| 1 | Flask dev `use_reloader=True` 与 send_file 冲突 | 看 `app.run(use_reloader=?)` |
| 2 | Werkzeug SocketIO 死锁 | 监控 socket 状态 |
| 3 | Response 直接传 bytes 不工作 (需 BytesIO) | 强制 BytesIO 包裹 |
| 4 | mimetype 与 content-type header 冲突 | 看 header 顺序 |
| 5 | 1.0.1+ 行为变更 | 看 Flask CHANGES |

### 工时

- 1h 试错测试 (5 假设各 10min)

### 当前状态

✅ **base64 包装方案 100% 解决** (Round 3 验证)
- 前端可识别 `_file_response: true` 标志
- 体积 ~33% 膨胀 (10MB → 13MB), 仍可接受

### 何时做

**仅当**: 客户端需要 100MB+ 文件流 OR WebSocket 文件流 OR 性能优化时。**当前 deferred**。

---

## 📊 6 任务实施时间线 (推荐)

| 周 | 任务 | 总工时 |
|---|------|:---:|
| 第 1 周 | Subflow chain_call (4h) + OpenAPI (2h) | 6h |
| 第 2 周 | TS types (2h) + action_handlers 迁移 (3h) | 5h |
| 第 3 周 | P1 6 Action (4h) + send_file 诊断 (1h) | 5h |
| **总计** | | **16h (2 周)** |

---

## 🛡️ 实施前置条件

- [x] 当前 `feature/bo-action-v3` 分支
- [ ] DB 备份 (实施每任务前 1 次)
- [x] E2E 测试脚本模板
- [x] 服务重启机制验证

---

## 🚦 回滚计划

每个任务独立:
- Subflow: 删除 `_chain` 端点
- action_handlers 迁移: 恢复 action_handlers.py
- OpenAPI: 删除 `_openapi.json` 端点
- TS types: 删除 `.d.ts` 文件
- P1 Action: 删除 service 文件 + server.py 注册行
- send_file 诊断: 纯诊断, 无回滚

---

## 💡 业务侧收益汇总

| 维度 | 当前 | 实施后 |
|------|------|--------|
| BO Action 数量 | 11 | 11 + 7(P1) = 18 |
| 业务能力 | 单步 | 单步 + Subflow (链式) |
| API 文档 | 无 | OpenAPI 3.0 标准 |
| 前端类型安全 | 无 | TypeScript 完整 |
| 注册表数 | 2 (bo_action_registry + action_handlers) | 1 (统一) |
| 文件流 | base64 包装 (可用) | send_file 优化 (deferred) |

---

## 🔗 关联文档

| 文档 | 关系 |
|------|------|
| [spec-p0-5-actions.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-p0-5-actions.md) | 5 个新 Action 详细 spec (已完成) |
| [bo-action-p0-5-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-p0-5-result.md) | 5 个新 Action 实施结果 |
| [bo-action-expansion-survey.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-expansion-survey.md) | 调研报告 (P0/P1/P2 排序) |
| [bo-action-vs-head-products.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-vs-head-products.md) | 头部产品对照 (Salesforce/ServiceNow/Power Platform) |
| [db-corruption-prevention-todo.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/db-corruption-prevention-todo.md) | DB 损坏预防 3 大方案 (用户明确不做, 但**优先级高于 6 任务**) |

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-05 | 创建 6 任务细化方案 spec |
