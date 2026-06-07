# Spec: Phase 3 - Formula 增强与状态模式定义

## 1. Background & Objectives

### 1.1 Background

Phase 3 Spec 中 FR-001（Deep Insert 事务回滚）和 FR-002（多态 Composition）已完成实施。
本文档细化 FR-003（Formula 增强）和 FR-004（状态模式定义）的实现方案。

### 1.2 现有实现状态

#### Formula 能力现状

| 组件 | 文件 | 状态 |
|------|------|------|
| `SafeExpressionEvaluator` | `rule_executor.py:130-361` | ✅ 基于 AST 的安全表达式求值 |
| `ComputationExecutor` | `rule_executor.py:576-630` | ✅ 计算规则执行器 |
| `MetaComputation` | `models.py:907-922` | ✅ 计算规则模型 |
| `ComputationService` | `computation_service.py` | ✅ UI 列统计计算 |
| `ExpressionEvaluator` | `rule_executor.py:363-381` | ✅ 表达式求值包装 |

#### Formula 已支持的内置函数（11 个）

```python
ALLOWED_FUNCTIONS = frozenset({
    'len', 'str', 'int', 'float', 'bool', 'abs',
    'min', 'max', 'sum', 'any', 'all',
})
```

#### Formula 已支持的上下文变量

```python
locals_dict = dict(self.context.original_data)
locals_dict.update(self.context.data)
locals_dict["original"] = self.context.original_data
locals_dict["changed_fields"] = self.context.changed_fields
locals_dict["is_changed"] = self.context.is_field_changed
locals_dict["get_value"] = self.context.get_field_value
locals_dict["get_original"] = self.context.get_original_value
```

#### Formula 已支持的 AST 节点

- 字面量: Constant, Num, Str
- 变量: Name
- 集合: List, Tuple, Dict, Set
- 运算: BinOp(+,-,*,/,%), UnaryOp(+,-,not), BoolOp(and,or)
- 比较: Compare(==,!=,<,<=,>,>=,in,not in,is,is not)
- 函数调用: Call（仅白名单函数）
- 属性访问: Attribute（禁止双下划线）
- 索引: Subscript
- 三元: IfExp

#### 状态管理现状

| 组件 | 文件 | 状态 |
|------|------|------|
| `MetaStateTransition` | `models.py:944-963` | ✅ 状态转换规则模型 |
| `StateTransitionExecutor` | `rule_executor.py:633-676` | ✅ 状态转换执行器 |
| `StateTransitionSideEffect` | `models.py:925-931` | ✅ 状态转换副作用 |
| `StateTransitionUIHints` | `models.py:934-940` | ✅ 状态转换 UI 提示 |
| `StateChange` | `rule_chain.py:66-70` | ✅ 规则链状态变更记录 |
| `RuleChainContext.changed_states` | `rule_chain.py:109` | ✅ 规则链状态变更追踪 |

### 1.3 缺失能力

#### Formula 缺失

| 能力 | 说明 | Salesforce 对标 |
|------|------|----------------|
| **日期函数** | TODAY(), ADD_DAYS(), ADD_MONTHS(), DATEDIFF() | ✅ Salesforce Formula |
| **字符串函数** | CONCAT(), SUBSTRING(), UPPER(), LOWER(), TRIM() | ✅ Salesforce Formula |
| **数学函数** | ROUND(), CEIL(), FLOOR(), POWER() | ✅ Salesforce Formula |
| **跨对象引用** | `self.customer.region.name` 多层嵌套 | ✅ Salesforce Formula |
| **条件函数** | IF(), CASE(), COALESCE() | ✅ Salesforce Formula |
| **逻辑函数** | ISNULL(), ISBLANK(), NOT() | ✅ Salesforce Formula |

#### 状态模式缺失

| 能力 | 说明 | SAP 对标 |
|------|------|---------|
| **状态模式定义** | StateSchema: 所有状态、状态组、状态属性 | ✅ SAP BOPF State Schema |
| **状态可视化** | 状态颜色、图标、分组 | ✅ SAP BOPF |
| **状态转换历史** | 记录每次状态变更 | ✅ SAP BOPF |
| **状态属性** | is_initial, is_final, category | ✅ SAP BOPF |

---

## 2. Functional Requirements

### FR-003: Formula 增强

#### FR-003-A: 日期函数库

