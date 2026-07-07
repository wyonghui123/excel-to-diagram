# SPEC: V007.38 PostgreSQL Migration (Detailed)

**作者**: 开发智能体 V047
**状态**: Draft, 待评审
**创建时间**: 2026-07-08
**预计执行**: 2026-07-15 起
**关联文档**: EVAL_PG_MIGRATION.md

---

## 1. 目标 (Goals)

将 yonaa 后端 db 从 SQLite (WAL) 迁移到 PostgreSQL 15+ (MVCC), 解决:
1. 单写锁导致的 task_scheduler 雪崩
2. 频繁的 disk I/O error (V007.34/35/37 修复链)
3. 读并发上限 (20 → 无)

**非目标**:
- 不动业务逻辑
- 不重写 schema, 仅等价翻译
- 不引入复杂中间件 (pgpool/citus), 单实例 PG 即可
- 不拆库 (不分库分表)

---

## 2. 验收标准 (Acceptance Criteria)

### 2.1 功能验收

| # | 项 | 标准 | 验证方式 |
|---|----|------|----------|
| AC-1 | 同一业务行为 | server.py 0 代码改动, 仅换 DATABASE_URL | git diff server.py = 0 |
| AC-2 | 数据一致 | SQLite → PG 行数 hash 一致 | SELECT count(*) = 117908+ |
| AC-3 | 测试通过 | 元测试 13/13 + 集成测试 100% | pytest + smoke_test.sh |
| AC-4 | 切流后无报错 | backend.log 24h 内 disk I/O error = 0 | log_service /api/log |
| AC-5 | 性能不下降 | 50 并发 list 响应时间 P95 < 1s | perf 脚本对比 |

### 2.2 非功能验收

| # | 项 | 标准 |
|---|----|------|
| AC-6 | 启动时间 | yonaa 重启到 5001 listening < 30s |
| AC-7 | db 大小 | PG 物理大小 < 200MB (含 indexes + WAL) |
| AC-8 | 回滚时间 | DATABASE_URL 切回 sqlite < 5 分钟 |
| AC-9 | 数据备份 | pg_dump 自动化 (cron 每日) |

---

## 3. 架构 (Architecture)

### 3.1 现有架构

```
[Browser 172.20.59.7:8081]
    ↓
[unified_server.py 8081]
    ↓ proxy /api/*
[server.py (Flask) 5001]
    ↓
[sql_connection_pool.py - 自实现 SQLite pool]
    ├─ Reader queue (max 20)
    ├─ Writer queue (WriteQueue 1 thread)
    └─ Connection lifecycle
    ↓
[SQLite WAL file: architecture.db (96MB)]
    ├─ WAL file
    └─ SHM file
```

### 3.2 目标架构

```
[Browser 172.20.59.7:8081]                                  ← 不变
    ↓
[unified_server.py 8081]                                     ← 不变
    ↓ proxy /api/*
[server.py (Flask) 5001]                                     ← 不变
    ↓
[SQLAlchemy 2.0 Engine/Connection Pool]                      ← 新增 P1
    ├─ QueuePool size=20 overflow=10
    ├─ connect_args={connect_timeout=5, application_name='meta-backend'}
    └─ Session (per-request)
    ↓
[sql_adapters.py 重构: SQLAlchemy dialect-aware SQL]         ← 重构
    ↓
[psycopg 3 (binary)]                                         ← 新增依赖
    ↓
[PostgreSQL 15 (127.0.0.1:5432 或 unix socket)]              ← 新增服务
    ├─ Database: meta
    ├─ User: meta_app
    └─ Tables, indexes (从 schema_generator 生成)
```

### 3.3 双 DB 兼容层 (过渡期)

保留 `DIALECT=sqlite` 时走老路径 (回滚用), `DIALECT=postgres` 时走新路径。

```python
# meta/core/datasource.py
class DataSource:
    def __init__(self, dialect=None):
        env_dialect = os.environ.get('META_DB_DIALECT', 'sqlite')
        self.dialect = dialect or env_dialect
        if self.dialect == 'sqlite':
            self._setup_sqlite()
        elif self.dialect == 'postgres':
            self._setup_postgres()
        else:
            raise ValueError(f'Unsupported dialect: {self.dialect}')

    def _setup_sqlite(self):
        # 现有逻辑不变
        self.engine = SQLiteConnectionPool(...)

    def _setup_postgres(self):
        # 新逻辑
        url = os.environ.get('DATABASE_URL',
                             'postgresql+psycopg://meta_app:****@127.0.0.1:5432/meta')
        self.engine = create_engine(url, pool_size=20, max_overflow=10)
```

