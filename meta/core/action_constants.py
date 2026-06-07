"""
标准 Action 名称常量

用于替代代码中的魔法字符串 'crud_create'、'associate' 等。
全项目 100+ 处引用，渐进式替换。
"""

CRUD_CREATE = "crud_create"
CRUD_READ = "crud_read"
CRUD_UPDATE = "crud_update"
CRUD_DELETE = "crud_delete"
CRUD_LIST = "crud_list"

ASSOCIATE = "associate"
DISSOCIATE = "dissociate"
ASSIGN = "assign"
UNASSIGN = "unassign"

CRUD_ACTIONS = frozenset({CRUD_CREATE, CRUD_READ, CRUD_UPDATE, CRUD_DELETE, CRUD_LIST})
ASSOCIATION_ACTIONS = frozenset({ASSOCIATE, DISSOCIATE, ASSIGN, UNASSIGN})
WRITE_ACTIONS = frozenset({CRUD_CREATE, CRUD_UPDATE, CRUD_DELETE, ASSOCIATE,
                           DISSOCIATE, ASSIGN, UNASSIGN})
