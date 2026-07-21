# v1 API 端点状态清单

> 自动生成于 `audit_v1_endpoints.py`，请勿手工编辑。
> 重新生成: `python scripts/audit_v1_endpoints.py`

## 一、概览

- **v1 端点总数**: 270
- **v2 端点总数**: 96

### v1 端点状态分布

| 状态 | 数量 | 占比 | 说明 |
|------|------|------|------|
| ACTIVE | 192 | 71.1% | 正常使用，无废弃标记 |
| DEPRECATED | 25 | 9.3% | 可用但警告，前端应迁移 |
| SUNSET | 53 | 19.6% | 已下线，返回 410 |
| REMOVED | 0 | 0.0% | 已删除，返回 404 |

## 二、需要前端迁移的端点

| 状态 | URL | 方法 | 迁移到 | 下线日期 | Blueprint |
|------|-----|------|--------|---------|-----------|
| SUNSET | `/api/v1/relationships` | GET, POST | `/api/v2/bo/relationships` | - | special |
| SUNSET | `/api/v1/business_object/<int:obj_id>/relations` | GET | `/api/v2/bo/business_object/<int:obj_id>/relations` | - | special |
| SUNSET | `/api/v1/<object_type>` | POST | `/api/v2/bo/<object_type>` | - | manage |
| SUNSET | `/api/v1/<object_type>/deep` | POST | `/api/v2/bo/<object_type>/deep` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>` | GET | `/api/v2/bo/<object_type>/<id>` | - | manage |
| SUNSET | `/api/v1/<object_type>` | GET | `/api/v2/bo/<object_type>` | - | manage |
| SUNSET | `/api/v1/<object_type>/list` | POST | `/api/v2/bo/<object_type>/list` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>` | PUT | `/api/v2/bo/<object_type>/<id>` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>` | DELETE | `/api/v2/bo/<object_type>/<id>` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>/recover` | POST | `/api/v2/bo/<object_type>/<id>/recover` | - | manage |
| SUNSET | `/api/v1/<object_type>/deleted` | GET | `/api/v2/bo/<object_type>/deleted` | - | manage |
| SUNSET | `/api/v1/<object_type>/batch-create` | POST | `/api/v2/bo/<object_type>/batch-create` | - | manage |
| SUNSET | `/api/v1/<object_type>/batch-update` | POST | `/api/v2/bo/<object_type>/batch-update` | - | manage |
| SUNSET | `/api/v1/<object_type>/batch-delete` | POST | `/api/v2/bo/<object_type>/batch-delete` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>/actions` | GET | `/api/v2/bo/<object_type>/<id>/actions` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>/actions/<action_id>` | POST | `/api/v2/bo/<object_type>/<id>/actions/<action_id>` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>/state_transitions` | GET | `/api/v2/bo/<object_type>/<id>/state_transitions` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>/state_history` | GET | `/api/v2/bo/<object_type>/<id>/state_history` | - | manage |
| SUNSET | `/api/v1/<object_type>/<id>/stage_metrics` | GET | `/api/v2/bo/<object_type>/<id>/stage_metrics` | - | manage |
| SUNSET | `/api/v1/meta/objects` | GET | `/api/v2/bo/meta/objects` | - | meta |
| SUNSET | `/api/v1/meta/objects/<object_type>` | GET | `/api/v2/bo/meta/objects/<object_type>` | - | meta |
| SUNSET | `/api/v1/meta/<object_type>/view-config` | GET | `/api/v2/bo/meta/<object_type>/view-config` | - | meta |
| SUNSET | `/api/v1/meta/<object_type>/view-config/<view_name>` | GET | `/api/v2/bo/meta/<object_type>/view-config/<view_name>` | - | meta |
| SUNSET | `/api/v1/meta/<object_type>/list-view` | GET | `/api/v2/bo/meta/<object_type>/list-view` | - | meta |
| SUNSET | `/api/v1/meta/<object_type>/detail-view` | GET | `/api/v2/bo/meta/<object_type>/detail-view` | - | meta |
| SUNSET | `/api/v1/meta/<object_type>/form-view` | GET | `/api/v2/bo/meta/<object_type>/form-view` | - | meta |
| SUNSET | `/api/v1/meta/reload` | POST | `/api/v2/bo/meta/reload` | - | meta |
| SUNSET | `/api/v1/meta/i18n/<locale>` | GET | `/api/v2/bo/meta/i18n/<locale>` | - | meta |
| SUNSET | `/api/v1/meta/<object_type>/filter-config` | GET | `/api/v2/bo/meta/<object_type>/filter-config` | - | meta |
| SUNSET | `/api/v1/meta/<object_type>/filter-tree/<filter_key>` | GET | `/api/v2/bo/meta/<object_type>/filter-tree/<filter_key>` | - | meta |
| SUNSET | `/api/v1/users` | GET | `/api/v2/bo/user` | - | user |
| SUNSET | `/api/v1/users` | POST | `/api/v2/bo/user` | - | user |
| SUNSET | `/api/v1/users/<int:user_id>` | GET | `/api/v2/bo/user` | - | user |
| SUNSET | `/api/v1/users/<int:user_id>` | PUT | `/api/v2/bo/user` | - | user |
| SUNSET | `/api/v1/users/<int:user_id>` | DELETE | `/api/v2/bo/user` | - | user |
| SUNSET | `/api/v1/data-permissions` | GET | `/api/v2/bo/data_permission` | - | data_permission |
| SUNSET | `/api/v1/data-permissions` | POST | `/api/v2/bo/data_permission` | - | data_permission |
| SUNSET | `/api/v1/data-permissions/<int:perm_id>` | DELETE | `/api/v2/bo/data_permission` | - | data_permission |
| SUNSET | `/api/v1/meta/cache-stats` | GET | `/api/v2/bo/meta/cache-stats` | - | management_dimension_meta |
| DEPRECATED | `/api/v1/user-groups/<int:group_id>/members` | GET | `/api/v2/bo/user_group/<group_id>/associations/members` | 2026-12-31 | user_group |
| DEPRECATED | `/api/v1/user-groups/<int:group_id>/members` | POST | `/api/v2/bo/user_group/<group_id>/associations/members` | 2026-12-31 | user_group |
| DEPRECATED | `/api/v1/user-groups/<int:group_id>/data-permissions` | GET | `/api/v2/bo/user_group/<group_id>/associations/roles` | 2026-12-31 | user_group |
| DEPRECATED | `/api/v1/user-groups/<int:group_id>/data-permissions` | POST | `/api/v2/bo/user_group/<group_id>/associations/roles` | 2026-12-31 | user_group |
| DEPRECATED | `/api/v1/user-groups/<int:group_id>/data-permissions/<int:perm_id>` | DELETE | `/api/v2/bo/user_group/<group_id>/associations/roles` | 2026-12-31 | user_group |
| DEPRECATED | `/api/v1/user-groups/<int:group_id>/roles` | GET | `/api/v2/bo/user_group/<group_id>/associations/roles` | 2026-12-31 | user_group |
| SUNSET | `/api/v1/permission-bundles` | GET | `/api/v2/bo/permission_bundle` | - | permission_bundle |
| SUNSET | `/api/v1/permission-bundles/<bundle_code>` | GET | `/api/v2/bo/permission_bundle` | - | permission_bundle |
| SUNSET | `/api/v1/permission-bundles` | POST | `/api/v2/bo/permission_bundle` | - | permission_bundle |
| SUNSET | `/api/v1/permission-bundles/<bundle_code>` | PUT | `/api/v2/bo/permission_bundle` | - | permission_bundle |
| SUNSET | `/api/v1/permission-bundles/<bundle_code>` | DELETE | `/api/v2/bo/permission_bundle` | - | permission_bundle |
| DEPRECATED | `/api/v1/permission-rules` | GET | `/api/v2/permission-rules` | 2026-12-31 | permission_rule |
| DEPRECATED | `/api/v1/permission-rules/<int:rule_id>` | GET | `/api/v2/permission-rules/<rule_id>` | 2026-12-31 | permission_rule |
| DEPRECATED | `/api/v1/permission-rules` | POST | `/api/v2/permission-rules` | 2026-12-31 | permission_rule |
| DEPRECATED | `/api/v1/permission-rules/<int:rule_id>` | PUT | `/api/v2/permission-rules/<rule_id>` | 2026-12-31 | permission_rule |
| DEPRECATED | `/api/v1/permission-rules/<int:rule_id>` | DELETE | `/api/v2/permission-rules/<rule_id>` | 2026-12-31 | permission_rule |
| DEPRECATED | `/api/v1/roles/<int:role_id>/overlaps` | GET | `/api/v2/roles/<int:role_id>/overlaps` | 2026-12-31 | overlap |
| DEPRECATED | `/api/v1/roles/<int:role_id>/overlaps/summary` | GET | `/api/v2/roles/<int:role_id>/overlaps/summary` | 2026-12-31 | overlap |
| DEPRECATED | `/api/v1/permissions/explain` | POST | `/api/v2/permissions/explain` | 2026-12-31 | permission_api |
| DEPRECATED | `/api/v1/permissions/check` | POST | `/api/v2/permissions/check` | 2026-12-31 | permission_api |
| DEPRECATED | `/api/v1/permissions/check_intent` | POST | `/api/v2/permissions/check_intent` | 2026-12-31 | intent_api |
| DEPRECATED | `/api/v1/bos` | GET | `/api/v2/bos` | 2026-12-31 | intent_api |
| DEPRECATED | `/api/v1/bos/<bo_id>/actions` | GET | `/api/v2/bos/<bo_id>/actions` | 2026-12-31 | intent_api |
| DEPRECATED | `/api/v1/bos/<bo_id>/actions/<action_name>` | GET | `/api/v2/bos/<bo_id>/actions/<action_name>` | 2026-12-31 | intent_api |
| DEPRECATED | `/api/v1/roles/<role_id>/intents` | GET | `/api/v2/roles/<role_id>/intents` | 2026-12-31 | intent_api |
| DEPRECATED | `/api/v1/roles/<role_id>/intents/<bo_id>/<action_name>` | PUT | `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` | 2026-12-31 | intent_api |
| DEPRECATED | `/api/v1/roles/<role_id>/intents/<bo_id>/<action_name>` | DELETE | `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` | 2026-12-31 | intent_api |
| SUNSET | `/api/v1/filter-variants` | GET | `/api/v2/bo/filter_variant` | - | filter_variant |
| SUNSET | `/api/v1/filter-variants/<int:variant_id>` | GET | `/api/v2/bo/filter_variant` | - | filter_variant |
| SUNSET | `/api/v1/filter-variants` | POST | `/api/v2/bo/filter_variant` | - | filter_variant |
| SUNSET | `/api/v1/filter-variants/<int:variant_id>` | PUT | `/api/v2/bo/filter_variant` | - | filter_variant |
| SUNSET | `/api/v1/filter-variants/<int:variant_id>` | DELETE | `/api/v2/bo/filter_variant` | - | filter_variant |
| DEPRECATED | `/api/v1/associations/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>` | POST | `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>/assign` | 2026-12-31 | association |
| DEPRECATED | `/api/v1/associations/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>` | DELETE | `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>/unassign` | 2026-12-31 | association |
| DEPRECATED | `/api/v1/associations/<source_type>/<int:source_id>/<association_name>` | GET | `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>` | 2026-12-31 | association |
| SUNSET | `/api/v1/associations/<entity_type>/<int:entity_id>` | DELETE | `/api/v2/bo/association` | - | association |
| SUNSET | `/api/v1/meta/objects` | GET | `/api/v2/bo/meta/objects` | - | meta_util |
| SUNSET | `/api/v1/meta/hierarchies` | GET | `/api/v2/bo/meta/hierarchies` | - | meta_util |
| SUNSET | `/api/v1/debug/current-user` | GET | `/api/v2/bo/debug/current-user` | - | debug |

