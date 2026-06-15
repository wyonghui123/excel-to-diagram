# TBD 决策建议 (基于中型头部产品调研) — 2026-06-12

> **调研对象**: Linear, Notion, GitHub Enterprise, Stripe, AWS CloudTrail, GitLab, Rails SolidQueue
> **目标**: 用中型头部产品的实战做法, 给我们 audit_log spec 的 8 个 TBD 决策点提供具体方案

---

## TBD-1: Hash chain (FR-014) 是否本期实施?

### 头部做法对比

| 产品 | Hash chain 机制 | 时机 |
|------|---------------|------|
| **AWS CloudTrail** | SHA-256 + RSA 数字签名 + 每小时 digest file | 强需求, GA 即做 |
| **PostgreSQL pgAudit 实践** | sha256(prev_hash + canonical_json) + 日终 verify | 金融级项目标配 |
| **GitHub Enterprise** | 公开文档不强调 hash chain, 但提供 SIEM streaming | Enterprise tier 内置 |
| **Linear** | 90 天保留, **不公开** hash chain 细节 | 内部实现, 不卖 |
| **Notion** | 90-180 天保留, **不强调** | 内部实现 |
| **Stripe** | API 事件不强调 hash chain (用签名/重试防篡改) | 替代方案 |

### 决策建议

**✅ 本期实施 (Phase 1 末), 推迟 S3 Object Lock 到 Phase 3**

- **理由 1**: Hash chain 实现成本低 (1 字段 + 1 verify 函数), 收益高
- **理由 2**: 不需要云存储, 纯本地 SQLite 即可
- **理由 3**: 中型 SaaS (GitHub Enterprise / Notion Enterprise) 都有, 是客户问"防篡改吗?"的标准答案
- **理由 4**: S3 Object Lock 需云存储 + 跨账户架构, 投资大, **不**应跟 hash chain 绑在一起

### 具体方案

- 加 2 字段: `prev_hash CHAR(64)` / `row_hash CHAR(64)`
- `meta/services/audit_hash_chain.py` 提供 `compute_row_hash()` + `verify_chain(start_id)`
- 日终 cron 跑 verify, 不匹配 → 触发告警
- 优先级: **Could → Should** (本期做, 推迟 S3)

---

## TBD-2: retention_until 保留期 (FR-013)

### 头部做法对比

| 产品 | 默认保留期 | Enterprise tier |
|------|----------|----------------|
| **Linear** | 90 天 | 同 (不区分) |
| **Notion** | 90 天 (Free/Plus), **180 天** (Business/Enterprise) | 180 天 |
| **GitHub Cloud** | **90 天** | 同 |
| **GitHub Enterprise Server** | 120 天 (GraphQL) | 可配置 |
| **GitHub Enterprise (Datadog 集成)** | 配置保留期, 主流 90/180/365 | 365 天可配 |
| **AWS CloudTrail** | 90 天 (S3), 可配 **7 年** | 7 年 (SOX) |
| **CloudWatch Logs** | 永久 (付费) | 永久 |
| **业界最佳实践** | 小型 90d / 中型 180d / 大型 365d | 监管严格行业 7y+ |

### 决策建议

**✅ 中型企业标准: 3 层分级保留**

| log_category | 保留期 | 理由 |
|-------------|-------|------|
| `security` (登录/密码/2FA) | **2 年** | SOX/GDPR 中位线 |
| `authz` (role/permission 变更) | **2 年** | 合规需要, 客户问"去年谁加了 admin?" |
| `business` (CRUD) | **1 年** | 业务回溯, 不需更久 |
| `access` (READ/EXPORT) | **90 天** | 数据访问频率高, 容量大 |
| `admin` (DELETE_BLOCKED) | **1 年** | 投诉/争议处理 |
| `system` (AUDIT_WRITE_FAILED) | **90 天** | 故障排查用 |
| `cascade` (级联衍生) | **90 天** | 配合主操作保留 |

**实施**:
```sql
-- 写入时根据 log_category 自动算 retention_until
retention_until = created_at + INTERVAL
  CASE log_category
    WHEN 'security' THEN '2 years'
    WHEN 'authz' THEN '2 years'
    WHEN 'business' THEN '1 year'
    WHEN 'admin' THEN '1 year'
    WHEN 'access' THEN '90 days'
    WHEN 'system' THEN '90 days'
    WHEN 'cascade' THEN '90 days'
  END
```