- **Description**: 系统 MUST 支持日期函数，用于计算规则中的日期操作。
- **Acceptance Criteria**:
  - AC-001: `TODAY()` 返回当前日期（date 类型）
  - AC-002: `NOW()` 返回当前日期时间（datetime 类型）
  - AC-003: `ADD_DAYS(date, n)` 返回 date + n 天
  - AC-004: `ADD_MONTHS(date, n)` 返回 date + n 月
  - AC-005: `ADD_YEARS(date, n)` 返回 date + n 年
  - AC-006: `DATEDIFF(date1, date2, unit)` 返回日期差值，unit 为 'days'/'months'/'years'
  - AC-007: `DAY(date)`, `MONTH(date)`, `YEAR(date)` 返回日期部分
  - AC-008: `DATE_STR(date, format)` 格式化日期为字符串
- **Priority**: Must
- **Source**: Salesforce Formula Fields

#### FR-003-B: 字符串函数库

- **Description**: 系统 MUST 支持字符串函数。
- **Acceptance Criteria**:
  - AC-001: `CONCAT(s1, s2, ...)` 连接字符串
  - AC-002: `SUBSTRING(s, start, length)` 截取子串
  - AC-003: `UPPER(s)`, `LOWER(s)` 大小写转换
  - AC-004: `TRIM(s)`, `LTRIM(s)`, `RTRIM(s)` 去除空白
  - AC-005: `REPLACE(s, old, new)` 替换
  - AC-006: `CONTAINS(s, sub)` 返回 bool
  - AC-007: `STARTS_WITH(s, prefix)`, `ENDS_WITH(s, suffix)` 返回 bool
  - AC-008: `LENGTH(s)` 返回字符串长度
- **Priority**: Must
- **Source**: Salesforce Formula Fields

#### FR-003-C: 数学函数库

- **Description**: 系统 MUST 支持数学函数。
- **Acceptance Criteria**:
  - AC-001: `ROUND(n, digits)` 四舍五入
  - AC-002: `CEIL(n)`, `FLOOR(n)` 向上/向下取整
  - AC-003: `POWER(base, exp)` 幂运算
  - AC-004: `SQRT(n)` 平方根
  - AC-005: `MOD(n, divisor)` 取模（与 % 运算符等效）
  - AC-006: `LOG(n)`, `LOG10(n)` 对数
- **Priority**: Should
- **Source**: Salesforce Formula Fields

#### FR-003-D: 条件与逻辑函数

- **Description**: 系统 MUST 支持条件与逻辑函数。
- **Acceptance Criteria**:
  - AC-001: `IF(condition, true_value, false_value)` 条件函数
  - AC-002: `COALESCE(v1, v2, ...)` 返回第一个非空值
  - AC-003: `ISNULL(v)`, `ISBLANK(v)` 空值检查
  - AC-004: `CASE(expr, val1, result1, val2, result2, ..., default)` 多条件分支
- **Priority**: Must
- **Source**: Salesforce Formula Fields

#### FR-003-E: 跨对象引用

- **Description**: 系统 MUST 支持跨对象引用语法，在公式中访问关联对象的字段。
- **Acceptance Criteria**:
  - AC-001: 支持 `self.customer.name` 单层引用
  - AC-002: 支持 `self.customer.region.name` 多层嵌套引用
  - AC-003: 引用失败时返回 None 而非报错（空安全）
  - AC-004: 支持 `parent.field` 引用父对象字段
  - AC-005: 跨对象引用通过 data_source 查询实现
- **Priority**: Must
- **Source**: Salesforce Formula Fields

### FR-004: 状态模式定义

#### FR-004-A: StateSchema 模型

- **Description**: 系统 MUST 支持 StateSchema 模型，定义所有可能的状态、状态组、状态属性。
- **Acceptance Criteria**:
  - AC-001: 支持定义状态列表（id, name, category, is_initial, is_final）
  - AC-002: 支持定义状态组（多个状态的集合，如 active_group = [draft, submitted]）
  - AC-003: 支持状态 UI 配置（color, icon）
  - AC-004: StateSchema 与 MetaStateTransition 关联验证
  - AC-005: 状态转换时自动验证目标状态是否在 StateSchema 中定义
- **Priority**: Must
- **Source**: SAP BOPF State Schema

#### FR-004-B: 状态转换历史

- **Description**: 系统 MUST 支持状态转换历史记录。
- **Acceptance Criteria**:
  - AC-001: 每次状态转换自动记录（from_state, to_state, operator, timestamp）
  - AC-002: 支持查询对象的完整状态转换历史
  - AC-003: 支持 API 端点 `GET /<object_type>/<id>/state_history`
  - AC-004: 历史记录存储在 `state_transition_history` 表
- **Priority**: Must
- **Source**: SAP BOPF

#### FR-004-C: 状态模式 API

- **Description**: 系统 MUST 支持状态模式查询 API。
- **Acceptance Criteria**:
  - AC-001: `GET /<object_type>/state_schema` 返回状态模式定义
  - AC-002: 返回结果包含状态列表、状态组、允许的转换、UI 配置
  - AC-003: 前端可基于此渲染状态机图
