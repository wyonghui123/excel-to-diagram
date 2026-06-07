# SAP与Salesforce字段级权限控制深度分析

## 一、SAP 字段级权限控制方案

### 1. SAP CAP 注解方式

#### (1) @readonly 和 @insertonly

```cds
// 实体级别
service BookshopService {
  @readonly entity Books {...}     // 只读实体
  @insertonly entity Orders {...}  // 只能插入
}

// 字段级别（用于输入验证）
entity SomeEntity {
  @readonly createdAt: Timestamp;  // 只读字段
}
```

**注意**：`@readonly` 在字段级别主要用于**输入验证**，不是安全控制。

#### (2) @Capabilities 注解（OData标准）

```cds
service SomeService {
  @Capabilities: {
    InsertRestrictions.Insertable: true,
    UpdateRestrictions.Updatable: true,
    DeleteRestrictions.Deletable: false
  }
  entity Foo { key ID : UUID }
}
```

#### (3) @restrict 注解（核心权限控制）

```cds
entity Orders @(restrict: [
  { grant: 'READ', to: 'Viewer', where: (buyer = $user) },
  { grant: 'WRITE', to: 'Editor' },
  { grant: '*', to: 'Admin' }
]) {
  // 字段定义
}
```

### 2. SAP HANA 数据脱敏

```sql
-- SAP HANA 数据脱敏函数
SELECT 
    NAME,
    MASK(EMAIL, 'email') AS EMAIL,           -- 邮箱脱敏
    MASK(CREDIT_CARD, 'credit_card') AS CC,  -- 信用卡脱敏
    MASK(PHONE, 'phone') AS PHONE            -- 电话脱敏
FROM CUSTOMER_TABLE;

-- 列级加密
ALTER TABLE CUSTOMER_DATA 
    ALTER (CREDIT_CARD ENCRYPT);
```

### 3. SAP S/4HANA 授权对象字段

```
授权对象结构：
├── 授权字段 (Authorization Fields)
│   ├── ACTVT (活动类型): 01=创建, 02=更改, 03=显示, 06=删除
│   ├── 组织字段: 公司代码、工厂、销售组织
│   └── 业务字段: 供应商组、物料类型
│
└── 字段值范围: From Value → To Value
```

**示例**：
```
授权对象: M_BEST_WRK
字段: WERKS (工厂)
值范围: 1000 → 1999 (可访问1000-1999范围内的工厂)
```

### 4. SAP 个人数据保护（GDPR合规）

```
数据分类：
├── 敏感数据 (Sensitive)
│   ├── 加密存储
│   ├── 访问限制
│   └── 审计日志
│
├── 个人数据 (Personal)
│   ├── 访问控制
│   └── 数据主体权利支持
│
└── 非个人数据 (Non-personal)
    └── 标准访问控制
```

## 二、Salesforce 字段级安全（FLS）

### 1. 核心概念

```
字段级安全 (Field-Level Security, FLS)
├── 可见性 (Visible)
│   └── 用户是否能看到该字段
│
└── 可编辑性 (Editable)
    └── 用户是否能修改该字段
```

### 2. 权限矩阵

```
              │  Visible=True  │  Visible=False
─────────────────────────────────────────────────
Editable=True │  可读可写      │     -
Editable=False│  只读          │   不可见
```

### 3. 配置方式

#### (1) Profile（配置文件）级别

```
Profile: Sales Rep
├── Object: Account
│   ├── Name: Visible, Editable
│   ├── Revenue: Visible, Read-Only
│   └── SSN: Hidden
│
└── Object: Contact
    ├── Email: Visible, Editable
    └── Phone: Visible, Editable
```

#### (2) Permission Set（权限集）级别

```
Permission Set: Finance Access
├── Object: Account
│   └── Revenue: Visible, Editable  (覆盖Profile设置)
│
└── Object: Opportunity
    └── Amount: Visible, Editable
```

### 4. FLS 与 Page Layout 的关系

```
优先级：FLS > Page Layout

Page Layout: 字段在页面上显示
FLS: 字段实际可访问性

如果FLS设置为Hidden，即使Page Layout上有该字段，用户也看不到。
```

### 5. API访问控制

```
FLS同样适用于API访问：
- REST API: 字段不可见时，API响应中不包含该字段
- SOAP API: 字段不可见时，查询结果中该字段为null
- Apex代码: 需要显式检查FLS
```

## 三、对比分析

### 1. 控制维度对比

| 维度 | SAP CAP | Salesforce FLS |
|------|---------|----------------|
| 可见性控制 | `@restrict.where` | Visible (True/False) |
| 可编辑性控制 | `@restrict.grant` | Editable (True/False) |
| 字段级只读 | `@readonly` (输入验证) | Read-Only (安全控制) |
| 敏感数据保护 | MASK函数 + 加密 | 无内置脱敏 |
| 权限继承 | 服务→实体→字段 | Profile + Permission Set |

### 2. 实现方式对比

