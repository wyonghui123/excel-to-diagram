-- 自动生成的 Schema
-- 生成时间: 2026-05-26 09:21:34.327380

-- AI异步任务: AI Agent异步执行的长期任务队列，支持优先级调度和成本追踪
CREATE TABLE IF NOT EXISTS ai_async_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type VARCHAR(200) NOT NULL,
    session_id VARCHAR(200),
    agent_id VARCHAR(200),
    parent_task_id INTEGER,
    request TEXT NOT NULL,
    context TEXT,
    priority INTEGER DEFAULT 50,
    queue VARCHAR(200) DEFAULT 'ai_normal',
    status VARCHAR(200) DEFAULT 'pending',
    worker_id VARCHAR(200),
    started_at DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER,
    result TEXT,
    error_message TEXT,
    tokens_used INTEGER,
    cost VARCHAR(200),
    model_used VARCHAR(200),
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    timeout INTEGER DEFAULT 300,
    tenant_id INTEGER,
    user_id INTEGER,
    created_at DATETIME,
    updated_at DATETIME
)

-- 备注信息: 为架构对象添加的业务备注信息，支持一个对象关联多条备注。
CREATE TABLE IF NOT EXISTS annotations (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_type VARCHAR(200) NOT NULL,
    target_id INTEGER NOT NULL,
    category VARCHAR(200) NOT NULL,
    content TEXT
)

-- 审计日志: 审计日志记录所有业务对象的变更历史，包括创建、更新、删除操作
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    log_category VARCHAR(200) NOT NULL DEFAULT 'business',
    log_level VARCHAR(200) NOT NULL DEFAULT 'INFO',
    object_type VARCHAR(200) NOT NULL,
    object_id INTEGER NOT NULL,
    parent_object_type VARCHAR(200),
    parent_object_id INTEGER,
    action VARCHAR(200) NOT NULL,
    field_name VARCHAR(200),
    old_value TEXT,
    new_value TEXT,
    user_id INTEGER,
    user_name VARCHAR(200),
    ip_address VARCHAR(200),
    user_agent VARCHAR(200),
    created_at DATETIME NOT NULL DEFAULT 'NOW()',
    extra_data TEXT,
    trace_id VARCHAR(200),
    transaction_id VARCHAR(200),
    status VARCHAR(200) DEFAULT 'written',
    status_entered_at DATETIME,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    agent_id VARCHAR(200),
    agent_session_id VARCHAR(200),
    tool_call_id VARCHAR(200),
    agent_reasoning TEXT
)

-- 变更事件: 变更事件记录所有业务对象的变更事件，支持事件驱动架构和通知分发
CREATE TABLE IF NOT EXISTS change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type VARCHAR(200) NOT NULL,
    object_id INTEGER NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    changed_fields TEXT,
    old_values TEXT,
    new_values TEXT,
    payload TEXT,
    channels TEXT,
    status VARCHAR(200) NOT NULL DEFAULT 'pending',
    status_entered_at DATETIME,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT 'NOW()',
    delivered_at DATETIME,
    audit_log_id INTEGER
)

-- 变更订阅: 变更订阅配置，支持用户订阅特定对象类型的变更事件
CREATE TABLE IF NOT EXISTS change_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    object_type VARCHAR(200) NOT NULL,
    event_types TEXT,
    channel VARCHAR(200) NOT NULL DEFAULT 'in_app',
    filter_condition TEXT,
    webhook_url VARCHAR(200),
    webhook_secret VARCHAR(200),
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT 'NOW()'
)

-- 数据权限: 控制用户对特定资源实例的访问权限
CREATE TABLE IF NOT EXISTS data_permissions (
    user_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    resource_id INTEGER NOT NULL,
    permission_level VARCHAR(200) NOT NULL,
    inherit_to_children INTEGER DEFAULT 1,
    created_at VARCHAR(200)
)

