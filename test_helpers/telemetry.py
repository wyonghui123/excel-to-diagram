"""
Test Telemetry — 浏览器测试遥测系统

三层数据结构:
  Run-level:    run.json — 一次测试运行的汇总摘要
  Operation-level: operations.jsonl — 每步操作的时间线
  Event-level:  events.jsonl — 错误/警告事件流

零侵入设计: 挂载到 PlaywrightCLI 后自动采集所有操作耗时和事件。
"""

import os
import json
import time
import glob
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class OperationRecord:
    seq: int
    timestamp: str
    op: str
    target: str
    duration_ms: float
    result: str
    retries: Optional[int] = None
    waited_ms: Optional[int] = None
    error: Optional[str] = None


@dataclass
class EventRecord:
    seq: int
    timestamp: str
    type: str
    layer: str
    message: str
    level: Optional[str] = None
    component: Optional[str] = None


class TestTelemetry:
    """
    浏览器测试遥测采集器

    自动采集:
      - 每步操作的名称、目标、耗时、结果
      - wait_for_stable 的等待次数和总耗时
      - pageerror / console.error / vue error / crash 事件

    Usage:
        cli = PlaywrightCLI(telemetry_dir='test_telemetry')
        # ... 所有操作自动采集 ...
        cli.close()  # 自动 flush + finalize
    """

    def __init__(self, test_name: str = '', telemetry_dir: str = 'test_telemetry'):
        self.test_name = test_name or 'browser_test'
        self.base_dir = telemetry_dir
        self.run_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.run_dir = os.path.join(self.base_dir, f'{self.test_name}_{self.run_id}')

        self.start_time = time.time()
        self.start_time_str = datetime.now().isoformat()

        self.operations: List[OperationRecord] = []
        self.events: List[EventRecord] = []
        self._op_seq = 0
        self._event_seq = 0

        self.page_visited = ''
        self.username = ''
        self.result = 'running'
        self.exit_code = 0

        self._flushed = False
        self._finalized = False

    def _ensure_dir(self):
        os.makedirs(self.run_dir, exist_ok=True)

    def _timestamp(self) -> str:
        return datetime.now().strftime('%H:%M:%S.%f')[:-3]

    def record_operation(
        self,
        op: str,
        target: str = '',
        duration_ms: float = 0,
        result: str = 'ok',
        retries: int = None,
        waited_ms: int = None,
        error: str = None
    ):
        self._op_seq += 1
        rec = OperationRecord(
            seq=self._op_seq,
            timestamp=self._timestamp(),
            op=op,
            target=target,
            duration_ms=duration_ms,
            result=result,
            retries=retries,
            waited_ms=waited_ms,
            error=error
        )
        self.operations.append(rec)

    def record_event(
        self,
        type: str,
        layer: str,
        message: str,
        level: str = None,
        component: str = None
    ):
        self._event_seq += 1
        evt = EventRecord(
            seq=self._event_seq,
            timestamp=self._timestamp(),
            type=type,
            layer=layer,
            message=message,
            level=level,
            component=component
        )
        self.events.append(evt)

    def flush_to_disk(self):
        """流式写入 operations.jsonl 和 events.jsonl"""
        if self._flushed:
            return
        self._ensure_dir()
        self._flushed = True

        ops_path = os.path.join(self.run_dir, 'operations.jsonl')
        with open(ops_path, 'w', encoding='utf-8') as f:
            for rec in self.operations:
                d = {
                    'seq': rec.seq,
                    'ts': rec.timestamp,
                    'op': rec.op,
                    'target': rec.target,
                    'duration_ms': round(rec.duration_ms, 1),
                    'result': rec.result
                }
                if rec.retries is not None:
                    d['retries'] = rec.retries
                if rec.waited_ms is not None:
                    d['waited_ms'] = rec.waited_ms
                if rec.error:
                    d['error'] = rec.error
                f.write(json.dumps(d, ensure_ascii=False) + '\n')

        evt_path = os.path.join(self.run_dir, 'events.jsonl')
        with open(evt_path, 'w', encoding='utf-8') as f:
            for evt in self.events:
                d = {
                    'seq': evt.seq,
                    'ts': evt.timestamp,
                    'type': evt.type,
                    'layer': evt.layer,
                    'message': evt.message
                }
                if evt.level:
                    d['level'] = evt.level
                if evt.component:
                    d['component'] = evt.component
                f.write(json.dumps(d, ensure_ascii=False) + '\n')

    def finalize(self, result: str = '', exit_code: int = 0):
        """
        生成 run.json 摘要。
        应在测试结束时调用（PlaywrightCLI.close() 中自动调用）。
        """
        if self._finalized:
            return
        self._finalized = True

        end_time = time.time()
        total_duration_ms = (end_time - self.start_time) * 1000

        self.result = result or ('pass' if exit_code == 0 else 'fail')
        self.exit_code = exit_code

        ok_ops = [o for o in self.operations if o.result == 'ok']
        fail_ops = [o for o in self.operations if o.result in ('fail', 'error')]
        timeout_ops = [o for o in self.operations if o.result == 'timeout']
        blocked_ops = [o for o in self.operations if o.result == 'blocked_health']
        wait_ops = [o for o in self.operations if o.op == 'wait_for_stable']

        total_wait_ms = sum(o.waited_ms or o.duration_ms for o in wait_ops)
        total_active_ms = sum(o.duration_ms for o in self.operations
                              if o.op not in ('wait_for_stable', 'wait_for_timeout'))

        error_events = [e for e in self.events if e.level == 'error']
        warn_events = [e for e in self.events if e.level in ('warning', 'warn')]
        pageerror_events = [e for e in self.events if e.type == 'pageerror']

        has_stuck = self._detect_stuck_points()

        slowest = sorted(self.operations, key=lambda o: o.duration_ms, reverse=True)[:10]

        summary = {
            'test_name': self.test_name,
            'run_id': self.run_id,
            'start_time': self.start_time_str,
            'end_time': datetime.now().isoformat(),
            'duration_ms': round(total_duration_ms, 1),
            'result': self.result,
            'exit_code': exit_code,
            'page_visited': self.page_visited,
            'username': self.username,

            'stats': {
                'total_operations': len(self.operations),
                'successful_operations': len(ok_ops),
                'failed_operations': len(fail_ops),
                'timed_out_operations': len(timeout_ops),
                'blocked_operations': len(blocked_ops),
                'total_wait_ms': round(total_wait_ms, 1),
                'total_active_ms': round(total_active_ms, 1),
                'wait_ratio': round(total_wait_ms / total_duration_ms, 3) if total_duration_ms > 0 else 0,
                'total_errors': len(error_events) + len(pageerror_events),
                'total_warnings': len(warn_events),
                'has_stuck_points': has_stuck
            },

            'error_summary': '',
            'slowest_operations': [
                {
                    'seq': o.seq,
                    'op': o.op,
                    'target': o.target,
                    'duration_ms': round(o.duration_ms, 1),
                    'result': o.result
                }
                for o in slowest[:5]
            ]
        }

        if error_events or pageerror_events:
            all_errors = pageerror_events + error_events
            summary['error_summary'] = '; '.join(
                e.message[:120] for e in all_errors[:3]
            )

        self._ensure_dir()
        run_path = os.path.join(self.run_dir, 'run.json')
        with open(run_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    def _detect_stuck_points(self) -> bool:
        """检测连续 timeout 或 blocked_health 的操作段"""
        if len(self.operations) < 3:
            return False
        consecutive = 0
        for o in self.operations:
            if o.result in ('timeout', 'blocked_health', 'fail'):
                consecutive += 1
                if consecutive >= 3:
                    return True
            else:
                consecutive = 0
        return False


class TelemetryAnalyzer:
    """
    分析历史遥测数据。

    Usage:
        analyzer = TelemetryAnalyzer('test_telemetry')
        runs = analyzer.list_runs()
        report = analyzer.stuck_points(runs[0])
    """

    def __init__(self, telemetry_dir: str = 'test_telemetry'):
        self.base_dir = telemetry_dir

    def list_runs(self, test_name: str = None) -> List[Dict]:
        """列出所有历史运行，按时间倒序"""
        runs = []
        pattern = os.path.join(self.base_dir, f'{test_name or "*"}_*', 'run.json')
        for path in sorted(glob.glob(pattern), reverse=True):
            try:
                with open(path, encoding='utf-8') as f:
                    data = json.load(f)
                    data['_path'] = path
                    data['_dir'] = os.path.dirname(path)
                    runs.append(data)
            except Exception:
                continue
        return runs

    def recent_runs(self, test_name: str = None, limit: int = 20) -> List[Dict]:
        return self.list_runs(test_name)[:limit]

    def load_operations(self, run_dir: str) -> List[Dict]:
        ops_path = os.path.join(run_dir, 'operations.jsonl')
        ops = []
        if os.path.exists(ops_path):
            with open(ops_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            ops.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return ops

    def load_events(self, run_dir: str) -> List[Dict]:
        evt_path = os.path.join(run_dir, 'events.jsonl')
        evts = []
        if os.path.exists(evt_path):
            with open(evt_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            evts.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return evts

    def stuck_points(self, run: Dict) -> List[Dict]:
        """找到卡点：连续 timeout/blocked >= 3 的操作段"""
        ops = self.load_operations(run['_dir'])
        stuck_segments = []
        current_segment = []

        for op in ops:
            if op.get('result') in ('timeout', 'blocked_health', 'fail'):
                current_segment.append(op)
            else:
                if len(current_segment) >= 3:
                    stuck_segments.append({
                        'start_seq': current_segment[0]['seq'],
                        'end_seq': current_segment[-1]['seq'],
                        'count': len(current_segment),
                        'total_ms': sum(o.get('duration_ms', 0) for o in current_segment),
                        'operations': current_segment
                    })
                current_segment = []

        if len(current_segment) >= 3:
            stuck_segments.append({
                'start_seq': current_segment[0]['seq'],
                'end_seq': current_segment[-1]['seq'],
                'count': len(current_segment),
                'total_ms': sum(o.get('duration_ms', 0) for o in current_segment),
                'operations': current_segment
            })

        return stuck_segments

    def stuck_report(self, run: Dict) -> str:
        """生成卡点的人类可读报告"""
        sps = self.stuck_points(run)
        if not sps:
            return "No stuck points detected."

        events = self.load_events(run['_dir'])
        lines = [f"[StuckPoints] {len(sps)} stuck segment(s) in {run.get('test_name', '?')}:"]

        for i, sp in enumerate(sps):
            seq_range = range(sp['start_seq'], sp['end_seq'] + 1)
            lines.append(
                f"  #{i+1} ops #{sp['start_seq']}-#{sp['end_seq']} "
                f"({sp['count']} ops, {sp['total_ms']:.0f}ms wasted)"
            )
            related_events = [
                e for e in events
                if e.get('type') in ('pageerror', 'console')
                and e.get('level') == 'error'
            ]
            if related_events:
                lines.append(f"       Related errors: {len(related_events)}")
                for e in related_events[:3]:
                    lines.append(f"         - [{e['type']}] {e['message'][:100]}")

        return '\n'.join(lines)

    def slowest_operations(self, run: Dict, top_n: int = 10) -> List[Dict]:
        """某次运行中最慢的操作"""
        ops = self.load_operations(run['_dir'])
        return sorted(
            ops,
            key=lambda o: o.get('duration_ms', 0),
            reverse=True
        )[:top_n]

    def wait_efficiency(self, run: Dict) -> Dict:
        """等待效率分析"""
        ops = self.load_operations(run['_dir'])
        wait_ops = [o for o in ops if o.get('op') == 'wait_for_stable']
        if not wait_ops:
            return {'wait_ratio': 0, 'total_wait_ms': 0, 'total_ops': 0}

        total_wait = sum(o.get('waited_ms', o.get('duration_ms', 0)) for o in wait_ops)
        total_duration = run.get('duration_ms', 1)
        return {
            'wait_ratio': round(total_wait / total_duration, 3),
            'total_wait_ms': round(total_wait, 1),
            'total_ops': len(ops),
            'wait_ops': len(wait_ops),
            'avg_wait_ms': round(total_wait / len(wait_ops), 1) if wait_ops else 0
        }

    def agent_loop_detection(self, run: Dict, threshold: int = 3) -> List[Dict]:
        """
        检测 Agent 推断-重试死循环。
        判断标准: 相同的 (operation, target) 序列重复出现 >= threshold 次。
        """
        ops = self.load_operations(run['_dir'])
        if len(ops) < threshold * 2:
            return []

        loops = []
        seen_patterns = {}

        window_size = min(4, len(ops) // 2)

        for i in range(len(ops) - window_size + 1):
            pattern = tuple(
                (o.get('op'), o.get('target'))
                for o in ops[i:i + window_size]
            )
            if pattern in seen_patterns:
                seen_patterns[pattern]['count'] += 1
                seen_patterns[pattern]['positions'].append(i)
            else:
                seen_patterns[pattern] = {
                    'pattern': [{'op': p[0], 'target': p[1]} for p in pattern],
                    'count': 1,
                    'positions': [i],
                    'window_size': window_size
                }

        for pdata in seen_patterns.values():
            if pdata['count'] >= threshold:
                loops.append(pdata)

        loops.sort(key=lambda l: l['count'], reverse=True)
        return loops

    def loop_report(self, run: Dict) -> str:
        """生成 Agent 循环检测的人类可读报告"""
        loops = self.agent_loop_detection(run)
        if not loops:
            return "No agent loops detected."

        lines = [f"[AgentLoop] {len(loops)} loop pattern(s) detected in {run.get('test_name', '?')}:"]
        for i, lp in enumerate(loops[:5]):
            ops_desc = ' → '.join(
                f"{p['op']}({p['target'][:30]})" for p in lp['pattern']
            )
            positions = lp['positions']
            lines.append(f"  #{i+1} repeated {lp['count']}x: {ops_desc}")
            lines.append(f"       at ops: {positions}")

        return '\n'.join(lines)

    def compare_runs(self, run_a: Dict, run_b: Dict) -> Dict:
        """对比两次运行"""
        ops_a = self.load_operations(run_a['_dir'])
        ops_b = self.load_operations(run_b['_dir'])

        return {
            'duration_diff_ms': round(run_b.get('duration_ms', 0) - run_a.get('duration_ms', 0), 1),
            'ops_count_diff': len(ops_b) - len(ops_a),
            'result_a': run_a.get('result', '?'),
            'result_b': run_b.get('result', '?'),
            'stats_a': run_a.get('stats', {}),
            'stats_b': run_b.get('stats', {}),
            'timeout_diff': (
                run_b.get('stats', {}).get('timed_out_operations', 0)
                - run_a.get('stats', {}).get('timed_out_operations', 0)
            )
        }

    def error_trend(self, test_name: str, limit: int = 20) -> List[Dict]:
        """某个测试最近 N 次运行的错误趋势"""
        runs = self.recent_runs(test_name, limit)
        trend = []
        for run in runs:
            trend.append({
                'run_id': run['run_id'],
                'result': run.get('result', '?'),
                'error_count': run.get('stats', {}).get('total_errors', 0),
                'error_summary': run.get('error_summary', ''),
                'duration_ms': run.get('duration_ms', 0),
                'wait_ratio': run.get('stats', {}).get('wait_ratio', 0)
            })
        return trend

    def page_stability(self, page_url: str, limit: int = 20) -> Dict:
        """某个页面的稳定性统计"""
        runs = self.recent_runs(limit=limit)
        page_runs = [r for r in runs if page_url in r.get('page_visited', '')]

        if not page_runs:
            return {'page': page_url, 'total_runs': 0}

        passed = sum(1 for r in page_runs if r.get('result') == 'pass')
        return {
            'page': page_url,
            'total_runs': len(page_runs),
            'passed': passed,
            'failed': len(page_runs) - passed,
            'pass_rate': round(passed / len(page_runs), 3),
            'avg_duration_ms': round(
                sum(r.get('duration_ms', 0) for r in page_runs) / len(page_runs), 1
            ),
            'top_errors': list(set(
                r.get('error_summary', '')
                for r in page_runs
                if r.get('error_summary')
            ))[:5]
        }