---

## 4. 详细工作分解 (WBS)

### Phase 1: P0 - 缓解 (2026-07-08 ~ 2026-07-10, 3 天)

**目标**: 让 yonaa 稳定下来, 不再崩溃

#### Task 1.1: 部署 V007.20 busy_timeout=30s
**Commit**: 已经在 release-prep-worktree
**动作**: 部署智能体重打包 + 部署 sql_connection_pool.py
**验收**:
- `/api/db/health` 返回 `busy_ms: 30000`
- 50 并发不再 disk I/O error

#### Task 1.2: V007.38 task_scheduler 写路径 retry
**新 commit** V007.38
**改动**:
- 文件 `meta/core/task_scheduler.py` (待定位)
- 加 retry 包裹器 (跟 V007.34 类似, 5 次 + backoff)
- 仅 retry `sqlite3.OperationalError` (含 disk I/O error, database locked)

**验收**:
- task_scheduler 触发的 "Failed to create execution record" 不再崩
- 但仍要把数据写进去 (业务不能丢)

#### Task 1.3: 减小 mmap_size 64MB
**改动**: sql_connection_pool.py: `mmap_size = 268435456` → `mmap_size = 67108864`
**理由**: 256MB mmap 在视图失效时需要重建整个窗口, 64MB 减小代价
**验收**:
- 50 并发 P95 < 1s
- memory < 1GB

#### Task 1.4: V007.38 + 1.3 打包 + 部署
**部署**: 跟 V007.36 同样流程
**验收**:
- 9 项 + V8d + V8e invariant 全过
- yonaa 24h 监控: disk I/O error < 5 次

### Phase 2: P1 - 抽象层 (2026-07-11 ~ 2026-07-18, 1.5 周)

**目标**: SQLAlchemy 接入 + postgres dialect

#### Task 2.1: 加 SQLAlchemy 依赖
**文件**: `meta/requirements.txt`
**新增**:
```
SQLAlchemy>=2.0,<3.0
psycopg[binary]>=3.1
```

#### Task 2.2: 新增 `meta/core/postgres_pool.py`
**功能**: 包装 SQLAlchemy Engine, 提供与 SQLiteConnectionPool 兼容的接口
```python
class PostgresPool:
    def __init__(self, url):
        self.engine = create_engine(url, pool_size=20, max_overflow=10)
        # dialect = 'postgres'

    def acquire_reader(self) -> Connection:
        return self.engine.connect()

    def execute(self, sql, params=None) -> Result:
        with self.engine.connect() as conn:
            return conn.execute(text(sql), params or {})

    def release_reader(self, conn):
        conn.close()

    def execute_write(self, sql, params=None):
        with self.engine.begin() as conn:
            conn.execute(text(sql), params or {})
```

#### Task 2.3: SchemaGenerator 加 postgres 分支
**文件**: `meta/core/schema_generator.py`
**改动**:
```python
TYPE_MAPPING = {
    FieldType.STRING: "VARCHAR(200)",     # PG 同 SQLite
    FieldType.INTEGER: "INTEGER",         # PG 同 SQLite
    FieldType.FLOAT: "DOUBLE PRECISION",  # PG 用 DOUBLE, SQLite REAL
    FieldType.BOOLEAN: "BOOLEAN",         # PG 原生, SQLite INTEGER
    FieldType.TEXT: "TEXT",               # 一致
    FieldType.JSON: "JSONB",              # PG 二进制 JSON
    FieldType.UUID: "UUID",               # 新增
    FieldType.DATETIME: "TIMESTAMPTZ",    # PG 时区感知
}

# AUTOINCREMENT
parts.append(
    "INTEGER GENERATED ALWAYS AS IDENTITY" if self.dialect == "postgres"
    else "PRIMARY KEY AUTOINCREMENT" if self.dialect == "sqlite"
    else "PRIMARY KEY AUTO_INCREMENT"
)

# FOREIGN KEY
# PG 同 SQLite (语法相同), 但是 ON DELETE CASCADE 行为略不同
```