-- 员工数据权限范围: 员工数据权限范围模板，支持本人/部门/层级三种范围
CREATE TABLE IF NOT EXISTS employee_data_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    condition_template VARCHAR(200) NOT NULL,
    description VARCHAR(200)
)

-- 枚举类型: 枚举类型定义，支持系统枚举和业务枚举的分层管理，支持多维枚举值。
-- 注意：updated_at 不在此表（由 audit_aspect 通过 audit_logs 实时计算，见 aspects.yaml）
CREATE TABLE IF NOT EXISTS enum_types (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id VARCHAR(200) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category VARCHAR(200) NOT NULL,
    mutability VARCHAR(200) NOT NULL,
    dimension_schema TEXT,
    description TEXT,
    created_at DATETIME
)

-- 枚举值: 枚举类型的具体值项，支持多维枚举值和层级枚举。
-- 注意：updated_at 不在此表（由 audit_aspect 通过 audit_logs 实时计算）
CREATE TABLE IF NOT EXISTS enum_values (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    enum_type_id VARCHAR(200) NOT NULL,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_en VARCHAR(200),
    dimensions TEXT,
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0,
    parent_code VARCHAR(200),
    metadata TEXT,
    created_at DATETIME,
    FOREIGN KEY (enum_type_id) REFERENCES enum_types(id)
)

-- 过滤变体: 用户保存的过滤条件组合，支持个人和共享变体
CREATE TABLE IF NOT EXISTS filter_variants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    object_type VARCHAR(200) NOT NULL,
    filters TEXT NOT NULL,
    user_id INTEGER,
    is_shared INTEGER DEFAULT 0,
    is_default INTEGER DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
)

-- 用户组数据权限: 用户组的数据访问权限
CREATE TABLE IF NOT EXISTS group_data_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    resource_id INTEGER NOT NULL,
    permission_level VARCHAR(200) NOT NULL,
    inherit_to_children INTEGER DEFAULT 1,
    created_at DATETIME
)

-- 菜单: 系统菜单配置，由BO元数据驱动。
菜单 = 通用页面组件 × 对象(s) + config

设计原则：
1. 菜单与BO通过 bo_bindings 声明关联
2. required_permissions 从 bo_bindings 自动推导
3. 支持 SAP PFCG 风格的菜单-权限联动

CREATE TABLE IF NOT EXISTS menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_code VARCHAR(200) UNIQUE NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200),
    page_type VARCHAR(200) NOT NULL DEFAULT 'object_list',
    object_types TEXT,
    primary_object_type VARCHAR(200),
    bo_bindings TEXT,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    data_permission_hint TEXT,
    page_config TEXT,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    color VARCHAR(200),
    description VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    show_in_sidebar INTEGER DEFAULT 1,
    auto_generated INTEGER DEFAULT 0
)

-- 菜单权限: 菜单访问权限配置，控制用户可见的菜单项
CREATE TABLE IF NOT EXISTS menu_permissions (
    menu_code VARCHAR(200) UNIQUE NOT NULL,
    menu_name VARCHAR(200) NOT NULL,
    menu_path VARCHAR(200) NOT NULL,
    required_permissions TEXT,
    required_any_permission INTEGER DEFAULT 0,
    parent_menu VARCHAR(200),
    icon VARCHAR(200),
    sort_order INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    data_permission_hint TEXT,
    created_at VARCHAR(200),
    updated_at VARCHAR(200)
)



-- 功能权限: 系统功能权限定义，控制用户对资源的操作能力
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    resource_type VARCHAR(200),
    action VARCHAR(200),
    description TEXT,
    resource_id INTEGER,
    scope VARCHAR(200) DEFAULT 'all'
)