- **Priority**: Should
- **Source**: SAP BOPF

---

## 3. Implementation Design

### 3.1 Formula 增强 - 架构设计

#### 新增文件: `meta/core/formula_functions.py`

```
formula_functions.py
├── FormulaFunctionRegistry     # 函数注册中心
├── DateFunctions               # 日期函数类
│   ├── today()
│   ├── now()
│   ├── add_days(date, n)
│   ├── add_months(date, n)
│   ├── add_years(date, n)
│   ├── datediff(date1, date2, unit)
│   ├── day(date), month(date), year(date)
│   └── date_str(date, format)
├── StringFunctions             # 字符串函数类
│   ├── concat(*args)
│   ├── substring(s, start, length)
│   ├── upper(s), lower(s)
│   ├── trim(s), ltrim(s), rtrim(s)
│   ├── replace(s, old, new)
│   ├── contains(s, sub)
│   ├── starts_with(s, prefix)
│   ├── ends_with(s, suffix)
│   └── length(s)
├── MathFunctions               # 数学函数类
│   ├── round(n, digits)
│   ├── ceil(n), floor(n)
│   ├── power(base, exp)
│   ├── sqrt(n)
│   ├── mod(n, divisor)
│   └── log(n), log10(n)
└── LogicFunctions              # 逻辑函数类
    ├── if_(condition, true_val, false_val)
    ├── coalesce(*args)
    ├── isnull(v), isblank(v)
    └── case(expr, *args)
```

#### 修改文件: `rule_executor.py`

**SafeExpressionEvaluator 扩展**:

1. `ALLOWED_FUNCTIONS` 扩展为动态注册
2. `_get_builtin_func()` 改为从 `FormulaFunctionRegistry` 查找
3. `_build_locals()` 增加跨对象引用解析器

**跨对象引用实现**:

```python
class CrossObjectResolver:
    """跨对象引用解析器"""
    
    def __init__(self, data_source, meta_object, data):
        self.data_source = data_source
        self.meta_object = meta_object
        self.data = data
    
    def resolve(self, path: str) -> Any:
        """
        解析跨对象引用路径
        
        示例:
          self.customer.name → 查询 customer 表
          self.customer.region.name → 多层嵌套查询
          parent.field → 查询父对象字段
        """
        parts = path.split('.')
        if parts[0] == 'self':
            return self._resolve_self_path(parts[1:])
        elif parts[0] == 'parent':
            return self._resolve_parent_path(parts[1:])
        return None
    
    def _resolve_self_path(self, parts):
        """解析 self.xxx.yyy 路径"""
        current_data = self.data
        current_type = self.meta_object
        
        for i, part in enumerate(parts):
            # 先检查当前数据中是否有该字段
            if isinstance(current_data, dict) and part in current_data:
                value = current_data[part]
                if i < len(parts) - 1:
                    # 还有更多层级，需要查询关联对象
                    current_data = value
                    continue
                return value
            
            # 检查是否是关联对象引用
            relation = self._find_relation(current_type, part)
            if relation:
                foreign_key = self._get_foreign_key_value(relation)
                if foreign_key:
                    target_type = relation.target_object or relation.target_entity
                    target_data = self._load_object(target_type, foreign_key)
                    if target_data and i < len(parts) - 1:
                        current_data = target_data
                        current_type = registry.get(target_type)
                        continue
                    return target_data
            
            return None
        return current_data
```

#### 修改文件: `models.py`

**RuleContext 扩展**:

```python
class RuleContext:
    # 新增属性
    cross_object_resolver: Optional[CrossObjectResolver] = None
    data_source: Optional[Any] = None
```

### 3.2 状态模式定义 - 架构设计

#### 新增模型: `models.py`

```python
@dataclass
class StateDefinition:
    """状态定义"""
    id: str
    name: str
    category: str = "active"     # active / inactive / final / error
    is_initial: bool = False
    is_final: bool = False
    ui: Optional[Dict[str, str]] = None  # color, icon, label

@dataclass
class StateGroup:
    """状态组"""
    id: str
    name: str
    states: List[str] = field(default_factory=list)

@dataclass
class StateSchema:
    """状态模式定义"""
    state_field: str = "status"
    states: List[StateDefinition] = field(default_factory=list)
    groups: List[StateGroup] = field(default_factory=list)
    
    def get_initial_state(self) -> Optional[str]:
        for s in self.states:
            if s.is_initial:
                return s.id
        return self.states[0].id if self.states else None
    
    def get_state(self, state_id: str) -> Optional[StateDefinition]:
        for s in self.states:
            if s.id == state_id:
                return s
        return None
    
    def is_valid_state(self, state_id: str) -> bool:
        return any(s.id == state_id for s in self.states)
    
    def is_final_state(self, state_id: str) -> bool:
        state = self.get_state(state_id)
        return state.is_final if state else False
```

