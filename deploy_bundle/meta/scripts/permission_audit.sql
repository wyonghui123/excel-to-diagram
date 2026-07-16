-- ============================================================
-- V1 权限审计 SQL (基于简化后的权限模型)
--
-- V1 简化说明:
--   - 管理员 = 拥有 '*' 通配权限的用户
--   - roles 表不再有 is_super_admin 和 priority 字段
--   - 权限赋权路径: 用户 → 用户组 → 角色 → 权限
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
--    V1 简化: 管理员 = 拥有 '*' 权限的用户
SELECT '=== 2.1 所有管理员 ===' AS '';
SELECT DISTINCT
    u.id AS user_id,
    u.username,
    u.display_name,
    u.email,
    u.is_active
FROM users u
JOIN user_roles ur ON u.id = ur.user_id
JOIN roles r ON ur.role_id = r.id
JOIN role_permissions rp ON r.id = rp.role_id
JOIN permissions p ON rp.permission_id = p.id
WHERE p.code = '*'
  AND r.is_active = 1
ORDER BY u.username;

-- 2.2 查看管理员数量统计
SELECT '=== 2.2 管理员统计 ===' AS '';
SELECT
    COUNT(DISTINCT u.id) AS admin_count,
    (SELECT COUNT(*) FROM users WHERE is_active = 1) AS active_user_count
FROM users u
JOIN user_roles ur ON u.id = ur.user_id
JOIN roles r ON ur.role_id = r.id
JOIN role_permissions rp ON r.id = rp.role_id
JOIN permissions p ON rp.permission_id = p.id
WHERE p.code = '*' AND r.is_active = 1;

-- 2.3 查看 admin 角色详情
SELECT '=== 2.3 admin 角色详情 ===' AS '';
SELECT
    r.id AS role_id,
    r.code,
    r.name,
    r.description,
    r.is_active,
    r.is_system
FROM roles r
WHERE r.code = 'admin';

-- 2.4 查看 admin 角色的所有权限
SELECT '=== 2.4 admin 角色权限 ===' AS '';
SELECT
    p.id AS perm_id,
    p.code,
    p.name,
    p.description
FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN roles r ON rp.role_id = r.id
WHERE r.code = 'admin';

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
        r.code AS role_code,
        r.name AS role_name,
        p.code AS perm_code,
        p.name AS perm_name
    FROM users u
    JOIN user_roles ur ON u.id = ur.user_id
    JOIN roles r ON ur.role_id = r.id
    JOIN role_permissions rp ON r.id = rp.role_id
    JOIN permissions p ON rp.permission_id = p.id
    WHERE u.username = 'admin' AND r.is_active = 1
)
SELECT * FROM user_perms ORDER BY role_code, perm_code;

-- 3.2 查看用户通过用户组获得的权限
SELECT '=== 3.2 用户组间接权限 ===' AS '';
SELECT DISTINCT
    u.username,
    ug.name AS group_name,
    r.code AS role_code,
    r.name AS role_name,
    p.code AS perm_code,
    p.name AS perm_name
FROM users u
JOIN user_group_members ugm ON u.id = ugm.user_id
JOIN user_groups ug ON ugm.group_id = ug.id
JOIN group_roles gr ON ug.id = gr.group_id
JOIN roles r ON gr.role_id = r.id
JOIN role_permissions rp ON r.id = rp.role_id
JOIN permissions p ON rp.permission_id = p.id
WHERE r.is_active = 1
ORDER BY u.username, ug.name, r.code;

-- 3.3 查看所有用户及其角色
SELECT '=== 3.3 所有用户角色 ===' AS '';
SELECT
    u.id AS user_id,
    u.username,
    u.display_name,
    u.is_active,
    GROUP_CONCAT(DISTINCT r.name, ', ') AS roles
FROM users u
LEFT JOIN user_roles ur ON u.id = ur.user_id
LEFT JOIN roles r ON ur.role_id = r.id AND r.is_active = 1
GROUP BY u.id, u.username, u.display_name, u.is_active
ORDER BY u.username;

-- ============================================================
-- 4. 用户组查询
-- ============================================================

-- 4.1 查看所有用户组
SELECT '=== 4.1 所有用户组 ===' AS '';
SELECT
    ug.id AS group_id,
    ug.name AS group_name,
    ug.description,
    ug.is_active,
    (SELECT COUNT(*) FROM user_group_members WHERE group_id = ug.id) AS member_count
FROM user_groups ug
ORDER BY ug.name;

-- 4.2 查看某用户组的所有成员
--    使用示例: 将 'Administrators' 替换为目标组名
SELECT '=== 4.2 用户组成员 (Administrators) ===' AS '';
SELECT
    u.id AS user_id,
    u.username,
    u.display_name,
    u.is_active,
    ugm.is_manager AS is_group_manager,
    ugm.joined_at
FROM users u
JOIN user_group_members ugm ON u.id = ugm.user_id
JOIN user_groups ug ON ugm.group_id = ug.id
WHERE ug.name = 'Administrators'
ORDER BY ugm.is_manager DESC, u.username;