#### Task 2.4: sql_adapters.py 双 dialect
**新逻辑**:
```python
def execute(self, sql, params=None):
    if self.dialect == 'sqlite':
        return self._execute_sqlite(sql, params)
    else:
        return self._execute_postgres(sql, params)
```

**SQL 翻译表**:

| SQLite | PostgreSQL | 备注 |
|--------|------------|------|
| `?` | `%s` | 占位符, SQLAlchemy 已自动处理 |
| `datetime('now')` | `NOW()` | |
| `julianday()` | `EXTRACT(JULIAN ...)` 或 `to_char(..., 'J')` | |
| `IFNULL()` | `COALESCE()` | |
| `||` (字符串拼接) | `||` | 同 |
| `json_extract()` | `->>` 操作符 | PG 原生 JSONB |
| `FTS5 MATCH` | `MATCH AGAINST` 或 `tsvector @@ tsquery` | PG tsvector |
| `BEGIN IMMEDIATE` | `BEGIN ISOLATION LEVEL SERIALIZABLE` | |
| `INSERT OR REPLACE` | `INSERT ... ON CONFLICT DO UPDATE` | |
| `INSERT OR IGNORE` | `INSERT ... ON CONFLICT DO NOTHING` | |
| `GROUP_CONCAT()` | `STRING_AGG()` | |

**重点**: 用 SQLAlchemy `text()` + `bindparam()` 让占位符自动适配, 不手写翻译

#### Task 2.5: Postgres 本地 docker-compose (开发测试)
**文件**: `docker-compose.yml` (项目根)
```yaml
services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: meta
      POSTGRES_USER: meta_app
      POSTGRES_PASSWORD: devpass
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

**验收**:
- `docker compose up -d` 后 PG 可连接
- `psql -U meta_app -d meta` 能进

#### Task 2.6: 测试 conftest 加 PG fixture
**文件**: `meta/tests/conftest.py`
```python
@pytest.fixture(scope='session')
def pg_datasource():
    """测试用 PostgreSQL DataSource"""
    import os
    os.environ['META_DB_DIALECT'] = 'postgres'
    os.environ['DATABASE_URL'] = 'postgresql+psycopg://meta_app:devpass@localhost:5432/meta'
    ds = DataSource(dialect='postgres')
    # 初始化 schema
    from meta.core.schema_generator import SchemaGenerator
    SchemaGenerator(dialect='postgres').generate_all(ds)
    yield ds
    # teardown 不做 (PG 容器常驻)
```

**验收**:
- `pytest meta/tests/test_sql_connection_pool.py -k postgres` 全过

### Phase 3: P2 - 数据迁移 + 部署 (2026-07-19 ~ 2026-07-30, 1.5 周)

#### Task 3.1: 数据迁移工具
**文件**: `meta/scripts/migrate_sqlite_to_pg.py`
**功能**:
1. 读 SQLite 所有表 (SELECT name FROM sqlite_master WHERE type='table')
2. 业务表 (非 sqlite_%, 非 view) 用 SchemaGenerator(pg) 生成 DDL
3. 流式 COPY: `SELECT * FROM table` → PG `COPY table FROM STDIN`
4. 重建索引 (从 schema_generator)
5. 重建视图 (从 sqlite_master sql)

**迁移顺序** (考虑 FK 依赖):
1. users, roles (基础)
2. enums (enum_types, enum_values)
3. products (配置)
4. business_objects (配置)
5. field_metadata (配置)
6. 业务数据表 (data)
7. audit_logs, *_audit (数据, 量大最后)
8. 重建视图

**验收**:
- 迁移后 count(*) 与 SQLite 一致 (100% 行级)
- 抽样 100 条 hash 对比 (字段级)

#### Task 3.2: yonaa 安装 PG
**动作** (部署智能体):
```bash
# CentOS/RHEL 7 (yonaa)
yum install -y postgresql15-server postgresql15
postgresql15-setup initdb
systemctl enable postgresql15
systemctl start postgresql15

# 创建用户和 db
sudo -u postgres psql -c "CREATE USER meta_app WITH PASSWORD '...';"
sudo -u postgres psql -c "CREATE DATABASE meta OWNER meta_app;"
sudo -u postgres psql -c "GRANT ALL ON DATABASE meta TO meta_app;"