**MetaObject 扩展**:

```python
class MetaObject:
    # 新增
    state_schema: Optional[StateSchema] = None
```

#### 新增表: `state_transition_history`

```sql
CREATE TABLE IF NOT EXISTS state_transition_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    object_type VARCHAR(100) NOT NULL,
    object_id INTEGER NOT NULL,
    state_field VARCHAR(100) NOT NULL,
    from_state VARCHAR(100),
    to_state VARCHAR(100) NOT NULL,
    operator_id VARCHAR(100),
    operator_name VARCHAR(200),
    transition_rule_id VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sth_object ON state_transition_history(object_type, object_id);
CREATE INDEX idx_sth_created ON state_transition_history(created_at);
```

#### 修改文件: `rule_executor.py`

**StateTransitionExecutor 扩展**:

```python
class StateTransitionExecutor(RuleExecutor):
    def _do_execute(self, rule, context):
        # ... 现有逻辑 ...
        
        # 新增：StateSchema 验证
        if context.meta_object.state_schema:
            if not context.meta_object.state_schema.is_valid_state(rule.to_state):
                return RuleResult(
                    success=False,
                    rule_id=rule.id,
                    rule_name=rule.name,
                    message=f"Invalid target state: {rule.to_state}",
                    severity=ValidationSeverity.ERROR,
                )
        
        # 新增：记录状态转换历史
        self._record_transition(context, current_state, rule.to_state, rule)
        
        # ... 设置新状态 ...
```

#### 新增 API 端点: `manage_api.py`

```python
@manage_bp.route('/<object_type>/state_schema', methods=['GET'])
def get_state_schema(object_type):
    """获取对象的状态模式定义"""

@manage_bp.route('/<object_type>/<int:object_id>/state_history', methods=['GET'])
def get_state_history(object_type, object_id):
    """获取对象的状态转换历史"""
```

#### YAML 配置扩展

```yaml
domains:
  - name: change_request
    state_schema:
      state_field: status
      states:
        - id: draft
          name: 草稿
          category: active
          is_initial: true
          ui:
            color: "#909399"
            icon: edit
        - id: submitted
          name: 已提交
          category: active
          ui:
            color: "#409EFF"
            icon: upload
        - id: approved
          name: 已审批
          category: final
          ui:
            color: "#67C23A"
            icon: check
        - id: rejected
          name: 已拒绝
          category: error
          is_final: true
          ui:
            color: "#F56C6C"
            icon: close
      groups:
        - id: pending
          name: 待处理
          states: [draft, submitted]
        - id: resolved
          name: 已完结
          states: [approved, rejected]
```

---

## 4. 受影响文件

| 文件 | 影响类型 | 说明 |
|------|---------|------|
| `meta/core/formula_functions.py` | **新增** | 日期/字符串/数学/逻辑函数库 |
| `meta/core/rule_executor.py` | **修改** | SafeExpressionEvaluator 扩展函数注册 |
| `meta/core/models.py` | **扩展** | 新增 StateSchema/StateDefinition/StateGroup 模型 |
| `meta/core/yaml_loader.py` | **扩展** | 解析 state_schema 配置 |
| `meta/api/manage_api.py` | **扩展** | 新增 state_schema/state_history API |
| `meta/core/cross_object_resolver.py` | **新增** | 跨对象引用解析器 |

---

## 5. Formula 函数增减分析

### 5.1 现有函数评估（11个）

| 函数 | 分类 | 保留/移除 | 理由 |
|------|------|----------|------|
| `len` | 类型转换 | ✅ 保留 | 通用长度函数，适用于字符串/列表/字典 |
| `str` | 类型转换 | ✅ 保留 | 基础类型转换 |
| `int` | 类型转换 | ✅ 保留 | 基础类型转换 |
| `float` | 类型转换 | ✅ 保留 | 基础类型转换 |
| `bool` | 类型转换 | ✅ 保留 | 基础类型转换 |
| `abs` | 数学 | ✅ 保留 | 绝对值，常用 |
| `min` | 聚合 | ✅ 保留 | 最小值聚合 |
| `max` | 聚合 | ✅ 保留 | 最大值聚合 |
| `sum` | 聚合 | ✅ 保留 | 求和聚合 |
| `any` | 逻辑聚合 | ✅ 保留 | 存在性判断 |
| `all` | 逻辑聚合 | ✅ 保留 | 全量判断 |

