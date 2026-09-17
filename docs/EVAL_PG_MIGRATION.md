# PostgreSQL 迁移评估

**撰写**: 开发智能体 V047
**时间**: 2026-07-08
**背景**: yonaa SQLite disk I/O error 反复触发 (V007.34/35/36/37 修复链), 触发 task_scheduler 写路径争用雪崩
**目标**: 评估迁移到 PostgreSQL 的可行性, 工作量, 收益, 风险

---

## 1. 现状盘点 (基于代码静态分析)

### 1.1 代码规模

| 维度 | 数值 | 来源 |
|------|------|------|
| SQL 调用点 (含测试) | **604** | grep `self.ds.execute\|self.execute\|self.ds.fetch` 78 文件 |
| 业务表 | 50+ | yonaa /api/db/health 报告 |
| audit_logs 行数 | **117,908** | yonaa /api/db/health |
| db 大小 | **96.21 MB** | yonaa /api/db/health |
| db 路径 | 单一文件 `/opt/app/deployments/meta/architecture.db` | |
| WAL 模式 | wal | |
| busy_timeout | 5000ms (V007.20 未生效) | |
| max_readers (池) | 20 | sql_connection_pool.py:45 |
| 写线程 | 1 (WriteQueue) | sql_write_queue.py |
| 审计后台 | task_scheduler + audit_async_queue + async_audit_writer | 3 个写路径 |

### 1.2 架构特征

```
单文件 SQLite + WAL
  ├─ 读池 (20 connections, max_readers=20)
  ├─ 写队列 (1 writer thread, WriteQueue)
  └─ 审计后台 (task_scheduler 2min 周期 + audit_async_queue + async_audit_writer)
       ↓
  雪崩: 写失败 → 读连接失效 → 频繁创建 → 重复 PRAGMA → disk I/O error
```

### 1.3 触发 IO error 的 3 个写后台

```
1. task_scheduler  →  "Failed to create execution record"  (每 2 分钟)
2. audit_async_queue →  user/role CRUD 时的异步审计
3. async_audit_writer →  同上, 另一条路径
                   3 个写并发, 跟业务读争用 db
```

### 1.4 SchemaGenerator 现状 (关键)

```python
# meta/core/schema_generator.py:30-37
TYPE_MAPPING = {
    FieldType.STRING: "VARCHAR(200)",
    FieldType.INTEGER: "INTEGER",
    FieldType.FLOAT: "REAL",
    FieldType.BOOLEAN: "INTEGER",
    FieldType.TEXT: "TEXT",
    FieldType.JSON: "TEXT",
}

# line 167
parts.append("PRIMARY KEY AUTOINCREMENT" if self.dialect == "sqlite" else "PRIMARY KEY AUTO_INCREMENT")
```

**已支持 `dialect` 参数**, 但**只有 sqlite 和 mysql 两个分支**, **没有 postgres**。
**`dialect` 默认值是 'sqlite'** (从 data_source 拿, 但 data_source 实际没设置).

---

## 2. 迁移目标分析

### 2.1 PostgreSQL 能解决哪些问题

| 当前 SQLite 问题 | PostgreSQL 解法 | 价值 |
|------------------|-----------------|------|
| 单写 (WAL 写锁互斥) | MVCC, 多写并发 | ✅ 解决 task_scheduler 雪崩 |
| 20 读连接上限 (实际) | 无上限, 真并行 | ✅ 解决高并发读 |
| disk I/O error 频繁 | 独立进程, 真 OS 文件系统 | ✅ 物理隔离 |
| busy_timeout=5s 等不到 | 无此概念 (MVCC 读不阻塞写) | ✅ 根除 disk I/O error |
| WAL 持续增长 | 自动 checkpoint + archive | ✅ 简化运维 |
| FTS5 (内置) | 内置 tsvector + GIN 索引 | ✅ 同等或更强 |
| JSON 存 TEXT | JSONB 二进制 | ✅ 性能更好 |
| 无原生 UUID | pgcrypto 扩展 | ✅ 加分项 |

### 2.2 PostgreSQL 引入的新问题