## 三、v1 端点完整清单（按 Blueprint 分组）

### `agent` (3 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/agent/context/<object_type>` | GET | ACTIVE | `-` |
| `/api/v1/agent/schema` | GET | ACTIVE | `-` |
| `/api/v1/agent/tools` | GET | ACTIVE | `-` |

### `annotation` (6 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/annotations` | POST | ACTIVE | `-` |
| `/api/v1/annotations/<int:annotation_id>` | GET | ACTIVE | `-` |
| `/api/v1/annotations/<int:annotation_id>` | PUT | ACTIVE | `-` |
| `/api/v1/annotations/<int:annotation_id>` | DELETE | ACTIVE | `-` |
| `/api/v1/annotations/by-target` | GET | ACTIVE | `-` |
| `/api/v1/annotations/category-stats` | GET | ACTIVE | `-` |

### `association` (5 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/associations/<entity_type>/<int:entity_id>` | DELETE | SUNSET | `/api/v2/bo/association` |
| `/api/v1/associations/<entity_type>/deletion-policy` | GET | ACTIVE | `-` |
| `/api/v1/associations/<source_type>/<int:source_id>/<association_name>` | GET | DEPRECATED | `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>` |
| `/api/v1/associations/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>` | POST | DEPRECATED | `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>/assign` |
| `/api/v1/associations/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>` | DELETE | DEPRECATED | `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>/unassign` |

### `audit` (7 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/audit/failed` | GET | ACTIVE | `-` |
| `/api/v1/audit/logs` | GET | ACTIVE | `-` |
| `/api/v1/audit/logs/<int:log_id>` | GET | ACTIVE | `-` |
| `/api/v1/audit/logs/export` | GET | ACTIVE | `-` |
| `/api/v1/audit/overview` | GET | ACTIVE | `-` |
| `/api/v1/audit/retry/status` | GET | ACTIVE | `-` |
| `/api/v1/audit/retry/trigger` | POST | ACTIVE | `-` |

