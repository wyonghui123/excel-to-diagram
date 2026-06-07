# 🆕 v3.14: Admin Unlock Cron 配置

> **日期**: 2026-06-06
> **状态**: ✅ 脚本 + 文档已就绪

---

## 🎯 背景

admin 账号在**5+ 次登录失败**后被自动锁。这是**安全设计**。但也会导致:
- 真实用户输错密码被锁
- CI / 自动化测试中累积失败导致锁
- 紧急情况下无法立即恢复

**解决**: 提供 `scripts/unlock_admin.py` 脚本, 可被 cron / Task Scheduler 定期调用。

---

## 📁 文件

```
scripts/
└── unlock_admin.py        # 🆕 v3.14: 解锁脚本
```

---

## 🚀 Usage

### 1. 一次性手动解锁

```bash
python scripts/unlock_admin.py
```

**输出** (admin 已 active):
```
✅ admin 已 active, 无需解锁 (last_failed: 2026-06-06T04:30:00)
```

**输出** (admin 被锁):
```
✅ admin 已解锁 (status: locked → active) at 2026-06-06T05:00:00
```

**输出** (admin 已被禁用, 需人工):
```
⚠️ admin 已被禁用 (disabled), 不会自动解锁 (需人工介入)
```

### 2. Dry Run (查状态, 不修改)

```bash
python scripts/unlock_admin.py --dry-run
```

### 3. 监控模式 (守护进程)

```bash
python scripts/unlock_admin.py --watch 60
```

每 60s 检查一次, 自动解锁。

### 4. 自定义 DB 路径

```bash
python scripts/unlock_admin.py --db /path/to/other.db
```

---

## ⏰ Cron 配置

### Linux (crontab)

```bash
# 编辑 crontab
crontab -e

# 添加 (每 5 分钟检查一次)
*/5 * * * * cd /path/to/project && python scripts/unlock_admin.py >> /var/log/admin-unlock.log 2>&1
```

### Windows (Task Scheduler)

```powershell
# 创建任务
$action = New-ScheduledTaskAction -Execute "python.exe" `
  -Argument "D:\filework\excel-to-diagram\scripts\unlock_admin.py" `
  -WorkingDirectory "D:\filework\excel-to-diagram"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
  -RepetitionInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName "BO-Action-Admin-Unlock" `
  -Action $action -Trigger $trigger `
  -Description "每 5 分钟检查并解锁 admin 账号"
```

### Docker (在容器内)

```dockerfile
# Dockerfile
RUN echo "*/5 * * * * cd /app && python scripts/unlock_admin.py >> /var/log/admin-unlock.log 2>&1" > /etc/cron.d/admin-unlock
RUN chmod 0644 /etc/cron.d/admin-unlock
RUN crontab /etc/cron.d/admin-unlock
```

### Windows Service (NSSM)

```powershell
# 用 NSSM 安装为服务
nssm install BOActionAdminUnlock "C:\Python314\python.exe" "D:\filework\excel-to-diagram\scripts\unlock_admin.py --watch 60"
nssm set BOActionAdminUnlock AppDirectory "D:\filework\excel-to-diagram"
nssm start BOActionAdminUnlock
```

---

## 🔐 安全考虑

| 维度 | 评估 |
|------|------|
| **自动解锁 disabled** | ✅ 不会 (仅解锁 locked/failed/suspended) |
| **DB 路径权限** | ✅ 需 OS 级别读/写权限 |
| **审计** | ⚠️ 建议加 audit log 记录解锁事件 |
| **远程调用** | ✅ 脚本仅本地, 不暴露网络端口 |

### 加 audit log (建议)

修改 `unlock_admin.py` 加 audit log:

```python
# 写入 audit_log 表
conn.execute("""
    INSERT INTO audit_log (event_type, target_user, action, performed_at)
    VALUES ('admin_unlock', 'admin', 'auto', ?)
""", (datetime.now().isoformat(),))
```

---

## 🧪 测试

### 1. 解锁被锁的 admin

```bash
# 1. 触发锁定 (用错密码登录 5+ 次)
for i in 1 2 3 4 5 6; do
  curl -X POST -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"wrong"}' \
    http://localhost:3010/api/v2/action/user.authenticate
done

# 2. 验证被锁
python -c "import sqlite3; print(sqlite3.connect('meta/architecture.db').execute(\"SELECT status FROM users WHERE username='admin'\").fetchone())"

# 3. 解锁
python scripts/unlock_admin.py

# 4. 验证
python -c "import sqlite3; print(sqlite3.connect('meta/architecture.db').execute(\"SELECT status FROM users WHERE username='admin'\").fetchone())"
```

### 2. 监控模式测试

```bash
# 终端 1: 启监控
python scripts/unlock_admin.py --watch 10

# 终端 2: 触发锁
for i in 1 2 3 4 5 6; do
  curl -X POST -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"wrong"}' \
    http://localhost:3010/api/v2/action/user.authenticate
done

# 终端 1 应在 10s 内输出 "admin 已解锁"
```

---

## 🔗 关联文档

| 文档 | 关系 |
|------|------|
| [bo-action-v3.14-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.14-result.md) | 进度档 |
| [ci.md](file:///d:/filework/excel-to-diagram/docs/ci.md) | A 选项 (CI) |