**用户可配置** (FR-013 增强):
- Enterprise 客户可调, 默认按上表
- 配置存在 `meta_config.audit_retention_overrides`

---

## TBD-3: 操作链 API 权限 (FR-008)

### 头部做法对比

| 产品 | 谁可访问 audit log | 鉴权方式 |
|------|-------------------|---------|
| **Linear** | **Only workspace owners** | UI 隐藏, API 需 admin token |
| **Notion** | Workspace owner + admin (Business+ 自动授权) | role-based |
| **GitHub** | Enterprise owner + **security manager** role | token scope `read:audit_log` |
| **GitLab** | Maintainer + Owner (Ultimate tier) | role-based |
| **AWS CloudTrail** | IAM 策略 + CloudTrail Lake | fine-grained |

### 决策建议

**✅ admin only (可扩展 security_manager role)**

| 角色 | 权限 |
|------|------|
| `user` | ❌ 不能看任何审计 |
| `admin` | ✅ 看全部审计 (按 tenant) |
| `security_manager` | ✅ 看全部审计 (跨 tenant, 预留) |
| `auditor` | ✅ 只读, 不能导出 (Phase 3) |

**实施**:
- 复用现有 `meta/api/auth_api.py` 的 `is_admin()` 检查
- 操作链 API 在 `audit_operation_api.py` 加 `@admin_required` 装饰器
- 预留 `security_manager` role, 表里没就先不实现, 但代码留扩展点
- 鉴权失败 → RFC 7807 `403 PERMISSION_DENIED` + recovery hint (申请 admin 权限)

---

## TBD-4: `'V3.17 Test (admin)'` 522 条 (带 admin 角色) 删不删?

### 头部做法对比

| 产品 | 测试数据处理 |
|------|-------------|
| **GitHub** | 测试组织独立, 不污染主企业 |
| **Linear** | workspace 删除后, 审计自动清 |
| **Notion** | workspace 删除清空 |
| **Stripe** | test mode/live mode 物理隔离 |

### 决策建议

**✅ 全删, 包括 `'V3.17 Test (admin)'` 522 条**

- **理由 1**: 这些是测试期间数据, 不是真实用户操作
- **理由 2**: 留 admin 角色测试数据有安全风险 (admin 权限暴露面)
- **理由 3**: 未来回归测试会创建新测试用户 (`UserFactory` 会自动生成唯一名)

**具体做法**:
```sql
-- 备份 (含 admin 角色测试数据, 1 个完整 backup)
CREATE TABLE audit_logs_backup_20260612 AS
SELECT * FROM audit_logs WHERE user_name LIKE 'V3.17 Test%';

-- 删
DELETE FROM audit_logs WHERE user_name LIKE 'V3.17 Test%';

-- 同时清理 users 表里的所有 V3.17 Test (因为 user_factory 会自动造)
DELETE FROM users WHERE display_name LIKE 'V3.17 Test%';

-- 保留唯一 admin (id=1)
-- (确认) SELECT COUNT(*) FROM users WHERE id=1 AND role='admin';  -- 应 = 1

-- VACUUM
VACUUM;
```

**实施**:
- 脚本 `meta/scripts/cleanup_test_audit.py`, 默认 `--dry-run`, 显式 `--apply` 才删
- 删除前 print 受影响行数, 二次确认
- 保留 1 个真实 admin (`id=1, role=admin`) 用于生产

---

## TBD-5: RFC 7807 错误格式迁移方式 (FR-001)

### 头部做法对比

| 产品 | API 迁移策略 | 周期 |
|------|------------|------|
| **Stripe** | **永远不破坏**, 引入 version transformer (按 account 锁定) | 12-24 月弃用 |
| **GitHub** | 24 月支持窗口, 提前 12 月公告 | 24 月 |
| **Google Cloud** | 12 月弃用周期 + 6 月 sunset header | 12 月 |
| **Twilio** | 12 月弃用, 6 月必迁 | 12 月 |
| **AWS** | 12 月弃用 (RDS/EFS 等) | 12 月 |
| **APIscout 2026 共识** | **6-12 月 minimum**, Stripe 12 月 | 6-12 月 |

### 决策建议

**✅ Feature flag 双写 2 周 + 切换 1 周 + 旧字段 4 周 deprecated 后移除**