### `audit_mgmt` (3 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/audit/failed` | GET | ACTIVE | `-` |
| `/api/v1/audit/failed/<int:record_id>/retry` | POST | ACTIVE | `-` |
| `/api/v1/audit/stats` | GET | ACTIVE | `-` |

### `auth` (5 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/auth/change-password` | POST | ACTIVE | `-` |
| `/api/v1/auth/dev-login` | GET | ACTIVE | `-` |
| `/api/v1/auth/login` | POST | ACTIVE | `-` |
| `/api/v1/auth/logout` | POST | ACTIVE | `-` |
| `/api/v1/auth/me` | GET | ACTIVE | `-` |

### `data_permission` (6 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/data-permissions` | GET | SUNSET | `/api/v2/bo/data_permission` |
| `/api/v1/data-permissions` | POST | SUNSET | `/api/v2/bo/data_permission` |
| `/api/v1/data-permissions/<int:perm_id>` | DELETE | SUNSET | `/api/v2/bo/data_permission` |
| `/api/v1/data-permissions/batch` | POST | ACTIVE | `-` |
| `/api/v1/data-permissions/effective` | GET | ACTIVE | `-` |
| `/api/v1/data-permissions/self` | GET | ACTIVE | `-` |

### `database` (9 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/system/database/analyze` | POST | ACTIVE | `-` |
| `/api/v1/system/database/health` | GET | ACTIVE | `-` |
| `/api/v1/system/database/integrity-check` | POST | ACTIVE | `-` |
| `/api/v1/system/database/metrics` | GET | ACTIVE | `-` |
| `/api/v1/system/database/metrics/prometheus` | GET | ACTIVE | `-` |
| `/api/v1/system/database/reindex` | POST | ACTIVE | `-` |
| `/api/v1/system/database/slow-queries` | GET | ACTIVE | `-` |
| `/api/v1/system/database/vacuum` | POST | ACTIVE | `-` |
| `/api/v1/system/database/wal-checkpoint` | POST | ACTIVE | `-` |

### `debug` (1 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/debug/current-user` | GET | SUNSET | `/api/v2/bo/debug/current-user` |

### `enum` (13 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/enum-types` | GET | ACTIVE | `-` |
| `/api/v1/enum-types` | POST | ACTIVE | `-` |
| `/api/v1/enum-types/<enum_type_id>` | GET | ACTIVE | `-` |
| `/api/v1/enum-types/<enum_type_id>` | PUT | ACTIVE | `-` |
| `/api/v1/enum-types/<enum_type_id>` | DELETE | ACTIVE | `-` |
| `/api/v1/enum-types/<enum_type_id>/history` | GET | ACTIVE | `-` |
| `/api/v1/enum-types/<enum_type_id>/values` | GET | ACTIVE | `-` |
| `/api/v1/enum-types/<enum_type_id>/values` | POST | ACTIVE | `-` |
| `/api/v1/enum-values` | GET | ACTIVE | `-` |
| `/api/v1/enum-values/<int:value_id>` | GET | ACTIVE | `-` |
| `/api/v1/enum-values/<int:value_id>` | PUT | ACTIVE | `-` |
| `/api/v1/enum-values/<int:value_id>` | DELETE | ACTIVE | `-` |
| `/api/v1/enums/<enum_type_id>/options` | GET | ACTIVE | `-` |

### `export_import` (9 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/export` | POST | ACTIVE | `-` |
| `/api/v1/export/async` | POST | ACTIVE | `-` |
| `/api/v1/export/download/<path:filename>` | GET | ACTIVE | `-` |
| `/api/v1/export/status/<task_id>` | GET | ACTIVE | `-` |
| `/api/v1/import` | POST | ACTIVE | `-` |
| `/api/v1/import-export/config/<object_type>` | GET | ACTIVE | `-` |
| `/api/v1/import/async` | POST | ACTIVE | `-` |
| `/api/v1/import/status/<task_id>` | GET | ACTIVE | `-` |
| `/api/v1/import/template/<object_type>` | GET | ACTIVE | `-` |

### `filter_variant` (6 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/filter-variants` | GET | SUNSET | `/api/v2/bo/filter_variant` |
| `/api/v1/filter-variants` | POST | SUNSET | `/api/v2/bo/filter_variant` |
| `/api/v1/filter-variants/<int:variant_id>` | GET | SUNSET | `/api/v2/bo/filter_variant` |
| `/api/v1/filter-variants/<int:variant_id>` | PUT | SUNSET | `/api/v2/bo/filter_variant` |
| `/api/v1/filter-variants/<int:variant_id>` | DELETE | SUNSET | `/api/v2/bo/filter_variant` |
| `/api/v1/filter-variants/<int:variant_id>/set-default` | POST | ACTIVE | `-` |

### `identity` (4 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/identity` | GET | ACTIVE | `-` |
| `/api/v1/identity/batch` | POST | ACTIVE | `-` |
| `/api/v1/identity/cache/clear` | POST | ACTIVE | `-` |
| `/api/v1/identity/formatted` | GET | ACTIVE | `-` |

### `intent_api` (7 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/bos` | GET | DEPRECATED | `/api/v2/bos` |
| `/api/v1/bos/<bo_id>/actions` | GET | DEPRECATED | `/api/v2/bos/<bo_id>/actions` |
| `/api/v1/bos/<bo_id>/actions/<action_name>` | GET | DEPRECATED | `/api/v2/bos/<bo_id>/actions/<action_name>` |
| `/api/v1/permissions/check_intent` | POST | DEPRECATED | `/api/v2/permissions/check_intent` |
| `/api/v1/roles/<role_id>/intents` | GET | DEPRECATED | `/api/v2/roles/<role_id>/intents` |
| `/api/v1/roles/<role_id>/intents/<bo_id>/<action_name>` | PUT | DEPRECATED | `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` |
| `/api/v1/roles/<role_id>/intents/<bo_id>/<action_name>` | DELETE | DEPRECATED | `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` |