-- 权限包: 预定义的权限组合包，支持一键分配功能权限+数据权限+菜单权限
CREATE TABLE IF NOT EXISTS permission_bundles (
    bundle_code VARCHAR(200) UNIQUE NOT NULL,
    bundle_name VARCHAR(200) NOT NULL,
    description TEXT,
    menu_permissions TEXT,
    function_permissions TEXT,
    data_permission_template TEXT,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0,
    created_at VARCHAR(200),
    updated_at VARCHAR(200)
)

-- 条件权限规则: 基于条件的动态权限规则，支持维度过滤和条件匹配
CREATE TABLE IF NOT EXISTS permission_rules (
    role_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    condition TEXT NOT NULL,
    permission_level VARCHAR(200) NOT NULL DEFAULT 'read',
    is_denied INTEGER DEFAULT 0,
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 1,
    analysis_mode VARCHAR(200),
    created_at VARCHAR(200),
    created_by INTEGER,
    updated_at VARCHAR(200)
)

-- 角色: 系统角色，用于基于角色的权限控制
CREATE TABLE IF NOT EXISTS roles (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0,
    is_super_admin INTEGER DEFAULT 0,
    priority INTEGER DEFAULT 0,
    created_at DATETIME,
    menu_count INTEGER,
    permission_count INTEGER,
    data_perm_count INTEGER
)

-- 角色数据权限: 角色级别的数据访问权限配置，控制角色可访问的资源实例范围
CREATE TABLE IF NOT EXISTS role_data_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    resource_id INTEGER NOT NULL,
    permission_level VARCHAR(200) DEFAULT 'read',
    inherit_to_children INTEGER DEFAULT 1,
    created_at VARCHAR(200),
    created_by INTEGER
)

-- 角色维度范围: 角色的管理维度范围声明，是权限推导的入口。
CREATE TABLE IF NOT EXISTS role_dimension_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    dimension_code VARCHAR(200) NOT NULL,
    dimension_values TEXT NOT NULL,
    inherit_children INTEGER DEFAULT 1,
    scope_mode VARCHAR(200) DEFAULT 'include'
)

-- 角色权限: 角色与权限的多对多关联
CREATE TABLE IF NOT EXISTS role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    created_at DATETIME
)

-- 任务定义: 后台调度任务定义，支持Cron定时、事件驱动、Webhook、手动等多种触发模式
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description VARCHAR(200),
    category VARCHAR(200) NOT NULL DEFAULT 'business',
    handler VARCHAR(200) NOT NULL,
    handler_config TEXT,
    trigger_mode VARCHAR(200) NOT NULL DEFAULT 'cron',
    schedule VARCHAR(200),
    trigger_config TEXT,
    queue VARCHAR(200) DEFAULT 'business',
    priority INTEGER DEFAULT 50,
    timeout INTEGER DEFAULT 300,
    max_retries INTEGER DEFAULT 3,
    retry_delay INTEGER DEFAULT 60,
    retry_backoff VARCHAR(200) DEFAULT 'linear',
    tenant_scope INTEGER DEFAULT 0,
    enabled INTEGER DEFAULT 1,
    last_run_at DATETIME,
    next_run_at DATETIME,
    ai_config TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 任务执行记录: 记录每次任务执行的详细信息，包括状态、耗时、结果等
CREATE TABLE IF NOT EXISTS task_executions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    task_id INTEGER,
    task_type VARCHAR(200) NOT NULL,
    handler VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'pending',
    attempt INTEGER DEFAULT 1,
    trigger_type VARCHAR(200),
    trigger_source VARCHAR(200),
    queue VARCHAR(200) DEFAULT 'business',
    priority INTEGER DEFAULT 50,
    params TEXT,
    result TEXT,
    error_message TEXT,
    error_traceback TEXT,
    timeout INTEGER DEFAULT 300,
    max_retries INTEGER DEFAULT 3,
    retry_count INTEGER DEFAULT 0,
    worker_id VARCHAR(200),
    queued_at DATETIME,
    started_at DATETIME,
    completed_at DATETIME,
    duration_ms INTEGER,
    tokens_used INTEGER,
    cost VARCHAR(200),
    model_used VARCHAR(200),
    ai_session_id VARCHAR(200),
    agent_id VARCHAR(200),
    ai_context TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 任务队列配置: 管理任务调度队列，每个队列有独立的线程池和优先级
