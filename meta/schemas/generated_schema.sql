-- 自动生成的 Schema
-- 生成时间: 2026-10-31 04:40:32.338663

-- 地址: 结构化地址库（支持对象）：国家 / 省 / 市 / 区 / 街道 / 门牌 / 邮编分列 + 格式化全文；只被引用，不承载用途 / 角色
CREATE TABLE IF NOT EXISTS addresses (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    country_id INTEGER NOT NULL,
    province_id INTEGER,
    city_id INTEGER,
    district_id INTEGER,
    street VARCHAR(200),
    street_number VARCHAR(200),
    postal_code VARCHAR(200),
    formatted_address TEXT NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    FOREIGN KEY (country_id) REFERENCES regions(id),
    FOREIGN KEY (province_id) REFERENCES regions(id),
    FOREIGN KEY (city_id) REFERENCES regions(id),
    FOREIGN KEY (district_id) REFERENCES regions(id)
)

-- 追溯调整: 追溯调整——对既有定价结果的补差 / 追溯改价 / 手工覆盖
CREATE TABLE IF NOT EXISTS adjustments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_result_id INTEGER,
    adjustment_type VARCHAR(200) NOT NULL DEFAULT 'subsequent_debit',
    delta_amount REAL NOT NULL DEFAULT 0,
    effective_period VARCHAR(200),
    posted_flag INTEGER NOT NULL DEFAULT 0,
    reason TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (original_result_id) REFERENCES calc_results(id)
)

-- 分摊结果: 分摊结果留痕——头记待摊总额、行记各行摊得额，含来源单据与分摊规则
CREATE TABLE IF NOT EXISTS allocation_results (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    document_type VARCHAR(200) NOT NULL,
    document_id INTEGER NOT NULL,
    document_line_id INTEGER,
    parent_id INTEGER NOT NULL,
    level VARCHAR(200) NOT NULL,
    sequence INTEGER NOT NULL DEFAULT 0,
    amount REAL NOT NULL,
    net_amount REAL NOT NULL,
    currency VARCHAR(200) DEFAULT 'CNY',
    sign VARCHAR(200) NOT NULL DEFAULT '+',
    allocation_rule_id INTEGER NOT NULL,
    allocation_basis VARCHAR(200) NOT NULL,
    allocation_basis_field VARCHAR(200),
    group_by VARCHAR(200),
    rounding VARCHAR(200),
    floor_value REAL,
    origin VARCHAR(200) NOT NULL DEFAULT 'unplanned',
    charge_source VARCHAR(200),
    source_document_type VARCHAR(200),
    source_document_id INTEGER,
    target VARCHAR(200),
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (allocation_rule_id) REFERENCES allocation_rules(id)
)

-- 分摊规则: 分摊规则——把一个金额按配置基数摊到多行（1→N）
CREATE TABLE IF NOT EXISTS allocation_rules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    basis VARCHAR(200) NOT NULL DEFAULT 'equal',
    manual_factor REAL,
    group_by VARCHAR(200),
    rounding VARCHAR(200),
    floor REAL,
    target VARCHAR(200) NOT NULL DEFAULT 'cost',
    description TEXT,
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

-- 属性定义: 属性字典定义层——租户级/平台级可扩展属性的类型、值域与使用分级
CREATE TABLE IF NOT EXISTS attribute_definitions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL DEFAULT 0,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    data_type VARCHAR(200) NOT NULL DEFAULT 'string',
    usage_class VARCHAR(200) NOT NULL DEFAULT 'descriptive',
    value_domain_type VARCHAR(200) NOT NULL DEFAULT 'none',
    value_domain_ref VARCHAR(200),
    multi_value_flag INTEGER NOT NULL DEFAULT 0,
    uom_code VARCHAR(200),
    is_configurable INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    revision INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    created_at DATETIME
)

-- 属性适用范围: 属性适用范围——属性作用于哪些对象或物料分类，以及是否必填
CREATE TABLE IF NOT EXISTS attribute_scopes (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL DEFAULT 0,
    attribute_id INTEGER NOT NULL,
    scope_type VARCHAR(200) NOT NULL DEFAULT 'object',
    scope_ref VARCHAR(200) NOT NULL,
    required_flag INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL DEFAULT 10,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (attribute_id) REFERENCES attribute_definitions(id)
)

-- 审计日志: 审计日志记录所有业务对象的变更历史，包括创建、更新、删除操作
CREATE TABLE IF NOT EXISTS audit_logs (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
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
    change_set_id VARCHAR(200),
    reason_code VARCHAR(200),
    status VARCHAR(200) DEFAULT 'written',
    status_entered_at DATETIME,
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,
    agent_id VARCHAR(200),
    agent_session_id VARCHAR(200),
    tool_call_id VARCHAR(200),
    agent_reasoning TEXT
)