### `manage` (17 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/<object_type>` | POST | SUNSET | `/api/v2/bo/<object_type>` |
| `/api/v1/<object_type>` | GET | SUNSET | `/api/v2/bo/<object_type>` |
| `/api/v1/<object_type>/<id>` | GET | SUNSET | `/api/v2/bo/<object_type>/<id>` |
| `/api/v1/<object_type>/<id>` | PUT | SUNSET | `/api/v2/bo/<object_type>/<id>` |
| `/api/v1/<object_type>/<id>` | DELETE | SUNSET | `/api/v2/bo/<object_type>/<id>` |
| `/api/v1/<object_type>/<id>/actions` | GET | SUNSET | `/api/v2/bo/<object_type>/<id>/actions` |
| `/api/v1/<object_type>/<id>/actions/<action_id>` | POST | SUNSET | `/api/v2/bo/<object_type>/<id>/actions/<action_id>` |
| `/api/v1/<object_type>/<id>/recover` | POST | SUNSET | `/api/v2/bo/<object_type>/<id>/recover` |
| `/api/v1/<object_type>/<id>/stage_metrics` | GET | SUNSET | `/api/v2/bo/<object_type>/<id>/stage_metrics` |
| `/api/v1/<object_type>/<id>/state_history` | GET | SUNSET | `/api/v2/bo/<object_type>/<id>/state_history` |
| `/api/v1/<object_type>/<id>/state_transitions` | GET | SUNSET | `/api/v2/bo/<object_type>/<id>/state_transitions` |
| `/api/v1/<object_type>/batch-create` | POST | SUNSET | `/api/v2/bo/<object_type>/batch-create` |
| `/api/v1/<object_type>/batch-delete` | POST | SUNSET | `/api/v2/bo/<object_type>/batch-delete` |
| `/api/v1/<object_type>/batch-update` | POST | SUNSET | `/api/v2/bo/<object_type>/batch-update` |
| `/api/v1/<object_type>/deep` | POST | SUNSET | `/api/v2/bo/<object_type>/deep` |
| `/api/v1/<object_type>/deleted` | GET | SUNSET | `/api/v2/bo/<object_type>/deleted` |
| `/api/v1/<object_type>/list` | POST | SUNSET | `/api/v2/bo/<object_type>/list` |

### `management_dimension_meta` (1 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/meta/cache-stats` | GET | SUNSET | `/api/v2/bo/meta/cache-stats` |

### `management_dimension_roles` (3 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/roles/<int:role_id>/calculate-impact` | POST | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/permission-rules` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/permission-rules` | POST | ACTIVE | `-` |

### `menu_permission` (9 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/menu-permission/menus` | GET | ACTIVE | `-` |
| `/api/v1/menu-permission/menus` | POST | ACTIVE | `-` |
| `/api/v1/menu-permission/menus/<menu_code>` | GET | ACTIVE | `-` |
| `/api/v1/menu-permission/menus/<menu_code>` | PUT | ACTIVE | `-` |
| `/api/v1/menu-permission/menus/<menu_code>` | DELETE | ACTIVE | `-` |
| `/api/v1/menu-permission/menus/<menu_code>/consistency` | GET | ACTIVE | `-` |
| `/api/v1/menu-permission/menus/all` | GET | ACTIVE | `-` |
| `/api/v1/menu-permission/menus/report` | GET | ACTIVE | `-` |
| `/api/v1/menu-permission/visible` | GET | ACTIVE | `-` |

### `meta` (14 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/meta/<object_type>/detail-view` | GET | SUNSET | `/api/v2/bo/meta/<object_type>/detail-view` |
| `/api/v1/meta/<object_type>/filter-config` | GET | SUNSET | `/api/v2/bo/meta/<object_type>/filter-config` |
| `/api/v1/meta/<object_type>/filter-tree/<filter_key>` | GET | SUNSET | `/api/v2/bo/meta/<object_type>/filter-tree/<filter_key>` |
| `/api/v1/meta/<object_type>/form-view` | GET | SUNSET | `/api/v2/bo/meta/<object_type>/form-view` |
| `/api/v1/meta/<object_type>/list-view` | GET | SUNSET | `/api/v2/bo/meta/<object_type>/list-view` |
| `/api/v1/meta/<object_type>/view-config` | GET | SUNSET | `/api/v2/bo/meta/<object_type>/view-config` |
| `/api/v1/meta/<object_type>/view-config/<view_name>` | GET | SUNSET | `/api/v2/bo/meta/<object_type>/view-config/<view_name>` |
| `/api/v1/meta/enums/batch` | GET | ACTIVE | `-` |
| `/api/v1/meta/i18n/<locale>` | GET | SUNSET | `/api/v2/bo/meta/i18n/<locale>` |
| `/api/v1/meta/i18n/locales` | GET | ACTIVE | `-` |
| `/api/v1/meta/i18n/text/<path:key>` | GET | ACTIVE | `-` |
| `/api/v1/meta/objects` | GET | SUNSET | `/api/v2/bo/meta/objects` |
| `/api/v1/meta/objects/<object_type>` | GET | SUNSET | `/api/v2/bo/meta/objects/<object_type>` |
| `/api/v1/meta/reload` | POST | SUNSET | `/api/v2/bo/meta/reload` |

### `meta_util` (5 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/meta/hierarchies` | GET | SUNSET | `/api/v2/bo/meta/hierarchies` |
| `/api/v1/meta/hierarchies/<hierarchy_id>/levels` | GET | ACTIVE | `-` |
| `/api/v1/meta/hierarchies/config` | GET | ACTIVE | `-` |
| `/api/v1/meta/objects` | GET | SUNSET | `/api/v2/bo/meta/objects` |
| `/api/v1/meta/objects/<object_type>/field_controls` | GET | ACTIVE | `-` |

### `notification` (9 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/notifications/events` | GET | ACTIVE | `-` |
| `/api/v1/notifications/events/<int:event_id>` | GET | ACTIVE | `-` |
| `/api/v1/notifications/events/<int:event_id>/retry` | POST | ACTIVE | `-` |
| `/api/v1/notifications/stats` | GET | ACTIVE | `-` |
| `/api/v1/notifications/subscriptions` | GET | ACTIVE | `-` |
| `/api/v1/notifications/subscriptions` | POST | ACTIVE | `-` |
| `/api/v1/notifications/subscriptions/<int:sub_id>` | GET | ACTIVE | `-` |
| `/api/v1/notifications/subscriptions/<int:sub_id>` | PUT | ACTIVE | `-` |
| `/api/v1/notifications/subscriptions/<int:sub_id>` | DELETE | ACTIVE | `-` |

### `overlap` (2 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/roles/<int:role_id>/overlaps` | GET | DEPRECATED | `/api/v2/roles/<int:role_id>/overlaps` |
| `/api/v1/roles/<int:role_id>/overlaps/summary` | GET | DEPRECATED | `/api/v2/roles/<int:role_id>/overlaps/summary` |

### `owner_transfer` (4 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/admin/owner/bulk-transfer` | POST | ACTIVE | `-` |
| `/api/v1/admin/owner/transfer` | POST | ACTIVE | `-` |
| `/api/v1/admin/owner/transfer-history` | GET | ACTIVE | `-` |
| `/api/v1/admin/owner/validate` | POST | ACTIVE | `-` |

### `permission_api` (2 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/permissions/check` | POST | DEPRECATED | `/api/v2/permissions/check` |
| `/api/v1/permissions/explain` | POST | DEPRECATED | `/api/v2/permissions/explain` |

