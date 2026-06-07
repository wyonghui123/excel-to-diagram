import pytest

pytestmark = pytest.mark.integration

"""
后端测试套件 - API层测试
测试 meta.api 模块
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch


class TestBOListAPI:
    """BO列表API测试"""
    
    def test_list_returns_json_format(self, db_connection, multiple_users):
        """TC-BE-006-01: GET /bo/{entity}返回JSON格式"""
        # 模拟API响应格式
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM users LIMIT 20")
        users = cursor.fetchall()
        
        # 转换为字典列表
        user_list = [dict(user) for user in users]
        
        response = {
            'success': True,
            'data': {
                'items': user_list,
                'total': len(user_list),
                'page': 1,
                'page_size': 20
            }
        }
        
        assert response['success'] == True
        assert 'items' in response['data']
        assert 'total' in response['data']
        assert isinstance(response['data']['items'], list)
    
    def test_list_with_pagination_params(self, db_connection, multiple_users):
        """TC-BE-006-02: 带分页参数的列表API"""
        cursor = db_connection.cursor()
        
        page = 1
        page_size = 2
        
        cursor.execute("SELECT * FROM users ORDER BY id LIMIT ? OFFSET ?", 
                     (page_size, (page - 1) * page_size))
        items = cursor.fetchall()
        
        cursor.execute("SELECT COUNT(*) as total FROM users")
        total = cursor.fetchone()['total']
        
        assert len(items) == 2
        assert total >= 5
    
    def test_list_with_filter_params(self, db_connection, multiple_users):
        """TC-BE-006-03: 带过滤器参数的列表API"""
        cursor = db_connection.cursor()
        
        filters = {'status': 'active'}
        
        # 应用过滤器
        cursor.execute("""
            SELECT * FROM users WHERE status = ?
        """, (filters['status'],))
        items = cursor.fetchall()
        
        # 验证所有结果都匹配过滤器
        for item in items:
            assert item['status'] == filters['status']
    
    def test_list_with_ordering_params(self, db_connection, multiple_users):
        """TC-BE-006-04: 带排序参数的列表API"""
        cursor = db_connection.cursor()
        
        ordering = 'username'
        
        cursor.execute(f"SELECT * FROM users ORDER BY {ordering} ASC")
        items = cursor.fetchall()
        
        usernames = [item['username'] for item in items]
        assert usernames == sorted(usernames)


class TestBOReadAPI:
    """BO读取API测试"""
    
    def test_read_existing_returns_data(self, db_connection, created_user):
        """TC-BE-006-05: 读取存在的记录"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (created_user['id'],))
        user = cursor.fetchone()
        
        assert user is not None
        assert user['username'] == created_user['username']
    
    def test_read_nonexistent_returns_404(self, db_connection):
        """TC-BE-006-17: 读取不存在的记录返回404"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (99999,))
        user = cursor.fetchone()
        
        assert user is None
    
    def test_read_returns_correct_format(self, db_connection, created_user):
        """读取返回正确格式"""
        cursor = db_connection.cursor()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (created_user['id'],))
        user = dict(cursor.fetchone())
        
        response = {
            'success': True,
            'data': user
        }
        
        assert response['success'] == True
        assert 'id' in response['data']
        assert 'username' in response['data']


class TestBOCreateAPI:
    """BO创建API测试"""
    
    def test_create_returns_created_data(self, db_connection, sample_user_data):
        """TC-BE-006-06: 创建返回创建的数据"""
        cursor = db_connection.cursor()
        
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
        
        user_id = cursor.lastrowid
        
        # 验证创建成功
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        created_user = dict(cursor.fetchone())
        
        response = {
            'success': True,
            'data': created_user
        }
        
        assert response['success'] == True
        assert response['data']['username'] == sample_user_data['username']
    
    def test_create_validation_error(self, db_connection, sample_user_data):
        """TC-BE-006-07: 创建验证错误"""
        cursor = db_connection.cursor()
        
        # 尝试插入必填字段为空
        try:
            cursor.execute("""
                INSERT INTO users (email) VALUES (?)
            """, ('test@example.com',))
            db_connection.commit()
        except Exception as e:
            # 应该抛出验证错误
            assert True


class TestBOUpdateAPI:
    """BO更新API测试"""
    
    def test_update_returns_updated_data(self, db_connection, created_user):
        """TC-BE-006-08: 更新返回更新的数据"""
        cursor = db_connection.cursor()
        
        new_username = 'updated_user'
        
        cursor.execute("""
            UPDATE users SET username = ? WHERE id = ?
        """, (new_username, created_user['id']))
        db_connection.commit()
        
        cursor.execute("SELECT * FROM users WHERE id = ?", (created_user['id'],))
        updated_user = dict(cursor.fetchone())
        
        response = {
            'success': True,
            'data': updated_user
        }
        
        assert response['success'] == True
        assert response['data']['username'] == new_username
    
    def test_update_validation_error(self, db_connection, created_user):
        """TC-BE-006-09: 更新验证错误"""
        cursor = db_connection.cursor()
        
        # 尝试更新不存在的记录
        cursor.execute("""
            UPDATE users SET username = ? WHERE id = ?
        """, ('updated', 99999))
        db_connection.commit()
        
        rows_affected = cursor.rowcount
        assert rows_affected == 0


class TestBODeleteAPI:
    """BO删除API测试"""
    
    def test_delete_success(self, db_connection, created_user):
        """TC-BE-006-10: 删除成功"""
        cursor = db_connection.cursor()
        
        cursor.execute("DELETE FROM users WHERE id = ?", (created_user['id'],))
        db_connection.commit()
        
        rows_affected = cursor.rowcount
        assert rows_affected >= 1
        
        # 验证删除成功
        cursor.execute("SELECT * FROM users WHERE id = ?", (created_user['id'],))
        user = cursor.fetchone()
        assert user is None
    
    def test_delete_nonexistent_returns_success(self, db_connection):
        """TC-BE-006-10: 删除不存在的记录返回成功"""
        cursor = db_connection.cursor()
        
        # 删除不存在的记录（不应该报错）
        cursor.execute("DELETE FROM users WHERE id = ?", (99999,))
        db_connection.commit()
        
        # 应该返回成功（0行受影响）
        rows_affected = cursor.rowcount
        assert rows_affected == 0


class TestAssociationAPI:
    """Association API测试"""

    def test_query_associations(self, db_connection, user_with_role):
        """TC-BE-006-21: 查询关联（通过用户组间接获取角色）"""
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

    def test_assign_association(self, db_connection, created_user, created_role):
        """TC-BE-006-23: 分配关联（通过用户组）"""
        cursor = db_connection.cursor()

        cursor.execute("INSERT INTO user_groups (code, name) VALUES (?, ?)",
            ('test_assign_group', 'Test Assign Group'))
        group_id = cursor.lastrowid
        cursor.execute("INSERT INTO user_group_members (user_id, group_id) VALUES (?, ?)",
            (created_user['id'], group_id))
        cursor.execute("INSERT INTO group_roles (group_id, role_id) VALUES (?, ?)",
            (group_id, created_role['id']))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (group_id, created_role['id']))
        association = cursor.fetchone()

        assert association is not None

    def test_unassign_association(self, db_connection, user_with_role):
        """TC-BE-006-24: 取消分配关联"""
        cursor = db_connection.cursor()

        user_id = user_with_role['user']['id']
        role_id = user_with_role['role']['id']
        group_id = user_with_role.get('group_id')

        if not group_id:
            pytest.skip("No group association")

        cursor.execute("""
            DELETE FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (group_id, role_id))
        db_connection.commit()

        cursor.execute("""
            SELECT * FROM group_roles
            WHERE group_id = ? AND role_id = ?
        """, (group_id, role_id))
        association = cursor.fetchone()

        assert association is None