-- 定价明细: 定价明细（步骤明细）——逐步骤回放，支持逐层小计与可解释
CREATE TABLE IF NOT EXISTS calc_details (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    element_type VARCHAR(200) NOT NULL,
    price_element_code VARCHAR(200),
    rate_type_code VARCHAR(200),
    label VARCHAR(200),
    unit_price REAL,
    extended_amount REAL NOT NULL DEFAULT 0,
    running_net_amount REAL NOT NULL DEFAULT 0,
    rollup_flag INTEGER NOT NULL DEFAULT 0,
    skip_running_price INTEGER NOT NULL DEFAULT 0,
    subtotal_key VARCHAR(200),
    base_level VARCHAR(200),
    base_source VARCHAR(200),
    base_step VARCHAR(200),
    rolling INTEGER NOT NULL DEFAULT 0,
    base_value REAL,
    skipped INTEGER NOT NULL DEFAULT 0,
    skip_reason VARCHAR(200),
    hit_ids TEXT,
    skipped_candidates TEXT,
    factor_snapshot TEXT,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 定价过程: 定价过程（业务别名：定价计算过程）——可配置的有序计算序列
CREATE TABLE IF NOT EXISTS calc_procedures (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    procedure_type VARCHAR(200) NOT NULL DEFAULT 'pricing',
    result_semantic VARCHAR(200) NOT NULL DEFAULT 'price',
    currency VARCHAR(200),
    subtotal_keys TEXT,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 定价过程步骤: 定价过程步骤 —— calc_procedure 的一条有序计算步骤
CREATE TABLE IF NOT EXISTS calc_procedure_steps (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calc_procedure_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    element_type VARCHAR(200) NOT NULL,
    rate_type_id INTEGER,
    condition INTEGER,
    params TEXT,
    rolling INTEGER NOT NULL DEFAULT 0,
    base_step VARCHAR(200),
    subtotal_key VARCHAR(200),
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 定价结果: 定价结果（结果行）——挂业务单据的定价结论
CREATE TABLE IF NOT EXISTS calc_results (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    document_type VARCHAR(200) NOT NULL,
    document_id INTEGER NOT NULL,
    document_line_id INTEGER,
    level VARCHAR(200) NOT NULL DEFAULT 'header',
    process_code VARCHAR(200) NOT NULL,
    result_semantic VARCHAR(200) NOT NULL DEFAULT 'price',
    rate_type_code VARCHAR(200),
    element_type VARCHAR(200),
    base_level VARCHAR(200) NOT NULL DEFAULT 'line',
    base_source VARCHAR(200) NOT NULL DEFAULT 'pricing_quantity',
    base_step VARCHAR(200),
    rolling INTEGER NOT NULL DEFAULT 0,
    base_formula TEXT,
    rate REAL,
    base REAL,
    amount REAL NOT NULL DEFAULT 0,
    net_amount REAL,
    currency VARCHAR(200) NOT NULL,
    sign VARCHAR(200) NOT NULL DEFAULT '+',
    sequence INTEGER NOT NULL DEFAULT 0,
    origin VARCHAR(200) NOT NULL DEFAULT 'planned',
    rate_source VARCHAR(200) NOT NULL DEFAULT 'rate_record',
    pricing_period_id INTEGER,
    external_rate_source_id INTEGER,
    fact_snapshot TEXT,
    price_mode VARCHAR(200) NOT NULL DEFAULT 'carry',
    freeze_policy VARCHAR(200),
    reprice_trigger VARCHAR(200),
    qty_basis VARCHAR(200),
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (external_rate_source_id) REFERENCES external_rate_sources(id),
    FOREIGN KEY (pricing_period_id) REFERENCES pricing_periods(id)
)

-- 作业日历: 作业日历字典（周工作日模式 + 地区归属；例外日子对象 calendar_days）
CREATE TABLE IF NOT EXISTS calendars (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    parent_calendar_id INTEGER,
    country_id INTEGER,
    day_mask_mon INTEGER NOT NULL DEFAULT 1,
    day_mask_tue INTEGER NOT NULL DEFAULT 1,
    day_mask_wed INTEGER NOT NULL DEFAULT 1,
    day_mask_thu INTEGER NOT NULL DEFAULT 1,
    day_mask_fri INTEGER NOT NULL DEFAULT 1,
    day_mask_sat INTEGER NOT NULL DEFAULT 0,
    day_mask_sun INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    FOREIGN KEY (parent_calendar_id) REFERENCES calendars(id),
    FOREIGN KEY (country_id) REFERENCES regions(id)
)

-- 日历例外日: 日历例外日（holiday 非工作日 / workday 强制工作日；无记录即标准）
CREATE TABLE IF NOT EXISTS calendar_days (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    calendar_id INTEGER NOT NULL,
    date DATETIME NOT NULL,
    day_type VARCHAR(200) NOT NULL,
    note VARCHAR(200),
    created_at DATETIME,
    FOREIGN KEY (calendar_id) REFERENCES calendars(id)
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
    audit_log_id INTEGER,
    FOREIGN KEY (audit_log_id) REFERENCES audit_logs(id)
)

-- 变更申请: 通用单据内容变更申请（审批通过后经统一写漏斗生效）
CREATE TABLE IF NOT EXISTS change_requests (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_object_type VARCHAR(200) NOT NULL,
    target_object_id VARCHAR(200) NOT NULL,
    target_revision_no INTEGER NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    reason_code VARCHAR(200),
    summary TEXT,
    submitted_by VARCHAR(200),
    submitted_at DATETIME,
    approved_by VARCHAR(200),
    approved_at DATETIME,
    applied_at DATETIME,
    applied_revision_no INTEGER,
    fail_reason VARCHAR(200),
    change_set_id VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME
)

-- 变更申请行: 变更申请明细（一行 = 目标对象的一个字段变更）
CREATE TABLE IF NOT EXISTS change_request_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    change_request_id INTEGER NOT NULL,
    line_key VARCHAR(200),
    field_name VARCHAR(200) NOT NULL,
    old_value TEXT,
    new_value TEXT
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
    created_at DATETIME NOT NULL DEFAULT 'NOW()',
    FOREIGN KEY (user_id) REFERENCES users(id)
)

-- 配置实例: 配置实例头（模型版本 / 状态 / hash / 求解上下文）
CREATE TABLE IF NOT EXISTS configurations (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_item_id INTEGER NOT NULL,
    structure_id INTEGER NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    config_hash VARCHAR(200),
    revision INTEGER NOT NULL DEFAULT 1,
    reused_from_id INTEGER,
    match_policy_used VARCHAR(200) NOT NULL DEFAULT 0,
    source_level VARCHAR(200) NOT NULL DEFAULT 'L2',
    context_json TEXT,
    validation_result_json TEXT,
    solved_at DATETIME,
    frozen_at DATETIME,
    variant_item_id INTEGER,
    FOREIGN KEY (model_item_id) REFERENCES items(id),
    FOREIGN KEY (structure_id) REFERENCES item_structures(id),
    FOREIGN KEY (reused_from_id) REFERENCES configurations(id),
    FOREIGN KEY (variant_item_id) REFERENCES items(id)
)

-- 配置组件: 一次配置展开出的组件（键 / 来源行 / 用量 / 来源规则）
CREATE TABLE IF NOT EXISTS configuration_components (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    configuration_id INTEGER NOT NULL,
    component_key VARCHAR(200) NOT NULL,
    structure_line_id INTEGER NOT NULL,
    component_item_id INTEGER NOT NULL,
    qty REAL NOT NULL,
    uom_code VARCHAR(200) NOT NULL,
    parent_component_key VARCHAR(200),
    selection_source VARCHAR(200) NOT NULL DEFAULT 'auto',
    source_rule_id INTEGER,
    child_configuration_id INTEGER,
    substitute_for_key VARCHAR(200),
    seq INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (configuration_id) REFERENCES configurations(id),
    FOREIGN KEY (structure_line_id) REFERENCES item_structure_lines(id),
    FOREIGN KEY (component_item_id) REFERENCES items(id),
    FOREIGN KEY (source_rule_id) REFERENCES config_rules(id),
    FOREIGN KEY (child_configuration_id) REFERENCES configurations(id)
)

-- 配置特征值: 一次配置求解的特征取值（按属性定义的数据类型填充对应值列）
CREATE TABLE IF NOT EXISTS configuration_values (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    configuration_id INTEGER NOT NULL,
    attribute_code VARCHAR(200) NOT NULL,
    seq INTEGER NOT NULL DEFAULT 1,
    value_text VARCHAR(200),
    value_number REAL,
    value_boolean INTEGER,
    source VARCHAR(200) NOT NULL DEFAULT 'user',
    source_rule_id INTEGER,
    FOREIGN KEY (configuration_id) REFERENCES configurations(id),
    FOREIGN KEY (source_rule_id) REFERENCES config_rules(id)
)

-- 配置规则: 模型版本的配置规则头（类型 / 严重度 / 优先级 / 解释文案）
CREATE TABLE IF NOT EXISTS config_rules (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    structure_id INTEGER NOT NULL,
    code VARCHAR(200),
    rule_type VARCHAR(200) NOT NULL,
    severity VARCHAR(200) NOT NULL DEFAULT 'blocking',
    priority INTEGER NOT NULL DEFAULT 100,
    message VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    description TEXT,
    FOREIGN KEY (structure_id) REFERENCES item_structures(id)
)

-- 配置规则条件项: 规则的条件项（if / then，目标 + 算子 + 取值）
CREATE TABLE IF NOT EXISTS config_rule_terms (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    seq INTEGER NOT NULL DEFAULT 1,
    clause VARCHAR(200) NOT NULL,
    target_type VARCHAR(200) NOT NULL,
    target_line_id INTEGER,
    target_class_item_id INTEGER,
    attribute_code VARCHAR(200),
    operator VARCHAR(200) NOT NULL,
    value_text VARCHAR(200),
    value_number REAL,
    value_number_to REAL,
    value_list TEXT,
    FOREIGN KEY (rule_id) REFERENCES config_rules(id),
    FOREIGN KEY (target_line_id) REFERENCES item_structure_lines(id),
    FOREIGN KEY (target_class_item_id) REFERENCES items(id)
)

-- 控制参数定义: 控制参数定义（参数名字典，含值类型与兜底默认值）
CREATE TABLE IF NOT EXISTS control_parameter_defs (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(200) NOT NULL DEFAULT 'sales',
    value_type VARCHAR(200) NOT NULL DEFAULT 'string',
    enum_type_id INTEGER,
    target_bo VARCHAR(200),
    default_value TEXT,
    description TEXT,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    FOREIGN KEY (enum_type_id) REFERENCES enum_types(id)
)

-- 控制参数取值: 控制参数取值（按组织 / 单据类型 / 行类型 / 物料组的维度组合给出参数值）
CREATE TABLE IF NOT EXISTS control_parameter_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    control_parameter_id INTEGER NOT NULL,
    org_id INTEGER,
    document_type_id INTEGER,
    line_type_id INTEGER,
    item_group_id INTEGER,
    specificity_rank INTEGER NOT NULL DEFAULT 100,
    value TEXT NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (control_parameter_id) REFERENCES control_parameter_defs(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (document_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (line_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (item_group_id) REFERENCES item_groups(id)
)

-- 累计用量: 累计用量——费率记录跨单据累计已用量（合同量用满失效）
CREATE TABLE IF NOT EXISTS cumulative_usages (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rate_record_id INTEGER NOT NULL,
    usage_group_id INTEGER,
    used_amount REAL NOT NULL DEFAULT 0,
    used_quantity REAL NOT NULL DEFAULT 0,
    used_documents INTEGER NOT NULL DEFAULT 0,
    last_used_at DATETIME,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (rate_record_id) REFERENCES rate_records(id),
    FOREIGN KEY (usage_group_id) REFERENCES usage_groups(id)
)

-- 币种: 币种主数据（ISO 4217 字典；单据流金额字段的币种载体）
CREATE TABLE IF NOT EXISTS currencies (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_en VARCHAR(200),
    decimal_places INTEGER NOT NULL DEFAULT 2,
    symbol VARCHAR(200),
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME
)

-- 汇率: 汇率（单向存储：1 个源币种 = rate 个目标币种，自生效日起）
CREATE TABLE IF NOT EXISTS currency_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    currency_id INTEGER NOT NULL,
    to_currency_id INTEGER NOT NULL,
    rate_type VARCHAR(200) NOT NULL DEFAULT 'spot',
    valid_from DATETIME NOT NULL,
    rate REAL NOT NULL,
    description TEXT,
    FOREIGN KEY (currency_id) REFERENCES currencies(id),
    FOREIGN KEY (to_currency_id) REFERENCES currencies(id)
)

-- 客户档案: 客户档案（我方与某 party 的客户关系侧商务属性；挂在 party_relation(role='customer') 之上 1:1）
CREATE TABLE IF NOT EXISTS customer_accounts (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relation_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    tax_classification_id INTEGER,
    default_payment_term_id INTEGER,
    default_incoterm_code VARCHAR(200),
    default_rate_table_id INTEGER,
    created_at DATETIME,
    FOREIGN KEY (tax_classification_id) REFERENCES tax_classifications(id),
    FOREIGN KEY (default_payment_term_id) REFERENCES payment_terms(id),
    FOREIGN KEY (default_rate_table_id) REFERENCES rate_tables(id)
)

-- 客户销售员分配: 客户与销售员的分配关系（可按销售组织区分，可设主销售员）
CREATE TABLE IF NOT EXISTS customer_salesperson_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER NOT NULL,
    sales_org_id INTEGER,
    salesperson_id INTEGER NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    valid_from DATETIME,
    valid_to DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
    FOREIGN KEY (sales_org_id) REFERENCES orgs(id),
    FOREIGN KEY (salesperson_id) REFERENCES salespersons(id)
)

-- 客户销售组织: 客户在特定销售组织下的商务条件差异（覆盖账户级默认值）
CREATE TABLE IF NOT EXISTS customer_sales_orgs (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER NOT NULL,
    sales_org_id INTEGER NOT NULL,
    tax_classification_id INTEGER,
    payment_term_id INTEGER,
    incoterm_code VARCHAR(200),
    currency_id INTEGER,
    rate_table_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
    FOREIGN KEY (sales_org_id) REFERENCES orgs(id),
    FOREIGN KEY (tax_classification_id) REFERENCES tax_classifications(id),
    FOREIGN KEY (payment_term_id) REFERENCES payment_terms(id),
    FOREIGN KEY (currency_id) REFERENCES currencies(id),
    FOREIGN KEY (rate_table_id) REFERENCES rate_tables(id)
)

-- 数据权限: 控制用户对特定资源实例的访问权限
CREATE TABLE IF NOT EXISTS data_permissions (
    user_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    resource_id INTEGER NOT NULL,
    permission_level VARCHAR(200) NOT NULL,
    inherit_to_children INTEGER DEFAULT 1,
    created_at DATETIME
)

-- 产品组: 产品组（SAP division 语义的扁平受控值集；非物料分类 item_group）
CREATE TABLE IF NOT EXISTS divisions (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT
)

-- 单据类型（只读）: 单据类型（type_definitions 的 header 切片，只读）
CREATE VIEW IF NOT EXISTS document_types AS SELECT id, code, name,
       document_category AS category,
       default_type_id AS default_line_type_id,
       number_sequence_id,
       status, description, created_at
FROM type_definitions
WHERE level = 'header'


-- 员工数据权限范围: 员工数据权限范围模板，支持本人/部门/层级三种范围
CREATE TABLE IF NOT EXISTS employee_data_scopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    condition_template VARCHAR(200) NOT NULL,
    description VARCHAR(200)
)

-- 枚举类型: 枚举类型定义，支持系统枚举和业务枚举的分层管理，支持多维枚举值。
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

-- 排斥组: 排斥组——同组内多候选命中时的消解规则（多候选取优）
CREATE TABLE IF NOT EXISTS exclusion_groups (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    members TEXT NOT NULL,
    resolution VARCHAR(200) NOT NULL DEFAULT 'first_in_sequence',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 外部价格源: 外部价格源——外部行情 / 指数取价来源定义
CREATE TABLE IF NOT EXISTS external_rate_sources (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    source VARCHAR(200) NOT NULL DEFAULT 'index',
    quote_code VARCHAR(200),
    calendar_id INTEGER,
    fallback_rule VARCHAR(200),
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (calendar_id) REFERENCES calendars(id)
)

-- 因子目录: 定价因子目录（业务别名：字段目录）——哪些字段可当定价因子、事实源分类、是否影响价格
CREATE TABLE IF NOT EXISTS factor_catalogs (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type VARCHAR(200) NOT NULL,
    field_id VARCHAR(200) NOT NULL,
    source_type VARCHAR(200) NOT NULL DEFAULT 'master',
    is_price_relevant INTEGER NOT NULL DEFAULT 1,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
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

-- 国际贸易术语: 国际贸易术语（Incoterms）字典——风险转移点与买卖双方责任划分
CREATE TABLE IF NOT EXISTS incoterms (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    name_en VARCHAR(200) NOT NULL,
    edition VARCHAR(200) NOT NULL DEFAULT '2020',
    transport_mode VARCHAR(200) NOT NULL,
    risk_transfer_point VARCHAR(200) NOT NULL,
    export_clearance_by VARCHAR(200) NOT NULL,
    import_clearance_by VARCHAR(200) NOT NULL,
    main_carriage_by VARCHAR(200) NOT NULL,
    unloading_by VARCHAR(200) NOT NULL,
    insurance_cover VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME
)

-- 物料: 物料主数据（foundation 物料锚）
CREATE TABLE IF NOT EXISTS items (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    spec VARCHAR(200),
    description TEXT,
    item_type VARCHAR(200) NOT NULL DEFAULT 'goods',
    billing_method_default VARCHAR(200),
    required_resource_type VARCHAR(200),
    standard_duration REAL,
    duration_type VARCHAR(200),
    is_field_service INTEGER DEFAULT 0,
    structure_role VARCHAR(200) NOT NULL DEFAULT 'none',
    config_match_policy VARCHAR(200) NOT NULL DEFAULT 'no',
    config_materialize_policy VARCHAR(200) NOT NULL DEFAULT 'off',
    variant_of_item_id INTEGER,
    variant_config_hash VARCHAR(200),
    item_group_id INTEGER NOT NULL,
    tax_classification_id INTEGER,
    base_uom INTEGER NOT NULL,
    sales_uom INTEGER,
    min_order_qty REAL,
    order_multiple REAL,
    net_weight REAL,
    gross_weight REAL,
    barcode VARCHAR(200),
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    created_at DATETIME,
    FOREIGN KEY (item_group_id) REFERENCES item_groups(id),
    FOREIGN KEY (base_uom) REFERENCES uoms(id),
    FOREIGN KEY (sales_uom) REFERENCES uoms(id),
    FOREIGN KEY (tax_classification_id) REFERENCES tax_classifications(id)
)

-- 物料分层参数值: 物料分层参数值（L0/L2 因子列 + 类型化值列 value_text/number/boolean，hybrid 参数；2026-10-07：L1 职能域层砍除 + 值列形态收口）
CREATE TABLE IF NOT EXISTS item_attribute_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    attribute_id INTEGER,
    attr_code VARCHAR(200) NOT NULL,
    org_id INTEGER,
    value_text TEXT,
    value_number REAL,
    value_boolean INTEGER,
    value_date DATETIME,
    value_datetime DATETIME,
    description TEXT,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (attribute_id) REFERENCES attribute_definitions(id)
)

-- 物料组: 物料组（树形分类对象，被物料引用）
CREATE TABLE IF NOT EXISTS item_groups (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    parent_id INTEGER,
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (parent_id) REFERENCES item_groups(id)
)

-- 物料结构: 物料结构头（一版结构；行见 item_structure_line）
CREATE TABLE IF NOT EXISTS item_structures (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    usage VARCHAR(200) NOT NULL DEFAULT 'production',
    alternative_no INTEGER NOT NULL DEFAULT 1,
    revision VARCHAR(200) NOT NULL,
    base_qty REAL NOT NULL DEFAULT 1,
    base_uom_id INTEGER NOT NULL,
    min_select INTEGER,
    max_select INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    valid_from DATETIME NOT NULL,
    valid_to DATETIME,
    description TEXT,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (base_uom_id) REFERENCES uoms(id)
)

-- 模型特征声明: 模型版本声明使用的可配置特征（编码 / 必填 / 默认值 / 展示顺序）
CREATE TABLE IF NOT EXISTS item_structure_attributes (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    structure_id INTEGER NOT NULL,
    attribute_code VARCHAR(200) NOT NULL,
    required_flag INTEGER NOT NULL DEFAULT 0,
    default_value_text VARCHAR(200),
    seq INTEGER NOT NULL DEFAULT 1,
    ui_widget VARCHAR(200),
    FOREIGN KEY (structure_id) REFERENCES item_structures(id)
)

-- 物料结构行: 物料结构行（组件 / 用量 / 可选性 / 有效期）
CREATE TABLE IF NOT EXISTS item_structure_lines (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    structure_id INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    component_item_id INTEGER NOT NULL,
    qty_per REAL,
    fixed_qty REAL,
    scrap_rate REAL NOT NULL DEFAULT 0,
    optional_flag INTEGER NOT NULL DEFAULT 0,
    default_flag INTEGER NOT NULL DEFAULT 0,
    default_qty REAL,
    min_qty REAL,
    max_qty REAL,
    valid_from DATETIME,
    valid_to DATETIME,
    operation_seq INTEGER,
    phantom_flag INTEGER NOT NULL DEFAULT 0,
    substitute_group_code VARCHAR(200),
    included_in_base_price INTEGER NOT NULL DEFAULT 0,
    bom_price REAL,
    note VARCHAR(200),
    FOREIGN KEY (structure_id) REFERENCES item_structures(id),
    FOREIGN KEY (component_item_id) REFERENCES items(id)
)

-- 物料单位换算: 物料单位换算（基本单位与其它单位的换算率）
CREATE TABLE IF NOT EXISTS item_uom_conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    uom_id INTEGER NOT NULL,
    factor REAL NOT NULL,
    description TEXT,
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id)
)

