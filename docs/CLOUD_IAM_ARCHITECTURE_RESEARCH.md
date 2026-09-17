# 云厂商权限架构深入研究报告：AWS / Azure / Google Cloud

> **文档目的**：为企业的权限架构重设计提供业界对标，深入剖析 3 大公有云厂商（AWS、Azure、Google Cloud）的 IAM 体系。
>
> **目标读者**：权限架构师、安全工程师、平台研发团队
>
> **文档版本**：v1.0 | **完成日期**：2026-07-19
>
> **研究方法**：基于官方文档、AWS Glossary、Microsoft Learn、Google Cloud 官方培训资料的系统性研究

---

## 目录

- [0. 研究背景与对照体系](#0-研究背景与对照体系)
- [1. AWS IAM 深度分析](#1-aws-iam-深度分析)
- [2. Azure RBAC 深度分析](#2-azure-rbac-深度分析)
- [3. Google Cloud IAM 深度分析](#3-google-cloud-iam-深度分析)
- [4. 三大云厂商横向对比](#4-三大云厂商横向对比)
- [5. 对我们权限体系重设计的启示](#5-对我们权限体系重设计的启示)
- [6. 参考文档](#6-参考文档)

---

## 0. 研究背景与对照体系

### 0.1 当前我们已有的 9 机制权限体系

我们当前实现了一套 9 机制的权限体系：

| 机制 | 描述 | 对标云厂商概念 |
|------|------|---------------|
| M1 功能权限 | 菜单/按钮/API 级别的功能授权 | AWS IAM Action、Azure Role Actions |
| M2 维度范围白名单 | 数据范围的预定义白名单 | Azure Scope、GCP Resource Hierarchy |
| M3 可见性 | 字段/列级别的可见性控制 | AWS Condition Keys、Azure DataActions |
| M4 Owner 例外 | 资源 Owner 自动获得权限 | AWS Resource-based Policy |
| M5 实例权限 | 具体实例的细粒度授权 | AWS Resource ARN、GCP Resource Path |
| M6 条件规则 | 基于条件的动态授权 | AWS Condition、GCP CEL Conditions |
| M7 M11 YAML RLS | 行级数据权限（Row Level Security） | 类似数据库 RLS，云厂商未直接对标 |
| M8 字段脱敏 | 字段值的脱敏处理 | 类似数据库动态脱敏 |
| M9 Owner 自动授权 | 资源 Owner 自动获得授权 | AWS Resource Owner、GCP Service Account |

### 0.2 研究目标

通过对 AWS、Azure、GCP 3 大云厂商的深入研究，回答以下核心问题：

1. **功能 + 数据统一权限**：云厂商如何把"功能权限"和"数据权限"统一在一个模型中？
2. **多租户 / 跨账号授权**：云厂商如何处理跨账号、跨组织的资源访问？
3. **临时授权**：STS、PIM、Workload Identity 等机制的实现差异？
4. **条件表达式**：AWS Condition Keys、Azure Conditions、GCP CEL 各有什么优劣？
5. **策略评估性能**：策略复杂时如何保证评估性能？缓存机制如何？
6. **资源层级继承**：组织→项目→资源的权限继承机制如何？

---

## 1. AWS IAM 深度分析

### 1.1 概述

AWS IAM（Identity and Access Management）是 AWS 中控制资源访问的核心服务。它采用 **RBAC + ABAC 混合模型**，以 JSON Policy 为核心表达单元，通过严格的评估逻辑（显式拒绝 > 显式允许 > 隐式拒绝）来决定权限。

AWS IAM 的核心特点：

- **9 种 Policy 类型**：基于身份、基于资源、VPC 端点、权限边界、SCP、RCP、ACL、RAM 共享、会话策略
- **50+ 全局条件键** + 数千个服务特定条件键，支持强大的 ABAC
- **STS 临时凭证**：AssumeRole/AssumeRoleWithSAML/AssumeRoleWithWebIdentity 多种联邦方式
- **多账号管理**：通过 AWS Organizations + SCP 实现层级管控
- **策略评估复杂度高**：多达 6 层策略的交叉评估（Organization SCP + RCP + Permission Boundary + Identity Policy + Resource Policy + Session Policy）

### 1.2 4 大核心实体模型

```
┌─────────────────────────────────────────────────────────────┐
│                       AWS Account                            │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ IAM User │    │ IAM Group│    │ IAM Role │              │
│  │  (用户)  │    │  (用户组)│    │  (角色)  │              │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘              │
│       │                │                │                    │
│       │   belongs to   │                │                    │
│       └───────────────►│                │                    │
│       │                │                │ assume             │
│       │                └──────────────►│                    │
│       │                                  │                    │
│       │  attached to (Identity-based)   │                    │
│       ▼                                  ▼                    │
│  ┌──────────────────────────────────────────┐                │
│  │            IAM Policy (JSON)             │                │
│  └──────────────────────────────────────────┘                │
│                                                              │
│  ┌──────────────────────────────────────────┐                │
│  │  Resource-based Policy (e.g. S3 Bucket)  │                │
│  └──────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

#### 1.2.1 IAM User（用户）

- 长期凭证：用户名/密码（控制台）+ Access Key/Secret Key（API）
- 1 个 AWS Account 最多 5000 个 IAM 用户
- 推荐做法：**不使用 IAM User，改用 IAM Role + SSO**
- 一个 IAM User 可以属于多个 Group，可以附加最多 10 个 Managed Policy

#### 1.2.2 IAM Group（用户组）

- 用于批量管理一组 IAM User 的权限
- 不能嵌套（不是树形结构）
- 一个 Group 最多 10 个 Managed Policy
- Inline Policy 单组最大 5120 字符

#### 1.2.3 IAM Role（角色）

- **无长期凭证**，通过 STS AssumeRole 获取临时凭证
- 包含两类 Policy：
  - **Trust Policy**（信任策略）：谁可以 Assume 这个 Role
  - **Permissions Policy**：Role 假设后能做什么
- 最大会话时长 12 小时（可配置 15min-12h）
- 支持 Session Policy（在 AssumeRole 时动态注入额外限制）
- Inline Policy 单 Role 最大 10240 字符

#### 1.2.4 IAM Policy（策略）

- **托管策略（Managed Policy）**：可复用、版本化（最多 5 个版本）、跨身份附加
  - AWS Managed（AWS 维护）
  - Customer Managed（用户自管理）
- **内联策略（Inline Policy）**：与单一身份绑定，删除身份即删除策略
- 托管策略文档大小限制：**6144 字符**（不含空白）

### 1.3 Policy JSON 语法详解

完整的 IAM Policy 由以下元素组成：

```json
{
  "Version": "2012-10-17",
  "Id": "Optional policy identifier",
  "Statement": [
    {
      "Sid": "Optional statement identifier",
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::123456789012:root" },
      "NotPrincipal": { ... },
      "Action": ["s3:GetObject", "s3:PutObject"],
      "NotAction": ["s3:DeleteBucket"],
      "Resource": "arn:aws:s3:::example-bucket/*",
      "NotResource": "arn:aws:s3:::example-bucket/secret/*",
      "Condition": {
        "StringEquals": { "aws:SourceIp": "203.0.113.0/24" },
        "Bool": { "aws:SecureTransport": "true" }
      }
    }
  ]
}
```

#### 1.3.1 BNF 文法（官方定义）

```
policy = {
    "Version": "2012-10-17",
    "Statement": statement_block,
    "Id": policy_id
}

statement_block = statement | [ statement, ... ]
statement = {
    "Sid": sid_string,
    "Effect": effect_string,
    "Principal": principal,
    "Action": action_string_list,
    "Resource": resource_string_list,
    "Condition": condition_block
}

condition_block = "Condition" : { condition_map }
condition_map = {
    condition_type_string : { condition_key_string : condition_value_list },
    ...
}
condition_value_list = [ condition_value, ... ]
condition_value = (condition_value_string | condition_value_string_wildcard)
```

#### 1.3.2 Effect 取值

- `Allow`：允许
- `Deny`：显式拒绝（优先级最高）

#### 1.3.3 Action 通配符

```json
"Action": [
  "s3:Get*",              // 匹配 s3:GetObject, s3:GetBucketAcl 等
  "s3:*",                 // 匹配所有 S3 操作
  "*",                    // 匹配所有服务的所有操作（极度危险）
  "ec2:Describe*"         // 匹配所有 Describe 操作
]
```

### 1.4 ARN（Amazon Resource Name）资源命名

ARN 是 AWS 中标识资源的标准格式：

```
arn:partition:service:region:account-id:resource
arn:partition:service:region:account-id:resource-type/resource-id
arn:partition:service:region:account-id:resource-type:resource-id
```

实际示例：

```
# S3 存桶（无 region）
arn:aws:s3:::my-corporate-bucket
arn:aws:s3:::my-corporate-bucket/*

# EC2 实例
arn:aws:ec2:us-east-1:123456789012:instance/i-1234567890abcdef0

# IAM 用户
arn:aws:iam::123456789012:user/JohnDoe

# Lambda 函数
arn:aws:lambda:us-east-1:123456789012:function:my-function

# DynamoDB 表
arn:aws:dynamodb:us-east-1:123456789012:table/my-table

# KMS Key
arn:aws:kms:us-east-1:123456789012:key/abc123-...
```

ARN 通配符使用：

```json
"Resource": [
  "arn:aws:s3:::my-bucket/*",                       // 桶内所有对象
  "arn:aws:ec2:us-east-1:123456789012:instance/*",  // 所有 EC2 实例
  "arn:aws:iam::123456789012:role/ProjectA-*"       // ProjectA 前缀的所有 Role
]
```

### 1.5 Condition Keys（条件键）

AWS 提供 50+ 全局条件键 + 数千个服务特定条件键，是 ABAC 的核心机制。

#### 1.5.1 全局条件键分类

| 类别 | 关键键名 | 用途 |
|------|----------|------|
| **主体属性** | `aws:PrincipalArn`、`aws:PrincipalAccount`、`aws:PrincipalOrgID`、`aws:PrincipalOrgPaths`、`aws:PrincipalTag/<tag-key>`、`aws:PrincipalIsAWSService`、`aws:PrincipalServiceName` | 标识请求者 |
| **会话属性** | `aws:userid`、`aws:username`、`aws:MultiFactorAuthPresent`、`aws:MultiFactorAuthAge`、`aws:PrincipalType` | 会话上下文 |
| **网络属性** | `aws:SourceIp`、`aws:SourceVpc`、`aws:SourceVpce`、`aws:SourceVpcSourceIp`、`aws:VpcSourceIp` | 网络位置控制 |
| **资源属性** | `aws:ResourceTag/<tag-key>`、`aws:ResourceAccount`、`aws:ResourceOrgID`、`aws:ResourceOrgPaths` | 基于资源属性 |
| **请求属性** | `aws:RequestedRegion`、`aws:CurrentTime`、`aws:EpochTime`、`aws:RequestTag/<tag-key>`、`aws:TagKeys` | 请求元信息 |
| **跨服务防混淆** | `aws:SourceArn`、`aws:SourceAccount` | Confused Deputy 防护 |

#### 1.5.2 条件运算符

| 类别 | 运算符 | 说明 |
|------|--------|------|
| **String** | `StringEquals`、`StringNotEquals`、`StringEqualsIgnoreCase`、`StringLike`、`StringNotLike` | 字符串比较，支持 `*` `?` 通配符 |
| **Numeric** | `NumericEquals`、`NumericNotEquals`、`NumericLessThan`、`NumericLessThanEquals`、`NumericGreaterThan`、`NumericGreaterThanEquals` | 数值比较 |
| **Date** | `DateEquals`、`DateNotEquals`、`DateLessThan`、`DateLessThanEquals`、`DateGreaterThan`、`DateGreaterThanEquals` | 日期比较（ISO 8601 或 epoch） |
| **Bool** | `Bool` | 布尔比较 |
| **IpAddress** | `IpAddress`、`NotIpAddress` | IPv4/IPv6 CIDR |
| **Arn** | `ArnEquals`、`ArnLike`、`ArnNotEquals`、`ArnNotLike` | ARN 比较 |
| **集合** | `ForAllValues`、`ForAnyValue` | 多值集合运算 |
| **条件变体** | `...IfExists` | 键不存在时视为 true |

#### 1.5.3 ABAC 实战示例

**场景**：开发者只能操作标记了与其同 Project 标签的资源

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowStartInstancesWithMatchingProjectTag",
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:RebootInstances"
      ],
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Project": "${aws:PrincipalTag/Project}"
        }
      }
    },
    {
      "Sid": "AllowDescribeInstances",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus"
      ],
      "Resource": "*"
    }
  ]
}
```

**优势**：新增 Project 不需要改 Policy，只需要打标签。

#### 1.5.4 高级条件组合

```json
"Condition": {
  "StringEquals": {
    "aws:PrincipalTag/Department": "Engineering"
  },
  "StringLike": {
    "aws:PrincipalTag/Project": "ProjectA*"
  },
  "IpAddress": {
    "aws:SourceIp": ["10.0.0.0/8", "192.168.0.0/16"]
  },
  "Bool": {
    "aws:MultiFactorAuthPresent": "true"
  },
  "NumericLessThan": {
    "aws:MultiFactorAuthAge": "3600"
  }
}
```

逻辑关系：**多个 condition_type_string 之间是 AND**，**同一 condition_type_string 内的多个 key 也是 AND**，**同一 key 的多个 value 是 OR**。

### 1.6 Permission Boundary（权限边界）

**Permission Boundary 是一个托管策略，用作 IAM 实体（用户或角色）的权限上限**。它不授予权限，只限制最大权限。

#### 1.6.1 评估公式

```
EffectivePermission = (IdentityBasedPolicy ∩ PermissionBoundary)
                    ∪ ResourceBasedPolicy
                    - ExplicitDeny
                    ∩ SCP (Organization level)
                    ∩ SessionPolicy (if any)
```

#### 1.6.2 使用场景

- **开发者自服务**：允许开发者创建 IAM Role，但限制最大权限不超过 ReadAllPlusS3
- **多租户场景**：每个租户的 IAM 实体被 Boundary 限制
- **职责分离**：DevOps 工程师可以管理 IAM，但不能突破预设边界

**示例 Boundary Policy**：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "MaximumPermissions",
      "Effect": "Allow",
      "Action": [
        "s3:*",
        "dynamodb:*",
        "lambda:*",
        "cloudwatch:*",
        "logs:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyIAM",
      "Effect": "Deny",
      "Action": "iam:*",
      "Resource": "*"
    },
    {
      "Sid": "DenyKMS",
      "Effect": "Deny",
      "Action": "kms:*",
      "Resource": "*"
    }
  ]
}
```

### 1.7 SCP（Service Control Policy）

SCP 是 AWS Organizations 级别的策略，用于定义账户内 IAM 实体的**最大权限边界**。SCP 不授予权限，只限制。

#### 1.7.1 Organizations 层级

```
Organization (Root)
├── OU "Production"
│   ├── Account "Prod-App1"
│   ├── Account "Prod-App2"
│   └── OU "Production-Databases"
│       └── Account "Prod-DB"
├── OU "Staging"
│   └── Account "Staging-App1"
└── OU "Sandbox"
    └── Account "Sandbox-Dev1"
```

SCP 评估规则：

- SCP 在每个层级附加，最多 5 个 SCP/层级
- 每个账户的最终 SCP = Root SCP ∩ OU SCP ∩ 子 OU SCP ∩ Account SCP
- SCP 评估**先于** Identity-based Policy

#### 1.7.2 典型 SCP 示例

**强制区域限制**：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyNonApprovedRegions",
      "Effect": "Deny",
      "NotAction": [
        "cloudfront:*",
        "iam:*",
        "route53:*",
        "support:*"
      ],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestedRegion": ["us-east-1", "us-west-2", "eu-west-1"]
        }
      }
    }
  ]
}
```

**禁止删除资源**：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyDeleteResources",
      "Effect": "Deny",
      "Action": [
        "ec2:TerminateInstances",
        "rds:DeleteDBInstance",
        "s3:DeleteBucket",
        "dynamodb:DeleteTable"
      ],
      "Resource": "*",
      "Condition": {
        "StringNotEquals": {
          "aws:PrincipalTag/Role": "BreakGlass"
        }
      }
    }
  ]
}
```

### 1.8 Resource-based Policy vs Identity-based Policy

| 维度 | Identity-based Policy | Resource-based Policy |
|------|----------------------|----------------------|
| **附加位置** | IAM Identity（User/Group/Role） | AWS Resource（S3 桶、KMS Key、SQS 队列、Lambda 函数） |
| **包含 Principal** | 不需要（隐含附加的身份） | 必须包含 `Principal` 字段 |
| **跨账号能力** | 不能直接授予跨账号权限 | 可以授予跨账号权限 |
| **典型例子** | 用户附加的 Managed Policy | S3 Bucket Policy、KMS Key Policy、IAM Role Trust Policy |
| **评估规则** | 必须 Allow | 同账号：Identity 或 Resource Allow 即可；跨账号：两者都必须 Allow |

#### 1.8.1 跨账号访问评估矩阵

| Same Account | Identity Allow | Resource Allow | Result |
|--------------|----------------|----------------|--------|
| Yes | Yes | Yes | Allow |
| Yes | Yes | No | Allow（资源策略不要求）|
| Yes | No | Yes | Allow（身份策略不要求，同账号）|
| Yes | No | No | Implicit Deny |
| No | Yes | Yes | Allow |
| No | Yes | No | Implicit Deny |
| No | No | Yes | Implicit Deny |

### 1.9 ABAC 支持

AWS 通过 Condition Keys 实现完整的 ABAC：

- `aws:PrincipalTag/<key>`：主体标签
- `aws:ResourceTag/<key>`：资源标签
- `aws:RequestTag/<key>`：请求中携带的标签（用于创建资源时强制打标签）
- `aws:TagKeys`：请求中的所有标签键

**强制资源打标签的示例**：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RequireTagsOnCreate",
      "Effect": "Deny",
      "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "StringNotEquals": {
          "aws:RequestTag/CostCenter": "*"
        }
      }
    },
    {
      "Sid": "RequireCostCenterAndOwner",
      "Effect": "Deny",
      "Action": "ec2:RunInstances",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "Null": {
          "aws:RequestTag/CostCenter": "true",
          "aws:RequestTag/Owner": "true"
        }
      }
    }
  ]
}
```

### 1.10 STS（Security Token Service）临时凭证

AWS STS 提供 6 种 AssumeRole 变体，覆盖各种联邦身份场景：

| API | 适用场景 | 凭证时长 |
|-----|----------|---------|
| `AssumeRole` | 同账号或跨账号 AssumeRole | 15min-12h |
| `AssumeRoleWithSAML` | 企业 SAML SSO（AD FS、Okta） | 15min-12h |
| `AssumeRoleWithWebIdentity` | OAuth/OIDC IdP（Google、Facebook、Amazon Cognito） | 15min-12h |
| `GetFederationToken` | 自定义身份 Broker | 15min-36h |
| `GetSessionToken` | MFA 强制要求场景（不能跨账号） | 15min-12h |
| `GetCallerIdentity` | 仅返回当前调用者身份，不获取凭证 | N/A |

#### 1.10.1 跨账号 AssumeRole 完整示例

**Account A 的 Role Trust Policy（被信任方）**：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:root"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "unique-external-id-from-account-b"
        },
        "Bool": {
          "aws:MultiFactorAuthPresent": "true"
        }
      }
    }
  ]
}
```

**Account B 的 Identity Policy（信任方）**：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::222222222222:role/CrossAccountReadOnlyRole"
    }
  ]
}
```

#### 1.10.2 Session Policy（会话策略）

AssumeRole 时可以传入 Session Policy，进一步缩小权限：

```python
import boto3

sts_client = boto3.client('sts')

session_policy = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::specific-bucket/specific-prefix/*"
        }
    ]
}

response = sts_client.assume_role(
    RoleArn="arn:aws:iam::123456789012:role/MyRole",
    RoleSessionName="MySession",
    DurationSeconds=3600,
    Policy=json.dumps(session_policy)  # Session Policy
)

# 最终权限 = Role 的 Permissions Policy ∩ Session Policy
```

### 1.11 实际 Policy 示例

#### 1.11.1 S3 跨账号访问（Resource-based Policy）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowCrossAccountRead",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111111111111:role/DataReaderRole"
      },
      "Action": [
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::shared-data-bucket",
        "arn:aws:s3:::shared-data-bucket/*"
      ],
      "Condition": {
        "StringEquals": {
          "aws:PrincipalTag/Department": "Analytics"
        },
        "IpAddress": {
          "aws:SourceIp": "10.0.0.0/8"
        }
      }
    },
    {
      "Sid": "DenyInsecureTransport",
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        "arn:aws:s3:::shared-data-bucket/*",
        "arn:aws:s3:::shared-data-bucket"
      ],
      "Condition": {
        "Bool": {
          "aws:SecureTransport": "false"
        }
      }
    }
  ]
}
```

#### 1.11.2 EC2 实例管理（ABAC）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ManageInstancesByTeam",
      "Effect": "Allow",
      "Action": [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:RebootInstances",
        "ec2:TerminateInstances"
      ],
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Team": "${aws:PrincipalTag/Team}"
        }
      }
    },
    {
      "Sid": "ViewAllInstances",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:DescribeTags"
      ],
      "Resource": "*"
    },
    {
      "Sid": "DenyTerminateProduction",
      "Effect": "Deny",
      "Action": "ec2:TerminateInstances",
      "Resource": "arn:aws:ec2:*:*:instance/*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Environment": "production"
        }
      }
    }
  ]
}
```

#### 1.11.3 RDS 数据库访问（Condition + Resource ARN）

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowRDSRead",
      "Effect": "Allow",
      "Action": [
        "rds:DescribeDBInstances",
        "rds:DescribeDBSnapshots",
        "rds:ListTagsForResource"
      ],
      "Resource": "*"
    },
    {
      "Sid": "AllowModifySpecificDB",
      "Effect": "Allow",
      "Action": [
        "rds:ModifyDBInstance",
        "rds:RebootDBInstance"
      ],
      "Resource": "arn:aws:rds:us-east-1:123456789012:db:prod-db-*",
      "Condition": {
        "StringEquals": {
          "aws:ResourceTag/Project": "ProjectA"
        },
        "DateGreaterThan": {
          "aws:CurrentTime": "2026-07-01T00:00:00Z"
        },
        "DateLessThan": {
          "aws:CurrentTime": "2026-07-31T23:59:59Z"
        }
      }
    },
    {
      "Sid": "DenyDeleteRDS",
      "Effect": "Deny",
      "Action": [
        "rds:DeleteDBInstance",
        "rds:DeleteDBCluster"
      ],
      "Resource": "*"
    }
  ]
}
```

### 1.12 权限评估流程（伪代码）

```python
def evaluate_iam_request(request):
    """
    AWS IAM 权限评估算法（简化版）
    
    评估顺序：
    1. 显式 Deny 检查（任意层级）
    2. Organization SCP 评估
    3. Permission Boundary 评估
    4. Identity-based Policy 评估
    5. Resource-based Policy 评估
    6. Session Policy 评估（如果存在）
    
    最终决策 = 通过所有层级 AND
    """
    
    # Step 1: 收集所有相关策略
    scp_policies = collect_scps(request.account_id, request.org_path)
    rcp_policies = collect_rcps(request.account_id, request.org_path)
    permission_boundary = get_permission_boundary(request.principal)
    identity_policies = get_identity_policies(request.principal)  # 包含 Group 的
    resource_policies = get_resource_policies(request.resource)
    session_policy = request.session_policy  # 可能为空
    
    # Step 2: 显式 Deny 检查（贯穿所有层级）
    for policy in (scp_policies + rcp_policies + permission_boundary 
                   + identity_policies + resource_policies + session_policy):
        if has_explicit_deny(policy, request.action, request.resource, request.context):
            return DENY
    
    # Step 3: SCP 评估（必须 Allow）
    if not scp_allows(scp_policies, request.action, request.resource, request.context):
        return IMPLICIT_DENY
    
    # Step 4: RCP 评估
    if not rcp_allows(rcp_policies, request.action, request.resource, request.context):
        return IMPLICIT_DENY
    
    # Step 5: Permission Boundary 评估（必须 Allow）
    if permission_boundary and not boundary_allows(
            permission_boundary, request.action, request.resource, request.context):
        return IMPLICIT_DENY
    
    # Step 6: Identity-based Policy 评估
    identity_allow = identity_allows(
        identity_policies, request.action, request.resource, request.context)
    
    # Step 7: Resource-based Policy 评估
    resource_allow = resource_allows(
        resource_policies, request.action, request.resource, request.context)
    
    # Step 8: 跨账号访问规则
    if request.is_cross_account:
        # 跨账号访问：Identity 和 Resource 都必须 Allow
        if not (identity_allow and resource_allow):
            return IMPLICIT_DENY
    else:
        # 同账号：Identity 或 Resource Allow 即可
        if not (identity_allow or resource_allow):
            return IMPLICIT_DENY
    
    # Step 9: Session Policy 评估（如果存在）
    if session_policy and not session_allows(
            session_policy, request.action, request.resource, request.context):
        return IMPLICIT_DENY
    
    return ALLOW
```

### 1.13 审计与合规（CloudTrail）

- **CloudTrail**：默认记录所有 API 调用（管理事件），可开启数据事件（S3/Lambda）
- **IAM Access Analyzer**：分析资源策略，发现外部可访问的资源
- **IAM Policy Simulator**：模拟测试 Policy 效果
- **Last Accessed Information**：分析 IAM 实体最近访问的资源，用于最小权限收敛
- **Access Analyzer Policy Generation**：基于 CloudTrail 数据自动生成最小权限策略

CloudTrail 事件示例：

```json
{
  "eventVersion": "1.08",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROAEXAMPLE:dev-session",
    "arn": "arn:aws:sts::123456789012:assumed-role/DevRole/dev-session",
    "sessionContext": {
      "sessionIssuer": {
        "type": "Role",
        "arn": "arn:aws:iam::123456789012:role/DevRole"
      },
      "attributes": {
        "mfaAuthenticated": "true",
        "creationDate": "2026-07-19T10:00:00Z"
      }
    }
  },
  "eventSource": "s3.amazonaws.com",
  "eventName": "GetObject",
  "requestParameters": {
    "bucketName": "my-corporate-bucket",
    "key": "data/file.json"
  },
  "sourceIPAddress": "203.0.113.10",
  "awsRegion": "us-east-1",
  "eventTime": "2026-07-19T10:05:30Z"
}
```

### 1.14 性能与规模

- **策略评估延迟**：通常 < 200ms，对于复杂策略可能到 500ms
- **策略缓存**：评估结果在 STS 会话期间缓存
- **策略大小限制**：托管策略 6144 字符，单身份最多 10 个 Managed Policy
- **策略评估配额**：单次评估最多 ~500 个 Policy Statement
- **优化建议**：
  - 使用 ABAC 减少策略数量（一个策略替代多个）
  - 避免使用 `*` 通配符 + `StringLike` 组合（性能差）
  - 用 Policy Simulator 提前验证

### 1.15 最佳实践

1. **最小权限原则**：从无权限开始，按需添加
2. **使用 IAM Role 替代 IAM User**：避免长期凭证
3. **ABAC 替代 RBAC**：用标签实现可扩展的权限管理
4. **Permission Boundary 必须使用**：限制 IAM 实体最大权限
5. **SCP 防止账户级事故**：如限制区域、限制服务
6. **STS 跨账号访问优先于 IAM User**：临时凭证优于长期凭证
7. **强制 MFA**：敏感操作要求 `aws:MultiFactorAuthPresent = true`
8. **IAM Access Analyzer 持续审计**：发现过度授权

---

## 2. Azure RBAC 深度分析

### 2.1 概述

Azure RBAC（Role-Based Access Control）是 Azure 资源管理器的核心授权系统。它基于 **Role Definition + Role Assignment + Scope 三元组**模型，与 Microsoft Entra ID（原 Azure AD）深度集成，并通过 Azure Policy 进行补充。

Azure RBAC 的核心特点：

- **角色驱动**：权限以 Role 形式打包，不能单独授予权限
- **层级继承**：Management Group → Subscription → Resource Group → Resource 4 级继承
- **数据/控制平面分离**：`Actions`/`NotActions` 是控制平面，`DataActions`/`NotDataActions` 是数据平面
- **PIM Just-In-Time**：特权角色按需激活
- **Managed Identity**：Azure 资源自动获得身份
- **Azure Policy 与 RBAC 互补**：RBAC 管"谁能做什么"，Policy 管"什么配置是允许的"

### 2.2 Role Definition 结构

完整的 Role Definition JSON：

```json
{
  "assignableScopes": [
    "/subscriptions/{subscription-id}",
    "/providers/Microsoft.Management/managementGroups/{mg-id}"
  ],
  "description": "Custom role for application developers",
  "id": "/subscriptions/{subscription-id}/providers/Microsoft.Authorization/roleDefinitions/{role-definition-id}",
  "name": "{role-definition-id}",
  "permissions": [
    {
      "actions": [
        "Microsoft.Compute/virtualMachines/read",
        "Microsoft.Compute/virtualMachines/write",
        "Microsoft.Storage/storageAccounts/read",
        "Microsoft.Network/virtualNetworks/read"
      ],
      "dataActions": [
        "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read",
        "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write"
      ],
      "notActions": [
        "Microsoft.Compute/virtualMachines/delete"
      ],
      "notDataActions": [
        "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/delete"
      ]
    }
  ],
  "roleName": "Application Developer",
  "roleType": "CustomRole",
  "type": "Microsoft.Authorization/roleDefinitions",
  "condition": "@Resource[Microsoft.Storage/storageAccounts/blobServices/containers/name] StringLike 'app-*'",
  "conditionVersion": "2.0"
}
```

#### 2.2.1 权限字符串格式

```
{Company}.{ProviderName}/{resourceType}/{action}
```

示例：

| 权限字符串 | 说明 |
|-----------|------|
| `Microsoft.Compute/virtualMachines/read` | 读取 VM |
| `Microsoft.Compute/virtualMachines/write` | 创建/更新 VM |
| `Microsoft.Compute/virtualMachines/delete` | 删除 VM |
| `Microsoft.Compute/*` | 所有 Compute 操作 |
| `Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read` | 读取 Blob 数据 |
| `*/read` | 读取所有控制平面资源 |

#### 2.2.2 控制平面 vs 数据平面

| 维度 | 控制平面 (Management Plane) | 数据平面 (Data Plane) |
|------|---------------------------|---------------------|
| 字段 | `Actions` / `NotActions` | `DataActions` / `NotDataActions` |
| 操作对象 | 资源管理（创建/读取/更新/删除资源） | 数据访问（读取 Blob、查询数据库） |
| 通过 ARM API | 是 | 是（部分通过） |
| 示例 | `Microsoft.Storage/storageAccounts/write` | `Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read` |

#### 2.2.3 AssignableScopes（可分配范围）

```json
"assignableScopes": [
  "/"                                                      // 整个 Azure（仅内置角色可用）
  "/providers/Microsoft.Management/managementGroups/abc"   // 管理组级别
  "/subscriptions/{sub-id}"                                // 订阅级别
  "/subscriptions/{sub-id}/resourceGroups/{rg-name}"       // 资源组级别
  "/subscriptions/{sub-id}/resourceGroups/{rg-name}/providers/Microsoft.Compute/virtualMachines/{vm-name}"  // 资源级别
]
```

### 2.3 Role Assignment 三元组

每个 Role Assignment 是 `(Principal, Role, Scope)` 三元组：

```json
{
  "id": "/subscriptions/{sub-id}/providers/Microsoft.Authorization/roleAssignments/{assignment-id}",
  "name": "{assignment-id}",
  "type": "Microsoft.Authorization/roleAssignments",
  "properties": {
    "roleDefinitionId": "/subscriptions/{sub-id}/providers/Microsoft.Authorization/roleDefinitions/{role-id}",
    "principalId": "{user-or-group-or-service-principal-object-id}",
    "principalType": "User",
    "scope": "/subscriptions/{sub-id}/resourceGroups/{rg-name}",
    "condition": "@Resource[Microsoft.Storage/storageAccounts/blobServices/containers/name] StringLike 'project-a-*'",
    "conditionVersion": "2.0",
    "createdOn": "2026-07-19T10:00:00Z",
    "updatedOn": "2026-07-19T10:00:00Z",
    "createdBy": "{principal-id}",
    "updatedBy": "{principal-id}"
  }
}
```

`principalType` 取值：

- `User`：用户
- `Group`：组
- `ServicePrincipal`：服务主体
- `ManagedIdentity`：托管身份
- `ForeignGroup`：外部组

### 2.4 Scope 层级（4 级继承）

```
Tenant Root Management Group
└── Management Group "Production"
    └── Subscription "Prod-Subscription"
        └── Resource Group "Production-RG"
            └── Resource "my-vm" (Microsoft.Compute/virtualMachines)
```

#### 2.4.1 继承规则

- 上级 Scope 的 Role Assignment **自动继承**到下级
- 子级权限 = 上级权限 ∪ 自身权限（**累积**）
- **不能减权**：在下级 Scope 不能 deny 上级 Scope 的权限
  - 解决方案：使用 Azure Policy（deny action）或 Deny Assignment
- 单个 Subscription 最多 2000 个 Role Assignment（可申请提升到 5000）

#### 2.4.2 实战示例

```bash
# 在管理组级别分配 Reader 角色
az role assignment create \
  --role "Reader" \
  --assignee "user@contoso.com" \
  --scope "/providers/Microsoft.Management/managementGroups/Production"

# 在资源组级别分配 Contributor
az role assignment create \
  --role "Contributor" \
  --assignee-object-id "12345678-1234-1234-1234-123456789012" \
  --assignee-principal-type "Group" \
  --scope "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/Production-RG"

# 在资源级别分配 Virtual Machine Contributor
az role assignment create \
  --role "Virtual Machine Contributor" \
  --assignee "user@contoso.com" \
  --scope "/subscriptions/12345678-1234-1234-1234-123456789012/resourceGroups/Production-RG/providers/Microsoft.Compute/virtualMachines/my-vm"
```

### 2.5 Built-in Roles vs Custom Roles

#### 2.5.1 关键内置角色

| 角色 | 关键权限 | 用途 |
|------|---------|------|
| **Owner** | `*/*` + `Microsoft.Authorization/*/Write` | 完全控制，可授权 |
| **Contributor** | `*/*` 但不能授权 | 完全控制，但不能授权 |
| **Reader** | `*/read` | 只读 |
| **User Access Administrator** | `Microsoft.Authorization/*/Write` | 仅授权管理 |
| **Virtual Machine Contributor** | VM 相关操作 | VM 管理 |
| **Storage Account Contributor** | 存储账户管理 | 存储账户管理 |
| **Key Vault Administrator** | KV 全部操作 | KV 管理 |
| **Security Admin** | 安全策略管理 | 安全管理 |

**注意**：Owner / User Access Administrator 是特权角色，应通过 PIM 管理。

#### 2.5.2 Custom Roles 限制

- 单租户最多 5000 个自定义角色
- 单角色定义文档大小：≤ 8 KB
- 必须指定 `assignableScopes`，限制可分配范围
- 支持版本管理（保留最多 5 个历史版本）

### 2.6 Azure Policy（与 RBAC 互补）

Azure Policy 是 **资源合规性** 控制，与 RBAC 互补：

| 维度 | Azure RBAC | Azure Policy |
|------|-----------|--------------|
| **目的** | 控制"谁能做什么" | 控制"什么配置是允许的" |
| **评估时机** | 授权时 | 创建/更新资源时 |
| **作用对象** | Principal | Resource |
| **效果** | Allow / Deny | Deny / Audit / Append / Modify / DeployIfNotExists / Disabled |
| **继承性** | 累积（不能减权） | 覆盖（Policy 可强制下级合规） |

#### 2.6.1 Policy 定义示例

```json
{
  "properties": {
    "displayName": "Allowed locations for resources",
    "policyType": "BuiltIn",
    "mode": "Indexed",
    "description": "This policy enables you to restrict the locations your organization can specify when deploying resources.",
    "parameters": {
      "listOfAllowedLocations": {
        "type": "Array",
        "metadata": {
          "displayName": "Allowed locations",
          "description": "The list of locations that can be specified when deploying resources.",
          "strongType": "location"
        }
      }
    },
    "policyRule": {
      "if": {
        "field": "location",
        "notIn": "[parameters('listOfAllowedLocations')]"
      },
      "then": {
        "effect": "deny"
      }
    }
  }
}
```

#### 2.6.2 Policy Initiative（倡议）

```json
{
  "properties": {
    "displayName": "ISO 27001:2013",
    "policyType": "BuiltIn",
    "parameters": { ... },
    "policyDefinitions": [
      {
        "policyDefinitionId": "/providers/Microsoft.Authorization/policyDefinitions/...",
        "parameters": { ... }
      },
      ...
    ]
  }
}
```

### 2.7 PIM（Privileged Identity Management）

PIM 是 Azure 的 **Just-In-Time 特权访问管理**，让特权角色按需激活。

#### 2.7.1 PIM 关键概念

| 概念 | 说明 |
|------|------|
| **Eligible Assignment**（符合条件） | 用户被分配了角色，但需要激活才能使用 |
| **Active Assignment**（活跃分配） | 用户被分配角色并处于激活状态 |
| **Activation**（激活） | 临时启用 Eligible 角色，需要 MFA/审批 |
| **Maximum Duration** | 激活时长上限（默认 8h，可配置） |
| **Approval Workflow** | 激活需审批 |
| **Access Review** | 定期审查角色分配 |
| **Notification** | 激活/分配时通知管理员 |

#### 2.7.2 PIM 激活流程

```
1. 用户在 PIM 门户请求激活 Owner 角色
   ↓
2. PIM 校验：
   - 用户是 Eligible 吗？
   - 在激活时段内吗？（如工作时间）
   - 需要 MFA 吗？
   - 需要审批吗？
   ↓
3. MFA 验证
   ↓
4. （可选）审批流程
   ↓
5. 激活成功，分配 Active Role Assignment
   ↓
6. 在 Duration 到期后自动撤销
   ↓
7. 全程审计日志记录
```

#### 2.7.3 PIM 配置示例（PowerShell）

```powershell
# 配置 Owner 角色的 PIM 策略
$roleDefinitionId = "/subscriptions/{sub-id}/providers/Microsoft.Authorization/roleDefinitions/8e3af657-a8ff-443c-a75c-2fe8c4bcb635"  # Owner

# 设置最大激活时长 1 小时，要求 MFA，要求审批
$scope = "/subscriptions/{sub-id}"
$policy = @{
  "properties" = @{
    "rules" = @(
      @{
        "ruleType" = "EnablementRule"
        "enabledRules" = @("MultiFactorAuthentication", "Justification", "Ticketing")
      },
      @{
        "ruleType" = "ExpirationRule"
        "maximumDuration" = "PT1H"  # 1 小时
      },
      @{
        "ruleType" = "ApprovalRule"
        "setting" = @{
          "isApprovalRequired" = $true
          "approvalStages" = @(
            @{
              "primaryApprovers" = @(
                @{
                  "id" = "{security-team-object-id}"
                  "type" = "Group"
                }
              )
            }
          )
        }
      }
    )
  }
}

Invoke-AzRestMethod -Method PUT -Path "$scope/providers/Microsoft.Authorization/roleManagementPolicies/Owner" -Payload ($policy | ConvertTo-Json -Depth 10)
```

#### 2.7.4 PIM 的优势

- **降低攻击面**：Microsoft 数据显示，使用 PIM 6 个月内特权相关安全事件减少 75%
- **强制零信任**：每个特权操作都需要显式激活
- **审计完整性**：所有激活事件都记录到 Audit Log

### 2.8 Managed Identity（托管身份）

Managed Identity 是 Azure 资源自动获得的身份，无需管理凭证：

| 类型 | 说明 | 用途 |
|------|------|------|
| **System-assigned** | 与资源 1:1 绑定，删除资源即删除身份 | 单资源访问 |
| **User-assigned** | 独立资源，可关联到多个资源 | 多资源共享身份 |

#### 2.8.1 使用流程

```csharp
// Azure SDK for .NET
using Azure.Identity;
using Azure.Security.KeyVault.Secrets;

// 在 Azure VM 上运行的代码
var credential = new DefaultAzureCredential();  // 自动使用 Managed Identity
var client = new SecretClient(
    new Uri("https://myvault.vault.azure.net/"),
    credential);

KeyVaultSecret secret = await client.GetSecretAsync("my-secret");
```

#### 2.8.2 优势

- **无凭证泄漏风险**：Azure 平台自动管理凭证轮换
- **支持 RBAC**：可分配任何 Azure Role
- **支持多种 Azure 服务**：VM、App Service、Function、Container Apps、AKS 等

### 2.9 Azure AD Conditional Access（条件访问）

Conditional Access 是 Entra ID 的策略引擎，基于信号做访问决策：

```
Signal              → Decision            → Enforcement
─────────────────    ─────────────────     ─────────────
User risk            Block                 MFA
Sign-in risk         Allow                 Password change
Device compliance    Require MFA           Terms of use
Location             Require password      Session controls
App sensitivity      change                (limited permissions)
Client app           Require approved app
                     Terms of use
```

#### 2.9.1 条件访问策略示例

```json
{
  "displayName": "Require MFA for admins",
  "state": "enabled",
  "conditions": {
    "users": {
      "includeRoles": [
        "62e90394-69f5-4237-9190-012177145e10",  // Global Administrator
        "194ae4cb-b126-40b2-bd5b-6091b380977d"   // Application Administrator
      ]
    },
    "applications": {
      "includeAllApplications": true
    },
    "locations": {
      "includeLocations": ["All"],
      "excludeLocations": ["trusted-networks"]
    }
  },
  "grantControls": {
    "operator": "AND",
    "builtInControls": ["mfa"]
  }
}
```

### 2.10 实际配置示例

#### 2.10.1 自定义角色（完整 JSON）

```json
{
  "assignableScopes": [
    "/subscriptions/12345678-1234-1234-1234-123456789012"
  ],
  "description": "Read blobs from app-* containers only, with condition",
  "permissions": [
    {
      "actions": [
        "Microsoft.Storage/storageAccounts/read",
        "Microsoft.Storage/storageAccounts/blobServices/containers/read"
      ],
      "dataActions": [
        "Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"
      ],
      "notActions": [],
      "notDataActions": []
    }
  ],
  "roleName": "App Blob Reader",
  "roleType": "CustomRole",
  "condition": "@Resource[Microsoft.Storage/storageAccounts/blobServices/containers/name] StringLike 'app-*' && @Resource[Microsoft.Storage/storageAccounts/blobServices/containers/blobs/path] StringLike 'documents/*'",
  "conditionVersion": "2.0"
}
```

#### 2.10.2 Condition（条件表达式）

Azure Role Assignment Condition 使用 **Azure Role Definition Language**：

```
@Principal[Microsoft.DirectoryServices/Groups/id] StringEquals '...'
@Resource[Microsoft.Storage/storageAccounts/blobServices/containers/name] StringLike 'app-*'
@Request[Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags:Project] StringEquals 'ProjectA'
@Principal[Microsoft.DirectoryServices/user/objectId] StringEquals '...'
```

操作符：`StringEquals`、`StringNotEquals`、`StringLike`、`StringNotLike`、`StringEqualsIgnoreCase`、`NumericEquals`、`NumericGreaterThan`、`NumericLessThan`、`DateTimeEquals`、`DateTimeLessThan`、`Exists`、`!Exists`

### 2.11 权限评估流程（伪代码）

```python
def evaluate_azure_rbac_request(principal, action, scope, resource=None):
    """
    Azure RBAC 权限评估算法
    
    评估顺序：
    1. 检查 Deny Assignment（优先级最高）
    2. 收集所有适用的 Role Assignment（继承自上级 Scope）
    3. 检查 Role Definition 中的 Actions/DataActions
    4. 检查 Condition（如果存在）
    5. PIM 状态检查（如果是 Eligible Assignment，需要检查激活状态）
    6. Azure Policy 评估（独立流程，针对资源配置）
    """
    
    # Step 1: 检查 Deny Assignment（不可被覆盖）
    deny_assignments = get_deny_assignments(principal, scope)
    for da in deny_assignments:
        if action_matches(da.deny_actions, action) or action_matches(da.deny_data_actions, action):
            return DENY
    
    # Step 2: 收集所有 Role Assignment（沿 Scope 链向上）
    role_assignments = []
    current_scope = scope
    while current_scope:
        ras = get_role_assignments(principal, current_scope)
        role_assignments.extend(ras)
        current_scope = parent_scope(current_scope)
    
    # Step 3: 评估每个 Role Assignment
    allow = False
    for ra in role_assignments:
        # PIM 状态检查
        if ra.is_eligible and not ra.is_active:
            continue  # Eligible 但未激活，跳过
        
        role_def = get_role_definition(ra.role_definition_id)
        
        # 检查 Actions
        if is_data_action(action):
            if action_in_list(action, role_def.data_actions) and not action_in_list(action, role_def.not_data_actions):
                # 检查 Condition
                if ra.condition:
                    if evaluate_condition(ra.condition, principal, resource, action):
                        allow = True
                else:
                    allow = True
        else:
            if action_in_list(action, role_def.actions) and not action_in_list(action, role_def.not_actions):
                if ra.condition:
                    if evaluate_condition(ra.condition, principal, resource, action):
                        allow = True
                else:
                    allow = True
    
    if not allow:
        return IMPLICIT_DENY
    
    # Step 4: Azure Policy 评估（独立流程）
    # Note: Policy 评估在资源 CRUD 时触发，不是 RBAC 评估的一部分
    # 但效果上会叠加
    return ALLOW
```

### 2.12 审计与合规

- **Azure Activity Log**：所有控制平面操作
- **Azure Diagnostic Settings**：可以导出到 Log Analytics、Storage、Event Hub
- **Microsoft Entra Audit Log**：Entra ID 相关操作（登录、角色分配等）
- **PIM Audit History**：PIM 激活历史
- **Azure Resource Graph**：跨订阅查询资源
- **Microsoft Defender for Cloud**：安全态势管理

Activity Log 事件示例：

```json
{
  "authorization": {
    "action": "Microsoft.Compute/virtualMachines/write",
    "scope": "/subscriptions/12345678-.../resourceGroups/MyRG/providers/Microsoft.Compute/virtualMachines/my-vm"
  },
  "caller": "user@contoso.com",
  "eventTimestamp": "2026-07-19T10:05:30.1234567Z",
  "operationName": {
    "value": "Microsoft.Compute/virtualMachines/write",
    "localizedValue": "Create or Update Virtual Machine"
  },
  "resourceGroup": "MyRG",
  "status": {
    "value": "Succeeded",
    "localizedValue": "Succeeded"
  },
  "submissionTimestamp": "2026-07-19T10:06:00Z"
}
```

### 2.13 性能与规模

- **Role Assignment 评估延迟**：通常 < 100ms（有缓存）
- **缓存机制**：每个 Subscription 缓存 Role Assignment，约 30 分钟刷新
- **Scope 限制**：
  - 单 Subscription 最多 2000 Role Assignment（默认）
  - 单 Management Group 最多 500 Role Assignment
  - 可申请提升到 5000
- **优化建议**：
  - 优先使用 Group 而非 User 进行 Role Assignment（减少 Assignment 数量）
  - 利用 Scope 继承，避免重复 Assignment
  - 使用 Azure Policy 而非 Role 实现"配置合规"

### 2.14 最佳实践

1. **最小权限**：从 Reader 开始，逐步添加
2. **使用 Group 管理权限**：把用户加入 Group，对 Group 分配 Role
3. **PIM 管理特权**：所有 Owner / User Access Administrator 必须走 PIM
4. **Managed Identity 替代 Service Principal**：避免凭证管理
5. **Azure Policy 强制合规**：用 Policy 实现"必须打标签"、"必须加密"等
6. **条件访问**：对所有敏感应用启用 MFA
7. **定期 Access Review**：每季度审查 Role Assignment
8. **Avoid Owner 角色滥用**：单 Subscription 最多 3 个 Owner

---

## 3. Google Cloud IAM 深度分析

### 3.1 概述

Google Cloud IAM 采用 **Allow/Deny 双策略模型**，与 Google Cloud Resource Hierarchy 深度集成。它的核心特点是：

- **Allow Policy + Deny Policy 双轨制**：Deny 优先，Allow 累积
- **CEL（Common Expression Language）条件表达式**：比 AWS Condition 更强大灵活
- **资源层级继承**：Organization → Folder → Project → Resource，权限向下继承
- **Workload Identity Federation**：无 Service Account Key 跨云访问
- **Service Account Impersonation**：通过短凭证链替代长期凭证
- **Policy Intelligence**：Policy Analyzer、Policy Troubleshooter、Recommender 等工具链

### 3.2 IAM Policy 结构

#### 3.2.1 Allow Policy（允许策略）

```json
{
  "version": 1,
  "etag": "BwUjMhCsNvY=",
  "bindings": [
    {
      "role": "roles/storage.objectViewer",
      "members": [
        "user:alice@example.com",
        "group:data-readers@example.com",
        "serviceAccount:reader-sa@my-project.iam.gserviceaccount.com"
      ]
    },
    {
      "role": "roles/storage.objectAdmin",
      "members": [
        "user:bob@example.com"
      ],
      "condition": {
        "title": "BusinessHoursAccess",
        "description": "Access only during business hours",
        "expression": "request.time.getHours('America/Los_Angeles') >= 9 && request.time.getHours('America/Los_Angeles') <= 17"
      }
    }
  ]
}
```

#### 3.2.2 Deny Policy（拒绝策略）

```json
{
  "name": "projects/my-project/denyPolicies/my-policy",
  "etag": "abc123",
  "denyRule": {
    "deniedPrincipals": [
      "user:*@contractor.example.com"
    ],
    "deniedPermissions": [
      "storage.objects.delete",
      "storage.objects.create"
    ],
    "exceptionPrincipals": [
      "user:admin@example.com"
    ],
    "condition": {
      "expression": "resource.type == 'storage.googleapis.com/Object' && resource.name.startsWith('projects/_/buckets/sensitive-')"
    }
  }
}
```

**Deny 评估规则**：Deny 总是优先于 Allow，被 Deny 的主体无法通过 Allow 恢复。

### 3.3 Member（主体）类型

| 类型 | 格式 | 说明 |
|------|------|------|
| Google Account | `user:alice@example.com` | 单个 Google 用户 |
| Service Account | `serviceAccount:sa@project.iam.gserviceaccount.com` | 服务账号 |
| Google Group | `group:devs@example.com` | Google 群组 |
| Cloud Identity / Workspace Domain | `domain:example.com` | 整个域 |
| All Authenticated Users | `allAuthenticatedUsers` | 所有已认证用户 |
| All Users | `allUsers` | 公开访问（含匿名） |
| Workload Identity Pool | `principalSet://iam.googleapis.com/locations/global/workloadIdentityPools/{pool}/*` | 外部工作负载身份 |
| Workforce Identity Pool | `principalSet://iam.googleapis.com/locations/global/workforcePools/{pool}/*` | 外部员工身份 |

### 3.4 Resource Hierarchy（4 级资源层级）

```
Organization (顶级)
├── Folder "Production"
│   ├── Folder "App-A"
│   │   ├── Project "app-a-prod"
│   │   │   ├── Compute Engine Instance
│   │   │   ├── Cloud Storage Bucket
│   │   │   └── BigQuery Dataset
│   │   └── Project "app-a-staging"
│   └── Folder "App-B"
│       └── Project "app-b-prod"
├── Folder "Non-Production"
│   ├── Project "sandbox-1"
│   └── Project "sandbox-2"
└── Project "shared-services"  (直接挂在 Org 下)
```

#### 3.4.1 继承规则

- **权限累积**：子级继承父级所有 IAM Policy，且自身 Policy 也生效
- **不能减权**：在下级不能直接 Deny 上级的 Allow（**重要差异**）
  - **解决方案 1**：在上级 Scope 使用 Deny Policy
  - **解决方案 2**：使用 Organization Policy 限制
- **最佳实践**：在尽可能高的层级赋权，在尽可能低的层级精确控制

### 3.5 Predefined Roles vs Custom Roles

#### 3.5.1 Predefined Roles 示例

| Role | 权限数 | 描述 |
|------|--------|------|
| `roles/viewer` | 数百个 `*.list` `*.get` | 查看所有资源 |
| `roles/editor` | 数千个 | 编辑所有资源（不含 IAM 管理） |
| `roles/owner` | 所有 + IAM 管理 | 完全控制 |
| `roles/storage.objectViewer` | `storage.objects.get` `storage.objects.list` | 查看对象 |
| `roles/storage.objectAdmin` | 对象 CRUD | 管理对象 |
| `roles/compute.instanceAdmin.v1` | Compute 实例管理 | 管理 VM |
| `roles/iam.serviceAccountUser` | `iam.serviceAccounts.actAs` | 使用 SA |
| `roles/resourcemanager.organizationAdmin` | Org 管理 | Org 管理员 |

#### 3.5.2 Custom Roles

```bash
# 创建自定义角色
gcloud iam roles create myAppDeveloper --organization=1234567890 \
  --title="My App Developer" \
  --description="Custom role for app developers" \
  --permissions=compute.instances.start,compute.instances.stop,storage.objects.create,storage.objects.list \
  --stage=GA
```

```yaml
title: "My App Developer"
description: "Custom role for app developers"
stage: "GA"
includedPermissions:
  - compute.instances.start
  - compute.instances.stop
  - compute.instances.get
  - storage.objects.create
  - storage.objects.list
  - storage.objects.get
```

**限制**：单 Organization 最多 300 个 Custom Role，单 Role 最多 3000 个权限。

### 3.6 IAM Conditions（CEL 表达式）

CEL（Common Expression Language）是 GCP IAM Conditions 的核心，比 AWS Condition 运算符更强大。

#### 3.6.1 CEL 基础语法

```cel
// 时间条件
request.time.getHours('America/Los_Angeles') >= 9
&& request.time.getHours('America/Los_Angeles') <= 17

// 日期条件
request.time.getFullYear() == 2026
&& request.time.getMonth() >= 6  // July+

// 资源属性
resource.type == 'storage.googleapis.com/Object'
resource.name.startsWith('projects/_/buckets/my-bucket/objects/public/')
resource.labels.env == 'production'

// 请求属性
request.path.startsWith('/v1/projects/my-project')
request.host == 'storage.googleapis.com'

// 主体属性（来自 Security Token）
request.auth.claims['aud'] == 'my-audience'
request.auth.claims.email.endsWith('@example.com')

// 复杂组合
(resource.type == 'storage.googleapis.com/Object'
 && resource.name.startsWith('projects/_/buckets/sensitive-'))
|| (request.auth.claims['email'].endsWith('@internal.example.com')
 && request.time.getHours('UTC') >= 9
 && request.time.getHours('UTC') <= 17)
```

#### 3.6.2 资源 vs 请求条件

- **Resource-based condition**：基于资源属性（标签、名称、类型）
- **Request-based condition**：基于请求属性（时间、IP、用户）

#### 3.6.3 实战示例

```json
{
  "role": "roles/storage.objectAdmin",
  "members": ["group:devs@example.com"],
  "condition": {
    "title": "ProjectTaggedResourcesDuringBusinessHours",
    "expression": "resource.matchTag('env', 'production') && request.time.getHours('America/New_York') >= 9 && request.time.getHours('America/New_York') <= 17 && request.time.getDayOfWeek('America/New_York') >= 1 && request.time.getDayOfWeek('America/New_York') <= 5"
  }
}
```

### 3.7 Workload Identity Federation

Workload Identity Federation 让外部工作负载（AWS、Azure、on-prem、GitHub Actions）无需 Service Account Key 即可访问 GCP。

#### 3.7.1 工作原理

```
1. External Workload (AWS EC2 / GitHub Actions / Azure VM)
   │
   │ 1. 获取原生身份凭证
   │    (AWS IAM Role, GitHub OIDC, Azure Managed Identity)
   ▼
2. 调用 GCP STS (Security Token Service)
   - 提交外部凭证
   - Workload Identity Pool 配置了信任规则
   ▼
3. STS 验证凭证，返回 Federated Token
   ▼
4. (可选) 调用 IAM Credentials API
   - 用 Federated Token 模拟 Service Account
   - 获取 GCP Access Token
   ▼
5. 用 GCP Access Token 访问 GCP 资源
```

#### 3.7.2 配置示例（GitHub Actions）

```bash
# 1. 创建 Workload Identity Pool
gcloud iam workload-identity-pools create "github-pool" \
  --location="global" \
  --display-name="GitHub Actions Pool"

# 2. 创建 OIDC Provider
gcloud iam workload-identity-pools providers create-oidc "github-provider" \
  --location="global" \
  --workload-identity-pool="github-pool" \
  --display-name="GitHub Provider" \
  --issuer-uri="https://token.actions.githubusercontent.com" \
  --attribute-mapping="google.subject=assertion.sub,repository=assertion.repository,ref=assertion.ref" \
  --attribute-condition="assertion.repository == 'my-org/my-repo'"

# 3. 允许 GitHub Actions impersonate Service Account
gcloud iam service-accounts add-iam-policy-binding \
  github-deployer@my-project.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-pool/attribute.repository/my-org/my-repo"

# 4. GitHub Actions workflow 使用
# (.github/workflows/deploy.yml)
```

```yaml
name: Deploy to Cloud Run
on:
  push:
    branches: [main]

permissions:
  id-token: write  # 关键：允许 OIDC

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: google-github-actions/auth@v3
        with:
          workload_identity_provider: "projects/123456789/locations/global/workloadIdentityPools/github-pool/providers/github-provider"
          service_account: "github-deployer@my-project.iam.gserviceaccount.com"
      - uses: google-github-actions/deploy-cloudrun@v3
        with:
          service: my-service
          region: us-central1
```

### 3.8 Service Account Impersonation

Service Account Impersonation 让一个 SA（或用户）通过短凭证链模拟另一个 SA：

```bash
# 用户 alice@... 被授予 Service Account User
gcloud iam service-accounts add-iam-policy-binding \
  target-sa@my-project.iam.gserviceaccount.com \
  --member="user:alice@example.com" \
  --role="roles/iam.serviceAccountUser"

# Alice 现在可以生成 target-sa 的 Access Token
gcloud auth print-access-token \
  --impersonate-service-account=target-sa@my-project.iam.gserviceaccount.com
```

#### 3.8.1 链式 Impersonation

```
User → SA1 (短凭证) → SA2 (短凭证) → SA3 (实际访问)
```

**优势**：

- **可审计**：每层 Impersonation 都记录在 Audit Log
- **限制传播**：通过 Condition 限制可 Impersonate 的 SA
- **凭证短生命周期**：默认 1 小时

### 3.9 Policy Analyzer / Policy Troubleshooter

#### 3.9.1 Policy Analyzer

```bash
# 查询谁有 storage.objects.delete 权限
gcloud asset analyze-iam-policy --scope=projects/my-project \
  --permissions="storage.objects.delete" \
  --format=json

# 查询 alice@example.com 能访问哪些资源
gcloud asset analyze-iam-policy --scope=projects/my-project \
  --identities="user:alice@example.com" \
  --format=json

# 查询谁访问了 my-bucket
gcloud asset analyze-iam-policy --scope=projects/my-project \
  --full-resource-name="//storage.googleapis.com/projects/_/buckets/my-bucket" \
  --format=json
```

#### 3.9.2 Policy Troubleshooter

诊断"为什么用户 X 无法访问资源 Y"：

```bash
gcloud iam policy-troubleshoot \
  "//storage.googleapis.com/projects/_/buckets/my-bucket" \
  --permissions="storage.objects.get" \
  --principal-email="alice@example.com" \
  --format=json
```

返回：

```json
{
  "access": "DENIED",
  "explainedPolicies": [
    {
      "bindingExplanations": [
        {
          "access": "MAYBE",
          "role": "roles/storage.objectViewer",
          "membership": "MEMBERSHIP_INCLUDED",
          "condition": {
            "expression": "request.time.getHours('UTC') >= 9",
            "evaluation": "FALSE"  // 时间条件不满足
          }
        }
      ]
    }
  ]
}
```

### 3.10 实际配置示例

#### 3.10.1 完整的 Project IAM Policy

```json
{
  "version": 1,
  "etag": "BwUjMhCsNvY=",
  "bindings": [
    {
      "role": "roles/owner",
      "members": ["group:admins@example.com"]
    },
    {
      "role": "roles/editor",
      "members": ["group:developers@example.com"],
      "condition": {
        "title": "BusinessHours",
        "description": "Allow edit only during business hours",
        "expression": "request.time.getHours('America/New_York') >= 9 && request.time.getHours('America/New_York') <= 17 && request.time.getDayOfWeek('America/New_York') >= 1 && request.time.getDayOfWeek('America/New_York') <= 5"
      }
    },
    {
      "role": "roles/storage.objectViewer",
      "members": ["user:viewer@example.com"],
      "condition": {
        "title": "PublicObjectsOnly",
        "expression": "resource.name.startsWith('projects/_/buckets/my-bucket/objects/public/')"
      }
    },
    {
      "role": "roles/compute.instanceAdmin.v1",
      "members": ["group:devops@example.com"],
      "condition": {
        "title": "ProductionOnly",
        "expression": "resource.labels.env == 'production'"
      }
    },
    {
      "role": "roles/iam.serviceAccountUser",
      "members": ["user:alice@example.com"],
      "condition": {
        "title": "ProjectSpecificSA",
        "expression": "resource.name.endsWith('@my-project.iam.gserviceaccount.com')"
      }
    }
  ]
}
```

#### 3.10.2 Organization Policy 约束

```yaml
# 限制资源只能创建在特定区域
constraint: constraints/gcp.resourceLocations
listPolicy:
  allowedValues:
    - "in:us-locations"
    - "in:europe-locations"

# 禁止创建 Service Account Key
constraint: constraints/iam.disableServiceAccountKeyCreation
booleanPolicy:
  enforced: true

# 限制外部成员（防止外部用户加入项目）
constraint: constraints/iam.allowedPolicyMemberDomains
listPolicy:
  allowedValues:
    - "C1234567890"  # Cloud Identity customer ID
```

### 3.11 权限评估流程（伪代码）

```python
def evaluate_gcp_iam_request(principal, permission, resource, request_context):
    """
    GCP IAM 权限评估算法
    
    评估顺序：
    1. 收集所有 Deny Policy（沿资源层级向上）
    2. 检查 Deny（如果命中则直接 Deny）
    3. 收集所有 Allow Policy（沿资源层级向上）
    4. 检查 Allow Policy 是否包含此 principal + permission
    5. 评估 Condition
    6. 检查 Organization Policy（针对资源配置）
    """
    
    # Step 1: 收集 Deny Policy（沿资源层级向上）
    deny_policies = []
    current = resource
    while current:
        deny_policies.extend(get_deny_policies(current))
        current = parent_resource(current)
    
    # Step 2: 检查 Deny
    for policy in deny_policies:
        rule = policy.deny_rule
        if principal_matches(principal, rule.denied_principals):
            if permission_matches(permission, rule.denied_permissions):
                if principal_not_in_exceptions(principal, rule.exception_principals):
                    if rule.condition is None or evaluate_cel(rule.condition, request_context):
                        return DENY
    
    # Step 3: 收集 Allow Policy（沿资源层级向上）
    allow_policies = []
    current = resource
    while current:
        allow_policies.extend(get_allow_policies(current))
        current = parent_resource(current)
    
    # Step 4 & 5: 检查 Allow Policy
    for policy in allow_policies:
        for binding in policy.bindings:
            if principal_in_binding(principal, binding.members):
                if permission_in_role(permission, binding.role):
                    if binding.condition:
                        if evaluate_cel(binding.condition.expression, request_context, resource, principal):
                            return ALLOW
                    else:
                        return ALLOW
    
    # Step 6: 隐式拒绝
    return IMPLICIT_DENY
```

### 3.12 审计与合规

- **Cloud Audit Logs**：分 Admin Activity（默认开启）、Data Access（需配置）、System Event
- **Cloud Logging**：统一日志管理
- **Policy Intelligence**：基于 ML 的权限分析
  - **Policy Analyzer**：查询"谁有 X 权限"
  - **Policy Troubleshooter**：诊断"为什么 X 不能访问 Y"
  - **Policy Recommender**：自动推荐最小权限
  - **IAM Recommender**：基于使用数据推荐移除角色
- **Access Transparency**：Google 员工访问您数据的日志

Audit Log 示例：

```json
{
  "protoPayload": {
    "@type": "type.googleapis.com/google.cloud.audit.AuditLog",
    "authenticationInfo": {
      "principalEmail": "alice@example.com",
      "serviceAccountDelegationInfo": [
        {
          "firstPartyPrincipal": {
            "principalEmail": "github-deployer@my-project.iam.gserviceaccount.com"
          }
        }
      ]
    },
    "requestMetadata": {
      "callerIp": "203.0.113.10",
      "callerSuppliedUserAgent": "gcloud/..."
    },
    "serviceName": "storage.googleapis.com",
    "methodName": "storage.objects.get",
    "resourceName": "projects/_/buckets/my-bucket/objects/file.json"
  },
  "resource": {
    "type": "gcs_bucket",
    "labels": {
      "bucket_name": "my-bucket",
      "project_id": "my-project"
    }
  },
  "timestamp": "2026-07-19T10:05:30.123456Z",
  "severity": "INFO"
}
```

### 3.13 性能与规模

- **策略评估延迟**：通常 < 50ms（有缓存）
- **缓存机制**：每个资源缓存其 IAM Policy，约 5-10 分钟刷新
- **限制**：
  - 单 Organization 最多 1500 个 Custom Role
  - 单资源最多 1500 个 binding
  - 单 Project IAM Policy 大小：32 KB
  - 单 condition 表达式长度：1024 字符
- **优化建议**：
  - 在上级层级赋权，避免在下级重复
  - 使用 Group 而非单个 user
  - 用 Policy Analyzer 定期清理多余授权
  - 用 IAM Recommender 自动收敛

### 3.14 最佳实践

1. **避免使用 Basic Role**（Owner/Editor/Viewer）：用 Predefined Role 替代
2. **优先在 Folder/Org 赋权**：减少重复
3. **使用 Workload Identity Federation**：消除 Service Account Key
4. **Service Account Impersonation**：让短期凭证链替代长期凭证
5. **用 Deny Policy 设护栏**：在 Org 级别 Deny 危险操作
6. **Organization Policy 强制合规**：限制区域、限制资源类型
7. **用 CEL Condition 实现细粒度控制**：基于时间、资源属性
8. **启用 Policy Intelligence**：自动优化权限

---

## 4. 三大云厂商横向对比

### 4.1 整体对比表

| 维度 | AWS IAM | Azure RBAC | Google Cloud IAM |
|------|---------|-----------|------------------|
| **权限模型** | RBAC + ABAC 混合（以 Action+Resource 为核心） | RBAC（以 Role 为核心） | RBAC + ABAC（以 binding 为核心） |
| **Policy 语法** | JSON（Statement 数组） | JSON（Role Definition） | JSON（bindings 数组） |
| **Policy 类型数** | 9 种 | 1 种 + Azure Policy | 4 种（Allow/Deny/PAB/Org Policy） |
| **条件表达式** | Condition 运算符（StringEquals, IpAddress...） | Azure Role Condition（@Resource/@Principal） | CEL 表达式 |
| **资源层级** | Organization → OU → Account → Resource | MGroup → Subscription → RG → Resource | Organization → Folder → Project → Resource |
| **层级继承** | SCP 沿层级生效（限制），Identity Policy 不继承 | Role Assignment 沿层级累积继承 | IAM Policy 沿层级累积继承 |
| **多账号** | AWS Organizations + STS AssumeRole | Management Group + Entra ID | Organization + Service Account Impersonation |
| **临时凭证** | STS（AssumeRole 6 种变体） | PIM（激活 Eligible 角色） | STS（Workload Identity） + Impersonation |
| **审计** | CloudTrail | Activity Log + Entra Audit | Cloud Audit Logs |
| **Deny 优先级** | 任意层级显式 Deny 总是优先 | Deny Assignment 优先 | Deny Policy 优先于 Allow |
| **跨账号授权** | Resource-based Policy 或 STS | Entra ID 跨租户 / Lighthouse | Service Account Impersonation |
| **托管身份** | IAM Role for EC2/Lambda | Managed Identity（System/User-assigned） | Service Account（Compute Engine/GKE） |
| **工具链** | IAM Access Analyzer, Policy Simulator | Defender for Cloud, PIM, Access Review | Policy Analyzer, Troubleshooter, Recommender |

### 4.2 权限模型对比

#### 4.2.1 RBAC 程度

- **Azure > GCP > AWS**
- Azure 是最纯粹的 RBAC，所有权限必须通过 Role 拥有，且 Role 是预打包的权限集合
- GCP 也是 RBAC，但通过 CEL Condition 提供 ABAC 能力
- AWS 是 RBAC + ABAC 混合，Condition Keys 提供强大 ABAC

#### 4.2.2 ABAC 能力

- **GCP（CEL） > AWS（Condition Keys） > Azure（Conditions）**
- GCP 的 CEL 表达式最灵活，支持复杂逻辑、函数调用
- AWS 的 Condition Keys 数量最多（50+ 全局 + 数千个服务特定），但语法相对简单
- Azure 的 Conditions 较新，仍在发展中

### 4.3 Policy 语法复杂度对比

#### 4.3.1 AWS Policy（中等复杂度）

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::bucket/*",
    "Condition": {
      "StringEquals": {"aws:ResourceTag/Env": "prod"}
    }
  }]
}
```

- **优点**：声明式，Effect + Action + Resource + Condition 结构清晰
- **缺点**：通配符易误用（`*` 通配符 + NotAction 容易出错）

#### 4.3.2 Azure Role Definition（中等复杂度）

```json
{
  "roleName": "App Reader",
  "permissions": [{
    "actions": ["Microsoft.Storage/storageAccounts/read"],
    "dataActions": ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read"],
    "notActions": [],
    "notDataActions": []
  }],
  "assignableScopes": ["/subscriptions/.../resourceGroups/MyRG"]
}
```

- **优点**：Action/NotAction、DataAction/NotDataAction 分离清晰
- **缺点**：Role 和 Assignment 分离，跨多文档理解

#### 4.3.3 GCP IAM Policy（最简洁）

```json
{
  "bindings": [{
    "role": "roles/storage.objectViewer",
    "members": ["user:alice@example.com"],
    "condition": {
      "expression": "resource.labels.env == 'prod'"
    }
  }]
}
```

- **优点**：最简洁，主体 + 角色 + 条件三元组
- **缺点**：CEL 表达式学习曲线陡峭

### 4.4 资源层级继承机制对比

| 维度 | AWS | Azure | GCP |
|------|-----|-------|-----|
| **层级数** | 4 层（Org → OU → Account → Resource） | 4 层（MG → Sub → RG → Resource） | 4 层（Org → Folder → Project → Resource） |
| **继承模式** | SCP 限制向下传递（不累积） | Role Assignment 累积（不能减权） | IAM Policy 累积（不能减权） |
| **减权机制** | SCP 显式 Deny（任意层级） | Deny Assignment（特权用户设置） | Deny Policy（任意层级） |
| **跨账号继承** | 否（每账号独立） | 是（Management Group 跨 Subscription） | 是（Organization 跨 Project） |
| **典型应用** | 多账号企业 | 多 Subscription 企业 | 多 Project 企业 |

### 4.5 条件表达式灵活度对比

| 维度 | AWS Condition | Azure Condition | GCP CEL |
|------|---------------|-----------------|---------|
| **语法类型** | 运算符 + 键值对 | `@Resource/@Principal` 表达式 | CEL（表达式语言） |
| **支持类型** | String/Numeric/Date/Bool/IP/Arn | String/Numeric/DateTime/Exists | String/Numeric/DateTime/Bool 任意 |
| **逻辑运算** | 多键 AND（隐式），同键多值 OR | AND, OR | 任意复杂表达式 |
| **函数调用** | 无 | 无 | 有（startsWith, endsWith, getHours...） |
| **跨字段引用** | `${aws:PrincipalTag/X}` | @Principal vs @Resource | resource.X, request.Y, principal.Z |
| **学习曲线** | 低（声明式） | 中 | 高（编程式） |
| **表达力** | 中 | 中 | **高** |

### 4.6 多账号管理方案对比

#### 4.6.1 AWS（Accounts + Organizations + SCP）

- **强账户隔离**：每个 AWS Account 是独立的 IAM 命名空间
- **跨账号访问**：通过 STS AssumeRole + Trust Policy
- **集中管控**：AWS Organizations + SCP
- **优势**：账户级隔离强，安全事故爆炸半径小
- **劣势**：跨账号管理复杂，需要大量 Role

#### 4.6.2 Azure（Tenants + Management Groups + Lighthouse）

- **单一 Entra ID 租户**：所有 Subscription 共享一个 Entra ID
- **Management Group 跨 Sub 管控**：Policy + RBAC 都可跨 Sub
- **Lighthouse 跨租户管理**：MSP（管理服务提供商）场景
- **优势**：跨 Subscription 管理简单，企业级集成强
- **劣势**：单一租户风险集中

#### 4.6.3 GCP（Organization + Folders + Projects + Impersonation）

- **单一 Organization**：所有 Project 共享一个 Organization
- **Service Account Impersonation**：跨 Project 访问
- **Workload Identity Federation**：跨云访问
- **优势**：模型简洁，Policy 沿层级继承
- **劣势**：Project 是计费/资源隔离边界，但身份不隔离

### 4.7 审计日志完整度对比

| 维度 | AWS CloudTrail | Azure Activity Log | GCP Cloud Audit Logs |
|------|----------------|--------------------|--------------------|
| **默认覆盖** | 管理事件默认开启 | 默认开启 | Admin Activity 默认开启 |
| **数据事件** | 需开启（S3/Lambda 等） | 需 Diagnostic Settings | 需开启 Data Access Logs |
| **保留期** | 默认 90 天，可配置 S3 长期保留 | 90 天，可导出 | 400 天（默认），可导出 |
| **查询能力** | Athena 查询 S3 | Log Analytics KQL | Cloud Logging |
| **告警能力** | CloudWatch + EventBridge | Alert Rules | Log-based Metrics |
| **完整性** | 高（含 STS 联邦） | 高（含 PIM） | 高（含 Impersonation 链） |

### 4.8 工具链成熟度对比

| 工具能力 | AWS | Azure | GCP |
|---------|-----|-------|-----|
| **Policy 验证** | IAM Policy Validator, Access Analyzer | Azure Policy 验证 | Policy Troubleshooter |
| **Policy 模拟** | IAM Policy Simulator | 无原生工具 | Policy Troubleshooter |
| **最小权限推荐** | Access Analyzer Policy Generation | Defender for Cloud Recommendations | IAM Recommender |
| **未使用权限分析** | Last Accessed Information | Defender for Cloud | Recommender |
| **外部访问分析** | Access Analyzer（资源策略） | Defender External Attack Surface | 无原生 |
| **审计查询** | Athena + CloudTrail | Log Analytics + KQL | Cloud Logging + Log Analytics |
| **可视化** | IAM Access Analyzer Dashboard | Defender for Cloud Dashboard | Policy Intelligence Dashboard |

### 4.9 性能对比

| 维度 | AWS | Azure | GCP |
|------|-----|-------|-----|
| **评估延迟** | ~200ms | ~100ms | ~50ms |
| **缓存机制** | 会话级缓存 | Scope 级缓存（30min） | 资源级缓存（5-10min） |
| **最大策略数** | 单身份 10 个 Managed | 单 Sub 2000 Assignment | 单 Policy 1500 binding |
| **大型企业支持** | 多账号 + SCP | Management Group + Policy | Organization + Folder |

---

## 5. 对我们权限体系重设计的启示

### 5.1 从 AWS 学到的：Condition Keys 体系

**启示 1：建立分层分类的条件键体系**

AWS 把条件键分为 6 大类（主体/会话/网络/资源/请求/跨服务防混淆），每个键都有清晰的命名规范（`aws:PrincipalTag/X`、`aws:ResourceTag/X`）。

我们的 M6 条件规则可以借鉴：

```
我们当前的条件规则缺乏统一规范。可以建立：
- principal.*：主体属性（如 principal.department, principal.role）
- resource.*：资源属性（如 resource.tags.Project, resource.region）
- request.*：请求属性（如 request.time, request.ip, request.source）
- environment.*：环境属性（如 environment.cluster, environment.env）
```

**启示 2：ABAC 与 RBAC 并存，而非二选一**

AWS 通过 Condition Keys 在 RBAC 基础上叠加 ABAC，这是一个非常成功的设计。我们的 9 机制权限体系中，M1（功能权限）是 RBAC，M2（维度范围白名单）是数据范围，M6（条件规则）是 ABAC。我们应该把 ABAC 视为对 RBAC 的增强，而非替代。

### 5.2 从 Azure 学到的：Scope 层级与 PIM

**启示 3：4 层 Scope 层级实现权限继承**

Azure 的 Management Group → Subscription → Resource Group → Resource 4 层继承模型非常清晰。我们的权限体系可以借鉴：

```
我们的资源层级建议：
- Organization（组织/集团）
  - BusinessUnit（业务单元）
    - Project（项目）
      - Resource（资源实例）
```

权限继承规则：
- 上级赋权 → 子级自动继承
- 子级不能减权（需要减权时使用 Deny Policy）
- 利用 Scope 继承减少重复赋权

**启示 4：Just-In-Time 特权激活（PIM）**

Azure PIM 的设计非常优雅：把"权限"和"激活"分离。我们当前的"Owner 例外"机制是常驻的，可以借鉴 PIM：

```
新机制建议：M10 特权激活
- 普通用户拥有 Eligible Owner 权限
- 需要操作时主动激活（MFA + 审批 + 时限）
- 激活后才获得 Active Owner 权限
- 自动过期撤销
```

这样可以大幅降低日常攻击面，符合零信任原则。

**启示 5：Control Plane 与 Data Plane 分离**

Azure 的 `Actions` vs `DataActions` 分离非常清晰。我们的 9 机制权限体系中，M1（功能权限）类似 Control Plane，M7（M11 YAML RLS）类似 Data Plane。可以借鉴这种分离：

```
权限模型建议：
- ControlActions: 配置类操作（如修改角色、修改菜单）
- DataActions: 数据类操作（如查询订单、查看客户）
- 这两类权限可以独立分配，例如：
  - 数据分析师：DataActions=多，ControlActions=少
  - 系统管理员：DataActions=少，ControlActions=多
```

### 5.3 从 GCP 学到的：CEL 表达式与 Workload Identity

**启示 6：引入 CEL 作为统一条件表达式语言**

GCP 的 CEL 是三大云厂商中最强大的条件表达式语言，支持：

- 函数调用（startsWith, endsWith, getHours, matchTag...）
- 跨字段引用（resource.X, request.Y, principal.Z）
- 任意复杂逻辑（&& || ! 嵌套）

我们的 M6（条件规则）和 M11（YAML RLS）可以统一用 CEL 表达式：

```cel
# 时间窗口限制
request.time.getHours('Asia/Shanghai') >= 9
&& request.time.getHours('Asia/Shanghai') <= 18

# 资源标签匹配
resource.tags.Project == principal.tags.Project

# 主体部门 + 资源环境组合
principal.department == 'Finance'
&& resource.tags.Env == 'production'
&& request.action == 'read'

# 跨字段引用（M11 RLS 也可用）
resource.owner_id == principal.user_id
|| principal.role == 'admin'
```

**启示 7：Workload Identity Federation 思路**

GCP 的 Workload Identity Federation 让外部系统通过 OIDC 联邦访问，无需长期凭证。我们的系统可以借鉴：

- **微服务间调用**：服务 A 访问服务 B 时，使用短期 Token 而非长期 API Key
- **CI/CD 流水线**：流水线动态获取权限，而非静态配置凭证
- **外部系统集成**：通过 OIDC 联邦，而非 Service Account Key

### 5.4 三大云厂商的"功能+数据"统一权限设计

#### 5.4.1 AWS 的方案

AWS 通过 Action + Resource + Condition 三元组统一表达功能权限和数据权限：

- **功能权限**：`Action = "ec2:StartInstances"`
- **数据权限**：`Action = "s3:GetObject"` + `Resource = "arn:aws:s3:::bucket/path"`
- **条件**：`Condition = {"StringEquals": {"aws:ResourceTag/Env": "prod"}}`

**核心思想**：不区分功能/数据，一切都是 (Action, Resource, Condition) 元组。

#### 5.4.2 Azure 的方案

Azure 显式分离 Control Plane 和 Data Plane：

- `Actions` / `NotActions`：控制平面（资源 CRUD）
- `DataActions` / `NotDataActions`：数据平面（数据读写）

**核心思想**：两个平面有不同语义，应分开管理。

#### 5.4.3 GCP 的方案

GCP 通过 Role 内置 permissions 统一：

- 一个 Role 可以同时包含 control permission 和 data permission
- 资源层级继承时，权限一起继承

**核心思想**：Role 是权限打包单元，控制/数据权限混合打包。

#### 5.4.4 对我们的启示

```
当前我们的 9 机制权限体系中：
- M1 功能权限 = 类似 Actions
- M2 维度范围白名单 = 类似 Resource 范围
- M5 实例权限 = 类似具体 Resource ARN
- M6 条件规则 = 类似 Condition
- M7 M11 RLS = 类似 Data Plane
- M8 字段脱敏 = 类似 Column-level

建议重设计方向（综合 3 大云厂商）：
1. 统一权限模型：Action + Resource + Condition 三元组
2. 显式 Control/Data 平面分离（学习 Azure）
3. 用 CEL 表达式统一所有条件（学习 GCP）
4. 用标签实现 ABAC（学习 AWS）
```

### 5.5 策略评估性能优化的启示

#### 5.5.1 AWS 的优化

- **缓存粒度**：会话级缓存（STS 凭证期间策略评估结果缓存）
- **策略展开优化**：通配符展开是性能瓶颈
- **Access Analyzer 离线分析**：避免在线评估开销

#### 5.5.2 Azure 的优化

- **Scope 级缓存**：每个 Subscription 缓存 Role Assignment，30min 刷新
- **跨 Subscription 查询**：通过 Resource Graph API 批量查询
- **限制 Assignment 数量**：单 Sub 2000 上限

#### 5.5.3 GCP 的优化

- **资源级缓存**：每个资源缓存其 IAM Policy，5-10min 刷新
- **CEL 编译缓存**：CEL 表达式编译结果缓存
- **限制 binding 数量**：单 Policy 1500 binding

#### 5.5.4 对我们的启示

```python
# 我们可以借鉴的评估性能优化：
class PermissionCache:
    """多级权限缓存"""
    
    def __init__(self):
        # L1: 用户级缓存（5min）
        self.user_cache = LRUCache(maxsize=10000, ttl=300)
        # L2: 角色级缓存（30min）
        self.role_cache = LRUCache(maxsize=1000, ttl=1800)
        # L3: 策略级缓存（60min）
        self.policy_cache = LRUCache(maxsize=100, ttl=3600)
    
    def evaluate(self, user, action, resource, context):
        # 1. 先查 L1 用户级缓存
        cache_key = (user.id, action, resource.id, hash(context))
        if cached := self.user_cache.get(cache_key):
            return cached
        
        # 2. 评估（带 L2/L3 缓存）
        result = self._do_evaluate(user, action, resource, context)
        
        # 3. 写入 L1 缓存
        self.user_cache[cache_key] = result
        return result

# 策略评估流程优化：
# 1. 显式 Deny 检查（短路）
# 2. 索引查找（按 Action 维度索引策略）
# 3. CEL 表达式预编译
# 4. 标签快速匹配（哈希表）
# 5. 资源层级向上查询（带缓存）
```

### 5.6 资源层级继承的启示

#### 5.6.1 三大云厂商的共识

三大云厂商都采用 **4 层资源层级**：

- AWS：Org → OU → Account → Resource
- Azure：MG → Sub → RG → Resource
- GCP：Org → Folder → Project → Resource

**共性设计原则**：

1. **层级 = 4 层最佳**：太少不够灵活，太多难以维护
2. **权限向下继承**：上级赋权 → 子级自动获得
3. **减权机制必不可少**：AWS SCP、Azure Deny Assignment、GCP Deny Policy

#### 5.6.2 对我们的启示

```
建议的资源层级：
Level 1: Organization（集团）
  - 维度：组织/集团层级
  - 角色：集团管理员
Level 2: BusinessUnit（业务单元/事业部）
  - 维度：BU 层级
  - 角色：BU 管理员
Level 3: Project（项目）
  - 维度：项目层级
  - 角色：项目经理（Owner）
Level 4: Resource（资源实例）
  - 维度：具体资源
  - 角色：资源 Owner

继承规则：
- 上级赋权 → 子级自动继承（累积）
- 子级不能减权（需要减权时通过 Deny 规则）
- Deny 优先级最高
```

### 5.7 多租户、跨账号、临时授权的可参考方案

#### 5.7.1 多租户

- **AWS 方案**：每租户独立 AWS Account（最强隔离）
- **Azure 方案**：多 Subscription 共享 Entra ID（适中隔离）
- **GCP 方案**：多 Project 共享 Organization（弱隔离）
- **我们的方案建议**：基于"业务单元+项目"逻辑隔离，通过 Row Level Security + Field Masking 实现数据隔离

#### 5.7.2 跨账号

- **AWS**：STS AssumeRole + Trust Policy + ExternalId
- **Azure**：Entra ID 跨租户 + Lighthouse
- **GCP**：Service Account Impersonation
- **我们的方案建议**：借鉴 STS 思路，提供"代用户访问"的 Token 颁发机制

#### 5.7.3 临时授权

- **AWS**：STS（15min-12h 临时凭证）
- **Azure**：PIM（按需激活 Eligible 角色）
- **GCP**：Workload Identity（短期 Token）+ Impersonation 链
- **我们的方案建议**：参考 PIM 实现 M10 特权激活机制

### 5.8 综合建议：9 机制 → 11 机制

基于 3 大云厂商的研究，建议在现有 9 机制基础上增加 2 个机制：

| 现有机制 | 优化建议 |
|---------|---------|
| M1 功能权限 | 引入 Control/Data Action 分离（学 Azure）|
| M2 维度范围白名单 | 改为 Scope 层级继承（学 Azure/GCP） |
| M3 可见性 | 用 CEL 表达式统一（学 GCP） |
| M4 Owner 例外 | 保留，但增加 M10 PIM 替代部分常驻权限 |
| M5 实例权限 | 通过 Resource Path 表达（学 AWS ARN） |
| M6 条件规则 | 用 CEL 替代自定义语法（学 GCP） |
| M7 M11 YAML RLS | 保留，与 CEL 协同 |
| M8 字段脱敏 | 保留 |
| M9 Owner 自动授权 | 保留 |
| **M10（新增）** | **特权激活机制**（学 Azure PIM） |
| **M11（新增）** | **资源层级继承**（学 3 大云厂商共识） |

### 5.9 关键设计原则总结

通过对 AWS、Azure、GCP 3 大云厂商的深入研究，提炼出 8 大设计原则：

1. **权限是 (Principal, Action, Resource, Condition) 四元组**：用统一模型表达功能权限和数据权限
2. **4 层资源层级**：组织 → 业务单元 → 项目 → 资源，权限向下继承
3. **Deny 优先于 Allow**：任何层级的显式 Deny 总是优先
4. **ABAC 增强而非替代 RBAC**：用 Condition/CEL 在 RBAC 上叠加 ABAC
5. **Just-In-Time 特权激活**：常驻特权应该最小化，激活机制替代常驻授权
6. **临时凭证优于长期凭证**：STS/Impersonation 思路替代 Service Account Key
7. **统一条件表达式语言**：CEL 或类似表达式统一所有条件规则
8. **多层缓存优化评估性能**：用户级/角色级/策略级多层缓存

---

## 6. 参考文档

### 6.1 AWS IAM 官方文档

- [AWS IAM User Guide](https://docs.aws.amazon.com/IAM/latest/UserGuide/introduction.html)
- [IAM JSON Policy Grammar](https://docs.amazonaws.cn/en_us/IAM/latest/UserGuide/reference_policies_grammar.html)
- [IAM Policy Elements: Statement](https://docs.aws.amazon.com/en_us/IAM/latest/UserGuide/reference_policies_elements_statement.html)
- [AWS Global Condition Context Keys](https://docs.aws.amazon.com/zh_cn/IAM/latest/UserGuide/reference_policies_condition-keys.html)
- [IAM and AWS STS Condition Keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_iam-condition-keys.html)
- [Policies and Permissions in IAM](https://docs.aws.amazon.com/zh_cn/IAM/latest/UserGuide/access_policies.html)
- [STS AssumeRole API Reference](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html)
- [Requesting Temporary Security Credentials](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_request.html)
- [AWS IAM Policy Glossary](https://awsglossary.org/terms/iam-policy)
- [IAM Condition Keys Glossary](https://awsglossary.org/terms/iam-condition-keys)
- [AWS Services Resource Providers](https://docs.amazonaws.cn/en_us/service-authorization/latest/reference/list_awskeymanagementservice.html)

### 6.2 Azure RBAC 官方文档

- [Azure RBAC Documentation](https://learn.microsoft.com/zh-cn/azure/role-based-access-control/)
- [Azure Custom Roles](https://learn.microsoft.com/zh-cn/azure/role-based-access-control/custom-roles)
- [Understand Azure Role Definitions](https://learn.microsoft.com/en-in/azure/role-based-access-control/role-definitions)
- [Azure Built-in Security Roles](https://learn.microsoft.com/zh-cn/azure/role-based-access-control/built-in-roles/security)
- [Plan a Privileged Identity Management Deployment](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-deployment-plan)
- [Azure Identity Management Best Practices](https://learn.microsoft.com/en-us/azure/security/fundamentals/identity-management-best-practices)
- [Azure Management Groups Overview](https://docs.microsoft.com/zh-cn/AZURE/governance/management-groups/overview)
- [Azure Policy Design Principles](https://learn.microsoft.com/ja-jp/training/modules/sovereignty-policy-initiatives/azure-policy-design-principles)
- [Azure Lighthouse Eligible Authorizations](https://learn.microsoft.com/en-gb/azure/lighthouse/how-to/create-eligible-authorizations)
- [Identity and Access Security Recommendations](https://learn.microsoft.com/id-id/Azure/defender-for-cloud/recommendations-reference-identity-access)
- [Microsoft Cloud Security Benchmark - Identity Management](https://learn.microsoft.com/zh-cn/security/benchmark/azure/mcsb-identity-management)

### 6.3 Google Cloud IAM 官方文档

- [Google Cloud IAM Overview](https://cloud.google.com/iam/docs/overview)
- [IAM Conditions Overview](https://cloud.google.com/iam/docs/conditions-overview)
- [IAM Training - Identity and Access Management](https://storage.googleapis.com/cloud-training/archinfra/v2.2/on-demand/2.1_IAM.pdf)
- [Managing Security in Google Cloud - IAM](https://storage.googleapis.com/cloud-training/gcpsec/v3.x/en/on-demand/T-GCPSEC1-I_Managing%20Security%20in%20Google%20Cloud/OD_PDF_M1.3_Identity_and_Access_Management.pdf)
- [GCP IAM Best Practices](https://zone.huoxian.cn/d/2630-google-cloud-platform)
- [Google Cloud IAM Role Hierarchies Explained](https://www.cloudoptimo.com/blog/google-cloud-iam-role-hierarchies-explained/)
- [GCP IAM and Resource Hierarchy](https://erikevenson.github.io/architect/providers/gcp/iam-organizations/)
- [What Is GCP IAM? Roles, Policies & Best Practices](https://www.usage.ai/blogs/gcp/guides/finops-on-gcp/gcp-iam)
- [Replace Service Account Keys with Workload Identity Federation](https://oneuptime.com/blog/post/2026-02-17-how-to-replace-service-account-keys-with-workload-identity-federation-in-gcp/view)
- [GitHub Actions OIDC to Google Cloud Tutorial](https://nerdleveltech.com/github-actions-gcp-workload-identity-federation-tutorial)
- [Google Auth Library Documentation](https://googleapis.dev/python/google-auth/2.47.0/user-guide.html)
- [GCP Identity & Security Course](https://resources.devweekends.com/courses/gcp-cloud-engineering/02-iam-security)

### 6.4 跨云对比与安全基准

- [AWS vs Azure vs GCP: Evaluating Cross-Cloud Security Models](https://www.cloudoptimo.com/blog/aws-vs-azure-vs-gcp-evaluating-cross-cloud-security-models/)
- [Cloud Security Across AWS, Azure & GCP: A Technical Comparison](https://blast.security/blog/deep-technical-guide-how-cloud-defense-strategies-differ-across-aws-azure-and-gcp/)
- [Azure and AWS Accounts and Subscriptions Comparison](https://learn.microsoft.com/en-ca/azure/architecture/aws-professional/accounts)
- [Can Azure Policy be applied across multiple subscriptions](https://learn.microsoft.com/en-nz/answers/questions/5935408/can-azure-policy-be-applied-across-multiple-subscr)

---

## 附录 A：术语对照表

| 概念 | AWS | Azure | GCP | 我们 |
|------|-----|-------|-----|------|
| 身份 | IAM User / Role | Entra ID User / SP / Managed Identity | Principal (User/SA/Group) | 用户/角色 |
| 权限单元 | Policy | Role Definition | IAM Role | 权限项 |
| 授权关系 | Policy Attachment | Role Assignment | IAM Binding | 角色分配 |
| 资源标识 | ARN | Resource ID | Resource Path | 资源 ID |
| 条件表达式 | Condition Keys | Role Condition (Azure AD Conditions) | CEL Expression | 条件规则 |
| 组织层级 | Organization / OU | Management Group / Subscription | Organization / Folder | 组织/事业部 |
| 资源层级 | Account / Resource | Resource Group / Resource | Project / Resource | 项目/资源 |
| 临时凭证 | STS Token | PIM Activation | Workload Identity Token | 临时 Token |
| 跨账号 | AssumeRole | Entra ID Lighthouse | Service Account Impersonation | 跨租户授权 |
| 审计日志 | CloudTrail | Activity Log | Cloud Audit Logs | 审计日志 |
| 策略模拟 | Policy Simulator | - | Policy Troubleshooter | - |
| 权限分析 | Access Analyzer | Defender for Cloud | Policy Analyzer | - |
| 托管身份 | IAM Role for Service | Managed Identity | Service Account | 服务账号 |
| 策略强制 | SCP / Permission Boundary | Azure Policy + Deny Assignment | Deny Policy + Org Policy | Deny 规则 |

---

## 附录 B：变更记录

| 日期 | 版本 | 变更人 | 变更内容 |
|------|------|--------|---------|
| 2026-07-19 | v1.0 | AI Assistant | 初版：完成 AWS / Azure / GCP 3 大云厂商权限架构深入研究 |

---

**文档结束**