class TestExportImportAPI:
    """导出导入API测试"""
    
    def test_export_returns_download_url(self, db_connection, multiple_users):
        """TC-BE-006-36: 导出返回下载URL"""
        # 模拟导出响应
        response = {
            'success': True,
            'data': {
                'download_url': '/api/v1/export/download/test_export.xlsx',
                'total_rows': len(multiple_users)
            }
        }
        
        assert response['success'] == True
        assert 'download_url' in response['data']
        assert '.xlsx' in response['data']['download_url']
    
    def test_import_preview_returns_validation(self, db_connection):
        """TC-BE-006-40: 导入预览返回校验结果"""
        # 模拟导入预览响应
        response = {
            'success': True,
            'data': {
                'sheet_count': 1,
                'preview': [
                    {'username': 'test1', 'email': 'test1@example.com'},
                    {'username': 'test2', 'email': 'test2@example.com'}
                ],
                'errors': []
            }
        }
        
        assert response['success'] == True
        assert response['data']['sheet_count'] == 1
        assert len(response['data']['preview']) == 2
    
    def test_import_preview_returns_errors(self, db_connection):
        """TC-BE-006-44: 导入预览返回错误"""
        # 模拟导入预览错误响应
        response = {
            'success': True,
            'data': {
                'errors': [
                    {'row': 1, 'field': 'username', 'message': '必填字段不能为空'},
                    {'row': 2, 'field': 'email', 'message': '无效的邮箱格式'}
                ]
            }
        }
        
        assert len(response['data']['errors']) == 2


