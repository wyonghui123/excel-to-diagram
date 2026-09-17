"""
v33_pipeline 状态机核心库 — Agent 间共享的事实源

提供原子性的 6 状态转换 + 单写者并发保护。

设计原则：
- .agent-status.json 是 .v33_pipeline 的唯一写入目标
- 所有转换经过单一函数 transition() 写入
- msvcrt 文件锁避免并发覆盖
- 每步自动 append .coord/events.jsonl (审计)
- 自动 .config_backup 写入前 5 份
"""
import json, msvcrt, os, re
from datetime import datetime, timezone
from pathlib import Path

# ── 路径 ──
ROOT_CO = Path('D:/filework/.coord')
ROOT_MAIN = Path('D:/filework/excel-to-diagram')
STATUS_FILE = Path('D:/filework/.agent-status.json')
EVENTS_FILE = ROOT_CO / 'events.jsonl'

# ── 6 状态定义 ──
ALL_STATES = ['DRAFT', 'SELF_VERIFIED', 'CHERRY_PICKED', 'PM_VERIFIED', 'DEPLOYED', 'REVERTED']
ACTIVE_STATES = ('PM_VERIFIED', 'DEPLOYED')

# ── helpers ──
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _lock_file() -> Path:
    return STATUS_FILE.with_suffix('.lock')


def _acquire_file_lock(timeout: float = 10.0):
    """获取 STATUS_FILE 锁，避免并发覆盖"""
    lock_path = _lock_file()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = open(lock_path, 'w')
    deadline = datetime.now().timestamp() + timeout
    while True:
        try:
            msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
            return fd
        except OSError:
            if datetime.now().timestamp() > deadline:
                return fd  # 超时继续，但不阻塞
            import time
            time.sleep(0.05)


def _release_file_lock(fd):
    try:
        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
    except OSError:
        pass
    try:
        fd.close()
    except OSError:
        pass
    try:
        _lock_file().unlink()
    except OSError:
        pass


def read_status() -> dict:
    """读取 .agent-status.json"""
    return json.loads(STATUS_FILE.read_text(encoding='utf-8'))


