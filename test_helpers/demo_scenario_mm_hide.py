"""demo_scenario_mm_hide.py - ScenarioRunner 回归示例
场景: mm-cross-domain (采购供应 + 所有跨领域)
流程: 展开到业务对象 → 隐藏项目云 → 取消隐藏 → 断言采购供应 BO 不受影响
验证: ①ScenarioRunner 全链路 ②render_stable 替代固定 sleep ③快照/差异/断言助手
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from test_helpers.scenario_runner import ScenarioRunner


def main():
    runner = ScenarioRunner(scenario='mm-cross-domain')
    try:
        result = runner.run([
            {'op': 'open'},
            {'op': 'expand_level', 'key': 'businessObject'},
            {'op': 'snapshot', 'name': 'init', 'watch': ['MM', 'PM']},
            # 隐藏/取消隐藏是"增量"操作 (同步 display:none, 无新 endRender),
            # 用短等待而非 render_stable (后者等待全量渲染标记, 增量操作会超时)
            {'op': 'hide', 'code': 'PM'},
            {'op': 'wait', 'ms': 1000},
            {'op': 'snapshot', 'name': 'after_hide', 'watch': ['MM', 'PM']},
            {'op': 'unhide', 'code': 'PM'},
            {'op': 'wait', 'ms': 1000},
            {'op': 'snapshot', 'name': 'after_unhide', 'watch': ['MM', 'PM']},
            # 回归断言: 隐藏/取消隐藏 PM 均不应影响 MM 的 BO 可见性
            {'op': 'diff', 'a': 'init', 'b': 'after_hide', 'watch': ['MM'], 'expect_unchanged': True},
            {'op': 'diff', 'a': 'init', 'b': 'after_unhide', 'watch': ['MM'], 'expect_unchanged': True},
            # PM 自身应被正确隐藏 (显示 assert 失败时打印明细)
            {'op': 'diff', 'a': 'init', 'b': 'after_hide', 'watch': ['PM'], 'expect_unchanged': False},
        ])
        # 打印 PM 隐藏明细 (供人工确认隐藏本身生效)
        d = result['diffs'][-1]
        pm = d.get('watch', {}).get('PM', {})
        print(f"\n[PM 隐藏效果] before={pm.get('boCount_before')} after={pm.get('boCount_after')} "
              f"hidden={len(pm.get('hidden', []))}")
        print('\n[PASS] 场景执行完成')
    except Exception as e:
        print(f'[FAIL] {e}')
        raise
    finally:
        runner.dump('test_helpers/out/mm_hide_regression.json')
        runner.close()


if __name__ == '__main__':
    main()
