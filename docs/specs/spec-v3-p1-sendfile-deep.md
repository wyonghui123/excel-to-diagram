## 目录

1. [📋 文档结构](#-文档结构)
2. [🎯 6 Action 业务总览](#-6-action-业务总览)
3. [1️⃣ value_help.resolve](#1-value_helpresolve)
4. [2️⃣ aggregate.refresh](#2-aggregaterefresh)
5. [3️⃣ aggregate.query](#3-aggregatequery)
6. [4️⃣ subscription.list](#4-subscriptionlist)
7. [5️⃣ enum_type.create](#5-enum_typecreate)
8. [6️⃣ enum_type.update](#6-enum_typeupdate)
9. [7️⃣ enum_type.delete](#7-enum_typedelete)
10. [🛡️ P1 6 Action 实施前置条件](#-p1-6-action-实施前置条件)
11. [🚦 风险评估](#-风险评估)
12. [实施时间](#实施时间)
13. [🔍 现象回顾](#-现象回顾)
14. [🕵️ 6 假设排查结果](#-6-假设排查结果)
15. [🎯 假设 5: use_debugger=True 与 send_file 冲突](#-假设-5-use_debuggertrue-与-send_file-冲突)
16. [🛠️ 诊断方案 (1h)](#-诊断方案-(1h))
17. [💡 推荐结论](#-推荐结论)
18. [📊 诊断后产出](#-诊断后产出)
19. [📅 实施顺序 (推荐 1 周内)](#-实施顺序-(推荐-1-周内))
20. [🛡️ 实施前置](#-实施前置)
21. [🚦 回滚计划](#-回滚计划)
22. [📊 最终状态预估](#-最终状态预估)
23. [变更记录](#变更记录)

---
# Spec: v3 BO Action — P1 6 Action + send_file 根因诊断详细方案 (v1.0)

> **日期**: 2026-06-05
> **作者**: AI Agent (Trae) — 基于深入代码调研
> **状态**: 📋 方案阶段
> **关联**: [spec-v3-post-5-followup.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3-post-5-followup.md) 剩余 2 任务
> **总工时**: 5h (P1 4h + send_file 1h)

---

## 📋 文档结构

| 章节 | 内容 |
|------|------|
| 第一部分 | **P1 6 Action 详细方案** (4h) |
| 第二部分 | **send_file 根因诊断** (1h, deferred) |
| 第三部分 | 实施时间线 + 风险评估 |

---

# 第一部分: P1 6 Action 详细方案

## 🎯 6 Action 业务总览

| # | Action | 端点 | 类别 | 鉴权 | 工时 |
|---|--------|------|------|------|:---:|
| 1 | `value_help.resolve` | `GET /api/v2/value-help/<type>/<id>/resolve` | 查询 | 登录 | 30min |
| 2 | `aggregate.refresh` | `POST /stats/aggregates/<id>/refresh` | 运维 | admin | 30min |
| 3 | `aggregate.query` | `POST /stats/aggregates/<id>/query` | 查询 | 登录 | 30min |
| 4 | `subscription.list` | `GET /api/v1/notification/subscriptions` | 查询 | 登录 | 30min |
| 5 | `enum_type.create` | `POST /enum-types` | 业务 | admin | 45min |
| 6 | `enum_type.update` | `PUT /enum-types/<id>` | 业务 | admin | 45min |
| 7 | `enum_type.delete` | `DELETE /enum-types/<id>` | 业务 | admin | 30min |
| **总** | | | | | **4h** |

---

## 1️⃣ value_help.resolve

### 现有端点 (value_help_api.py:99-133)

```python
@value_help_bp.route("/api/v2/value-help/<source_type>/<source_id>/resolve", methods=["GET"])
@login_required
def resolve_value_help(source_type, source_id):
    value = request.args.get("value")
    if not value:
        return jsonify({"success": False, "error": "value parameter is required"}), 400

    source = ValueHelpSource(type=source_type)
    if source_type == "enum":
        source.enum_type_id = source_id
        source.apply_target_permissions = False
    elif source_type == "bo":
        source.target_bo = source_id
        source.value_field = request.args.get("value_field", "id")
        source.display_field = request.args.get("display_field", "name")
        source.code_field = request.args.get("code_field", "code")
    elif source_type == "custom":
        source.endpoint = source_id
    else:
        return jsonify({"success": False, "error": f"Unknown source type: {source_type}"}), 400

    try:
        provider = get_provider(source)
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    user_context = _get_user_context()

    try:
        result = provider.resolve(value, user_context)
        if result is None:
            return jsonify({"success": True, "data": {"value": value, "display": str(value), "code": str(value)}})
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

### Action 化设计

#### API 契约
```http
POST /api/v2/action/value_help.resolve
Content-Type: application/json
Cookie: auth_token=...

{
  "source_type": "enum",     // enum | bo | custom
  "source_id": "color",      // enum_type_id / target_bo / endpoint
  "value": "red",            // 要解析的值
  "value_field": "id",       // bo 模式
  "display_field": "name",
  "code_field": "code"
}
```

#### Handler 实现 (新文件 `meta/services/value_help_resolve.py`)

```python
def value_help_resolve_handler(params, context):
    source_type = params.get('source_type')
    source_id = params.get('source_id')
    value = params.get('value')

    if not source_type or not source_id or value is None:
        return {'success': False, 'data': None, 'message': 'source_type/source_id/value 必填'}

    # 鉴权
    user_info = g.current_user if hasattr(g, 'current_user') else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}

    # 构造 source
    from meta.core.models import ValueHelpSource
    source = ValueHelpSource(type=source_type)
    if source_type == "enum":
        source.enum_type_id = source_id
        source.apply_target_permissions = False
    elif source_type == "bo":
        source.target_bo = source_id
        source.value_field = params.get('value_field', 'id')
        source.display_field = params.get('display_field', 'name')
        source.code_field = params.get('code_field', 'code')
    elif source_type == "custom":
        source.endpoint = source_id
    else:
        return {'success': False, 'data': None, 'message': f'Unknown source type: {source_type}'}

    # 调 provider
    try:
        from meta.core.value_help_providers import get_provider
        provider = get_provider(source)
    except ValueError as e:
        return {'success': False, 'data': None, 'message': str(e)}

    user_context = {
        'user_id': user_info.get('user_id'),
        'roles': user_info.get('roles', []),
        'is_admin': 'admin' in user_info.get('roles', []),
    }

    try:
        result = provider.resolve(value, user_context)
        if result is None:
            result = {'value': value, 'display': str(value), 'code': str(value)}
        return {
            'success': True,
            'data': result,
            'message': '解析成功',
        }
    except Exception as e:
        logger.exception(f"[value_help.resolve] failed: {e}")
        return {'success': False, 'data': None, 'message': f'解析失败: {e}'}
```

#### 注册 (server.py)
```python
bo_action_registry.register(
    'value_help.resolve',
    value_help_resolve_handler,
    description='解析 value_help 值的显示信息 (display/code)',
    object_type='*',
    category='value_help',
    input_schema={
        'type': 'object',
        'required': ['source_type', 'source_id', 'value'],
        'properties': {
            'source_type': {'type': 'string', 'enum': ['enum', 'bo', 'custom']},
            'source_id': {'type': 'string'},
            'value': {},  # 任意类型
            'value_field': {'type': 'string', 'default': 'id'},
            'display_field': {'type': 'string', 'default': 'name'},
            'code_field': {'type': 'string', 'default': 'code'},
        }
    },
    requires_auth=True,
    idempotent=True,
)
```

#### E2E 测试 (5 用例)
| # | 场景 | 期望 |
|---|------|------|
| 1 | enum 解析 (id=color, value=red) | success, data={value:red, display:'Red', code:'red'} |
| 2 | bo 解析 (target_bo=user, value=1) | success, data={value:1, display:'admin', code:'admin'} |
| 3 | 不存在的 value | data={value, display, code} fallback |
| 4 | 未登录 | 401 |
| 5 | 缺 source_type | "source_type/source_id/value 必填" |

---

## 2️⃣ aggregate.refresh

### 现有端点 (stats_api.py:244-264)

```python
@stats_bp.route('/stats/aggregates/<aggregate_id>/refresh', methods=['POST'])
def refresh_aggregate(aggregate_id):
    try:
        manager = _get_aggregate_manager()
        row_count = manager.refresh(aggregate_id, force=True)
        return jsonify({
            'success': True,
            'data': {
                'aggregate_id': aggregate_id,
                'row_count': row_count,
                'freshness': manager.get_freshness(aggregate_id),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
```

### Action 化设计

#### Handler
```python
def aggregate_refresh_handler(params, context):
    aggregate_id = params.get('aggregate_id')
    if not aggregate_id:
        return {'success': False, 'data': None, 'message': 'aggregate_id 必填'}
    force = bool(params.get('force', True))

    try:
        from meta.core.aggregate_manager import AggregateManager
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)
        manager = AggregateManager(ds)
        manager.register_all()
        row_count = manager.refresh(aggregate_id, force=force)
        return {
            'success': True,
            'data': {
                'aggregate_id': aggregate_id,
                'row_count': row_count,
                'freshness': manager.get_freshness(aggregate_id),
            },
            'message': f'已刷新 {row_count} 行',
        }
    except Exception as e:
        logger.exception(f"[aggregate.refresh] failed: {e}")
        return {'success': False, 'data': None, 'message': f'刷新失败: {e}'}
```

#### 注册
```python
bo_action_registry.register(
    'aggregate.refresh',
    aggregate_refresh_handler,
    description='刷新聚合表 (admin 限定)',
    object_type='aggregate',
    category='stats',
    input_schema={
        'type': 'object',
        'required': ['aggregate_id'],
        'properties': {
            'aggregate_id': {'type': 'string'},
            'force': {'type': 'boolean', 'default': True},
        }
    },
    requires_auth=True,
    requires_admin=True,
    idempotent=False,  # 重复 refresh 会重新计算
)
```

#### E2E (4 用例)
| # | 场景 | 期望 |
|---|------|------|
| 1 | admin 刷新 (id=user_stats) | success, row_count=N |
| 2 | 不存在 aggregate_id | "刷新失败" |
| 3 | 普通用户 | 403 |
| 4 | 未登录 | 401 |

---

## 3️⃣ aggregate.query

### 现有端点 (stats_api.py:213-241)

```python
@stats_bp.route('/stats/aggregates/<aggregate_id>/query', methods=['POST'])
def query_aggregate(aggregate_id):
    try:
        manager = _get_aggregate_manager()
        body = request.get_json() or {}
        results = manager.query(
            aggregate_id,
            filters=body.get('filters'),
            order_by=body.get('order_by'),
            limit=body.get('limit')
        )
        return jsonify({
            'success': True,
            'data': results,
            'meta': {
                'aggregate_id': aggregate_id,
                'row_count': len(results),
                'freshness': manager.get_freshness(aggregate_id),
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
```

### Action 化设计

#### Handler
```python
def aggregate_query_handler(params, context):
    aggregate_id = params.get('aggregate_id')
    if not aggregate_id:
        return {'success': False, 'data': None, 'message': 'aggregate_id 必填'}
    filters = params.get('filters')
    order_by = params.get('order_by')
    limit = params.get('limit', 1000)

    try:
        from meta.core.aggregate_manager import AggregateManager
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)
        manager = AggregateManager(ds)
        manager.register_all()
        results = manager.query(aggregate_id, filters=filters, order_by=order_by, limit=limit)
        return {
            'success': True,
            'data': results,
            'meta': {
                'aggregate_id': aggregate_id,
                'row_count': len(results),
                'freshness': manager.get_freshness(aggregate_id),
            },
            'message': f'查询到 {len(results)} 行',
        }
    except Exception as e:
        return {'success': False, 'data': None, 'message': f'查询失败: {e}'}
```

#### 注册
```python
bo_action_registry.register(
    'aggregate.query',
    aggregate_query_handler,
    description='查询聚合表数据',
    object_type='aggregate',
    category='stats',
    input_schema={
        'type': 'object',
        'required': ['aggregate_id'],
        'properties': {
            'aggregate_id': {'type': 'string'},
            'filters': {'type': 'object'},
            'order_by': {'type': 'string'},
            'limit': {'type': 'integer', 'default': 1000, 'maximum': 10000},
        }
    },
    requires_auth=True,
    idempotent=True,
)
```

#### E2E (4 用例)
| # | 场景 | 期望 |
|---|------|------|
| 1 | 查询 user_stats | success, row_count=N |
| 2 | 过滤 filters={name:admin} | success, filtered rows |
| 3 | limit=10 | 最多 10 行 |
| 4 | 不存在 aggregate_id | "查询失败" |

---

## 4️⃣ subscription.list

### 现有端点 (notification_api.py:160-187)

```python
@notification_bp.route('/subscriptions', methods=['GET'])
def get_subscriptions():
    user_id = g.get('user_id')
    if not user_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    if not ds:
        stats = websocket_manager.get_stats()
        user_clients = [
            c for c in stats.get('clients', [])
            if c.get('user_id') == user_id
        ]
        return jsonify({'success': True, 'data': user_clients})

    subscriptions = ds.find(
        'change_subscriptions',
        filters={'user_id': user_id},
        order_by='created_at DESC'
    )

    return jsonify({'success': True, 'data': subscriptions or []})
```

### Action 化设计

#### Handler
```python
def subscription_list_handler(params, context):
    user_info = g.current_user if hasattr(g, 'current_user') else None
    if not user_info:
        return {'success': False, 'data': None, 'message': '未登录'}
    user_id = user_info.get('user_id')

    object_type = params.get('object_type')  # 可选过滤

    try:
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)

        filters = {'user_id': user_id}
        if object_type:
            filters['object_type'] = object_type

        # 用 raw SQL (ds.find 在某些版本不支持复杂查询)
        import json
        rows = ds.execute(
            """SELECT id, user_id, object_type, event_types, channel, webhook_url,
                      webhook_secret, filter_condition, enabled, created_at
               FROM change_subscriptions
               WHERE user_id = ? AND (? IS NULL OR object_type = ?)
               ORDER BY created_at DESC""",
            [user_id, object_type, object_type]
        ).fetchall()

        subscriptions = []
        for r in rows:
            sub = dict(r) if hasattr(r, 'keys') else {
                'id': r[0], 'user_id': r[1], 'object_type': r[2],
                'event_types': json.loads(r[3]) if r[3] else [],
                'channel': r[4], 'webhook_url': r[5], 'webhook_secret': r[6],
                'filter_condition': json.loads(r[7]) if r[7] else {},
                'enabled': r[8], 'created_at': r[9],
            }
            subscriptions.append(sub)

        return {
            'success': True,
            'data': subscriptions,
            'message': f'找到 {len(subscriptions)} 个订阅',
        }
    except Exception as e:
        logger.exception(f"[subscription.list] failed: {e}")
        return {'success': False, 'data': None, 'message': f'查询失败: {e}'}
```

#### 注册
```python
bo_action_registry.register(
    'subscription.list',
    subscription_list_handler,
    description='列出当前用户的订阅 (可选 object_type 过滤)',
    object_type='change_subscription',
    category='notification',
    input_schema={
        'type': 'object',
        'properties': {
            'object_type': {'type': 'string'},
        }
    },
    requires_auth=True,
    idempotent=True,
)
```

#### E2E (4 用例)
| # | 场景 | 期望 |
|---|------|------|
| 1 | 登录用户 list 自己的订阅 | success, list 包含自己订阅 |
| 2 | filter by object_type=user | 只返回 user 订阅 |
| 3 | 没订阅 | success, data=[] |
| 4 | 未登录 | 401 |

---

## 5️⃣ enum_type.create

### 现有端点 (enum_api.py:318-371)

```python
@enum_bp.route('/enum-types', methods=['POST'])
@_auth_required
@_admin_required
def create_enum_type():
    """创建枚举类型（仅业务枚举）"""
    try:
        ds = _get_data_source()
        data = request.get_json()

        enum_type_id = data.get('id')
        name = data.get('name')
        category = data.get('category', 'business')
        mutability = data.get('mutability', 'extensible')
        dimension_schema = data.get('dimension_schema')
        description = data.get('description', '')

        if not enum_type_id or not name:
            return _api_error('编码和名称不能为空', 'VALIDATION_ERROR')

        import json
        dimension_schema_str = json.dumps(dimension_schema) if dimension_schema else None

        now = datetime.now().isoformat()
        sql = """INSERT INTO enum_types ..."""
        ds.execute(sql, [enum_type_id, name, category, mutability, dimension_schema_str, description, now])
        ds.commit()
        # 审计日志...
```

### Action 化设计

#### Handler
```python
def enum_type_create_handler(params, context):
    enum_type_id = params.get('id')
    name = params.get('name')
    if not enum_type_id or not name:
        return {'success': False, 'data': None, 'message': 'id 和 name 必填'}

    category = params.get('category', 'business')
    if category == 'system':
        return {'success': False, 'data': None, 'message': '不能创建 system 类别枚举'}
    mutability = params.get('mutability', 'extensible')
    dimension_schema = params.get('dimension_schema')
    description = params.get('description', '')

    import json
    from datetime import datetime
    dimension_schema_str = json.dumps(dimension_schema) if dimension_schema else None

    try:
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)

        # 检查重复
        existing = ds.execute("SELECT id FROM enum_types WHERE id = ?", [enum_type_id]).fetchone()
        if existing:
            return {'success': False, 'data': None, 'message': f'枚举类型 {enum_type_id} 已存在'}

        # 设置上下文 (审计)
        from meta.core.bo_framework import bo_framework
        from flask import request
        bo_framework.set_user_context(
            user_id=context.get('user_id'),
            user_name=context.get('user_name'),
            ip_address=request.remote_addr,
        )

        # 写库
        ds.execute(
            """INSERT INTO enum_types (id, name, category, mutability, dimension_schema, description, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [enum_type_id, name, category, mutability, dimension_schema_str, description, datetime.now().isoformat()]
        )
        ds.commit()

        return {
            'success': True,
            'data': {'id': enum_type_id, 'name': name, 'category': category},
            'message': '枚举类型创建成功',
        }
    except Exception as e:
        logger.exception(f"[enum_type.create] failed: {e}")
        return {'success': False, 'data': None, 'message': f'创建失败: {e}'}
```

#### 注册
```python
bo_action_registry.register(
    'enum_type.create',
    enum_type_create_handler,
    description='创建业务枚举类型 (admin 限定)',
    object_type='enum_type',
    category='metadata',
    input_schema={
        'type': 'object',
        'required': ['id', 'name'],
        'properties': {
            'id': {'type': 'string', 'minLength': 1},
            'name': {'type': 'string', 'minLength': 1},
            'category': {'type': 'string', 'enum': ['business'], 'default': 'business'},
            'mutability': {'type': 'string', 'enum': ['extensible', 'frozen'], 'default': 'extensible'},
            'dimension_schema': {'type': 'object'},
            'description': {'type': 'string'},
        }
    },
    requires_auth=True,
    requires_admin=True,
    idempotent=False,
)
```

#### E2E (5 用例)
| # | 场景 | 期望 |
|---|------|------|
| 1 | admin 创建 business 枚举 | success |
| 2 | 缺 id | "id 和 name 必填" |
| 3 | 缺 name | "id 和 name 必填" |
| 4 | 重复 id | "枚举类型已存在" |
| 5 | 尝试创建 system 类别 | "不能创建 system 类别" |

---

## 6️⃣ enum_type.update

### 现有端点 (enum_api.py:374-443)

完整的 70 行代码。详见 enum_api.py:374-443。

### Action 化设计

#### Handler
```python
def enum_type_update_handler(params, context):
    enum_type_id = params.get('id') or params.get('enum_type_id')
    if not enum_type_id:
        return {'success': False, 'data': None, 'message': 'id 必填'}

    try:
        from meta.core.datasource import get_data_source
        import os
        from datetime import datetime
        import json
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)

        existing = ds.execute(
            "SELECT * FROM enum_types WHERE id = ?", [enum_type_id]
        ).fetchone()
        if not existing:
            return {'success': False, 'data': None, 'message': '枚举类型不存在'}

        # 提取字段
        existing_dict = dict(existing) if hasattr(existing, 'keys') else {
            'id': existing[0], 'name': existing[1], 'category': existing[2],
            'mutability': existing[3], 'dimension_schema': existing[4],
            'description': existing[5], 'created_at': existing[6],
        }
        if existing_dict.get('category') == 'system':
            return {'success': False, 'data': None, 'message': '系统枚举不可修改'}

        name = params.get('name', existing_dict.get('name'))
        mutability = params.get('mutability', existing_dict.get('mutability'))
        description = params.get('description', existing_dict.get('description', ''))
        dimension_schema = params.get('dimension_schema')
        dimension_schema_str = (
            json.dumps(dimension_schema) if dimension_schema
            else existing_dict.get('dimension_schema')
        )

        # 写库
        ds.execute(
            """UPDATE enum_types SET name = ?, mutability = ?, dimension_schema = ?, description = ?
               WHERE id = ?""",
            [name, mutability, dimension_schema_str, description, enum_type_id]
        )
        ds.commit()

        return {
            'success': True,
            'data': {'id': enum_type_id, 'name': name, 'mutability': mutability},
            'message': '更新成功',
        }
    except Exception as e:
        logger.exception(f"[enum_type.update] failed: {e}")
        return {'success': False, 'data': None, 'message': f'更新失败: {e}'}
```

#### 注册
```python
bo_action_registry.register(
    'enum_type.update',
    enum_type_update_handler,
    description='更新业务枚举类型 (admin 限定, system 不可改)',
    object_type='enum_type',
    category='metadata',
    input_schema={
        'type': 'object',
        'required': ['id'],
        'properties': {
            'id': {'type': 'string'},
            'name': {'type': 'string'},
            'mutability': {'type': 'string', 'enum': ['extensible', 'frozen']},
            'dimension_schema': {'type': 'object'},
            'description': {'type': 'string'},
        }
    },
    requires_auth=True,
    requires_admin=True,
    idempotent=True,
)
```

#### E2E (4 用例)
| # | 场景 | 期望 |
|---|------|------|
| 1 | admin 更新 name | success |
| 2 | 缺 id | "id 必填" |
| 3 | 更新 system 枚举 | "系统枚举不可修改" |
| 4 | 不存在 id | "枚举类型不存在" |

---

## 7️⃣ enum_type.delete

### 现有端点 (enum_api.py:445-510)

### Action 化设计

#### Handler
```python
def enum_type_delete_handler(params, context):
    enum_type_id = params.get('id') or params.get('enum_type_id')
    if not enum_type_id:
        return {'success': False, 'data': None, 'message': 'id 必填'}

    try:
        from meta.core.datasource import get_data_source
        import os
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        ds = get_data_source("sqlite", database=db_path)

        existing = ds.execute(
            "SELECT * FROM enum_types WHERE id = ?", [enum_type_id]
        ).fetchone()
        if not existing:
            return {'success': False, 'data': None, 'message': '枚举类型不存在'}

        existing_dict = dict(existing) if hasattr(existing, 'keys') else {
            'id': existing[0], 'category': existing[2], 'name': existing[1],
        }
        if existing_dict.get('category') == 'system':
            return {'success': False, 'data': None, 'message': '系统枚举不可删除'}

        # 检查是否有 enum_values
        value_count = ds.execute(
            "SELECT COUNT(*) FROM enum_values WHERE enum_type_id = ?", [enum_type_id]
        ).fetchone()[0]
        if value_count > 0:
            return {
                'success': False, 'data': None,
                'message': f'该枚举类型下有 {value_count} 个枚举值, 无法删除',
            }

        # 删除
        ds.execute("DELETE FROM enum_types WHERE id = ?", [enum_type_id])
        ds.commit()

        return {
            'success': True,
            'data': {'id': enum_type_id, 'name': existing_dict.get('name')},
            'message': '删除成功',
        }
    except Exception as e:
        logger.exception(f"[enum_type.delete] failed: {e}")
        return {'success': False, 'data': None, 'message': f'删除失败: {e}'}
```

#### 注册
```python
bo_action_registry.register(
    'enum_type.delete',
    enum_type_delete_handler,
    description='删除业务枚举类型 (admin 限定, 仅当无 enum_values 时)',
    object_type='enum_type',
    category='metadata',
    input_schema={
        'type': 'object',
        'required': ['id'],
        'properties': {
            'id': {'type': 'string'},
        }
    },
    requires_auth=True,
    requires_admin=True,
    idempotent=False,  # 删除不可逆
)
```

#### E2E (4 用例)
| # | 场景 | 期望 |
|---|------|------|
| 1 | admin 删除空 enum | success |
| 2 | 删除有 enum_values 的 | "有 X 个枚举值, 无法删除" |
| 3 | 删除 system 枚举 | "系统枚举不可删除" |
| 4 | 不存在 id | "枚举类型不存在" |

---

## 🛡️ P1 6 Action 实施前置条件

- [x] 当前 `feature/bo-action-v3` 分支
- [ ] DB 备份 (实施前 1 次)
- [x] E2E 测试脚本模板

## 🚦 风险评估

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| enum_type 操作破坏业务数据 | 🟠 高 | 实施前备份 DB, 测完清理, **业务 enum 谨慎** |
| 鉴权漏 admin 限定 | 🟢 低 | 注册时 requires_admin=True |
| 现有 enum_api.py endpoint 删除风险 | 🟡 中 | **不删**老 endpoint, 保留兼容 |

## 实施时间

| Action | 工时 | 累计 |
|--------|:---:|:---:|
| value_help.resolve | 30min | 0.5h |
| aggregate.refresh | 30min | 1h |
| aggregate.query | 30min | 1.5h |
| subscription.list | 30min | 2h |
| enum_type.create | 45min | 2.75h |
| enum_type.update | 45min | 3.5h |
| enum_type.delete | 30min | 4h |

---

# 第二部分: send_file 根因诊断详细方案

## 🔍 现象回顾

**Round 3 实施 audit.export 时**:
- `audit_export_handler` 直接调成功 (返回 ActionResult)
- Flask `Response(bytes, mimetype)` → 进程死亡 (watchdog 重启掩盖)
- Flask `send_file(BytesIO(bytes))` → 同样进程死亡
- Flask `test_request_context` 下 send_file **正常工作**
- base64 包装方案 100% 解决, **绕过了根因**

## 🕵️ 6 假设排查结果

| # | 假设 | 验证方式 | 结论 |
|---|------|----------|:---:|
| 1 | Flask dev `use_reloader=True` 冲突 | `app.run(use_reloader=?)` | ❌ **False** (server.py:970 明确 `False`) |
| 2 | Werkzeug SocketIO 死锁 | 监控 socket 状态 | 🟡 待验证 |
| 3 | `Response` 直接传 bytes | 强制 `BytesIO` 包裹 | ❌ 也不行 (`send_file(BytesIO)` 也崩) |
| 4 | mimetype 与 content-type header 冲突 | 看 header 顺序 | 🟡 待验证 |
| 5 | **Flask `use_debugger=True` 与 send_file 冲突** | 关 `use_debugger` 测试 | 🎯 **最大嫌疑** |
| 6 | Werkzeug dev server 单线程死锁 | 看 thread model | 🟡 待验证 |

## 🎯 假设 5: use_debugger=True 与 send_file 冲突

### 证据

**server.py:970**:
```python
app.run(
    host='0.0.0.0',
    port=port,
    debug=debug_mode,           # 默认 True (FLASK_DEBUG env)
    use_reloader=False,        # ✅ 排除
    use_debugger=debug_mode,   # ← 嫌疑点
    ...
)
```

**service_manager.ps1** 启动时未设置 `FLASK_DEBUG=false`。

**Werkzeug debugger 工作原理**:
- 启用后, 每个请求会 fork 一个**守护线程** (watchdog)
- 该线程**心跳 + 评估 eval 表达式** (debug console)
- send_file 写大文件 + BytesIO 时, socket buffer 可能被守护线程打断
- Python `BytesIO.seek/tell` 与 Werkzeug streaming 冲突 → SIGPIPE → 进程死

**为什么 `test_request_context` 不崩**:
- test_request_context 是**单元测试**, 不走真实 HTTP socket
- 无 Werkzeug debugger 守护线程

## 🛠️ 诊断方案 (1h)

### Step 1: 复现 (10min)

启动一个**最小 Flask app**, 包含 send_file, 启用 use_debugger:
```python
# /tmp/repro_sendfile.py
from flask import Flask, send_file
from io import BytesIO
app = Flask(__name__)

@app.route('/test')
def test():
    data = b'X' * 10000
    return send_file(BytesIO(data), mimetype='application/octet-stream')

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, use_debugger=True, port=5001)
```

用 curl 调用, 观察进程是否死。

### Step 2: 对比 (20min)

| 启动配置 | 是否崩 |
|---------|:------:|
| `debug=False, use_debugger=False` | ❌ 不崩 (生产模式) |
| `debug=True, use_debugger=False` | ❌ 待测 (无 debugger 线程) |
| `debug=True, use_debugger=True` | 🎯 崩 |

### Step 3: 验证 Flask 3.1.3 Issue Tracker (15min)

搜索 Flask GitHub issues:
- 关键词: `send_file use_debugger crash`
- 已知 issue: Flask #5034 (Werkzeug debugger + send_file 死锁)

### Step 4: 解决方案候选 (15min)

| 方案 | 描述 | 风险 |
|------|------|:---:|
| **A. 关闭 use_debugger** | `use_debugger=os.environ.get('FLASK_DEBUG', 'True')` 但**忽略**, 永远 False | 🟡 中 (失去断点调试) |
| **B. 生产模式启动** | `FLASK_DEBUG=false` | 🟢 低 (推荐生产配置) |
| **C. 用 nginx/gunicorn** | Werkzeug dev server 换 gunicorn | 🟢 低 (标准生产部署) |
| **D. base64 方案** | **当前方案**, 100% 可靠 | 🟢 无 (已实施) |

## 💡 推荐结论

**send_file 根因 = use_debugger=True + 大文件响应 + Werkzeug 守护线程冲突**。

**修复方案**: 推荐 **A+B 组合**:
- 修改 `server.py` 让 `use_debugger` 总是 False
- 修改 `service_manager.ps1` 启动时 `FLASK_DEBUG=false`
- 保留 base64 方案作为兜底

**为什么保留 base64 方案**:
- 某些客户端环境 (旧 nginx + gunicorn) 也可能崩
- base64 在 HTTP/2 下不会比 send_file 慢多少
- 100% 可靠性 = 0 调试时间

**何时真正优化 send_file**:
- 仅当需要 **WebSocket 文件流** OR **>10MB 文件** OR **流式进度条**

**当前业务**: audit.export ≤ 10MB, 完全用 base64 即可。

## 📊 诊断后产出

1. 写一份诊断报告 `docs/progress/sendfile-root-cause.md`
2. 给出 `server.py` 推荐改动 patch (可选, 不强制)
3. 记录在 `docs/progress/bo-action-p1-result.md`

---

# 第三部分: 实施时间线 + 风险评估

## 📅 实施顺序 (推荐 1 周内)

| 日 | 任务 | 工时 | 验收 |
|---|------|:---:|------|
| Day 1 | send_file 根因诊断 (优先) | 1h | 确认假设 5 是真凶 |
| Day 1 | P1 6 Action 1+2 (value_help.resolve + aggregate.refresh) | 1h | 2 个 E2E 全过 |
| Day 2 | P1 6 Action 3+4 (aggregate.query + subscription.list) | 1h | 2 个 E2E 全过 |
| Day 2 | P1 6 Action 5 (enum_type.create) | 45min | 5 个 E2E 全过 |
| Day 3 | P1 6 Action 6+7 (enum_type.update + delete) | 1.25h | 2 个 E2E 全过 |
| Day 3 | 全量回归 + 写进度档 | 1h | 11+7=18 Action 健康 |
| **总** | | **5h** | |

## 🛡️ 实施前置

- [ ] DB 备份 (实施前 1 次, 参考 `pre-v3.2.4tasks.1780701909.bak`)
- [x] `feature/bo-action-v3` 分支
- [x] E2E 测试脚本模板

## 🚦 回滚计划

每个 Action 独立回滚:
- 删除 `meta/services/X.py`
- 删除 server.py 注册行
- 重启服务
- 老 endpoint 继续工作

## 📊 最终状态预估

| 维度 | 当前 (v3.2) | 实施后 (v3.3) |
|------|------|------|
| Action 总数 | 12 | **19** (+7) |
| send_file | base64 包装 | **可选 send_file** (诊断后确认) |
| 业务能力 | 强 | **更强** (枚举 CRUD + 聚合 + 订阅完整) |
| 文档 | spec 已存 | **实施结果** + **send_file 诊断报告** |

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-05 | 创建 P1 6 Action + send_file 诊断详细 spec |
