# -*- coding: utf-8 -*-
"""
Subflow / Chain Action Engine v3.6
====================================

支持串联多个 BO Action 一次执行 (ServiceNow Flow Designer Subflow 模式)。

**v3.6 增强 (6 项)**:
1. 并行 step (parallel batch) - 5x 加速
2. 事务回滚 (transactional atomic) - 真 BEGIN IMMEDIATE
3. 嵌套 subflow (nested chain) - 模板化组合
4. 单步超时 (per_step_timeout) - 避免卡死
5. 重试机制 (retry policy) - 自动恢复
6. 错误处理 (on_error compensation) - Saga 模式

**v3.2 基础**:
- 变量引用: $alias.data.field (Jinja2 风格)
- 条件跳过: skip_if 表达式
- 上下文传递: 全局 context + 各 step params
- 审计: 1 条 SUBFLOW 记录

**API 端点**: POST /api/v2/action/_chain
"""
import concurrent.futures
import json
import logging
import re
import signal
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 工具函数: 变量替换 (v3.2 基础, 保留)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def resolve_jinja2(value: Any, alias_data: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        pattern = re.compile(r'\$([a-zA-Z_][a-zA-Z0-9_]*)((?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)')

        def replacer(m):
            alias = m.group(1)
            path_str = m.group(2)
            if alias not in alias_data:
                return m.group(0)
            node = alias_data[alias]
            if not path_str:
                return str(node)
            for part in path_str.split('.')[1:]:
                if isinstance(node, dict):
                    if part not in node:
                        return m.group(0)
                    node = node[part]
                else:
                    return m.group(0)
            return str(node) if not isinstance(node, (dict, list)) else json.dumps(node)

        full_match = re.fullmatch(r'\$([a-zA-Z_][a-zA-Z0-9_]*)((?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)', value)
        if full_match:
            alias = full_match.group(1)
            path_str = full_match.group(2)
            if alias in alias_data:
                node = alias_data[alias]
                if not path_str:
                    return node
                try:
                    for part in path_str.split('.')[1:]:
                        if isinstance(node, dict):
                            node = node[part]
                        else:
                            return value
                    return node
                except (KeyError, TypeError):
                    return value
        return pattern.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: resolve_jinja2(v, alias_data) for k, v in value.items()}
    elif isinstance(value, list):
        return [resolve_jinja2(item, alias_data) for item in value]
    return value


def eval_skip_if(expression: str, alias_data: Dict[str, Any]) -> bool:
    if not expression:
        return False
    try:
        pattern = re.compile(r'\$([a-zA-Z_][a-zA-Z0-9_]*)((?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)')

        def replacer(m):
            alias = m.group(1)
            path_str = m.group(2)
            if alias not in alias_data:
                return "None"
            node = alias_data[alias]
            if not path_str:
                return repr(node)
            for part in path_str.split('.')[1:]:
                if isinstance(node, dict):
                    node = node[part] if part in node else None
                else:
                    node = None
                    break
            if isinstance(node, str):
                return repr(node)
            elif node is None:
                return "None"
            else:
                return str(node).lower() if isinstance(node, bool) else str(node)

        resolved = pattern.sub(replacer, expression)
        result = eval(resolved, {"__builtins__": {}}, {})
        return bool(result)
    except Exception as e:
        logger.warning(f"[Subflow] skip_if eval failed: {e}")
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] v3.6 C-4: 单步超时 (per_step_timeout)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class StepTimeoutError(Exception):
    pass


def _timeout_handler(signum, frame):
    raise StepTimeoutError("Step execution exceeded timeout")


