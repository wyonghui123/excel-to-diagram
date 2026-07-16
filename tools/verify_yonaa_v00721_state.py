#!/usr/bin/env python3
"""
verify_yonaa_v00721_state.py - yonaa 当前状态对账

V46 架构: SERVER_DIR = $DEPLOYMENTS_DIR/meta (共享根)
- V007.20 fix 在 /opt/app/deployments/meta/core/sql_connection_pool.py (你之前 grep 确认)
- V007.20 fix 在 /opt/app/deployments/meta/services/import_export_service.py (你之前 grep 确认)
- 旧 cache_manager (async with) 在 /opt/app/deployments/meta/core/enums/cache_manager.py
- /opt/app/current -> /opt/app/deployments/v20260706_021 (你之前确认, 但 v20260706_021 现在状态未知)

之前我加的 "mv 到 VERSION_PATH" 逻辑导致 yonaa 上:
  unzip 解到 DEPLOYMENTS_DIR/ 根
  mkdir v20260706_021/
  mv DEPLOYMENTS_DIR/meta -> v20260706_021/meta
  mv DEPLOYMENTS_DIR/frontend_dist_files -> v20260706_021/frontend_dist_files
  mv DEPLOYMENTS_DIR/MANIFEST -> v20260706_021/MANIFEST
  mv DEPLOYMENTS_DIR/telemetry -> v20260706_021/telemetry
  mv DEPLOYMENTS_DIR/mcp -> v20260706_021/mcp

yonaa 上当前:
  /opt/app/deployments/v20260706_021/meta/              (V007.21 修复)
  /opt/app/deployments/v20260706_021/frontend_dist_files/
  /opt/app/deployments/v20260706_021/MANIFEST
  /opt/app/deployments/v20260706_021/telemetry/
  /opt/app/deployments/v20260706_021/mcp/
  /opt/app/deployments/meta/  (空)
  /opt/app/deployments/frontend_dist_files/  (空)
  /opt/app/current -> v20260706_021  (指向 v20260706_021 但 V46 架构本应指向 v20260704_007)

修复: 把 v20260706_021/ 内容 mv 回 DEPLOYMENTS_DIR/ 根
"""

print("""
yonaa 实际状态分析:
====================

1. V46 架构: SERVER_DIR = $DEPLOYMENTS_DIR/meta (共享根)
   yonaa 上 V007.20 fix (busy_timeout + skip_audit) 就在 DEPLOYMENTS_DIR/meta/

2. 之前 yonaa 上 current 软链接指向 v20260704_007 (我之前推断错了)
   实际: yonaa 21:58 部署后, v20260704_007 不存在 (V46 deploy 不创建 VERSION_PATH)
   所以 current 当时是断链 (但 V46 架构不在乎, server code 在 DEPLOYMENTS_DIR/meta)

3. 我之前加的 mv 逻辑 (VERSION_PATH 创建 + mv 5 项) 破坏了 V46 架构:
   - DEPLOYMENTS_DIR/meta 被 mv 到 v20260706_021/meta
   - 现在 DEPLOYMENTS_DIR/meta 是空
   - SERVER_DIR (=$DEPLOYMENTS_DIR/meta) 不再有效
   - deploy.sh 后续 (cd $SERVER_DIR, systemd WorkingDirectory=$SERVER_DIR) 都会失败

修复命令 (单条, yonaa SSH):
  cd /opt/app/deployments && mv v20260706_021/meta ./ && mv v20260706_021/frontend_dist_files ./ && mv v20260706_021/MANIFEST ./ && mv v20260706_021/telemetry ./ && mv v20260706_021/mcp ./ && rmdir v20260706_021

修复后状态:
  /opt/app/deployments/meta/  (V007.21 修复)
  /opt/app/deployments/frontend_dist_files/  (V007.21 修复)
  /opt/app/deployments/MANIFEST
  /opt/app/deployments/telemetry/
  /opt/app/deployments/mcp/
  /opt/app/deployments/v20260706_021/  (空, 但 current 软链接还指向它, 断链)
  /opt/app/current -> v20260706_021  (断链, 但 V46 架构不在乎)

然后 deploy.sh 跑 (用 V46 原版 - 不含我之前加的 mv 逻辑):
  - PHASE 0.5: meta/ 存在, frontend_dist_files/ 存在, V007.21 cache_manager fix 也在
  - NEED_UNZIP = false
  - skip unzip
  - dist hash 验证 (用 root index.html)
  - 继续 PHASE 1-7

但 dist hash 验证需要 zip 在, 让我看 V46 deploy.sh --skip-unzip 路径...
""")
