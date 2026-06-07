# API开发指南

## 后端API结构

```
meta/api/
├── agent_api.py        # Agent API（预留）
├── auth_api.py         # 认证API
├── database_api.py     # 数据库API
├── enum_api.py         # 枚举API
├── manage_api.py       # 管理API
├── meta_api.py         # 元模型API
├── notification_api.py # 通知API
├── query_api.py        # 查询API
├── role_api.py         # 角色API
├── schema_api.py       # Schema API
├── stats_api.py        # 统计API
├── user_api.py         # 用户API
└── user_group_api.py   # 用户组API
```

## API规范

- 路由前缀：/api/v1/
- 响应格式：{ success: bool, data: any, error?: string }
- 分页参数：page, page_size
- 搜索参数：keyword

## Agent API

已预留Agent API（meta/api/agent_api.py），支持：
- 获取所有Tool Schema
- 获取对象上下文
- 获取完整元数据Schema
