# 部署通用化基础设施 (通用 5 工具)

> [2026-09-16] 针对 staging round 15 v087/v088/v089 部署事故沉淀的通用基础设施。
> **设计原则**: 全部工具**不假设具体表名/列名/SQL 方言/部署目标**, 任何项目都可以复用。

## 背景

staging 部署 round 15 期间发现三个深层次问题:

1. **代码 / DB schema drift**: 部署目录里的 init_auth.py / init_menu_permissions.py
   里 `role_id` 列名未重命名为 `permission_set_id` (v087 改动遗漏), 但 staging DB
   是 prod 备份 (已应用 v087), server 启动时报 `no such column: role_id`.
2. **Watchdog 假成功**: unified_18081 反向代理在 server.py 死了之后仍返 200 OK,
   `curl http://127.0.0.1:13011/` 看起来 "健康" 但实际服务挂了。
3. **部署动作不可追溯**: 谁、什么时候、传了什么文件、是否成功, 全部靠口头/git log 推断。

## 5 个工具一览

| 工具 | 作用 | 优先级 |
|------|------|--------|
| `code_db_compat_check.py` | AST 提取 SQL 列引用 vs DB schema 对比 | P0-1 |
| `pre_deploy_validator.py` | 部署前通用校验编排器 (插件式) | P0-2 |
| `migration_deploy_sync.py` | 部署目录 migrations vs DB schema_migrations diff | P1-1 |
| `service_health_probe.py` | 多路径探活 (HTTP+进程+DB+introspect+migration tail) | P1-2 |
| `audit_viewer.py` | 部署动作 JSONL 审计 + viewer | P2 |

---

## 1. `code_db_compat_check.py`

**问题**: 代码里 SQL 引用了 DB 没有的列 (rename / drop 后漏改)。

**用法**:
```bash
python tools/code_db_compat_check.py \
    --files meta/scripts/init_auth.py meta/scripts/init_menu_permissions.py \
    --db db.sqlite \
    --json --exit-code
```

**实现**:
- `ast` 提取 .py 里所有 string literal, 过滤 SQL-like
- `sqlparse` (首选) + 正则 (兜底) 解析 (table, column, op) 引用
- `sqlite3.PRAGMA table_info` + `sqlite_master` 读 schema
- 对比: code 引用 column 是否在 table 存在

**输出**:
```json
{
  "db_tables_count": 9,
  "compatibility_issues": [
    {"file": "...", "line": 29, "table": "users", "column": "last_login_at",
     "reason": "column not found in table"}
  ],
  "ok": false
}
```

---

## 2. `pre_deploy_validator.py`

**问题**: 多类校验散落各处, 部署前需要一个统一编排器。

**用法**:
```bash
# 直接跑
python tools/pre_deploy_validator.py --files f1.py f2.py --db db.sqlite --json

# 被 deploy_upload 内部调用
from pre_deploy_validator import validate_files
report = validate_files(files, db_path)
if not report['ok']:
    abort()
```

**实现**:
- `BaseChecker` 接口: `run(files, context) -> {checker, issues, stats}`
- `CodeDBChecker` 默认实现, 包装 `code_db_compat_check`
- `DEFAULT_CHECKERS` 注册表: 顺序执行, 可 `--skip` / `--enable`

**扩展**:
```python
class MyCustomChecker(BaseChecker):
    name = "my_check"
    def run(self, files, context):
        return {"checker": self.name, "issues": [...]}

DEFAULT_CHECKERS.append(MyCustomChecker())
```

---

## 3. `migration_deploy_sync.py`

**问题**: 部署目录的 migrations 文件和 DB schema_migrations 表不一致 (drift)。

**用法**:
```bash
python tools/migration_deploy_sync.py \
    --migrations-dir meta/migrations \
    --db db.sqlite \
    --json --exit-code
```

**实现**:
- `rglob("*.py")` 扫描 migrations 目录, 自动提取版本前缀 (v\d+, fix_, add_ 等)
- 读 DB `schema_migrations` 表 (自动 `CREATE IF NOT EXISTS`)
- diff: in_files_only / in_db_only / common
- **drift_count = len(in_db_only)**: DB 跑过但部署目录找不到 (DRIFT = WARN)

**典型 drift 场景**:
- staging DB 是 prod 备份 (已跑 v087+), 部署目录是旧版
- 历史 migration 被删, 但 DB 没清理 schema_migrations
- 部署目录用错分支

