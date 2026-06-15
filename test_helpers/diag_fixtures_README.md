# test_helpers/diag_fixtures.py —— 诊断 fixture (PLACEHOLDER)

> **Date**: 2026-06-15 | **Status**: 文档占位 (v0.1)
> **Owner**: AI Infra
> **范围**: **仅测试基础设施**。不涉及产品端点设计。

---

## 占位说明

本文档**目前仅是占位**。完整设计**不在本 spec 范围**——实施需要产品端点（`why-blocked` / `admin/record`），那是**产品功能**归产品 owner。

## 当前状态

- ❌ `test_helpers/diag_fixtures.py` **未创建**（设计阶段）
- ❌ 不在本 spec 范围
- ✅ 命名规范已记录（`why_blocked_` / `record_view_` / `as_user_` 前缀）

## 未来 Phase 计划（**不在本 spec 范围**）

如果用户/产品决定实施 `why-blocked` / `admin/record` 端点（产品 spec），后续可：

1. 复用 [test-case-standards.md](../.trae/rules/test-case-standards.md) 的 fixture 规范
2. 在 `test_helpers/` 创建 `diag_fixtures.py` 真实代码
3. 在 `meta/tests/conftest.py` 注册
4. 写示例测试 `test_diag_fixtures_e2e.py`

## 不在本文档范围

- ❌ `meta/api/permissions_api.py` (why-blocked 端点) - **产品功能**
- ❌ `meta/api/admin_api.py` (admin/record 端点) - **产品功能**
- ❌ 拦截器 `on_error` 修改 - **产品功能**
- ❌ 任何 `meta/` 下的代码改动

## CHANGELOG

| 日期 | 变更人 | 内容 |
|------|--------|------|
| 2026-06-15 | Batch2 Agent | 修正：明确占位 + 移除越界的产品端点设计 |
