## 目录

1. [1. 概述](#1-概述)
2. [2. 头部产品参考](#2-头部产品参考)
3. [3. 现状分析](#3-现状分析)
4. [4. KeyTemplate 设计](#4-keytemplate-设计)
5. [5. 启用对象（按用户决策）](#5-启用对象（按用户决策）)
6. [6. 存量数据与序列号起点](#6-存量数据与序列号起点)
7. [7. 实施难度与价值](#7-实施难度与价值)
8. [8. 实施计划](#8-实施计划)
9. [12. 实施完成记录 (v1.1)](#12-实施完成记录-(v11))
10. [9. YAML 配置示例](#9-yaml-配置示例)
11. [10. 结论](#10-结论)
12. [11. 架构思考：YAML 配置与配置BO 的边界](#11-架构思考：yaml-配置与配置bo-的边界)

---
# Spec: KeyTemplate — 灵活的业务编码规则

> **版本**: v1.1
> **日期**: 2026-05-23
> **状态**: ✅ 已实施
> **依赖**: Formula 引擎（已就绪）、Deep Insert API（已就绪）

---

## 1. 概述

### 1.1 背景

当前系统已经全面使用 `code` 作为**业务关键字**：

| 对象 | code 字段 | pattern | 生成方式 | 唯一性 |
|------|----------|---------|---------|--------|
| product | `产品编码` | `^[A-Z][A-Z0-9_]*$` | **手动输入** | `conflict_key: code` |
| version | `版本编码` | `^[A-Z][A-Z0-9_]*$` | **手动输入** | `conflict_key: code` |
| domain | `编码` | `^[A-Z][A-Z0-9_]*$` | **手动输入（预留）** | `business_key: true` |
| sub_domain | `编码` | `^[A-Z][A-Z0-9_]*$` | **手动输入（预留）** | `business_key: true` |
| service_module | `编码` | - | **手动输入** | `business_key: true` |
| user_group | `code` | - | **手动输入** | `target_code_field` |

**痛点**:
- 所有 `code` 字段都是**手动输入**，容易重复、不规范
- 层级对象（product → version → domain → sub_domain → service_module）的编码没有继承关系
- `data_category: code` 标记了"这是编码字段"但缺乏自动生成能力
- 导入导出时依赖编码作为业务键，但编码一致性靠人工保证

### 1.2 目标

提供**声明式编码规则引擎**，支持：

1. **自动生成** — 根据规则自动生成编码，无需手动输入
2. **层级编码** — 子对象编码继承父对象前缀
3. **序列号** — 支持自动递增序号
4. **格式灵活** — 前缀 + 分隔符 + 序列/日期 + 后缀
5. **与现有 code 字段兼容** — 不破坏已有手动编码能力

---

## 2. 头部产品参考

| 产品 | 编码方案 | 特点 |
|------|---------|------|
| **SAP S/4HANA** | Number Range (NR) | 独立编号范围对象，支持内/外部编号 |
| **Salesforce** | Auto Number 字段类型 | `{PREFIX}-{00000}` 格式，自动递增 |
| **Odoo** | Sequence + XML ID | `ir.sequence` 模型，支持前缀/后缀/填充 |
| **ServiceNow** | Number Maintenance | `sys_number` 表，支持多租户独立编号 |
| **Oracle EBS** | Document Sequencing | 支持多级分类，按分类独立编号 |

**共同模式**: 前缀 + 分隔符 + 序号（定长补零）

---

## 3. 现状分析

### 3.1 现有 code 字段统计

```
对象层级结构:
  product (1) → version (2) → domain (3) → sub_domain (4) → service_module (5)
                                      ↕
                                 business_object (6) → relationship (7)
```

| 层级 | 对象 | code 字段ID | pattern | 是否启用 | 唯一约束 |
|------|------|-----------|---------|---------|---------|
| 1 | product | `code` | `^[A-Z][A-Z0-9_]*$` | ✅ 启用 | `conflict_key: code` |
| 2 | version | `code` | `^[A-Z][A-Z0-9_]*$` | ✅ 启用 | `conflict_key: code` |
| 3 | domain | `code` | `^[A-Z][A-Z0-9_]*$` | ⚠️ 预留 | `business_key: true` |
| 4 | sub_domain | `code` | `^[A-Z][A-Z0-9_]*$` | ⚠️ 预留 | `business_key: true` |
| 5 | service_module | `code` | 无 | ⚠️ 手动 | `business_key: true` |
| - | user_group | `code` | 无 | ✅ 启用 | `target_code_field: code` |

### 3.2 现有语义标注

| 标注 | 含义 | 出现在 |
|------|------|--------|
| `data_category: code` | 标记为编码类型字段 | domain, version, sub_domain |
| `business_key: true` | 业务关键字 | domain, sub_domain, service_module, product, version |
| `immutable: true` | 创建后不可修改 | domain, sub_domain, product, version |
| `conflict_key: code` | 导入时用 code 做冲突检测 | product, version |
| `pattern: "^[A-Z]..."` | 格式校验 | domain, sub_domain, product, version |

### 3.3 唯一索引

```yaml
# domain.yaml L525
unique_constraints:
  - name: uq_version_code
    columns: [version_id, code]
    description: "版本+编码唯一索引（业务键约束）"
```

---

## 4. KeyTemplate 设计

### 4.1 核心概念

```
KeyTemplate = {
    pattern: "固定文本 + 变量占位符",
    segments: [segment1, segment2, ...],
    auto: true/false    # 是否自动生成
}
```

### 4.2 变量占位符

| 占位符 | 说明 | 示例 |
|--------|------|------|
| `{parent.code}` | 父对象编码 | `FIN` |
| `{parent.code:upper}` | 父对象编码（大写） | `FIN` |
| `{parent.code:lower}` | 父对象编码（小写） | `fin` |
| `{SEQ:n}` | 自动递增序号（n位，补零） | `SEQ:4` → `0001` |
| `{SEQ:category}` | 按分类独立编号 | `{SEQ:domain_type}` |
| `{DATE:format}` | 日期 | `{DATE:yyyyMM}` → `202605` |
| `{DATE:yyyy}` | 年份 | `2026` |
| `{YEAR}` | 年份简写 | `26` |
| `{MONTH}` | 月份 | `05` |

### 4.3 层级编码继承

```
product:       FIN            (手动)
  version:     FIN-V1         (继承 product.code + 后缀)
    domain:    FIN-V1-SUP     (继承 version.code + 后缀)
      sub:     FIN-V1-SUP-01  (继承 domain.code + 序号)
```

### 4.4 YAML 配置方案

```yaml
# domain.yaml 中新增
key_template:
  enabled: true
  auto_generate: true                    # 新建时自动生成
  pattern: "{parent.code}_{SEQ:3}"       # 模板: 前缀_序号
  separator: "_"
  segments:
    - type: parent_field
      source: version_code               # 从 version.code 取值
      transform: upper
      length: 0                          # 不截断
    - type: separator
      value: "_"
    - type: sequence
      name: domain_seq                   # 序列名（全局唯一）
      scope: version_id                  # 按 version 独立编号
      start: 1
      padding: 3                         # 0填充到3位
      step: 1
  preview: "FIN_001"                     # 预览示例
```

### 4.5 序列管理

```yaml
# 内置 _sequences 表（系统表，不在 schema 中暴露）
sequences:
  - name: domain_seq
    scope_field: version_id
    current_value: 15
  - name: service_module_seq
    scope_field: sub_domain_id
    current_value: 42
```

---

## 5. 启用对象（按用户决策）

| 对象 | 模板 | 自动建议 | 用户可变更 | 理由 |
|------|------|---------|-----------|------|
| **business_object** | `{service_module_code}_{SEQ:4}` | ✅ | ✅ | code 字段已有，需规范 |
| **version** | `{product_code}_{SEQ:2}` 或 `{product_code}-{DATE:yyyyMM}` | ✅ | ✅ | code 字段已有，支持语义 |
| **relationship** | `{source_code}-{target_code}-{SEQ:2}` | ✅ | ✅ | **需新增 code 字段** |
| product | - | ❌ | 手动 | 顶层、数量少 |
| domain | - | ❌ | 手动 | 暂不需要模板 |
| sub_domain | - | ❌ | 手动 | 暂不需要模板 |
| service_module | - | ❌ | 手动 | 暂不需要模板 |

### 5.1 relationship 为何需要 code 字段

**现状诊断**: relationship 是系统中**唯一缺少实例级 `code` 字段**的核心业务对象。

| 对象 | code | relationship 有吗 |
|------|------|------------------|
| product | ✅ | - |
| version | ✅ | - |
| domain | ✅ | - |
| sub_domain | ✅ | - |
| service_module | ✅ | - |
| business_object | ✅ | - |
| role | ✅ | - |
| user_group | ✅ | - |
| **relationship** | **❌** | ← 唯一缺的 |

现有"编码"字段分析：

| 字段 | 实际含义 | 能唯一标识实例吗 |
|------|---------|----------------|
| `source_code` | 源 BO 的 code（如 PUM07） | ❌ 多条关系可同源 |
| `target_code` | 目标 BO 的 code（如 PUM14） | ❌ 多条关系可同目标 |
| `relation_code` | 关系**类型**枚举（DEPENDS_ON） | ❌ 同类型可多条 |
| 三字段组合 | source + target + type | ✅ 有唯一索引，但**不可读** |

三字段组合虽能唯一确定一条关系，但不是一个字段，导致：
- 导入导出无法用单一冲突键匹配（当前 `conflict_key: ""` 隐式依赖组合逻辑）
- 图表/拓扑中无法用简短标签标识一条关系
- API 中引用关系没有简洁的路由标识

**需新增**:

```yaml
# relationship.yaml 新增
- id: code
  name: 关系编码
  type: string
  db_column: code
  required: true
  unique: true
  description: 关系实例的唯一编码，由模板自动生成
  semantics:
    meaning: 关系实例编码，格式为 源-目标-序号
    business_key: true
    immutable: true
    examples:
      - ORDER-USER-01
      - ORDER-PRODUCT-02
    data_category: code
    import_visible: true
    export_visible: true
  ui:
    visible: true
    editable: false
```

### 5.2 自动建议 vs 自动生成

**关键设计**: code 字段**自动建议但不强制**，用户可在创建时修改。

```
新建 business_object:
  1. 用户选择 service_module (如 ORDER_SVC)
  2. 系统建议: ORDER_SVC_0001  (基于模板 + 序列)
  3. 用户可修改为: ORDER_SVC_VIP  (或接受建议)
  4. 保存: 最终 code = 用户确认值
```

**实现**: 
- Deep Insert 创建前，先调用 KeyTemplate 生成建议值
- 如果用户提供了 `code`（非空），使用用户值
- 如果用户未提供，使用建议值
- 序列只在用户接受建议值时消耗（用户自定义值不消耗序列）

### 5.3 user_group 和 role：不需要模板

两者已有 `code` 字段，但编码性质决定了**不适合 KeyTemplate**：

| 属性 | role | user_group |
|------|------|-----------|
| code 字段 | `角色编码` | `组编码` |
| business_key | ✅ true | ✅ true |
| immutable | ✅ true | ✅ true |
| pattern | `^[a-z][a-z0-9_]*$` | `^[a-z][a-z0-9_]*$` |

**原因**:

```
role code 的典型值:    admin, editor, viewer, auditor
user_group code 典型值: developers, managers, finance_team
```

这些是**语义编码**，不是序号编码。你希望角色叫 `admin` 而不是 `ROLE_0001`。

| 对比维度 | business_object | user_group / role |
|---------|----------------|-------------------|
| 数量 | 多（几十到几百） | 少（5-15个） |
| 编码性质 | **序列号**（ORDER_0001） | **语义名**（admin, viewer） |
| 规律性 | 有规律（按 service_module 分组编号） | 无规律（完全语义驱动） |
| 适合模板 | ✅ | ❌ |

> **结论**: KeyTemplate 解决的是"大量同类对象需要编号"的问题，不是"给对象起一个有意义的名字"。role 和 user_group 的 code 是名字，不需要模板。

### 5.4 Technical ID 备注

当前所有对象的 `id` 字段均为 SQLite `AUTOINCREMENT` 整数（1, 2, 3...），前端已通过 `f.id !== 'id'` 过滤完全隐藏。

| 评估项 | 结论 |
|--------|------|
| 是否需要改为 UUID/ULID | **暂不需要** — 单机部署无分布式冲突；导入导出以 `code` 做业务键，不受 ID 影响 |
| 是否需要对外 Hash | **暂不需要** — 前端已隐藏，API 也不暴露给用户 |
| 是否有安全风险 | **无** — 权限控制基于 `version_id` 上下文，不依赖 ID 的不可猜测性 |
| 未来考虑 | 多租户/分布式部署时可加一层 API 响应 hash |

## 6. 存量数据与序列号起点

### 6.1 核心问题

```
现有数据: ORDER_0001, ORDER_0002, ORDER_0005, ORDER_0010 (手动输入)
启用模板后: 应该从 ORDER_0011 开始还是 ORDER_0003？
```

**答案: 从 MAX(已有序号) + 1 开始**，避免空洞或冲突。

### 6.2 auto_detect 模式

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| `auto_detect: true`（默认） | 扫描现有 code，提取序号，从 MAX + 1 开始 | 有存量数据 |
| `auto_detect: false, start: N` | 手动指定起始序号 | 重置编号 |
| `auto_detect: false, start: 1` | 从 1 开始 | 全新对象 |

### 6.3 各对象存量场景分析

| 对象 | code 字段现状 | 存量数据 | auto_detect 行为 | 首个建议值 |
|------|-------------|---------|-----------------|-----------|
| **business_object** | ✅ 已有，手动输入 | 有（如 `ORDER_0001`~`ORDER_0010`） | 扫描 MAX(序号)→11 | `ORDER_SVC_0011` |
| **version** | ✅ 已有，手动输入 | 有（如 `SCM_V1`, `SCM_V2`） | 注意：非序号格式的存量 code 会被忽略，从 1 开始 | `SCM_01` |
| **relationship** | ❌ 无 code 字段 | **无存量 code** | 新增字段后所有旧记录 code=NULL，auto_detect 扫描结果为空 → 从 1 开始 | `ORDER-USER-01` |

### 6.4 特殊情况：version 的非序号存量

```
存量 version code: SCM_V1, SCM_V2, FIN_R1  （非纯序号格式）
模板 pattern: {product_code}_{SEQ:2}
auto_detect 扫描:

  对 product_code=SCM:
    扫描 code LIKE 'SCM_%' → SCM_V1, SCM_V2
    extract_sequence_number 无法从 'SCM_V1' 中提取纯数字 → 忽略
    MAX = 0 → 从 1 开始 → 建议 SCM_01

  对 product_code=FIN:
    扫描 code LIKE 'FIN_%' → FIN_R1  
    同上 → MAX = 0 → 从 1 开始 → 建议 FIN_01
```

> **设计原则**: 存量数据中如果 code 格式不符合模板（如手动输入的 `SCM_V1`），auto_detect 会跳过它，从 1 开始。这不会冲突，因为模板格式是 `{product_code}_{SEQ:n}`，和手动输入的 `SCM_V1` 格式完全不同。

### 6.5 relationship 新增 code 后存量处理

```
新增 code 字段: ALTER TABLE relationships ADD COLUMN code TEXT;
存量记录: code = NULL（所有已有关系无 code）

KeyTemplate 首次启用:
  auto_detect 扫描: SELECT code FROM relationships WHERE code LIKE 'ORDER-USER-%'
  结果: 空（所有 code 为 NULL）
  序列起点: 1
  新建议值: ORDER-USER-01

用户创建新关系时:
  自动建议 code = ORDER-USER-01（用户可改）
  旧关系保持 code=NULL（不影响业务）
  
后续补填:
  可提供批量回填脚本，为存量关系按模板补填 code
```

### 6.6 检测逻辑

```python
def detect_sequence_start(table, code_column, pattern_prefix, scope_value):
    """
    扫描存量数据，返回下一个序号
    
    Args:
        table: 数据库表名
        code_column: code 列名
        pattern_prefix: 模板前缀（如 'ORDER_SVC_'）
        scope_value: scope 字段值（如 service_module_code='ORDER_SVC'）
    
    Returns:
        int: 下一个可用序号 (MAX(已有序号) + 1)
    """
    rows = query(
        f"SELECT {code_column} FROM {table} "
        f"WHERE {code_column} LIKE ? AND {code_column} IS NOT NULL",
        [pattern_prefix + '%']
    )
    
    max_seq = 0
    for row in rows:
        code = row[code_column]
        seq_num = extract_sequence_number(code, pattern_prefix)
        if seq_num is not None and seq_num > max_seq:
            max_seq = seq_num
    
    return max_seq + 1

def extract_sequence_number(code, prefix):
    """
    从编码中提取序号部分
    例: 'ORDER_SVC_0011' + prefix='ORDER_SVC_' → 11
         'SCM_V1' + prefix='SCM_' → None（非纯数字，跳过）
    """
    if not code.startswith(prefix):
        return None
    suffix = code[len(prefix):]
    try:
        return int(suffix)
    except ValueError:
        return None
```

**示例**:

```
存量: ORDER_0001, ORDER_0002, ORDER_0005, ORDER_0010
detect: MAX(序号) = 10 → 从 11 开始
下一个建议: ORDER_0011
```

## 7. 实施难度与价值

### 7.1 依赖分析

| 依赖 | 状态 | 说明 |
|------|------|------|
| Formula 引擎 | ✅ 已就绪 | 模板解析 |
| Deep Insert API | ✅ 已就绪 | 自动建议 code |
| CrossObjectResolver | ✅ 已就绪 | 解析 source_code / target_code 引用 |
| MetaField `computation` | ✅ 已就绪 | 虚拟字段计算 |
| 序列存储 | ❌ 需新建 | `_sequences` 系统表 |

### 7.2 难度评估

| 任务 | 难度 | 工作量 |
|------|------|--------|
| YAML 配置解析 | 低 | 小 |
| 序列号引擎 + 存量检测 | 中 | 中 |
| 模板解析器（占位符展开） | 低 | 小 |
| Deep Insert 集成 | 低 | 小 |
| relationship 新增 code 字段 | 低 | 小 |
| 前端 code 字段改为「建议值+可编辑」 | 低 | 小 |
| 序列号并发 + 存量检测 | 中 | 中 |

### 7.3 价值评估

| 场景 | 当前 | KeyTemplate后 |
|------|------|--------------|
| 新建 business_object | 手动输入 `BO_ORDER` | 建议 `ORDER_SVC_0001`，可改 |
| 新建 relationship | 无 code | 自动建议 `ORDER-USER-01` |
| 新建 version | 手动输入 `V1.0` | 建议 `SCM_01` 或自定义 |
| 存量兼容 | - | 从 MAX 已有序号 + 1 开始 |

---

## 8. 实施计划

### Phase 1: 核心引擎

| 任务 | 说明 |
|------|------|
| 1.1 `SequenceEngine` | 序列号生成器，支持 scope 隔离 + 存量 auto_detect + 并发安全 |
| 1.2 `KeyTemplateParser` | 模板解析器，占位符展开 |
| 1.3 `key_template` YAML 配置 | 解析 key_template 配置块（enabled/pattern/segments/auto_suggest） |
| 1.4 序列持久化 | `_sequences` 系统表 |
| 1.5 存量检测 | `auto_detect` 模式：扫描 MAX + 1 |

### Phase 2: 对象集成

| 任务 | 对象 | 说明 |
|------|------|------|
| 2.1 business_object | `{service_module_code}_{SEQ:4}` | code 字段已有 |
| 2.2 relationship | `{source_code}-{target_code}-{SEQ:2}` | **需新增 code 字段** |
| 2.3 version | `{product_code}_{SEQ:2}` | code 字段已有 |
| 2.4 Deep Insert 集成 | 全部 | 创建时自动建议 code |

### Phase 3: 前端适配

| 任务 | 说明 |
|------|------|
| 3.1 auto_suggest 模式 | code 字段显示建议值，可编辑 |
| 3.2 建议值预览 | 输入框旁显示建议值（灰色预填） |
| 3.3 导入导出兼容 | 无 code 时自动建议 |

---

## 12. 实施完成记录 (v1.1)

> **实施日期**: 2026-05-23
> **实施范围**: Phase 1-3 全部完成

### 12.1 实施文件清单

| 文件 | 类型 | 说明 |
|------|:----:|------|
| `meta/core/key_template_engine.py` | 新增 | KeyTemplateEngine + SequenceEngine + KeyTemplateParser |
| `meta/core/models.py` | 修改 | MetaObject 新增 `key_template` 字段 |
| `meta/core/yaml_loader.py` | 修改 | YAML 加载器解析 `key_template` 配置块 |
| `meta/core/interceptors/key_template_interceptor.py` | 新增 | BO 创建时自动生成编码的拦截器 (priority=45) |
| `meta/schemas/business_object.yaml` | 修改 | 新增 `key_template: {service_module_code}_{SEQ:4}` |
| `meta/schemas/version.yaml` | 修改 | 新增 `key_template: {product_code}_{SEQ:2}` |
| `meta/schemas/relationship.yaml` | 修改 | 新增 `code` 字段 + `key_template: {source_code}-{target_code}-{SEQ:2}` |
| `meta/server.py` | 修改 | 注册 KeyTemplateInterceptor + key_template_bp |
| `meta/core/app_builder.py` | 修改 | 注册 KeyTemplateInterceptor + key_template_bp |
| `meta/api/key_template_api.py` | 新增 | 3 个 API 端点 |
| `meta/tests/test_key_template_engine.py` | 新增 | 29 个单元测试 |
| `meta/tests/test_key_template_interceptor.py` | 新增 | 14 个单元测试 |

### 12.2 架构设计

```
┌─────────────────────────────────────────────────────────────────┐
│                     KeyTemplate 架构                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  YAML Schema                    BO Framework Interceptor Chain  │
│  ┌──────────────────────┐       ┌─────────────────────────┐    │
│  │ key_template:         │       │ ContextInterceptor  10  │    │
│  │   enabled: true       │       │ VersionContextInt.  12  │    │
│  │   pattern: "{...}"    │       │ DataPermissionInt.  15  │    │
│  │   segments: [...]     │──────▶│ FieldPolicyInt.     25  │    │
│  │   auto_suggest: true  │       │ EnumProtectionInt.  22  │    │
│  └──────────────────────┘       │ KeyTemplateInt. ◀─ 45  │ NEW│
│         ↓                       │ LockInterceptor     50  │    │
│  meta_object.key_template       │ HierarchyValid.Int. 60  │    │
│         ↓                       │ CascadeInterceptor  70  │    │
│  KeyTemplateConfig.from_dict()  │ QueryInterceptor    80  │    │
│         ↓                       │ AuditInterceptor    90  │    │
│  KeyTemplateEngine.generate()   │ PersistenceInt.     95  │    │
│         ↓                       │ OwnerAutoPerm.Int. 100  │    │
│  context.params['code'] = ...   └─────────────────────────┘    │
│                                                                 │
│  Sequence Engine (Thread-Safe)                                  │
│  ┌─────────────────────────────────────────────┐               │
│  │ _sequences table                             │               │
│  │  INSERT OR IGNORE → UPDATE +1 → SELECT       │               │
│  │  Python threading.Lock                       │               │
│  │  scope 隔离: bo_code_seq:ORDER_SVC           │               │
│  └─────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

### 12.3 启用对象

| 对象 | 模板 | auto_suggest | code 字段 | 状态 |
|------|------|:---:|:---:|:---:|
| business_object | `{service_module_code}_{SEQ:4}` | ✅ | ✅ 已有 | ✅ 已实施 |
| version | `{product_code}_{SEQ:2}` | ✅ | ✅ 已有 | ✅ 已实施 |
| relationship | `{source_code}-{target_code}-{SEQ:2}` | ✅ | ✅ 新增 | ✅ 已实施 |

### 12.4 API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/v2/key-template/config/<object_type>` | 获取对象的 key_template 配置 |
| POST | `/api/v2/key-template/preview/<object_type>` | 预览/生成编码 |
| GET | `/api/v2/key-template/list-objects` | 列出所有启用 KeyTemplate 的对象 |

### 12.5 关键设计决策

1. **无新表** — 复用 `_sequences` 表存储序列号（与定时任务调度共享）
2. **仅 create 时生效** — update 时不自动生成 code，保持 `immutable: true` 语义
3. **用户自定义优先** — 如果用户提供了 code 值，不覆盖
4. **scope 隔离** — 不同 parent_field 值独立编号
5. **并发安全** — Python `threading.Lock` + SQLite 事务

### 12.6 测试覆盖 (52 tests)

| 测试类 | 测试数 | 覆盖范围 |
|--------|:------:|---------|
| TestKeyTemplateParser | 15 | 解析各类 pattern、resolve、scope key |
| TestKeyTemplateConfig | 4 | from_dict 各种配置组合 |
| TestSequenceEngine | 7 | 递增、隔离、重置、auto_detect |
| TestKeyTemplateEngine | 9 | 生成编码、预览、禁用状态、scope |
| TestKeyTemplateInterceptor | 14 | should_execute、before_action 自动生成、跳过、优先级 |
| **合计** | **52** | |

### 12.7 后续优化方向

| 方向 | 说明 | 优先级 |
|------|------|:---:|
| 前端 auto_suggest | code 输入框显示建议值（灰色预填） | P1 |
| 配置 BO 迁移 | pattern 值从 YAML 迁移到 config_values | P2 |
| Record Type 变体 | 同一对象不同 record_type 可用不同模板 | P3 |
| 批量导入兼容 | 无 code 时在导入流程中自动建议 | P2 |

---

## 9. YAML 配置示例

### 9.1 business_object.yaml

```yaml
key_template:
  enabled: true
  auto_suggest: true                     # 自动建议，不强制
  pattern: "{service_module_code}_{SEQ:4}"
  separator: "_"
  segments:
    - type: parent_field
      source: service_module_code
      transform: upper
    - type: separator
      value: "_"
    - type: sequence
      name: bo_code_seq
      scope: service_module_code
      auto_detect: true
      padding: 4
      start: 1
  preview: "ORDER_SVC_0001"
```

### 9.2 version.yaml

```yaml
key_template:
  enabled: true
  auto_suggest: true
  pattern: "{product_code}_{SEQ:2}"
  separator: "_"
  segments:
    - type: parent_field
      source: product_code
      transform: upper
    - type: separator
      value: "_"
    - type: sequence
      name: version_seq
      scope: product_code
      auto_detect: true
      padding: 2
      start: 1
  preview: "SCM_01"
```

### 9.3 relationship.yaml（需新增 code 字段）

```yaml
key_template:
  enabled: true
  auto_suggest: true
  pattern: "{source_code}-{target_code}-{SEQ:2}"
  separator: "-"
  segments:
    - type: parent_field
      source: source_code
    - type: separator
      value: "-"
    - type: parent_field
      source: target_code
    - type: separator
      value: "-"
    - type: sequence
      name: rel_code_seq
      scope: source_code + target_code    # 按 源-目标 组合独立编号
      auto_detect: true
      padding: 2
      start: 1
  preview: "ORDER-USER-01"
```

---

## 10. 结论

### 实施范围

| 对象 | code字段 | 模板 | auto_suggest | 备注 |
|------|---------|------|-------------|------|
| business_object | ✅ 已有 | `{service_module_code}_{SEQ:4}` | ✅ | |
| version | ✅ 已有 | `{product_code}_{SEQ:2}` | ✅ | |
| relationship | ❌ 需新增 | `{source_code}-{target_code}-{SEQ:2}` | ✅ | 新增字段 |

### 关键设计决策

1. **自动建议、用户可变更** — code 不是强制的，用户可以自定义
2. **存量兼容** — `auto_detect: true` 从 MAX(已有序号) + 1 开始
3. **domain/sub_domain/service_module/product 暂不启用** — 暂无需模板
4. **用户自定义 code 不消耗序列号** — 只有接受建议值才递增

---

## 11. 架构思考：YAML 配置与配置BO 的边界

### 11.1 头部产品参考

| 产品 | Schema/结构层 | 配置/实施层 | 数据/操作层 | 边界逻辑 |
|------|-------------|-----------|-----------|---------|
| **Salesforce** | Metadata API（CustomObject, Field, Layout） | Custom Metadata Types（CMDT） | Custom Objects（Data） | Metadata=随代码部署；CMDT=配置记录但可部署；Data=环境独立 |
| **SAP S/4HANA** | DDIC（Domain, DataElement, Table） | Customizing / IMG（配置表） | Master Data + Transactional | DDIC=ABAP字典；Customizing=传输请求可搬运；业务数据=环境独立 |
| **ServiceNow** | sys_dictionary（表/字段定义） | sys_properties / sys_choice | Task / Incident / ... | Dictionary=平台定义；Properties=实例级参数；业务表=操作数据 |

**共同模式**: 三层架构 —— **Schema**（开发者，代码版本化）→ **Configuration**（实施者，可部署但非代码）→ **Data**（用户，环境独立）

### 11.2 黄金规则

```
Rule/Structure → YAML          Value/Preference → Config BO
────────────────────────────────────────────────────────
如果修改它需要 code review  → YAML
如果修改它不需要 code review → Config BO
如果所有环境都一样         → YAML
如果环境间有差异           → Config BO
开发者定义                 → YAML
业务管理员定义             → Config BO
```

### 11.3 当前系统 YAML 内容的归属判定

#### ✅ 明确该留在 YAML（Schema/结构层 — 开发者空间）

| 配置项 | 归属理由 |
|--------|---------|
| 对象定义（id, name, table_name） | Schema 定义，不可变 |
| 字段定义（type, db_column, required, unique） | Schema 结构 |
| 语义标注（business_key, immutable, parent_key） | 模型语义 |
| 关系定义（relations, associations, cardinality） | 模型结构 |
| 索引定义 | 性能优化，随schema变化 |
| 分析模型（measures, dimensions, aggregates） | 数据建模 |
| 审计配置（哪些字段、哪些事件） | 安全/合规 |
| 授权模型（scope, auto_owner） | 安全模型 |
| 删除策略（cascade, restrict） | 数据完整性 |
| 状态机定义（enum_values, transitions） | 业务规则 |
| 计算公式（computation.formula） | 业务逻辑 |
| 级联选择（cascade_select） | UI交互逻辑 |
| **KeyTemplate 配置** | **编码规则，与schema一致** |
| 导入导出策略（conflict_key） | 数据集成规则 |

#### ✅ 已实现为配置BO（实施者空间）

| 配置项 | 实现方式 |
|--------|---------|
| 枚举值（enum_value） | `enum_values` 表，独立 CRUD |
| 菜单/导航（menu） | `menus` 表，`bo_category: configuration` |
| 角色-权限映射 | `role_permission` / `menu_permission` 表 |
| 角色维度范围 | `role_dimension_scope` 表，`bo_category: configuration` |
| 用户-组成员 | `user_group_member` 表 |

#### ⚠️ 灰色地带 — 可讨论

| 配置项 | 当前 | 建议 | 理由 |
|--------|------|------|------|
| UI视图配置（list.columns, detail.facets, form.sections） | YAML | **保持YAML** | 紧密耦合 schema，随字段增减变化，应版本化 |
| 用户自定义列表视图（保存的筛选条件） | `filter_variant` 表 | **保持配置BO** | 用户个人偏好，环境独立 |
| 校验规则（validations） | YAML | **保持YAML** | 业务逻辑=代码，但参数化阈值可抽到配置BO |
| 变更通知配置（change_notification） | YAML | **保持YAML** | 但通知模板内容可抽到配置BO |

### 11.4 未来配置BO扩展路径

```
当前已有:
  enum_type / enum_value  →  枚举管理
  menu                    →  菜单配置
  filter_variant          →  用户筛选偏好
  role_dimension_scope    →  角色维度范围

建议新增:
  system_parameter        →  系统参数（timeout、pageSize默认值、token过期时间）
  notification_template   →  通知模板（邮件/站内信内容）
  business_rule_parameter →  业务规则参数（阈值、限额、有效期天数）
```

### 11.5 设计原则总结

```
┌──────────────────────────────────────────────────────────┐
│  开发者空间                  实施者空间                   │
│  (YAML)                     (配置BO)                     │
│                                                          │
│  Schema定义                  Enum values                 │
│  Field types                 Menu items                  │
│  Business logic (formulas)   Role assignments            │
│  State machines              System parameters           │
│  Validation rules            Notification templates      │
│  Audit policies              Business rule params        │
│  Authorization model         User preferences            │
│  KeyTemplate rules                                       │
│  UI layout structures                                    │
│                                                          │
│  Git versioned               DB versioned                │
│  Code deploy                 可运行时变更                │
│  需code review               无需code review              │
└──────────────────────────────────────────────────────────┘
```

> **核心原则**: 你的系统已经走在了正确的路径上。`BusinessObjectCategory.CONFIGURATION` 枚举 + `bo_category: configuration` 标注已经建立了开发者空间和实施者空间的边界。KeyTemplate 配置放在 YAML 中是正确的 —— 它是 schema 的一部分，不是运行时调参。

### 11.6 深度思考：客户是否能在生产环境通过 YAML 配置？

#### 问题拆解

| 场景 | 谁编辑 | 在哪编辑 | 目标 | 是否有企业产品这么做 |
|------|--------|---------|------|-------------------|
| 开发者配置 | 开发团队 | IDE/Git | CI/CD→生产 | ✅ Salesforce DX, SAP DDIC |
| **客户自服务** | **客户的IT/管理员** | **?** | **生产直接生效** | **❌ 无企业产品允许** |
| GitOps | 客户运维 | Git repo | ArgoCD同步 | ⚠️ Git是中介，不是直接改文件 |

#### 头部企业产品的一致选择

| 产品 | schema定义 | 客户配置渠道 | 客户能直接编辑文件吗 |
|------|-----------|------------|------------------|
| **Salesforce** | 元数据XML（Source Format） | Custom Metadata Types（UI+DB） | ❌ |
| **SAP S/4HANA** | DDIC字典 | IMG/Customizing表 | ❌ |
| **ServiceNow** | sys_dictionary | sys_properties/sys_choice | ❌ |
| **Kubernetes** | CRD YAML | GitOps（ArgoCD） | ❌ (Git是唯一入口) |

**共同逻辑**: schema 文件属于供应商/平台方，客户通过**UI+数据库**或**Git+PR流程**变更配置，**绝不**直接编辑生产服务器的文件。

#### 为什么没有任何企业产品允许客户直接编辑生产环境 YAML

```
┌───────────────────────────────────────────────────────────────┐
│  直接编辑生产YAML的风险                                        │
├───────────────────────────────────────────────────────────────┤
│  ❌ 无审计日志    — 谁在什么时候改了什么？                     │
│  ❌ 无回滚        — 改错了无法 git revert                      │
│  ❌ 无Review      — 没有 PR/MR，无人复核                       │
│  ❌ 无验证        — 缩进错一个空格直接崩溃                     │
│  ❌ 无Diff        — 不知道当前版本与上次版本的差异              │
│  ❌ 环境漂移      — 测试环境与生产环境YAML逐渐不同步            │
│  ❌ 升级冲突      — 新版本覆盖了客户的修改                     │
└───────────────────────────────────────────────────────────────┘
```

#### Salesforce DX 的启示：最近似的正确模式

Salesforce DX 是**唯一**将元数据"文件化"的企业产品，但它有严格的流程：

```
开发者编辑XML → git push → PR review → CI验证 → sfdx deploy → Sandbox → Production
      ↑                                                                    ↑
  开发者在IDE中                                                      不是直接改生产
  不是在生产环境改                                                    经过完整CI/CD
```

客户的自助配置走 **Custom Metadata Types**（类似你的 `enum_value`/`menu` 配置BO），通过 Web UI 操作，存数据库，有审计日志。

#### 双重结论

**对当前阶段**: 你的客户**不应该**直接编辑 `meta/schemas/*.yaml`。你应该沿着现有路径，让 schema 变更走 Code Review + 部署流程，让运行时可调配走配置BO。

**对未来阶段**: 如果客户确实需要深度定制（比如自定义字段、自定义 KeyTemplate），建议借鉴 Salesforce DX 模式：

```
客户定制 YAML 的推荐路径:

  方案A: 配置BO 扩展（推荐，低风险）
    将可定制项做成新的配置BO
    客户通过Web管理界面操作
    例: 自定义 KeyTemplate pattern → config_objects 表

  方案B: GitOps Overlay（高级客户，类似Kustomize）
    meta/schemas/                ← 平台基础schema（vendor）
    meta/overlays/customer-abc/   ← 客户差异overlay（customer）
      business_object.custom.yaml
        key_template:
          pattern: "{service_module_code}_ABC_{SEQ:4}"
    部署: 客户提交 overlay → PR review → CI merge → deploy
    优点: Git审计、可回滚、可review
    复杂度: 需要构建 merge + validation 引擎
```

**当下建议**: 先走稳方案A。你现有的 `BusinessObjectCategory.CONFIGURATION` 已经预留了这扇门。KeyTemplate 的 pattern 如果未来需要客户自定义，做成一个配置BO项，而不是让客户改 YAML。

### 11.7 深度修正：真正的边界不是"开发者 vs 客户"而是"ALTER TABLE vs 纯元数据"

#### 头部产品的关键证据

Salesforce 的公式字段和 ServiceNow 的计算字段**都可以在生产环境直接创建**：

| 产品 | 操作者 | 操作方式 | 是否需要部署 | 底层机制 |
|------|--------|---------|:---:|---------|
| **Salesforce** | Admin | Setup UI → Object Manager → 新建 Formula 字段 | ❌ | 存元数据表，查询时动态计算 |
| **ServiceNow** | Admin | Dictionary Entry → Advanced → 勾选 Calculated → 写脚本 | ❌ | sys_dictionary 属性，运行时执行 |
| **Salesforce 物理字段** | 开发者 | Metadata API deploy | ✅ | 需要 ALTER TABLE |

Salesforce 的 New Field 对话框中，选择 "Formula" 和选择 "Text/Number/Date" 走的是**完全不同的底层路径**：

```
选择 "Text/Number" → 需要写物理列 → Metadata API → Sandbox → Production deploy
选择 "Formula"     → 只写元数据    → Setup UI 直接保存 → 立即生效
```

这是因为公式字段不需要 ALTER TABLE——它只是一条元数据记录，查询时由引擎计算。

#### 修正后的边界模型

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                   │
│  旧边界（不准确）: 开发者空间(YAML) ←→ 实施者空间(配置BO)         │
│                                                                   │
│  新边界（准确）:   需要 ALTER TABLE ←→ 纯元数据无需 ALTER TABLE   │
│                                                                   │
│  实际操作边界:     代码部署(Git+CI/CD) ←→ 运行时变更(Web UI+DB)   │
│                                                                   │
└──────────────────────────────────────────────────────────────────┘
```

#### 对你的系统 YAML 配置的重新分类

| 配置项 | 需要 ALTER TABLE | 可运行时变更 | Salesforce 类比 | 建议归属 |
|--------|:---:|:---:|------|------|
| 新增 stored 字段 + db_column | ✅ | ❌ | Custom Field (Text/Number) | YAML + 部署 |
| 修改字段类型/长度/索引 | ✅ | ❌ | Metadata API only | YAML + 部署 |
| 表名/表结构 | ✅ | ❌ | Object Definition | YAML + 部署 |
| **新增 virtual 字段 + formula** | **❌** | **✅** | **Formula Field** | **可配置BO** |
| **修改 computation.formula** | **❌** | **✅** | **Edit Formula** | **可配置BO** |
| 校验规则 (validation) | ❌ | ✅ | Validation Rule | 可配置BO |
| 状态机定义 (enum_values + transitions) | ❌ | ✅ | Process Builder | 可配置BO |
| UI 布局 (list.columns, form.sections) | ❌ | ✅ | Lightning App Builder | 可配置BO |
| 审计策略 (audit.enabled, events) | ❌ | ✅ | Field History Tracking | 可配置BO |
| KeyTemplate (pattern, segments) | ❌ | ✅ | Auto Number Field | 可配置BO |
| 导入导出策略 (conflict_key) | ❌ | ✅ | External ID config | 可配置BO |
| 权限模型 (authorization) | ❌ | ✅ | Profiles/Permission Sets | 可配置BO |

#### 这些"可配置BO"的前提条件

从 YAML 迁移到运行时配置BO 需要三个基础设施：

| 条件 | 状态 | 说明 |
|------|:---:|------|
| **元数据热加载** | ⚠️ 待验证 | Schema 变更后能否不重启生效？ |
| **前端动态渲染** | ✅ 已有 | MetaListPage/DetailPage 已基于 meta_config 动态渲染 |
| **审计追踪** | ✅ 已有 | audit_log + change_event 已覆盖配置变更 |

#### 更现实的中期路径

```
Phase 1 (现在): 保持所有 schema 在 YAML，走 Git 部署
Phase 2 (中期): 将"纯元数据"项（formula、validation、UI layout）
                开放到配置BO，通过 Web UI 可编辑
                前提: 实现 schema 热加载
Phase 3 (远期): 完整的两层架构
                物理 schema (YAML) → ALTER TABLE → 平台部署
                元数据配置 (Config BO) → Web UI → 客户自助
```

#### 回到 KeyTemplate

KeyTemplate 配置（pattern, segments, auto_detect）**不需要 ALTER TABLE**——它只影响 code 值的计算逻辑，不改变数据库结构。因此它属于「可配置BO」阵营。

**SAP 的自动编号明确在配置级（IMG/SNRO），不在开发级（DDIC）**。Salesforce 的 Auto Number 也可在 Setup UI 调整格式和起始号。

**单一事实原则修正 (v1.1)**：之前的设计使用 "YAML 默认值 + Config BO 覆盖"，但从单一事实原则出发，同一配置项不应在两个地方有值。修正方案：

```
Phase 1 (当前 — YAML 是唯一来源):
  YAML 中定义 key_template 的所有内容（包括 pattern 值）
  YAML 是唯一来源，不存在 DB 覆盖
  通过 Git + Code Review 变更

Phase 2 (Config BO 就绪后 — YAML 和 DB 各司其职):

  YAML (唯一来源 → 引擎定义):
    key_template:
      enabled: true           ← "这个对象需要自动编码"
      auto_suggest: true      ← "建议但不强制"
      segments:               ← "引擎支持这些占位符类型"
        - type: parent_field
        - type: sequence
      auto_detect: true       ← "引擎支持存量检测"
    # 注意: 不含 pattern 具体值

  Config Values / DB (唯一来源 → 配置值):
    部署脚本写入初始值:
      object_id="business_object", config_key="key_template.pattern",
      config_value={"pattern": "{service_module_code}_{SEQ:4}"}

    运行时 Record Type 变体:
      scope='record_type:purchase',
      config_value={"pattern": "PO_{service_module_code}_{SEQ:5}"}

  → YAML 和 DB 定义不同的东西，绝不重叠
  → 对齐 SAP: CDS (定义结构) + IMG 表 (存储值)
  → 对齐 SF: Metadata XML (定义 CMDT 类型) + CMDT records (存储值)
```
