"""
run_all.py - 跑所有 M11 测试（D1+D2+D3）
不通过 pytest（避免 conftest.py 干扰）
"""
import sys
import os
from pathlib import Path

# 路径：rls/tests/run_all.py -> d:\filework\excel-to-diagram
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import unittest

# 加载所有测试
loader = unittest.TestLoader()
suite = unittest.TestSuite()

# D1
from rls.tests.test_loader import TestRLSLoader
suite.addTests(loader.loadTestsFromTestCase(TestRLSLoader))

# D2
from rls.tests.test_enforce import (
    TestCheckAction, TestGetActiveRowFilter,
    TestApplyFieldMasks, TestApplyFieldMasksToList,
)
suite.addTests(loader.loadTestsFromTestCase(TestCheckAction))
suite.addTests(loader.loadTestsFromTestCase(TestGetActiveRowFilter))
suite.addTests(loader.loadTestsFromTestCase(TestApplyFieldMasks))
suite.addTests(loader.loadTestsFromTestCase(TestApplyFieldMasksToList))

# D3
from rls.tests.test_examples import (
    TestPermissionIntegration, TestDataPermissionIntegration,
    TestFieldPolicyIntegration, TestExistingInterceptorsNotModified,
)
suite.addTests(loader.loadTestsFromTestCase(TestPermissionIntegration))
suite.addTests(loader.loadTestsFromTestCase(TestDataPermissionIntegration))
suite.addTests(loader.loadTestsFromTestCase(TestFieldPolicyIntegration))
suite.addTests(loader.loadTestsFromTestCase(TestExistingInterceptorsNotModified))

# TODO-1: AI Agent 角色注入测试
from rls.tests.test_ai_agent_role import (
    TestInjectAIAgentRole, TestAIAgentRoleWithRLS,
    TestAIAgentPermissionInterceptorBeforeAction,
)
suite.addTests(loader.loadTestsFromTestCase(TestInjectAIAgentRole))
suite.addTests(loader.loadTestsFromTestCase(TestAIAgentRoleWithRLS))
suite.addTests(loader.loadTestsFromTestCase(TestAIAgentPermissionInterceptorBeforeAction))

# TODO-2: 3 拦截器真实集成测试
from rls.tests.test_integration_real import (
    TestCheckYAMLPermission, TestCheckYAMLRowFilter, TestApplyYAMLFieldMasks,
    TestPermissionInterceptorAfterAction, TestDataPermissionInterceptorYAML,
    TestEndToEndScenarios,
)
suite.addTests(loader.loadTestsFromTestCase(TestCheckYAMLPermission))
suite.addTests(loader.loadTestsFromTestCase(TestCheckYAMLRowFilter))
suite.addTests(loader.loadTestsFromTestCase(TestApplyYAMLFieldMasks))
suite.addTests(loader.loadTestsFromTestCase(TestPermissionInterceptorAfterAction))
suite.addTests(loader.loadTestsFromTestCase(TestDataPermissionInterceptorYAML))
suite.addTests(loader.loadTestsFromTestCase(TestEndToEndScenarios))

# TODO-3 + TODO-4: 热加载 + 5×5 场景矩阵
from rls.tests.test_hot_reload import (
    TestHotReloadWatcher, TestCheckAndReload, TestStartHotReload,
    TestFiveByFiveScenarios,
)
suite.addTests(loader.loadTestsFromTestCase(TestHotReloadWatcher))
suite.addTests(loader.loadTestsFromTestCase(TestCheckAndReload))
suite.addTests(loader.loadTestsFromTestCase(TestStartHotReload))
suite.addTests(loader.loadTestsFromTestCase(TestFiveByFiveScenarios))

# TODO-5: DSL 解析器
from rls.tests.test_dsl import (
    TestParseCondition, TestIsFieldReference,
    TestGetRowFilterParsed, TestDSLEndToEnd,
)
suite.addTests(loader.loadTestsFromTestCase(TestParseCondition))
suite.addTests(loader.loadTestsFromTestCase(TestIsFieldReference))
suite.addTests(loader.loadTestsFromTestCase(TestGetRowFilterParsed))
suite.addTests(loader.loadTestsFromTestCase(TestDSLEndToEnd))

# TODO-6: 10 entity YAML 验证
from rls.tests.test_yaml_files import (
    TestYAMLFilesLoad, TestYAMLFilesFiveRoles,
)
suite.addTests(loader.loadTestsFromTestCase(TestYAMLFilesLoad))
suite.addTests(loader.loadTestsFromTestCase(TestYAMLFilesFiveRoles))

# 跑
runner = unittest.TextTestRunner(verbosity=2)
result = runner.run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
