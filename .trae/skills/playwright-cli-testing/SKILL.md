---
name: "playwright-cli-testing"
description: "Playwright CLI 高效测试工作流。Token 消耗比 MCP 低 4-5x，适用于长流程测试、回归测试和 CI 集成。CLI 通过常驻浏览器守护进程保持 session 稳定。"
---

# Playwright CLI 高效测试工作流

> **Token 效率**：~27K tokens/任务（vs MCP ~114K）
> **适用场景**：长流程测试 (>10 步)、回归测试、CI 自动化
> **浏览器工具规范：** `.trae/rules/SESSION_REMINDER.md` — 场景 A（自动化测试）禁止 MCP 工具，场景 B（开发调试）允许
> **认证规范**：`.trae/rules/frontend-test-auth.md`
> **验证方法**：`.trae/rules/browser-test-verification.md`

## 一、核心优势

| 维度 | Playwright CLI | 优势 |
|------|---------------|------|
| Token 消耗 | ~27K/任务 | 原生 Python 执行，无中间序列化 |
| 并行隔离 | 天然隔离 | 每个 Agent 独立浏览器进程 |
| Session 稳定性 | 常驻进程 | 命令间保持存活 |
| 跨浏览器 | Chrome/Firefox/WebKit | 全面支持 |
| CI 集成 | 原生支持 | 标准化 |

## 二、唯一合法入口

> **重要：不要用 `python -c "..."` 命令行。PowerShell 转义复杂，易出错。始终写 Python 脚本文件再运行。**

```python
import sys; sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
    # ... 你的测试操作 ...
    cli.screenshot('result.png')
```

**运行方式：**
```bash
# [X] 禁止：-c 命令行（PowerShell 转义地狱）
python -c "from test_helpers.browser_auth_cli import PlaywrightCLI; cli = PlaywrightCLI(); ..."

# [OK] 正确：写脚本文件再运行
python debug_filter.py
```

## 三、验证方法（速查）

> **完整方法表见 `.trae/rules/browser-test-verification.md`**

**最常用：**

```python
# 表格验证
table = cli.assert_table('.el-table')
assert table['rowCount'] > 0

# 一行验证：操作 + 追踪变化
result = cli.verify_action(
    "document.querySelector('.el-checkbox').click()",
    store_name='boCrud'
)
print(result['diff'])  # { changed: true, changes: { boCrud: { ... } } }

# 三层追踪：Store + DOM + Network
cli.start_all_tracking('.el-table')
cli.click('.save-btn')
cli.wait_for_stable()  # 智能等待，不盲目 sleep
changes = cli.get_all_changes()

# 跨层一致性
consistency = cli.verify_table_consistency('boCrud', '.el-table')
assert consistency['ok']

# 自动错误检测
err = cli.assert_no_errors()
assert err['ok']
```

## 四、脚本编写规范

| 禁止 | 原因 | 正确做法 |
|------|------|---------|
| `input()` 阻塞调用 | 自动化脚本永久挂起 | `with PlaywrightCLI() as cli:` 自动管理生命周期 |
| `time.sleep()` 盲目等待 | 不稳定 | `cli.wait_for_stable()` 智能等待 |
| `import` 在函数内部 | 不规范 | 模块顶部导入 |
| 混用中英文 | 不一致 | 全文件统一语言 |
| `cli.close()` 写在 `finally` 后 | 可能遗漏 | 用 `with` 语句自动析构 |

## 五、SPA 特殊处理

### 5.1 认证流程（一行搞定）

```python
# authenticated_navigate 自动处理：dev-login → 首页 → SPA 内部导航
cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-table')
```

### 5.2 禁止 networkidle

```python
# [X] 禁止 - SPA 中永远不会完成
page.wait_for_load_state('networkidle')

# [OK] 正确 - domcontentloaded + 元素等待
cli.wait_for_selector('.el-table', timeout=15000)
```

### 5.3 智能等待

```python
# [X] 禁止 - 等固定时间（不可靠 + 慢）
cli.wait_for_timeout(3000)

# [OK] 正确 - 等实际状态稳定
cli.wait_for_stable(max_wait=10000, stable_window=500)
```

## 六、常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 浏览器启动失败 | Playwright 未安装 | `playwright install chromium` |
| 截图是空白页 | SPA 异步渲染未完成 | 添加 `wait_for_selector` |
| API 认证 401 | 自己拼 Bearer token 格式不对 | 项目用 httpOnly cookie 认证，Playwright 场景用 `authenticated_page()`，纯 requests 用 cookie |
| API 认证 401 | 不知道用什么认证方式 | 先 `curl.exe -c cookies.txt http://localhost:3010/api/v1/auth/dev-login?username=admin` 看返回的 Set-Cookie |

## 七、API 调试规范

> **项目后端使用 httpOnly cookie 认证，不是 Bearer token。不要自己拼 Authorization header。**

```python
# [X] 错误：自己猜 Bearer token 结构
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
token = r.json()['data']['user']['user_id']  # dev-login 不返回这个！
r = s.get(url, headers={'Authorization': f'Bearer {token}'})

# [OK] 方式1：直接用 cookie（dev-login 设置的 httpOnly cookie）
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
# requests 自动携带 cookie
r = s.get('http://localhost:3010/api/v2/bo/user_group?_view=list')

# [OK] 方式2：检查返回结构
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
print(r.cookies.get_dict())  # 看看设置了哪些 cookie
print(r.json())              # 看看返回体结构
```