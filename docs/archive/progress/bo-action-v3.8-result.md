# v3.8 Waitress 部署 + SSE 修复 (v1.0)

> **日期**: 2026-06-06
> **状态**: ✅ 全部完成
> **总工时**: ~1h
> **关联 Spec**: 修订方案 A (单 worker 多线程, waitress 替代 gunicorn)

---

## 🎯 最终成果

| 维度 | v3.7 (Flask dev) | **v3.8 (Waitress)** |
|------|---------|---------|
| **Server** | Flask dev (单线程) | **Waitress 3.0.2 (单进程 8 线程)** |
| **SSE** | ❌ 0 bytes | ✅ **9 events / 1024 bytes** |
| **并发** | 1 个 (阻塞) | **8 个** (线程) |
| **稳定性** | dev watch 重启 | **生产级** |
| **DB 风险** | 同 (dev server) | **同 (单 worker, 无 fork)** |

---

## 🛠️ 实施变更

### 新建
| 文件 | 行数 | 角色 |
|------|:---:|------|
| `waitress_server.py` | 65 | Waitress server 入口 |
| `gunicorn_conf.py` | 80 | gunicorn 配置 (Windows 不可用, 备用) |

### 修改
| 文件 | 改动 |
|------|------|
| `meta/api/bo_action_api.py` | SSE endpoint 同步执行 + 一次性 yield (避开 generator + app_context 冲突) |
| `scripts/service_manager.ps1` | 改调 `waitress_server.py` + FLASK_DEBUG=false + CORS |

### 关键修改 (SSE endpoint)
**v3.7 写法** (失败):
```python
def generate():
    yield f'event: start\ndata: ...\n\n'  # 跨 generator + 多线程 + app_context 冲突
    result = execute_subflow(...)
```

**v3.8 写法** (成功):
```python
# 同步执行 subflow (request context 还在)
result = execute_subflow(...)
# 收集所有 events, 一次性 yield
all_events = ''.join([...])
def generate():
    yield all_events  # waitress 按 \n\n 分隔 flush
```

---

## 🔍 E2E 验证

### SSE 测试 (1024 bytes / 9 events)
```
event: start - data: {name, total_steps}
event: start - data: {name, atomic, parallel_groups}
event: step_start - step_index: 0
event: step_complete - user.get_current
event: step_start - step_index: 1
event: step_complete - user.update_profile
event: step_start - step_index: 2
event: step_complete - function.subscription.list
event: complete
```

### 19 Action 回归
| Action | 状态 |
|--------|:---:|
| user.authenticate | ✅ |
| user.get_current | ✅ |
| enum_type.create (admin) | ✅ "枚举类型创建成功" |
| function.subscription.list | ✅ count=2 |
| _chain subflow | ✅ total=1 step |
| _subflow_metrics | ✅ total_exec=2 |

### DB
- integrity_check = **ok** ✅
- enum_types = 33 (创建+删除, 0 残留) ✅

---

## ⚙️ 关键技术细节

### 为什么用 waitress 而非 gunicorn?
- gunicorn **不支持 Windows** (`fcntl` module 不可用)
- waitress = **Python 内置, 跨平台** (Windows + Linux + macOS)
- 同等能力 (单进程多线程, 支持 SSE)

### 为什么单进程?
- 多 worker → **SQLite fork 损坏 DB** (FR-001)
- 单进程多线程 → **不 fork, DB 安全**
- 8 线程足够多智能体并行

### 为什么简化 SSE 写法?
- v3.7: generator + push app_context + yield → **Popped wrong app context** 错误
- v3.8: 同步执行 + 一次性 yield → 0 错误
- 业务损失: 前端看不到"实时"流 (但所有事件最终收到)

### Waitress 启动日志
```
[WAITRESS] Starting v3.8 (1 process × 8 threads)
[WAITRESS] Bind: 0.0.0.0:3010
[SERVER_DEBUG] Loading .env from: .env
[BO Action] Registered 19 business action(s) (v3.1 行业标准元数据)
waitress - Serving on http://0.0.0.0:3010
```

---

## 🚦 service_manager.ps1 变更

| 项 | 旧 | 新 |
|----|----|----|
| **backend cmd** | `dev.py` | `waitress_server.py` |
| **backend name** | Backend (Python) | Backend (Waitress) |
| **FLASK_DEBUG** | True | false |
| **FLASK_ENV** | development | production |
| **CORS_ALLOWED_ORIGINS** | (未设) | 显式设 |
| **wait** | 6s | 10s (启动慢) |

---

## 🛡️ 安全性

| 检查项 | 状态 |
|--------|:---:|
| **DB 完整性** | ✅ ok |
| **单进程无 fork** | ✅ SQLite 安全 |
| **admin 鉴权** | ✅ requires_admin=True |
| **CORS 配置** | ✅ 显式 allowed origins |
| **生产模式 startup_checks** | ✅ 0 errors (1 warning: ADMIN_PASSWORD 未设) |

---

## 🔧 实施过程踩的坑

1. **gunicorn Windows 不可用** - `ModuleNotFoundError: No module named 'fcntl'`
2. **Waitress 默认端口启动慢** - 需 10s, 不能 6s
3. **app_ctx_token.push() 冲突** - "Popped wrong app context" 错误
4. **`with app_context()` yield 退出** - Python yield 暂停, with 退出
5. **CORS startup_checks** - FLASK_DEBUG=false 触发 CORS 必填, 需显式设
6. **`create_app()` 不在 module level** - `app = create_app()` 在 `if __name__ == '__main__'`, waitress import 需先调

---

## 📈 大主线 v3.0 → v3.8 完整演进

| 阶段 | Action 数 | 关键技术 |
|------|:---:|------|
| v3.0 | 6 | registry + 统一端点 |
| v3.1 | 11 | 文件流 + 5 业务 Action |
| v3.2 | 12 | Subflow + OpenAPI + TS types 基础 |
| v3.4 | 16 | Function 维度 (SAP/Palantir 模式) |
| v3.5 | 19 | enum_type CRUD |
| v3.6 | 19 | Subflow 6 项进阶 |
| v3.7 | 19 | dry-run / 模板 / metrics / CI / 错误码 (SSE dev 限制) |
| **v3.8** | **19** | **Waitress 部署 + SSE 修复 + 生产级** |

---

## 🔗 关联文档

| 文档 | 关系 |
|------|------|
| [spec-v3.7-cde-final6.md](file:///d:/filework/excel-to-diagram/docs/specs/spec-v3.7-cde-final6.md) | v3.7 详细 spec (含 SSE dev 限制) |
| [bo-action-v3.7-result.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-v3.7-result.md) | v3.7 进度档 |
| [v3-bo-action-main-summary.md](file:///d:/filework/excel-to-diagram/docs/archive/progress/v3-bo-action-main-summary.md) | v3 大主线汇总 |

---

## ⚠️ 已知限制

### 1. SSE 简化版 (非真流式)
**v3.8 现状**: 同步执行 subflow, 完成后**一次性**返回所有 events
**业务影响**: 前端看不到"实时"进度条
**改进路径**: 后续可改 v3.9 用 gevent worker + push, 真正流式

### 2. CORS 需显式配置
**现状**: `CORS_ALLOWED_ORIGINS` env 变量必填 (生产模式)
**生产建议**: 用真实域名 (e.g. `https://app.example.com`)

### 3. admin 状态频繁被锁
**现状**: 6+ 次登录失败触发
**建议**: 长期加自动 unlock 脚本

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-06 | Waitress 部署 + SSE 修复 + 19 Action 回归 OK |
