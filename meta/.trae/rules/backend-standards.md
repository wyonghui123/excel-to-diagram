---
alwaysApply: false
description: "后端开发规范：Python + Flask + Waitress 技术栈、API 规则、数据库规则"
globs: "meta/**/*.py,meta/**/*.yaml"
---

# 后端开发规范

## 技术栈
- Python 3.11 + Flask + Waitress
- ORM: SQLite (meta/architecture.db)
- 验证: metadata_driven_validator
- API: /api/v1/ 和 /api/v2/ 前缀

## 开发规则
- API 路由在 `meta/api/` 目录
- 业务逻辑在 `meta/core/` 目录
- 数据模型在 `meta/core/models_annotations.py`
- 配置加载: `meta/core/yaml_loader.py`
- 错误码: `meta/core/error_codes.py` + `meta/core/error_fix_hints.py`

## 数据库规则
- 严禁直接读写 `meta/architecture.db`（测试时用 test.py 自动快照）
- DB 操作走 `batch_save` action
- 修改 schema 后必须更新 `models_annotations.py`

## API 规则
- 所有 API 必须加 trace_id (TraceId.get())
- 错误响应必须含 error_code + fix_hint
- 认证用 httpOnly cookie（不是 Bearer token）
- 跨进程测试用 `requests.Session()` + dev-login

## 常见坑
- `AGENT_PORT` 环境变量决定后端端口（默认 3010）
- waitress_server.py 有 AGENT_PORT fallback 逻辑
- DB 锁文件 `.architecture.lock` 可能残留（死进程），需手动删除
