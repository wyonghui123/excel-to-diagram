# Debug Session: user-group-association-no-log

**Status**: [FIXED]
**Created**: 2026-06-10
**Bug**: 删除 user_group 时，user_group_members / group_roles 中间表被级联清空，但 audit_logs 表无任何 DISSOCIATE 记录

## 根因
`meta/core/interceptors/cascade_interceptor.py::_cleanup_association_tables` 在 `before_action` 阶段执行级联删除（DELETE FROM user_group_members WHERE group_id=?），但 **完全没有写审计日志**。

调用链：`bo.delete('user_group', id)` → `BOFramework.execute` → `CascadeInterceptor.before_action._cleanup_association_tables`（先删 m2m，无审计） → `PersistenceInterceptor.after_action._do_delete`（再删 user_group，写 DELETE 审计）

`_cleanup_m2m_tables`（action_executor）虽然存在，但执行时机在 persistence 拦截器里，并且那时表已经被 cascade_interceptor 清空了。

## 修复
修改 `meta/core/interceptors/cascade_interceptor.py::_cleanup_association_tables`：
1. 级联删除前先 SELECT 待删的 target_ids
2. DELETE 后为每个被删的 association 写一条 DISSOCIATE 审计日志（含 parent_object_type/parent_object_id 关联父-子对象）

## 验证
e2e 测试：删除带成员/角色的 user_group

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| DELETE 审计记录 | 1 | 1 |
| DISSOCIATE 审计记录 | 0 | 2 (members + roles) |

## 步骤
- [x] Step 1: 列出假设
- [x] Step 2: 插桩 + 直接单测定位（在 _cleanup_m2m_tables 加日志发现 targets=[]）
- [x] Step 3: 证据分析（cascade_interceptor 先于 persistence 拦截器清空了 m2m 表）
- [x] Step 4: 最小修复（在 cascade_interceptor 写 DISSOCIATE 审计）
- [x] Step 5: 修复后验证（e2e 测试 PASS，DISSOCIATE=2）
- [x] Step 6: 用户确认
- [x] Step 7: 清理调试脚本

## 改动文件
- `meta/core/interceptors/cascade_interceptor.py` — 在 _cleanup_association_tables 写 DISSOCIATE 审计
- `meta/core/action_executor.py` — _cleanup_m2m_tables 保留原行为（兼容直接调用）