-- 物料外部标识: 物料外部标识交叉引用（客户/供应商/制造商件号配对）
CREATE TABLE IF NOT EXISTS item_xrefs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    partner_type VARCHAR(200) NOT NULL,
    partner_id INTEGER NOT NULL,
    part_no VARCHAR(200) NOT NULL,
    description TEXT,
    FOREIGN KEY (item_id) REFERENCES items(id)
)

-- 匹配键表: 匹配键表（业务别名：条件表）——用哪些因子的组合做键
CREATE TABLE IF NOT EXISTS key_schemas (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    key_fields TEXT NOT NULL,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 行类型（只读）: 行类型（type_definitions 的 line 切片，只读）
CREATE VIEW IF NOT EXISTS line_types AS SELECT id, code, name,
       line_category AS category,
       COALESCE(delivery_relevant, 1) AS delivery_relevant,
       status, description, created_at
FROM type_definitions
WHERE level = 'line'


-- 销售行类型确定: 销售行类型确定（单据类型 + 物料组 → 行类型）
CREATE TABLE IF NOT EXISTS line_type_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_type_id INTEGER NOT NULL,
    item_group_id INTEGER,
    specificity_rank INTEGER NOT NULL DEFAULT 100,
    line_type_id INTEGER NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (document_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (item_group_id) REFERENCES item_groups(id),
    FOREIGN KEY (line_type_id) REFERENCES type_definitions(id)
)

-- 位置: 位置主数据（统一自引用树：site / warehouse / zone / bin）
CREATE TABLE IF NOT EXISTS locations (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    location_type VARCHAR(200) NOT NULL,
    parent_id INTEGER,
    address_id INTEGER,
    calendar_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (parent_id) REFERENCES locations(id),
    FOREIGN KEY (address_id) REFERENCES addresses(id),
    FOREIGN KEY (calendar_id) REFERENCES calendars(id)
)

-- 查找序列: 查找序列（业务别名：存取序列）——有序查表列表，定义查表次序与所用键
CREATE TABLE IF NOT EXISTS lookup_sequences (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    steps TEXT NOT NULL,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
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
    created_at DATETIME,
    updated_at DATETIME
)

-- 编号序列: 单据编号规则（pattern 单一真源；当前值存平台 _sequences）
CREATE TABLE IF NOT EXISTS number_sequences (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    pattern VARCHAR(200) NOT NULL,
    scope_fields TEXT,
    date_field VARCHAR(200) DEFAULT 'order_date',
    start_value INTEGER NOT NULL DEFAULT 1,
    on_exhaust VARCHAR(200) NOT NULL DEFAULT 'error',
    preview VARCHAR(200),
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME
)

-- 组织: 组织（Org），用于组织用户和实现委托管理
CREATE TABLE IF NOT EXISTS orgs (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(200) UNIQUE NOT NULL,
    org_type VARCHAR(200) NOT NULL DEFAULT 'department',
    org_scope VARCHAR(200) DEFAULT 'internal',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    parent_id INTEGER,
    manager_id INTEGER,
    description VARCHAR(200),
    created_at DATETIME,
    FOREIGN KEY (parent_id) REFERENCES orgs(id)
)

-- 组织数据权限: 组织的数据访问权限
CREATE TABLE IF NOT EXISTS org_data_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    resource_id INTEGER NOT NULL,
    permission_level VARCHAR(200) NOT NULL,
    inherit_to_children INTEGER DEFAULT 1,
    created_at DATETIME
)

-- 法人主体: 法人主体面：恒取具备 legal_entity 职能的 org（候选集口径由视图 SQL 结构强制）
CREATE VIEW IF NOT EXISTS org_legal_entity AS SELECT o.id, o.code, o.name, o.org_type, o.parent_id, o.manager_id, o.status
FROM orgs o
WHERE EXISTS (
  SELECT 1 FROM org_functions f
  WHERE f.org_id = o.id AND f.function_type = 'legal_entity'
)


-- 组织成员: 组织成员关系（原 user_group_member.yaml, Plan A 迁移）
CREATE TABLE IF NOT EXISTS org_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    org_id INTEGER NOT NULL,
    is_manager INTEGER DEFAULT 0,
    joined_at DATETIME
)

-- 销售组织: 销售组织面：恒取具备 sales 职能的 org（候选集口径由视图 SQL 结构强制）
CREATE VIEW IF NOT EXISTS org_sales_org AS SELECT o.id, o.code, o.name, o.org_type, o.status
FROM orgs o
WHERE EXISTS (
  SELECT 1 FROM org_functions f
  WHERE f.org_id = o.id AND f.function_type = 'sales'
)


-- 身份主体: 身份锚（party）：组织 / 个人的统一身份记录；org 记录经 source='org' 进入本轴（1:1）
CREATE TABLE IF NOT EXISTS parties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    party_type VARCHAR(200) NOT NULL DEFAULT 'organization',
    source VARCHAR(200),
    org_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    FOREIGN KEY (org_id) REFERENCES orgs(id)
)

-- 往来单位地址: 往来单位在特定地址角色下引用的地址（收货 / 收票 / 售达）
CREATE TABLE IF NOT EXISTS party_addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party_id INTEGER NOT NULL,
    address_id INTEGER NOT NULL,
    role VARCHAR(200) NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (party_id) REFERENCES parties(id),
    FOREIGN KEY (address_id) REFERENCES addresses(id)
)

-- 身份档案（对外）: 对外档案面：恒排除 source='org' 的内部组织表示（口径由视图 SQL 结构强制）
CREATE VIEW IF NOT EXISTS party_archive AS SELECT id, code, name, party_type, source, org_id, status
FROM parties
WHERE COALESCE(source, '') <> 'org'


-- 业务伙伴属性值: 业务伙伴属性值——描述性/分析性属性的类型化值列（一行一列非空，多值用 seq 区分）
CREATE TABLE IF NOT EXISTS party_attribute_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL DEFAULT 0,
    party_id INTEGER NOT NULL,
    attribute_id INTEGER NOT NULL,
    seq INTEGER NOT NULL DEFAULT 1,
    value_text TEXT,
    value_number REAL,
    value_boolean INTEGER,
    value_date DATETIME,
    value_datetime DATETIME,
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (party_id) REFERENCES parties(id),
    FOREIGN KEY (attribute_id) REFERENCES attribute_definitions(id)
)

-- 业务伙伴组: 业务伙伴组（树形分类对象，被业务伙伴关系引用；role_scope 标注客户/供应商适用范围）
CREATE TABLE IF NOT EXISTS party_groups (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    role_scope VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    parent_id INTEGER,
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (parent_id) REFERENCES party_groups(id)
)

-- 内部治理台账: 内部治理台账面：取 source='org' 且该 org 当前具备我方主体职能（法人 / 管理单元）的内部组织表示（经 org 维度范围注入过滤）
CREATE VIEW IF NOT EXISTS party_internal AS SELECT p.id, p.code, p.name, p.party_type, p.source, p.org_id, p.status
FROM parties p
WHERE p.source = 'org'
  AND EXISTS (
    SELECT 1 FROM org_functions f
    WHERE f.org_id = p.org_id
      AND f.function_type IN ('legal_entity', 'management_unit')
  )


-- 业务伙伴关系: 客户 / 供应商关系实例（party₁ 我方 — party₂ 对手；单表 + role，一实例一角色）
CREATE TABLE IF NOT EXISTS party_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party1_id INTEGER NOT NULL,
    party2_id INTEGER NOT NULL,
    role VARCHAR(200) NOT NULL,
    internal_mark VARCHAR(200) NOT NULL,
    le_org_id INTEGER,
    group_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    FOREIGN KEY (party1_id) REFERENCES parties(id),
    FOREIGN KEY (party2_id) REFERENCES parties(id),
    FOREIGN KEY (le_org_id) REFERENCES orgs(id),
    FOREIGN KEY (group_id) REFERENCES party_groups(id)
)

-- 税务登记: 业务伙伴税务登记号（按国家 + 税种，至多一个主号）
CREATE TABLE IF NOT EXISTS party_tax_registrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party_id INTEGER NOT NULL,
    country_id INTEGER NOT NULL,
    tax_type VARCHAR(200) NOT NULL,
    registration_number VARCHAR(200) NOT NULL,
    is_primary INTEGER NOT NULL DEFAULT 0,
    valid_from DATETIME,
    valid_to DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    FOREIGN KEY (party_id) REFERENCES parties(id),
    FOREIGN KEY (country_id) REFERENCES regions(id)
)

-- 付款条件: 付款条件（账期规则头：基准日 + 截止日顺延；分期与折扣见行）
CREATE TABLE IF NOT EXISTS payment_terms (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    basis_date_rule VARCHAR(200) NOT NULL DEFAULT 'invoice_date',
    cutoff_day INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME
)

-- 付款条件分期: 付款条件分期行（百分比 / 月偏移 / 固定日 / 天偏移 / 现金折扣）
CREATE TABLE IF NOT EXISTS payment_term_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payment_term_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    percentage REAL NOT NULL DEFAULT 100,
    offset_months INTEGER NOT NULL DEFAULT 0,
    fixed_day_of_month INTEGER,
    offset_days INTEGER NOT NULL DEFAULT 0,
    discount_percent REAL,
    discount_days INTEGER,
    description TEXT,
    FOREIGN KEY (payment_term_id) REFERENCES payment_terms(id)
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
    created_at DATETIME,
    updated_at DATETIME
)

-- 权限资源: 权限资源 (view over permissions table)
CREATE TABLE IF NOT EXISTS permissions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200),
    name VARCHAR(200),
    description VARCHAR(200),
    resource_type VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME
)

-- 权限资源继承: 权限资源继承规则 (view over data_permission_rules)
CREATE TABLE IF NOT EXISTS data_permission_rules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER,
    resource_type VARCHAR(200),
    resource_id INTEGER,
    rule_type VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME
)

-- 条件权限规则: 基于条件的动态权限规则，支持维度过滤和条件匹配
CREATE TABLE IF NOT EXISTS permission_rules (
    permission_set_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    condition TEXT NOT NULL,
    permission_level VARCHAR(200) NOT NULL DEFAULT 'read',
    is_denied INTEGER DEFAULT 0,
    inherit_to_children INTEGER DEFAULT 1,
    propagate_to_parents INTEGER DEFAULT 1,
    analysis_mode VARCHAR(200),
    created_at DATETIME,
    created_by INTEGER,
    updated_at DATETIME
)

-- 权限集: 权限集，用于基于权限集的访问控制（PBAC）
CREATE TABLE IF NOT EXISTS permission_sets (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    is_system INTEGER DEFAULT 0,
    created_at DATETIME,
    user_count INTEGER,
    menu_count INTEGER,
    permission_count INTEGER,
    data_perm_count INTEGER
)

-- 权限集数据权限: 权限集级别的数据访问权限配置，控制权限集可访问的资源实例范围
CREATE TABLE IF NOT EXISTS permission_set_data_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER NOT NULL,
    resource_type VARCHAR(200) NOT NULL,
    resource_id INTEGER NOT NULL,
    permission_level VARCHAR(200) DEFAULT 'read',
    inherit_to_children INTEGER DEFAULT 1,
    created_at DATETIME,
    created_by INTEGER
)