CREATE TABLE IF NOT EXISTS task_queues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) UNIQUE NOT NULL,
    description VARCHAR(200),
    priority INTEGER NOT NULL DEFAULT 50,
    max_workers INTEGER DEFAULT 5,
    timeout INTEGER DEFAULT 300,
    enabled INTEGER DEFAULT 1,
    current_workers INTEGER DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME
)

-- 用户: 系统用户，支持本地认证和SSO集成
CREATE TABLE IF NOT EXISTS users (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(200) UNIQUE NOT NULL,
    email VARCHAR(200),
    password_hash VARCHAR(200),
    display_name VARCHAR(200),
    status VARCHAR(200) DEFAULT 'active',
    -- [REMOVED 2026-06-09] status_entered_at DATETIME 已删除
    -- 单一事实源改为 audit_logs (current_status_duration_days 公式从 audit_logs 派生)
    sso_provider VARCHAR(200),
    sso_user_id VARCHAR(200),
    must_change_password INTEGER DEFAULT 0,
    password_history VARCHAR(200) DEFAULT '[]',
    last_login_at DATETIME,
    created_at DATETIME,
    locale VARCHAR(200) DEFAULT 'zh-CN',
    timezone VARCHAR(200) DEFAULT 'Asia/Shanghai',
    date_style VARCHAR(200) DEFAULT 'medium',
    time_style VARCHAR(200) DEFAULT 'short',
    hour_cycle INTEGER DEFAULT 24
)

-- 用户组: 用户组，用于组织用户和实现委托管理
CREATE TABLE IF NOT EXISTS user_groups (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(200) UNIQUE NOT NULL,
    parent_id INTEGER,
    manager_id INTEGER,
    description VARCHAR(200),
    created_at DATETIME
)

-- 用户组成员: 用户组成员关系
CREATE TABLE IF NOT EXISTS user_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    is_manager INTEGER DEFAULT 0,
    joined_at DATETIME
)

-- 用户角色: 用户与角色的多对多关联
CREATE TABLE IF NOT EXISTS user_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    role_id INTEGER NOT NULL,
    created_at DATETIME
)

-- 新对象: 新对象描述
CREATE TABLE IF NOT EXISTS new_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME
)

-- 产品线: 产品线是业务系统的顶层分类，代表一个独立的产品或产品系列。一个产品线可以包含多个版本。
CREATE TABLE IF NOT EXISTS products (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(200) UNIQUE NOT NULL,
    description TEXT,
    owner_id INTEGER,
    is_active INTEGER DEFAULT 1
)

-- 产品版本: 产品版本是产品线的软件版本，如 v1.0、2024-Q4 等。每个版本包含独立的领域模型数据。
-- [CHANGED 2026-06-13] 删除 code 列, name 作为唯一业务键(产品内唯一)
-- 迁移: 原 code 数据已合并到 name, 唯一性由 (product_id, name) 联合约束保证
CREATE TABLE IF NOT EXISTS versions (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    visibility VARCHAR(200) NOT NULL DEFAULT 'draft',
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_current INTEGER DEFAULT 0,
    owner_id INTEGER,
    FOREIGN KEY (product_id) REFERENCES products(id),
    UNIQUE(product_id, name)
)

-- 领域: 领域是业务领域的顶层分类，代表一个业务领域。领域下包含多个子领域。
CREATE TABLE IF NOT EXISTS domains (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    owner_id INTEGER,
    FOREIGN KEY (version_id) REFERENCES versions(id)
)

