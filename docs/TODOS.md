# 技术待办 (Technical TODOs)

> 生成时间: 2026-06-09
> 来源: Dimension Scope v1.0.4 权限系统重构 + 全面排查

---

## 全面排查结论

### 数据分布现实
- DB 中所有 version IDs: `[1, 2, 11, 12]`
- TEST60 dimension scope: `version=[1, 2, 11, 12]`
- **结论: TEST60 的 scope 覆盖了 DB 中所有数据**
- 这意味着对 TEST60 而言，所有无 dimension scope 过滤的端点**没有实际数据泄漏风险**
- 但对于**scope 更小**的用户（如只配了 version=1 的用户），v1 端点**会有数据泄漏**

### 拦截器架构分析

| 端点类型 | action | is_query_action | dimension_scope 过滤 | 风险 |
|---------|--------|----------------|---------------------|------|
| `crud_query` (GET /bo/{type}) | `crud_query` | True | ✅ 应用 | 低 |
| `crud_read` (GET /bo/{type}/{id}) | `crud_read` | True | ✅ 应用 | 低 |
| `query_associations` | `query_associations` | **False** | ❌ 不应用 | 中 |
| `retrieve_with_associations` | `retrieve_with_associations` | **False** | ❌ 不应用 | 中 |
| `batch_query_associations` | `batch_query_associations` | **False** | ❌ 不应用 | 中 |
| `/api/v1/relationships` | N/A (special route) | N/A | ❌ 无 | **高** (已修复) |
| `/api/v1/business_object/{id}/relations` | N/A (special route) | N/A | ❌ 无 | **高** |
| `/api/v2/bo/architecture/preview` | N/A (special route) | N/A | ❌ 无 | 中 |
| `/api/v2/meta/hierarchy/tree` | N/A (metadata) | N/A | N/A | 低 |

---

## P0 - 本次修复遗留

### 1. RelationScopeSection.vue → 改用 v2 端点 (已完成修复)
- **问题**: `/api/v1/relationships` 无 dimension scope 过滤，dimension scope 用户返回 0 条
- **当前修复**: `special_routes_api.py` 加了兼容性逻辑（已生效）
- **长期方案**: 前端改为调用 `/api/v2/bo/relationship`（与 list 端点一致）
- **文件**: `src/components/common/RelationScopeTree/RelationScopeSection.vue` L451
- **状态**: 临时修复已生效 (special_routes_api.py L89-117), v2 迁移待做
- **优先级**: 中（临时修复已生效）

---

## P1 - 需评估风险

### 2. query_associations 端点无 dimension scope 过滤
- **问题**: `context.action = 'query_associations'` → `is_query_action = False` → 拦截器返回 early
- **风险**: association 查询不应用 dimension scope（但 association 主要用于 composition 树，
  用户通过 parent object 进入，且 `merged_one_to_many` 类型不支持，所以实际风险较低）
- **文件**: `meta/api/bo_api.py` L416, L446, L661
- **状态**: 待评估
- **优先级**: 低-中

### 3. retrieve_with_associations 端点无 dimension scope 过滤
- **问题**: 同上，action 不在 is_query_action 列表
- **缓解**: 内部调用 `self.read(object_type, obj_id)` 会应用 dimension scope
- **风险**: 关联数据本身（通过 associations 参数获取）无过滤
- **文件**: `meta/api/bo_api.py` L688
- **状态**: 待评估
- **优先级**: 低-中

### 4. /api/v1/business_object/{id}/relations 端点无过滤
- **问题**: 直接查询 relationships 表，无任何权限过滤
- **风险**: 但 DB 中所有 version 都在 scope 内，实际泄漏风险为 0
- **文件**: `meta/api/special_routes_api.py` L356
- **状态**: 待评估
- **优先级**: 低（version 范围全覆盖）

### 5. /api/v2/bo/architecture/preview 无 dimension scope 过滤
- **问题**: 架构预览聚合端点无过滤，但接受 `domain_ids`/`sub_domain_ids` 参数
- **风险**: 如果用户传了 scope 外的大 ID，会返回超出 scope 的数据
- **缓解**: 前端调用时只传用户有权限的 scope 内的 ID
- **文件**: `meta/api/bo_api.py` L847
- **状态**: 待评估
- **优先级**: 中

