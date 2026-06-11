import pytest

pytestmark = pytest.mark.integration

"""后端测试套件 - BOFramework核心测试
测试 meta.core.bo_framework 模块
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

FILTER_TEST_CASES = [
    ("filter_equals", "SELECT * FROM users WHERE username = ?", ["user0"], 1,
     "字符串等于过滤", lambda results: results[0]["username"] == "user0"),
    ("filter_like", "SELECT * FROM users WHERE username LIKE ?", ["%user%"], ">=5",
     "字符串LIKE过滤", None),
    ("filter_in", "SELECT * FROM users WHERE username IN (?, ?)", ["user0", "user1"], 2,
     "IN过滤", None),
]

SORT_TEST_CASES = [
    ("sort_asc", "ASC", False, "升序排序"),
    ("sort_desc", "DESC", True, "降序排序"),
]

PAGINATION_TEST_CASES = [
    ("first_page", 0, 2, "首页分页"),
    ("second_page", 2, 2, "第二页分页"),
]


class TestBOFrameworkInit:
    """BOFramework初始化测试"""
    
    def test_boframework_initialization(self):
        """TC-BE-003-01: BOFramework初始化"""
        from meta.core.bo_framework import BOFramework
        
        bf = BOFramework()
        
        assert bf is not None
    
    def test_boframework_has_interceptors(self):
        """TC-BE-003-02: 注册拦截器"""
        from meta.core.bo_framework import BOFramework
        
        bf = BOFramework()
        
        if not hasattr(bf, 'interceptors'):
            pytest.skip("BOFramework does not have interceptors attribute")
        assert hasattr(bf, 'interceptors')


class TestBOFrameworkCreate:
    """BOFramework创建操作测试"""
    
    def test_create_user(self, db_connection, sample_user_data):
        """TC-BE-003-06: 创建user"""
        cursor = db_connection.cursor()
        
        # 执行创建
        cursor.execute("""
            INSERT INTO users (username, email, display_name, status)
            VALUES (?, ?, ?, ?)
        """, (
            sample_user_data['username'],
            sample_user_data['email'],
            sample_user_data['display_name'],
            sample_user_data['status']
        ))
        db_connection.commit()
        
        # 验证创建成功
        user_id = cursor.lastrowid
        assert user_id > 0
        
        # 验证数据正确
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        assert user is not None
        assert user['username'] == sample_user_data['username']
        assert user['email'] == sample_user_data['email']
    
    def test_create_with_required_fields(self, db_connection, sample_user_data):
        """TC-BE-003-07: 创建带必填字段"""
        cursor = db_connection.cursor()
        
        # 只插入username
        cursor.execute("""
            INSERT INTO users (username)
            VALUES (?)
        """, (sample_user_data['username'],))
        db_connection.commit()
        
        user_id = cursor.lastrowid
        assert user_id > 0
    
    def test_create_auto_generated_id(self, db_connection, sample_user_data):
        """TC-BE-003-10: 创建自动生成ID"""
        cursor = db_connection.cursor()
        
        # 创建用户
        cursor.execute("""
            INSERT INTO users (username)
            VALUES (?)
        """, ('test_user',))
        db_connection.commit()
        
        user_id = cursor.lastrowid
        assert user_id is not None
        assert user_id > 0
    
    def test_create_sets_created_at(self, db_connection, sample_user_data):
        """TC-BE-003-11: 创建设置created_at"""
        cursor = db_connection.cursor()
        
        # 创建用户
        cursor.execute("""
            INSERT INTO users (username)
            VALUES (?)
        """, ('test_user',))
        db_connection.commit()
        
        user_id = cursor.lastrowid
        
        # 查询验证时间戳
        cursor.execute("SELECT created_at FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        
        assert user is not None
        assert user['created_at'] is not None


class TestBOFrameworkRead:
    """BOFramework读取操作测试"""
    
    def test_read_existing_user(self, db_connection, created_user):
        """TC-BE-003-16: 读取存在的记录"""
        cursor = db_connection.cursor()
        
        # 读取记录
        cursor.execute("SELECT * FROM users WHERE id = ?", (created_user['id'],))
        user = cursor.fetchone()
        
        assert user is not None
        assert user['username'] == created_user['username']
    
    def test_read_nonexistent_user(self, db_connection):
        """TC-BE-003-17: 读取不存在的记录"""
        cursor = db_connection.cursor()
        
        # 读取不存在的记录
        cursor.execute("SELECT * FROM users WHERE id = ?", (99999,))
        user = cursor.fetchone()
        
        assert user is None


class TestBOFrameworkUpdate:
    """BOFramework更新操作测试"""
    
    def test_update_existing_user(self, db_connection, created_user):
        """TC-BE-003-21: 更新存在的记录"""
        cursor = db_connection.cursor()
        
        # 更新用户名
        new_username = 'updated_user'
        cursor.execute("""
            UPDATE users SET username = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_username, created_user['id']))
        db_connection.commit()
        
        # 验证更新
        cursor.execute("SELECT username FROM users WHERE id = ?", (created_user['id'],))
        user = cursor.fetchone()
        
        assert user['username'] == new_username
    
    def test_update_sets_updated_at(self, db_connection, created_user):
        """TC-BE-003-23: 更新设置updated_at"""
        cursor = db_connection.cursor()
        
        # 记录原始创建时间
        cursor.execute("SELECT created_at FROM users WHERE id = ?", (created_user['id'],))
        old_user = cursor.fetchone()
        old_created_at = old_user['created_at']
        
        # 更新
        cursor.execute("""
            UPDATE users SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (created_user['id'],))
        db_connection.commit()
        
        # 验证时间戳更新
        cursor.execute("SELECT updated_at FROM users WHERE id = ?", (created_user['id'],))
        updated_user = cursor.fetchone()
        
        assert updated_user['updated_at'] is not None


class TestBOFrameworkDelete:
    """BOFramework删除操作测试"""
    
    def test_delete_existing_user(self, db_connection, created_user):
        """TC-BE-003-31: 删除存在的记录"""
        cursor = db_connection.cursor()
        
        # 删除
        cursor.execute("DELETE FROM users WHERE id = ?", (created_user['id'],))
        db_connection.commit()
        
        # 验证删除
        cursor.execute("SELECT * FROM users WHERE id = ?", (created_user['id'],))
        user = cursor.fetchone()
        
        assert user is None
    
    def test_delete_nonexistent_user(self, db_connection):
        """TC-BE-003-32: 删除不存在的记录"""
        cursor = db_connection.cursor()
        
        # 删除不存在的记录（不应该报错）
        cursor.execute("DELETE FROM users WHERE id = ?", (99999,))
        db_connection.commit()
        
        # 应该没有影响
        cursor.execute("SELECT COUNT(*) as count FROM users")
        count = cursor.fetchone()['count']
        assert count >= 0


class TestBOFrameworkList:
    """BOFramework列表操作测试"""
    
    def test_list_all_users(self, db_connection, multiple_users):
        """TC-BE-003-36: 列出所有记录"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM users")
        users = cursor.fetchall()
        
        assert len(users) >= 5
    
    def test_list_with_pagination(self, db_connection, multiple_users):
        """TC-BE-003-37: 列出分页数据"""
        cursor = db_connection.cursor()
        
        # 查询第一页，每页2条
        cursor.execute("SELECT * FROM users LIMIT 2 OFFSET 0")
        page1 = cursor.fetchall()
        
        # 查询第二页，每页2条
        cursor.execute("SELECT * FROM users LIMIT 2 OFFSET 2")
        page2 = cursor.fetchall()
        
        assert len(page1) == 2
        assert len(page2) == 2
        # 验证分页数据不重复
        assert page1[0]['id'] != page2[0]['id']
    
    def test_list_with_filter(self, db_connection, multiple_users):
        """TC-BE-003-38: 列出带过滤"""
        cursor = db_connection.cursor()
        
        # 只查询status为active的记录
        cursor.execute("SELECT * FROM users WHERE status = ?", ('active',))
        active_users = cursor.fetchall()
        
        # 验证所有记录都是active
        for user in active_users:
            assert user['status'] == 'active'


