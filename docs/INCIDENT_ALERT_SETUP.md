# INCIDENT_ALERT_SETUP.md - IM 告警配置 (V007.58+V007.59 2026-07-15)

> **目标**: yonaa 端出事故时, 5 分钟内推到运维手机 (飞书/钉钉/微信)
> **架构**: agent 端 (公司电脑, 有公网) 轮询 + 推送
> **适用**: yonaa 在阿里云 air-gapped 环境, 服务器无法直连公网 IM
> **作者**: AI Agent
> **更新**: 2026-07-15 (V007.59 加飞书应用机器人支持)

---

## 0. 为什么需要 agent 中转?

```
yonaa 服务器 (172.20.59.7, 阿里云 ECS)
  │
  │ 实测: TCP 80/443 可达, 但 HTTPS 握手被 reset/timeout
  │ DNS 解析正常, 但 HTTP 真正发请求被安全组拦截
  │
  │ 结论: 服务器无法直连公网 IM
  │
  ▼
agent 电脑 (公司电脑, 有公网)
  │
  │ Windows Task Scheduler 每 5 分钟
  │ → python tools/alert_monitor.py --check-now
  │
  │ 检查 yonaa 7 个关键端口
  │ 任一失败 → 推 IM webhook (飞书/钉钉/微信)
  │
  ▼
运维手机 (飞书/钉钉/微信群)
```

**网络测试结果** (2026-07-15 V007.58 实测):
| 目标 | 结果 |
|------|------|
| DNS 解析 baidu.com / feishu.cn / aliyun.com | ✅ OK |
| TCP connect 到 baidu.com:80 / feishu.cn:443 | ✅ OK |
| HTTPS GET feishu.cn | ❌ Connection reset / timeout |
| 阿里云 metadata 100.100.100.200:80 | ❌ timeout |
| 内网 172.20.59.7 (自己) | ✅ OK |
| 内网其他机器 10.6.x.x / 172.20.59.x | ❌ timeout |

---

## 1. 5 分钟快速开始 (运维)

### Step 0: 选 IM (V007.59 推荐飞书应用机器人)

**重要 V007.59 更新**: 飞书**自定义机器人 webhook** 在很多企业版被禁 (找不到入口), 改用 **飞书应用机器人 API** 走 `tenant_access_token` + `im/v1/messages`, **不被任何限制**。

| IM | 推荐度 | 不被禁 | 难度 |
|---|------|------|------|
| **飞书应用机器人 (lark_app)** | ⭐⭐⭐⭐⭐ | ✅ | 中 (10 分钟) |
| 钉钉 webhook | ⭐⭐⭐⭐ | ✅ | 低 (5 分钟) |
| 飞书 webhook | ⭐⭐⭐ | ❌ 可能被禁 | 低 (5 分钟) |
| 企业微信 webhook | ⭐⭐⭐ | ✅ | 低 (5 分钟) |

### Step 1: 飞书应用机器人 (推荐, V007.59)

#### 飞书 (Lark) webhook 获取
1. 打开飞书 → 群 → 设置 → 群机器人 → 添加机器人 → 自定义机器人
2. 安全设置: 选"签名校验", 复制 webhook URL + 签名密钥
3. URL 格式: `https://open.feishu.cn/open-apis/bot/v2/hook/<token>`

#### 飞书应用机器人 (V007.59 推荐) 获取

