# SPEC: 剩余 8 项基础设施 TODO 实现

## 任务概述
把 TODO_LONGTERM.md 的 8 项 P0/P1 todo 全部实施,
让 yonaa 部署可观测性、健壮性、可恢复性达到生产级别.

涉及: L8.6 (multipart) / L8.8 (隔离检测) / L12 (exec session)
/ L13.3 (dbops_service) / L13.4 (audit coverage) / L14 (deploy_service)
/ L15 (monitor 演进).

## 涉及文件（白名单）
- tools/unzip_safe.py
- tools/audit_coverage_check.py
- tools/dbops_service.py
- tools/deploy_service.py
- tools/tests/test_unzip_safe.py
- tools/tests/test_audit_coverage.py
- tools/tests/test_deploy_service.py
- tools/core_service.py (修改: 加 /api/isolation_check + /api/exec/session 端点)
- tools/post_deploy_check.py (修改: 集成 audit_coverage)
- deploy_bundle/deploy.sh (修改: 集成 unzip_safe)
- monitor_prod.py (修改: 加 4 个新检查)
- docs/superpowers/plans/2026-07-14-remaining-todo-impl.md
- docs/superpowers/specs/2026-07-14-remaining-todo-spec-design.md

## 涉及文件（黑名单，绝对禁止修改）
- d:\filework\excel-to-diagram\**    (主工作树)
- meta/server.py (后端服务不改动, 除非该任务明确要求)
- src/ (前端不改动)
- meta/architecture.db (db 数据)

## 完成标准
- [ ] L8.6 unzip_safe 12/12 tests PASS
- [ ] L8.8 isolation_check 返回 tmp_isolated + systemd_private_tmp
- [ ] L12 exec/session create/run/state/destroy 4 端点工作
- [ ] L13.3 dbops_service 9204 可访问, audit/recover 三端点
- [ ] L13.4 audit_coverage_check 返回 ok/warn/fail 状态
- [ ] L14 deploy_service 9205 状态机 + 二次确认
- [ ] L15 monitor_prod.py 加 4 个新检查 (config/isolation/audit/post_deploy)