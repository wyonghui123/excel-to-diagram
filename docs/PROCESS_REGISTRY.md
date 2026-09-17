# PROCESS_REGISTRY — yonaa (172.20.59.7) 进程-端口归属登记表

> 建立日期: 2026-09-03 | 服务器原件: `/opt/app/PROCESS_REGISTRY.md`
> 建立动机: prod 8081 自伤性故障复盘 (docs/retrospectives/2026-09-03-prod-8081-outage-self-inflicted.md)
> **任何 pkill/kill 前必须先查此表。服务增删/端口变更/管理方式变更时必须同步更新（两处同步）。**

## 生产环境 (prod)

| 端口 | 服务 | 管理方式 | BIND | 说明 |
|---|---|---|---|---|
| 8081 | prod 前端网关 (unified) | **systemd: meta-unified.service** | 172.20.59.7 | /opt/app/deployments/lib/unified_8081.py → 代理 /api 到 172.20.59.7:5001 |
| 5001 | prod 后端 API | **systemd: meta-backend.service** | 172.20.59.7 | /opt/app/deployments/meta/server.py (current=v20260713_002); env: /opt/app/deployments/.env.prod (600) + /opt/app/.env_global |
| 9200 | core_service (能力服务) | systemd: core_service.service | *:9200 ⚠️0.0.0.0 | 合规 BIND 待收敛 (P2) |
| 9214 | dbops_audit_service | systemd: dbops_audit_service.service | 172.20.59.7 | 2026-09-03 清除 nohup 双主体 |
| 9215 | deploy_service | systemd: deploy_service.service | 172.20.59.7 | 2026-09-03 清除 nohup 双主体 |
| 9101 | log_service_prod | unit enabled 但 inactive | — | 停机原因不明, 待查 (P2) |
| ~~3011~~ | ~~prod 后端 (临时)~~ | 已废弃 | — | 2026-07 临时方案, 8/1 后弃用, 勿再启用 |

## staging 环境

| 端口 | 服务 | 管理方式 | BIND | 说明 |
|---|---|---|---|---|
| 13011 | staging 后端 | nohup (staging deploy 流程管理) | *:13011 | python -m meta.server |
| 18081 | staging 网关 | nohup: /opt/app/staging/tools/unified_18081.py | *:18081 | → 13011 |
| 19101 | log_service_staging | systemd: log_service_staging.service | *:19101 | |
| 19200 | **staging 工具链 exec/upload 通道** | nohup: core_service.py PORT=19200 | *:19200 | ⚠️ 运维工具链依赖 (token: v007.52), 严禁误杀; P2 systemd 化 |

## 操作铁律

1. **pkill/kill 前必查本表**: 确认目标端口的合法归属后用精确 `kill <pid>`; 严禁 `pkill -f` 模式匹配。
2. **恢复验收 = 端到端**: prod 恢复必须本机验证 `http://172.20.59.7:8081/` 200 + `/api/v1/enum-types` 200 + 真实登录成功; 严禁单点探活或拿 staging 冒充 prod。
3. **常驻进程禁止 nohup 长期运行 / /tmp 脚本启动**: 一律 systemd unit + EnvironmentFile。
4. **探活**: 每分钟 cron `/opt/app/shared/port_watchdog.sh` → 健康记 /var/log/port_watchdog.log, 失败记 /var/log/port_watchdog_alert.log (覆盖 8081/5001/13011)。
5. **SOP**: 重启用 `bash /opt/app/deployments/restart.sh` (lib/common.sh 已于 2026-09-03 恢复); 状态用 `status.sh`。
6. **密钥**: prod 密钥持久化在 /opt/app/deployments/.env.prod (mode 600); deploy.sh 再部署生成新密钥时必须同步更新。

## 遗留 P2 清单

- [ ] core_service (9200) BIND 收敛到 172.20.59.7
- [ ] 19200 staging 通道 systemd 化
- [ ] 9101 log_service_prod 停机原因排查
- [ ] 13011/18081 staging 进程 systemd 化