| 问题 | 说明 | 影响 |
|------|------|------|
| 独立进程 | 需要启动 postmaster, 监听 5432 | 部署复杂度↑ |
| 客户端-服务器 | 每次 query 走网络 | 延迟↑ (~1ms) |
| 连接池 | 需用 psycopg / pgpool | 多一层 |
| 事务隔离 | 默认 READ COMMITTED, 跟 SQLite SERIALIZABLE 不同 | 业务代码需审视 |
| 类型差异 | BOOLEAN/JSON/UUID/ARRAY | 需 dialect 支持 |
| 数据库迁移 | 现有 96MB SQLite 数据需导出导入 | 一次性 |
| 索引重建 | 现有 50+ 业务表, 100+ 索引 | 一次性 |
| 测试环境 | 需本地起 PG, 或 testcontainer | 复杂度↑ |
| 备份/恢复 | pg_dump / pg_restore | 运维 SOP |
| 许可证 | PostgreSQL License (BSD-style) | ✅ 商业友好 |

---

## 3. 迁移方案设计

### 3.1 方案 A: 完整替换 (推荐) ⭐

**架构**:
```
[Flask server.py]
    ↓
[SQLAlchemy 2.0 Core]  ← 新加抽象层
    ↓
[psycopg 3 (async) / psycopg2 (sync)]
    ↓
[PostgreSQL 15+]
```

**步骤**:

1. **加 SQLAlchemy 抽象层** (1 周)
   - 引入 `sqlalchemy` + `psycopg[binary]`
   - 重写 `sql_adapters.py` 为 SQLAlchemy engine/session
   - `datasource.py` 改为 SQLAlchemy URL
   - 保留 `sqlite3` 路径作为开发环境 fallback

2. **SchemaGenerator 加 postgres dialect** (2 天)
   ```python
   if self.dialect == "postgres":
       # VARCHAR, SERIAL, BOOLEAN, JSONB, UUID, TIMESTAMPTZ
       # AUTOINCREMENT → SERIAL 或 GENERATED ALWAYS AS IDENTITY
       # TEXT → TEXT (一致)
       # REAL → DOUBLE PRECISION
   ```

3. **数据迁移工具** (1 周)
   - 用 `pgloader` 从 SQLite 拉到 PG
   - 或自写 `meta/scripts/migrate_sqlite_to_pg.py`:
     - 读 SQLite 所有表 (sqlite_master)
     - CREATE TABLE in PG (用 schema_generator)
     - 流式 COPY 数据
     - 重建索引/约束

4. **测试套件适配** (1 周)
   - 78 文件, 604 个 SQL 调用点
   - 改用 PG 的 conftest (Docker testcontainer 或 本地 PG)
   - 数据 fixtures 改用 PG 语法

5. **生产部署** (3 天)
   - yonaa 装 PG 15+ (`yum install postgresql15-server`)
   - 初始化 db cluster, 调优 (shared_buffers, work_mem)
   - 导入数据
   - 切流量 (server.py 改 DATABASE_URL)
   - SQLite 备 30 天回滚

**总工作量**: **4-5 周** (1 人)

### 3.2 方案 B: 混合模式 (过渡) ⭐⭐

**架构**:
```
[server.py]
    ↓
[SQLAlchemy]
    ↓
  ├─ SQLite (开发/test/小规模)
  └─ PostgreSQL (生产/yonaa)
       同一代码, 不同 DATABASE_URL
```

**额外工作**: +3 天 (SQLAlchemy 已经支持双 DB)

**优势**: 平滑过渡, 测试充分, 风险低

### 3.3 方案 C: 跑路式替换 (不推荐)

直接换 psycopg2, 不用 SQLAlchemy。
- 工作量看似少 (1 周)
- 实际: 604 个 SQL 调用点全手改 → 风险极高
- 失去 ORM 抽象, 后期维护难

---

## 4. 风险评估