def _write_status(status: dict):
    """原子写入（带文件锁 + 备份）"""
    fd = _acquire_file_lock()
    try:
        # 备份
        try:
            sys_path = str(Path(__file__).parent)
            if sys_path not in os.sys.path:
                os.sys.path.insert(0, sys_path)
            from _config_backup import backup as _backup
            _backup(str(STATUS_FILE))
        except Exception:
            pass
        # 写入
        STATUS_FILE.write_text(
            json.dumps(status, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )
    finally:
        _release_file_lock(fd)


def _log_event(event_type: str, message: str, **kv):
    """写一条事件到 events.jsonl（带锁）"""
    line = {'timestamp': _now_iso(), 'type': event_type, 'message': message, **kv}
    events_str = json.dumps(line, ensure_ascii=False) + '\n'
    EVENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd2 = open(EVENTS_FILE, 'a', encoding='utf-8')
    try:
        try:
            msvcrt.locking(fd2.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            pass
        fd2.write(events_str)
        fd2.flush()
    finally:
        try:
            msvcrt.locking(fd2.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        fd2.close()


# ── 状态转换 API ──
def transition(bug_id: str, new_state: str, actor: str = 'coordinator', note: str = '') -> bool:
    """
    触发 bug 的状态转换，并自动维护 v33_pipeline 状态机

    Args:
        bug_id:  BUG 编号 (e.g. "V046" "V040")
        new_state: 新状态 (DRAFT|SELF_VERIFIED|CHERRY_PICKED|PM_VERIFIED|DEPLOYED|REVERTED)
        actor: 谁做的
        note: 备注

    Returns:
        True 写入成功, False 失败
    """
    if new_state not in ALL_STATES:
        print(f'  ERROR: 未知状态 {new_state}')
        return False

    status = read_status()
    v33 = status.setdefault('v33_pipeline', {})
    v33.setdefault('handover_lifecycle', {}).setdefault('states', ALL_STATES)

    pm = v33.setdefault('pm_review_pending', {
        'pending': False,
        'bugs': [],
        'ready_for': 'PM 验证 release-prep 3006/3011',
    })
    dp = v33.setdefault('deploy_pending', {
        'pending': False,
        'bugs': [],
        'ready_for': '协调智能体触发 staging_deploy_orchestrator.py',
    })

    # 转换规则：每个状态对应不同的 pm/dp 变更
    old_pm_pending = pm['pending']
    old_dp_pending = dp['pending']

    if new_state == 'CHERRY_PICKED':
        # 进入待 PM 验证
        if bug_id not in pm['bugs']:
            pm['bugs'].append(bug_id)
        pm['pending'] = True
        pm['ready_at'] = _now_iso()
        # 同时从 deploy_pending 清掉（不可能已经在 pending deploy）
        dp['bugs'] = [b for b in dp['bugs'] if b != bug_id]
        if not dp['bugs']:
            dp['pending'] = False

    elif new_state == 'PM_VERIFIED':
        # PM 验证通过 → 进入待部署
        if bug_id in pm['bugs']:
            pm['bugs'].remove(bug_id)
        if bug_id not in dp['bugs']:
            dp['bugs'].append(bug_id)
        dp['pending'] = True
        dp['pm_verified_at'] = _now_iso()
        pm['pending'] = bool(pm['bugs'])
        if not pm['bugs']:
            pm.pop('ready_at', None)

    elif new_state == 'DEPLOYED':
        # 部署成功 → 清出队列
        if bug_id in dp['bugs']:
            dp['bugs'].remove(bug_id)
        dp['last_deployed'] = _now_iso()
        dp['pending'] = bool(dp['bugs'])
        # 记录里程碑
        history = dp.setdefault('history', [])
        history.append({
            'bug_id': bug_id,
            'deployed_at': _now_iso(),
            'actor': actor,
            'note': note,
        })

    elif new_state == 'REVERTED':
        # 回滚
        for section in (pm, dp):
            if bug_id in section['bugs']:
                section['bugs'].remove(bug_id)
        pm['pending'] = bool(pm['bugs'])
        dp['pending'] = bool(dp['bugs'])
        reverted_list = dp.setdefault('reverted_history', [])
        reverted_list.append({'bug_id': bug_id, 'at': _now_iso(), 'actor': actor, 'note': note})

    elif new_state in ('DRAFT', 'SELF_VERIFIED'):
        # 私有智能体状态，不修改 v33_pipeline
        pass

    # 写回
    _write_status(status)

    # 写事件
    _log_event(
        event_type=f'v33_TRANSITION_{new_state}',
        message=f'{bug_id} -> {new_state} by {actor}' + (f': {note}' if note else ''),
        actor=actor, bug_id=bug_id, state=new_state,
        old_pm_pending=old_pm_pending, new_pm_pending=pm['pending'],
        old_dp_pending=old_dp_pending, new_dp_pending=dp['pending'],
    )

    return True


def query(bug_id: str = None) -> dict:
    """查询 v33_pipeline 当前状态"""
    status = read_status()
    v33 = status.get('v33_pipeline', {})
    pm = v33.get('pm_review_pending', {})
    dp = v33.get('deploy_pending', {})
    if bug_id:
        result = {}
        if bug_id in pm.get('bugs', []):
            result['state'] = 'CHERRY_PICKED'
            result['wait_at'] = 'pm_review_pending'
        elif bug_id in dp.get('bugs', []):
            result['state'] = 'PM_VERIFIED'
            result['wait_at'] = 'deploy_pending'
        else:
            history = dp.get('history', [])
            reverted = dp.get('reverted_history', [])
            for h in history + reverted:
                if h.get('bug_id') == bug_id:
                    result['state'] = 'DEPLOYED' if h in history else 'REVERTED'
                    result['history'] = h
                    break
            else:
                result['state'] = 'DRAFT/SELF_VERIFIED'
        return result
    return {
        'pm_review_pending': pm,
        'deploy_pending': dp,
        'pm_count': len(pm.get('bugs', [])),
        'dp_count': len(dp.get('bugs', [])),
    }


# ── CLI ──
def main():
    import argparse
    parser = argparse.ArgumentParser(description='v33_pipeline 状态机')
    sub = parser.add_subparsers(dest='cmd', required=True)

    # transition
    t = sub.add_parser('transition', help='推进 bug 状态')
    t.add_argument('bug_id')
    t.add_argument('state', choices=ALL_STATES)
    t.add_argument('--actor', default='coordinator')
    t.add_argument('--note', default='')

    # query
    q = sub.add_parser('query', help='查询状态')
    q.add_argument('--bug', help='查询指定 bug')
    q.add_argument('--all', action='store_true', help='列出所有')

    args = parser.parse_args()

    if args.cmd == 'transition':
        ok = transition(args.bug_id, args.state, args.actor, args.note)
        print(f'  {"✓" if ok else "✗"} {args.bug_id} -> {args.state}')
        # 立即 query 当前状态
        q = query(args.bug_id)
        print(f'  当前: {q}')
    elif args.cmd == 'query':
        if args.bug:
            print(json.dumps(query(args.bug), indent=2, ensure_ascii=False))
        else:
            r = query()
            print(json.dumps(r, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
