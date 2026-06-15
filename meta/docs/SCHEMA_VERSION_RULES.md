# SCHEMA_VERSION_RULES.md

> **Schema 版本管理规则文档**
> 版本: v1.0
> 创建: 2026-06-14
> BMRD DEFER ID: SCHEMA-VERSION

## 1. 概述

系统使用**基于 MD5 hash** 的 schema 版本号 (12 字符截断)。
版本号基于 `meta/schemas/*.yaml` 文件内容计算。

## 2. Schema 类型

系统支持 3 种 schema:
| 类型 | 端点 | 用途 |
|------|------|------|
| `form_schema` | 内嵌在 `ui-config` | 详情页表单字段定义 |
| `list_schema` | 内嵌在 `ui-config` | 列表页列定义 |
| `ui_schema` | 内嵌在 `ui-config` | UI 元素配置 (按钮/对话框/标签页) |

### 2.1 实际端点
| 端点 | 状态 | 说明 |
|------|------|------|
| `/api/v2/meta/schema-version` | ✅ 200 | 返回 schema_version hash |
| `/api/v2/meta/<object_type>/ui-config` | ✅ 200 | 返回 object_type 的完整 UI config (含 form/list/ui) |
| `/api/v2/meta/form_schema` | ❌ 500 | 路由未单独注册 (使用 ui-config) |
| `/api/v2/meta/list_schema` | ❌ 500 | 路由未单独注册 (使用 ui-config) |
| `/api/v2/meta/ui_schema` | ❌ 500 | 路由未单独注册 (使用 ui-config) |

**结论**: 实际架构是 **ui-config = form_schema + list_schema + ui_schema 合一**，不是 3 个独立端点。

## 3. Schema Version 计算

### 3.1 关键代码 (`bo_api.py:201`)
```python
@meta_v2_bp.route('/schema-version', methods=['GET'])
def get_schema_version():
    import hashlib
    from datetime import datetime

    schema_dir = os.path.join(os.path.dirname(...), 'schemas')
    hasher = hashlib.md5()

    try:
        for filename in sorted(os.listdir(schema_dir)):
            if filename.endswith('.yaml') and not filename.startswith('_'):
                filepath = os.path.join(schema_dir, filename)
                with open(filepath, 'rb') as f:
                    hasher.update(f.read())
    except Exception as e:
        logger.warning(f"[schema-version] failed to hash schemas: {e}")
        hasher.update(str(datetime.now().date()).encode())

    return jsonify({
        'success': True,
        'data': {
            'schema_version': hasher.hexdigest()[:12],  # 12 字符截断
            'timestamp': datetime.now().isoformat()
        }
    })
```

### 3.2 计算规则
- **算法**: MD5
- **输入**: `meta/schemas/` 下所有 `.yaml` 文件 (排除 `_` 开头)
- **排序**: 按文件名**字典序**排序 (保证一致性)
- **输出**: 12 字符截断 (例: `0cc2cb95bc82`)

### 3.3 响应格式
```json
{
  "success": true,
  "data": {
    "schema_version": "0cc2cb95bc82",
    "timestamp": "2026-06-14T11:04:44.553568"
  }
}
```

## 4. 缓存机制

### 4.1 客户端缓存
- 前端应缓存 `schema_version` 在 localStorage / Vuex
- 每次页面加载时, 对比**当前** vs **缓存**:
  - **相同**: 直接使用缓存的 UI config
  - **不同**: 重新拉取 ui-config + 更新缓存

### 4.2 示例代码 (前端)
```javascript
async function checkSchemaVersion() {
  const resp = await fetch('/api/v2/meta/schema-version')
  const data = await resp.json()
  const newVersion = data.data.schema_version
  
  const cached = localStorage.getItem('schema_version')
  if (cached !== newVersion) {
    // Schema 已变更, 清除 UI config 缓存
    localStorage.removeItem('ui_config_cache')
    localStorage.setItem('schema_version', newVersion)
    // 通知用户刷新或自动重载
    if (cached) {
      console.warn('[SCHEMA] Version changed:', cached, '->', newVersion)
    }
  }
}
```

## 5. UI Config 端点

### 5.1 端点
```
GET /api/v2/meta/<object_type>/ui-config
```

