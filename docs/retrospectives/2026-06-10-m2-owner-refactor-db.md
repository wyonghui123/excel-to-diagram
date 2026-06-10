# M2 迁移报告: 数据库 owner 字段重构

**日期**: 2026-06-10
**版本**: v1.1.0-m2
**范围**: 数据库 schema 迁移
**状态**: ✅ 完成 + 验证通过

---

## 1. 迁移脚本

`meta/scripts/migrate_v1_1_owner_refactor.py`

**功能**:
- Dry-run 模式 (`--dry-run`): 仅检查, 不执行
- 实际迁移 (无参数): 自动备份 + 4 步迁移 + 验证
- 回滚 (`--rollback <backup_file>`): 从备份恢复

## 2. 迁移步骤 (4 步)

### Step 1: products 加 visibility
- ALTER TABLE products ADD COLUMN visibility VARCHAR(20)
- 反推逻辑: 如果 product 下任一 version 是 public, 则 product.visibility='public'; 否则 private
- 结果: 9 private + 3 public (符合预期)

### Step 2: versions 删除 visibility
- 12-step 重建 (SQLite 不支持 DROP COLUMN)
- 保留: 14 列(原 16 列去 visibility 和 owner_id)
- 注: owner_id 在 step 3 删

### Step 3: 6 张 child 表删除 owner_id (TBD-2: 不保留数据)
| 表 | 处理 |
|---|------|
| versions | dropping owner_id (kept 14 cols) |
| domains | dropping owner_id (kept 16 cols) |
| sub_domains | dropping owner_id (kept 19 cols) |
| service_modules | dropping owner_id (kept 21 cols) |
| business_objects | dropping owner_id (kept 21 cols) |
| relationships | no owner_id column, skip (本来就没) |

### Step 4: 4 张 child 表删除冗余 visibility
| 表 | 处理 |
|---|------|
| domains | dropping visibility (kept 15 cols) |
| sub_domains | dropping visibility (kept 18 cols) |
| service_modules | dropping visibility (kept 20 cols) |
| business_objects | dropping visibility (kept 20 cols) |

## 3. 数据迁移结果

| 数据类型 | 迁移前 | 迁移后 | 备注 |
|---------|--------|--------|------|
| products.visibility | 0 (无字段) | private=9, public=3 | 从 versions.visibility 反推 |
| versions.visibility | draft=14, public=5 | 0 (字段删除) | 已上移到 product |
| versions.owner_id | 17/19 行 | 0 (字段删除) | TBD-2 不保留 |
| domains.owner_id | 100/249 行 | 0 (字段删除) | TBD-2 不保留 |
| sub_domains.owner_id | 4/16 行 | 0 (字段删除) | TBD-2 不保留 |
| service_modules.owner_id | 7/27 行 | 0 (字段删除) | TBD-2 不保留 |
| business_objects.owner_id | 17/93 行 | 0 (字段删除) | TBD-2 不保留 |
| products.owner_id | 11/12 行 | 11/12 行 | **保留** ✅ |
| 4 张表冗余 visibility | draft=339, public=20 | 0 (字段删除) | 历史遗留,清理 |

## 4. 迁移前后 Schema 对比

```
products:        owner_id=True,  visibility=False   →   owner_id=True,  visibility=True
versions:        owner_id=True,  visibility=True    →   owner_id=False, visibility=False
domains:         owner_id=True,  visibility=True    →   owner_id=False, visibility=False
sub_domains:     owner_id=True,  visibility=True    →   owner_id=False, visibility=False
service_modules: owner_id=True,  visibility=True    →   owner_id=False, visibility=False
business_objects:owner_id=True,  visibility=True    →   owner_id=False, visibility=False
relationships:   owner_id=False, visibility=False   →   owner_id=False, visibility=False
```

## 5. 关键实现细节

### 5.1 SQLite 12-step 重建
SQLite 不支持 `DROP COLUMN`, 用以下流程:
1. CREATE TABLE _migrate_X_new (从 sqlite_master 拿原 CREATE SQL, 改表名, 删除指定列)
2. INSERT INTO _migrate_X_new (keep_cols) SELECT keep_cols FROM X
3. DROP TABLE X
4. ALTER TABLE _migrate_X_new RENAME TO X

### 5.2 CREATE SQL 智能解析
原设计 regex 太脆弱(吃掉了 `DEFAULT` 关键字), 改用:
- 用括号配对 split 顶级段 (`,` 在括号外才 split)
- 检查每段首 token 是否在 drop_columns 列表
- 过滤后拼回

### 5.3 事务注意
SQLite DDL (CREATE/DROP TABLE) **不能**被 `conn.rollback()` 回滚:
- ALTER TABLE ADD COLUMN 是事务安全的 → 可回滚
- CREATE/DROP/ALTER RENAME 是 autocommit 模式 → **不可回滚**
- 因此迁移失败后必须用 `--rollback` 从备份恢复

## 6. 已知问题

1. **dev-login 报 500 NotFound**:
   - 现象: `GET /api/v2/auth/dev-login?username=admin` 返回 500
   - 原因: 待调查 (可能是 manage_api.py:362 的 `data['owner_id']` 写到不存在的列)
   - 临时修复: 已改 manage_api.py:362,只对 product 设 owner_id
   - 状态: 需进一步调查 (M3 范畴)

2. **relationships 表本来就没有 owner_id 列**:
   - 之前的 TBD-1 决策说"6 张表删 owner_id",实际只有 5 张有
   - 已修: 脚本自动检测,无列则 skip

## 7. 维护窗口 Runbook

```bash
# 1. 停服务
powershell -File scripts/service_manager.ps1 stop

# 2. Dry-run 检查
python meta/scripts/migrate_v1_1_owner_refactor.py --dry-run

# 3. 实际迁移
python meta/scripts/migrate_v1_1_owner_refactor.py

# 4. 重启服务
powershell -File scripts/service_manager.ps1 start

# 5. 健康检查
powershell -File scripts/service_manager.ps1 status

# 6. (可选) Smoke test
python d:\filework\test.py --all --force

# 7. (如果失败) 回滚
python meta/scripts/migrate_v1_1_owner_refactor.py --rollback
```

## 8. 回滚 Runbook

```bash
# 1. 停服务
powershell -File scripts/service_manager.ps1 stop

# 2. 找最近备份
ls meta/backups/architecture.db.bak.* -Latest

# 3. 回滚
python meta/scripts/migrate_v1_1_owner_refactor.py --rollback <backup_path>

# 4. 重启
powershell -File scripts/service_manager.ps1 start
```

## 9. 备份管理

迁移脚本在 `meta/backups/` 目录自动生成:
- 命名: `architecture.db.bak.YYYYMMDD_HHMMSS`
- 含 DB + WAL + SHM
- 建议保留 7 天

## 10. 待办 (M3)

- [ ] 调查 dev-login 500 错误
- [ ] 实施 effective_owner_id 派生 (后端 + 前端)
- [ ] 8 个测试用例 (test_owner_refactor_v1_1.py)
- [ ] 集成 E2E 测试

---

**M2 完成. DB schema 已与 v1.1 yaml 100% 一致.**