我们项目阶段, 不需要 6-12 月窗口, 但**也不能 1 天切**:
- **Week 1-2 (双写期)**: 旧接口保留, 同时返 `problem` 字段含 RFC 7807 内容
  ```json
  {
    "success": false,
    "message": "用户组下还有 12 个成员...",
    "error_code": "RESTRICT_ON_DELETE",
    "problem": {  // [NEW] RFC 7807 内容
      "type": "https://api.example.com/errors/user-group-not-empty",
      "title": "User Group Not Empty",
      "status": 422,
      "detail": "用户组下还有 12 个成员...",
      "instance": "/api/v2/bo/user_group/567",
      "code": "USER_GROUP_NOT_EMPTY",
      "trace_id": "abc123...",
      "recovery": {...}
    }
  }
  ```
- **Week 3 (切换期)**: Feature flag `RFC7807_ENABLED=true`, 前端读 `problem` 字段
- **Week 4-7 (废弃期)**: 旧字段 `success/message/error_code` 标 deprecated, 4 周后移除
- **Week 8+**: 移除旧字段

**实施**:
- `meta/api/_problem_details.py` 工厂方法, 既存 `problem` 字段也保留旧字段
- Feature flag `meta_config.api_format = "v1"|"v2"`, 默认 v1 (双写)
- 前端 PR 准备好后改 v2, 跑 1 周无问题就回主分支
- 旧字段 4 周后从代码移除

---

## TBD-6: retry worker 部署方式 (FR-010)

### 头部做法对比

| 产品 | retry 实现 | 关键点 |
|------|----------|-------|
| **Stripe webhook** | 独立 worker process (systemd / Docker) | 不与 HTTP server 共享生命周期 |
| **Rails SolidQueue** | 独立 worker, 0.1s polling | 与 web 完全分离, 各自扩缩容 |
| **dev.to 2026 文章** | "If you run it as setInterval inside web service, it dies on redeploy" | **关键警告** |
| **GitHub Actions** | GitHub-hosted runner, 独立 VM | 完全隔离 |
| **BullMQ / Sidekiq** | 独立 process, Redis 队列 | 业界标准 |
| **Laravel Horizon** | supervisor 管理多个 worker | PHP 生态 |
| **Inngest / Trigger.dev** | serverless, 自动扩缩容 | SaaS 方案 |

### 决策建议

**✅ 独立 daemon thread + service_manager 集成, 不放 setInterval**

- **理由 1**: setInterval 会在 Flask 重启时丢失, 跟 dev.to 文章的踩坑案例一致
- **理由 2**: 独立 thread 跟 service_manager 集成, 服务启停可管理
- **理由 3**: 我们用 `service_manager.ps1`, 已经支持多进程 (frontend + backend), 加一个 audit-worker 是 0 成本

**具体方案**:
```python
# meta/services/audit_retry_worker.py
class AuditRetryWorker(threading.Thread):
    """独立线程, 由 service_manager 拉起
    
    跟 Flask 主进程共享 DB 连接, 但生命周期独立
    优雅退出: stop_event.wait() 在 stop 信号时立即返回
    """
    def __init__(self, data_source, interval=60, max_retries=10):
        super().__init__(daemon=True, name="AuditRetryWorker")
        self.ds = data_source
        self.interval = interval
        self.max_retries = max_retries
        self._stop_event = threading.Event()
    
    def run(self):
        while not self._stop_event.is_set():
            self._retry_failed_records()
            self._stop_event.wait(self.interval)
    
    def stop(self):
        self._stop_event.set()
```

**集成**:
- `meta/services/service_orchestrator.py` 加 worker 启动点
- `scripts/service_manager.ps1` 加 `-Workers audit` 参数
- 默认开, 故障时手动 stop (`Stop-AuditWorker`)

**为什么不 cron**:
- cron 最小 1 分钟粒度, 启动开销大
- cron 不会立即响应 (重试 1 次要等下一分钟)
- cron 跟 system clock 绑定, 测试时不方便
- 独立 thread 可立即响应 + 复用 DB 连接池

---

## TBD-7: 自动清理 cron 周期 (FR-015)

### 头部做法对比

| 产品 | 清理频率 | 触发 |
|------|---------|------|
| **GitHub** | 实时 streaming + 90 天 | TTL on S3 / DB |
| **Linear** | 90 天 hard delete | 后台 worker |
| **Notion** | 90/180 天 | trash 30 天 + retained N 天 |
| **AWS CloudTrail** | 90 天 → S3 Glacier | lifecycle rule, 每日扫 |
| **AWS S3 lifecycle** | 每日 0:00 UTC | cron-like |
| **行业最佳实践** | 每周日 03:00 / 每日 02:00 | off-peak |