---

## 4. `service_health_probe.py`

**问题**: 单点探活不可靠 (代理假成功), 需要多路径加权评分。

**用法**:
```bash
python tools/service_health_probe.py \
    --target staging \
    --probe-port 13011 \
    --probe-path / \
    --process-pattern server.py \
    --db-path /opt/app/staging/db.sqlite \
    --expected-table users \
    --introspect-module meta.api.v2_bo.bo_user \
    --deploy-root /opt/app/staging/deploy/current \
    --tail-migrations 5 \
    --json --exit-code
```

**5 个探活点** (独立可调用):

| 探活 | 权重 | 作用 |
|------|------|------|
| `probe_http_port` | 1.0 | curl 端口 + 检查 body (避免代理假 200) |
| `probe_process_alive` | 2.0 | `ps aux \| grep` 至少 1 个匹配 (高权重) |
| `probe_db_schema` | 1.5 | sqlite3 连通 + 关键表存在 |
| `probe_python_introspect` | 1.0 | 远端 import, 看 `__file__` 是不是 deploy_root 里 |
| `probe_migration_tail` | 0.5 | 最近 N 条 migration status 都是 SUCCESS |

**整体判定**: `overall_score >= 0.5` 才算 OK (加权通过率)。

**绑定 exec_fn**: 自动尝试 `from staging_round import remote_exec`, 拿到 exec_fn 走远端模式 (ls / ps / sqlite3 / python import)。

---

## 5. `audit_viewer.py` + `.staging_deploy_audit.jsonl`

**问题**: 部署动作不可追溯, 失败排查靠 git log + 记忆。

**JSONL 格式** (一行一记录):
```json
{"ts": "2026-09-16T07:39:09Z", "action": "upload", "target": "staging",
 "files": ["meta/scripts/init_auth.py"], "ok": false, "duration_sec": 0.066,
 "actor": "deploy-upload", "drift_count": 4, "stale_count": 0,
 "error": "pre-deploy validator failed", "note": "abort by pre-deploy validator"}
```

**用法**:
```bash
# 追加 (deploy_upload 自动调用)
python tools/audit_viewer.py append --action upload --target staging \
    --file meta/scripts/init_auth.py --fail --drift-count 4 --error "..."

# 查看最近 20 条
python tools/audit_viewer.py tail -n 20

# 按 target 过滤
python tools/audit_viewer.py tail --target staging -n 10

# 失败统计
python tools/audit_viewer.py stats --since 2026-09-01
```

**deploy_upload 自动审计**:
- 成功上传 → 记 OK + drift_count + stale_count
- 失败 → 记 FAIL + error + note (`abort by pre-deploy validator` / `abort by stale check`)
- dry-run → 记 `upload-dry-run` (不会真的改远端)

---

## 集成效果

### 部署前 (在 `deploy_upload.py upload` 中自动串联):

```
1. pre_deploy_validator (SQL vs DB schema)
   ↓ 4 drift 检出
2. [ABORT] (除非 --force-drift-acknowledge)
   ↓ 放行
3. _stale_check (prod 远端 mtime 检查)
   ↓ 0 stale
4. 上传
   ↓
5. audit JSONL 自动记录
```

### 部署后:

```bash
# 看本次部署是否触发了 validator / stale check
python tools/audit_viewer.py tail --target staging -n 5

# 强制 staging 服务真活 (多路径加权)
python tools/service_health_probe.py --target staging \
    --probe-port 13011 --process-pattern server.py \
    --introspect-module meta.api.v2_bo.bo_user --deploy-root ...
```

---

## 通用性保证

| 维度 | 具体保证 |
|------|----------|
| 表名/列名 | 不假设 (正则 + AST 提取, 任意 DDL/DML) |
| 部署目标 | 不假设 (target 由 CLI 参数传入) |
| 服务端口/路径 | 不假设 (probe-port / --probe-path CLI) |
| 文件类型 | .py 走 AST, 其他文件可加新 Checker |
| 数据库 | SQLite 内置, 其他类型可加 db_check 包装 |
| 操作人 | 由 actor CLI 参数传入, 不假设 CI/手工 |

---

## 历史

- **2026-09-16**: 5 工具完成 + 本地测试通过 + commit
- 解决 staging round 15 v087/v088/v089 部署事故的 3 个深层次问题