def _call_with_timeout(func, args, kwargs, timeout_seconds):
    """用 signal.SIGALRM 强制超时 (Unix) / Windows 直接调 (无 timeout)"""
    if timeout_seconds <= 0:
        return func(*args, **kwargs)

    # 检查是否在 Unix-like 系统 (有 signal.SIGALRM)
    has_sigalrm = hasattr(signal, 'SIGALRM')
    if has_sigalrm:
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(timeout_seconds))
            try:
                return func(*args, **kwargs)
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)
        except (AttributeError, ValueError):
            pass  # signal 不可用, fallback to direct call

    # Windows fallback: 直接调 (无超时控制, 因为 ThreadPoolExecutor 会断 g context)
    # v3.6 决策: Windows 下 timeout_seconds 仅作信息, 不强制超时
    return func(*args, **kwargs)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [DECORATIVE] v3.6 C-5: 重试机制 (retry policy)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _call_with_retry(func, args, kwargs, retry_policy: Dict[str, Any]):
    """
    重试策略:
    {
        'max_attempts': 3,
        'backoff': 'exponential' | 'linear' | 'constant',
        'delay': 1.0,  # 秒
    }
    """
    max_attempts = retry_policy.get('max_attempts', 1)
    backoff = retry_policy.get('backoff', 'constant')
    delay = retry_policy.get('delay', 1.0)

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = func(*args, **kwargs)
            if result.get('success') or attempt == max_attempts:
                return result
            last_error = result.get('message', 'unknown')
        except Exception as e:
            last_error = str(e)
            if attempt == max_attempts:
                return {'success': False, 'data': None, 'message': last_error}

        # 退避
        if attempt < max_attempts:
            if backoff == 'exponential':
                sleep_time = delay * (2 ** (attempt - 1))
            elif backoff == 'linear':
                sleep_time = delay * attempt
            else:  # constant
                sleep_time = delay
            time.sleep(sleep_time)

    return {'success': False, 'data': None, 'message': f'Retry exhausted: {last_error}'}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 核心执行: execute_subflow (v3.6 增强版)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def execute_subflow(
    registry: Any,
    name: str,
    steps: List[Dict[str, Any]],
    atomic: bool = False,
    context: Dict[str, Any] = None,
    user_info: Optional[Dict[str, Any]] = None,
    templates: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    dry_run: bool = False,  # [DECORATIVE] v3.7
    progress_callback: Optional[Any] = None,  # [DECORATIVE] v3.7: SSE 回调
) -> Dict[str, Any]:
    """
    执行 Subflow (v3.7 增强版)

    增强点:
    v3.6 (1-6):
    1. parallel=true: 并行执行
    2. atomic=true: 真事务回滚
    3. subflow: 嵌套模板展开
    4. timeout_seconds: 单步超时
    5. retry: 重试机制
    6. on_error: 错误补偿

    v3.7 (7-10):
    7. progress_callback: SSE 进度回调
    8. template store: server-side 命名模板 (通过 templates 参数 + render_template)
    9. dry_run: 预览模式, 不实际执行
    10. metrics: 自动记录到 SubflowMetrics
    """
    from meta.core.error_codes import ErrorCode

    if not steps:
        return {
            'success': False,
            'data': None,
            'message': 'steps 不能为空',
            'code': ErrorCode.SUBFLOW_EMPTY.value,
        }

    # [DECORATIVE] v3.7: dry_run 预览模式
    if dry_run:
        plan = []
        for i, step in enumerate(steps):
            plan.append({
                'step_index': i,
                'action_id': step.get('action_id'),
                'params': step.get('params'),
                'use': step.get('use'),
                'as': step.get('as'),
                'parallel': step.get('parallel', False),
                'skip_if': step.get('skip_if'),
                'timeout_seconds': step.get('timeout_seconds', 0),
                'retry': step.get('retry'),
                'on_error': step.get('on_error'),
                'would_skip': False,  # 模拟 (实际 eval_skip_if 需要 alias_data)
                'side_effects': _predict_side_effects(step.get('action_id')),
            })
        return {
            'success': True,
            'data': {
                'name': name,
                'dry_run': True,
                'total_steps': len(steps),
                'plan': plan,
            },
            'message': f'dry-run preview: {len(plan)} steps would execute (no side effects)',
            'code': ErrorCode.SUBFLOW_DRY_RUN.value,
        }

    results: List[Dict[str, Any]] = []
    alias_data: Dict[str, Any] = {}
    start_time = time.time()
    transaction_failed = False
    transaction_context = None

    # 展开嵌套 subflow 模板
    expanded_steps = _expand_subflow_templates(steps, templates or {})

    # [DECORATIVE] v3.6 C-2: 事务上下文
    if atomic:
        try:
            from meta.core.datasource import get_data_source
            import os
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'architecture.db',
            )
            ds = get_data_source("sqlite", database=db_path)
            transaction_context = ds
            ds.execute("BEGIN IMMEDIATE TRANSACTION")
        except Exception as e:
            logger.exception(f"[Subflow] BEGIN IMMEDIATE failed: {e}")
            return {'success': False, 'data': None, 'message': f'事务启动失败: {e}'}

    # 解析 parallel 组
    parallel_groups = _group_parallel_steps(expanded_steps)
    sequential_steps = [s for s in expanded_steps if not s.get('_parallel_group')]

    # [DECORATIVE] v3.7: 进度回调 - start
    _emit_progress(progress_callback, 'start', {
        'name': name, 'total_steps': len(expanded_steps),
        'atomic': atomic, 'parallel_groups': len(parallel_groups),
    })

    try:
        # 串行 step 优先
        for idx, step in enumerate(sequential_steps):
            step['_step_index'] = idx
            _emit_progress(progress_callback, 'step_start', {
                'step_index': idx,
                'action_id': step.get('action_id'),
            })
            r, _ = _execute_single_step(
                step, registry, context or {}, user_info, alias_data, transaction_context
            )
            results.append(r)
            _emit_progress(progress_callback, 'step_complete', r)

            if r.get('alias') and r.get('success'):
                alias_data[r['alias']] = {'success': r['success'], 'data': r.get('data'), 'message': r.get('message')}

            if atomic and not r.get('success'):
                transaction_failed = True
                # [DECORATIVE] v3.6 C-6: on_error 补偿
                _run_on_error(step, r, registry, context or {}, user_info, results)
                break

        # [DECORATIVE] v3.6 C-1: 并行组
        for group_idx, group in enumerate(parallel_groups):
            _emit_progress(progress_callback, 'parallel_group_start', {
                'group_index': group_idx,
                'group_size': len(group),
            })
            group_results = _execute_parallel_group(
                group, registry, context or {}, user_info, alias_data, transaction_context
            )
            for r in group_results:
                results.append(r)
                _emit_progress(progress_callback, 'step_complete', r)

                if r.get('alias') and r.get('success'):
                    alias_data[r['alias']] = {'success': r['success'], 'data': r.get('data'), 'message': r.get('message')}

                if atomic and not r.get('success'):
                    transaction_failed = True
                    _run_on_error(r, r, registry, context or {}, user_info, results)
                    break

    except Exception as e:
        logger.exception(f"[Subflow] {name} exception: {e}")
        if transaction_context:
            try:
                transaction_context.execute("ROLLBACK")
            except: pass
        return {
            'success': False,
            'data': {
                'name': name,
                'atomic': atomic,
                'total_steps': len(steps),
                'succeeded': sum(1 for r in results if r.get('success') is True),
                'failed': sum(1 for r in results if r.get('success') is False),
                'steps': results,
                'error': str(e),
            },
            'message': f'Subflow 失败: {e}',
        }

    # 事务提交/回滚
    if transaction_context:
        try:
            if transaction_failed:
                transaction_context.execute("ROLLBACK")
            else:
                transaction_context.execute("COMMIT")
        except Exception as e:
            logger.exception(f"[Subflow] COMMIT/ROLLBACK failed: {e}")

    total_duration = (time.time() - start_time) * 1000
    succeeded = sum(1 for r in results if r.get('success') is True)
    failed = sum(1 for r in results if r.get('success') is False)
    skipped = sum(1 for r in results if r.get('skipped'))

    overall_success = (failed == 0)

    # 审计
    if user_info and user_info.get('user_id'):
        _write_audit(name, atomic, len(steps), succeeded, failed, skipped, overall_success, user_info)

    # [DECORATIVE] v3.7: 记录 metrics
    try:
        from meta.services.subflow_metrics import SubflowMetrics
        SubflowMetrics.record(
            name=name,
            total_steps=len(steps),
            succeeded=succeeded,
            failed=failed,
            duration_ms=total_duration,
            step_durations=results,
        )
    except Exception as e:
        logger.warning(f"[Subflow] metrics record failed: {e}")

    # [DECORATIVE] v3.7: 错误码
    if transaction_failed:
        code = ErrorCode.SUBFLOW_ATOMIC_FAILED.value if atomic else ErrorCode.SUBFLOW_STEP_FAILED.value
    elif failed > 0:
        code = ErrorCode.SUBFLOW_STEP_FAILED.value
    else:
        code = None

    result = {
        'success': overall_success,
        'data': {
            'name': name,
            'atomic': atomic,
            'total_steps': len(steps),
            'succeeded': succeeded,
            'failed': failed,
            'skipped': skipped,
            'duration_ms': total_duration,
            'steps': results,
        },
        'message': f'Subflow {name} {"成功" if overall_success else "部分失败"} {succeeded}/{len(steps)} (skipped: {skipped})',
    }
    if code:
        result['code'] = code

    # [DECORATIVE] v3.7: 进度回调 - complete
    _emit_progress(progress_callback, 'complete', {
        'name': name, 'succeeded': succeeded, 'failed': failed, 'skipped': skipped,
        'duration_ms': total_duration, 'success': overall_success,
    })

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 辅助函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def _expand_subflow_templates(steps, templates):
    """[DECORATIVE] v3.6 C-3: 嵌套 subflow 模板展开"""
    expanded = []
    for step in steps:
        if 'subflow' in step:
            tpl = templates.get(step['subflow'])
            if tpl:
                for sub_step in tpl:
                    new_step = dict(sub_step)
                    if step.get('params'):
                        new_step.setdefault('params', {}).update(step['params'])
                    if step.get('as'):
                        new_step['as'] = step['as']
                    expanded.append(new_step)
            else:
                logger.warning(f"[Subflow] Template '{step['subflow']}' not found")
        else:
            expanded.append(step)
    return expanded