| 方面 | SAP CAP | Salesforce |
|------|---------|------------|
| **声明方式** | CDS注解 | Profile/Permission Set配置 |
| **粒度** | 实体级 + 条件过滤 | 字段级开关 |
| **动态性** | 支持运行时条件 | 静态配置 |
| **数据脱敏** | 内置MASK函数 | 需自定义实现 |
| **审计** | 需额外配置 | 内置审计日志 |

### 3. 字段属性映射

```
SAP CAP                          Salesforce FLS
─────────────────────────────────────────────────────
@readonly (字段级)          →    Read-Only = True
@restrict.grant='READ'      →    Visible = True, Editable = False
@restrict.grant='WRITE'     →    Visible = True, Editable = True
无权限                      →    Visible = False
MASK()函数                  →    (无内置，需自定义)
```

## 四、对我们的启示

### 1. 借鉴Salesforce FLS的双维度模型

```yaml
# 字段级安全定义
fields:
  - id: cost_amount
    name: 成本金额
    type: decimal
    
    # FLS风格的双维度控制
    fls:
      visible_for: ['read', 'write', 'admin']   # 可见性
      editable_for: ['write', 'admin']          # 可编辑性
      
    # 敏感数据保护
    sensitivity: confidential
    mask_pattern: '******'  # 脱敏显示模式
```

### 2. 借鉴SAP的条件过滤

```yaml
# 实例级权限条件
entity: Orders
restrict:
  - grant: ['READ', 'WRITE']
    to: ['SalesRep']
    where: 'sales_region = $user.region'  # 条件过滤
```

### 3. 综合方案设计

```python
class FieldLevelSecurity:
    """字段级安全控制"""
    
    def get_field_access(self, user_id, object_type, field_id):
        """获取字段访问权限"""
        
        # 1. 获取用户数据权限级别
        data_permission = self.get_data_permission(user_id, object_type)
        
        # 2. 获取字段FLS定义
        fls = self.get_field_fls(object_type, field_id)
        
        # 3. 计算可见性
        visible = data_permission in fls.visible_for
        
        # 4. 计算可编辑性
        editable = data_permission in fls.editable_for
        
        # 5. 处理敏感数据
        if visible and fls.sensitivity:
            if data_permission < fls.min_permission_for_clear:
                masked = True
            else:
                masked = False
        else:
            masked = False
        
        return {
            'visible': visible,
            'editable': editable,
            'masked': masked,
            'readonly': visible and not editable
        }
```

### 4. API响应处理

```python
def filter_response_fields(data, user_id, object_type):
    """根据FLS过滤API响应字段"""
    
    result = {}
    
    for field_id, value in data.items():
        access = get_field_access(user_id, object_type, field_id)
        
        if not access['visible']:
            continue  # 跳过不可见字段
        
        if access['masked']:
            # 应用脱敏
            result[field_id] = mask_value(value, field_id)
        else:
            result[field_id] = value
    
    return result
```

## 五、最佳实践

### 1. 字段分类

```
字段敏感级别分类：
├── Public (公开)
│   └── 所有权限级别可见
│
├── Internal (内部)
│   └── 认证用户可见
│
├── Confidential (机密)
│   └── 编辑权限以上可见，只读权限脱敏
│
└── Restricted (限制)
    └── 管理员可见，其他权限不可见
```

### 2. 权限级别与字段属性映射

```
权限级别     Public    Internal   Confidential   Restricted
─────────────────────────────────────────────────────────────
none        hidden    hidden      hidden         hidden
read        visible   visible     masked         hidden
write       visible   visible     visible        masked
admin       visible   visible     visible        visible
```

### 3. 配置示例

```yaml
# 业务对象字段FLS配置
business_object:
  fields:
    - id: code
      fls:
        visible_for: [read, write, admin]
        editable_for: [write, admin]
      sensitivity: public
      
    - id: name
      fls:
        visible_for: [read, write, admin]
        editable_for: [write, admin]
      sensitivity: public
      
    - id: description
      fls:
        visible_for: [read, write, admin]
        editable_for: [write, admin]
      sensitivity: internal
      
    - id: cost_amount
      fls:
        visible_for: [write, admin]
        editable_for: [admin]
      sensitivity: confidential
      mask_pattern: '***.**'
      
    - id: internal_notes
      fls:
        visible_for: [admin]
        editable_for: [admin]
      sensitivity: restricted
```

## 六、总结

### SAP CAP 特点

1. **声明式权限**：通过注解定义权限
2. **条件过滤**：支持运行时动态条件
3. **数据脱敏**：内置MASK函数
4. **局限性**：字段级权限控制相对简单

### Salesforce FLS 特点

1. **双维度控制**：Visible + Editable
2. **细粒度**：精确到每个字段
3. **配置驱动**：无需编码
4. **全局生效**：影响所有访问方式

### 推荐方案

结合两者优点：
1. **双维度模型**：借鉴Salesforce的Visible/Editable
2. **条件过滤**：借鉴SAP的where条件
3. **敏感数据保护**：借鉴SAP的MASK函数
4. **配置驱动**：通过YAML定义字段FLS