### 6. /api/v1/analytics/{type} 端点无过滤
- **问题**: 分析端点无任何权限过滤
- **文件**: `meta/api/special_routes_api.py` L413
- **状态**: 待评估
- **优先级**: 低（分析数据通常不涉及敏感数据）

---

## P2 - 长期架构统一

### 7. 统一 permission service (get_allowed_resource_ids)
- **问题**: `DataPermissionService.get_allowed_resource_ids()` 只查 data_permissions 旧表，不支持 dimension scope 派生
- **现状**: v1.0.4 新增 `DimensionScopeEngine.derive_data_conditions()` 独立运作，两套系统并存
- **方向**: 融合两套系统，`get_allowed_resource_ids()` 内部调用 `DimensionScopeEngine`
- **文件**: `meta/services/data_permission_service.py`
- **状态**: 待处理
- **优先级**: 高

### 8. 废弃 data_permissions 旧表
- **问题**: P12 设计的 data_permissions 旧表与 dimension scope 新系统重复
- **现状**: `role_data_permissions` / `group_data_permissions` 表已为空 (0 条数据)
- **方向**: 确认无遗留数据后，废弃 data_permissions 表，迁移所有用户到 dimension scope
- **文件**: `meta/services/data_permission_service.py`, 数据库迁移脚本
- **状态**: 待处理
- **优先级**: 中

### 9. 关系 BO 派生权限改为运行时检查 (Phase 2)
- **问题**: 当前 `ASSOCIATION_BOS` 将 relationship 权限写入 role_permissions 表
- **方向**: 改为运行时派生（用户访问 relationship → 后端查 source 端点权限 → 通过则放行）
- **文件**: `meta/core/interceptors/permission_interceptor.py`, `meta/services/dimension_scope_engine.py`
- **状态**: 待评估
- **优先级**: 低

### 10. 菜单过滤加入 dimension scope 检查
- **问题**: 菜单可见性只看 permission code，不看 dimension scope 范围
- **现状**: 方案 A（接受现状）— TEST60 看到 4 个菜单是正确的
- **文件**: `meta/api/menu_permission_api.py`
- **状态**: 方案 A 接受
- **优先级**: 低

### 11. is_query_action 补充 association actions
- **问题**: `query_associations` / `retrieve_with_associations` 等不触发 dimension scope 过滤
- **方向**: 扩展 `ActionContext.is_query_action` 或在 `DataPermissionInterceptor.before_action` 中单独处理
- **文件**: `meta/core/action_context.py`, `meta/core/interceptors/data_permission_interceptor.py`
- **状态**: 待评估
- **优先级**: 中

---

## P3 - 前端迁移 (v1 → v2)

### 12. v1 API 服务迁移清单

以下前端服务/组件仍在调用废弃的 `/api/v1/` 端点，建议逐步迁移：

| 服务/组件 | v1 端点数 | 风险 | 建议 |
|-----------|---------|------|------|
| `permissionService.js` | 30+ | 中 (权限数据) | 迁移到 v2 或确保 v1 有 admin 检查 |
| `filterVariantService.js` | 4 | 低 | 迁移到 v2 |
| `annotationService.js` | 5 | 中 (标注数据) | 迁移到 v2 |
| `useObjectIdentity.js` | 4 | 低 | 迁移到 v2 |
| `useMenuPermissions.js` | 3 | 中 (菜单权限) | 迁移到 v2 |
| `objectTypeService.js` | 1 | 低 | 迁移到 v2 (与 permissionService 合并) |
| `enumService.js` | 2 | 低 | 评估是否迁移 |
| `userPreferences.js` | 2 | 低 | 合并到 authService |

### 13. 导入导出端点无过滤
- **问题**: `useImportExportApi.js` / `boExportImportService.exportData()` 无 dimension scope 过滤
- **现状**: ExportDialog 当前不向用户开放
- **方向**: 导出时传入 `dimension_scope` 参数，后端过滤
- **文件**: `src/services/useImportExportApi.js`, `src/services/boExportImportService.js`
- **状态**: 待处理
- **优先级**: 中

