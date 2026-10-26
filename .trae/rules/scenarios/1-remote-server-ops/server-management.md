# 服务器管理规范

> **最后更新**: 2026-09-02 | **状态**: 活跃
> **重大变更**: v2.0 引入 service_manager / start.ps1 / staging_watchdog 统一入口
> 旧版 taskkill/Test-NetConnection 仅适用于无 service_manager 的旧环境

---

## 一、本地开发环境（Windows）

### 1.1 唯一启动入口（强制）

```powershell
# 唯一推荐命令（覆盖所有 npm/python 直启方式）
powershell -File scripts/start.ps1

# 强制重启
powershell -File scripts/start.ps1 -Force
```

详见: [.trae/rules/project_startup.md](../../project_startup.md)

### 1.2 服务生命周期（service_manager）

```powershell
# 状态
powershell -File scripts/service_manager.ps1 status

# 启停
powershell -File scripts/service_manager.ps1 start
powershell -File scripts/service_manager.ps1 stop
powershell -File scripts/service_manager.ps1 restart
```

详见: [service-management-rules.md](../../service-management-rules.md)

### 1.3 服务守护（watchdog）

`scripts/watchdog.ps1` 每 30s 健康检查 + 自动修复。

详见: [project_startup.md](../../project_startup.md) §[CLIPBOARD]

### 1.4 禁止行为

| 禁止 | 原因 |
|---|---|
| 直接 `python dev.py` | 端口冲突（sandbox 隔离进程不可见） |
| 直接 `npm run dev` | 已被 npm script 重定向到 start.ps1，但仍保留 fallback |
| 用 `taskkill /F` 杀进程 | 多 Agent 环境下会误杀 |
| 用 `Get-Process` 判断状态 | sandbox 隔离下不可见 |

---

## 二、Staging 环境（Linux yonaa 172.20.59.7）

### 2.1 服务拓扑

| 服务 | 端口 | 进程 owner | 守护 |
|---|---|---|---|
| core_service | 19200 | nobody | staging_watchdog |
| log_service | 19101 | root | systemd + staging_watchdog |
| meta_backend | 13011 | root | staging_watchdog |
| unified_18081 | 18081 | nobody | staging_watchdog |

**依赖图**：
- core_service ← log_service
- core_service ← meta_backend（共享 DB）
- meta_backend ← unified_18081（API 代理）

**拓扑序 start order**: core → log → meta_backend → unified_18081
**拓扑反序 stop order**: unified → meta_backend → log → core

### 2.2 服务管理（staging_services.sh）

```bash
# SSH 上 staging 后
bash /opt/app/staging/bin/staging_services.sh list
bash /opt/app/staging/bin/staging_services.sh status <name>
bash /opt/app/staging/bin/staging_services.sh health
bash /opt/app/staging/bin/staging_services.sh start [name|--all]
bash /opt/app/staging/bin/staging_services.sh stop  [name|--all]
bash /opt/app/staging/bin/staging_services.sh restart <name>
bash /opt/app/staging/bin/staging_services.sh restart-deps <name>    # 目标服务 + 上游依赖
bash /opt/app/staging/bin/staging_services.sh topo                  # 看依赖图
```

**重要陷阱**：
- `restart <name>` 只重启单个服务，**不会拉上游依赖**
- `restart-deps <name>` 才重启目标服务 + 全部上游
- 想重启 18081 必须 `restart-deps unified_18081`（会先重启 13011/19200）

### 2.3 服务守护（staging_watchdog.sh）

**2026-09-02 v1.0 强制启用**，30s 周期健康检查 + 自动重启。

```bash
# 看状态
bash /opt/app/staging/bin/staging_watchdog.sh status

# 后台启动守护
nohup bash /opt/app/staging/bin/staging_watchdog.sh --watch --interval 30 \
    >> /opt/app/staging/logs/staging_watchdog.log 2>&1 &
disown

# 停止守护
bash /opt/app/staging/bin/staging_watchdog.sh stop
```

详见: [staging-process-guardian.md](../staging-process-guardian.md)

### 2.4 健康检查（staging_health_check.sh）

```bash
# 一键查 4 服务 + watchdog 状态
bash /opt/app/staging/tools/staging_health_check.sh
```

升级自 v2.0（2026-09-02）：从 2 个 endpoint 扩到 4 个。

### 2.5 远程运维安全

详见: [remote-server-alert-avoidance.md](../remote-server-alert-avoidance.md)

**铁律**：
- ❌ 禁止 SUID 提权 / chmod 4755 / cp /bin/bash /tmp/
- ❌ 禁止 stop / 卸载 aegis.service
- ✅ 用 sudo / pkexec / SSH 标准机制
- ✅ Python 服务必须 py3.11.9（防绿盟指纹回落）

---

## 三、核心服务架构冻结

详见: [core-service-architecture.md](../core-service-architecture.md)

| 服务 | 端口 (prod/staging) | 端点数 | 状态 |
|---|---|---|---|
| core_service | 9200 / 19200 | 4 | 冻结 |
| log_service | 9101 / 19101 | 10+ | 活跃 |
| ops_scheduler | 9202 | - | ⚠️ 未监听 |
| config_service | 9203 | - | 待创建 |
| dbops_service | 9204 | - | 待创建 |

**core_service 添加新端点前必过 4 问**（详见 core-service-architecture.md §3）。

---

## 四、消息通知服务（CRUD 反馈）

所有 CRUD 操作必须提供用户反馈：

```javascript
import { useMessage } from '@/composables/useMessage'
const message = useMessage()

async function handleSave() {
  try {
    const resp = await fetch('/api/...', { method: 'POST', ... })
    const data = await resp.json()
    if (data.success) {
      message.success('保存成功')
    } else {
      message.error(data.message || '保存失败')
    }
  } catch (e) {
    message.error('网络错误，请重试')
  }
}
```

**消息类型**：success / error / warning / info（详见 useMessage composable）

**禁止 alert()**。

---

## 五、导出功能规范

- 导出列名优先使用字段的 `ui.title` 配置
- 版本/产品线列通过 `default_exclude_fields` 排除
- 层级相关字段（父对象_name）不导出，通过 `hierarchy_fields` 排除
- Virtual 字段如需导出，需设置 `export_visible: true`

---

## 六、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-09-02 | AI Assistant | **v2.0**: 重写 §1-2，引入 service_manager + start.ps1 + staging_watchdog 统一入口；新增 staging 进程守护规范引用；新增核心服务架构冻结节；本地/staging 分章 |
| 2026-06-07 | AI Assistant | v1.0 从 project_rules.md 拆分 |