-- 子领域: 子领域是领域的下一级分类，代表业务领域的细分。子领域下包含多个服务模块。
CREATE TABLE IF NOT EXISTS sub_domains (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    domain_id INTEGER,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    created_at DATETIME,
    owner_id INTEGER,
    FOREIGN KEY (version_id) REFERENCES versions(id),
    FOREIGN KEY (domain_id) REFERENCES domains(id)
)

-- 服务模块: 服务模块是子领域的下一级分类，代表一个独立的服务模块。服务模块下包含多个业务对象。
CREATE TABLE IF NOT EXISTS service_modules (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    sub_domain_id INTEGER NOT NULL,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    owner_id INTEGER,
    FOREIGN KEY (version_id) REFERENCES versions(id),
    FOREIGN KEY (sub_domain_id) REFERENCES sub_domains(id)
)

-- 业务对象: 业务对象是领域模型的核心实体，代表业务领域中的重要的事物或概念。业务对象之间可以有各种关系。
CREATE TABLE IF NOT EXISTS business_objects (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    service_module_id INTEGER,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    owner_id INTEGER,
    FOREIGN KEY (version_id) REFERENCES versions(id),
    FOREIGN KEY (service_module_id) REFERENCES service_modules(id)
)

-- 业务关系: 业务关系描述业务对象之间的关联关系，如依赖、调用、数据流转等。
CREATE TABLE IF NOT EXISTS relationships (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    source_bo_id INTEGER NOT NULL,
    target_bo_id INTEGER NOT NULL,
    source_code VARCHAR(200),
    target_code VARCHAR(200),
    code VARCHAR(200),
    relation_code VARCHAR(200),
    relation_type VARCHAR(200) NOT NULL,
    relation_direction VARCHAR(200),
    relation_desc TEXT,
    FOREIGN KEY (version_id) REFERENCES versions(id)
)

-- Indexes for AI异步任务
CREATE INDEX IF NOT EXISTS idx_ai_async_task_status ON ai_async_tasks(status)
CREATE INDEX IF NOT EXISTS idx_ai_async_task_session ON ai_async_tasks(session_id)
CREATE INDEX IF NOT EXISTS idx_ai_async_task_tenant ON ai_async_tasks(tenant_id)
CREATE INDEX IF NOT EXISTS idx_ai_async_task_priority ON ai_async_tasks(priority)
CREATE INDEX IF NOT EXISTS idx_ai_async_task_time ON ai_async_tasks(created_at)

-- Indexes for 审计日志
CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_logs(log_category)
CREATE INDEX IF NOT EXISTS idx_audit_category_action_time ON audit_logs(log_category, action, created_at)
CREATE INDEX IF NOT EXISTS idx_audit_level ON audit_logs(log_level)
CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_logs(object_type, object_id)
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at)
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_logs(trace_id)
CREATE INDEX IF NOT EXISTS idx_audit_txn ON audit_logs(transaction_id)
CREATE INDEX IF NOT EXISTS idx_audit_status ON audit_logs(status)
CREATE INDEX IF NOT EXISTS idx_audit_tool_call ON audit_logs(tool_call_id)
CREATE INDEX IF NOT EXISTS idx_audit_parent ON audit_logs(parent_object_type, parent_object_id)

-- Indexes for 变更事件
CREATE INDEX IF NOT EXISTS idx_change_events_object_type ON change_events(object_type)
CREATE INDEX IF NOT EXISTS idx_change_events_object_id ON change_events(object_id)
CREATE INDEX IF NOT EXISTS idx_change_events_status ON change_events(status)
CREATE INDEX IF NOT EXISTS idx_change_events_created_at ON change_events(created_at)
CREATE INDEX IF NOT EXISTS idx_change_events_audit_log ON change_events(audit_log_id)

-- Indexes for 变更订阅
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_user_id ON change_subscriptions(user_id)
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_object_type ON change_subscriptions(object_type)
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_enabled ON change_subscriptions(enabled)

-- Indexes for 员工数据权限范围
CREATE UNIQUE INDEX IF NOT EXISTS idx_emp_scope_code ON employee_data_scopes(code)