### 4.1 技术风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| 数据丢失 | 🔴 高 | 迁移前完整 SQLite 备份; PG 导入前后 hash 校验 |
| 业务行为变化 | 🟡 中 | 全量测试 + 灰度切流 (10% → 50% → 100%) |
| 性能回退 | 🟢 低 | PG 默认比 SQLite 强; 用 pgbench 压测 |
| 死锁 | 🟡 中 | PG 死锁检测比 SQLite 强; 改事务隔离级别 |
| 时间类型 | 🟡 中 | SQLite TEXT vs PG TIMESTAMPTZ; 需显式 cast |
| BOOLEAN 转换 | 🟡 中 | SQLite INTEGER 0/1 vs PG BOOLEAN; SQLAlchemy 自动处理 |
| AUTOINCREMENT 语义 | 🟡 中 | SQLite 复用 ID vs PG SEQUENCE; 业务上一般无影响 |
| 外键 cascade | 🟡 中 | SQLite 需 PRAGMA foreign_keys=ON; PG 默认 ON |
| FTS 语法 | 🟡 中 | SQLite FTS5 vs PG tsvector/GIN; 需改 query |
| NULL 处理 | 🟢 低 | 一致 |

### 4.2 业务风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| 用户操作中断 | 🔴 高 | 选业务低峰 (周末) 切流; 完整回滚 SOP |
| 审计日志丢失 | 🔴 高 | 117,908 条不能丢; 全量导出 + 校验 |
| 性能更差 | 🟡 中 | PG 默认调优 + 索引重建 |
| 备份失败 | 🟡 中 | PG 有成熟 pg_dump; 配 cron |

### 4.3 运维风险

| 风险 | 等级 | 缓解 |
|------|------|------|
| PG 进程挂 | 🟡 中 | systemd unit + 自动重启 (log_service 同理) |
| OOM | 🟡 中 | shared_buffers 不能占满; 预留 |
| 连接数满 | 🟡 中 | 用 pgpool 中间件 |
| 慢查询 | 🟢 低 | 慢查询日志 + 自动 EXPLAIN |
| 磁盘满 | 🟢 低 | WAL 自动 archive 到 OSS |

---

## 5. 工作量分解

### 5.1 完整迁移 (方案 A/B) 时间表

| 阶段 | 内容 | 工作量 | 里程碑 |
|------|------|--------|--------|
| 1. SQLAlchemy 接入 | engine/session, 改 sql_adapters | 1 周 | 单元测试可跑 |
| 2. postgres dialect | schema_generator, type mapping | 2 天 | DDL 兼容 |
| 3. 数据迁移工具 | sqlite→pg 一次性脚本 | 1 周 | 全量数据可迁 |
| 4. 测试套件 | 78 文件适配, conftest, fixtures | 1 周 | 7×7=49 测试场景全过 |
| 5. yonaa 部署 | PG 15 安装, 调优, 切流 | 3 天 | 生产跑通 |
| 6. 观察 + 回滚预案 | 监控 7 天, 备份 30 天 | 1 周 | 稳定 |
| **合计** | | **5-6 周** | |

### 5.2 渐进方案 (P0-1-2-3)

| 阶段 | 范围 | 工作量 | 解决的问题 |
|------|------|--------|----------|
| **P0: 缓解** | 1) busy_timeout 30s 重新部署 2) task_scheduler 加 retry 3) mmap 改 64MB | 3 天 | 当前的 disk I/O error |
| **P1: 抽象** | SQLAlchemy 接入, 保留 SQLite 兜底 | 1.5 周 | 准备好 PG 接口 |
| **P2: 迁移** | 1) PG 安装 2) 数据迁移 3) 切流 | 1.5 周 | 切换到 PG |
| **P3: 优化** | 索引重建, 调优, 监控 | 1 周 | 性能最大化 |

**P0+P1+P2+P3 合计: 5 周** (跟方案 A 相当, 但分阶段降低风险)

---

## 6. 成本与收益

### 6.1 一次性成本

| 项 | 工作量 | 备注 |
|-----|--------|------|
| 人力 (开发智能体 V047) | 5 周 | 全职 |
| 部署智能体配合 | 1 周 | 部署 + 切流 + 回滚预案 |
| 测试智能体配合 | 1 周 | 性能基线 + 回归 |
| **总人力** | **7 人周** | |

### 6.2 长期收益

| 项 | 估算 |
|-----|------|
| 消除 disk I/O error 雪崩 | 100% |
| 读并发提升 | 10x+ (20 → 无上限) |
| 写并发提升 | ∞ (1 → 任意) |
| 减少 V007.xx 紧急修复 | 80%+ (不用再改 sqlite_busy/retry/pragma) |
| 简化运维 | WAL 文件管理 → PG 自动 |
| 准备 future scaling | 100GB 数据也能扛 |

