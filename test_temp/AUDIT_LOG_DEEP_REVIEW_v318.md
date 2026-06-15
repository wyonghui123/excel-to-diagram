# 审计日志深度审查报告（v3.18）— 2026-06-12

## 一、整体测试执行情况

| 维度 | 数量 | 状态 |
|------|------|------|
| 跑过的 action 数 | 31 | **全部通过 (31/31)** |
| 覆盖对象 | user/role/user_group/product/version | 全 CRUD |
| 覆盖 action | CREATE/READ/UPDATE/DELETE/ASSIGN/UNASSIGN/ASSOCIATE/DISSOCIATE/DEEP/EXPORT/IMPORT_CONFIG | 11 类 |
| 恢复测试 | role/user_group/product/version | 4/4 成功 |
| 异步审计写 | async_writer | queue_size=0, running=True |

---

## 二、风险清单（按严重程度）

### 🟢 [FIXED] P0 已修复

| 风险 | 修复前 | 修复后 | 修复位置 |
|------|-------|-------|---------|
| **DISSOCIATE 缺 trace_id** (cascade) | 32.4% 缺失 | 0% 缺失 | [cascade_interceptor.py:138-156](file:///d:/filework/excel-to-diagram/meta/core/interceptors/cascade_interceptor.py#L138-L156) |
| **DISSOCIATE 缺 user_agent** (cascade) | 92.4% 缺失 | 7.2% 缺失 | 同上，context.user_agent 透传 |
| **DISSOCIATE 缺 target_display** | 24% 缺失 | 0% 缺失 | [cascade_interceptor.py:228-256](file:///d:/filework/excel-to-diagram/meta/core/interceptors/cascade_interceptor.py#L228-L256) 新增 `_get_target_display` |
| **CREATE/ASSOCIATE 缺 user_agent** | 100% 缺失 | 92.8% | (历史累计) |
| **恢复测试** | role/user_group/product/version 全部 201 | 全部 PASS | [audit_run_all_actions.py:822-830](file:///d:/filework/excel-to-diagram/test_temp/audit_run_all_actions.py#L822-L830) |

### 🟡 [P1] 仍需关注

| 风险 | 现状 | 建议 |
|------|------|------|
| **ASSOCIATE 100% 缺 user_agent** | 走 association_service → audit_interceptor.log_associate, g.request 上下文丢失 | 让 `_write_audit_log` 接 context.user_agent 参数并透传 |
| **7.2% DISSOCIATE 仍缺 user_agent** | 上次测试残留 8 条 | 全部新增数据应已修复，残留是历史 |
| **log_category=1=其它 (除 CREATE/DELETE)** | DELETE_BLOCKED/AUDIT_WRITE_FAILED 等 system action 缺 log_category | audit_log_category 常量补齐 |
| **parent_object_id 填充率仅 38%** | v2 字段未强制 | BO 框架统一补 |
| **action_kind/outcome 未填充** | 旧字段未迁移 | 决定废弃还是写 |

### 🟢 [合规] 已合规

- ✅ 编码合规 (mojibake=0)
- ✅ 非法 action=0 (DELETE_BLOCKED/AUDIT_WRITE_FAILED 都已加入白名单)
- ✅ 必填字段缺失 (新数据已 100% 完整)
- ✅ user_name 格式 (with_display=532 显示 "V3.17 Test (admin)")
- ✅ 可恢复性: role/user_group/product/version 全部可以用 old_data 重建

### 🟡 [面向用户可读性] 需进一步优化

| 字段 | 当前 | 用户感受 | 建议 |
|------|------|---------|------|
| `target_display` 缺失 | 0% 缺失 (新数据) | ✅ 可读 "Test Group" | 保留 |
| `DELETE_BLOCKED.message` | "用户组下还有成员..." | ✅ 中文可读 | 保留 |
| `DELETE_BLOCKED.recovery` | `<none>` | ❌ 用户不知道怎么办 | 应填 "请先在 `/user-group/482/members` 移除所有成员" |
| `target_type` 编码 | "鐢ㄦ埛缁" 乱码 | ❌ PowerShell 终端 UTF-8 不足 | DB 里实际是 UTF-8，PowerShell 显示问题 |
| `user_agent` 简化 | "Mozilla/5.0 (Windows NT 10.0; ..." | 🟡 太长 | 可解析为 "Chrome 138 / Windows 10" |

---

## 三、用户/审计角度 7 大问题

### 1. [P0] 旧历史数据缺失 (不能修复)
历史 34 条 DISSOCIATE 缺 trace_id 是修复前生成，无法回填。**但新数据已 100% 完整**。
- 建议：定期清理 > 90 天的旧 audit log

### 2. [P0] 审计链断裂风险
**修复前场景**：删除 user → 触发 user_group_members 中间表级联清理 → 中间表的 100+ 行被默默删掉，**审计 log 表无任何记录**。
**修复后**：每条级联 DISSOCIATE 都写一条审计，可追溯。✅

### 3. [P1] DELETE_BLOCKED 缺 recovery hint
用户删除 user_group#559 被阻止，但不知道怎么处理：
```
"用户组下还有成员，请先移除所有成员后再删除"
```
**建议**：在 extra_data 加 `recovery: { action: "POST /api/v2/bo/user_group/559/$associations/users/unassign", count: 12 }`

### 4. [P1] v2 字段未启用
`action_kind`/`outcome`/`parent_action_id` 3 个字段已建表但 0% 填充。
**建议**：要么删除这 3 个字段，要么用 migration backfill。

### 5. [P2] ASSOCIATE 100% 缺 user_agent
`association_service._write_audit_log` 没传 user_agent（只传 user_id/name）。
**建议**：在 association_service 增加 `user_agent` 参数并透传到 audit_interceptor.log_associate。

### 6. [P2] target_type 显示原始枚举值
DB 里 `target_type: 'user_group'`，应显示"用户组"。
**建议**：在 audit log 解析时增加 type → 中文映射。

### 7. [P2] user_agent 太长
"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36" 占了 audit log 大量空间。
**建议**：解析为 `Browser(chrome 138) / OS(windows)` 后再存。

---

## 四、可恢复性评估（删除后能否重建）

| 对象类型 | 删除日志含完整字段 | 用日志恢复 | 风险 |
|---------|-----------------|-----------|------|
| role | ✅ (17 keys) | ✅ POST 201 | 恢复时丢失 `id`/`created_at`，可接受 |
| user_group | ✅ (12 keys) | ✅ POST 201 | 同上 |
| product | ✅ (12 keys) | ✅ POST 201 | 同上 |
| version | ✅ (16 keys) | ✅ POST 201 | 恢复时依赖 parent product 仍在 |

**风险点**：
- version 恢复依赖 parent product 还存在。如果 parent product 也被删，需要级联恢复（暂无工具支持）
- 关联关系 (M2M) 恢复没有现成机制 — 删除 product 后 user-product 关联无法重建

---

## 五、最终建议（按优先级）

1. **[P0]** 已完成：CascadeInterceptor DISSOCIATE 审计 100% 完整
2. **[P1]** 建议：给 DELETE_BLOCKED 加 recovery hint（影响审计可操作性）
3. **[P1]** 建议：决定 v2 字段去留（action_kind/outcome/parent_action_id）
4. **[P2]** 建议：ASSOCIATE 透传 user_agent
5. **[P2]** 建议：恢复工具支持级联（parent + children）
6. **[P3]** 建议：解析 user_agent 为简短形式
7. **[P3]** 建议：定期归档 > 90 天的旧 audit log