**结论**: 现有 11 个函数全部保留，均为 Python 内建函数，是表达式求值的基础能力。

### 5.2 新增函数清单（26个）

#### 日期函数（8个）

| 函数 | 签名 | 说明 | 业务场景 |
|------|------|------|----------|
| `TODAY` | `TODAY()` → date | 返回当前日期 | 日期比较基准 |
| `NOW` | `NOW()` → datetime | 返回当前日期时间 | 时间戳计算 |
| `ADD_DAYS` | `ADD_DAYS(date, n)` → date | 日期加减天数 | 到期日计算 |
| `ADD_MONTHS` | `ADD_MONTHS(date, n)` → date | 日期加减月数 | 月度周期计算 |
| `ADD_YEARS` | `ADD_YEARS(date, n)` → date | 日期加减年数 | 年度周期计算 |
| `DATEDIFF` | `DATEDIFF(d1, d2, unit)` → int | 日期差值(unit: days/months/years/hours/minutes/seconds) | **change_event 投递延迟**、**user 不活跃天数** |
| `DAY/MONTH/YEAR` | `DAY(date)` → int | 提取日期部分 | 按维度分组统计 |
| `DATE_STR` | `DATE_STR(date, fmt)` → str | 格式化日期 | 显示格式化 |

#### 字符串函数（8个）

| 函数 | 签名 | 说明 | 业务场景 |
|------|------|------|----------|
| `CONCAT` | `CONCAT(s1, s2, ...)` → str | 连接字符串 | 拼接显示名称 |
| `SUBSTRING` | `SUBSTRING(s, start, len)` → str | 截取子串 | 编码规则截取 |
| `UPPER/LOWER` | `UPPER(s)` → str | 大小写转换 | 标准化比较 |
| `TRIM/LTRIM/RTRIM` | `TRIM(s)` → str | 去除空白 | 输入清洗 |
| `REPLACE` | `REPLACE(s, old, new)` → str | 替换子串 | 文本处理 |
| `CONTAINS` | `CONTAINS(s, sub)` → bool | 包含检查 | 条件判断 |
| `STARTS_WITH/ENDS_WITH` | `STARTS_WITH(s, prefix)` → bool | 前缀/后缀检查 | 编码规则匹配 |
| `LENGTH` | `LENGTH(s)` → int | 字符串长度 | 与 `len` 互补，语义更明确 |

#### 数学函数（6个）

| 函数 | 签名 | 说明 | 业务场景 |
|------|------|------|----------|
| `ROUND` | `ROUND(n, digits)` → float | 四舍五入 | 精度控制 |
| `CEIL/FLOOR` | `CEIL(n)` → int | 向上/向下取整 | 分页计算、配额 |
| `POWER` | `POWER(base, exp)` → float | 幂运算 | 复合计算 |
| `SQRT` | `SQRT(n)` → float | 平方根 | 统计计算 |
| `MOD` | `MOD(n, divisor)` → int | 取模 | 奇偶判断、周期计算 |
| `LOG/LOG10` | `LOG(n)` → float | 对数 | 统计计算 |

#### 条件与逻辑函数（4个）

| 函数 | 签名 | 说明 | 业务场景 |
|------|------|------|----------|
| `IF` | `IF(cond, t, f)` → Any | 条件分支 | **BO密度计算**: `IF(child_count > 0, relation_count / child_count, 0)` |
| `COALESCE` | `COALESCE(v1, v2, ...)` → Any | 首个非空值 | 默认值处理 |
| `ISNULL/ISBLANK` | `ISNULL(v)` → bool | 空值检查 | 条件守卫 |
| `CASE` | `CASE(expr, v1, r1, ..., default)` → Any | 多条件分支 | 分类标签映射 |

### 5.3 建议额外新增函数（3个）

基于存量对象分析，以下函数在业务场景中高频出现，建议一并纳入：

| 函数 | 签名 | 说明 | 业务场景 |
|------|------|------|----------|
| `REGEX_MATCH` | `REGEX_MATCH(s, pattern)` → bool | 正则匹配 | **business_object.code_format** 校验规则增强 |
| `FORMAT_NUMBER` | `FORMAT_NUMBER(n, pattern)` → str | 数字格式化 | 百分比/金额显示 |
| `LOOKUP` | `LOOKUP(object_type, filter_field, filter_value, result_field)` → Any | 跨对象查找 | 简化版跨对象引用，比 `self.xxx.yyy` 更直观 |

### 5.4 函数总计

