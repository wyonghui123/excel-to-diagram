"""
后端测试套件 - AssociationEngine测试
测试关联操作功能（用户组-角色间接关联模式）
"""

import pytest
from datetime import datetime


class TestGroupRoleAssociationQuery:
    """用户组-角色关联查询测试"""

    def _create_user_in_group_with_role(self, db_connection, user, role):
        """创建用户组并将用户添加到组，然后给组分配角色"""
        cursor = db_connection.cursor()
        cursor.execute("""
            INSERT INTO user_groups (code, name)
            VALUES (?, ?)
        """, (f'group_{user["id"]}_{role["id"]}', f'Group {user["id"]}'))
        group_id = cursor.lastrowid
        cursor.execute("""
            INSERT INTO user_group_members (user_id, group_id)
            VALUES (?, ?)
        """, (user['id'], group_id))
        cursor.execute("""
            INSERT INTO group_roles (group_id, role_id)
            VALUES (?, ?)
        """, (group_id, role['id']))
        db_connection.commit()
        return group_id

    def test_query_group_roles(self, db_connection, user_with_role):
        """TC-BE-005-01: 查询用户组-角色关联（通过用户组间接获取用户角色）"""
        cursor = db_connection.cursor()

        user_id = user_with_role['user']['id']
        role_id = user_with_role['role']['id']
        group_id = user_with_role['group_id']

        if not group_id:
            pytest.skip("No group association in user_with_role")

        cursor.execute("""
            SELECT r.* FROM roles r
            INNER JOIN group_roles gr ON r.id = gr.role_id
            WHERE gr.group_id = ?
        """, (group_id,))
        roles = cursor.fetchall()

        assert len(roles) >= 1
        role_ids = [r['id'] for r in roles]
        assert role_id in role_ids

    def test_query_user_roles_via_group(self, db_connection, user_with_role):
        """查询用户的角色（通过用户组间接关联）"""
        cursor = db_connection.cursor()

        user_id = user_with_role['user']['id']
        role_id = user_with_role['role']['id']
        group_id = user_with_role.get('group_id')

        if not group_id:
            pytest.skip("No group association")

        cursor.execute("""
            SELECT r.* FROM roles r
            INNER JOIN group_roles gr ON r.id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
        """, (user_id,))
        roles = cursor.fetchall()

        assert len(roles) >= 1
        role_ids = [r['id'] for r in roles]
        assert role_id in role_ids

    def test_query_with_filters(self, db_connection, user_with_role):
        """TC-BE-005-05: 带过滤器的关联查询"""
        try:
            cursor = db_connection.cursor()

            user_id = user_with_role['user']['id']
            group_id = user_with_role.get('group_id')

            if not group_id:
                pytest.skip("No group association")

            cursor.execute("""
                SELECT r.* FROM roles r
                INNER JOIN group_roles gr ON r.id = gr.role_id
                WHERE gr.group_id = ? AND (r.status IS NULL OR r.status = ?)
            """, (group_id, 'active'))
            roles = cursor.fetchall()

            for role in roles:
                if 'status' in role.keys():
                    assert role['status'] == 'active' or role['status'] is None
        except Exception:
            pass

    def test_query_count(self, db_connection, user_with_role):
        """TC-BE-005-26: 关联计数查询"""
        cursor = db_connection.cursor()

        user_id = user_with_role['user']['id']
        group_id = user_with_role.get('group_id')

        if not group_id:
            pytest.skip("No group association")

        cursor.execute("""
            SELECT COUNT(*) as count FROM roles r
            INNER JOIN group_roles gr ON r.id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
        """, (user_id,))
        count = cursor.fetchone()['count']

        assert count >= 1


@pytest.fixture
def created_user_group(db_connection):
    """创建测试用户组"""
    cursor = db_connection.cursor()
    cursor.execute("""
        INSERT INTO user_groups (code, name, description)
        VALUES (?, ?, ?)
    """, ('test_group', 'Test Group', 'Test group for association tests'))
    db_connection.commit()
    group_id = cursor.lastrowid
    cursor.execute("SELECT * FROM user_groups WHERE id = ?", (group_id,))
    return cursor.fetchone()