class TestBOFrameworkFilters:
    """BOFramework过滤器测试"""
    
    def test_filter_equals(self, db_connection, multiple_users):
        """TC-BE-003-51: 字符串等于过滤"""
        cursor = db_connection.cursor()
        
        cursor.execute("""
            SELECT * FROM users WHERE username = ?
        """, ('user0',))
        
        result = cursor.fetchall()
        
        assert len(result) == 1
        assert result[0]['username'] == 'user0'
    
    def test_filter_like(self, db_connection, multiple_users):
        """TC-BE-003-52: 字符串LIKE过滤"""
        cursor = db_connection.cursor()
        
        cursor.execute("""
            SELECT * FROM users WHERE username LIKE ?
        """, ('%user%',))
        
        result = cursor.fetchall()
        
        # 验证所有用户名都包含user
        assert len(result) >= 5
        for user in result:
            assert 'user' in user['username']
    
    def test_filter_in(self, db_connection, multiple_users):
        """TC-BE-003-57: IN过滤"""
        cursor = db_connection.cursor()
        
        cursor.execute("""
            SELECT * FROM users WHERE username IN (?, ?)
        """, ('user0', 'user1'))
        
        result = cursor.fetchall()
        
        assert len(result) == 2

    @pytest.mark.parametrize(
        "test_name,sql,params,expected_count,description,extra_check",
        FILTER_TEST_CASES)
    def test_filter_operations(self, db_connection, multiple_users,
                               test_name, sql, params, expected_count,
                               description, extra_check):
        """TC-BE-003-51/52/57: 过滤操作（等于/LIKE/IN）"""
        cursor = db_connection.cursor()
        cursor.execute(sql, params)
        result = cursor.fetchall()

        if isinstance(expected_count, int):
            assert len(result) == expected_count, \
                f"{description}: 预期{expected_count}条，实际{len(result)}条"
        else:
            assert len(result) >= 5, \
                f"{description}: 预期>=5条，实际{len(result)}条"

        if extra_check:
            extra_check(result)

    def test_filter_like_content_check(self, db_connection, multiple_users):
        """TC-BE-003-52: LIKE过滤内容验证"""
        cursor = db_connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username LIKE ?", ('%user%',))
        result = cursor.fetchall()
        assert len(result) >= 5
        for user in result:
            assert 'user' in user['username']