# 调优
echo "shared_buffers = 256MB" >> /var/lib/pgsql/15/data/postgresql.conf
echo "work_mem = 64MB" >> /var/lib/pgsql/15/data/postgresql.conf
echo "max_connections = 100" >> /var/lib/pgsql/15/data/postgresql.conf
```

**验收**:
- yonaa 上 `psql -U meta_app -d meta` 能连
- `select version();` 返回 PostgreSQL 15.x

#### Task 3.3: yonaa 迁移数据
**动作**:
```bash
# 1. 备份 SQLite
cp /opt/app/deployments/meta/architecture.db /tmp/architecture.db.bak

# 2. 跑迁移脚本
META_DB_DIALECT=sqlite python migrate_sqlite_to_pg.py

# 3. 校验
psql -U meta_app -d meta -c "SELECT count(*) FROM audit_logs;"
# 期望: 117908 (跟 SQLite 一致)
```

#### Task 3.4: 切流量
**动作**:
```bash
# /opt/app/deployments/.env (新增)
META_DB_DIALECT=postgres
DATABASE_URL=postgresql+psycopg://meta_app:****@127.0.0.1:5432/meta

# 重启 server.py
pkill -f "python3 server.py" ; sleep 2
systemctl start meta-server
# 或 nohup ...
```

**验证**:
- 登录 (user.authenticate)
- 列表 (bo list)
- 创建 (bo create)
- 导出 Excel

#### Task 3.5: 监控 7 天
**每日**:
- `[ ]` disk I/O error 数 (log_service)
- `[ ]` PG 连接数
- `[ ]` 慢查询 (> 100ms)
- `[ ]` 业务报错数
- `[ ]` 性能 P95

**应急**:
- 回滚脚本 `rollback_to_sqlite.sh` (改 DATABASE_URL, cp 备份回 SQLite 路径)

### Phase 4: P3 - 优化 (后续, 不在本 spec 范围)

- 索引重建与 EXPLAIN 分析
- 慢查询优化
- PG → read replica (如果业务继续增长)
- 表分区 (audit_logs 按月分区)

---

## 5. 数据迁移工具详细设计

### 5.1 文件

`meta/scripts/migrate_sqlite_to_pg.py` (新)

### 5.2 用法

```bash
python meta/scripts/migrate_sqlite_to_pg.py \
    --sqlite-path /opt/app/deployments/meta/architecture.db \
    --pg-url postgresql+psycopg://meta_app:****@127.0.0.1:5432/meta \
    --batch-size 1000 \
    --verify
```

### 5.3 主要流程

```python
def migrate(sqlite_path, pg_url, batch_size=1000, verify=True):
    # 1. 打开两个连接
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    pg_engine = create_engine(pg_url)
    
    # 2. 读所有表 (按 FK 顺序)
    tables = get_migration_order(sqlite_conn)
    
    # 3. 生成 PG schema
    from meta.core.schema_generator import SchemaGenerator
    sg = SchemaGenerator(dialect='postgres')
    
    # 4. 创建表
    for table in tables:
        meta_obj = load_meta_object_for_table(table)
        if meta_obj:
            create_sql = sg.generate_table(meta_obj)
            pg_engine.execute(text(create_sql))
    
    # 5. 拷贝数据
    for table in tables:
        copy_table_data(sqlite_conn, pg_engine, table, batch_size)
    
    # 6. 验证
    if verify:
        return verify_migration(sqlite_conn, pg_engine)
    return {'ok': True}
```

### 5.4 验证逻辑

```python
def verify_migration(sqlite_conn, pg_engine) -> dict:
    """每个表计数 + 抽样 hash 对比"""
    results = {'ok': True, 'tables': {}}
    
    tables = get_all_tables(sqlite_conn)
    for table in tables:
        sqlite_count = sqlite_conn.execute(
            f'SELECT count(*) FROM {table}'
        ).fetchone()[0]
        pg_count = pg_engine.execute(
            text(f'SELECT count(*) FROM {table}')
        ).scalar()
        
        if sqlite_count != pg_count:
            results['ok'] = False
            results['tables'][table] = {
                'sqlite_count': sqlite_count,
                'pg_count': pg_count,
                'diff': pg_count - sqlite_count
            }
            continue
        
        # 抽样校验 hash
        sample_size = min(100, sqlite_count)
        sqlite_sample = sqlite_conn.execute(
            f'SELECT * FROM {table} ORDER BY RANDOM() LIMIT {sample_size}'
        ).fetchall()
        # ... hash 对比每行
    
    return results
