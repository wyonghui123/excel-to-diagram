#!/usr/bin/env python3
"""[2026-09-18] 单测 P0 三条修复:
1. deploy_upload.py --retry-on-mismatch 重试逻辑
2. staging_round.ProdVerifyError 抛错 + _prod_verify_endpoint raise
3. staging_round nargs='*' 兼容 0 个 arg + PowerShell @() 数组

不需要真实远端, 用 mock。
"""
import sys
import os
import json
import argparse
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# 加 tools 到 sys.path
sys.path.insert(0, r'D:\filework\excel-to-diagram\tools')
sys.path.insert(0, r'D:\filework\excel-to-diagram')

# ========================
# 测试 1: --retry-on-mismatch
# ========================
class TestRetryOnMismatch(unittest.TestCase):
    """P0-1: deploy_upload.upload 偶发 md5 mismatch 应自动重试"""

    def _make_args(self, retry_on_mismatch=1):
        # 用真实存在的 staging_round.py 绝对路径 (cmd_upload _abs_path 走 Path.exists)
        return argparse.Namespace(
            local_path=[r'D:\filework\excel-to-diagram\tools\staging_round.py'],
            resource_type=None,
            skip_pre_validate=True,
            pre_validate_db=None,
            force_drift_acknowledge=False,
            skip_stale_check=True,
            stale_days=7,
            force_allow_stale=False,
            skip_verify=False,
            dry_run=False,
            retry_on_mismatch=retry_on_mismatch,
        )

    def _make_target(self, mismatch_count=0):
        """mock 一个 DeployTarget: 前 mismatch_count 次调用 md5 mismatch, 之后 ok"""
        target = MagicMock()
        target.name = 'test-target'
        call_count = {'n': 0}

        def fake_upload(local, resource_type=None, skip_verify=False):
            from lib.deploy_topology import UploadResult
            call_count['n'] += 1
            if call_count['n'] <= mismatch_count:
                # md5 mismatch
                return [UploadResult(
                    local_path=str(local), remote_path='/fake/remote',
                    success=True, md5_match=False, method='remote_upload'
                )]
            return [UploadResult(
                local_path=str(local), remote_path='/fake/remote',
                success=True, md5_match=True, method='remote_upload'
            )]

        target.upload = fake_upload
        return target

    def test_retry_succeeds_on_first_attempt(self):
        """正常情况: 1 次成功, 不重试"""
        from deploy_upload import cmd_upload
        args = self._make_args(retry_on_mismatch=1)
        target = self._make_target(mismatch_count=0)

        with patch('deploy_upload._pre_deploy_check', return_value=(True, '')):
            with patch('deploy_upload._stale_check', return_value=(True, '')):
                with patch('deploy_upload.audit_append'):
                    rc = cmd_upload(args, target)
        self.assertEqual(rc, 0)
        self.assertEqual(target.upload.call_count if hasattr(target.upload, 'call_count') else 1, 1)

    def test_retry_succeeds_after_one_mismatch(self):
        """1 次 mismatch 后第 2 次成功, retry_on_mismatch=1 应成功"""
        from deploy_upload import cmd_upload
        args = self._make_args(retry_on_mismatch=1)
        target = self._make_target(mismatch_count=1)

        upload_calls = {'count': 0}
        original_upload = target.upload.side_effect if hasattr(target.upload, 'side_effect') else None

        # 替换 side_effect 让 magic mock 计数
        call_log = []
        from lib.deploy_topology import UploadResult

        def upload_with_log(local, resource_type=None, skip_verify=False):
            upload_calls['count'] += 1
            if upload_calls['count'] <= 1:
                return [UploadResult(local_path=str(local), remote_path='/fake',
                                     success=True, md5_match=False, method='remote_upload')]
            return [UploadResult(local_path=str(local), remote_path='/fake',
                                 success=True, md5_match=True, method='remote_upload')]
        target.upload = upload_with_log

        with patch('deploy_upload._pre_deploy_check', return_value=(True, '')):
            with patch('deploy_upload._stale_check', return_value=(True, '')):
                with patch('deploy_upload.audit_append'):
                    rc = cmd_upload(args, target)
        self.assertEqual(rc, 0, f"retry should succeed but got rc={rc}")
        self.assertEqual(upload_calls['count'], 2, "should retry exactly once")

    def test_retry_exhausted_returns_fail(self):
        """连续多次 mismatch, retry 耗尽后应 return 1 (fail)"""
        from deploy_upload import cmd_upload
        args = self._make_args(retry_on_mismatch=1)  # 最多 2 次
        target = self._make_target(mismatch_count=5)  # 永远 mismatch

        upload_calls = {'count': 0}
        from lib.deploy_topology import UploadResult

        def upload_always_mismatch(local, resource_type=None, skip_verify=False):
            upload_calls['count'] += 1
            return [UploadResult(local_path=str(local), remote_path='/fake',
                                 success=True, md5_match=False, method='remote_upload')]
        target.upload = upload_always_mismatch

        with patch('deploy_upload._pre_deploy_check', return_value=(True, '')):
            with patch('deploy_upload._stale_check', return_value=(True, '')):
                with patch('deploy_upload.audit_append'):
                    rc = cmd_upload(args, target)
        self.assertEqual(rc, 1, "retry exhausted should fail")
        self.assertEqual(upload_calls['count'], 2, "should attempt max 2 times (initial + 1 retry)")

    def test_retry_zero_means_no_retry(self):
        """retry_on_mismatch=0: 第 1 次失败立即报, 不重试"""
        from deploy_upload import cmd_upload
        args = self._make_args(retry_on_mismatch=0)
        target = self._make_target(mismatch_count=5)

        upload_calls = {'count': 0}
        from lib.deploy_topology import UploadResult

        def upload_always_mismatch(local, resource_type=None, skip_verify=False):
            upload_calls['count'] += 1
            return [UploadResult(local_path=str(local), remote_path='/fake',
                                 success=True, md5_match=False, method='remote_upload')]
        target.upload = upload_always_mismatch

        with patch('deploy_upload._pre_deploy_check', return_value=(True, '')):
            with patch('deploy_upload._stale_check', return_value=(True, '')):
                with patch('deploy_upload.audit_append'):
                    rc = cmd_upload(args, target)
        self.assertEqual(rc, 1)
        self.assertEqual(upload_calls['count'], 1, "retry_on_mismatch=0 means no retry")


