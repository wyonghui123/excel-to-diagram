import sys, os, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')
os.environ['AUTH_ENABLED'] = 'true'

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

from meta.core.interceptors.data_permission_interceptor import DataPermissionInterceptor
from meta.core.action_context import ActionContext
from meta.core.models import registry

# Simulate what the interceptor does for TEST888 querying 'product'
interceptor = DataPermissionInterceptor()

# Create a mock context
meta_object = registry.get('product')
context = ActionContext(
    meta_object=meta_object,
    action='crud_query',
    params={'page_size': 20},
    data_source=ds,
    user_id=3371,  # TEST888's user_id
    user_name='TEST888',
)

print(f'context.user_id = {context.user_id}')
print(f'context.is_query_action = {context.is_query_action}')
print(f'context.object_type = {context.object_type}')

# Check if admin
is_admin = interceptor._is_admin(context)
print(f'is_admin = {is_admin}')

# Try applying dimension scope filter
result = interceptor._apply_dimension_scope_filter(context)
print(f'_apply_dimension_scope_filter returned: {result}')
print(f'query_conditions = {context.extra.get("query_conditions", [])}')

# Also check: what role_ids does the interceptor find?
cursor = ds.execute("""
    SELECT DISTINCT gr.role_id
    FROM group_roles gr
    JOIN user_group_members ugm ON gr.group_id = ugm.group_id
    WHERE ugm.user_id = ?
""", [3371])
role_ids = [row[0] for row in cursor.fetchall()]
print(f'role_ids for user_id=3371: {role_ids}')

# Check role_dimension_scopes for those role_ids
if role_ids:
    placeholders = ','.join('?' * len(role_ids))
    cursor = ds.execute(
        f"SELECT COUNT(*) FROM role_dimension_scopes WHERE role_id IN ({placeholders})",
        role_ids
    )
    count = cursor.fetchone()[0]
    print(f'role_dimension_scopes count: {count}')