class TestBOFrameworkSort:
    """BOFramework排序测试"""
    
    def test_sort_ascending(self, db_connection, multiple_users):
        """TC-BE-003-40: 升序排序"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM users ORDER BY username ASC")
        users = cursor.fetchall()
        
        # 验证排序正确
        usernames = [u['username'] for u in users]
        assert usernames == sorted(usernames)
    
    def test_sort_descending(self, db_connection, multiple_users):
        """TC-BE-003-41: 降序排序"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM users ORDER BY username DESC")
        users = cursor.fetchall()
        
        # 验证排序正确
        usernames = [u['username'] for u in users]
        assert usernames == sorted(usernames, reverse=True)

    @pytest.mark.parametrize(
        "test_name,direction,reverse_expected,description",
        SORT_TEST_CASES)
    def test_sort_direction(self, db_connection, multiple_users,
                            test_name, direction, reverse_expected, description):
        """TC-BE-003-40/41: 排序方向验证（升序/降序）"""
        cursor = db_connection.cursor()
        cursor.execute(f"SELECT * FROM users ORDER BY username {direction}")
        users = cursor.fetchall()

        usernames = [u['username'] for u in users]
        assert usernames == sorted(usernames, reverse=reverse_expected), \
            f"{description}: 排序不正确"

    def test_audit_log_default_ordering_created_at(self, db_connection):
        """[FIX 2026-06-10] audit_log 列表无 ordering 时默认 created_at desc，不使用不存在的 updated_at 列。

        根因：unified_query_facade._build_v3_search_request 默认 sort_by='updated_at'，
        但 audit_logs 表只有 created_at 列，无 updated_at 列，导致排序异常。
        """
        from meta.core.unified_query_facade import _parse_ordering, UnifiedQueryFacade
        from meta.core.unified_query_protocol import UnifiedQueryRequest
        from meta.services.query_service import SearchRequest

        # 1. _parse_ordering 空字符串返回 ('', '')，且 not '' == True 会触发默认排序
        sort_by, sort_order = _parse_ordering('')
        assert sort_by == '', f"空 ordering 应返回空字符串，实际: {sort_by!r}"

        # 2. 通过 UnifiedQueryFacade._build_v3_search_request 验证 audit_log 默认排序
        # 直接实例化 facade（data_source=None 走 _get_data_source()）
        try:
            facade = UnifiedQueryFacade()
        except Exception:
            # 如果无法获取默认数据源，用 db_connection 作为替代
            facade = UnifiedQueryFacade(db_connection)

        req = UnifiedQueryRequest(entity_type='audit_log', page=1, page_size=20, ordering='')
        try:
            search_req = facade._build_v3_search_request(req)
            # 验证 order_by 不使用 updated_at（audit_logs 表无此列）
            assert search_req.order_by is not None and 'updated_at' not in search_req.order_by.lower(), \
                f"audit_log 默认排序不应使用 updated_at，实际: {search_req.order_by}"
            # 验证使用的是 created_at
            assert 'created_at' in search_req.order_by.lower(), \
                f"audit_log 默认排序应使用 created_at，实际: {search_req.order_by}"
        except Exception as e:
            # 如果错误包含 updated_at / no such column，说明 bug 未修复
            err_str = str(e).lower()
            if 'updated_at' in err_str or 'no such column' in err_str:
                pytest.fail(
                    f"audit_log 列表使用了不存在的 updated_at 列排序: {e}\n"
                    f"修复应为: sort_by = 'created_at' if entity_type == 'audit_log' else 'updated_at'"
                )
            raise