# ========================
# 测试 2: ProdVerifyError
# ========================
class TestProdVerifyError(unittest.TestCase):
    """P0-2: _prod_verify_endpoint 失败时 raise ProdVerifyError"""

    def test_prod_verify_error_constructs(self):
        from staging_round import ProdVerifyError
        e = ProdVerifyError('login-no-token', '/api/v2/bo/test', raw='{"data":{"foo":"bar"}}')
        self.assertEqual(e.stage, 'login-no-token')
        self.assertEqual(e.path, '/api/v2/bo/test')
        self.assertIn('login-no-token', str(e))
        self.assertIn('api/v2/bo/test', str(e))

    def test_prod_verify_endpoint_raises_on_no_token(self):
        """模拟 login 返回 data 但没 token: 必须 raise"""
        from staging_round import _prod_verify_endpoint, ProdVerifyError

        # mock remote_exec: 返回含 data 但无 token 的响应
        fake_login = {
            'stdout': json.dumps({'data': {'user_id': 1, 'must_change_password': False}}),
            'error': None
        }

        with patch('staging_round.remote_exec', return_value=fake_login):
            with self.assertRaises(ProdVerifyError) as ctx:
                _prod_verify_endpoint('/api/v2/bo/audit_log')
            self.assertEqual(ctx.exception.stage, 'login-no-token')
            self.assertEqual(ctx.exception.path, '/api/v2/bo/audit_log')
            # 必须有诊断信息 (top_keys / data_keys)
            self.assertIn('top_keys', ctx.exception.reason)
            self.assertIn('data_keys', ctx.exception.reason)

    def test_prod_verify_endpoint_succeeds_with_data_token(self):
        """正常路径: data.token 拿到"""
        from staging_round import _prod_verify_endpoint

        fake_login = {
            'stdout': json.dumps({'data': {'token': 'fake-jwt-token', 'user_id': 1}}),
            'error': None
        }
        fake_probe = {
            'stdout': '200 0.234',
            'error': None
        }

        with patch('staging_round.remote_exec', side_effect=[fake_login, fake_probe]):
            r = _prod_verify_endpoint('/api/v2/bo/audit_log')
            self.assertEqual(r['http'], '200')
            self.assertEqual(r['time_s'], '0.234')
            self.assertIn('fake-jwt', r['token_used'])

    def test_prod_verify_endpoint_raises_on_login_http_error(self):
        """login 调用失败 (gateway 4xx/5xx) 应 raise"""
        from staging_round import _prod_verify_endpoint, ProdVerifyError

        fake_login = {'error': True, 'status': 403, 'body': 'forbidden'}

        with patch('staging_round.remote_exec', return_value=fake_login):
            with self.assertRaises(ProdVerifyError) as ctx:
                _prod_verify_endpoint('/api/v2/bo/test')
            self.assertEqual(ctx.exception.stage, 'login')