| 分类 | 现有 | 新增 | 合计 |
|------|------|------|------|
| 类型转换 | 5 | 0 | 5 |
| 聚合 | 3 | 0 | 3 |
| 逻辑聚合 | 2 | 0 | 2 |
| 数学 | 1 | 6 | 7 |
| 日期 | 0 | 8 | 8 |
| 字符串 | 0 | 8 | 8 |
| 条件/逻辑 | 0 | 4 | 4 |
| 高级 | 0 | 3 | 3 |
| **合计** | **11** | **29** | **40** |

---

## 6. 存量对象采纳分析

### 6.1 采纳 Formula 的对象

#### 高优先级 ✅ 已完成

| 对象 | 场景 | 公式 | 状态 |
|------|------|------|------|
| **change_event** | 投递延迟计算 | `IF(ISNULL(delivered_at), DATEDIFF(created_at, NOW(), "seconds"), DATEDIFF(created_at, delivered_at, "seconds"))` | ✅ 已完成 |
| **user** | 不活跃天数 | `IF(ISNULL(last_login_at), DATEDIFF(created_at, NOW(), "days"), DATEDIFF(last_login_at, NOW(), "days"))` | ✅ 已完成 |
| **user** | 账号年龄 | `DATEDIFF(created_at, NOW(), "days")` | ✅ 已完成 |
| **user** | 当前状态停留天数 | `IF(ISNULL(status_entered_at), 0, DATEDIFF(status_entered_at, NOW(), "days"))` | ✅ 已完成 |

#### 中优先级

| 对象 | 场景 | 建议公式 | 状态 |
|------|------|----------|------|
| **domain** | BO密度 | `IF(child_count > 0, ROUND(relation_count / child_count, 2), 0)` | 待实施 |
| **sub_domain** | BO密度 | `IF(child_count > 0, ROUND(relation_count / child_count, 2), 0)` | 待实施 |
| **service_module** | BO密度 | `IF(child_count > 0, ROUND(relation_count / child_count, 2), 0)` | 待实施 |
| **relationship** | 范围标签增强 | `IF(DATEDIFF(created_at, NOW(), "days") > 90, "stale", "active")` | 待实施 |
| **user_group_member** | 组龄计算 | `DATEDIFF(joined_at, NOW(), "days")` | 待实施 |

#### 低优先级

| 对象 | 场景 | 建议公式 | 状态 |
|------|------|----------|------|
| **product** | 跨层级总BO数 | `LOOKUP("version", "product_id", id, "total_bo_count")` | 待实施 |
| **version** | 跨层级总BO数 | `sum(LOOKUP("domain", "version_id", id, "child_count"))` | 待实施 |
| **role** | 权限覆盖率 | `ROUND(permission_count / total_permissions * 100, 1)` | 待实施 |
| **audit_log** | 日志老化 | `DATEDIFF(created_at, NOW(), "hours")` | 待实施 |

### 6.2 采纳 State 的对象

#### 高优先级 ✅ 已完成

| 对象 | 状态字段 | 状态值 | 转换规则 | 状态 |
|------|----------|--------|----------|------|
| **change_event** | `status` | pending/processing/delivered/failed | 4条: process_event, deliver_event, fail_event, retry_event | ✅ 已完成 |
| **user** | `status` | active/inactive/locked | 3条: activate_user, lock_user, deactivate_user | ✅ 已完成 |

#### 中优先级

| 对象 | 状态字段 | 建议 StateSchema + 转换规则 | 状态 |
|------|----------|---------------------------|------|
| **audit_log** | `status` | 异步写入补偿: pending→written, pending→failed, failed→pending(重试) | 待实施 |
| **change_subscription** | `enabled` | 将 boolean 映射为语义状态 | 待实施 |

#### 低优先级

| 对象 | 状态字段 | 建议 | 状态 |
|------|----------|------|------|
| **product** | `is_active` | 启用/停用转换 + 业务约束 | 待实施 |
| **version** | `is_current` | 设为当前版本转换 + 互斥约束 | 待实施 |
| **enum_value** | `is_active` | 启用/停用转换 + 引用检查 | 待实施 |
| **menu** | `is_active` | 简单启用/停用 | 待实施 |
| **permission_bundle** | `is_active` | 简单启用/停用 | 待实施 |

### 6.3 采纳优先级矩阵

```
                    │ Formula 需求高        │ Formula 需求低
────────────────────┼──────────────────────┼──────────────────────
State 需求高        │ change_event ✅       │ user ✅
                    │ audit_log ★★         │ change_subscription ★★
────────────────────┼──────────────────────┼──────────────────────
State 需求中        │ domain/sub_domain ★★  │ product ★★
                    │ service_module ★★     │ version ★★
                    │                       │ enum_value ★
────────────────────┼──────────────────────┼──────────────────────
State 需求低        │ user_group_member ★   │ menu ★
                    │ relationship ★        │ permission_bundle ★
```