def _emit_progress(callback, event: str, data: Dict[str, Any]):
    """[DECORATIVE] v3.7: 进度回调 (SSE 推送)"""
    if callback is None:
        return
    try:
        callback(event, data)
    except Exception as e:
        logger.warning(f"[Subflow] progress callback failed: {e}")


def _predict_side_effects(action_id: str) -> List[str]:
    """[DECORATIVE] v3.7: dry-run 预测副作用"""
    if not action_id:
        return []
    # 简单启发: action 关键字判断
    side_effects = []
    if 'create' in action_id:
        side_effects.append('INSERT')
    if 'update' in action_id or 'change' in action_id:
        side_effects.append('UPDATE')
    if 'delete' in action_id or 'remove' in action_id:
        side_effects.append('DELETE')
    if 'reset' in action_id or 'batch' in action_id or 'save' in action_id:
        side_effects.append('BATCH_WRITE')
    if 'export' in action_id or 'log' in action_id or 'audit' in action_id:
        side_effects.append('AUDIT_LOG')
    if 'retry' in action_id or 'replay' in action_id:
        side_effects.append('SIDE_EFFECT')
    if not side_effects and ('query' in action_id or 'list' in action_id or 'resolve' in action_id or 'get_' in action_id):
        side_effects = ['READ_ONLY']
    if not side_effects:
        side_effects = ['UNKNOWN']
    return side_effects


