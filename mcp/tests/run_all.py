"""
mcp/tests/run_all.py - M10 v1.1.0 测试运行器
"""
import os
import sys
import unittest

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, _PROJECT_ROOT)


def load_all_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # T1 protocol
    from mcp.tests.test_protocol import (
        TestJSONRPCRequest, TestJSONRPCResponse, TestHandleRequest,
    )
    suite.addTests(loader.loadTestsFromTestCase(TestJSONRPCRequest))
    suite.addTests(loader.loadTestsFromTestCase(TestJSONRPCResponse))
    suite.addTests(loader.loadTestsFromTestCase(TestHandleRequest))

    # T2 tools
    from mcp.tests.test_tools import (
        TestMCPToolBase, TestGetEntityByIdTool, TestListEntityTool, TestGetAllTools,
    )
    suite.addTests(loader.loadTestsFromTestCase(TestMCPToolBase))
    suite.addTests(loader.loadTestsFromTestCase(TestGetEntityByIdTool))
    suite.addTests(loader.loadTestsFromTestCase(TestListEntityTool))
    suite.addTests(loader.loadTestsFromTestCase(TestGetAllTools))

    # T3 server
    from mcp.tests.test_server import TestMCPServer
    suite.addTests(loader.loadTestsFromTestCase(TestMCPServer))

    # TODO-7: M10 + M11 RLS 集成
    from mcp.tests.test_rls_integration import (
        TestNormalizeUserContext, TestApplyRLSToResult,
    )
    suite.addTests(loader.loadTestsFromTestCase(TestNormalizeUserContext))
    suite.addTests(loader.loadTestsFromTestCase(TestApplyRLSToResult))

    return suite


if __name__ == '__main__':
    suite = load_all_tests()
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