1. 打开 [飞书开放平台](https://open.feishu.cn/app) → 创建企业自建应用
2. 添加能力 → **机器人**
3. 凭证与基础信息 → 拿 `App ID` (cli_xxx) + `App Secret`
4. 权限管理 → 搜索 `im:message` → 勾选 `im:message:send_as_bot` 等
5. 版本发布 → 创建版本 → 发布
6. 飞书群 → 设置 → 群机器人 → 添加机器人 → 找到你的应用机器人 → 加入
7. 用 alert_monitor.py 列群: `python tools/alert_monitor.py --list-chats` → 拿 `chat_id`

#### 凭证安全 (强烈推荐用环境变量)

⚠️ `app_secret` 是敏感凭证, **绝对不要 commit 到 git**!

**推荐方式**: 用环境变量 (Windows 任务计划里设一次, 一直生效):
```powershell
$env:LARK_APP_ID="cli_xxx"
$env:LARK_APP_SECRET="xxx"
$env:LARK_CHAT_ID="oc_xxx"
python tools/alert_monitor.py --test-lark-app
```

**或 Windows 任务计划**: 创建任务时 → 操作 → 编辑 → 勾选 "设置环境变量" → 填 3 个变量。

#### 钉钉 webhook 获取
1. 群 → 群设置 → 智能群助手 → 添加机器人 → 自定义
2. 安全设置: 选"加签", 复制 webhook URL + 加签密钥
3. URL 格式: `https://oapi.dingtalk.com/robot/send?access_token=<token>`

#### 企业微信 webhook 获取
1. 群 → 添加群机器人 → 复制 webhook URL
2. URL 格式: `https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=<key>`

### Step 2: 配置

```bash
# 在公司电脑 (agent 端) 上, 一次性生成配置
cd d:\filework\release-prep-worktree\tools
python alert_monitor.py --init-config

# 编辑 alert_monitor_config.json, 填入 webhook URL
notepad alert_monitor_config.json
```

配置示例 (飞书 + 钉钉 + 企业微信):
```json
{
  "im": {
    "default": "feishu",
    "feishu": {
      "webhook": "https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxxxx",
      "secret": "SECxxxxxxxxxxxxxxxx"
    },
    "dingtalk": {
      "webhook": "https://oapi.dingtalk.com/robot/send?access_token=xxxxxxxx",
      "secret": "SECxxxxxxxxxxxxxxxx"
    },
    "wecom": {
      "webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxxxxxxx"
    }
  },
  "alert": {
    "interval_sec": 300,
    "cooldown_sec": 600,
    "at_all_on_fail": true,
    "at_all_on_recovery": false
  }
}
```

### Step 3: 测试推送

```bash
python alert_monitor.py --test-im
# 期望: [IM] feishu: OK
# 手机应收到: [TEST] yonaa IM 告警连通测试
```

如果失败, 检查:
- webhook URL 是否正确 (无空格, 无中文)
- 飞书/钉钉: 是否启用了"签名校验"→ secret 必须填
- 飞书: webhook host 是否为 `open.feishu.cn` (不是 `open.larksuite.com`)
- 钉钉: webhook 是否带 `access_token=`

### Step 4: 跑一次实际检查

```bash
python alert_monitor.py --check-now
# 期望: [OK] 全部健康
```

### Step 5: Windows 任务计划 (5 分钟循环)

1. 打开"任务计划程序" → 创建基本任务
2. 名称: `yonaa_alert_monitor`
3. 触发器: 每 5 分钟
4. 操作: 启动程序
   - 程序: `d:\filework\release-prep-worktree\tools\alert_monitor.bat`
   - 起始位置: `d:\filework\release-prep-worktree\tools`
5. 完成 → 双击任务 → 属性 → 勾选"不管用户是否登录都要运行"

或者用命令行注册:
```powershell
$action = New-ScheduledTaskAction -Execute "d:\filework\release-prep-worktree\tools\alert_monitor.bat"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "yonaa_alert_monitor" -Action $action -Trigger $trigger
```

---

## 2. 监控什么?

| 服务 | 端口 | 检查方式 | 重要度 |
|------|------|---------|--------|
| `log_service_prod` | 9101 | GET /api/health → 200 | ⭐⭐⭐⭐⭐ |
| `log_service_staging` | 19101 | GET /api/health → 200 | ⭐⭐⭐⭐ |
| `core_service_prod` | 9200 | GET / → 4xx/5xx (端口在 listen) | ⭐⭐⭐ |
| `core_service_staging` | 19200 | GET / → 4xx/5xx | ⭐⭐⭐ |
| `frontend` | 8081 | GET / → 200 | ⭐⭐⭐⭐ |
| `backend` | 3011 | GET /health → 200 | ⭐⭐⭐⭐ |
| `observability` | 9201 | GET / → 200 | ⭐⭐ |
| `log_service:process` | - | 远端 ps -ef 看到 log_service.py | ⭐⭐⭐⭐⭐ |

---

## 3. 告警逻辑

### 3.1 失败推送 (新失败)
- 条件: 上次健康, 本次失败
- 推送: `[ALERT] yonaa N 服务异常` + 失败清单
- `@所有人`: 取决于配置 `at_all_on_fail`

### 3.2 冷却 (cooldown)
- 默认 10 分钟
- 同一告警不重复推送 (避免刷屏)
- 失败变化 (新增/恢复) 触发新推送

### 3.3 恢复推送
- 条件: 上次失败, 本次全 OK
- 推送: `[OK] yonaa 全部恢复 (N)`
- 默认不 @所有人 (避免打扰)

### 3.4 错误状态文件
- 路径: `tools/alert_monitor_config_state.json`
- 内容: `{failed_keys: [...], last_alert_ts: ...}`
- 失败时写入, OK 时清空

---

## 4. 故障排查

### 4.1 告警没推到
1. 查 `tools/alert_monitor.log`
2. 看 `[IM]` 行 — 是否 "FAIL: ..."
3. 常见原因:
   - webhook URL 是占位符 (含 `<` `>` `替换`)
   - secret 错 (飞书/钉钉)
   - 网络问题 (公司电脑断网)

### 4.2 总是告警但实际正常
- 看 alert_monitor 输出 `ports: X/7 OK`
- 7 个里 1-2 个挂是正常 (例如 core_service 用 /api/health 返回 404)
- 修复: alert_monitor 已修正 (4xx 视为 OK, 5xx 视为 fail)

### 4.3 告警太频繁 (刷屏)
- 调大 `cooldown_sec` (默认 600 = 10 分钟)
- 关掉 `at_all_on_fail` (用 @具体人)

### 4.4 想去掉某个端口的监控
- 编辑 alert_monitor.py 的 YONAA_PROBE dict
- 或注释掉不需要的端口

---

## 5. 进阶: 多 IM 推送

如果想**飞书 + 钉钉双发**:
- 改 `run_once` 中的 `send_im` 调用, 改成循环 3 个 IM 类型

如果想**不同级别用不同 IM**:
- 改 `format_alert` 加 `level: 'critical'/'warning'/'info'`
- 在 `send_im` 中根据 level 选 IM

---

## 6. 替代方案 (备选)

| 方案 | 适用 | 优点 | 缺点 |
|------|------|------|------|
| **当前: agent 轮询 + 推 IM** | 服务器无公网 | 简单, agent 可控 | 5 分钟延迟 |
| agent WebSocket 长连接 | 服务器无公网 | 实时推送 | 复杂, 需 WebSocket 服务 |
| 服务器直推 IM | 服务器有公网 | 实时, 不依赖 agent | 服务器需开公网 |
| 内网 SMTP 邮件 | 公司有 SMTP | 简单 | 邮件比 IM 慢 |
| 阿里云短信 (CMS) | 服务器有公网 | 实时 | 收费 |

---

## 7. 相关工具

| 工具 | 用途 |
|------|------|
| `tools/alert_monitor.py` | agent 端守护 (5 分钟检查 + 推 IM) |
| `tools/alert_monitor.bat` | Windows 任务计划包装 |
| `tools/alert_monitor_config.json` | webhook 配置 (本地, 不提交) |
| `tools/alert_monitor_config_state.json` | 失败状态 (本地, 不提交) |
| `tools/alert_monitor.log` | agent 运行日志 |
| `tools/remote_capability_probe.py --check-systemd` | 备用检查 (server 端 systemd) |
| `tools/find_log_service_killer.py` | 出事故时找元凶 |

---

**总入口**: [AGENT_INFRA.md §1](AGENT_INFRA.md) | [DEPLOY_INFRASTRUCTURE.md §1.3 #25](../DEPLOY_INFRASTRUCTURE.md) | [INCIDENT_RESPONSE_RUNBOOK.md §9](INCIDENT_RESPONSE_RUNBOOK.md)