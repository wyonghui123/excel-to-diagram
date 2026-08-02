"""
chart_fixtures.py - 嵌入图表 E2E 通用测试数据 + golden 基线
============================================================

[目的]
  为 chart_e2e.py 提供结构化的测试输入 (scope) 与 golden 预期 (渲染指标)。
  取代散落的一次性 _verify_*.py: 同一份 fixture 同时驱动
  数据完整性 / 颜色 / 备注 / 交互 四类断言。

[golden 生成流程] (防"测试跟着实现走")
  1. python -m test_helpers.chart_e2e --regenerate-golden
     → 打开真实图表, 记录 4 类指标 → 写 chart_fixtures_golden.json
  2. python -m test_helpers.chart_e2e
     → 读 golden → 四类断言 → PASS/FAIL 报告 + 截图
  3. golden 变更需人工 review (不是自动漂移)

[测试数据来源]
  使用现有测试环境: 产品 TTTTT000 / 版本 863 / 子域 299 (见 chart_diag.DEFAULT_SCOPE)。
  scope 是唯一的"输入", golden 是"预期输出"。改 scope 即换测试数据集。

[场景矩阵 (分级 2026-08-02)]
  | 场景名     | tier  | chartType       | scope        | 用途                          |
  |------------|-------|-----------------|--------------|-------------------------------|
  | bo_short   | L0    | businessObject  | 1 BO (SHORT) | 秒级快速回归 (颜色/结构/交互)  |
  | bo_default | L1    | businessObject  | 30 BO (DEFAULT)| 数据完整性/颜色/备注/交互主场景 |
  | sm_default | L1    | serviceModule   | 同 bo_default | SM 图数据完整性/容器          |
  | bo_large   | L2    | businessObject  | 子域全量(299)| 大规模图 (性能 + ELK + 结构)  |

[数据指纹 2026-08-02]
  golden 记录 node_codes (全量节点 code) + scope_hash (scope 规范化 hash)。
  A5 断言区分「数据漂移」与「代码回归」: 数据变了需 --regenerate-golden, 代码回归会同时暴露缺节点。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional

# 测试环境基线 (与 chart_diag.py 一致)
BASE_URL = 'http://localhost:3006'
PRODUCT_CODE = 'TTTTT000'
VERSION_ID = 863

# scope 输入 (唯一输入源)
SCOPE_BO_DEFAULT = {
    'sub_domain': [299],
    'business_object': [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                        2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                        2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]
}
SCOPE_BO_SHORT = {'sub_domain': [299], 'business_object': [3220]}
# [L2 2026-08-02] 大规模: 子域 329 全量 (150 BO, 见 _probe_subdomains.py 分布).
#   原先用子域 299 全量 (仅 30 BO, 与 bo_default 相同) 不具备大图验证意义.
#   150 BO 是默认 30 BO 的 5 倍, 验证性能 + ELK + 大图结构, 又不至于渲染过慢.
SCOPE_BO_LARGE = {'sub_domain': [329]}


def fingerprint(obj) -> str:
    """确定性指纹: 规范化 JSON (key 排序) → sha256 前 16 位.
    [数据指纹 2026-08-02] 用于区分「测试数据漂移」与「代码回归」:
      - scope 被修改 → scope_hash 不匹配 (fixture 变更)
      - 后端数据变更 → node_codes 集合不匹配 (数据漂移, 需 --regenerate-golden)"""
    canon = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'))
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()[:16]


def _make_scenario(chart_type: str, scope: Dict[str, Any],
                   key_nodes: Optional[list] = None,
                   color_group_by: str = 'domain',
                   color_scheme: str = 'default',
                   tier: str = 'L1',
                   expect_annotations: bool = False) -> Dict[str, Any]:
    """构造一个场景定义. golden 字段由 --regenerate-golden 填充.
    [分级 2026-08-02] tier: L0 smoke(秒级) / L1 常规 / L2 大规模.
    [备注 2026-08-02] expect_annotations: 该场景数据集是否应含备注 (C 类断言前置)."""
    return {
        'chart_type': chart_type,
        'product_code': PRODUCT_CODE,
        'version_id': VERSION_ID,
        'scope': scope,
        'color_group_by': color_group_by,
        'color_scheme': color_scheme,
        'tier': tier,
        'expect_annotations': expect_annotations,
        # golden 预期 (生成后填充):
        #   nodeCount / edgeCount / containerCount   (SVG 级, 来自 useDiagnostics.lastRender)
        #   key_nodes                                (必须存在的节点 code, 防漏节点)
        #   node_codes                               (数据指纹: 全量节点 code, 防数据漂移)
        #   scope_hash                               (数据指纹: scope 规范化 hash, 防 fixture 变更)
        #   node_colors                              (关键节点 {code: fill}, 来自 stepMeta.nodeColorMappings)
        #   annotation_item_count                    (.annotation-dock-panel .annotation-item 数量)
        #   annotation_type_counts                   (备注类型分布, C6)
        #   legend_item_count                        (.color-legend-panel 图例项数, B8)
        'golden': None
    }


# 通用测试数据集 (输入 + 预期结构)
CHART_FIXTURES: Dict[str, Any] = {
    'scenarios': {
        # L0 smoke: 秒级快速回归 (颜色/结构/交互关键路径)
        'bo_short': _make_scenario(
            'businessObject', SCOPE_BO_SHORT,
            key_nodes=[], tier='L0',
        ),
        # L1 常规: 30 BO 主场景 (数据完整性/颜色/备注/交互全量)
        'bo_default': _make_scenario(
            'businessObject', SCOPE_BO_DEFAULT,
            key_nodes=['DP01'],  # 占位, golden 生成时自动补全
            tier='L1',
        ),
        # L1 SM: 服务模块图 (容器结构/分组色)
        'sm_default': _make_scenario(
            'serviceModule', SCOPE_BO_DEFAULT,
            key_nodes=[], tier='L1',
        ),
        # [种子数据 2026-08-02] L1 备注主场景: 复用 bo_default scope (结构断言基线一致),
        #   但 expect_annotations=True — C 类真实备注断言 (数据源: chart_seed.py 注入的种子)
        'bo_annotations': _make_scenario(
            'businessObject', SCOPE_BO_DEFAULT,
            key_nodes=['SCN03', 'SCN01'],  # 种子目标 BO (3220/3218), 必须渲染
            tier='L1',
            expect_annotations=True,
        ),
        # L2 大规模: 整个子域 299 (性能 + ELK + 大图结构)
        'bo_large': _make_scenario(
            'businessObject', SCOPE_BO_LARGE,
            key_nodes=[], tier='L2',
        ),
    }
}

# golden 文件路径 (test_helpers/ 下)
GOLDEN_FILE = Path(__file__).resolve().parent / 'chart_fixtures_golden.json'


def load_golden() -> Dict[str, Any]:
    """加载 golden 文件. 不存在时返回空 dict (需先 --regenerate-golden)."""
    if GOLDEN_FILE.exists():
        return json.loads(GOLDEN_FILE.read_text(encoding='utf-8'))
    return {'scenarios': {}}


def save_golden(data: Dict[str, Any]) -> None:
    """保存 golden 文件 (带缩进, 便于人工 review diff)."""
    GOLDEN_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f'[chart_fixtures] golden 已写入: {GOLDEN_FILE}')


def get_scenario_golden(scenario_name: str) -> Optional[Dict[str, Any]]:
    """读取指定场景的 golden 预期."""
    golden = load_golden()
    return golden.get('scenarios', {}).get(scenario_name)


def update_scenario_golden(scenario_name: str, metrics: Dict[str, Any]) -> None:
    """把本次实测指标写入 golden (--regenerate-golden 用)."""
    golden = load_golden()
    scenarios = golden.setdefault('scenarios', {})
    scenarios[scenario_name] = metrics
    save_golden(golden)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='chart fixtures 自检')
    parser.add_argument('--show', action='store_true', help='打印当前 golden')
    args = parser.parse_args()

    print(f'可用场景: {list(CHART_FIXTURES["scenarios"].keys())}')
    print(f'golden 文件: {GOLDEN_FILE} ({"存在" if GOLDEN_FILE.exists() else "未生成, 先跑 --regenerate-golden"})')
    if args.show:
        print(json.dumps(load_golden(), indent=2, ensure_ascii=False))