### `permission_audit` (6 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/permission-audit/excessive` | GET | ACTIVE | `-` |
| `/api/v1/permission-audit/history` | GET | ACTIVE | `-` |
| `/api/v1/permission-audit/orphans` | GET | ACTIVE | `-` |
| `/api/v1/permission-audit/report` | GET | ACTIVE | `-` |
| `/api/v1/permission-audit/stats` | GET | ACTIVE | `-` |
| `/api/v1/permission-audit/user/<int:user_id>/summary` | GET | ACTIVE | `-` |

### `permission_bundle` (7 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/permission-bundles` | GET | SUNSET | `/api/v2/bo/permission_bundle` |
| `/api/v1/permission-bundles` | POST | SUNSET | `/api/v2/bo/permission_bundle` |
| `/api/v1/permission-bundles/<bundle_code>` | GET | SUNSET | `/api/v2/bo/permission_bundle` |
| `/api/v1/permission-bundles/<bundle_code>` | PUT | SUNSET | `/api/v2/bo/permission_bundle` |
| `/api/v1/permission-bundles/<bundle_code>` | DELETE | SUNSET | `/api/v2/bo/permission_bundle` |
| `/api/v1/permission-bundles/assign` | POST | ACTIVE | `-` |
| `/api/v1/permission-bundles/user/<int:user_id>` | GET | ACTIVE | `-` |

### `permission_rule` (12 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/permission-rules` | GET | DEPRECATED | `/api/v2/permission-rules` |
| `/api/v1/permission-rules` | POST | DEPRECATED | `/api/v2/permission-rules` |
| `/api/v1/permission-rules/<int:rule_id>` | GET | DEPRECATED | `/api/v2/permission-rules/<rule_id>` |
| `/api/v1/permission-rules/<int:rule_id>` | PUT | DEPRECATED | `/api/v2/permission-rules/<rule_id>` |
| `/api/v1/permission-rules/<int:rule_id>` | DELETE | DEPRECATED | `/api/v2/permission-rules/<rule_id>` |
| `/api/v1/permission-rules/check` | POST | ACTIVE | `-` |
| `/api/v1/permission-rules/dimensions` | GET | ACTIVE | `-` |
| `/api/v1/permission-rules/dimensions/<string:dimension_code>/values` | GET | ACTIVE | `-` |
| `/api/v1/permission-rules/employee-scopes` | GET | ACTIVE | `-` |
| `/api/v1/permission-rules/field-metadata` | GET | ACTIVE | `-` |
| `/api/v1/permission-rules/preview` | POST | ACTIVE | `-` |
| `/api/v1/permission-rules/reference-check` | POST | ACTIVE | `-` |

### `permission_sync` (5 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/admin/permissions/orphans` | GET | ACTIVE | `-` |
| `/api/v1/admin/permissions/orphans` | DELETE | ACTIVE | `-` |
| `/api/v1/admin/permissions/report` | GET | ACTIVE | `-` |
| `/api/v1/admin/permissions/sync` | POST | ACTIVE | `-` |
| `/api/v1/admin/permissions/validate` | GET | ACTIVE | `-` |

### `query` (5 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/query/aggregate` | POST | ACTIVE | `-` |
| `/api/v1/query/full-text` | GET | ACTIVE | `-` |
| `/api/v1/query/hierarchy/<path:path>` | GET | ACTIVE | `-` |
| `/api/v1/query/search` | POST | ACTIVE | `-` |
| `/api/v1/query/suggest/<object_type>/<field>` | GET | ACTIVE | `-` |

### `role` (14 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/roles` | GET | ACTIVE | `-` |
| `/api/v1/roles` | POST | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>` | PUT | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>` | DELETE | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/data-permissions` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/data-permissions` | POST | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/logs` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/menus` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/permissions` | PUT | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/permissions` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/users` | POST | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/users/<int:user_id>` | DELETE | ACTIVE | `-` |
| `/api/v1/roles/permissions` | GET | ACTIVE | `-` |

### `role_dim` (3 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/roles/<int:role_id>/derived-permissions` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/dimension-scopes` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/dimension-scopes` | POST | ACTIVE | `-` |

### `role_menu` (3 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/roles/<int:role_id>/menu-permissions` | GET | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/menu-permissions` | PUT | ACTIVE | `-` |
| `/api/v1/roles/<int:role_id>/unified-permissions` | GET | ACTIVE | `-` |

### `schema` (9 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/schema/indexes/create` | POST | ACTIVE | `-` |
| `/api/v1/schema/indexes/report` | GET | ACTIVE | `-` |
| `/api/v1/schema/indexes/report/<object_id>` | GET | ACTIVE | `-` |
| `/api/v1/schema/indexes/stats` | GET | ACTIVE | `-` |
| `/api/v1/schema/status` | GET | ACTIVE | `-` |
| `/api/v1/schema/sync` | POST | ACTIVE | `-` |
| `/api/v1/schema/tables` | GET | ACTIVE | `-` |
| `/api/v1/schema/tables/<table_name>` | GET | ACTIVE | `-` |
| `/api/v1/schema/tables/<table_name>/create` | POST | ACTIVE | `-` |

### `schema_dashboard` (4 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/schema/dashboard/diff-history` | GET | ACTIVE | `-` |
| `/api/v1/schema/dashboard/entities` | GET | ACTIVE | `-` |
| `/api/v1/schema/dashboard/summary` | GET | ACTIVE | `-` |
| `/api/v1/schema/dashboard/sync-status` | GET | ACTIVE | `-` |

### `special` (3 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/analytics/<object_type>` | POST | ACTIVE | `-` |
| `/api/v1/business_object/<int:obj_id>/relations` | GET | SUNSET | `/api/v2/bo/business_object/<int:obj_id>/relations` |
| `/api/v1/relationships` | GET, POST | SUNSET | `/api/v2/bo/relationships` |

### `stats` (13 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/stats/aggregates` | GET | ACTIVE | `-` |
| `/api/v1/stats/aggregates/<aggregate_id>/query` | POST | ACTIVE | `-` |
| `/api/v1/stats/aggregates/<aggregate_id>/refresh` | POST | ACTIVE | `-` |
| `/api/v1/stats/aggregates/freshness` | GET | ACTIVE | `-` |
| `/api/v1/stats/cache` | GET | ACTIVE | `-` |
| `/api/v1/stats/cache/invalidate` | POST | ACTIVE | `-` |
| `/api/v1/stats/model/<object_type>` | GET | ACTIVE | `-` |
| `/api/v1/stats/model/<object_type>/dimensions/<dimension_id>/members` | GET | ACTIVE | `-` |
| `/api/v1/stats/model/<object_type>/navigation` | POST | ACTIVE | `-` |
| `/api/v1/stats/olap/<object_type>` | POST | ACTIVE | `-` |
| `/api/v1/stats/olap/<object_type>/drill-down` | POST | ACTIVE | `-` |
| `/api/v1/stats/olap/<object_type>/roll-up` | POST | ACTIVE | `-` |
| `/api/v1/stats/overview` | GET | ACTIVE | `-` |