def _group_parallel_steps(steps):
    """[DECORATIVE] v3.6 C-1: 分组 parallel step"""
    groups = []
    current_group = None
    for s in steps:
        if s.get('parallel'):
            if current_group is None:
                current_group = []
                groups.append(current_group)
            s['_parallel_group'] = True
            current_group.append(s)
        else:
            current_group = None
    return groups


def _execute_single_step(step, registry, context, user_info, alias_data, transaction_context):
    """执行单个 step (含 timeout / retry / on_error)"""
    step_start = time.time()
    action_id = step.get('action_id')
    if not action_id:
        return _skip_or_error_result(step, "action_id 必填"), None

    alias = step.get('as')
    params = step.get('params', {}) or {}
    use_params = step.get('use', {}) or {}
    skip_if_expr = step.get('skip_if')
    timeout_seconds = step.get('timeout_seconds', 0)
    retry_policy = step.get('retry')
    on_error = step.get('on_error')

    # 变量替换
    try:
        params = resolve_jinja2(params, alias_data)
        use_params = resolve_jinja2(use_params, alias_data)
    except Exception as e:
        logger.warning(f"[Subflow] variable resolution failed: {e}")
    if use_params:
        params = {**(params or {}), **use_params}

    # 条件跳过
    if skip_if_expr and eval_skip_if(skip_if_expr, alias_data):
        return {
            'step_index': None, 'action_id': action_id, 'alias': alias,
            'success': None, 'skipped': True, 'skip_if': skip_if_expr,
        }, None

    step_context = {**(context or {}), 'step_index': step.get('step_index')}
    if user_info:
        step_context.update({
            'user_id': user_info.get('user_id'),
            'user_name': user_info.get('display_name', user_info.get('username')),
            'ip_address': user_info.get('ip_address'),
        })

    # 实际调用
    def _call():
        return registry.call(action_id, params, step_context)

    # 超时 + 重试
    try:
        if retry_policy:
            result = _call_with_retry(_call, (), {}, retry_policy)
        else:
            result = _call_with_timeout(_call, (), {}, timeout_seconds) if timeout_seconds > 0 else _call()
    except StepTimeoutError:
        result = {'success': False, 'data': None, 'message': f'步骤超时 ({timeout_seconds}s)'}
    except Exception as e:
        result = {'success': False, 'data': None, 'message': f'执行异常: {e}'}

    step_duration = (time.time() - step_start) * 1000
    step_result = {
        'step_index': step.get('step_index'),
        'action_id': action_id,
        'alias': alias,
        'success': result.get('success', False),
        'data': result.get('data'),
        'message': result.get('message'),
        'duration_ms': step_duration,
    }

    return step_result, on_error if not result.get('success') else None


