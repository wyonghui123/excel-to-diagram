# Post-V2.1 测试套件 - 6月22日之后修改的测试覆盖

> 创建日期: 2026-06-26
> 依据: [.trae/specs/test-suite/post-6-22-roadmap.md](../../../.trae/specs/test-suite/post-6-22-roadmap.md)

## 目录结构

```
post_v2_1/
├── conftest.py                                # 共享 fixtures
├── README.md                                  # 本文件
├── import_export/                             # Agent A (7 文件)
├── permission/                                # Agent B (11 文件)
├── audit_help/                                # Agent C (7 文件)
├── cascade/                                   # 架构 Agent (3 文件)
│   ├── test_cascade_bug_v013.py              # BUG-V013 单元测试
│   ├── test_cascade_bug_v014.py              # BUG-V014 单元测试
│   └── test_cascade_e2e.py                   # 浏览器 E2E
├── frontend/                                  # 架构 Agent (2 文件)
│   ├── _helpers.py
│   ├── test_frontend_bug_v015_detail.py      # BUG-V015 详情
│   └── test_frontend_bug_v015_list.py        # BUG-V015 列表
└── integration/                               # 架构 Agent (5 文件)
    ├── test_e2e_v2_1_integration_force.py    # force_override × cascade × write_scope
    ├── test_e2e_v2_1_integration_rbac.py     # RBAC graceful degradation
    ├── test_e2e_v2_1_integration_audit.py    # cascade + audit
    ├── test_e2e_v2_1_browser_bug_v015.py     # BUG-V015 浏览器 E2E
    └── test_e2e_v2_1_integration_async.py    # thread-local + async
```

## 运行

```bash
# 单文件
python d:\filework\test.py --file meta/tests/post_v2_1/cascade/test_cascade_bug_v013.py

# 按主题
pytest -m "post_v2_1 and cascade" meta/tests/post_v2_1/
pytest -m "post_v2_1 and frontend" meta/tests/post_v2_1/
pytest -m "post_v2_1 and integration" meta/tests/post_v2_1/
```

## 阶段 3 成果 (架构 Agent)

| 文件 | 用例数 | 状态 |
|------|--------|------|
| cascade/test_cascade_bug_v013.py | 6 | ✅ |
| cascade/test_cascade_bug_v014.py | 8 | ✅ |
| cascade/test_cascade_e2e.py | 3 | ✅ |
| frontend/test_frontend_bug_v015_detail.py | 8 | ✅ |
| frontend/test_frontend_bug_v015_list.py | 6 | ✅ |
| integration/test_e2e_v2_1_integration_force.py | 5 | ✅ |
| integration/test_e2e_v2_1_integration_rbac.py | 4 | ✅ |
| integration/test_e2e_v2_1_integration_audit.py | 5 | ✅ |
| integration/test_e2e_v2_1_browser_bug_v015.py | 3 | ✅ |
| integration/test_e2e_v2_1_integration_async.py | 6 | ✅ |
| **小计** | **~52 用例** | **全部 ✅** |