### 6.3 长期成本

| 项 | 估算 |
|-----|------|
| yonaa 资源 | +1GB RAM (PG shared_buffers) |
| 维护成本 | 跟 SQLite 持平 (SOP 化后) |
| 备份 | pg_dump 100MB ~ 5s |

---

## 7. 决策建议

### 7.1 推荐: **P0 立即做, P1 启动, P2 看情况**

| 时间 | 行动 | 负责人 |
|------|------|--------|
| **本周** | 实施 P0 (busy_timeout + task_scheduler retry + 减小 mmap) | 开发 + 部署 |
| **下周** | 评估 P1 (SQLAlchemy 接入可行性) | 开发智能体 |
| **3 周内** | 决定是否启动 P2 (正式迁移 PG) | 协调智能体 + PM |
| **3 月内** | 完成 P2 (如果决策启动) | 全员 |

### 7.2 不推荐

- ❌ 立即直接迁 PG (没准备, 风险高)
- ❌ 用方案 C (裸 psycopg, 没抽象层, 后期维护噩梦)
- ❌ 继续打补丁 SQLite (V007.38, V007.39... 治标不治本)

### 7.3 决策前需要回答的问题

1. **业务增长预期**: 3 个月内 audit_logs 会不会破 50 万? 100 万?
2. **运维投入**: yonaa 团队是否接受多一个 PG 进程?
3. **回滚窗口**: PG 出问题, 多长时间必须能切回 SQLite?
4. **数据合规**: PG 是否能放在 yonaa (vs 独立 RDS)?
5. **未来微服务**: 是否要把 db 拆出去 (读写分离 / 分库)?

---

## 8. 立即可做的预备工作 (无风险, 高价值)

| # | 工作 | 工作量 | 价值 |
|---|------|--------|------|
| 1 | 在 `datasource.py` 加 `dialect` 字段 (默认 sqlite) | 1h | P1 铺垫 |
| 2 | 引入 `sqlalchemy` 依赖 (requirements.txt) | 1h | P1 准备 |
| 3 | 写一个 PostgreSQL docker-compose (本地开发) | 4h | P1/P2 测试环境 |
| 4 | schema_generator 加 postgres 分支 (不动 sqlite) | 1d | 验证可行性 |
| 5 | 跑 SQLAlchemy 兼容性测试 (单测) | 1d | 验证 ORM 抽象 |
| 6 | 写 SQLite→PG 数据迁移工具 (1 次性脚本) | 1d | 验证数据可迁移 |
| **合计** | | **4 天** | 零风险验证 P2 可行性 |

---

## 9. 备选: 不迁移的备选方案

如果决定不迁移 PG, 还能做的:

1. **审计日志归档** (移到独立 db)
   - audit_logs > 90 天 → 移到 audit_archive.db
   - 主 db 大小从 96MB 降到 < 30MB
2. **写路径异步化**
   - task_scheduler 改每 10 分钟 (而不是 2 分钟)
   - 写失败不抛, 进 dead letter queue
3. **读连接池扩到 50**
   - max_readers: 20 → 50
4. **定期 VACUUM**
   - 清理碎片, 减小 db 文件
5. **换 MySQL/MariaDB**
   - 单写限制没解决, 但运维工具更熟
   - **不推荐**, 治标不治本

---

## 10. 结论

**PG 迁移是值得的, 但不是"必须立即做"**。

当前问题可以用 P0 缓解, 给 P1+P2 留 4-6 周准备时间。
如果 3 个月内业务继续增长, P2 必须启动。

**当下最高 ROI 行动**: **P0 立即做** (3 天, 显著缓解当前问题)。
**次高 ROI**: **8 项预备工作** (4 天, 验证 P2 可行性, 零风险)。

---

**附录**:
- A. 关键代码引用 (line numbers)
- B. PostgreSQL vs SQLite 性能对比 (来自网络 benchmark)
- C. yonaa 资源评估 (CPU/RAM/Disk)
- D. 类似项目迁移案例 (Wiki.js, GitLab, Mastodon 等开源项目)