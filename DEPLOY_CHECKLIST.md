# 部署前 Checklist（DEPLOY_CHECKLIST.md）

> 最后更新: 2026-07-12 | 适用范围: yonaa 生产部署
> 关联: BUG-V056/V060 复盘 (init_menu_permissions 幂等陷阱)

## 设计原则

**部署=代码+数据**。本 checklist 强制分离两者，避免"代码已部署但 DB 未更新"类问题。

---

## Phase 0：影响分析（**强制**）

> 不要上来就部署，先做静态分析。

- [ ] **代码变更类型识别**（PR/commits 标题 + 文件路径）：

| 类型 | 信号 | 后续必须执行 |
|------|------|------------|
| **纯逻辑修复** | interceptor / validator 改动 | Phase 1 + 2（重启即可） |
| **数据模型变更** | schema / `*.yaml` 改动 | **Phase 1.5 必须执行** |
| **菜单权限变更** | `init_menu_permissions.py` / menu SQL 改动 | **Phase 1.5 必须执行** |
| **数据库脚本** | `*.sql` / `init_*.py` 改动 | **Phase 1.5 必须执行** |

- [ ] **关联文件清单**（commit 中涉及的文件）：
  - 列出来 → 核对 → 识别哪些需要"数据迁移"

---

## Phase 1：代码部署

- [ ] **代码同步**：`meta/ → deploy_bundle/`
  ```powershell
  python -c "import shutil,os; src=r'D:\filework\release-prep-worktree\meta'; dst=r'D:\filework\release-prep-worktree\deploy_bundle\meta'; [shutil.copy2(os.path.join(r,f), os.path.join(d,f)) for r,_,fs in os.walk(src) for f in fs]"
  ```

- [ ] **前端构建**：
  ```bash
  cd d:\filework\release-prep-worktree\frontend
  npm run build
  ```

- [ ] **批量上传**：
  ```bash
  python d:\filework\release-prep-worktree\tools\batch_upload.py
  ```

---

## Phase 1.5：数据迁移（**V007.49-A 新增**）

> 这是本次 BUG-V056 修复的关键。如果涉及菜单权限 / DB schema，必须执行。

### 1.5.1：菜单权限增量同步（v007.49-A 修复后自动执行）

修复后**不再需要手动执行** init_menu_permissions.py：
- 服务重启时**自动**检测变更并 UPSERT
- 输出 `[SUMMARY] menu_permissions: +N 新增, ~N 更新`
- 如果是 [V007.49-A] 之前的部署，运行：
  ```bash
  cd /opt/app/deployments/meta/scripts
  python3 init_menu_permissions.py /opt/app/deployments/meta/architecture.db
  ```

### 1.5.2：DB Schema 变更

如果 commits 包含 schema 改动：
- [ ] 确认有对应 migration SQL
- [ ] **备份** DB：
  ```bash
  cp /opt/app/deployments/meta/architecture.db \
     /opt/app/deployments/meta/architecture.db.bak.$(date +%Y%m%d_%H%M%S)
  ```
- [ ] 在 **dev 环境**先执行 migration 测试
- [ ] 执行到生产：
  ```bash
  python3 migration_xxx.py
  ```

### 1.5.3：种子数据 / 静态数据变更

如果包含 `init_menu_permissions.py` / `init_role_xxx.py` / `seed_xxx.sql`：
- [ ] 在 dev 执行后比对前后差异（diff）
- [ ] 在生产执行后比对前后差异
- [ ] 验证关键 record（如 `relationship:create` 是否存在）

---

## Phase 2：服务重启与验证

- [ ] **重启服务**（按依赖顺序）：
  1. backend (5001)
  2. unified_server (8081)
  3. core_service (9200) — 如受影响
  4. log_service (9101)

- [ ] **健康检查**：
  ```bash
  curl -k https://172.20.59.7:9200/health   # core_service
  curl http://172.20.59.7:8081/api/v2/health # unified_server
  ```

---

## Phase 3：业务验证

- [ ] **权限验证**（v007.49-A 新增）：
  ```bash
  python verify_menu_perms.py --menu arch-data
  # 应返回: ✓ menu arch-data contains relationship:create/update/delete
  ```

- [ ] **关键功能烟测**：
  - 登录 admin → 进入架构数据 → 创建关系 → 应成功（验证 BUG-V056 修复）
  - 进入审计日志 → 应可见

---

## 违规后果（必须重视）

| 跳过 Phase | 后果 |
|-----------|------|
| 跳过 Phase 0 | 不知道部署什么，回滚难 |
| 跳过 Phase 1 | 代码不一致 |
| **跳过 Phase 1.5** | **本次 BUG-V056 根因：代码部署但 DB 不更新** |
| 跳过 Phase 3 | 业务带病上线，用户发现问题 |

---

## 关联文档

- [DEPLOY_SOP_V2.md](./DEPLOY_SOP_V2.md) - 完整部署 SOP
- [OPS_MANUAL.md](./OPS_MANUAL.md) - 远程运维服务介绍
- [docs/HANDOFF_V20260712_002.md](./HANDOFF_V20260712_002.md) - BUG-V056 复盘

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-12 | AI Assistant | 创建（基于 BUG-V056 复盘），Phase 1.5 为新增 |