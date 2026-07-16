# 部署 SOP V2 - 防范"代码已部署 ≠ 数据已生效"

> 制定时间: 2026-07-12  
> 更新时间: 2026-07-14 — 补充 V007.50 DB 路径统一、staging 部署 SOP
> 背景: 今日部署 BUG-V056 关系权限修复时, 代码已部署但 DB 中缺失关系 CRUD 权限, 导致前端无法勾选关系编辑权限  
> 目标: 避免下次类似问题

---

## 一、问题回顾

### 1.1 现象

今日 commit `d9256bb` 修改了 `meta/scripts/init_menu_permissions.py`, 在 arch-data 菜单的 `bo_bindings` 和 `required_permissions` 中补全了 relationship 的 create/update/delete 权限。

部署后验证:
- 文件已上传 (4 后端 + 115 前端, 共 119 个文件) ✓
- 后端 API 正常 (v2 user/role 返回 200) ✓
- 前端 SPA 已刷新 (新 hash index-DBDrRMS8.js) ✓

但前端反馈: 关系的编辑/管理权限无法看到。

### 1.2 根因

`init_menu_permissions()` 函数有幂等保护:

```python
if perm_count > 0 and menu_count > 0:
    print(f"[SKIP] init_menu_permissions: 已有 {perm_count} 权限 + {menu_count} 导航, 跳过")
    return
```

这导致:
- DB 初始化后, 函数永远不会再执行
- 代码层的变更 (新增 relationship CRUD) 无法反映到 DB
- "代码已部署 ≠ 数据已生效"

### 1.3 影响范围

凡是修改了以下文件的部署, 都需要数据迁移:
- `meta/scripts/init_menu_permissions.py` - 菜单权限声明
- `meta/scripts/init_task_menus.py` - 任务菜单
- `meta/scripts/init_task_seed_data.py` - 任务种子数据
- `meta/scripts/init_auth.py` - 认证初始化
- `meta/migrations/*.py` - 数据库迁移

---

## 二、改进措施

### 2.1 [P0 - 必须] 改进幂等保护为增量更新

修改 `meta/scripts/init_menu_permissions.py` 的跳过逻辑:

```python
# 之前 (全量跳过):
if perm_count > 0 and menu_count > 0:
    print(f"[SKIP] init_menu_permissions: 已有 {perm_count} 权限 + {menu_count} 导航, 跳过")
    return

# 之后 (增量更新):
# 1. 总是执行, 但只更新变化的部分
# 2. 对每个 menu_code 检查 required_permissions 是否齐全
# 3. 对每个 bo_binding 检查 include_actions 是否齐全
```

### 2.2 [P0 - 必须] 部署 checklist 增加数据迁移步骤

```
[DEPLOY CHECKLIST V2]
[OK] 1. 文件已上传 (X/X)
[OK] 2. 后端服务已重启 (pid changed)
[OK] 3. 前端 SPA 已刷新 (new hash)
[OK] 4. 服务健康检查 (log_service/ops_scheduler/...)
[  ] 5. 数据迁移已执行 (init_menu_permissions 等)
[  ] 6. DB 一致性验证 (代码声明 ⊆ DB 实际)
[  ] 7. 业务端到端验证 (UI 可用新功能)
```

### 2.3 [P1 - 重要] 部署验证脚本增强

`verify_deploy.py` 应增加:

```python
def verify_permissions(commit_list):
    """验证本次部署涉及的权限声明是否生效"""
    for commit in commit_list:
        if 'BUG-V' in commit.message and 'perm' in commit.message:
            # 该 commit 修改了权限, 必须验证 DB
            check_menu_permissions_in_db()
            check_bo_bindings_in_db()
            check_jwt_contains_required_perms()
```

### 2.4 [P2 - 改进] 引入迁移版本号

在 `architecture.db` 中添加 `system_meta` 表:

```sql
CREATE TABLE IF NOT EXISTS system_meta (
    key VARCHAR(100) PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO system_meta (key, value) VALUES 
    ('perm_schema_version', '2026-07-12-V060'),
    ('last_migration', '2026-07-12T19:50:00Z');
```

`init_menu_permissions()` 检查版本号, 如果代码版本 > DB 版本, 触发全量更新。

### 2.5 [P2 - 改进] 添加 daily 一致性巡检

新增 `tools/daily_consistency_check.py`:

```python
def check_code_db_consistency():
    """每日巡检: 检查代码声明的权限 ⊆ DB 实际存在的权限"""
    code_perms = parse_permissions_from_code()
    db_perms = query_permissions_from_db()
    
    missing = code_perms - db_perms
    if missing:
        send_alert('CRITICAL', 
            f'代码声明了权限 {missing} 但 DB 中不存在, '
            f'需要执行 init_menu_permissions 或手动迁移')
```

加入 ops_scheduler 每 6 小时执行一次。

---

## 三、立即可执行的临时方案

如果 2.1 还没改, 部署涉及 `init_menu_permissions.py` 时:

```bash
# 手动触发数据迁移
python -c "
import sys; sys.path.insert(0, '/opt/app/deployments')
from meta.scripts.init_menu_permissions import init_menu_permissions
init_menu_permissions('/opt/app/deployments/meta/architecture.db')
"
```

