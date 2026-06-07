# -*- coding: utf-8 -*-
"""
Add and mark 11 tasks as completed in fix_tasks.json:
- 4 GAP tasks (GAP-016~019): P2 API tests
- 6 SVC tasks (SVC-001~006): service layer tests
- 1 BUG task (BUG-007): cache_monitor source bug fix
"""
import json
from datetime import datetime, timezone

PATH = r'd:\filework\fix_tasks.json'

COMPLETIONS = [
    # ── GAP-016~019: P2 API tests ──
    {
        'id': 'GAP-016',
        'category': 'test-coverage',
        'title': '新建 test_agent_api.py — agent_api 端到端测试 (5 用例)',
        'priority': 'P2',
        'related_fr': 'FR-022 Agent',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_agent_api.py::TestAgentAPI'],
        'fixed_count': 5, 'count': 5,
    },
    {
        'id': 'GAP-017',
        'category': 'test-coverage',
        'title': '新建 test_key_template_api.py — key_template_api 端到端测试 (5 用例)',
        'priority': 'P2',
        'related_fr': 'FR-key-template',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_key_template_api.py::TestKeyTemplateAPI'],
        'fixed_count': 5, 'count': 5,
    },
    {
        'id': 'GAP-018',
        'category': 'test-coverage',
        'title': '新建 test_intent_api.py — intent_api 端到端测试 (8 用例, v1+v2 双路由)',
        'priority': 'P2',
        'related_fr': 'FR-017 BO Intent',
        'difficulty': 'medium',
        'test_list': ['meta/tests/test_intent_api.py::TestIntentAPI'],
        'fixed_count': 8, 'count': 8,
    },
    {
        'id': 'GAP-019',
        'category': 'test-coverage',
        'title': '新建 test_audit_management_api.py — audit_management_api 端到端测试 (5 用例)',
        'priority': 'P2',
        'related_fr': 'audit-retry',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_audit_management_api.py::TestAuditManagementAPI'],
        'fixed_count': 5, 'count': 5,
    },
    # ── SVC-001~006: Service layer tests ──
    {
        'id': 'SVC-001',
        'category': 'test-coverage',
        'title': '新建 test_i18n_service.py — I18nService 单元测试 (8 用例, 含 YAML 加载)',
        'priority': 'P2',
        'related_fr': 'i18n',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_i18n_service.py::TestI18nService'],
        'fixed_count': 8, 'count': 8,
    },
    {
        'id': 'SVC-002',
        'category': 'test-coverage',
        'title': '新建 test_log_filter_service.py — LogFilter 单元测试 (6 用例, 含 regex 验证)',
        'priority': 'P2',
        'related_fr': 'audit-log',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_log_filter_service.py::TestLogFilterService'],
        'fixed_count': 6, 'count': 6,
    },
    {
        'id': 'SVC-003',
        'category': 'test-coverage',
        'title': '新建 test_excel_design_system.py — ExcelDesignSystem 单元测试 (10 用例, 含 openpyxl 集成)',
        'priority': 'P2',
        'related_fr': 'excel-import-export',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_excel_design_system.py::TestExcelDesignSystem'],
        'fixed_count': 10, 'count': 10,
    },
    {
        'id': 'SVC-004',
        'category': 'test-coverage',
        'title': '新建 test_cache_monitor.py — CacheMonitor 单元测试 (6 用例, 含命中率/健康度计算)',
        'priority': 'P2',
        'related_fr': 'spec-batch1',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_cache_monitor.py::TestCacheMonitor'],
        'fixed_count': 6, 'count': 6,
    },
    {
        'id': 'SVC-005',
        'category': 'test-coverage',
        'title': '新建 test_rate_limiter.py — RateLimiter 单元测试 (5 用例, 含 env 禁用验证)',
        'priority': 'P2',
        'related_fr': 'security',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_rate_limiter.py::TestRateLimiter'],
        'fixed_count': 5, 'count': 5,
    },
    {
        'id': 'SVC-006',
        'category': 'test-coverage',
        'title': '新建 test_token_blacklist_service.py — TokenBlacklistService 单元测试 (5 用例, 含过期清理)',
        'priority': 'P2',
        'related_fr': 'auth',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_token_blacklist_service.py::TestTokenBlacklistService'],
        'fixed_count': 5, 'count': 5,
    },
    # ── BUG-007: cache_monitor source bug fix ──
    {
        'id': 'BUG-007',
        'category': 'bug-fix',
        'title': 'cache_monitor.py:116 .total_seconds 漏 () → to_dict 抛 TypeError → 修复',
        'priority': 'P1',
        'related_fr': 'SVC-004 (test_cache_monitor.py 暴露)',
        'difficulty': 'low',
        'test_list': ['meta/tests/test_cache_monitor.py::TestCacheMonitor'],
        'fixed_count': 6, 'count': 6,
    },
]


def main():
    with open(PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    added = 0
    updated = 0
    existing_ids = {t.get('id') for t in data['tasks']}

    for comp in COMPLETIONS:
        if comp['id'] in existing_ids:
            for task in data['tasks']:
                if task.get('id') == comp['id']:
                    task['status'] = 'completed'
                    task['fixed_count'] = comp['fixed_count']
                    task['count'] = comp['count']
                    task['test_list'] = comp['test_list']
                    task['assigned_session'] = 'session-2026-06-07-gap-svc-batch2'
                    task['completed_at'] = now
                    updated += 1
                    print(f"  {comp['id']}: updated {comp['fixed_count']}/{comp['count']}")
                    break
        else:
            new_task = {
                'id': comp['id'],
                'category': comp['category'],
                'title': comp['title'],
                'priority': comp['priority'],
                'related_fr': comp['related_fr'],
                'difficulty': comp['difficulty'],
                'test_list': comp['test_list'],
                'count': comp['count'],
                'fixed_count': comp['fixed_count'],
                'status': 'completed',
                'assigned_session': 'session-2026-06-07-gap-svc-batch2',
                'completed_at': now,
            }
            data['tasks'].append(new_task)
            added += 1
            print(f"  {comp['id']}: added {comp['fixed_count']}/{comp['count']}")

    data['workflow']['phase'] = 'idle'
    data['workflow']['last_test_run'] = now
    data['workflow']['fixed_issues'] = data['workflow'].get('fixed_issues', 0) + added + updated

    with open(PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\nAdded {added} new tasks, updated {updated} existing")
    print(f"Total fixed_issues: {data['workflow']['fixed_issues']}")


if __name__ == '__main__':
    main()
