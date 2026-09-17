-- ============================================================
-- V2 权限审计 SQL (Spec 16 RENAME + Spec 19 软删后)
--
-- V2 关键变更:
--   - roles -> permission_sets
--   - role_permissions -> permission_set_permissions
--   - user_roles -> user_permission_sets
--   - user_groups -> orgs
--   - user_group_members -> org_members
--   - group_roles -> org_permission_sets
--   - role_data_permissions -> permission_set_data_permissions
--   - role_dimension_scopes -> permission_set_dimension_scopes
--   - role_effective_intents -> permission_set_effective_intents
--   - role_menu_permissions -> permission_set_menu_permissions
--   - group_data_permissions -> org_data_permissions
--   - user_group_members.is_manager / orgs.manager_id 软删 (Spec 19 M4)
--     不再作为审计维度; 受托管理员由 OrgAdminScopeService 提供
--   - 管理员仍 = 拥有 '*' 通配权限的用户
--
-- 使用方式:
--   sqlite3 meta/architecture.db < permission_audit.sql
--   或在 Python 中执行
-- ============================================================

.headers on
.mode column

-- ============================================================
-- 1. 权限总览
-- ============================================================

-- 1.1 查看所有权限
SELECT '=== 1.1 所有权限 ===' AS '';
SELECT id, code, name, description FROM permissions ORDER BY code;

-- ============================================================
-- 2. 管理员相关查询
-- ============================================================

-- 2.1 查看所有管理员 (拥有 '*' 权限的用户)
--    V2 简化: 管理员 = 拥有 '*' 权限的用户 (经 permission_sets 链路)
SELECT '=== 2.1 所有管理员 ===' AS '';
SELECT DISTINCT
    u.id AS user_id,
    u.username,
    u.display_name,
    u.email,
    u.status
FROM users u
JOIN user_permission_sets ups ON u.id = ups.user_id
JOIN permission_sets ps ON ups.permission_set_id = ps.id
JOIN permission_set_permissions psp ON ps.id = psp.permission_set_id
JOIN permissions p ON psp.permission_id = p.id
WHERE p.code = '*'
  AND ps.is_active = 1
ORDER BY u.username;

-- 2.2 查看管理员数量统计
SELECT '=== 2.2 管理员统计 ===' AS '';
SELECT
    COUNT(DISTINCT u.id) AS admin_count,
    (SELECT COUNT(*) FROM users WHERE status = 'active') AS active_user_count
FROM users u
JOIN user_permission_sets ups ON u.id = ups.user_id
JOIN permission_sets ps ON ups.permission_set_id = ps.id
JOIN permission_set_permissions psp ON ps.id = psp.permission_set_id
JOIN permissions p ON psp.permission_id = p.id
WHERE p.code = '*' AND ps.is_active = 1;

-- 2.3 查看 admin 角色详情
SELECT '=== 2.3 admin 权限集详情 ===' AS '';
SELECT
    ps.id AS permission_set_id,
    ps.code,
    ps.name,
    ps.description,
    ps.is_active,
    ps.is_system
FROM permission_sets ps
WHERE ps.code = 'admin';

-- 2.4 查看 admin 权限集的所有权限
SELECT '=== 2.4 admin 权限集权限 ===' AS '';
SELECT
    p.id AS perm_id,
    p.code,
    p.name,
    p.description
FROM permissions p
JOIN permission_set_permissions psp ON p.id = psp.permission_id
JOIN permission_sets ps ON psp.permission_set_id = ps.id
WHERE ps.code = 'admin';

-- ============================================================
-- 3. 用户权限查询
-- ============================================================

-- 3.1 查看某用户的完整权限链
--    使用示例: 将 'admin' 替换为目标用户名
SELECT '=== 3.1 用户权限链示例 (admin) ===' AS '';
WITH user_perms AS (
    SELECT DISTINCT
        u.id AS user_id,
        u.username,
        u.display_name,
        ps.code AS permission_set_code,
        ps.name AS permission_set_name,
        p.code AS perm_code,
        p.name AS perm_name
    FROM users u
    JOIN user_permission_sets ups ON u.id = ups.user_id
    JOIN permission_sets ps ON ups.permission_set_id = ps.id
    JOIN permission_set_permissions psp ON ps.id = psp.permission_set_id
    JOIN permissions p ON psp.permission_id = p.id
    WHERE u.username = 'admin' AND ps.is_active = 1
)
SELECT * FROM user_perms ORDER BY permission_set_code, perm_code;