### `telemetry` (7 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/telemetry/configure` | POST | ACTIVE | `-` |
| `/api/v1/telemetry/error` | POST | ACTIVE | `-` |
| `/api/v1/telemetry/errors` | GET | ACTIVE | `-` |
| `/api/v1/telemetry/stats` | GET | ACTIVE | `-` |
| `/api/v1/telemetry/traces` | GET | ACTIVE | `-` |
| `/api/v1/telemetry/traces/<trace_id>` | GET | ACTIVE | `-` |
| `/api/v1/telemetry/traces/slow` | GET | ACTIVE | `-` |

### `test` (1 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/test/ready` | GET | ACTIVE | `-` |

### `user` (14 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/users` | GET | SUNSET | `/api/v2/bo/user` |
| `/api/v1/users` | POST | SUNSET | `/api/v2/bo/user` |
| `/api/v1/users/<int:user_id>` | GET | SUNSET | `/api/v2/bo/user` |
| `/api/v1/users/<int:user_id>` | PUT | SUNSET | `/api/v2/bo/user` |
| `/api/v1/users/<int:user_id>` | DELETE | SUNSET | `/api/v2/bo/user` |
| `/api/v1/users/<int:user_id>/logs` | GET | ACTIVE | `-` |
| `/api/v1/users/<int:user_id>/menus` | GET | ACTIVE | `-` |
| `/api/v1/users/<int:user_id>/reset-password` | POST | ACTIVE | `-` |
| `/api/v1/users/batch-data-permissions` | POST | ACTIVE | `-` |
| `/api/v1/users/batch-delete` | POST | ACTIVE | `-` |
| `/api/v1/users/me` | GET | ACTIVE | `-` |
| `/api/v1/users/me` | PUT | ACTIVE | `-` |
| `/api/v1/users/self` | GET | ACTIVE | `-` |
| `/api/v1/users/self` | PUT | ACTIVE | `-` |

### `user_group` (14 个端点)

| URL | 方法 | 状态 | 迁移到 |
|-----|------|------|--------|
| `/api/v1/system/migrate-group-permissions-to-roles` | POST | ACTIVE | `-` |
| `/api/v1/user-groups/<int:group_id>/data-permissions` | GET | DEPRECATED | `/api/v2/bo/user_group/<group_id>/associations/roles` |
| `/api/v1/user-groups/<int:group_id>/data-permissions` | POST | DEPRECATED | `/api/v2/bo/user_group/<group_id>/associations/roles` |
| `/api/v1/user-groups/<int:group_id>/data-permissions/<int:perm_id>` | DELETE | DEPRECATED | `/api/v2/bo/user_group/<group_id>/associations/roles` |
| `/api/v1/user-groups/<int:group_id>/logs` | GET | ACTIVE | `-` |
| `/api/v1/user-groups/<int:group_id>/members` | GET | DEPRECATED | `/api/v2/bo/user_group/<group_id>/associations/members` |
| `/api/v1/user-groups/<int:group_id>/members` | POST | DEPRECATED | `/api/v2/bo/user_group/<group_id>/associations/members` |
| `/api/v1/user-groups/<int:group_id>/members` | PUT | ACTIVE | `-` |
| `/api/v1/user-groups/<int:group_id>/members/<int:user_id>` | DELETE | ACTIVE | `-` |
| `/api/v1/user-groups/<int:group_id>/roles` | GET | DEPRECATED | `/api/v2/bo/user_group/<group_id>/associations/roles` |
| `/api/v1/user-groups/<int:group_id>/roles` | PUT | ACTIVE | `-` |
| `/api/v1/user-groups/<int:group_id>/roles/<int:role_id>` | POST | ACTIVE | `-` |
| `/api/v1/user-groups/<int:group_id>/roles/<int:role_id>` | DELETE | ACTIVE | `-` |
| `/api/v1/user-groups/<int:group_id>/roles/available` | GET | ACTIVE | `-` |

## 四、v2 端点清单（简要）

> v2 端点总数: 96

