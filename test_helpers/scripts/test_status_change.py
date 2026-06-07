"""
状态变更自动化测试脚本

测试架构数据的状态变更功能（启用/停用/锁定等）

使用方式:
    python test_helpers/scripts/test_status_change.py /system/archdata 启用

Token 消耗: ~7.5K (vs MCP ~114K)
"""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from test_helpers.browser_auth_cli import PlaywrightCLI


def test_status_change(
    target_path: str = "/system/archdata",
    status_button_text: str = "启用"
) -> dict:
    """
    测试状态变更功能

    Args:
        target_path: 目标页面路径
        status_button_text: 状态按钮文本（如"启用"、"停用"）

    Returns:
        测试结果 dict
    """
    results = {
        "passed": False,
        "path": target_path,
        "button": status_button_text,
        "steps": [],
        "errors": [],
        "screenshot": "",
        "before": None,
        "after": None
    }

    cli = PlaywrightCLI()

    try:
        # ========== 认证 + 导航 ==========
        results["steps"].append("01-认证导航")
        cli.authenticated_navigate(
            target_path,
            wait_for_selector=".el-table",
            timeout=15000
        )
        results["steps"].append("02-页面已加载")

        # ========== 获取初始状态 ==========
        results["steps"].append("03-获取初始状态")

        # 尝试多种可能的状态标签选择器
        status_selectors = [
            ".el-table__row:first-child .el-tag",
            ".el-table__body tr:first-child .cell .el-tag",
            ".el-table__row:first-child td:nth-child(2) .el-tag"
        ]

        initial_status = None
        for selector in status_selectors:
            if cli.is_visible(selector, timeout=1000):
                initial_status = cli.get_text(selector).strip()
                results["steps"].append(f"04-初始状态: {initial_status}")
                break

        if initial_status is None:
            results["errors"].append("未找到状态标签")
            cli.screenshot("test_status_error.png")
            results["screenshot"] = "test_status_error.png"
            return results

        results["before"] = initial_status

        # ========== 点击状态按钮 ==========
        results["steps"].append("05-点击状态按钮")

        # 查找状态按钮
        button_selectors = [
            f".el-table__row:first-child .el-button:has-text('{status_button_text}')",
            f".el-table__row:first-child .el-table__actions .el-button:has-text('{status_button_text}')"
        ]

        clicked = False
        for selector in button_selectors:
            if cli.is_visible(selector, timeout=2000):
                cli.click(selector, timeout=3000)
                clicked = True
                results["steps"].append(f"06-点击按钮: {selector}")
                break

        if not clicked:
            results["errors"].append(f"未找到状态按钮: {status_button_text}")
            cli.screenshot("test_status_error.png")
            results["screenshot"] = "test_status_error.png"
            return results

        # ========== 处理确认对话框 ==========
        results["steps"].append("07-等待确认对话框")
        if cli.wait_for_selector(".el-message-box", timeout=5000):
            results["steps"].append("08-确认对话框已出现")

            # 点击确定
            cli.click(".el-message-box__btns .el-button:has-text('确定')", timeout=3000)
            results["steps"].append("09-点击确定")
        else:
            results["steps"].append("08-无确认对话框，继续")

        # ========== 等待状态更新 ==========
        results["steps"].append("10-等待状态更新")

        # 轮询等待状态变化
        max_wait = 15000
        start_time = time.time()
        status_changed = False

        while time.time() - start_time < max_wait:
            current_status = cli.get_text(status_selectors[0]).strip()
            if current_status != initial_status:
                results["after"] = current_status
                results["steps"].append(f"11-状态已变更: {initial_status} -> {current_status}")
                status_changed = True
                break
            cli.wait_for_timeout(500)

        if not status_changed:
            results["errors"].append("状态未在预期时间内变更")
            results["after"] = cli.get_text(status_selectors[0]).strip()

        # ========== 截图记录 ==========
        results["steps"].append("12-截图记录")
        cli.screenshot("test_status_result.png")
        results["screenshot"] = "test_status_result.png"

        # ========== 判定结果 ==========
        results["passed"] = status_changed and results["before"] != results["after"]
        results["steps"].append(f"13-测试{'通过' if results['passed'] else '失败'}")

    except Exception as e:
        results["errors"].append(f"异常: {str(e)}")
        cli.screenshot("test_status_error.png")
        results["screenshot"] = "test_status_error.png"

    finally:
        cli.close()

    return results


def main():
    import argparse
    import time

    parser = argparse.ArgumentParser(description="状态变更测试")
    parser.add_argument("path", nargs="?", default="/system/archdata", help="目标路径")
    parser.add_argument("button", nargs="?", default="启用", help="状态按钮文本")
    args = parser.parse_args()

    print(f"[INFO] 测试状态变更: {args.button} @ {args.path}")

    results = test_status_change(args.path, args.button)

    # 输出结果
    print("\n" + "=" * 60)
    print("测试结果:")
    print("=" * 60)
    print(f"通过: {results['passed']}")
    print(f"路径: {results['path']}")
    print(f"按钮: {results['button']}")
    print(f"变更前: {results['before']}")
    print(f"变更后: {results['after']}")
    print(f"步骤: {' -> '.join(results['steps'])}")

    if results['errors']:
        print(f"错误: {results['errors']}")

    print(f"截图: {results['screenshot']}")
    print("=" * 60)

    print("\n[JSON_RESULT]")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
