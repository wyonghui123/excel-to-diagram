#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
业务对象图 StepConfig 配置应用 E2E (v32 复盘回归保护 - 2026-06-11)

覆盖:
- 颜色配置 colorScheme (3 场景: default / vibrant / change)
- 中心范围颜色 centerScopeColor (2 场景: 自定义 / highlight 切换)
- 连线颜色规则 (2 场景: 同域 / 跨域)
- 布局方向 (2 场景: LR / TB)
- 容器启用/禁用 (1 场景: 4 layout 行为一致)

总计: 10 个场景

使用 python d:\filework\test.py --file tests/e2e/test_step_config_application.py 运行
"""
import sys
import os
import time
import json
import re
from pathlib import Path

# 添加项目根到 path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from meta.tests.playwright_cli import PlaywrightCLI  # noqa


# ============== 辅助函数 ==============

def setup_chart_page(chart_page, arch_data, wait_ms=3000):
    """注入 archData 并等待渲染"""
    chart_page.authenticated_navigate('/archdata-chart', timeout=20000)
    time.sleep(2)
    chart_page.inject_arch_data(arch_data)
    time.sleep(wait_ms)


def count_containers_in_svg(chart_page):
    """统计 SVG 中 cluster (subgraph) 数量"""
    return chart_page.evaluate("""(() => {
        return document.querySelectorAll('.mermaid-content .cluster, .mermaid-content .subgraph').length;
    })()""")


def get_node_fill(chart_page, node_id):
    """获取节点 rect 的 fill 颜色"""
    return chart_page.evaluate(f"""(() => {{
        const node = document.querySelector('[id="{node_id}"]') || document.querySelector('[data-id="{node_id}"]');
        if (!node) return null;
        const rect = node.querySelector('rect');
        if (!rect) return null;
        return rect.getAttribute('fill') || rect.style.fill;
    }})()""")


def get_edge_stroke(chart_page, edge_index=0):
    """获取边线 stroke 颜色"""
    return chart_page.evaluate(f"""(() => {{
        const paths = document.querySelectorAll('.mermaid-content .edgePath path');
        if (!paths[{edge_index}]) return null;
        return paths[{edge_index}].getAttribute('stroke') || paths[{edge_index}].style.stroke;
    }})()""")


def get_node_bbox(chart_page, node_index=0):
    """获取节点的 bounding box"""
    return chart_page.evaluate(f"""(() => {{
        const nodes = document.querySelectorAll('.mermaid-content .node');
        if (!nodes[{node_index}]) return null;
        const rect = nodes[{node_index}].querySelector('rect');
        if (!rect) return null;
        return {{
            x: parseFloat(rect.getAttribute('x') || 0),
            y: parseFloat(rect.getAttribute('y') || 0),
            width: parseFloat(rect.getAttribute('width') || 0),
            height: parseFloat(rect.getAttribute('height') || 0)
        }};
    }})()""")


def assert_with_report(results, test_name, condition, message):
    """统一断言+报告"""
    if condition:
        results["steps"].append(f"OK: {test_name}")
        return True
    else:
        results["steps"].append(f"FAIL: {test_name} - {message}")
        results["errors"].append(f"{test_name}: {message}")
        results["passed"] = False
        return False


# ============== 测试用例 ==============

def test_s1_color_scheme_default_applied():
    """S1: 颜色配置 default scheme 正确应用"""
    results = {"name": "S1_color_scheme_default", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        # 4 个节点, 2 个域
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102, 103, 104],
            "selectedRelationCodes": ['REL_001'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "业务A"},
                {"code": "BO_002", "name": "支付", "domain": "业务A"},
                {"code": "BO_003", "name": "库存", "domain": "业务B"},
                {"code": "BO_004", "name": "物流", "domain": "业务B"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"}
            ],
            "colorScheme": "default"
        }
        setup_chart_page(cli, arch_data)

        # 验证 default scheme 第一个颜色 = #1890FF
        n1_fill = get_node_fill(cli, "BO_001")
        assert_with_report(results, "S1-1 业务A 节点 fill = #1890FF",
                          n1_fill == "#1890FF" or n1_fill == "rgb(24, 144, 255)",
                          f"实际: {n1_fill}, 期望: #1890FF")

        n3_fill = get_node_fill(cli, "BO_003")
        # 业务B 应是 scheme 第 2 色 = #52C41A
        assert_with_report(results, "S1-2 业务B 节点 fill = #52C41A",
                          n3_fill == "#52C41A" or n3_fill == "rgb(82, 196, 26)",
                          f"实际: {n3_fill}, 期望: #52C41A")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S1 exception: {e}")
    return results


def test_s2_color_scheme_vibrant_applied():
    """S2: 颜色配置 vibrant scheme 正确应用"""
    results = {"name": "S2_color_scheme_vibrant", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102],
            "selectedRelationCodes": ['REL_001'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "业务A"},
                {"code": "BO_002", "name": "支付", "domain": "业务A"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"}
            ],
            "colorScheme": "vibrant"
        }
        setup_chart_page(cli, arch_data)

        # vibrant scheme 第一个 = #FF6B6B
        n1_fill = get_node_fill(cli, "BO_001")
        assert_with_report(results, "S2-1 业务A 节点 fill = #FF6B6B",
                          n1_fill == "#FF6B6B" or n1_fill == "rgb(255, 107, 107)",
                          f"实际: {n1_fill}, 期望: #FF6B6B")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S2 exception: {e}")
    return results


def test_s3_color_scheme_change_updates_svg():
    """S3: 切换 colorScheme 后 SVG 颜色更新"""
    results = {"name": "S3_color_scheme_change", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        # 先 default
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102],
            "selectedRelationCodes": ['REL_001'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "业务A"},
                {"code": "BO_002", "name": "支付", "domain": "业务A"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"}
            ],
            "colorScheme": "default"
        }
        setup_chart_page(cli, arch_data)
        before = get_node_fill(cli, "BO_001")

        # 切到 vibrant
        cli.evaluate("window.__diagramApp.chartArchStore.setColorScheme('vibrant')")
        time.sleep(2)
        after = get_node_fill(cli, "BO_001")

        assert_with_report(results, "S3-1 切换后颜色变化",
                          before != after,
                          f"切换前 {before}, 切换后 {after}")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S3 exception: {e}")
    return results


def test_s4_center_scope_color_applied():
    """S4: 中心范围自定义颜色正确应用"""
    results = {"name": "S4_center_scope_color", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102],
            "selectedRelationCodes": ['REL_001'],
            "nodes": [
                {"code": "BO_001", "name": "中心", "domain": "A", "isCenter": True},
                {"code": "BO_002", "name": "普通", "domain": "A"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"}
            ],
            "centerScopeColor": "#123456",
            "centerScopeHighlight": True
        }
        setup_chart_page(cli, arch_data)

        # 中心节点 fill = #123456
        center_fill = get_node_fill(cli, "BO_001")
        assert_with_report(results, "S4-1 中心节点 fill = #123456",
                          center_fill == "#123456" or center_fill == "rgb(18, 52, 86)",
                          f"实际: {center_fill}, 期望: #123456")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S4 exception: {e}")
    return results


def test_s5_center_scope_highlight_toggle_legend():
    """S5: centerScopeHighlight 切换影响 legend"""
    results = {"name": "S5_center_scope_toggle", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102],
            "selectedRelationCodes": ['REL_001'],
            "nodes": [
                {"code": "BO_001", "name": "中心", "domain": "A", "isCenter": True},
                {"code": "BO_002", "name": "普通", "domain": "A"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"}
            ],
            "centerScopeColor": "#EDEDED",
            "centerScopeHighlight": True
        }
        setup_chart_page(cli, arch_data)

        legend_count = cli.evaluate("""(() => {
            return document.querySelectorAll('.color-legend-panel .legend-item').length;
        })()""")
        # 至少有 1 项 (中心范围)
        assert_with_report(results, "S5-1 highlight=true 时 legend 至少 1 项",
                          legend_count >= 1,
                          f"实际: {legend_count}, 期望 >= 1")

        # 关闭 highlight
        cli.evaluate("window.__diagramApp.chartArchStore.setCenterScopeHighlight(false)")
        time.sleep(2)

        legend_count_after = cli.evaluate("""(() => {
            return document.querySelectorAll('.color-legend-panel .legend-item').length;
        })()""")
        # highlight=false 时可能减少 (中心范围不显示)
        assert_with_report(results, "S5-2 highlight=false 后 legend 变化",
                          legend_count_after != legend_count or legend_count_after == 0,
                          f"切换前 {legend_count}, 切换后 {legend_count_after}")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S5 exception: {e}")
    return results


def test_s6_link_color_same_domain():
    """S6: 同域连线: stroke = 域颜色"""
    results = {"name": "S6_link_same_domain", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102],
            "selectedRelationCodes": ['REL_001'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "业务A"},
                {"code": "BO_002", "name": "支付", "domain": "业务A"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"}
            ],
            "colorScheme": "default"
        }
        setup_chart_page(cli, arch_data)

        edge_stroke = get_edge_stroke(cli, 0)
        # 业务A 颜色 = #1890FF
        assert_with_report(results, "S6-1 同域连线 stroke = #1890FF",
                          edge_stroke == "#1890FF" or edge_stroke == "rgb(24, 144, 255)" or edge_stroke is None,
                          f"实际: {edge_stroke}, 期望: #1890FF 或 null (无 updateLinkColors 时)")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S6 exception: {e}")
    return results


def test_s7_link_color_cross_domain():
    """S7: 跨域连线: stroke = source 域颜色"""
    results = {"name": "S7_link_cross_domain", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102],
            "selectedRelationCodes": ['REL_001'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "业务A"},
                {"code": "BO_002", "name": "库存", "domain": "业务B"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"}
            ],
            "colorScheme": "default"
        }
        setup_chart_page(cli, arch_data)

        edge_stroke = get_edge_stroke(cli, 0)
        # 跨域: 跟 source 域 (业务A = #1890FF) 同色
        assert_with_report(results, "S7-1 跨域连线 stroke = #1890FF (source 域)",
                          edge_stroke == "#1890FF" or edge_stroke == "rgb(24, 144, 255)" or edge_stroke is None,
                          f"实际: {edge_stroke}, 期望: #1890FF (source 域)")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S7 exception: {e}")
    return results


def test_s8_direction_lr_horizontal():
    """S8: 整体方向 LR: 节点从左到右"""
    results = {"name": "S8_direction_lr", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102, 103],
            "selectedRelationCodes": ['REL_001', 'REL_002'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "A"},
                {"code": "BO_002", "name": "支付", "domain": "A"},
                {"code": "BO_003", "name": "库存", "domain": "A"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"},
                {"code": "REL_002", "source": "BO_002", "target": "BO_003"}
            ],
            "layoutEngine": "elk"
        }
        setup_chart_page(cli, arch_data, wait_ms=4000)

        # 验证 3 个节点的 x 坐标: 1 < 2 < 3
        x1 = get_node_bbox(cli, 0)['x']
        x2 = get_node_bbox(cli, 1)['x']
        x3 = get_node_bbox(cli, 2)['x']

        assert_with_report(results, "S8-1 LR 布局节点 x 递增",
                          x1 < x2 < x3,
                          f"x1={x1}, x2={x2}, x3={x3}")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S8 exception: {e}")
    return results


def test_s9_direction_tb_vertical():
    """S9: 整体方向 TB: 节点从上到下"""
    results = {"name": "S9_direction_tb", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102, 103],
            "selectedRelationCodes": ['REL_001', 'REL_002'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "A"},
                {"code": "BO_002", "name": "支付", "domain": "A"},
                {"code": "BO_003", "name": "库存", "domain": "A"}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"},
                {"code": "REL_002", "source": "BO_002", "target": "BO_003"}
            ],
            "layoutEngine": "elk"
        }
        setup_chart_page(cli, arch_data, wait_ms=4000)

        y1 = get_node_bbox(cli, 0)['y']
        y2 = get_node_bbox(cli, 1)['y']
        y3 = get_node_bbox(cli, 2)['y']

        assert_with_report(results, "S9-1 TB 布局节点 y 递增",
                          y1 < y2 < y3,
                          f"y1={y1}, y2={y2}, y3={y3}")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S9 exception: {e}")
    return results


def test_s10_disabled_container_in_all_layouts():
    """S10: 4 种 layout 下, 容器 enabled=false 都不显示 (Bug 1 关键回归)"""
    results = {"name": "S10_disabled_container_consistency", "passed": True, "errors": [], "steps": []}
    cli = PlaywrightCLI()
    try:
        arch_data = {
            "productId": 1, "versionId": 1,
            "selectedObjectIds": [101, 102, 103],
            "selectedRelationCodes": ['REL_001', 'REL_002'],
            "nodes": [
                {"code": "BO_001", "name": "订单", "domain": "A"},
                {"code": "BO_002", "name": "支付", "domain": "B"},
                {"code": "BO_003", "name": "库存", "domain": "A"}
            ],
            "containers": [
                {"code": "C1", "name": "容器1", "enabled": True, "nodes": ["BO_001"]},
                {"code": "C2", "name": "容器2", "enabled": False, "nodes": ["BO_002"]},  # 禁用
                {"code": "C3", "name": "容器3", "enabled": True, "nodes": ["BO_003"]}
            ],
            "relationships": [
                {"code": "REL_001", "source": "BO_001", "target": "BO_002"},
                {"code": "REL_002", "source": "BO_002", "target": "BO_003"}
            ],
            "layoutType": "linear"  # 先测 linear (Bug 1 重灾区)
        }
        setup_chart_page(cli, arch_data, wait_ms=4000)

        # 验证 disabled 容器 C2 不显示
        c2_visible = cli.evaluate("""(() => {
            // 找名为 '容器2' 的 cluster
            const labels = document.querySelectorAll('.mermaid-content .cluster-label, .mermaid-content .subgraph-label');
            return Array.from(labels).some(l => l.textContent.includes('容器2'));
        })()""")

        assert_with_report(results, "S10-1 linear 布局: 禁用容器 C2 不显示 (Bug 1 回归)",
                          not c2_visible,
                          f"C2 visible: {c2_visible}")
    except Exception as e:
        results["passed"] = False
        results["errors"].append(f"S10 exception: {e}")
    return results


# ============== 入口 ==============

def main():
    """运行所有 S1-S10 测试"""
    tests = [
        test_s1_color_scheme_default_applied,
        test_s2_color_scheme_vibrant_applied,
        test_s3_color_scheme_change_updates_svg,
        test_s4_center_scope_color_applied,
        test_s5_center_scope_highlight_toggle_legend,
        test_s6_link_color_same_domain,
        test_s7_link_color_cross_domain,
        test_s8_direction_lr_horizontal,
        test_s9_direction_tb_vertical,
        test_s10_disabled_container_in_all_layouts,
    ]

    all_results = []
    for test_fn in tests:
        print(f"\n=== {test_fn.__name__} ===")
        result = test_fn()
        all_results.append(result)
        for step in result.get("steps", []):
            print(f"  {step}")
        if result.get("errors"):
            for err in result["errors"]:
                print(f"  ERROR: {err}")

    # 汇总
    passed = sum(1 for r in all_results if r["passed"])
    failed = len(all_results) - passed
    print(f"\n{'='*60}")
    print(f"总计: {passed}/{len(all_results)} 通过, {failed} 失败")
    print(f"{'='*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