-- 权限集维度范围: 权限集的管理维度范围声明，是权限推导的入口。
CREATE TABLE IF NOT EXISTS permission_set_dimension_scopes (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER NOT NULL,
    dimension_code VARCHAR(200) NOT NULL,
    dimension_values TEXT NOT NULL,
    inherit_children INTEGER DEFAULT 1,
    scope_mode VARCHAR(200) DEFAULT 'include'
)

-- 权限集维度范围 (复数视图): 权限集维度范围列表视图 (alias of permission_set_dimension_scope)
CREATE TABLE IF NOT EXISTS permission_set_dimension_scopes (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER,
    dimension_code VARCHAR(200),
    dimension_values TEXT,
    inherit_children INTEGER DEFAULT 1,
    scope_mode VARCHAR(200) DEFAULT 'include',
    created_at DATETIME,
    updated_at DATETIME
)

-- 权限集权限: 权限集与权限的多对多关联
CREATE TABLE IF NOT EXISTS permission_set_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permission_set_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    granted INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME
)

-- 个人档案: person 私有档案（PII 专属载体）：party_type='person' 的 1:1 扩展档案；独立权限域
CREATE TABLE IF NOT EXISTS person_profiles (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    party_id INTEGER UNIQUE NOT NULL,
    mobile VARCHAR(200),
    email VARCHAR(200)
)