```

### 5.5 错误处理

- 表不存在 → 跳过, 警告
- 字段类型不兼容 → 记录日志, 跳过字段值 (e.g. PG BOOLEAN 不接受 'yes')
- 大表 (>100MB) → 分批, 显示进度
- FK 约束冲突 → 临时禁用, 全表加载后开启
- 失败 → 中断, 保留 pg db 用于诊断

---

## 6. 测试策略

### 6.1 单元测试 (P1 阶段)

| 测试 | 文件 | 期望 |
|------|------|------|
| SchemaGenerator postgres 分支 | test_schema_generator_pg.py | DDL 字符串正确 |
| PostgresPool 基本操作 | test_postgres_pool.py | connect/execute/close |
| sql_adapters 双 dialect | test_sql_adapters_dual.py | 同接口双实现 |
| 数据类型映射 | test_type_mapping.py | FieldType → SQL type |

### 6.2 集成测试 (P2 阶段)

| 测试 | 文件 | 期望 |
|------|------|------|
| 迁移工具跑通 | test_migrate_sqlite_to_pg.py | 行数 hash 一致 |
| PG 端 CRUD | test_pg_crud.py | 增删改查 |
| 业务接口在 PG 下跑 | test_api_pg.py | 登录/列表/创建/导出 |
| 50 并发不崩 | test_concurrency_pg.py | 500/500 成功 |

### 6.3 性能测试 (P2 阶段)

| 测试 | 命令 | 期望 |
|------|------|------|
| 50 并发 list | scripts/perf_50_concurrent.py | P95 < 1s |
| 1000 行导入 | scripts/perf_import_1k.py | < 30s |
| 100 个 user 创建 | scripts/perf_create_100_user.py | < 60s |

### 6.4 回归测试

**绝对不变项**:
- 业务接口路径 (`/api/v2/...`)
- 业务行为 (登录、权限、CRUD)
- 前端 Vue 代码

**可能微调**:
- 时间格式 (PG TIMESTAMPTZ vs SQLite TEXT)
- JSON 字段顺序 (PG JSONB vs SQLite TEXT)
- 大小写敏感 (PG 默认 sensitive, SQLite 默认 insensitive)

---

## 7. 风险与缓解

### 7.1 P0 阶段风险 (缓解)

| 风险 | 缓解 |
|------|------|
| V007.38 retry 把错误吞了 | logger.error 记录所有 retry, 暴露 retry_count metric |
| mmap_size=64MB 性能回退 | P95 监控, 必要时回滚到 256MB |
| 部署过程中 service 中断 | yonaa 部署是单进程, 选业务低峰 |

### 7.2 P1 阶段风险 (低)

| 风险 | 缓解 |
|------|------|
| SQLAlchemy 学习曲线 | 604 个 SQL 调用点分批迁移, 引入统一抽象 |
| SQLAlchemy 性能开销 | 大多数 query 走 Core (轻量), 不用 ORM |
| dialect 漏写一个 | 全量单测覆盖每个 FieldType + 每种表操作 |

### 7.3 P2 阶段风险 (中)

| 风险 | 缓解 |
|------|------|
| 数据迁移丢数据 | 迁移后逐表 count + 抽样 hash; 完整备份保留 |
| 业务接口 PG 下崩 | 全量 E2E 测试 + 灰度切流 (10% → 50% → 100%) |
| PG 性能不如预期 | 索引重建 + EXPLAIN + 调优 |
| 回滚困难 | 双 DB 并存 + DATABASE_URL 一键切换 |

### 7.4 业务风险

| 风险 | 缓解 |
|------|------|
| 切流期间服务中断 | 选业务低峰 (周末); 30 分钟窗口 |
| 审计日志不丢 | 117,908 行全量导出导入 + 校验 |
| 用户感知慢 | 性能 P95 监控 + 必要优化 |

---

## 8. 时间表

| 周 | 阶段 | 关键节点 |
|----|------|----------|
| W1 (7/8-7/14) | P0 缓解 | yonaa 稳定, disk I/O error < 5 次/天 |
| W2 (7/15-7/21) | P1 抽象层 | SQLAlchemy 接入, postgres dialect, 双 DB 测试 |
| W3 (7/22-7/28) | P2.1 准备 | 数据迁移工具开发完成 |
| W4 (7/29-8/4) | P2.2 部署 | PG 安装, 数据迁移, 切流 |
| W5 (8/5-8/11) | 监控 + 回滚预案 | 7 天观察期 |

**关键路径**: P1 SQLAlchemy 接入 (4 天) → 数据迁移工具 (5 天) → PG 部署 (3 天)
**并行**: 监控/回滚工具 (全程)

---

## 9. 资源需求

### 9.1 人力

| 角色 | 工作量 | 时间 |
|------|--------|------|
| 开发智能体 V047 | 5 周 | 全程 |
| 部署智能体 | 1 周 | P2.2 部署周 + 切流 |
| 测试智能体 | 0.5 周 | P2 测试 |
| PM/协调智能体 | 0.2 周 | 评审 + 决策 |

### 9.2 yonaa 资源

| 资源 | 现值 | 估增 |
|------|------|------|
| RAM | 14GB free | +1GB (PG shared_buffers + work_mem) |
| CPU | 4 cores | 同 |
| Disk | 多 GB free | +500MB (PG base + WAL) |

### 9.3 依赖

```
SQLAlchemy>=2.0,<3.0   # 已有 Python 环境, 直接 pip install
psycopg[binary]>=3.1    # PostgreSQL 15+ driver
```

可选:
```
alembic               # 后续 schema 迁移工具
pgwatch2              # 监控 (或 prometheus + pg_exporter)
```

---

## 10. 回滚 SOP

### 10.1 触发条件 (任一)

- 切流后 1 小时内 disk I/O error 不降反升
- 业务接口 50%+ 报错
- P95 性能下降 > 5x
- PG 进程无法启动

### 10.2 回滚步骤 (15 分钟内)

```bash
# 1. 停 server.py
systemctl stop meta-server  # 或 pkill