### 6.4 实施进度

**第一批（核心验证）✅ 已完成**: change_event + user
- ✅ change_event: Formula（投递延迟）+ State（事件生命周期）
- ✅ user: Formula（不活跃天数 + 账号年龄 + 状态停留天数）+ State（用户状态机）

**第二批（业务增强）待实施**: audit_log + domain/sub_domain/service_module
- audit_log: State（写入补偿状态机）
- domain/sub_domain/service_module: Formula（BO密度计算）

**第三批（完善补充）待实施**: product/version/enum_value + 其余对象
- product/version: State（启用/停用 + 互斥约束）
- enum_value: State（引用安全停用）
- 其余对象按需采纳

---

## 7. 实施计划

### Milestone 1: Formula 增强 ✅ 已完成

| 步骤 | 内容 | 状态 |
|------|------|------|
| 1 | 新增 `formula_functions.py`（日期/字符串/数学/逻辑/高级函数，共 37 个新函数） | ✅ 完成 |
| 2 | 新增 `FormulaFunctionRegistry` 动态函数注册中心 | ✅ 完成 |
| 3 | 修改 `SafeExpressionEvaluator` 支持动态函数注册 + 跨对象引用 | ✅ 完成 |
| 4 | 新增 `cross_object_resolver.py` 跨对象引用解析器 | ✅ 完成 |
| 5 | 修改 `RuleContext` 增加 `data_source` 参数 | ✅ 完成 |
| 6 | 修改 `RuleEngine` 传递 `data_source` 到上下文 | ✅ 完成 |
| 7 | 集成测试验证 | ✅ 48 个函数全部通过 |

**已实现文件清单**:

| 文件 | 类型 | 说明 |
|------|------|------|
| `meta/core/formula_functions.py` | 新增 | 5 类函数库 + FormulaFunctionRegistry |
| `meta/core/cross_object_resolver.py` | 新增 | CrossObjectResolver + ParentResolver |
| `meta/core/rule_executor.py` | 修改 | SafeExpressionEvaluator 动态注册 + 跨对象引用 |
| `meta/tests/test_formula_integration.py` | 新增 | 集成测试 |

**函数统计**: 11(原有) + 37(新增) = **48 个函数**

### Milestone 2: 状态模式定义 ✅ 已完成

> **方案调整**: 经深入分析，原 StateSchema 方案会导致状态定义重复，违反单一事实来源原则。
> 最终采用扩展 `enum_values` 属性 + 基于 audit_log 的状态历史查询方案。

| 原计划 | 最终方案 | 状态 |
|--------|---------|------|
| 新增 StateSchema 模型 | ❌ 取消，避免重复定义 | - |
| 新增 StateDefinition 模型 | ❌ 取消，复用 enum_values | - |
| 新增 StateGroup 模型 | ❌ 取消，通过 Computation 实现 | - |
| 扩展 enum_values 属性 | ✅ 新增 icon/is_initial/is_final/category | ✅ 完成 |
| 新增状态转换历史表 | ✅ 基于 audit_log 查询（无新增表） | ✅ 完成 |
| 新增状态转换 API | ✅ state_history + stage_metrics | ✅ 完成 |
| StateTransitionExecutor 自动维护 status_entered_at | ✅ | ✅ 完成 |
| 存量对象采纳 | ✅ user + change_event | ✅ 完成 |

**详细方案**: [spec-state-management-enhancement.md](./spec-state-management-enhancement.md)

**已实现文件清单**:

| 文件 | 类型 | 说明 |
|------|------|------|
| `meta/api/manage_api.py` | 修改 | 新增 get_state_history, get_stage_metrics API |
| `meta/core/rule_executor.py` | 修改 | StateTransitionExecutor 自动维护 status_entered_at |
| `meta/schemas/user.yaml` | 更新 | enum_values 扩展 + status_entered_at 字段 |
| `meta/schemas/change_event.yaml` | 更新 | enum_values + 4 条状态转换规则 |
| `meta/tests/test_state_management_enhancement.py` | 新增 | 验证测试 |

---

## 8. 验证方案

### Formula 增强 测试用例