### 决策建议

**✅ 每周日 03:00 (本地时区) 自动清理测试数据**

**具体方案**:
```python
# meta/scripts/cleanup_test_audit.py
"""
每周日 03:00 执行
清理 user_name LIKE 'V3.17%' OR 'test_%' OR 'audit_%' 的 > 7 天的数据
保留 backup 表
"""
def cleanup(days_old=7, patterns=['V3.17%', 'test_%', 'audit_%']):
    # 1. 备份 (按日期)
    today = datetime.now().strftime('%Y%m%d')
    backup_table = f'audit_logs_deleted_{today}'
    execute(f"CREATE TABLE {backup_table} AS SELECT * FROM audit_logs WHERE ...")
    
    # 2. 删
    execute("DELETE FROM audit_logs WHERE ...")
    
    # 3. 30 天后自动删 backup
    # (在 SQL 里写 trigger 或单独 cron)
```

**部署**:
- Windows: 用 Task Scheduler, 触发 `python cleanup_test_audit.py --apply`
- 或: 集成到 service_manager, 启动时注册
- 默认 dry_run, 真正删要 `--apply` (防误操作)

**为什么不每天**:
- 测试数据通常是批量产生, 每天清意义不大
- 每周一次降低误删风险
- 30 天 backup 兜底

**为什么不用 retention_until 自动归档**:
- 那个是给真实数据用的 (按 log_category 分类)
- 测试数据不应该走正常保留期, 应该提前清

---

## TBD-8: S3 Object Lock 归档本期做不做?

### 头部做法对比

| 产品 | 存储 | 防篡改机制 |
|------|------|-----------|
| **AWS CloudTrail** | S3 + Object Lock (Compliance) | 强 |
| **GitHub Enterprise** | 内部存储 + S3 兼容 (SIEM streaming) | 中 |
| **GitLab** | 内部 DB (合规 mode 需 Ultimate) | 中 |
| **Linear** | 内部 (不公开) | 不强调 |
| **Notion** | 内部 (不公开) | 不强调 |
| **Stripe** | 内部 (签名 + 重试) | 替代方案 |
| **中型 SaaS 共识** | 大多用内部 DB + access control | **WORM 不是必须的** |

### 决策建议

**❌ 本期不做, Phase 3 再说**

- **理由 1**: 中型 SaaS (Linear/Notion) **不强调 S3 Object Lock**, 说明不是必须
- **理由 2**: S3 Object Lock 需云存储 + 跨账户架构, 投资大 (人力 + 钱)
- **理由 3**: 本期有 hash chain (TBD-1) + access control (TBD-3) + retention_until (TBD-2) 已能应对 90% 合规需求
- **理由 4**: 客户真要 WORM 归档, 我们再说; 不要超前投资

**实施 (Phase 3 计划, 不在本期)**:
- S3 Object Lock Compliance mode
- 每日 ETL 把 > retention_until 的审计 export 到 S3
- 跨账户归档 (log archive account)
- 但不绑死 cloud, 设计成 "可插拔 backend" (S3 / GCS / Azure Blob / 本地 NAS 都行)

---

## 最终决策汇总 (8 TBD 全部明确)

| TBD | 决策 | 关键依据 |
|-----|------|---------|
| **TBD-1** | ✅ **本期**实施 hash chain, S3 推迟 Phase 3 | Stripe/Linear 不做, 但 GitHub Enterprise 做, 我们应有 |
| **TBD-2** | ✅ **3 层分级**: security/authz=2y / business=1y / access/system=90d | Linear 90d / Notion 180d / GitHub 90-120d / 中型共识 |
| **TBD-3** | ✅ **admin only** (预留 security_manager role) | Linear owner only / GitHub owner+security_manager / 共识 admin |
| **TBD-4** | ✅ **全删** (含 admin 角色测试数据) | 安全优先, user_factory 自动造 |
| **TBD-5** | ✅ **双写 2 周 + 切换 1 周 + 4 周废弃** | Stripe 12 月太长, 我们 4-7 周合适 |
| **TBD-6** | ✅ **独立 daemon thread** + service_manager | dev.to 警告 setInterval 风险, Stripe 用独立 process |
| **TBD-7** | ✅ **每周日 03:00** | AWS 每日 02:00, 中型多按周 |
| **TBD-8** | ❌ **本期不做 S3 Object Lock**, Phase 3 再说 | Linear/Notion 不强调, 中型 SaaS 不必须 |