注意: 当前的 `init_menu_permissions()` 不会更新已有数据, 这个命令可能无效。  
需要先用 `delete from menu_permissions where menu_code='arch-data'` 之类的语句清掉再执行。

或参考今日的处理:
```python
# 直接更新 DB
conn.execute(
    "UPDATE menu_permissions SET required_permissions=? WHERE menu_code='arch-data'",
    (json.dumps([...补全后的权限列表...]),)
)
conn.execute(
    "UPDATE menus SET bo_bindings=? WHERE menu_code='arch-data'",
    (json.dumps([...补全后的 bo_bindings...]),)
)
conn.commit()
```

---

## 四、流程改进

### 4.1 部署三阶段

```
阶段 1: 代码部署 (5-10 分钟)
  - 上传文件
  - 不需要重启 (Python 缓存由阶段 2 处理)

阶段 2: 服务重启 + 数据迁移 (3-5 分钟)
  - 重启 meta_server (加载新拦截器)
  - 执行 init_menu_permissions (补全权限)
  - 执行其他迁移脚本

阶段 3: 验证 (2-3 分钟)
  - 服务健康检查
  - DB 一致性检查
  - 关键 API 调用验证
  - UI 关键路径验证
```

### 4.2 跨智能体协作规范

当多个智能体并行工作时:
- 每个智能体提交时, 必须标注本次是否涉及数据迁移
- 涉及数据迁移的, 必须在 PR/commit 中明确说明
- 主智能体 (打包部署角色) 必须主动询问每个智能体是否需要数据迁移

### 4.3 [V007.50 新增] staging 部署 SOP

**先 staging 后 prod 是铁律**。任何代码改动必须先在 staging 跑通 8 项 smoke test 才能部署到生产。

```
步骤 1: 改代码 (本地)
  ↓
步骤 2: 部署到 staging
  bash /opt/app/staging/scripts/deploy_staging.sh
  (自动: 8 smoke test + 5 min 监控, 失败自动回退)
  ↓
步骤 3: staging OK 后, 部署到生产
  bash /tmp/deploy_bundle/deploy.sh --version v20260714_001 --port 3011
  ↓
步骤 4: 5 min 后无问题, 部署完成
```

**staging 端口架构 (V007.50)**:
- unified_18081 (前端代理): 18081
- server.py (后端): 13011
- log_service: 19101
- core_service: 19200

详见 [docs/STAGING_GUIDE.md](docs/STAGING_GUIDE.md)。

### 4.4 [V007.50 新增] DB 路径统一验证

**问题根因**: 20+ 个 API/service 模块用 `__file__` 路径计算 `architecture.db` 位置，不读环境变量。导致 DataSource cache key 不同，创建了第二个 instance 用部署包内 db（重新部署会丢失测试数据）。

**修复方案**: `start_staging.sh` 第 0.3 步把 `deploy/current/architecture.db` 替换为 symlink → `/opt/app/staging/meta/architecture.db`。

**部署后必须验证**:
```bash
# 检查进程 fd 中只有 1 个 .db 文件
ls -la /proc/$(pgrep -f 'staging/deploy/current/server.py')/fd/ | grep '\.db'
# 应只看到 /opt/app/staging/meta/architecture.db

# 检查 symlink
ls -la /opt/app/staging/deploy/current/architecture.db
# 应显示: architecture.db -> /opt/app/staging/meta/architecture.db
```

如果验证失败，说明 DB 路径未统一，重新部署会丢失测试数据。

---

## 五、checklist

部署完成后, 必须完成以下检查:

- [ ] 文件上传成功 (数量与预期一致)
- [ ] 后端服务已重启 (进程 PID 改变)
- [ ] 前端资源已更新 (JS hash 变化)
- [ ] 所有服务健康 (log_service 9101, core_service 9200, unified 8081, backend 3011)
- [ ] **本次涉及 init_*/migrations/*.py 的话, 数据迁移已执行**
- [ ] **DB 中权限声明与代码一致**
- [ ] **关键 API 返回符合预期** (用 admin 登录测试)
- [ ] **UI 关键路径可用** (浏览器端到端验证)
- [ ] **[V007.50] staging 部署后 DB 路径统一验证通过** (仅 staging 部署需要)
- [ ] **[V007.50] 进程 fd 中只有 1 个 .db 文件** (仅 staging 部署需要)

---

## 六、相关文档

- [DEPLOYMENT.md](DEPLOYMENT.md) — 完整部署指南（V007.50 更新）
- [docs/STAGING_GUIDE.md](docs/STAGING_GUIDE.md) — staging 使用指南（V007.50 4 端口架构）
- [docs/OPS_MANUAL.md](docs/OPS_MANUAL.md) — 远程运维服务智能体使用手册
- [docs/INCIDENT_RESPONSE_RUNBOOK.md](docs/INCIDENT_RESPONSE_RUNBOOK.md) — 事故响应手册
- [docs/PERFORMANCE_BASELINE.md](docs/PERFORMANCE_BASELINE.md) — 性能基线（2026-07-14）
- [tools/log_service.py] — 包含 /api/exec 用于远程执行修复
- [.trae/rules/core-service-architecture.md](../.trae/rules/core-service-architecture.md) — 元能力服务架构铁律