| URL | 方法 | Blueprint |
|-----|------|-----------|
| `/api/v2/action/` | GET | bo_action |
| `/api/v2/action/<path:action_id>` | DELETE, GET, POST, PUT | bo_action |
| `/api/v2/action/_chain` | POST | bo_action |
| `/api/v2/action/_chain_stream` | POST | bo_action |
| `/api/v2/action/_db_health` | GET | db_admin |
| `/api/v2/action/_docs` | GET | bo_action |
| `/api/v2/action/_health` | GET | bo_action |
| `/api/v2/action/_openapi.json` | GET | bo_action |
| `/api/v2/action/_schemas` | GET | bo_action |
| `/api/v2/action/_subflow_metrics` | GET | bo_action |
| `/api/v2/action/_subflow_template` | GET | bo_action |
| `/api/v2/action/_subflow_template/<name>` | PUT | bo_action |
| `/api/v2/action/_subflow_template/<name>` | DELETE | bo_action |
| `/api/v2/action/_subflow_template/<name>` | GET | bo_action |
| `/api/v2/action/db.backup` | POST | db_admin |
| `/api/v2/action/db.recover` | POST | db_admin |
| `/api/v2/bo/<object_type>` | POST | bo_v2 |
| `/api/v2/bo/<object_type>` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/$associations/<association_name>/batch-query` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>` | PUT | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>` | DELETE | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/$associations/<association_name>` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/$associations/<association_name>/assign` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/$associations/<association_name>/batch_assign` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/$associations/<association_name>/batch_unassign` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/$associations/<association_name>/count` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/$associations/<association_name>/unassign` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/actions` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/actions` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/actions/<action_id>` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/associations/<association_name>` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/associations/<association_name>` | DELETE | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/associations/<association_name>` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/recover` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/retrieve` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/stage_metrics` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/state_history` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<int:obj_id>/state_transitions` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<path:obj_id>` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/<path:obj_id>` | PUT | bo_v2 |
| `/api/v2/bo/<object_type>/<path:obj_id>` | DELETE | bo_v2 |
| `/api/v2/bo/<object_type>/<path:obj_id>/state_transitions` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/batch-create` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/batch-delete` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/batch-update` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/deep` | POST | bo_v2 |
| `/api/v2/bo/<object_type>/deleted` | GET | bo_v2 |
| `/api/v2/bo/<object_type>/list` | POST | bo_v2 |
| `/api/v2/bo/architecture/preview` | GET | bo_v2 |
| `/api/v2/bo/business_object/<int:bo_id>` | GET | value_help |
| `/api/v2/bo/business_object/pick_by_code` | GET | value_help |
| `/api/v2/bo/management_dimension` | GET | management_dimension |
| `/api/v2/bo/management_dimension/../roles/<int:role_id>/permission-rules` | GET | management_dimension |
| `/api/v2/bo/management_dimension/<string:dimension_id>/instances` | GET | management_dimension |
| `/api/v2/bos` | GET | intent_api |
| `/api/v2/bos/<bo_id>/actions` | GET | intent_api |
| `/api/v2/bos/<bo_id>/actions/<action_name>` | GET | intent_api |
| `/api/v2/key-template/config/<object_type>` | GET | key_template |
| `/api/v2/key-template/list-objects` | GET | key_template |
| `/api/v2/key-template/preview/<object_type>` | POST | key_template |
| `/api/v2/meta/<object_type>/field-policies` | GET | meta_v2 |
| `/api/v2/meta/<object_type>/full` | GET | meta_v2 |
| `/api/v2/meta/<object_type>/schema` | GET | meta_v2 |
| `/api/v2/meta/<object_type>/ui-config` | GET | meta_v2 |
| `/api/v2/meta/<object_type>/view-config` | GET | meta_v2 |
| `/api/v2/meta/<object_type>/view-config/<view_name>` | GET | meta_v2 |
| `/api/v2/meta/<object_type>/views` | GET | meta_v2 |
| `/api/v2/meta/_openapi.json` | GET | meta_v2 |
| `/api/v2/meta/hierarchy/levels` | GET | meta_v2 |
| `/api/v2/meta/hierarchy/tree` | GET | meta_v2 |
| `/api/v2/meta/schema-version` | GET | meta_v2 |
| `/api/v2/permission-rules` | GET | permission_rule_v2 |
| `/api/v2/permission-rules` | POST | permission_rule_v2 |
| `/api/v2/permission-rules/<int:rule_id>` | PUT | permission_rule_v2 |
| `/api/v2/permission-rules/<int:rule_id>` | DELETE | permission_rule_v2 |
| `/api/v2/permissions/check` | POST | permission_api |
| `/api/v2/permissions/check_intent` | POST | intent_api |
| `/api/v2/permissions/explain` | POST | permission_api |
| `/api/v2/roles/<int:role_id>/menu-permissions` | PUT | role_v2 |
| `/api/v2/roles/<int:role_id>/overlaps` | GET | overlap |
| `/api/v2/roles/<int:role_id>/overlaps/summary` | GET | overlap |
| `/api/v2/roles/<int:role_id>/unified-permissions` | GET | role_v2 |
| `/api/v2/roles/<role_id>/intents` | GET | intent_api |
| `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` | PUT | intent_api |
| `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` | DELETE | intent_api |
| `/api/v2/task-executions/<int:execution_id>/cancel` | POST | task_api |
| `/api/v2/task-executions/<int:execution_id>/retry` | POST | task_api |
| `/api/v2/task-queues/stats` | GET | task_api |
| `/api/v2/task-scheduler/reload` | POST | task_api |
| `/api/v2/task-scheduler/status` | GET | task_api |
| `/api/v2/tasks/<task_code>/disable` | POST | task_api |
| `/api/v2/tasks/<task_code>/enable` | POST | task_api |
| `/api/v2/tasks/<task_code>/trigger` | POST | task_api |
| `/api/v2/value-help/<source_type>/<source_id>` | GET | value_help |
| `/api/v2/value-help/<source_type>/<source_id>/resolve` | GET | value_help |

## 五、迁移建议

### 优先级 P0（SUNSET 状态）

前端必须立即停止调用以下端点（已返回 410）:

- `GET, POST /api/v1/relationships` → `/api/v2/bo/relationships`
- `GET /api/v1/business_object/<int:obj_id>/relations` → `/api/v2/bo/business_object/<int:obj_id>/relations`
- `POST /api/v1/<object_type>` → `/api/v2/bo/<object_type>`
- `POST /api/v1/<object_type>/deep` → `/api/v2/bo/<object_type>/deep`
- `GET /api/v1/<object_type>/<id>` → `/api/v2/bo/<object_type>/<id>`
- `GET /api/v1/<object_type>` → `/api/v2/bo/<object_type>`
- `POST /api/v1/<object_type>/list` → `/api/v2/bo/<object_type>/list`
- `PUT /api/v1/<object_type>/<id>` → `/api/v2/bo/<object_type>/<id>`
- `DELETE /api/v1/<object_type>/<id>` → `/api/v2/bo/<object_type>/<id>`
- `POST /api/v1/<object_type>/<id>/recover` → `/api/v2/bo/<object_type>/<id>/recover`
- `GET /api/v1/<object_type>/deleted` → `/api/v2/bo/<object_type>/deleted`
- `POST /api/v1/<object_type>/batch-create` → `/api/v2/bo/<object_type>/batch-create`
- `POST /api/v1/<object_type>/batch-update` → `/api/v2/bo/<object_type>/batch-update`
- `POST /api/v1/<object_type>/batch-delete` → `/api/v2/bo/<object_type>/batch-delete`
- `GET /api/v1/<object_type>/<id>/actions` → `/api/v2/bo/<object_type>/<id>/actions`
- `POST /api/v1/<object_type>/<id>/actions/<action_id>` → `/api/v2/bo/<object_type>/<id>/actions/<action_id>`
- `GET /api/v1/<object_type>/<id>/state_transitions` → `/api/v2/bo/<object_type>/<id>/state_transitions`
- `GET /api/v1/<object_type>/<id>/state_history` → `/api/v2/bo/<object_type>/<id>/state_history`
- `GET /api/v1/<object_type>/<id>/stage_metrics` → `/api/v2/bo/<object_type>/<id>/stage_metrics`
- `GET /api/v1/meta/objects` → `/api/v2/bo/meta/objects`
- `GET /api/v1/meta/objects/<object_type>` → `/api/v2/bo/meta/objects/<object_type>`
- `GET /api/v1/meta/<object_type>/view-config` → `/api/v2/bo/meta/<object_type>/view-config`
- `GET /api/v1/meta/<object_type>/view-config/<view_name>` → `/api/v2/bo/meta/<object_type>/view-config/<view_name>`
- `GET /api/v1/meta/<object_type>/list-view` → `/api/v2/bo/meta/<object_type>/list-view`
- `GET /api/v1/meta/<object_type>/detail-view` → `/api/v2/bo/meta/<object_type>/detail-view`
- `GET /api/v1/meta/<object_type>/form-view` → `/api/v2/bo/meta/<object_type>/form-view`
- `POST /api/v1/meta/reload` → `/api/v2/bo/meta/reload`
- `GET /api/v1/meta/i18n/<locale>` → `/api/v2/bo/meta/i18n/<locale>`
- `GET /api/v1/meta/<object_type>/filter-config` → `/api/v2/bo/meta/<object_type>/filter-config`
- `GET /api/v1/meta/<object_type>/filter-tree/<filter_key>` → `/api/v2/bo/meta/<object_type>/filter-tree/<filter_key>`
- `GET /api/v1/users` → `/api/v2/bo/user`
- `POST /api/v1/users` → `/api/v2/bo/user`
- `GET /api/v1/users/<int:user_id>` → `/api/v2/bo/user`
- `PUT /api/v1/users/<int:user_id>` → `/api/v2/bo/user`
- `DELETE /api/v1/users/<int:user_id>` → `/api/v2/bo/user`
- `GET /api/v1/data-permissions` → `/api/v2/bo/data_permission`
- `POST /api/v1/data-permissions` → `/api/v2/bo/data_permission`
- `DELETE /api/v1/data-permissions/<int:perm_id>` → `/api/v2/bo/data_permission`
- `GET /api/v1/meta/cache-stats` → `/api/v2/bo/meta/cache-stats`
- `GET /api/v1/permission-bundles` → `/api/v2/bo/permission_bundle`
- `GET /api/v1/permission-bundles/<bundle_code>` → `/api/v2/bo/permission_bundle`
- `POST /api/v1/permission-bundles` → `/api/v2/bo/permission_bundle`
- `PUT /api/v1/permission-bundles/<bundle_code>` → `/api/v2/bo/permission_bundle`
- `DELETE /api/v1/permission-bundles/<bundle_code>` → `/api/v2/bo/permission_bundle`
- `GET /api/v1/filter-variants` → `/api/v2/bo/filter_variant`
- `GET /api/v1/filter-variants/<int:variant_id>` → `/api/v2/bo/filter_variant`
- `POST /api/v1/filter-variants` → `/api/v2/bo/filter_variant`
- `PUT /api/v1/filter-variants/<int:variant_id>` → `/api/v2/bo/filter_variant`
- `DELETE /api/v1/filter-variants/<int:variant_id>` → `/api/v2/bo/filter_variant`
- `DELETE /api/v1/associations/<entity_type>/<int:entity_id>` → `/api/v2/bo/association`
- `GET /api/v1/meta/objects` → `/api/v2/bo/meta/objects`
- `GET /api/v1/meta/hierarchies` → `/api/v2/bo/meta/hierarchies`
- `GET /api/v1/debug/current-user` → `/api/v2/bo/debug/current-user`

