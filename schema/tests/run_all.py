"""
schema/tests/run_all.py - M13 v1.1.0 测试运行器
"""
import os
import sys
import unittest

# 添加项目根目录
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, _PROJECT_ROOT)


def load_all_tests():
    """加载所有 M13 测试"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # D1.1 OpenAPI 导出器
    from schema.tests.test_openapi import TestOpenAPIExporter
    suite.addTests(loader.loadTestsFromTestCase(TestOpenAPIExporter))

    # D1.2 JSON Schema 导出器
    from schema.tests.test_json_schema import TestJSONSchemaExporter
    suite.addTests(loader.loadTestsFromTestCase(TestJSONSchemaExporter))

    # D1.3 TypeScript 导出器
    from schema.tests.test_typescript import TestTypeScriptExporter
    suite.addTests(loader.loadTestsFromTestCase(TestTypeScriptExporter))

    # D2 字段变更审计
    from schema.tests.test_audit import TestScore, TestDiff, TestCompatibilityScenarios
    suite.addTests(loader.loadTestsFromTestCase(TestScore))
    suite.addTests(loader.loadTestsFromTestCase(TestDiff))
    suite.addTests(loader.loadTestsFromTestCase(TestCompatibilityScenarios))

    # D3 CI 校验
    from schema.tests.test_ci import TestExtractEntitySchemas, TestRunCICheck
    suite.addTests(loader.loadTestsFromTestCase(TestExtractEntitySchemas))
    suite.addTests(loader.loadTestsFromTestCase(TestRunCICheck))

    # D4 Dashboard API
    from schema.tests.test_dashboard import TestSchemaDashboardAPI, TestSchemaAPIExport
    suite.addTests(loader.loadTestsFromTestCase(TestSchemaDashboardAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestSchemaAPIExport))

    # D5 meta_object 同步
    from schema.tests.test_meta_object_sync import TestMetaObjectSync
    suite.addTests(loader.loadTestsFromTestCase(TestMetaObjectSync))

    return suite


if __name__ == '__main__':
    suite = load_all_tests()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