-- 3.2 查看用户通过组织 (旧"用户组") 获得的权限
SELECT '=== 3.2 组织间接权限 ===' AS '';
SELECT DISTINCT
    u.username,
    o.name AS org_name,
    ps.code AS permission_set_code,
    ps.name AS permission_set_name,
    p.code AS perm_code,
    p.name AS perm_name
FROM users u
JOIN org_members om ON u.id = om.user_id
JOIN orgs o ON om.org_id = o.id
JOIN org_permission_sets ops ON o.id = ops.org_id
JOIN permission_sets ps ON ops.permission_set_id = ps.id
JOIN permission_set_permissions psp ON ps.id = psp.permission_set_id
JOIN permissions p ON psp.permission_id = p.id
WHERE ps.is_active = 1
ORDER BY u.username, o.name, ps.code;

-- 3.3 查看所有用户及其权限集
SELECT '=== 3.3 所有用户权限集 ===' AS '';
SELECT
    u.id AS user_id,
    u.username,
    u.display_name,
    u.status,
    GROUP_CONCAT(DISTINCT ps.name) AS permission_sets
FROM users u
LEFT JOIN user_permission_sets ups ON u.id = ups.user_id
LEFT JOIN permission_sets ps ON ups.permission_set_id = ps.id AND ps.is_active = 1
GROUP BY u.id, u.username, u.display_name, u.status
ORDER BY u.username;

-- ============================================================
-- 4. 组织查询 (旧"用户组", Spec 16 重命名)
-- ============================================================

-- 4.1 查看所有组织
SELECT '=== 4.1 所有组织 ===' AS '';
SELECT
    o.id AS org_id,
    o.name AS org_name,
    o.description,
    (SELECT COUNT(*) FROM org_members WHERE org_id = o.id) AS member_count
FROM orgs o
ORDER BY o.name;

-- 4.2 查看某组织的所有成员
--    使用示例: 将 'Administrators' 替换为目标组织名
SELECT '=== 4.2 组织成员 (Administrators) ===' AS '';
SELECT
    u.id AS user_id,
    u.username,
    u.display_name,
    u.status,
    om.joined_at
FROM users u
JOIN org_members om ON u.id = om.user_id
JOIN orgs o ON om.org_id = o.id
WHERE o.name = 'Administrators'
ORDER BY u.username;

-- 4.3 受托管理员审计 (Spec 19 M4 软删后)
--    orgs.manager_id 与 org_members.is_manager 已软删
--    受托管理员由 OrgAdminScopeService 通过资源矩阵动态计算
--    实际可用性数据见 tools/v19_p2_audit_remote.py
SELECT '=== 4.3 受托管理员 (审计) ===' AS '';
SELECT
    o.name AS org_name,
    COUNT(om.user_id) AS member_count
FROM orgs o
LEFT JOIN org_members om ON o.id = om.org_id
GROUP BY o.id, o.name
ORDER BY o.name;

-- ============================================================
-- 5. 权限覆盖与冲突检测 (V2b Deny-Overrides-Allow 预备)
-- ============================================================

-- 5.1 查看拥有敏感权限的用户
--    可扩展为检测潜在的权限滥用
SELECT '=== 5.1 敏感权限持有者 ===' AS '';
SELECT
    p.code AS sensitive_perm,
    p.name AS perm_name,
    GROUP_CONCAT(DISTINCT u.username) AS users
FROM permissions p
JOIN permission_set_permissions psp ON p.id = psp.permission_id
JOIN permission_sets ps ON psp.permission_set_id = ps.id
JOIN user_permission_sets ups ON ps.id = ups.permission_set_id
JOIN users u ON ups.user_id = u.id
WHERE u.status = 'active' AND ps.is_active = 1
  AND p.code IN ('*', 'user:delete', 'role:assign', 'permission:grant')
GROUP BY p.code, p.name
ORDER BY p.code;

-- 5.2 查看拥有多权限集的用户 (潜在职责分离风险)
SELECT '=== 5.2 多权限集用户 (潜在 SoD 风险) ===' AS '';
SELECT
    u.id AS user_id,
    u.username,
    u.display_name,
    COUNT(DISTINCT ps.id) AS permission_set_count,
    GROUP_CONCAT(DISTINCT ps.name) AS permission_sets
FROM users u
JOIN user_permission_sets ups ON u.id = ups.user_id
JOIN permission_sets ps ON ups.permission_set_id = ps.id AND ps.is_active = 1
WHERE u.status = 'active'
GROUP BY u.id, u.username, u.display_name
HAVING COUNT(DISTINCT ps.id) >= 3
ORDER BY permission_set_count DESC, u.username;

-- ============================================================
-- 6. 审计与合规
-- ============================================================