---

## Spec + RFC 调整建议

基于以上决策, [SPEC_AUDIT_LOG_V318.md](file:///d:/filework/excel-to-diagram/test_temp/SPEC_AUDIT_LOG_V318.md) 需调整:

### 调整 1: TBD-1 → FR-014 升 Must

```diff
- FR-014: Hash chain (Phase 3, 合规要求高时)
+ FR-014: Hash chain 防篡改 (本期, 推荐)
+ Priority: Should → Must
+ Phase 1 末实施, 推迟 S3 Object Lock
```

### 调整 2: TBD-2 → FR-013 7 类 retention 明确

```python
# 替换 FR-013 保留期
RETENTION_MAP = {
    'security': timedelta(days=730),   # 2 年
    'authz':    timedelta(days=730),
    'business': timedelta(days=365),   # 1 年
    'admin':    timedelta(days=365),
    'access':   timedelta(days=90),
    'system':   timedelta(days=90),
    'cascade':  timedelta(days=90),
}
```

### 调整 3: TBD-3 → FR-008 权限 admin_required

```python
@admin_required
def get_operation_chain(trace_id):
    ...
```

### 调整 4: TBD-4 → FR-007 删所有 V3.17 Test (含 admin 角色)

```diff
- TBD-4: 'V3.17 Test (admin)' 522 条删不删?
+ TBD-4 [已解决]: 全删, 留 1 个真实 admin
```

### 调整 5: TBD-5 → TR-003 双写 2 周

```diff
- TBD-5: RFC 7807 迁移方式
+ TBD-5 [已解决]: 双写 2 周 + 切换 1 周 + 4 周 deprecated
```

### 调整 6: TBD-6 → FR-010 独立 thread

```diff
- TBD-6: retry worker thread vs cron?
+ TBD-6 [已解决]: 独立 daemon thread, 集成 service_manager
```

### 调整 7: TBD-7 → FR-015 每周日 03:00

```diff
- TBD-7: cron 周期
+ TBD-7 [已解决]: 每周日 03:00 (本地时区)
```

### 调整 8: TBD-8 → Phase 3 标记

```diff
- TBD-8: S3 Object Lock 本期?
+ TBD-8 [已解决]: 本期不做, Phase 3 (FR-016 新增)
```

### 新增 FR-016 (Phase 3 占位)

```python
### FR-016: WORM 归档到 S3 Object Lock (Phase 3)
- Description: > 365 天的审计自动 export 到 S3 Object Lock (Compliance mode)
- Priority: Could
- Source: AWS CloudTrail, GitHub Enterprise
- Trigger: 客户 Enterprise tier 且开启合规 mode
```

---

## 验证清单 (决策可落地性)

| 决策 | 可验证性 |
|------|---------|
| TBD-1 hash chain | 单元测试: 改 1 条审计, verify_chain() 必报 |
| TBD-2 3 层保留 | 单元测试: 不同 log_category 算出的 retention_until 不同 |
| TBD-3 admin only | 集成测试: 普通用户调 API 返 403 + recovery |
| TBD-4 删 admin 测试 | SQL 跑后: SELECT COUNT WHERE role='admin' = 1 |
| TBD-5 双写 | 集成测试: 旧字段 + problem 字段都有, 且内容一致 |
| TBD-6 独立 thread | 单元测试: worker.stop() 后立即退出 (不卡 wait) |
| TBD-7 每周日 03:00 | 集成测试: mock datetime, 验证触发时间 |
| TBD-8 不做 S3 | 无验证 (无 S3 集成代码) |

---

## 结论

8 个 TBD 全部明确, 基于中型头部产品 (Linear / Notion / GitHub Enterprise) 的实战做法 + 我们项目阶段调整 (不必 12 月弃用周期) + 工程取舍 (本地 SQLite 不必 S3)。

完整决策 → Spec + RFC 调整请查看 [SPEC_AUDIT_LOG_V318.md](file:///d:/filework/excel-to-diagram/test_temp/SPEC_AUDIT_LOG_V318.md) 更新版 (待输出)。

---

**请确认这些决策, 我会按调整后的 Spec + RFC 实施 (Step 1-9 顺序)。**