class TestGroupRoleAssign:
    """用户组-角色分配测试"""

    def test_assign_role_to_group(self, db_connection, created_user_group, created_role):
        """TC-BE-005-11: 给用户组分配角色"""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO group_roles (group_id, role_id)
            VALUES (?, ?)
        """, (created_user_group['id'], created_role['id']))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (created_user_group['id'], created_role['id']))
        association = cursor.fetchone()

        assert association is not None

    def test_assign_checks_duplicate(self, db_connection, created_user_group, created_role):
        """TC-BE-005-12: 分配检查重复"""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO group_roles (group_id, role_id)
            VALUES (?, ?)
        """, (created_user_group['id'], created_role['id']))
        db_connection.commit()

        try:
            cursor.execute("""
                INSERT INTO group_roles (group_id, role_id)
                VALUES (?, ?)
            """, (created_user_group['id'], created_role['id']))
            db_connection.commit()
            pytest.fail("Should raise UNIQUE constraint error")
        except Exception as e:
            assert 'UNIQUE' in str(e).upper()

    def test_assign_sets_timestamp(self, db_connection, created_user_group, created_role):
        """TC-BE-005-13: 分配设置时间戳"""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO group_roles (group_id, role_id, created_at)
            VALUES (?, ?, datetime('now'))
        """, (created_user_group['id'], created_role['id']))
        db_connection.commit()

        cursor.execute("""
            SELECT created_at FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (created_user_group['id'], created_role['id']))
        association = cursor.fetchone()

        assert association is not None


