# prod `deployments/current` symlink 断链问题

> **发现日期**: 2026-07-14 | **优先级**: 中 | **状态**: 已知问题，待下次部署时修复
> **影响**: 回滚脚本依赖 current symlink，断链时回滚会失败

---

## 一、问题描述

在 2026-07-14 环境检查中发现，prod 环境的 `/opt/app/deployments/current` symlink 指向一个不存在的目录：

```bash
ls -la /opt/app/deployments/current
# lrwxrwxrwx  current -> v20260713_223807_staging
```

但 `v20260713_223807_staging` 是 **staging 版本号**，在 prod 的 `/opt/app/deployments/` 下不存在：
- prod 实际运行在 `/opt/app/deployments/meta/` 目录下
- staging 运行在 `/opt/app/staging/deploy/v20260713_223807_staging/`

## 二、根因分析

1. 7 月 13 日部署 staging 时，deploy.sh 脚本在**共享的 deployments 目录**下解压了 staging 版本
2. 部署完成后，`current` symlink 被切到了 staging 版本号
3. 之后 staging 迁移到独立目录 `/opt/app/staging/deploy/`，原 staging 版本目录被清理
4. 但 `current` symlink 仍指向已清理的目录 → **断链**

## 三、当前影响

| 功能 | 是否受影响 | 说明 |
|------|-----------|------|
| prod 前端访问 (8081) | ❌ 不受影响 | unified_8081.py 直接代理到 meta/ 目录 |
| prod 后端 API (3011) | ❌ 不受影响 | server.py 在 meta/ 目录下运行 |
| rollback.sh | ⚠️ 受影响 | 依赖 current symlink 定位旧版本 |
| check_deploy_health.sh | ⚠️ 受影响 | 检查 current/MANIFEST 是否存在 |
| 新版本部署 | ⚠️ 受影响 | deploy.sh PHASE 7 会覆盖 current，但 PHASE 0.5 可能检测异常 |

## 四、修复方案

### 方案 A: 修复 current symlink（推荐，下次部署时执行）

```bash
# 在下次部署时，deploy.sh PHASE 7 会自动修复 current
# 如果需要立即修复:
ln -sfn /opt/app/deployments/meta /opt/app/deployments/current

# 验证
ls -la /opt/app/deployments/current
# 应显示: current -> /opt/app/deployments/meta

cat /opt/app/deployments/current/MANIFEST 2>/dev/null
# 应能正常读取
```

### 方案 B: deploy.sh 增加断链检测（长期）

在 deploy.sh PHASE 0 (precheck) 中添加：

```bash
# 检查 current symlink 是否断链
if [ -L "/opt/app/deployments/current" ]; then
    CURRENT_TARGET=$(readlink /opt/app/deployments/current)
    if [ ! -d "/opt/app/deployments/$CURRENT_TARGET" ] && [ ! -d "$CURRENT_TARGET" ]; then
        echo "[WARN] current symlink is broken: -> $CURRENT_TARGET"
        echo "[FIX] Will be fixed by PHASE 7 after deployment"
    fi
fi
```

### 方案 C: prod 和 staging 使用独立 deployments 目录（V007.50 已实现）

V007.50 已将 staging 隔离到 `/opt/app/staging/deploy/`，staging 部署不再影响 prod 的 `/opt/app/deployments/`。

## 五、修复时间表

| 时间 | 操作 | 说明 |
|------|------|------|
| 2026-07-14 | 记录问题 | 本文档 |
| 下次部署 | 自动修复 | deploy.sh PHASE 7 切 current |
| 如需立即修复 | 手动 `ln -sfn` | 见方案 A |

---

## 六、相关文档

- [STAGING_GUIDE.md](STAGING_GUIDE.md) — staging 使用指南（V007.50）
- [../DEPLOYMENT.md](../DEPLOYMENT.md) — 完整部署指南
- [INCIDENT_RESPONSE_RUNBOOK.md](INCIDENT_RESPONSE_RUNBOOK.md) — 事故响应手册