### 5.2 响应 (例: enum_type)
```json
{
  "success": true,
  "data": {
    "actions": [...],
    "fields": [
      {
        "field_name": "code",
        "field_type": "string",
        "required": true,
        "label": "编码",
        "max_length": 50
      },
      {
        "field_name": "name",
        "field_type": "string",
        "required": true,
        "label": "名称"
      }
    ],
    "layout": {
      "sections": [...],
      "tabs": [...]
    },
    "list_columns": [
      {"field": "code", "label": "编码", "width": 120},
      {"field": "name", "label": "名称", "width": 200}
    ]
  }
}
```

### 5.3 关键代码 (`bo_api.py:1462`)
```python
@meta_v2_bp.route('/<object_type>/ui-config', methods=['GET'])
@login_required
def get_ui_config(object_type):
    try:
        bo = _get_bo()
        config = bo.get_ui_config(object_type)
        if config:
            json_safe_config = _make_json_safe(config)
            return jsonify({'success': True, 'data': json_safe_config})
        return jsonify({'success': False, 'message': f'Unknown object type: {object_type}'}), 404
    except Exception as e:
        ...
```

## 6. Schema 文件组织

### 6.1 目录
```
meta/schemas/
├── _pm_boundary.yaml          # 边界定义 (排除, 不计入 hash)
├── enum_type.yaml             # 枚举类型
├── enum_value.yaml            # 枚举值
├── business_object.yaml       # 业务对象
├── user.yaml                  # 用户
├── role.yaml                  # 角色
├── permission.yaml            # 权限
└── ... (~50+ 文件)
```

### 6.2 排除规则
- 文件名以 `_` 开头 → **不计入 hash**
- 非 `.yaml` 后缀 → **不计入 hash**
- 不存在的目录 → fallback to date string

## 7. 版本变更检测

### 7.1 何时变更
- 任何 `meta/schemas/*.yaml` 文件**内容变更**
- **新增** yaml 文件
- **删除** yaml 文件 (前提是非 `_` 开头)
- **重命名** yaml 文件

### 7.2 不变更
- 修改 `_` 开头的 yaml (例: `_pm_boundary.yaml`)
- 修改 `meta/api/*.py` 代码
- 修改数据库 schema
- 修改前端代码

## 8. 已知限制

| 限制 | 原因 | 解决方案 |
|------|------|----------|
| 无细粒度版本 (只 total hash) | 简单实现 | P2: 改为 JSON-based version |
| 12 字符 MD5 可能冲突 | 空间 16^12 = 281T | 接受碰撞概率极低 |
| 不支持 schema 回滚 | 简单 | P2: 引入 Git 同步机制 |
| 前端缓存无失效机制 | 设计取舍 | P2: ETag / Last-Modified |

## 9. 未来规划

- [ ] ETag 头支持 (减少不必要 schema-version 请求)
- [ ] 单文件级版本 (定位变更文件)
- [ ] Schema 变更通知 (webhook)
- [ ] Schema diff 可视化

## 10. BMRD 规则

| 规则 ID | 状态 | 说明 |
|---------|------|------|
| SCHEMA-1 | ACTIVE | form_schema / ui-config 端点 |
| SCHEMA-2 | ACTIVE | list_schema / ui-config 端点 |
| SCHEMA-3 | ACTIVE | ui_schema / ui-config 端点 |
| SCHEMA-VERSION | 🟡 DEFER (文档化完成) | 等前端实现缓存机制后改 ACTIVE |

## 11. 解锁条件

SCHEMA-VERSION DEFER → ACTIVE:
- [x] 文档化完成 ✅
- [x] 关键代码确认 ✅ (`/api/v2/meta/schema-version` 200 OK)
- [x] 端点确认 ✅ (ui-config 200 OK)
- [x] 计算规则确认 ✅ (MD5 of yaml files, 12 chars)
- [x] BMRD 规则引用 ✅
- [ ] 解锁: 改 `_masterdata_schema_workflow_rules.yaml` 中 `SCHEMA-VERSION` 为 ACTIVE
- [ ] (可选) 前端实现缓存 + 版本检测逻辑

## 12. 测试覆盖

- `meta/tests/test_bo_api.py` (端点测试)
- `meta/tests/test_schema_version.py` (待建)

## 13. 参考

- 后端核心: `meta/api/bo_api.py:201` (get_schema_version)
- 后端核心: `meta/api/bo_api.py:1462` (get_ui_config)
- Schema 目录: `meta/schemas/`
- BMRD 规则: `.trae/specs/_business_rules/_masterdata_schema_workflow_rules.yaml`
