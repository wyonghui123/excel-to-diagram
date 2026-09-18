"""
[2026-09-18 P1] 验证 staging_round.cmd_pack 在 Windows 下生成的 build_cmd 是字符串(非 list+shell=True 触 0xC0000409).

bug: subprocess.run(['npm.cmd', 'run', 'build'], shell=True) 在 Windows cmd.exe 中转时,
Node 11+ 触发 STACK_BUFFER_OVERRUN (rc=0xC0000409), build 实际成功但 exit code 是 overrun.
fix: 改为 subprocess.run('npm.cmd run build', shell=True), 走 cmd.exe 字符串路径, 避免 list 序列化触发 buffer 问题.
"""
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
STAGING_ROUND = REPO / 'tools' / 'staging_round.py'

# [v1.1 兼容] cmd_pack 在 tools/ 下, sys.path 直接 import staging_round
sys.path.insert(0, str(REPO / 'tools'))
import staging_round  # noqa: E402


def _fake_args(note='t', type_='delta', ignore_dirty=True, reuse_dist=False):
    ns = mock.Mock()
    ns.note = note
    ns.type = type_
    ns.ignore_dirty = ignore_dirty
    ns.reuse_dist = reuse_dist
    return ns


def test_win_build_cmd_is_string():
    """Windows: build_cmd 必须是 str, 不是 list+shell=True 组合."""
    if sys.platform != 'win32':
        return  # 跳过非 win32

    captured = {}

    def fake_run(cmd, *a, **kw):
        captured['cmd'] = cmd
        captured['shell'] = kw.get('shell', False)
        r = mock.Mock(); r.returncode = 0
        return r

    with mock.patch.object(staging_round.subprocess, 'run', side_effect=fake_run), \
         mock.patch.object(staging_round, 'git_has_uncommitted', return_value=False), \
         mock.patch.object(staging_round, 'git_head', return_value='abcdef1234567890'), \
         mock.patch.object(staging_round, 'git_head_short', return_value='abcdef1'), \
         mock.patch.object(staging_round, 'git_branch', return_value='main'), \
         mock.patch.object(staging_round, 'next_round_number', return_value=99), \
         mock.patch.object(staging_round, 'write_round', return_value=None), \
         mock.patch.object(staging_round, 'zipfile') as _zf, \
         mock.patch.object(staging_round, '_ef', create=True) as _ef_mod, \
         mock.patch.object(staging_round, 'Path'):
        # 让 env_facts.run_check 不抛
        sys.modules['env_facts'] = mock.Mock(run_check=lambda silent=True: (True, [], None))
        try:
            staging_round.cmd_pack(_fake_args(reuse_dist=False))
        except SystemExit:
            pass
        except Exception:
            pass

    assert 'cmd' in captured, 'subprocess.run 未被调用'
    assert isinstance(captured['cmd'], str), \
        f'Windows build_cmd 应是 str, 实际 {type(captured["cmd"]).__name__}: {captured["cmd"]!r}'
    assert captured['shell'] is True, 'shell=True 是 cmd.exe 字符串中转的必需条件'
    assert 'npm' in captured['cmd']
    assert 'run' in captured['cmd']
    assert 'build' in captured['cmd']


def test_non_win_uses_npm():
    """非 Windows: build_cmd 应是 'npm run build' (POSIX), 不用 npm.cmd."""
    with mock.patch.object(sys, 'platform', 'linux'):
        # 重新跑 cmd_pack 时, cmd_pack 内会读 sys.platform; 我们 patch sys.platform 后用字符串中
        captured = {}

        def fake_run(cmd, *a, **kw):
            captured['cmd'] = cmd
            r = mock.Mock(); r.returncode = 0
            return r

        with mock.patch.object(staging_round.subprocess, 'run', side_effect=fake_run), \
             mock.patch.object(staging_round, 'git_has_uncommitted', return_value=False), \
             mock.patch.object(staging_round, 'git_head', return_value='abcdef1234567890'), \
             mock.patch.object(staging_round, 'git_head_short', return_value='abcdef1'), \
             mock.patch.object(staging_round, 'git_branch', return_value='main'), \
             mock.patch.object(staging_round, 'next_round_number', return_value=99), \
             mock.patch.object(staging_round, 'write_round', return_value=None), \
             mock.patch.object(staging_round, 'zipfile'), \
             mock.patch.object(staging_round, 'Path'):
            sys.modules['env_facts'] = mock.Mock(run_check=lambda silent=True: (True, [], None))
            try:
                staging_round.cmd_pack(_fake_args(reuse_dist=False))
            except SystemExit:
                pass
            except Exception:
                pass

        assert 'cmd' in captured
        assert captured['cmd'] == 'npm run build', \
            f'非 Windows build_cmd 应是 "npm run build", 实际: {captured["cmd"]!r}'
        assert '.cmd' not in captured['cmd']


if __name__ == '__main__':
    test_win_build_cmd_is_string()
    test_non_win_uses_npm()
    print('OK: staging_round.cmd_pack build_cmd 类型正确')