-- 定价确定规则: 定价确定规则——按销售组织 / 单据类型 / 基准日决定价目表、定价过程与查找序列
CREATE TABLE IF NOT EXISTS pricing_determinations (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    sales_org_id INTEGER,
    order_type_id INTEGER,
    rate_table_id INTEGER,
    calc_procedure_id INTEGER NOT NULL,
    lookup_sequence_id INTEGER,
    currency VARCHAR(200),
    seq INTEGER NOT NULL DEFAULT 100,
    valid_from DATETIME,
    valid_to DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (sales_org_id) REFERENCES orgs(id),
    FOREIGN KEY (order_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (rate_table_id) REFERENCES rate_tables(id),
    FOREIGN KEY (calc_procedure_id) REFERENCES calc_procedures(id),
    FOREIGN KEY (lookup_sequence_id) REFERENCES lookup_sequences(id)
)

-- 计价期: 计价期——按单据日期或固定区间取均价的期间定义
CREATE TABLE IF NOT EXISTS pricing_periods (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    period_type VARCHAR(200) NOT NULL DEFAULT 'shipment_date',
    start_offset INTEGER NOT NULL DEFAULT 0,
    end_offset INTEGER NOT NULL DEFAULT 0,
    average_basis VARCHAR(200) NOT NULL DEFAULT 'average',
    rounding VARCHAR(200),
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 费率记录: 费率记录（业务别名：价目行 · 条件记录）——键组合下的费率值
CREATE TABLE IF NOT EXISTS rate_records (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    rate_table_id INTEGER NOT NULL,
    key_schema_id INTEGER NOT NULL,
    keys TEXT NOT NULL,
    rate_type_id INTEGER NOT NULL,
    rate REAL,
    value REAL,
    valid_from DATETIME,
    valid_to DATETIME,
    currency VARCHAR(200),
    rate_unit VARCHAR(200),
    rate_qty REAL,
    scale TEXT,
    scale_semantic VARCHAR(200),
    scale_divisor VARCHAR(200),
    exclude_bo VARCHAR(200),
    hit_policy VARCHAR(200) NOT NULL DEFAULT 'exclusive',
    allocation_weight REAL,
    priority INTEGER NOT NULL DEFAULT 100,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 费率表: 费率表（业务别名：价目表）——费率记录的容器
CREATE TABLE IF NOT EXISTS rate_tables (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    type VARCHAR(200),
    currency VARCHAR(200) NOT NULL,
    owner_org_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 费率类型: 费率类型（业务别名：条件类型，配置对象）——决定一条费率怎么算
CREATE TABLE IF NOT EXISTS rate_types (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    rate_class VARCHAR(200) NOT NULL,
    calc_type VARCHAR(200) NOT NULL DEFAULT 'percent',
    rate_source VARCHAR(200) NOT NULL DEFAULT 'rate_record',
    sign VARCHAR(200) NOT NULL DEFAULT '+',
    rounding VARCHAR(200),
    numeric_field VARCHAR(200),
    display_scale VARCHAR(200),
    exclusion_group_id INTEGER,
    manual_allowed INTEGER NOT NULL DEFAULT 0,
    mandatory INTEGER NOT NULL DEFAULT 0,
    statistical INTEGER NOT NULL DEFAULT 0,
    lookup_sequence_id INTEGER,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 行政区划: 行政区划字典（国/省/市/区四级，单表自引用树；address 四 FK 的引用目标）
CREATE TABLE IF NOT EXISTS regions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    parent_id INTEGER,
    level VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    FOREIGN KEY (parent_id) REFERENCES regions(id)
)

-- 销售员: 销售员字典——编码、姓名及可选的人员 / 账号绑定
CREATE TABLE IF NOT EXISTS salespersons (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    party_id INTEGER,
    user_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (party_id) REFERENCES parties(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
)

-- 销售员区域分配: 销售员与区域的分配关系（按生效日期区分，可设主区域）
CREATE TABLE IF NOT EXISTS salesperson_territory_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    salesperson_id INTEGER NOT NULL,
    territory_id INTEGER NOT NULL,
    effective_from DATETIME,
    effective_to DATETIME,
    is_primary INTEGER NOT NULL DEFAULT 0,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (salesperson_id) REFERENCES salespersons(id),
    FOREIGN KEY (territory_id) REFERENCES territories(id)
)

-- 销售订单: 销售订单头（行见 sales_order_line）
CREATE TABLE IF NOT EXISTS sales_orders (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no VARCHAR(200) NOT NULL,
    order_type_id INTEGER NOT NULL,
    order_date DATETIME NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    customer_account_id INTEGER NOT NULL,
    bill_to_account_id INTEGER,
    payer_account_id INTEGER,
    ship_to_party_id INTEGER,
    ship_to_address_id INTEGER,
    bill_to_address_id INTEGER,
    ship_to_address_text TEXT,
    bill_to_address_text TEXT,
    contact_party_id INTEGER,
    contact_name_text VARCHAR(200),
    contact_phone_text VARCHAR(200),
    salesperson_id INTEGER,
    territory_id INTEGER,
    org_id INTEGER NOT NULL,
    sales_org_id INTEGER NOT NULL,
    division_code VARCHAR(200),
    currency_id INTEGER NOT NULL,
    exchange_rate REAL NOT NULL DEFAULT 1,
    exchange_rate_type VARCHAR(200) NOT NULL DEFAULT 'spot',
    exchange_rate_date DATETIME,
    header_discount_percent REAL,
    header_surcharge_percent REAL,
    header_discount_amount REAL NOT NULL DEFAULT 0,
    header_surcharge_amount REAL NOT NULL DEFAULT 0,
    payment_term_id INTEGER,
    incoterm_code VARCHAR(200),
    customer_po_no VARCHAR(200),
    requested_date DATETIME,
    confirmed_date DATETIME,
    price_date DATETIME,
    pricing_status VARCHAR(200) NOT NULL DEFAULT 'pending',
    price_list_id INTEGER,
    pricing_procedure_id INTEGER,
    net_amount REAL NOT NULL DEFAULT 0,
    tax_amount REAL NOT NULL DEFAULT 0,
    gross_amount REAL NOT NULL DEFAULT 0,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    fulfillment_status VARCHAR(200) NOT NULL DEFAULT 'not_started',
    fulfillment_derived_at DATETIME,
    revision_no INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (order_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
    FOREIGN KEY (bill_to_account_id) REFERENCES customer_accounts(id),
    FOREIGN KEY (payer_account_id) REFERENCES customer_accounts(id),
    FOREIGN KEY (ship_to_party_id) REFERENCES parties(id),
    FOREIGN KEY (ship_to_address_id) REFERENCES addresses(id),
    FOREIGN KEY (bill_to_address_id) REFERENCES addresses(id),
    FOREIGN KEY (salesperson_id) REFERENCES salespersons(id),
    FOREIGN KEY (territory_id) REFERENCES territories(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (sales_org_id) REFERENCES orgs(id),
    FOREIGN KEY (currency_id) REFERENCES currencies(id),
    FOREIGN KEY (payment_term_id) REFERENCES payment_terms(id),
    FOREIGN KEY (price_list_id) REFERENCES rate_tables(id),
    FOREIGN KEY (pricing_procedure_id) REFERENCES calc_procedures(id)
)

-- 销售订单行: 销售订单行（物料 / 服务 / 文本 / 免费 / 退货行）
CREATE TABLE IF NOT EXISTS sales_order_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    line_no VARCHAR(200) NOT NULL,
    line_type_id INTEGER NOT NULL,
    item_id INTEGER,
    customer_item_code VARCHAR(200),
    description VARCHAR(200),
    qty REAL NOT NULL,
    uom_id INTEGER NOT NULL,
    unit_price REAL,
    net_amount REAL,
    header_discount_amount REAL NOT NULL DEFAULT 0,
    header_surcharge_amount REAL NOT NULL DEFAULT 0,
    ship_to_address_text VARCHAR(200),
    bill_to_address_text VARCHAR(200),
    tax_code_id INTEGER,
    tax_base_amount REAL,
    tax_rate_percent REAL,
    tax_amount REAL,
    gross_amount REAL,
    requested_date DATETIME,
    plant_location_id INTEGER,
    service_start_date DATETIME,
    service_end_date DATETIME,
    billing_method VARCHAR(200),
    required_resource_type VARCHAR(200),
    service_duration REAL,
    duration_type VARCHAR(200),
    configuration_id INTEGER,
    parent_line_id INTEGER,
    reference_line_id INTEGER,
    component_no VARCHAR(200),
    pricing_mode VARCHAR(200) NOT NULL DEFAULT 'standalone',
    price_source VARCHAR(200),
    price_trace TEXT,
    status VARCHAR(200) NOT NULL DEFAULT 'open',
    created_at DATETIME,
    updated_at DATETIME,
    fulfillment_status VARCHAR(200) NOT NULL DEFAULT 'not_started',
    fulfillment_derived_at DATETIME,
    FOREIGN KEY (order_id) REFERENCES sales_orders(id),
    FOREIGN KEY (line_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id),
    FOREIGN KEY (tax_code_id) REFERENCES tax_codes(id),
    FOREIGN KEY (plant_location_id) REFERENCES locations(id),
    FOREIGN KEY (parent_line_id) REFERENCES sales_order_lines(id),
    FOREIGN KEY (reference_line_id) REFERENCES sales_order_lines(id),
    FOREIGN KEY (configuration_id) REFERENCES configurations(id)
)

-- 订单计划行: 销售订单计划行（承诺交期 / 承诺量，一行多批次）
CREATE TABLE IF NOT EXISTS sales_order_schedules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    line_id INTEGER NOT NULL,
    plant_location_id INTEGER,
    schedule_no INTEGER NOT NULL,
    schedule_kind VARCHAR(200) NOT NULL,
    promised_date DATETIME NOT NULL,
    promised_qty REAL,
    billing_percent REAL,
    milestone_code VARCHAR(200),
    service_visit_no INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'planned',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (order_id) REFERENCES sales_orders(id),
    FOREIGN KEY (line_id) REFERENCES sales_order_lines(id),
    FOREIGN KEY (plant_location_id) REFERENCES locations(id)
)

-- 供应方式策略: 供应方式策略——物料组/物料在目标组织上的自制、采购或调拨基线
CREATE TABLE IF NOT EXISTS sourcing_mode_policies (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_group_id INTEGER NOT NULL,
    item_id INTEGER,
    org_id INTEGER NOT NULL,
    mode VARCHAR(200) NOT NULL,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (item_group_id) REFERENCES item_groups(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (org_id) REFERENCES orgs(id)
)

-- 供应来源规则: 供应来源规则——需求组织与物料到库存组织/仓库/供应商的路由规则
CREATE TABLE IF NOT EXISTS sourcing_rules (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    rule_usage VARCHAR(200) NOT NULL DEFAULT 'all',
    effectivity_start DATETIME NOT NULL,
    effectivity_end DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'draft',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 供应来源规则分配: 供应来源规则作用域分配——规则在全局/物料组/物料范围的生效声明
CREATE TABLE IF NOT EXISTS sourcing_rule_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    scope_type VARCHAR(200) NOT NULL,
    scope_ref_id INTEGER,
    dest_org_id INTEGER,
    dest_location_id INTEGER,
    specificity_rank INTEGER DEFAULT 60,
    seq INTEGER NOT NULL DEFAULT 1,
    effectivity_start DATETIME NOT NULL,
    effectivity_end DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (rule_id) REFERENCES sourcing_rules(id),
    FOREIGN KEY (dest_org_id) REFERENCES orgs(id),
    FOREIGN KEY (dest_location_id) REFERENCES locations(id)
)

-- 供应来源行: 供应来源行——规则下的一条来源候选（组织/位置/供应商/生产）
CREATE TABLE IF NOT EXISTS sourcing_rule_lines (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    seq INTEGER NOT NULL,
    source_type VARCHAR(200) NOT NULL,
    source_org_id INTEGER,
    source_location_id INTEGER,
    supplier_party_id INTEGER,
    rank INTEGER NOT NULL DEFAULT 1,
    allocation_pct REAL NOT NULL DEFAULT 100,
    blocked INTEGER NOT NULL DEFAULT 0,
    fixed INTEGER NOT NULL DEFAULT 0,
    effectivity_start DATETIME NOT NULL,
    effectivity_end DATETIME,
    note VARCHAR(200),
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (rule_id) REFERENCES sourcing_rules(id),
    FOREIGN KEY (source_org_id) REFERENCES orgs(id),
    FOREIGN KEY (source_location_id) REFERENCES locations(id),
    FOREIGN KEY (supplier_party_id) REFERENCES parties(id)
)

-- 税务分类: 税务分类字典（按客户 / 供应商 / 物料用途轴归组，决定默认税码）
CREATE TABLE IF NOT EXISTS tax_classifications (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    applicable_to VARCHAR(200) NOT NULL,
    country_id INTEGER,
    description TEXT,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    FOREIGN KEY (country_id) REFERENCES regions(id)
)

-- 税码: 税码字典（税种 / 方向 / 税务处理方式 / 税率取数方式 / 舍入方式）
CREATE TABLE IF NOT EXISTS tax_codes (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    country_id INTEGER,
    tax_type VARCHAR(200) NOT NULL,
    direction VARCHAR(200) NOT NULL DEFAULT 'both',
    tax_treatment VARCHAR(200) NOT NULL DEFAULT 'standard',
    rate_source VARCHAR(200) NOT NULL DEFAULT 'internal',
    rounding VARCHAR(200) NOT NULL DEFAULT 'round',
    exemption_reason TEXT,
    external_tax_system VARCHAR(200),
    description TEXT,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    created_at DATETIME,
    FOREIGN KEY (country_id) REFERENCES regions(id)
)

-- 税率: 税率（税码的生效期切片，半开区间 [effective_from, effective_to)）
CREATE TABLE IF NOT EXISTS tax_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tax_code_id INTEGER NOT NULL,
    effective_from DATETIME NOT NULL,
    effective_to DATETIME,
    rate_percent REAL NOT NULL,
    is_provisional INTEGER NOT NULL DEFAULT 0,
    legal_basis VARCHAR(200),
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (tax_code_id) REFERENCES tax_codes(id)
)

-- 销售区域: 销售区域树——按 parent_id 自引用分层，表达客户与订单的责任归属
CREATE TABLE IF NOT EXISTS territories (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    parent_id INTEGER,
    level INTEGER,
    owner_org_id INTEGER,
    territory_type VARCHAR(200) NOT NULL DEFAULT 'geographic',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (parent_id) REFERENCES territories(id),
    FOREIGN KEY (owner_org_id) REFERENCES orgs(id)
)

-- 客户区域分配: 客户与销售区域的分配关系（按生效日期区分，可设主区域与优先级）
CREATE TABLE IF NOT EXISTS territory_account_assignments (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_account_id INTEGER NOT NULL,
    territory_id INTEGER NOT NULL,
    effective_from DATETIME,
    effective_to DATETIME,
    is_primary INTEGER NOT NULL DEFAULT 0,
    priority INTEGER,
    assignment_source VARCHAR(200) NOT NULL DEFAULT 'manual',
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (customer_account_id) REFERENCES customer_accounts(id),
    FOREIGN KEY (territory_id) REFERENCES territories(id)
)

-- 测试对象: 用于测试的临时对象
CREATE TABLE IF NOT EXISTS test_objects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(200) UNIQUE NOT NULL,
    price REAL,
    active INTEGER DEFAULT 1,
    description TEXT
)

-- 测试表: 用于简单事务测试的表
CREATE TABLE IF NOT EXISTS test_table (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(200) DEFAULT 'pending'
)

-- 类型字典: 类型字典（单据类型 / 行类型的统一载体，按 scope_bo + level 判别）
CREATE TABLE IF NOT EXISTS type_definitions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    scope_bo VARCHAR(200) NOT NULL,
    level VARCHAR(200) NOT NULL,
    document_category VARCHAR(200) DEFAULT 'standard',
    default_type_id INTEGER,
    number_sequence_id INTEGER,
    line_category VARCHAR(200) DEFAULT 'material',
    delivery_relevant INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (default_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (number_sequence_id) REFERENCES number_sequences(id)
)

-- 计量单位: 计量单位主数据（基础最小集）
CREATE TABLE IF NOT EXISTS uoms (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    uom_group_id INTEGER NOT NULL,
    decimal_places INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (uom_group_id) REFERENCES uom_groups(id)
)

-- 计量单位组换算: 计量单位组换算（组内单位与组基本单位的标准换算率）
CREATE TABLE IF NOT EXISTS uom_conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uom_group_id INTEGER NOT NULL,
    uom_id INTEGER NOT NULL,
    factor REAL NOT NULL,
    description TEXT,
    FOREIGN KEY (uom_group_id) REFERENCES uom_groups(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id)
)

-- 计量单位组: 计量单位组（类层主对象，定义组内换算基准）
CREATE TABLE IF NOT EXISTS uom_groups (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    base_uom_id INTEGER,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    FOREIGN KEY (base_uom_id) REFERENCES uoms(id)
)

-- 条件更新组: 条件更新组（累计用量组）——累计用量的上限配置
CREATE TABLE IF NOT EXISTS usage_groups (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    max_amount REAL,
    max_quantity REAL,
    max_documents INTEGER,
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)

-- 用户: 系统用户，支持本地认证和SSO集成
CREATE TABLE IF NOT EXISTS users (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username VARCHAR(200) UNIQUE NOT NULL,
    email VARCHAR(200) NOT NULL,
    party_id INTEGER,
    password_hash VARCHAR(200),
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(200) DEFAULT 'active',
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

-- 供应商档案: 供应商档案（我方与某 party 的供应商关系侧商务属性；挂在 party_relation(role='vendor') 之上 1:1）
CREATE TABLE IF NOT EXISTS vendor_accounts (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    relation_id INTEGER UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    tax_classification_id INTEGER,
    created_at DATETIME,
    FOREIGN KEY (tax_classification_id) REFERENCES tax_classifications(id)
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
    visibility VARCHAR(200) NOT NULL DEFAULT 'private',
    owner_id INTEGER,
    is_active INTEGER DEFAULT 1
)

-- 产品版本: 产品版本是产品线的软件版本，如 v1.0、2024-Q4 等。每个版本包含独立的领域模型数据。
CREATE TABLE IF NOT EXISTS versions (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    visibility VARCHAR(200) DEFAULT 'draft',
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_current INTEGER DEFAULT 0,
    owner_id INTEGER,
    FOREIGN KEY (product_id) REFERENCES products(id)
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
    FOREIGN KEY (version_id) REFERENCES versions(id)
)

-- 子领域: 子领域是从属于领域的二级业务分类。
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
    FOREIGN KEY (version_id) REFERENCES versions(id),
    FOREIGN KEY (domain_id) REFERENCES domains(id)
)

-- 服务模块: 服务模块是从属于子领域的三级业务分类。
CREATE TABLE IF NOT EXISTS service_modules (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    domain_id INTEGER,
    sub_domain_id INTEGER NOT NULL,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
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
    domain_id INTEGER,
    sub_domain_id INTEGER,
    service_module_id INTEGER,
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
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
    source_domain_id INTEGER,
    source_sub_domain_id INTEGER,
    source_service_module_id INTEGER,
    target_domain_id INTEGER,
    target_sub_domain_id INTEGER,
    target_service_module_id INTEGER,
    source_bo_id INTEGER NOT NULL,
    target_bo_id INTEGER NOT NULL,
    source_code VARCHAR(200),
    target_code VARCHAR(200),
    code VARCHAR(200),
    relation_code VARCHAR(200) DEFAULT '',
    relation_type VARCHAR(200),
    relation_direction VARCHAR(200),
    relation_desc TEXT,
    FOREIGN KEY (version_id) REFERENCES versions(id),
    FOREIGN KEY (source_bo_id) REFERENCES business_objects(id),
    FOREIGN KEY (target_bo_id) REFERENCES business_objects(id)
)

-- Indexes for 地址
CREATE UNIQUE INDEX IF NOT EXISTS idx_address_code ON addresses(code)
CREATE INDEX IF NOT EXISTS idx_address_postal_code ON addresses(postal_code)
CREATE INDEX IF NOT EXISTS idx_address_status ON addresses(status)
CREATE INDEX IF NOT EXISTS idx_addresses_formatted_address ON addresses(formatted_address)

-- Indexes for 追溯调整
CREATE INDEX IF NOT EXISTS idx_adjustment_original_result ON adjustments(original_result_id)
CREATE INDEX IF NOT EXISTS idx_adjustment_type ON adjustments(adjustment_type)
CREATE INDEX IF NOT EXISTS idx_adjustments_created_at ON adjustments(created_at)

-- Indexes for 分摊结果
CREATE UNIQUE INDEX IF NOT EXISTS idx_allocation_result_code ON allocation_results(code)
CREATE INDEX IF NOT EXISTS idx_allocation_result_host ON allocation_results(document_type, document_id)
CREATE INDEX IF NOT EXISTS idx_allocation_result_parent ON allocation_results(parent_id)
CREATE INDEX IF NOT EXISTS idx_allocation_result_rule ON allocation_results(allocation_rule_id)
CREATE INDEX IF NOT EXISTS idx_allocation_results_created_at ON allocation_results(created_at)

-- Indexes for 分摊规则
CREATE UNIQUE INDEX IF NOT EXISTS idx_allocation_rule_code ON allocation_rules(code)
CREATE INDEX IF NOT EXISTS idx_allocation_rules_name ON allocation_rules(name)

-- Indexes for 备注信息
CREATE INDEX IF NOT EXISTS idx_annotations_target_type ON annotations(target_type)

-- Indexes for 属性定义
CREATE UNIQUE INDEX IF NOT EXISTS idx_attribute_definition_tenant_code ON attribute_definitions(tenant_id, code)
CREATE INDEX IF NOT EXISTS idx_attribute_definition_tenant_status ON attribute_definitions(tenant_id, status)
CREATE INDEX IF NOT EXISTS idx_attribute_definitions_name ON attribute_definitions(name)

-- Indexes for 属性适用范围
CREATE UNIQUE INDEX IF NOT EXISTS idx_attribute_scope_tenant_attr_scope ON attribute_scopes(tenant_id, attribute_id, scope_type, scope_ref)
CREATE INDEX IF NOT EXISTS idx_attribute_scope_lookup ON attribute_scopes(tenant_id, scope_type, scope_ref)

-- Indexes for 审计日志
CREATE INDEX IF NOT EXISTS idx_audit_category ON audit_logs(log_category)
CREATE INDEX IF NOT EXISTS idx_audit_category_action_time ON audit_logs(log_category, action, created_at)
CREATE INDEX IF NOT EXISTS idx_audit_level ON audit_logs(log_level)
CREATE INDEX IF NOT EXISTS idx_audit_object ON audit_logs(object_type, object_id)
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id)
CREATE INDEX IF NOT EXISTS idx_audit_time ON audit_logs(created_at)
CREATE INDEX IF NOT EXISTS idx_audit_trace ON audit_logs(trace_id)
CREATE INDEX IF NOT EXISTS idx_audit_txn ON audit_logs(transaction_id)
CREATE INDEX IF NOT EXISTS idx_audit_change_set ON audit_logs(change_set_id)
CREATE INDEX IF NOT EXISTS idx_audit_status ON audit_logs(status)
CREATE INDEX IF NOT EXISTS idx_audit_tool_call ON audit_logs(tool_call_id)
CREATE INDEX IF NOT EXISTS idx_audit_parent ON audit_logs(parent_object_type, parent_object_id)

-- Indexes for 定价明细
CREATE INDEX IF NOT EXISTS idx_calc_detail_result_seq ON calc_details(result_id, seq)
CREATE INDEX IF NOT EXISTS idx_calc_detail_element ON calc_details(element_type)
CREATE INDEX IF NOT EXISTS idx_calc_detail_skipped ON calc_details(skipped)

-- Indexes for 定价过程
CREATE UNIQUE INDEX IF NOT EXISTS idx_calc_procedure_code ON calc_procedures(code)
CREATE INDEX IF NOT EXISTS idx_calc_procedure_type ON calc_procedures(procedure_type)
CREATE INDEX IF NOT EXISTS idx_calc_procedure_semantic ON calc_procedures(result_semantic)
CREATE INDEX IF NOT EXISTS idx_calc_procedures_name ON calc_procedures(name)

-- Indexes for 定价过程步骤
CREATE INDEX IF NOT EXISTS idx_calc_procedure_step_proc_seq ON calc_procedure_steps(calc_procedure_id, seq)
CREATE INDEX IF NOT EXISTS idx_calc_procedure_step_element ON calc_procedure_steps(element_type)

-- Indexes for 定价结果
CREATE INDEX IF NOT EXISTS idx_calc_results_external_rate_source_id ON calc_results(external_rate_source_id)
CREATE INDEX IF NOT EXISTS idx_calc_results_pricing_period_id ON calc_results(pricing_period_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_calc_result_code ON calc_results(code)
CREATE INDEX IF NOT EXISTS idx_calc_result_doc ON calc_results(document_type, document_id, document_line_id)
CREATE INDEX IF NOT EXISTS idx_calc_result_process ON calc_results(process_code)
CREATE INDEX IF NOT EXISTS idx_calc_result_status ON calc_results(status)
CREATE INDEX IF NOT EXISTS idx_calc_results_sequence ON calc_results(sequence)

-- Indexes for 作业日历
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_code ON calendars(code)
CREATE INDEX IF NOT EXISTS idx_calendar_parent_id ON calendars(parent_calendar_id)
CREATE INDEX IF NOT EXISTS idx_calendar_country_id ON calendars(country_id)
CREATE INDEX IF NOT EXISTS idx_calendar_status ON calendars(status)
CREATE INDEX IF NOT EXISTS idx_calendars_name ON calendars(name)

-- Indexes for 日历例外日
CREATE INDEX IF NOT EXISTS idx_calendar_days_calendar_id ON calendar_days(calendar_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_calendar_day_unique ON calendar_days(calendar_id, date)
CREATE INDEX IF NOT EXISTS idx_calendar_day_date ON calendar_days(date)
CREATE INDEX IF NOT EXISTS idx_calendar_day_type ON calendar_days(day_type)

-- Indexes for 变更事件
CREATE INDEX IF NOT EXISTS idx_change_events_object_type ON change_events(object_type)
CREATE INDEX IF NOT EXISTS idx_change_events_object_id ON change_events(object_id)
CREATE INDEX IF NOT EXISTS idx_change_events_status ON change_events(status)
CREATE INDEX IF NOT EXISTS idx_change_events_created_at ON change_events(created_at)
CREATE INDEX IF NOT EXISTS idx_change_events_audit_log ON change_events(audit_log_id)

-- Indexes for 变更申请
CREATE INDEX IF NOT EXISTS idx_cr_target ON change_requests(target_object_type, target_object_id, status)
CREATE INDEX IF NOT EXISTS idx_cr_status ON change_requests(status)

-- Indexes for 变更申请行
CREATE UNIQUE INDEX IF NOT EXISTS uq_crl_cr_line_field ON change_request_lines(change_request_id, line_key, field_name)

-- Indexes for 变更订阅
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_user_id ON change_subscriptions(user_id)
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_object_type ON change_subscriptions(object_type)
CREATE INDEX IF NOT EXISTS idx_change_subscriptions_enabled ON change_subscriptions(enabled)

-- Indexes for 配置实例
CREATE INDEX IF NOT EXISTS idx_configuration_structure_hash ON configurations(structure_id, config_hash)
CREATE INDEX IF NOT EXISTS idx_configuration_model_status ON configurations(model_item_id, status)
CREATE INDEX IF NOT EXISTS idx_configurations_solved_at ON configurations(solved_at)

-- Indexes for 配置组件
CREATE INDEX IF NOT EXISTS idx_configuration_components_configuration_id ON configuration_components(configuration_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_configuration_component_key ON configuration_components(configuration_id, component_key)
CREATE INDEX IF NOT EXISTS idx_configuration_component_line ON configuration_components(structure_line_id)
CREATE INDEX IF NOT EXISTS idx_configuration_component_item ON configuration_components(component_item_id)
CREATE INDEX IF NOT EXISTS idx_configuration_components_component_key ON configuration_components(component_key)
CREATE INDEX IF NOT EXISTS idx_configuration_components_seq ON configuration_components(seq)

-- Indexes for 配置特征值
CREATE INDEX IF NOT EXISTS idx_configuration_values_configuration_id ON configuration_values(configuration_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_configuration_value_code ON configuration_values(configuration_id, attribute_code, seq)
CREATE INDEX IF NOT EXISTS idx_configuration_value_attribute ON configuration_values(attribute_code)

-- Indexes for 配置规则
CREATE INDEX IF NOT EXISTS idx_config_rule_structure_status ON config_rules(structure_id, status)
CREATE INDEX IF NOT EXISTS idx_config_rule_structure_priority ON config_rules(structure_id, priority)

-- Indexes for 配置规则条件项
CREATE UNIQUE INDEX IF NOT EXISTS uidx_config_rule_term_seq ON config_rule_terms(rule_id, seq)
CREATE INDEX IF NOT EXISTS idx_config_rule_term_line ON config_rule_terms(target_line_id)
CREATE INDEX IF NOT EXISTS idx_config_rule_term_attribute ON config_rule_terms(attribute_code)

-- Indexes for 控制参数定义
CREATE INDEX IF NOT EXISTS idx_control_parameter_defs_enum_type_id ON control_parameter_defs(enum_type_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_control_parameter_def_code ON control_parameter_defs(code)
CREATE INDEX IF NOT EXISTS idx_control_parameter_def_domain ON control_parameter_defs(domain)
CREATE INDEX IF NOT EXISTS idx_control_parameter_defs_name ON control_parameter_defs(name)

-- Indexes for 控制参数取值
CREATE INDEX IF NOT EXISTS idx_control_parameter_values_org_id ON control_parameter_values(org_id)
CREATE INDEX IF NOT EXISTS idx_control_parameter_values_item_group_id ON control_parameter_values(item_group_id)
CREATE INDEX IF NOT EXISTS idx_control_parameter_value_param ON control_parameter_values(control_parameter_id)
CREATE INDEX IF NOT EXISTS idx_control_parameter_value_rank ON control_parameter_values(control_parameter_id, specificity_rank)

-- Indexes for 累计用量
CREATE UNIQUE INDEX IF NOT EXISTS idx_cumulative_usage_rate_record ON cumulative_usages(rate_record_id)
CREATE INDEX IF NOT EXISTS idx_cumulative_usage_group ON cumulative_usages(usage_group_id)

-- Indexes for 币种
CREATE UNIQUE INDEX IF NOT EXISTS idx_currency_code ON currencies(code)
CREATE INDEX IF NOT EXISTS idx_currencies_name ON currencies(name)

-- Indexes for 汇率
CREATE UNIQUE INDEX IF NOT EXISTS idx_currency_rate_key ON currency_rates(rate_type, currency_id, to_currency_id, valid_from)
CREATE INDEX IF NOT EXISTS idx_currency_rate_from ON currency_rates(currency_id)
CREATE INDEX IF NOT EXISTS idx_currency_rate_to ON currency_rates(to_currency_id)

-- Indexes for 客户档案
CREATE INDEX IF NOT EXISTS idx_customer_accounts_tax_classification_id ON customer_accounts(tax_classification_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_customer_account_relation_unique ON customer_accounts(relation_id)
CREATE INDEX IF NOT EXISTS idx_customer_accounts_name ON customer_accounts(name)

-- Indexes for 客户销售员分配
CREATE UNIQUE INDEX IF NOT EXISTS uidx_customer_salesperson_assign ON customer_salesperson_assignments(customer_account_id, sales_org_id, salesperson_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_customer_salesperson_primary ON customer_salesperson_assignments(customer_account_id, sales_org_id) WHERE is_primary = 1 AND status = 'active'
CREATE UNIQUE INDEX IF NOT EXISTS uidx_customer_salesperson_primary_all_org ON customer_salesperson_assignments(customer_account_id) WHERE sales_org_id IS NULL AND is_primary = 1 AND status = 'active'
CREATE INDEX IF NOT EXISTS idx_customer_salesperson_salesperson ON customer_salesperson_assignments(salesperson_id)

-- Indexes for 客户销售组织
CREATE INDEX IF NOT EXISTS idx_customer_sales_orgs_customer_account_id ON customer_sales_orgs(customer_account_id)
CREATE INDEX IF NOT EXISTS idx_customer_sales_orgs_tax_classification_id ON customer_sales_orgs(tax_classification_id)
CREATE INDEX IF NOT EXISTS idx_customer_sales_orgs_payment_term_id ON customer_sales_orgs(payment_term_id)
CREATE INDEX IF NOT EXISTS idx_customer_sales_orgs_currency_id ON customer_sales_orgs(currency_id)
CREATE INDEX IF NOT EXISTS idx_customer_sales_orgs_rate_table_id ON customer_sales_orgs(rate_table_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_customer_sales_org_account_org ON customer_sales_orgs(customer_account_id, sales_org_id)
CREATE INDEX IF NOT EXISTS idx_customer_sales_org_org ON customer_sales_orgs(sales_org_id)

-- Indexes for 产品组
CREATE UNIQUE INDEX IF NOT EXISTS uidx_division_code ON divisions(code)
CREATE INDEX IF NOT EXISTS idx_division_status ON divisions(status)
CREATE INDEX IF NOT EXISTS idx_divisions_name ON divisions(name)

-- Indexes for 员工数据权限范围
CREATE UNIQUE INDEX IF NOT EXISTS idx_emp_scope_code ON employee_data_scopes(code)

-- Indexes for 枚举类型
CREATE INDEX IF NOT EXISTS idx_enum_types_name ON enum_types(name)
CREATE INDEX IF NOT EXISTS idx_enum_types_category ON enum_types(category)

-- Indexes for 枚举值
CREATE UNIQUE INDEX IF NOT EXISTS uidx_enum_values_type_code ON enum_values(enum_type_id, code)
CREATE INDEX IF NOT EXISTS idx_enum_values_enum_type_id ON enum_values(enum_type_id)
CREATE INDEX IF NOT EXISTS idx_enum_values_name ON enum_values(name)

-- Indexes for 排斥组
CREATE UNIQUE INDEX IF NOT EXISTS idx_exclusion_group_code ON exclusion_groups(code)
CREATE INDEX IF NOT EXISTS idx_exclusion_groups_name ON exclusion_groups(name)

-- Indexes for 外部价格源
CREATE UNIQUE INDEX IF NOT EXISTS idx_external_rate_source_code ON external_rate_sources(code)
CREATE INDEX IF NOT EXISTS idx_external_rate_source_calendar ON external_rate_sources(calendar_id)
CREATE INDEX IF NOT EXISTS idx_external_rate_sources_name ON external_rate_sources(name)

-- Indexes for 因子目录
CREATE UNIQUE INDEX IF NOT EXISTS idx_factor_catalog_obj_field ON factor_catalogs(object_type, field_id)
CREATE INDEX IF NOT EXISTS idx_factor_catalog_source ON factor_catalogs(source_type)
CREATE INDEX IF NOT EXISTS idx_factor_catalog_price_rel ON factor_catalogs(is_price_relevant)

-- Indexes for 过滤变体
CREATE INDEX IF NOT EXISTS idx_filter_variants_user_object ON filter_variants(user_id, object_type)
CREATE INDEX IF NOT EXISTS idx_filter_variants_shared ON filter_variants(is_shared, object_type)
CREATE INDEX IF NOT EXISTS idx_filter_variants_name ON filter_variants(name)

-- Indexes for 用户组数据权限
CREATE UNIQUE INDEX IF NOT EXISTS idx_group_data_perm_unique ON group_data_permissions(group_id, resource_type, resource_id)
CREATE INDEX IF NOT EXISTS idx_group_data_perm_group ON group_data_permissions(group_id)

-- Indexes for 国际贸易术语
CREATE UNIQUE INDEX IF NOT EXISTS idx_incoterm_code_edition ON incoterms(code, edition)
CREATE INDEX IF NOT EXISTS idx_incoterms_name ON incoterms(name)

-- Indexes for 物料
CREATE UNIQUE INDEX IF NOT EXISTS idx_item_code ON items(code)
CREATE INDEX IF NOT EXISTS idx_item_group ON items(item_group_id)
CREATE INDEX IF NOT EXISTS idx_item_type ON items(item_type)
CREATE INDEX IF NOT EXISTS idx_item_status ON items(status)
CREATE INDEX IF NOT EXISTS idx_item_base_uom ON items(base_uom)
CREATE INDEX IF NOT EXISTS idx_item_sales_uom ON items(sales_uom)
CREATE INDEX IF NOT EXISTS idx_item_barcode ON items(barcode)
CREATE INDEX IF NOT EXISTS idx_item_tax_classification ON items(tax_classification_id)
CREATE INDEX IF NOT EXISTS idx_items_name ON items(name)

-- Indexes for 物料分层参数值
CREATE INDEX IF NOT EXISTS idx_item_attribute_values_item_id ON item_attribute_values(item_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_item_attr_l0 ON item_attribute_values(item_id, attr_code) WHERE org_id IS NULL
CREATE UNIQUE INDEX IF NOT EXISTS uidx_item_attr_l2 ON item_attribute_values(item_id, attr_code, org_id) WHERE org_id IS NOT NULL
CREATE INDEX IF NOT EXISTS idx_item_attr_org ON item_attribute_values(org_id)

-- Indexes for 物料组
CREATE UNIQUE INDEX IF NOT EXISTS idx_item_group_code ON item_groups(code)
CREATE INDEX IF NOT EXISTS idx_item_group_parent ON item_groups(parent_id)
CREATE INDEX IF NOT EXISTS idx_item_group_status ON item_groups(status)
CREATE INDEX IF NOT EXISTS idx_item_groups_name ON item_groups(name)

-- Indexes for 物料结构
CREATE INDEX IF NOT EXISTS idx_item_structures_item_id ON item_structures(item_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_item_structure_version ON item_structures(item_id, usage, alternative_no, revision)
CREATE INDEX IF NOT EXISTS idx_item_structure_item_status ON item_structures(item_id, usage, status)

-- Indexes for 模型特征声明
CREATE UNIQUE INDEX IF NOT EXISTS uidx_item_structure_attribute_code ON item_structure_attributes(structure_id, attribute_code)
CREATE INDEX IF NOT EXISTS idx_item_structure_attribute_ref ON item_structure_attributes(attribute_code)
CREATE INDEX IF NOT EXISTS idx_item_structure_attributes_seq ON item_structure_attributes(seq)

-- Indexes for 物料结构行
CREATE UNIQUE INDEX IF NOT EXISTS uidx_item_structure_line_no ON item_structure_lines(structure_id, line_no)
CREATE INDEX IF NOT EXISTS idx_item_structure_line_component ON item_structure_lines(component_item_id)

-- Indexes for 物料单位换算
CREATE UNIQUE INDEX IF NOT EXISTS idx_item_uom_conv_unique ON item_uom_conversions(item_id, uom_id)
CREATE INDEX IF NOT EXISTS idx_item_uom_conv_item ON item_uom_conversions(item_id)
CREATE INDEX IF NOT EXISTS idx_item_uom_conv_uom ON item_uom_conversions(uom_id)
CREATE INDEX IF NOT EXISTS idx_item_uom_conversions_id ON item_uom_conversions(id)

-- Indexes for 物料外部标识
CREATE UNIQUE INDEX IF NOT EXISTS idx_item_xref_unique ON item_xrefs(item_id, partner_type, partner_id)
CREATE INDEX IF NOT EXISTS idx_item_xref_item ON item_xrefs(item_id)
CREATE INDEX IF NOT EXISTS idx_item_xref_partner ON item_xrefs(partner_type, partner_id)
CREATE INDEX IF NOT EXISTS idx_item_xref_part_no ON item_xrefs(part_no)

-- Indexes for 匹配键表
CREATE UNIQUE INDEX IF NOT EXISTS idx_key_schema_code ON key_schemas(code)
CREATE INDEX IF NOT EXISTS idx_key_schemas_name ON key_schemas(name)

-- Indexes for 销售行类型确定
CREATE INDEX IF NOT EXISTS idx_line_type_assignments_item_group_id ON line_type_assignments(item_group_id)
CREATE INDEX IF NOT EXISTS idx_line_type_assignment_doc_type ON line_type_assignments(document_type_id)
CREATE INDEX IF NOT EXISTS idx_line_type_assignment_rank ON line_type_assignments(document_type_id, specificity_rank)

-- Indexes for 位置
CREATE INDEX IF NOT EXISTS idx_locations_address_id ON locations(address_id)
CREATE INDEX IF NOT EXISTS idx_locations_calendar_id ON locations(calendar_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_location_code ON locations(code)
CREATE INDEX IF NOT EXISTS idx_location_parent ON locations(parent_id)
CREATE INDEX IF NOT EXISTS idx_location_type ON locations(location_type)
CREATE INDEX IF NOT EXISTS idx_location_status ON locations(status)
CREATE INDEX IF NOT EXISTS idx_locations_name ON locations(name)

-- Indexes for 查找序列
CREATE UNIQUE INDEX IF NOT EXISTS idx_lookup_sequence_code ON lookup_sequences(code)
CREATE INDEX IF NOT EXISTS idx_lookup_sequences_name ON lookup_sequences(name)

-- Indexes for 编号序列
CREATE UNIQUE INDEX IF NOT EXISTS idx_number_sequence_code ON number_sequences(code)
CREATE INDEX IF NOT EXISTS idx_number_sequences_name ON number_sequences(name)

-- Indexes for 组织
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_code ON orgs(code)
CREATE INDEX IF NOT EXISTS idx_org_parent ON orgs(parent_id)
CREATE INDEX IF NOT EXISTS idx_org_type ON orgs(org_type)
CREATE INDEX IF NOT EXISTS idx_org_status ON orgs(status)
CREATE INDEX IF NOT EXISTS idx_orgs_name ON orgs(name)

-- Indexes for 组织数据权限
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_data_perm_unique ON org_data_permissions(org_id, resource_type, resource_id)
CREATE INDEX IF NOT EXISTS idx_org_data_perm_org ON org_data_permissions(org_id)

-- Indexes for 组织成员
CREATE UNIQUE INDEX IF NOT EXISTS idx_org_member_unique ON org_members(user_id, org_id)
CREATE INDEX IF NOT EXISTS idx_org_member_org ON org_members(org_id)
CREATE INDEX IF NOT EXISTS idx_org_member_user ON org_members(user_id)

-- Indexes for 身份主体
CREATE UNIQUE INDEX IF NOT EXISTS idx_party_org_unique ON parties(org_id) WHERE source = 'org'
CREATE INDEX IF NOT EXISTS idx_party_source ON parties(source)
CREATE INDEX IF NOT EXISTS idx_party_status ON parties(status)
CREATE INDEX IF NOT EXISTS idx_parties_name ON parties(name)

-- Indexes for 往来单位地址
CREATE INDEX IF NOT EXISTS idx_party_addresses_party_id ON party_addresses(party_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_party_address_party_addr_role ON party_addresses(party_id, address_id, role)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_party_address_default ON party_addresses(party_id, role) WHERE is_default = 1 AND status = 'active'
CREATE INDEX IF NOT EXISTS idx_party_address_address ON party_addresses(address_id)
CREATE INDEX IF NOT EXISTS idx_party_address_status ON party_addresses(status)

-- Indexes for 业务伙伴属性值
CREATE INDEX IF NOT EXISTS idx_party_attribute_values_party_id ON party_attribute_values(party_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_party_attr_value ON party_attribute_values(tenant_id, party_id, attribute_id, seq)
CREATE INDEX IF NOT EXISTS idx_party_attr_value_attr ON party_attribute_values(attribute_id)

-- Indexes for 业务伙伴组
CREATE UNIQUE INDEX IF NOT EXISTS idx_party_group_code ON party_groups(code)
CREATE INDEX IF NOT EXISTS idx_party_group_parent ON party_groups(parent_id)
CREATE INDEX IF NOT EXISTS idx_party_group_status ON party_groups(status)
CREATE INDEX IF NOT EXISTS idx_party_groups_name ON party_groups(name)

-- Indexes for 业务伙伴关系
CREATE UNIQUE INDEX IF NOT EXISTS idx_party_relation_unique ON party_relations(party1_id, party2_id, role, le_org_id) WHERE le_org_id IS NOT NULL
CREATE INDEX IF NOT EXISTS idx_party_relation_party1 ON party_relations(party1_id)
CREATE INDEX IF NOT EXISTS idx_party_relation_party2 ON party_relations(party2_id)
CREATE INDEX IF NOT EXISTS idx_party_relation_le_org_id ON party_relations(le_org_id)
CREATE INDEX IF NOT EXISTS idx_party_relation_group_id ON party_relations(group_id)
CREATE INDEX IF NOT EXISTS idx_party_relation_status ON party_relations(status)

-- Indexes for 税务登记
CREATE UNIQUE INDEX IF NOT EXISTS idx_party_tax_reg_unique ON party_tax_registrations(party_id, country_id, tax_type, registration_number)
CREATE INDEX IF NOT EXISTS idx_party_tax_reg_party ON party_tax_registrations(party_id)
CREATE INDEX IF NOT EXISTS idx_party_tax_registrations_is_primary ON party_tax_registrations(is_primary)

-- Indexes for 付款条件
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_term_code ON payment_terms(code)
CREATE INDEX IF NOT EXISTS idx_payment_terms_name ON payment_terms(name)

-- Indexes for 付款条件分期
CREATE UNIQUE INDEX IF NOT EXISTS idx_payment_term_line_seq ON payment_term_lines(payment_term_id, seq)
CREATE INDEX IF NOT EXISTS idx_payment_term_line_term ON payment_term_lines(payment_term_id)

-- Indexes for 权限集
CREATE UNIQUE INDEX IF NOT EXISTS idx_permission_set_code ON permission_sets(code)

-- Indexes for 权限集权限
CREATE INDEX IF NOT EXISTS idx_permission_set_permissions_permission_set_id ON permission_set_permissions(permission_set_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_permission_set_permission_unique ON permission_set_permissions(permission_set_id, permission_id)

-- Indexes for 个人档案
CREATE UNIQUE INDEX IF NOT EXISTS idx_person_profile_party_unique ON person_profiles(party_id)

-- Indexes for 定价确定规则
CREATE INDEX IF NOT EXISTS idx_pricing_determinations_rate_table_id ON pricing_determinations(rate_table_id)
CREATE INDEX IF NOT EXISTS idx_pricing_determinations_calc_procedure_id ON pricing_determinations(calc_procedure_id)
CREATE INDEX IF NOT EXISTS idx_pricing_determinations_lookup_sequence_id ON pricing_determinations(lookup_sequence_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_pd_code ON pricing_determinations(code)
CREATE INDEX IF NOT EXISTS idx_pd_lookup ON pricing_determinations(sales_org_id, order_type_id, status, seq)
CREATE UNIQUE INDEX IF NOT EXISTS uq_pd_dimension ON pricing_determinations(COALESCE(sales_org_id, 0), COALESCE(order_type_id, 0), COALESCE(valid_from, '')) WHERE 1 = 1
CREATE INDEX IF NOT EXISTS idx_pricing_determinations_name ON pricing_determinations(name)

-- Indexes for 计价期
CREATE UNIQUE INDEX IF NOT EXISTS idx_pricing_period_code ON pricing_periods(code)
CREATE INDEX IF NOT EXISTS idx_pricing_periods_name ON pricing_periods(name)

-- Indexes for 费率记录
CREATE UNIQUE INDEX IF NOT EXISTS idx_rate_record_code ON rate_records(code)
CREATE INDEX IF NOT EXISTS idx_rate_record_table ON rate_records(rate_table_id)
CREATE INDEX IF NOT EXISTS idx_rate_record_schema ON rate_records(key_schema_id)
CREATE INDEX IF NOT EXISTS idx_rate_record_type ON rate_records(rate_type_id)
CREATE INDEX IF NOT EXISTS idx_rate_record_lookup ON rate_records(rate_table_id, key_schema_id, priority)
CREATE INDEX IF NOT EXISTS idx_rate_record_status ON rate_records(status)

-- Indexes for 费率表
CREATE UNIQUE INDEX IF NOT EXISTS idx_rate_table_code ON rate_tables(code)
CREATE INDEX IF NOT EXISTS idx_rate_table_status ON rate_tables(status)
CREATE INDEX IF NOT EXISTS idx_rate_table_currency ON rate_tables(currency)
CREATE INDEX IF NOT EXISTS idx_rate_tables_name ON rate_tables(name)

-- Indexes for 费率类型
CREATE UNIQUE INDEX IF NOT EXISTS idx_rate_type_code ON rate_types(code)
CREATE INDEX IF NOT EXISTS idx_rate_type_class ON rate_types(rate_class)
CREATE INDEX IF NOT EXISTS idx_rate_types_name ON rate_types(name)

-- Indexes for 行政区划
CREATE UNIQUE INDEX IF NOT EXISTS idx_region_code ON regions(code)
CREATE INDEX IF NOT EXISTS idx_region_parent_id ON regions(parent_id)
CREATE INDEX IF NOT EXISTS idx_region_level ON regions(level)
CREATE INDEX IF NOT EXISTS idx_region_status ON regions(status)
CREATE INDEX IF NOT EXISTS idx_regions_name ON regions(name)

-- Indexes for 销售员
CREATE INDEX IF NOT EXISTS idx_salespersons_party_id ON salespersons(party_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_salesperson_code ON salespersons(code)
CREATE INDEX IF NOT EXISTS idx_salesperson_user ON salespersons(user_id)
CREATE INDEX IF NOT EXISTS idx_salespersons_name ON salespersons(name)

-- Indexes for 销售员区域分配
CREATE INDEX IF NOT EXISTS idx_salesperson_territory_assignments_salesperson_id ON salesperson_territory_assignments(salesperson_id)
CREATE INDEX IF NOT EXISTS idx_salesperson_territory_assignments_territory_id ON salesperson_territory_assignments(territory_id)
CREATE UNIQUE INDEX IF NOT EXISTS uq_sta_triple ON salesperson_territory_assignments(salesperson_id, territory_id, effective_from)
CREATE UNIQUE INDEX IF NOT EXISTS uq_sta_primary ON salesperson_territory_assignments(salesperson_id, effective_from) WHERE is_primary = 1

-- Indexes for 销售订单
CREATE INDEX IF NOT EXISTS idx_sales_orders_customer_account_id ON sales_orders(customer_account_id)
CREATE INDEX IF NOT EXISTS idx_sales_orders_salesperson_id ON sales_orders(salesperson_id)
CREATE INDEX IF NOT EXISTS idx_sales_orders_org_id ON sales_orders(org_id)
CREATE INDEX IF NOT EXISTS idx_sales_orders_currency_id ON sales_orders(currency_id)
CREATE INDEX IF NOT EXISTS idx_sales_orders_payment_term_id ON sales_orders(payment_term_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_sales_order_no ON sales_orders(order_no)
CREATE INDEX IF NOT EXISTS idx_sales_order_customer_date ON sales_orders(customer_account_id, order_date)
CREATE INDEX IF NOT EXISTS idx_sales_order_sales_org_date ON sales_orders(sales_org_id, order_date)
CREATE INDEX IF NOT EXISTS idx_sales_order_status ON sales_orders(status)
CREATE INDEX IF NOT EXISTS idx_sales_order_type ON sales_orders(order_type_id)
CREATE INDEX IF NOT EXISTS idx_sales_order_territory ON sales_orders(territory_id)

-- Indexes for 销售订单行
CREATE INDEX IF NOT EXISTS idx_sales_order_lines_uom_id ON sales_order_lines(uom_id)
CREATE INDEX IF NOT EXISTS idx_sales_order_lines_tax_code_id ON sales_order_lines(tax_code_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_sales_order_line_no ON sales_order_lines(order_id, line_no)
CREATE INDEX IF NOT EXISTS idx_sales_order_line_item ON sales_order_lines(item_id)
CREATE INDEX IF NOT EXISTS idx_sales_order_line_order_status ON sales_order_lines(order_id, status)
CREATE INDEX IF NOT EXISTS idx_sales_order_line_parent ON sales_order_lines(parent_line_id)
CREATE INDEX IF NOT EXISTS idx_sales_order_line_reference ON sales_order_lines(reference_line_id)
CREATE INDEX IF NOT EXISTS idx_sales_order_line_configuration ON sales_order_lines(configuration_id)
CREATE UNIQUE INDEX IF NOT EXISTS uidx_sales_order_line_component ON sales_order_lines(parent_line_id, component_no)

-- Indexes for 订单计划行
CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_line_kind_no ON sales_order_schedules(line_id, schedule_kind, schedule_no)
CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_service_visit ON sales_order_schedules(line_id, service_visit_no) WHERE schedule_kind = 'service' AND service_visit_no IS NOT NULL
CREATE INDEX IF NOT EXISTS idx_schedule_order ON sales_order_schedules(order_id)
CREATE INDEX IF NOT EXISTS idx_schedule_line ON sales_order_schedules(line_id)

-- Indexes for 供应方式策略
CREATE INDEX IF NOT EXISTS idx_sourcing_mode_policies_item_group_id ON sourcing_mode_policies(item_group_id)
CREATE INDEX IF NOT EXISTS idx_sourcing_mode_policies_item_id ON sourcing_mode_policies(item_id)
CREATE INDEX IF NOT EXISTS idx_sourcing_mode_key ON sourcing_mode_policies(item_group_id, item_id, org_id)
CREATE INDEX IF NOT EXISTS idx_sourcing_mode_org ON sourcing_mode_policies(org_id)

-- Indexes for 供应来源规则
CREATE UNIQUE INDEX IF NOT EXISTS idx_sourcing_rule_code ON sourcing_rules(code)
CREATE INDEX IF NOT EXISTS idx_sourcing_rule_status_usage ON sourcing_rules(status, rule_usage)
CREATE INDEX IF NOT EXISTS idx_sourcing_rules_name ON sourcing_rules(name)

-- Indexes for 供应来源规则分配
CREATE INDEX IF NOT EXISTS idx_sourcing_assign_rule ON sourcing_rule_assignments(rule_id)
CREATE INDEX IF NOT EXISTS idx_sourcing_assign_scope ON sourcing_rule_assignments(scope_type, scope_ref_id, dest_org_id, dest_location_id, status)
CREATE INDEX IF NOT EXISTS idx_sourcing_assign_rank ON sourcing_rule_assignments(specificity_rank, seq)

-- Indexes for 供应来源行
CREATE UNIQUE INDEX IF NOT EXISTS idx_sourcing_line_rule_seq ON sourcing_rule_lines(rule_id, seq)
CREATE INDEX IF NOT EXISTS idx_sourcing_line_rule_rank ON sourcing_rule_lines(rule_id, rank, seq)
CREATE INDEX IF NOT EXISTS idx_sourcing_line_rule_type ON sourcing_rule_lines(rule_id, source_type)
CREATE INDEX IF NOT EXISTS idx_sourcing_line_source_org ON sourcing_rule_lines(source_org_id)
CREATE INDEX IF NOT EXISTS idx_sourcing_line_supplier ON sourcing_rule_lines(supplier_party_id)

-- Indexes for 税务分类
CREATE UNIQUE INDEX IF NOT EXISTS idx_tax_classification_code_applicable ON tax_classifications(code, applicable_to)
CREATE INDEX IF NOT EXISTS idx_tax_classification_status ON tax_classifications(status)
CREATE INDEX IF NOT EXISTS idx_tax_classifications_name ON tax_classifications(name)

-- Indexes for 税码
CREATE UNIQUE INDEX IF NOT EXISTS idx_tax_code_code ON tax_codes(code)
CREATE INDEX IF NOT EXISTS idx_tax_code_country ON tax_codes(country_id)
CREATE INDEX IF NOT EXISTS idx_tax_code_status ON tax_codes(status)
CREATE INDEX IF NOT EXISTS idx_tax_codes_name ON tax_codes(name)

-- Indexes for 税率
CREATE INDEX IF NOT EXISTS idx_tax_rates_tax_code_id ON tax_rates(tax_code_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_tax_rate_code_from ON tax_rates(tax_code_id, effective_from)
CREATE INDEX IF NOT EXISTS idx_tax_rate_code_window ON tax_rates(tax_code_id, effective_from, effective_to)

-- Indexes for 销售区域
CREATE UNIQUE INDEX IF NOT EXISTS uq_territory_code ON territories(code)
CREATE INDEX IF NOT EXISTS idx_territory_parent ON territories(parent_id)
CREATE INDEX IF NOT EXISTS idx_territory_owner_org ON territories(owner_org_id)
CREATE INDEX IF NOT EXISTS idx_territory_status ON territories(status)
CREATE INDEX IF NOT EXISTS idx_territories_name ON territories(name)

-- Indexes for 客户区域分配
CREATE UNIQUE INDEX IF NOT EXISTS uq_taa_triple ON territory_account_assignments(customer_account_id, territory_id, effective_from)
CREATE UNIQUE INDEX IF NOT EXISTS uq_taa_primary ON territory_account_assignments(customer_account_id, effective_from) WHERE is_primary = 1
CREATE INDEX IF NOT EXISTS idx_taa_territory ON territory_account_assignments(territory_id)
CREATE INDEX IF NOT EXISTS idx_taa_customer ON territory_account_assignments(customer_account_id)

-- Indexes for 测试对象
CREATE INDEX IF NOT EXISTS idx_test_objects_name ON test_objects(name)

-- Indexes for 测试表
CREATE INDEX IF NOT EXISTS idx_test_table_name ON test_table(name)

-- Indexes for 类型字典
CREATE INDEX IF NOT EXISTS idx_type_definitions_number_sequence_id ON type_definitions(number_sequence_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_type_definition_scope_code ON type_definitions(scope_bo, level, code)
CREATE INDEX IF NOT EXISTS idx_type_definition_scope_status ON type_definitions(scope_bo, level, status)
CREATE INDEX IF NOT EXISTS idx_type_definitions_name ON type_definitions(name)

-- Indexes for 计量单位
CREATE UNIQUE INDEX IF NOT EXISTS idx_uom_code ON uoms(code)
CREATE INDEX IF NOT EXISTS idx_uom_group ON uoms(uom_group_id)
CREATE INDEX IF NOT EXISTS idx_uom_status ON uoms(status)
CREATE INDEX IF NOT EXISTS idx_uoms_name ON uoms(name)

-- Indexes for 计量单位组换算
CREATE UNIQUE INDEX IF NOT EXISTS idx_uom_conv_group_uom_unique ON uom_conversions(uom_group_id, uom_id)
CREATE INDEX IF NOT EXISTS idx_uom_conv_group ON uom_conversions(uom_group_id)
CREATE INDEX IF NOT EXISTS idx_uom_conv_uom ON uom_conversions(uom_id)
CREATE INDEX IF NOT EXISTS idx_uom_conversions_id ON uom_conversions(id)

-- Indexes for 计量单位组
CREATE UNIQUE INDEX IF NOT EXISTS idx_uom_group_code ON uom_groups(code)
CREATE INDEX IF NOT EXISTS idx_uom_group_status ON uom_groups(status)
CREATE INDEX IF NOT EXISTS idx_uom_groups_name ON uom_groups(name)

-- Indexes for 条件更新组
CREATE UNIQUE INDEX IF NOT EXISTS idx_usage_group_code ON usage_groups(code)
CREATE INDEX IF NOT EXISTS idx_usage_groups_name ON usage_groups(name)

-- Indexes for 用户
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_username ON users(username)
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_sso ON users(sso_provider, sso_user_id)
CREATE INDEX IF NOT EXISTS idx_user_party ON users(party_id)
CREATE INDEX IF NOT EXISTS idx_users_display_name ON users(display_name)

-- Indexes for 供应商档案
CREATE INDEX IF NOT EXISTS idx_vendor_accounts_tax_classification_id ON vendor_accounts(tax_classification_id)
CREATE UNIQUE INDEX IF NOT EXISTS idx_vendor_account_relation_unique ON vendor_accounts(relation_id)
CREATE INDEX IF NOT EXISTS idx_vendor_accounts_name ON vendor_accounts(name)

-- Indexes for 产品线
CREATE INDEX IF NOT EXISTS idx_products_name ON products(name)
CREATE INDEX IF NOT EXISTS idx_products_is_active ON products(is_active)
CREATE INDEX IF NOT EXISTS idx_products_visibility ON products(visibility)

-- Indexes for 产品版本
CREATE UNIQUE INDEX IF NOT EXISTS uidx_versions_product_name ON versions(product_id, name)
CREATE INDEX IF NOT EXISTS idx_versions_product_id ON versions(product_id)
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
CREATE INDEX IF NOT EXISTS idx_business_objects_domain_id ON business_objects(domain_id)

-- Indexes for 业务关系
CREATE UNIQUE INDEX IF NOT EXISTS uidx_relationships_version_code ON relationships(version_id, code)
CREATE INDEX IF NOT EXISTS idx_relationships_version_source ON relationships(version_id, source_bo_id)
CREATE INDEX IF NOT EXISTS idx_relationships_version_target ON relationships(version_id, target_bo_id)
CREATE INDEX IF NOT EXISTS idx_relationships_version_id ON relationships(version_id)
CREATE INDEX IF NOT EXISTS idx_relationships_source_bo_id ON relationships(source_bo_id)
CREATE INDEX IF NOT EXISTS idx_relationships_target_bo_id ON relationships(target_bo_id)
CREATE INDEX IF NOT EXISTS idx_relationships_version_source_target_type_dir ON relationships(version_id, source_bo_id, target_bo_id, relation_type, relation_direction)
CREATE INDEX IF NOT EXISTS idx_relationships_version_type ON relationships(version_id, relation_code)
CREATE INDEX IF NOT EXISTS idx_relationships_relation_desc ON relationships(relation_desc)