```python
# 日期函数
assert TODAY() == date.today()
assert ADD_DAYS(date(2026, 1, 1), 30) == date(2026, 1, 31)
assert DATEDIFF(date(2026, 1, 1), date(2026, 2, 1), 'days') == 31

# 字符串函数
assert CONCAT("Hello", " ", "World") == "Hello World"
assert UPPER("hello") == "HELLO"
assert CONTAINS("Hello World", "World") == True

# 数学函数
assert ROUND(3.14159, 2) == 3.14
assert CEIL(3.1) == 4
assert POWER(2, 10) == 1024

# 逻辑函数
assert IF(True, "yes", "no") == "yes"
assert COALESCE(None, None, "default") == "default"
assert ISNULL(None) == True

# 跨对象引用
assert evaluate("self.customer.name", context) == "Acme Corp"
assert evaluate("self.customer.region.name", context) == "North America"
assert evaluate("self.customer.nonexistent.field", context) == None  # 空安全
```

### 状态模式定义 测试用例

```python
# StateSchema 验证
schema = meta_obj.state_schema
assert schema.is_valid_state("draft") == True
assert schema.is_valid_state("unknown") == False
assert schema.is_final_state("approved") == True
assert schema.get_initial_state() == "draft"

# 状态转换历史
api.get("/change_requests/1/state_history")
# 返回: [{from_state: "draft", to_state: "submitted", operator: "admin", ...}]

# StateSchema API
api.get("/change_requests/state_schema")
# 返回: {states: [...], groups: [...], transitions: [...]}
```

---

## 9. Phase 3.5: 状态转换按钮组件 ✅ 已完成

### 9.1 功能概述

在详情页的状态字段区域显示可用的状态转换按钮，用户点击后执行状态转换操作。

### 9.2 实现方案

#### 9.2.1 API 端点

**新增**: `GET /manage/<object_type>/<id>/state_transitions`

返回当前可用的状态转换规则列表：

```json
{
  "success": true,
  "data": [
    {
      "id": "activate_user",
      "name": "激活用户",
      "state_field": "status",
      "from_states": ["inactive", "locked"],
      "to_state": "active",
      "current_state": "inactive",
      "available": true,
      "label": "激活",
      "icon": "check",
      "confirm_message": "确定要激活此用户吗？",
      "highlight": true,
      "hidden": false
    }
  ]
}
```

#### 9.2.2 前端组件

**新增**: `StateTransitionButtons.vue`

```vue
<template>
  <div v-if="availableTransitions.length > 0" class="state-transition-buttons">
    <el-button
      v-for="transition in availableTransitions"
      :type="transition.highlight ? 'primary' : 'default'"
      :size="size"
      @click="handleTransition(transition)"
    >
      {{ transition.label }}
    </el-button>
  </div>
</template>
```

**特性**:
- 自动从 API 获取状态转换规则
- 根据 `available` 属性过滤可用转换
- 支持 `highlight` 属性高亮重要操作
- 支持 `confirm_message` 确认对话框
- 执行成功后自动刷新数据

#### 9.2.3 详情页集成

**修改**: `ObjectPage.vue`

在 header-right 区域（状态徽章后面）添加状态转换按钮：

```vue
<!-- 右侧区域：状态 + 操作按钮 -->
<div class="object-page__header-right">
  <span v-if="status" :class="['status-badge', `status-badge--${statusType}`]">
    {{ status }}
  </span>

  <!-- 状态转换按钮（元数据驱动） -->
  <StateTransitionButtons
    v-if="showStateTransitions && objectType && objectId && !internalEditing"
    :object-type="objectType"
    :object-id="objectId"
    size="small"
    @refresh="$emit('refresh')"
  />

  <!-- YAML-Driven 操作按钮 -->
  <div v-if="hasActionsConfig" class="op-actions">
    ...
  </div>
</div>
```

**新增 prop**: `showStateTransitions: Boolean` (default: true)

### 9.3 已实现文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `meta/api/manage_api.py` | 修改 | 新增 get_state_transitions API |
| `src/components/bo/StateTransitionButtons.vue` | 新增 | 状态转换按钮组件 |
| `src/components/common/ObjectPage/ObjectPage.vue` | 修改 | 集成状态转换按钮到 header |
| `src/components/common/DetailPage/DetailPage.vue` | 修改 | 处理 refresh 事件 |

### 9.4 使用示例

在详情页中，状态转换按钮会自动显示在状态徽章旁边：

```
┌─────────────────────────────────────────────────────────────┐
│  用户详情                              [停用中] [激活] [编辑] │
├─────────────────────────────────────────────────────────────┤
│  基本信息                                                    │
│  用户名: admin                                               │
│  状态: 停用中                                                │
│  ...                                                         │
└─────────────────────────────────────────────────────────────┘
```

点击"激活"按钮后：
1. 弹出确认对话框（如果配置了 confirm_message）
2. 用户确认后执行状态转换
3. 转换成功后自动刷新详情页数据
4. 按钮列表根据新状态自动更新

### 9.5 待办事项

- [ ] 状态历史时间线组件（详情页或独立抽屉中显示）- **暂缓实施**