-- 6.1 查看最近创建的用户 (需要 audit_logs 表支持)
-- SELECT '=== 6.1 最近创建的用户 ===' AS '';
-- SELECT
--     u.id,
--     u.username,
--     u.display_name,
--     u.created_at,
--     al.action,
--     al.operator
-- FROM users u
-- LEFT JOIN audit_logs al ON al.object_type = 'user' AND al.object_id = u.id AND al.action = 'create'
-- ORDER BY u.created_at DESC
-- LIMIT 20;

-- 6.2 查看非活跃用户 (长期未登录)
-- SELECT '=== 6.2 非活跃用户 ===' AS '';
-- SELECT
--     u.id,
--     u.username,
--     u.display_name,
--     u.is_active,
--     (SELECT MAX(created_at) FROM audit_logs WHERE operator = u.username) AS last_activity
-- FROM users u
-- WHERE u.is_active = 1
--   AND (
--     (SELECT MAX(created_at) FROM audit_logs WHERE operator = u.username) IS NULL
--     OR (SELECT MAX(created_at) FROM audit_logs WHERE operator = u.username) < datetime('now', '-30 days')
--   )
-- ORDER BY last_activity;

-- 6.3 权限变更历史 (需要 audit_logs 表支持)
-- SELECT '=== 6.3 权限变更记录 ===' AS '';
-- SELECT
--     al.created_at,
--     al.operator,
--     al.action,
--     al.object_type,
--     al.object_id,
--     al.old_value,
--     al.new_value
-- FROM audit_logs al
-- WHERE al.object_type = 'permission'
--    OR al.object_type = 'permission_set'
-- ORDER BY al.created_at DESC
-- LIMIT 50;

-- ============================================================
-- 7. 健康检查
-- ============================================================

-- 7.1 检查孤立的用户权限集关联 (权限集已被删除但用户仍有关联)
SELECT '=== 7.1 孤立用户权限集 ===' AS '';
SELECT
    ups.id AS ups_id,
    u.username,
    u.id AS user_id,
    ups.permission_set_id
FROM user_permission_sets ups
JOIN users u ON ups.user_id = u.id
WHERE ups.permission_set_id NOT IN (SELECT id FROM permission_sets);
-- 结果为空 = 正常

-- 7.2 检查孤立的权限集权限 (权限已被删除但权限集仍有关联)
SELECT '=== 7.2 孤立权限集权限 ===' AS '';
SELECT
    psp.id AS psp_id,
    ps.name AS permission_set_name,
    psp.permission_id
FROM permission_set_permissions psp
JOIN permission_sets ps ON psp.permission_set_id = ps.id
WHERE psp.permission_id NOT IN (SELECT id FROM permissions);
-- 结果为空 = 正常

-- 7.3 检查孤立组织成员 (用户或组织已被删除)
SELECT '=== 7.3 孤立组织成员 ===' AS '';
SELECT
    om.id AS om_id,
    om.user_id,
    om.org_id
FROM org_members om
WHERE om.user_id NOT IN (SELECT id FROM users)
   OR om.org_id NOT IN (SELECT id FROM orgs);
-- 结果为空 = 正常

-- 7.4 检查 orphaned admin (没有任何有效权限链路的用户)
SELECT '=== 7.4 Orphaned 用户 (无任何权限) ===' AS '';
SELECT
    u.id,
    u.username,
    u.display_name
FROM users u
WHERE u.status = 'active'
  AND u.id NOT IN (
    SELECT DISTINCT ups.user_id FROM user_permission_sets ups
    JOIN permission_sets ps ON ups.permission_set_id = ps.id
    JOIN permission_set_permissions psp ON ps.id = psp.permission_set_id
    WHERE ps.is_active = 1
  )
ORDER BY u.username;
-- 结果可能为空 = 正常 (某些用户可能只有数据权限)

-- ============================================================
-- 8. 数据统计
-- ============================================================

SELECT '=== 8. 权限体系统计 ===' AS '';
SELECT '总用户数' AS metric, COUNT(*) AS value FROM users;
SELECT '活跃用户数' AS metric, COUNT(*) AS value FROM users WHERE status = 'active';
SELECT '权限集总数' AS metric, COUNT(*) AS value FROM permission_sets;
SELECT '活跃权限集数' AS metric, COUNT(*) AS value FROM permission_sets WHERE is_active = 1;
SELECT '权限总数' AS metric, COUNT(*) AS value FROM permissions;
SELECT '组织总数' AS metric, COUNT(*) AS value FROM orgs;
SELECT '组织成员关系数' AS metric, COUNT(*) AS value FROM org_members;

.quit