---

## P2 - BUG-V049 长期修复 (2026-07-05 新增)

> **背景**: 生产 172.20.59.7:8081 全局导入卡死 0% 不动, 根因 `[Errno 24] Too many open files` (openpyxl read_only 临时文件泄漏)
> **当前修复**: setrlimit + wb.close() 临时缓解 (commit 89c63f0)
> **方向**: 彻底重构, 消除依赖

### 14. 重构 import_cascade 消除二次 load_workbook
- **问题**: `import_cascade` 调 `load_workbook` 解析每个 sheet, 然后 `_import_sheet` 又调 `load_workbook` 解析同一个 sheet。双重 IO + 双重临时文件
- **现状**: `import_cascade` 解析后把 `rows` 存到 `sheet_info["preview_rows"]`, 但没传给 `_import_sheet`
- **方向**: 修改 `import_cascade` 把 `sheet_info` 直接传给 `_import_sheet`, `_import_sheet` 优先使用内存 rows, 没有再 load
- **文件**: `meta/services/import_export_service.py:5576` (import_cascade) + `meta/services/import_export_service.py:6801` (_import_sheet)
- **状态**: 待处理
- **优先级**: 高 (单 sheet 导入节省 1 次 IO, 多 sheet 节省 3-4 次)
- **预期收益**: 单次导入 IO 减少 50%, FD 消耗减少 50%

### 15. 替换 openpyxl read_only 为 zipfile + xml.etree
- **问题**: openpyxl read_only 模式创建 3-5 个临时文件 / load_workbook, 不可控
- **现状**: 临时文件路径 `/tmp/tmpXXXXXX`, 不可预测, 难追踪
- **方向**: 自己用 zipfile 解压 .xlsx (本质是 zip) + xml.etree 解析 sheetN.xml + sharedStrings.xml, 整个过程在内存完成, 0 临时文件
- **文件**: 新建 `meta/utils/xlsx_reader.py` (替代 openpyxl read_only 路径)
- **状态**: 待处理
- **优先级**: 中 (彻底解决 FD 泄漏, 但工作量大)
- **预期收益**: 0 临时文件, FD 不增长; 启动更快 (无 zipfile 临时解压)
- **风险**: 兼容性测试 (公式、样式、空 cell、日期格式)

### 16. 进程级 ulimit 永久提升 (写进 systemd unit)
- **问题**: 当前 setrlimit 在 Python 进程内调用, 可能被 systemd / docker / hard limit 锁住
- **现状**: 临时 setrlimit 在 `waitress_server.py:36-55` (commit 89c63f0)
- **方向**: 
  1. **systemd unit** 加 `LimitNOFILE=65536`
  2. **docker compose** 加 `ulimits: nofile: 65536:65536`
  3. **deploy.sh** 加 `ulimit -n 65536` 在启动 waitress 前
  4. **k8s** 加 `securityContext.sysctls` 或 `pod.spec.containers.resources.limits`
- **文件**: `tools/systemd/meta-backend.service` (新建) + `tools/deploy.sh` + `docker-compose.yml` (如有)
- **状态**: 待处理
- **优先级**: 中 (临时 setrlimit 95% 情况有效, 但基础设施层修复更可靠)
- **预期收益**: 不会因为 Python setrlimit 失败导致再次卡死

---

## 已完成记录

| 日期 | 任务 | 说明 |
|------|------|------|
| 2026-06-09 | v1.0.4 dimension scope 修复 | 详见变更记录 |
| 2026-06-09 | /api/v1/relationships 兼容性修复 | special_routes_api.py L89-117 |
| 2026-06-09 | 全面 API 权限排查 | 确认所有高风险点 |
| 2026-07-05 | BUG-V049 setrlimit 修复 | waiter_server.py:36-55 + import_export_service.py:5637-5647 (commit 89c63f0) |
| 2026-07-05 | BUG-V049 DEPLOY_HANDOVER | DEPLOY_HANDOVER_BUG_V049.md 通知部署智能体 (commit d55cf4f + c328e8a) |