-- Indexes for 枚举类型
CREATE INDEX IF NOT EXISTS idx_enum_types_name ON enum_types(name)
CREATE INDEX IF NOT EXISTS idx_enum_types_category ON enum_types(category)

-- Indexes for 枚举值
CREATE UNIQUE INDEX IF NOT EXISTS uidx_enum_values_type_code ON enum_values(enum_type_id, code)
CREATE INDEX IF NOT EXISTS idx_enum_values_enum_type_id ON enum_values(enum_type_id)
CREATE INDEX IF NOT EXISTS idx_enum_values_name ON enum_values(name)

-- Indexes for 过滤变体
CREATE INDEX IF NOT EXISTS idx_filter_variants_user_object ON filter_variants(user_id, object_type)
CREATE INDEX IF NOT EXISTS idx_filter_variants_shared ON filter_variants(is_shared, object_type)
CREATE INDEX IF NOT EXISTS idx_filter_variants_name ON filter_variants(name)

-- Indexes for 用户组数据权限
CREATE UNIQUE INDEX IF NOT EXISTS idx_group_data_perm_unique ON group_data_permissions(group_id, resource_type, resource_id)
CREATE INDEX IF NOT EXISTS idx_group_data_perm_group ON group_data_permissions(group_id)

-- Indexes for 角色
CREATE UNIQUE INDEX IF NOT EXISTS idx_role_code ON roles(code)

-- Indexes for 角色权限
CREATE INDEX IF NOT EXISTS idx_role_permissions_role_id ON role_permissions(role_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_role_permission_unique ON role_permissions(role_id, permission_id)

-- Indexes for 任务定义
CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_task_code ON scheduled_tasks(code)
CREATE INDEX IF NOT EXISTS idx_scheduled_task_category ON scheduled_tasks(category)
CREATE INDEX IF NOT EXISTS idx_scheduled_task_enabled ON scheduled_tasks(enabled)
CREATE INDEX IF NOT EXISTS idx_scheduled_task_next_run ON scheduled_tasks(next_run_at)

-- Indexes for 任务执行记录
CREATE INDEX IF NOT EXISTS idx_task_execution_task ON task_executions(task_id)
CREATE INDEX IF NOT EXISTS idx_task_execution_status ON task_executions(status)
CREATE INDEX IF NOT EXISTS idx_task_execution_time ON task_executions(created_at)
CREATE INDEX IF NOT EXISTS idx_task_execution_type ON task_executions(task_type)

-- Indexes for 任务队列配置
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_queue_name ON task_queues(name)
CREATE INDEX IF NOT EXISTS idx_task_queue_priority ON task_queues(priority)

-- Indexes for 用户
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_username ON users(username)
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_sso ON users(sso_provider, sso_user_id)
CREATE INDEX IF NOT EXISTS idx_users_display_name ON users(display_name)

-- Indexes for 用户组
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_group_code ON user_groups(code)
CREATE INDEX IF NOT EXISTS idx_user_group_parent ON user_groups(parent_id)
CREATE INDEX IF NOT EXISTS idx_user_groups_name ON user_groups(name)

-- Indexes for 用户组成员
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_group_member_unique ON user_group_members(user_id, group_id)
CREATE INDEX IF NOT EXISTS idx_user_group_member_group ON user_group_members(group_id)
CREATE INDEX IF NOT EXISTS idx_user_group_member_user ON user_group_members(user_id)

-- Indexes for 用户角色
CREATE INDEX IF NOT EXISTS idx_user_roles_user_id ON user_roles(user_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_role_unique ON user_roles(user_id, role_id)

-- Indexes for 新对象
CREATE UNIQUE INDEX IF NOT EXISTS idx_code ON new_objects(code)
CREATE INDEX IF NOT EXISTS idx_new_objects_name ON new_objects(name)

-- Indexes for 产品线
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)
CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active)