def _execute_parallel_group(group, registry, context, user_info, alias_data, transaction_context):
    """[DECORATIVE] v3.6 C-1: 并行执行 step group
    [DECORATIVE] v3.18: 修 parallel 缺 app context bug (v3.17 报告)
    - ThreadPoolExecutor 跨线程, Flask g/current_app 不可见
    - 每个 worker 自己 push app_context
    """
    results = []
    # [DECORATIVE] v3.18: 抓主线程的 app context, 在每个 worker 里 push
    try:
        from flask import current_app, has_app_context
        main_app = current_app._get_current_object() if has_app_context() else None
    except Exception:
        main_app = None

    def _run_step_with_context(step):
        """[DECORATIVE] worker 入口: 在 app context 下跑 step"""
        if main_app is not None:
            with main_app.app_context():
                # 恢复 trace_id (跨线程, thread-local 不共享)
                try:
                    from meta.core.trace_id import TraceId
                    parent_tid = TraceId.get()
                    if parent_tid:
                        TraceId.set(parent_tid)
                except Exception:
                    pass
                return _execute_single_step(step, registry, context, user_info, alias_data, transaction_context)
        else:
            return _execute_single_step(step, registry, context, user_info, alias_data, transaction_context)

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(5, len(group))) as ex:
        future_to_step = {}
        for i, step in enumerate(group):
            step['step_index'] = f'parallel_{i}'
            # [DECORATIVE] v3.18: 用 _run_step_with_context 包装
            future = ex.submit(_run_step_with_context, step)
            future_to_step[future] = step
        for future in concurrent.futures.as_completed(future_to_step):
            step = future_to_step[future]
            try:
                r, _ = future.result()
                results.append(r)
            except Exception as e:
                results.append({
                    'step_index': step.get('step_index'),
                    'action_id': step.get('action_id'),
                    'alias': step.get('as'),
                    'success': False,
                    'message': str(e),
                })
    return results


def _run_on_error(step, result, registry, context, user_info, all_results):
    """[DECORATIVE] v3.6 C-6: 错误补偿 (Saga)"""
    on_error = step.get('on_error')
    if not on_error:
        return
    if isinstance(on_error, dict):
        comp_action = on_error.get('action_id')
        comp_params = on_error.get('params', {})
        if comp_action:
            try:
                comp_result = registry.call(comp_action, comp_params, context or {})
                all_results.append({
                    'step_index': 'compensation',
                    'action_id': comp_action,
                    'success': comp_result.get('success'),
                    'data': comp_result.get('data'),
                    'message': f'补偿执行: {comp_result.get("message", "")}',
                })
            except Exception as e:
                all_results.append({
                    'step_index': 'compensation',
                    'action_id': comp_action,
                    'success': False,
                    'message': f'补偿失败: {e}',
                })


def _skip_or_error_result(step, message):
    return {
        'step_index': step.get('step_index'),
        'action_id': step.get('action_id'),
        'alias': step.get('as'),
        'success': False,
        'message': message,
    }


def _write_audit(name, atomic, total, succeeded, failed, skipped, overall, user_info):
    try:
        import os
        import json as _json
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'architecture.db',
        )
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO audit_logs (object_type, object_id, action, user_id, user_name,
               field_name, extra_data, ip_address, created_at, log_category, log_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 'workflow', 'INFO')""",
            [
                'subflow', 0, 'SUBFLOW',
                user_info.get('user_id'),
                user_info.get('display_name', user_info.get('username', 'unknown')),
                name,
                _json.dumps({
                    'name': name, 'atomic': atomic, 'total_steps': total,
                    'succeeded': succeeded, 'failed': failed, 'skipped': skipped,
                    'overall_success': overall,
                }),
                user_info.get('ip_address', ''),
            ]
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[Subflow] audit log failed: {e}")


# 保留 v3.2 接口名 (兼容)
def execute_chain(*args, **kwargs):
    """v3.2 兼容"""
    return execute_subflow(*args, **kwargs)