# 2. 切回 SQLite
echo "META_DB_DIALECT=sqlite" > /opt/app/deployments/.env

# 3. 验证 SQLite db 还在 (期间只读)
ls -la /opt/app/deployments/meta/architecture.db
# 应存在, 大小 ~96MB

# 4. 启动 server.py
systemctl start meta-server

# 5. 业务接口验证
curl http://localhost:5001/api/v2/action/user.authenticate -d ...
```

### 10.3 数据一致性 (回滚后)

切回 SQLite 后:
- P2 阶段新增的 user/role/audit 数据 (若有) **会丢**, 因为 SQLite 不接收新数据
- 业务报告"过去 N 分钟的数据不见了", 需要手动从 PG 导出 CSV 重新导入 SQLite (P3 阶段做)

### 10.4 后续

回滚后 24h 内:
- 1. 回滚报告 (原因 + 时间 + 影响)
- 2. 修复 PG 端问题
- 3. 重新切流 (或维持 SQLite)

---

## 11. 与现有 V007.xx 的关系

| 版本 | 关系 |
|------|------|
| V007.34 retry | 在 SQLite 路径下继续有效 (P0 后台找补) |
| V007.35 mmap/cache | 在 SQLite 路径下继续有效 (P0 调整 mmap_size) |
| V007.36 _is_debug | 不变 |
| V007.37 PRAGMA 幂等 | 不变, SQLite 路径下有效 |
| **V007.38 (本 spec)** | 迁移到 PG, 从此 SQLite 仅 fallback |

**V007.38 不取消前面任何修复**, 它们在回滚时仍然有效。

---

## 12. 不在本 spec 范围

明确**不做** (避免 scope creep):
- 拆库 / 分库
- 读写分离 (read replica)
- PG → 跨地域复制
- 性能调优 (索引/explain 单独 P3)
- 审计日志分区
- 数据分析 (BI 接入)
- 微服务拆分
- 全文检索迁移 (先暂用 SQLite FTS, 后续单独)

---

## 13. 评审检查清单

提交 spec 前确认:

- [ ] Phase 1 P0 工作量 ≤ 3 天?
- [ ] Phase 2 P1 风险 ≤ 中?
- [ ] Phase 3 P2 有完整回滚 SOP?
- [ ] 验收标准可量化?
- [ ] 测试覆盖率 ≥ 现有 (单元+集成)?
- [ ] 不破坏 AC-1 (server.py 不动)?
- [ ] 不在禁用列表 (拆库等)?

---

**作者**: 开发智能体 V047
**评审**: 待 PM + 协调智能体
**最后更新**: 2026-07-08