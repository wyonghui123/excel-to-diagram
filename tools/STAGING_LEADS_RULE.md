# Staging 领先铁律 — prod 部署的前置条件

> 制定时间: 2026-09-14
> 背景: prod 停更 2 个月后部署 delta-7, 出现 2 个月代差 (v070-v086), 彩排才发现 6 个关键问题 (migration_runner 状态管理 / 列名 backfill / v084 适配等). 必须把"staging 领先 prod 24h + 全链彩排" 写进铁律.
> 适用范围: 任何 prod 后端代码或迁移变更.

---

## 铁律 (强制)

**prod 后端代码 / 迁移部署前, 必须满足**:

1. **staging 必须已领先部署相同 commit 至少 24 小时**, 且:
   - staging 浏览器级核心场景验证 PASS (deploy_test 登录 + 至少 1 个业务页面)
   - 24h 内 staging 后端无 crash / 无重启 / 无 health 异常

2. **必须完成全链彩排**:
   ```bash
   python tools/rehearsal_lifecycle.py start --tag <feature> --port 13xxx --db-path /tmp/rehearsal_<feature>.db
   # 跑全链迁移:
   python -m meta.core.migration_runner --db-path /tmp/rehearsal_<feature>.db --dry-run
   python -m meta.core.migration_runner --db-path /tmp/rehearsal_<feature>.db
   # 跑对账基线验收:
   python tools/_r4_check.py  # 类比 delta-7 用的 _r4_check.py
   # 验收通过才能部署 prod
   python tools/rehearsal_lifecycle.py stop --tag <feature>
   ```

3. **prod 部署命令必须显式说明 staging 领先时长**:
   ```
   # deploy_topology.yaml / deploy runbook 必填:
   staging_deployed_at: <ISO 时间>
   staging_soak_hours: <整数, ≥ 24>
   rehearsal_passed: true
   ```

---

## 例外 (需 PM 授权 + 额外补救)

紧急 hotfix (P0 服务不可用) 例外放行, 但必须:
- hotfix 部署 prod 后立即部署 staging (补 staging 领先)
- 6h 内补一次彩排 (哪怕只跑迁移链)
- 通知 PM 在 prod 后台盯 30min 黄金指标

---

## 验收脚本 (CI / 部署前自检)

```bash
# 查 staging 后端 mtime:
STAGING_BIN="/opt/app/staging/deploy/current"
NOW=$(date +%s)
STAGING_MTIME=$(stat -c %Y "$STAGING_BIN/server.py")
SOAK_HOURS=$(( (NOW - STAGING_MTIME) / 3600 ))
if [ $SOAK_HOURS -lt 24 ]; then
    echo "BLOCK: staging 仅领先 ${SOAK_HOURS}h, 必须 ≥ 24h"
    exit 1
fi

# 查 staging 进程健康:
if ! systemctl is-active staging-backend.service >/dev/null 2>&1; then
    echo "BLOCK: staging-backend 不健康"
    exit 1
fi

# 查彩排目录残留 (上次彩排应在 7 天 TTL 内):
python tools/rehearsal_lifecycle.py list
```

---

## 历史事故

| 日期 | 事件 | 教训 |
|------|------|------|
| 2026-09-13 | delta-7 prod 部署, 距上次 prod 部署 2 个月, 全链彩排才发现 6 个迁移问题 | staging 必须领先 24h + 全链彩排强制化 |

---

## 关联工具 (本批新增)

- `tools/rehearsal_lifecycle.py` — 彩排 transient unit 生命周期 (start/stop/list/cleanup)
- `tools/safe_kill.py` — 清理守卫 (pid + cmdline + cwd 三重校验)
- `meta/core/migration_runner.py --frontend-only` — 前端-only 部署跳过迁移守卫
- `tools/staging-backend.service` — staging 后端 systemd unit (替代孤儿进程)