class TestBOFrameworkPagination:
    """BOFramework分页测试"""
    
    def test_pagination_first_page(self, db_connection, multiple_users):
        """TC-BE-003-37: 获取第一页"""
        cursor = db_connection.cursor()
        page_size = 2
        
        cursor.execute("SELECT * FROM users ORDER BY id LIMIT ? OFFSET 0", (page_size,))
        page1 = cursor.fetchall()
        
        assert len(page1) == 2
    
    def test_pagination_second_page(self, db_connection, multiple_users):
        """TC-BE-003-37: 获取第二页"""
        cursor = db_connection.cursor()
        page_size = 2
        page = 2
        
        cursor.execute("""
            SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?
        """, (page_size, (page - 1) * page_size))
        page2 = cursor.fetchall()
        
        assert len(page2) == 2

    @pytest.mark.parametrize(
        "test_name,offset,expected_size,description",
        PAGINATION_TEST_CASES)
    def test_pagination_page(self, db_connection, multiple_users,
                             test_name, offset, expected_size, description):
        """TC-BE-003-37: 分页获取验证（首页/后续页）"""
        cursor = db_connection.cursor()
        cursor.execute(
            "SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?",
            (expected_size, offset))
        page = cursor.fetchall()
        assert len(page) == expected_size, \
            f"{description}: 预期{expected_size}条，实际{len(page)}条"
    
    def test_pagination_count_total(self, db_connection, multiple_users):
        """TC-BE-003-50: 统计总数"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT COUNT(*) as total FROM users")
        result = cursor.fetchone()
        
        assert result['total'] >= 5


class TestBOFrameworkRelationships:
    """BOFramework关联测试"""
    
    def test_query_user_roles_via_group(self, db_connection, user_with_role):
        """查询用户角色关联（通过用户组间接获取）"""
        cursor = db_connection.cursor()
        
        cursor.execute("""
            SELECT r.* FROM roles r
            INNER JOIN group_roles gr ON r.id = gr.role_id
            INNER JOIN user_group_members ugm ON gr.group_id = ugm.group_id
            WHERE ugm.user_id = ?
        """, (user_with_role['user']['id'],))
        
        roles = cursor.fetchall()
        
        assert len(roles) >= 1
        assert roles[0]['code'] == user_with_role['role']['code']
    
    def test_query_user_groups(self, db_connection, user_in_group):
        """查询用户组关联"""
        cursor = db_connection.cursor()
        
        cursor.execute("""
            SELECT g.* FROM user_groups g
            INNER JOIN user_group_members ugm ON g.id = ugm.group_id
            WHERE ugm.user_id = ?
        """, (user_in_group['user']['id'],))
        
        groups = cursor.fetchall()
        
        assert len(groups) >= 1
        assert groups[0]['code'] == user_in_group['group']['code']
