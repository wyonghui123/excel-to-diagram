import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

# Check TEST888 user
cursor = ds.execute("SELECT id, username FROM users WHERE username = 'TEST888'", [])
user = cursor.fetchone()
print(f'User: {user}')

user_id = user[0] if user else None
if user_id:
    # Check user_group_members
    cursor = ds.execute("SELECT * FROM user_group_members WHERE user_id = ?", [user_id])
    cols = [d[0] for d in cursor.description]
    members = [dict(zip(cols, row)) for row in cursor.fetchall()]
    print(f'\nuser_group_members for user_id={user_id}:')
    for m in members:
        print(f'  {m}')

    # Check group_roles
    if members:
        group_ids = [m['group_id'] for m in members]
        placeholders = ','.join('?' * len(group_ids))
        cursor = ds.execute(f"SELECT * FROM group_roles WHERE group_id IN ({placeholders})", group_ids)
        cols = [d[0] for d in cursor.description]
        group_roles = [dict(zip(cols, row)) for row in cursor.fetchall()]
        print(f'\ngroup_roles:')
        for gr in group_roles:
            print(f'  {gr}')

        # Check roles
        if group_roles:
            role_ids = [gr['role_id'] for gr in group_roles]
            placeholders = ','.join('?' * len(role_ids))
            cursor = ds.execute(f"SELECT * FROM roles WHERE id IN ({placeholders})", role_ids)
            cols = [d[0] for d in cursor.description]
            roles = [dict(zip(cols, row)) for row in cursor.fetchall()]
            print(f'\nroles:')
            for r in roles:
                print(f'  {r}')

            # Check role_dimension_scopes
            cursor = ds.execute(f"SELECT * FROM role_dimension_scopes WHERE role_id IN ({placeholders})", role_ids)
            cols = [d[0] for d in cursor.description]
            scopes = [dict(zip(cols, row)) for row in cursor.fetchall()]
            print(f'\nrole_dimension_scopes:')
            for s in scopes:
                print(f'  {s}')
    else:
        print('\nNo group memberships found!')

    # Also check: what does the interceptor's query return?
    cursor = ds.execute("""
        SELECT DISTINCT gr.role_id
        FROM group_roles gr
        JOIN user_group_members ugm ON gr.group_id = ugm.group_id
        WHERE ugm.user_id = ?
    """, [user_id])
    role_ids = [row[0] for row in cursor.fetchall()]
    print(f'\nInterceptor query role_ids: {role_ids}')