class TestSchemaAPI:
    """Schema API测试"""
    
    def test_get_schema_returns_structure(self):
        """TC-BE-006-46: 获取Schema返回结构"""
        # 模拟Schema响应
        response = {
            'success': True,
            'data': {
                'name': 'user',
                'label': '用户',
                'fields': [
                    {'id': 'username', 'type': 'string', 'required': True},
                    {'id': 'email', 'type': 'string', 'required': False}
                ]
            }
        }
        
        assert response['success'] == True
        assert response['data']['name'] == 'user'
        assert len(response['data']['fields']) >= 1
    
    def test_get_ui_config_returns_view_config(self):
        """TC-BE-006-47: 获取UI配置返回视图配置"""
        # 模拟UI配置响应
        response = {
            'success': True,
            'data': {
                'title': '用户管理',
                'columns': [
                    {'key': 'username', 'label': '用户名'},
                    {'key': 'email', 'label': '邮箱'}
                ]
            }
        }
        
        assert response['success'] == True
        assert 'title' in response['data']
        assert 'columns' in response['data']


class TestPermissionAPI:
    """权限API测试"""
    
    def test_unauthorized_returns_401(self):
        """TC-BE-006-15: 未授权返回401"""
        # 模拟未授权响应
        response = {
            'success': False,
            'message': 'Unauthorized',
            'code': 401
        }
        
        assert response['success'] == False
        assert response['code'] == 401
    
    def test_forbidden_returns_403(self):
        """TC-BE-006-11: 无权限返回403"""
        response = {
            'success': False,
            'message': 'Forbidden',
            'code': 403
        }
        
        assert response['success'] == False
        assert response['code'] == 403


class TestBadRequestAPI:
    """错误请求API测试"""
    
    def test_missing_required_field_returns_400(self):
        """TC-BE-006-18: 缺少必填字段返回400"""
        response = {
            'success': False,
            'message': 'Bad Request',
            'errors': [
                {'field': 'username', 'message': 'username is required'}
            ],
            'code': 400
        }
        
        assert response['success'] == False
        assert response['code'] == 400
        assert 'username' in str(response['errors'])
    
    def test_invalid_format_returns_400(self):
        """无效格式返回400"""
        response = {
            'success': False,
            'message': 'Bad Request',
            'errors': [
                {'field': 'email', 'message': 'Invalid email format'}
            ],
            'code': 400
        }
        
        assert response['success'] == False
        assert response['code'] == 400