-- Indexes for 产品版本
CREATE INDEX IF NOT EXISTS idx_versions_product_id ON versions(product_id)
CREATE INDEX IF NOT EXISTS idx_versions_name ON versions(name)
CREATE INDEX IF NOT EXISTS idx_versions_is_current ON versions(is_current)

-- Indexes for 领域
CREATE UNIQUE INDEX IF NOT EXISTS uidx_domains_version_code ON domains(version_id, code)
CREATE INDEX IF NOT EXISTS idx_domains_version_id ON domains(version_id)
CREATE INDEX IF NOT EXISTS idx_domains_name ON domains(name)

-- Indexes for 子领域
CREATE UNIQUE INDEX IF NOT EXISTS uidx_sub_domains_version_code ON sub_domains(version_id, code)
CREATE INDEX IF NOT EXISTS idx_sub_domains_version_id ON sub_domains(version_id)
CREATE INDEX IF NOT EXISTS idx_sub_domains_domain_id ON sub_domains(domain_id)
CREATE INDEX IF NOT EXISTS idx_sub_domains_version_domain_id ON sub_domains(version_id, domain_id)
CREATE INDEX IF NOT EXISTS idx_sub_domains_name ON sub_domains(name)

-- Indexes for 服务模块
CREATE UNIQUE INDEX IF NOT EXISTS uidx_service_modules_version_code ON service_modules(version_id, code)
CREATE INDEX IF NOT EXISTS idx_service_modules_version_id ON service_modules(version_id)
CREATE INDEX IF NOT EXISTS idx_service_modules_sub_domain_id ON service_modules(sub_domain_id)
CREATE INDEX IF NOT EXISTS idx_service_modules_version_sub_domain_id ON service_modules(version_id, sub_domain_id)
CREATE INDEX IF NOT EXISTS idx_service_modules_name ON service_modules(name)

-- Indexes for 业务对象
CREATE UNIQUE INDEX IF NOT EXISTS uidx_business_objects_version_code ON business_objects(version_id, code)
CREATE INDEX IF NOT EXISTS idx_business_objects_version_service_module ON business_objects(version_id, service_module_id)
CREATE INDEX IF NOT EXISTS idx_business_objects_version_id ON business_objects(version_id)
CREATE INDEX IF NOT EXISTS idx_business_objects_service_module_id ON business_objects(service_module_id)
CREATE INDEX IF NOT EXISTS idx_business_objects_version_name ON business_objects(version_id, name)
CREATE INDEX IF NOT EXISTS idx_business_objects_name ON business_objects(name)

-- Indexes for 业务关系
CREATE UNIQUE INDEX IF NOT EXISTS uidx_relationships_version_source_target_type ON relationships(version_id, source_bo_id, target_bo_id, relation_code)
-- [2026-06-15] 业务层+DB层联合校验: 源+目标+方向在版本内唯一 (修复历史 bug: id=101 vs id=129 同源同目标同方向但 code 不同)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_relationships_version_source_target_direction ON relationships(version_id, source_bo_id, target_bo_id, relation_direction)
CREATE INDEX IF NOT EXISTS idx_relationships_version_source ON relationships(version_id, source_bo_id)
CREATE INDEX IF NOT EXISTS idx_relationships_version_target ON relationships(version_id, target_bo_id)
CREATE INDEX IF NOT EXISTS idx_relationships_version_id ON relationships(version_id)
CREATE INDEX IF NOT EXISTS idx_relationships_source_bo_id ON relationships(source_bo_id)
CREATE INDEX IF NOT EXISTS idx_relationships_target_bo_id ON relationships(target_bo_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_relationships_code ON relationships(code)
CREATE INDEX IF NOT EXISTS idx_relationships_version_type ON relationships(version_id, relation_code)
CREATE INDEX IF NOT EXISTS idx_relationships_relation_desc ON relationships(relation_desc)