### 优先级 P1（DEPRECATED 状态）

前端应在 sunset_at 之前迁移以下端点:

- `GET /api/v1/user-groups/<int:group_id>/members` → `/api/v2/bo/user_group/<group_id>/associations/members` (下线: 2026-12-31)
- `POST /api/v1/user-groups/<int:group_id>/members` → `/api/v2/bo/user_group/<group_id>/associations/members` (下线: 2026-12-31)
- `GET /api/v1/user-groups/<int:group_id>/data-permissions` → `/api/v2/bo/user_group/<group_id>/associations/roles` (下线: 2026-12-31)
- `POST /api/v1/user-groups/<int:group_id>/data-permissions` → `/api/v2/bo/user_group/<group_id>/associations/roles` (下线: 2026-12-31)
- `DELETE /api/v1/user-groups/<int:group_id>/data-permissions/<int:perm_id>` → `/api/v2/bo/user_group/<group_id>/associations/roles` (下线: 2026-12-31)
- `GET /api/v1/user-groups/<int:group_id>/roles` → `/api/v2/bo/user_group/<group_id>/associations/roles` (下线: 2026-12-31)
- `GET /api/v1/permission-rules` → `/api/v2/permission-rules` (下线: 2026-12-31)
- `GET /api/v1/permission-rules/<int:rule_id>` → `/api/v2/permission-rules/<rule_id>` (下线: 2026-12-31)
- `POST /api/v1/permission-rules` → `/api/v2/permission-rules` (下线: 2026-12-31)
- `PUT /api/v1/permission-rules/<int:rule_id>` → `/api/v2/permission-rules/<rule_id>` (下线: 2026-12-31)
- `DELETE /api/v1/permission-rules/<int:rule_id>` → `/api/v2/permission-rules/<rule_id>` (下线: 2026-12-31)
- `GET /api/v1/roles/<int:role_id>/overlaps` → `/api/v2/roles/<int:role_id>/overlaps` (下线: 2026-12-31)
- `GET /api/v1/roles/<int:role_id>/overlaps/summary` → `/api/v2/roles/<int:role_id>/overlaps/summary` (下线: 2026-12-31)
- `POST /api/v1/permissions/explain` → `/api/v2/permissions/explain` (下线: 2026-12-31)
- `POST /api/v1/permissions/check` → `/api/v2/permissions/check` (下线: 2026-12-31)
- `POST /api/v1/permissions/check_intent` → `/api/v2/permissions/check_intent` (下线: 2026-12-31)
- `GET /api/v1/bos` → `/api/v2/bos` (下线: 2026-12-31)
- `GET /api/v1/bos/<bo_id>/actions` → `/api/v2/bos/<bo_id>/actions` (下线: 2026-12-31)
- `GET /api/v1/bos/<bo_id>/actions/<action_name>` → `/api/v2/bos/<bo_id>/actions/<action_name>` (下线: 2026-12-31)
- `GET /api/v1/roles/<role_id>/intents` → `/api/v2/roles/<role_id>/intents` (下线: 2026-12-31)
- `PUT /api/v1/roles/<role_id>/intents/<bo_id>/<action_name>` → `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` (下线: 2026-12-31)
- `DELETE /api/v1/roles/<role_id>/intents/<bo_id>/<action_name>` → `/api/v2/roles/<role_id>/intents/<bo_id>/<action_name>` (下线: 2026-12-31)
- `POST /api/v1/associations/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>` → `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>/assign` (下线: 2026-12-31)
- `DELETE /api/v1/associations/<source_type>/<int:source_id>/<association_name>/<target_type>/<int:target_id>` → `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>/unassign` (下线: 2026-12-31)
- `GET /api/v1/associations/<source_type>/<int:source_id>/<association_name>` → `/api/v2/bo/<object_type>/<obj_id>/$associations/<association_name>` (下线: 2026-12-31)

### 优先级 P2（ACTIVE 状态）

以下 192 个端点仍正常工作，可按需评估是否迁移到 v2:

| Blueprint | 端点数 |
|-----------|--------|
| role | 14 |
| stats | 13 |
| enum | 13 |
| export_import | 9 |
| schema | 9 |
| user | 9 |
| menu_permission | 9 |
| notification | 9 |
| database | 9 |
| user_group | 8 |
| permission_rule | 7 |
| audit | 7 |
| telemetry | 7 |
| annotation | 6 |
| permission_audit | 6 |
| query | 5 |
| auth | 5 |
| permission_sync | 5 |
| owner_transfer | 4 |
| identity | 4 |
| schema_dashboard | 4 |
| meta | 3 |
| agent | 3 |
| data_permission | 3 |
| role_menu | 3 |
| role_dim | 3 |
| management_dimension_roles | 3 |
| audit_mgmt | 3 |
| meta_util | 3 |
| permission_bundle | 2 |
| special | 1 |
| filter_variant | 1 |
| association | 1 |
| test | 1 |