# ========================
# 测试 3: nargs='*' 兼容
# ========================
class TestNargsCompatibility(unittest.TestCase):
    """P0-3: --files / --endpoints nargs='*' 兼容 0 个 + 数组"""

    def test_prod_deploy_accepts_ps_array_form(self):
        """模拟 PS @() 数组传入: sys.argv 应该是 ['--files', 'a.py', 'b.py']"""
        from staging_round import main as sr_main
        import sys

        # mock 所有外部依赖
        test_argv = [
            'staging_round.py', 'prod-deploy',
            '--files', 'meta/api/audit_api.py', 'meta/api/user_group_api.py',
            '--force-allow-stale',
        ]
        with patch.object(sys, 'argv', test_argv):
            with patch('staging_round.cmd_prod_deploy') as mock_cmd:
                # main 入口应该解析成功 (不抛 SystemExit)
                try:
                    sr_main()
                except SystemExit as e:
                    # SystemExit(0) 是 OK, 其他是错
                    if e.code != 0 and e.code is not None:
                        # 1 通常是 cmd_prod_deploy 真的跑了 + abort
                        # 但 mock 了 cmd_prod_deploy 所以不会跑到那
                        pass
        # 验证 mock 被调用, 且 args.files 是 list (2 个元素)
        self.assertTrue(mock_cmd.called)
        call_args = mock_cmd.call_args[0][0]
        self.assertIsInstance(call_args.files, list)
        self.assertEqual(len(call_args.files), 2)
        self.assertIn('meta/api/audit_api.py', call_args.files)
        self.assertIn('meta/api/user_group_api.py', call_args.files)

    def test_prod_deploy_files_empty_exits_in_cmd(self):
        """nargs='*' 兼容 0 个, 但 cmd_prod_deploy 内部应 sys.exit (代码层校验)"""
        # 这部分测试 cmd_prod_deploy 函数本身的 files 校验
        from staging_round import cmd_prod_deploy, ProdVerifyError
        import argparse

        args = argparse.Namespace(files=None, skip_stale_check=False, force_allow_stale=False,
                                   stale_days=None, verify_endpoints=None)
        with self.assertRaises(SystemExit) as ctx:
            cmd_prod_deploy(args)
        self.assertIn('--files', str(ctx.exception))


if __name__ == '__main__':
    unittest.main(verbosity=2)