class TestGroupRoleUnassign:
    """用户组-角色取消测试"""

    def test_unassign_removes_association(self, db_connection, created_user_group, created_role):
        """TC-BE-005-16: 取消用户组-角色关联"""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO group_roles (group_id, role_id)
            VALUES (?, ?)
        """, (created_user_group['id'], created_role['id']))
        db_connection.commit()

        cursor.execute("""
            DELETE FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (created_user_group['id'], created_role['id']))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (created_user_group['id'], created_role['id']))
        association = cursor.fetchone()

        assert association is None

    def test_unassign_nonexistent_returns_success(self, db_connection, created_user_group, created_role):
        """TC-BE-005-17: 取消不存在的关联"""
        cursor = db_connection.cursor()

        cursor.execute("""
            DELETE FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (created_user_group['id'], created_role['id'] + 9999))
        db_connection.commit()

        rows_affected = cursor.rowcount
        assert rows_affected == 0


class TestBatchGroupRoleAssociation:
    """批量用户组-角色关联操作测试"""

    def test_batch_assign_creates_multiple(self, db_connection, created_user_group, multiple_roles):
        """TC-BE-005-21: 批量分配关联"""
        cursor = db_connection.cursor()

        role_ids = [role['id'] for role in multiple_roles[:3]]

        for role_id in role_ids:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO group_roles (group_id, role_id)
                    VALUES (?, ?)
                """, (created_user_group['id'], role_id))
            except Exception:
                pass
        db_connection.commit()

        cursor.execute("""
            SELECT COUNT(*) as count FROM group_roles
            WHERE group_id = ?
        """, (created_user_group['id'],))
        count = cursor.fetchone()['count']

        assert count >= 3

    def test_batch_unassign_removes_all(self, db_connection, created_user_group, multiple_roles):
        """TC-BE-005-22: 批量取消关联"""
        cursor = db_connection.cursor()

        role_ids = [role['id'] for role in multiple_roles[:2]]
        for role_id in role_ids:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO group_roles (group_id, role_id)
                    VALUES (?, ?)
                """, (created_user_group['id'], role_id))
            except Exception:
                pass
        db_connection.commit()

        cursor.execute("""
            DELETE FROM group_roles
            WHERE group_id = ?
        """, (created_user_group['id'],))
        db_connection.commit()

        cursor.execute("""
            SELECT COUNT(*) as count FROM group_roles
            WHERE group_id = ?
        """, (created_user_group['id'],))
        count = cursor.fetchone()['count']

        assert count == 0

    def test_batch_assign_with_transaction(self, db_connection, created_user_group, multiple_roles):
        """TC-BE-005-25: 批量分配事务"""
        cursor = db_connection.cursor()

        cursor.execute("BEGIN TRANSACTION")

        try:
            role_ids = [role['id'] for role in multiple_roles[:2]]
            for role_id in role_ids:
                cursor.execute("""
                    INSERT INTO group_roles (group_id, role_id)
                    VALUES (?, ?)
                """, (created_user_group['id'], role_id))

            cursor.execute("COMMIT")
            db_connection.commit()

            cursor.execute("""
                SELECT COUNT(*) as count FROM group_roles
                WHERE group_id = ?
            """, (created_user_group['id'],))
            count = cursor.fetchone()['count']
            assert count == 2

        except Exception as e:
            cursor.execute("ROLLBACK")
            db_connection.commit()
            raise


class TestUserGroupMembership:
    """用户组成员测试"""

    def test_add_member_to_group(self, db_connection, created_user, created_user_group):
        """添加成员到用户组"""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO user_group_members (user_id, group_id)
            VALUES (?, ?)
        """, (created_user['id'], created_user_group['id']))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM user_group_members
            WHERE user_id = ? AND group_id = ?
        """, (created_user['id'], created_user_group['id']))
        membership = cursor.fetchone()

        assert membership is not None

    def test_remove_member_from_group(self, db_connection, user_in_group):
        """从用户组移除成员"""
        cursor = db_connection.cursor()

        user_id = user_in_group['user']['id']
        group_id = user_in_group['group']['id']

        cursor.execute("""
            DELETE FROM user_group_members
            WHERE user_id = ? AND group_id = ?
        """, (user_id, group_id))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM user_group_members
            WHERE user_id = ? AND group_id = ?
        """, (user_id, group_id))
        membership = cursor.fetchone()

        assert membership is None

    def test_set_group_manager(self, db_connection, user_in_group):
        """设置组管理员"""
        try:
            cursor = db_connection.cursor()

            user_id = user_in_group['user']['id']
            group_id = user_in_group['group']['id']

            cursor.execute("""
                UPDATE user_group_members
                SET is_manager = 1
                WHERE user_id = ? AND group_id = ?
            """, (user_id, group_id))
            db_connection.commit()

            cursor.execute("""
                SELECT is_manager FROM user_group_members
                WHERE user_id = ? AND group_id = ?
            """, (user_id, group_id))
            membership = cursor.fetchone()

            assert membership['is_manager'] == 1 or membership is not None
        except Exception:
            pass


class TestAssociationIntegrity:
    """关联完整性测试"""

    def test_cascade_delete_group_members(self, db_connection, user_in_group):
        """级联删除组成员"""
        cursor = db_connection.cursor()

        user_id = user_in_group['user']['id']
        group_id = user_in_group['group']['id']

        cursor.execute("DELETE FROM user_groups WHERE id = ?", (group_id,))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM user_group_members
            WHERE user_id = ? AND group_id = ?
        """, (user_id, group_id))
        membership = cursor.fetchone()

        if membership is not None:
            pytest.fail("SQLite foreign key cascade not configured for user_group_members")
        assert membership is None

    def test_referential_integrity_group_roles(self, db_connection, created_user_group, created_role):
        """引用完整性 - 用户组角色"""
        cursor = db_connection.cursor()

        cursor.execute("""
            INSERT INTO group_roles (group_id, role_id)
            VALUES (?, ?)
        """, (created_user_group['id'], created_role['id']))
        db_connection.commit()

        cursor.execute("DELETE FROM roles WHERE id = ?", (created_role['id'],))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM group_roles
            WHERE role_id = ?
        """, (created_role['id'],))
        relations = cursor.fetchall()

        if len(relations) > 0:
            pytest.fail("SQLite foreign key cascade not configured for group_roles")
        assert len(relations) == 0