-- 4.3 查看用户组的管理员
SELECT '=== 4.3 用户组管理员 ===' AS '';
SELECT
    ug.name AS group_name,
    u.username AS manager_username,
    u.display_name AS manager_display
FROM user_group_members ugm
JOIN user_groups ug ON ugm.group_id = ug.id
JOIN users u ON ugm.user_id = u.id
WHERE ugm.is_manager = 1
ORDER BY ug.name;

-- ============================================================
-- 5. 权限覆盖与冲突检测 (V2b Deny-Overrides-Allow 预备)
-- ============================================================

-- 5.1 查看拥有敏感权限的用户
--    可扩展为检测潜在的权限滥用
SELECT '=== 5.1 敏感权限持有者 ===' AS '';
SELECT
    p.code AS sensitive_perm,
    p.name AS perm_name,
    GROUP_CONCAT(DISTINCT u.username, ', ') AS users
FROM permissions p
JOIN role_permissions rp ON p.id = rp.permission_id
JOIN roles r ON rp.role_id = r.id
JOIN user_roles ur ON r.id = ur.role_id
JOIN users u ON ur.user_id = u.id
WHERE u.is_active = 1 AND r.is_active = 1
  AND p.code IN ('*', 'user:delete', 'role:assign', 'permission:grant')
GROUP BY p.code, p.name
ORDER BY p.code;

-- 5.2 查看拥有多角色的用户 (潜在职责分离风险)
SELECT '=== 5.2 多角色用户 (潜在 SoD 风险) ===' AS '';
SELECT
    u.id AS user_id,
    u.username,
    u.display_name,
    COUNT(DISTINCT r.id) AS role_count,
    GROUP_CONCAT(DISTINCT r.name, ', ') AS roles
FROM users u
JOIN user_roles ur ON u.id = ur.user_id
JOIN roles r ON ur.role_id = r.id AND r.is_active = 1
WHERE u.is_active = 1
GROUP BY u.id, u.username, u.display_name
HAVING COUNT(DISTINCT r.id) >= 3
ORDER BY role_count DESC, u.username;

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
--    OR al.object_type = 'role'
-- ORDER BY al.created_at DESC
-- LIMIT 50;

-- ============================================================
-- 7. 健康检查
-- ============================================================

-- 7.1 检查孤立的用户角色关联 (角色已被删除但用户仍有关联)
SELECT '=== 7.1 孤立用户角色 ===' AS '';
SELECT
    ur.id AS ur_id,
    u.username,
    u.id AS user_id,
    ur.role_id
FROM user_roles ur
JOIN users u ON ur.user_id = u.id
WHERE ur.role_id NOT IN (SELECT id FROM roles);
-- 结果为空 = 正常

-- 7.2 检查孤立的角色权限 (权限已被删除但角色仍有关联)
SELECT '=== 7.2 孤立角色权限 ===' AS '';
SELECT
    rp.id AS rp_id,
    r.name AS role_name,
    rp.permission_id
FROM role_permissions rp
JOIN roles r ON rp.role_id = r.id
WHERE rp.permission_id NOT IN (SELECT id FROM permissions);
-- 结果为空 = 正常

-- 7.3 检查孤立用户组成员 (用户或组已被删除)
SELECT '=== 7.3 孤立用户组成员 ===' AS '';
SELECT
    ugm.id AS ugm_id,
    ugm.user_id,
    ugm.group_id
FROM user_group_members ugm
WHERE ugm.user_id NOT IN (SELECT id FROM users)
   OR ugm.group_id NOT IN (SELECT id FROM user_groups);
-- 结果为空 = 正常

-- 7.4 检查 orphaned admin (没有任何有效权限链路的用户)
SELECT '=== 7.4 Orphaned 用户 (无任何权限) ===' AS '';
SELECT
    u.id,
    u.username,
    u.display_name
FROM users u
WHERE u.is_active = 1
  AND u.id NOT IN (
    SELECT DISTINCT ur.user_id FROM user_roles ur
    JOIN roles r ON ur.role_id = r.id
    JOIN role_permissions rp ON r.id = rp.role_id
    WHERE r.is_active = 1
  )
ORDER BY u.username;
-- 结果可能为空 = 正常 (某些用户可能只有数据权限)

-- ============================================================
-- 8. 数据统计
-- ============================================================

SELECT '=== 8. 权限体系统计 ===' AS '';
SELECT '总用户数' AS metric, COUNT(*) AS value FROM users;
SELECT '活跃用户数' AS metric, COUNT(*) AS value FROM users WHERE is_active = 1;
SELECT '角色总数' AS metric, COUNT(*) AS value FROM roles;
SELECT '活跃角色数' AS metric, COUNT(*) AS value FROM roles WHERE is_active = 1;
SELECT '权限总数' AS metric, COUNT(*) AS value FROM permissions;
SELECT '用户组总数' AS metric, COUNT(*) AS value FROM user_groups;
SELECT '用户组成员关系数' AS metric, COUNT(*) AS value FROM user_group_members;

.quit
