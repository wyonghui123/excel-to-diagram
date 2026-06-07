"""
架构数据 CRUD 自动化测试脚本

使用 PlaywrightCLI 高效执行 Token 消耗 ~7.5K (vs MCP ~114K)

使用方式:
    python test_helpers/scripts/test_archdata_crud.py

带参数:
    python test_helpers/scripts/test_archdata_crud.py /system/archdata 业务对象
"""

import sys
import json
import os

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from test_helpers.browser_auth_cli import PlaywrightCLI


def test_archdata_crud(target_path: str = "/system/archdata", entity_name: str = "业务对象") -> dict:
    """
    测试架构数据的完整 CRUD 流程

    Args:
        target_path: 目标页面路径
        entity_name: 实体名称（用于日志输出）

    Returns:
        测试结果 dict
    """
    results = {
        "passed": False,
        "entity": entity_name,
        "path": target_path,
        "steps": [],
        "errors": [],
        "screenshot": "",
        "data": {}
    }

    cli = PlaywrightCLI()

    try:
        # ========== 认证 + 导航 ==========
        results["steps"].append("01-开始认证导航")
        cli.authenticated_navigate(
            target_path,
            wait_for_selector=".el-table",
            timeout=15000
        )
        results["steps"].append("02-认证导航完成")
        results["data"]["auth"] = cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const auth = pinia._s.get('auth')
                return { loggedIn: !!auth?.user, username: auth?.user?.username }
            }
        """)

        # ========== 获取初始数据 ==========
        results["steps"].append("03-获取初始表格数据")
        initial_count = cli.evaluate("""
            () => document.querySelectorAll('.el-table__row').length
        """)
        results["data"]["initial_count"] = initial_count

        # ========== CREATE ==========
        results["steps"].append("04-点击新建按钮")
        cli.click(".el-button:has-text('新建')", timeout=5000)
        cli.wait_for_selector(".el-dialog", timeout=5000)
        results["steps"].append("05-对话框已打开")

        # 填写表单（根据实际情况调整选择器）
        results["steps"].append("06-填写表单")
        test_name = f"自动化测试_{int(os.urandom(4).hex(), 16)}"

        # 尝试不同的可能选择器
        name_input_selectors = [
            'input[placeholder*="名称"]',
            'input[placeholder*="对象"]',
            'input[placeholder*="name"]',
            '.el-dialog input:first-of-type'
        ]

        filled = False
        for selector in name_input_selectors:
            if cli.is_visible(selector, timeout=1000):
                cli.fill(selector, test_name)
                results["data"]["test_name"] = test_name
                filled = True
                results["steps"].append(f"07-使用选择器填充: {selector}")
                break

        if not filled:
            results["errors"].append("未找到名称输入框")
            cli.screenshot("test_crud_error.png")
            results["screenshot"] = "test_crud_error.png"
            return results

        # 点击确定
        results["steps"].append("08-点击确定按钮")
        cli.click(".el-dialog .el-button:has-text('确定')", timeout=5000)

        # 等待对话框关闭
        cli.wait_for_selector(".el-dialog", state="hidden", timeout=10000)
        results["steps"].append("09-对话框已关闭")

        # 等待表格更新
        cli.wait_for_timeout(2000)
        results["steps"].append("10-新建完成")

        # ========== VERIFY ==========
        results["steps"].append("11-验证新建结果")
        new_count = cli.evaluate("""
            () => document.querySelectorAll('.el-table__row').length
        """)
        results["data"]["new_count"] = new_count

        if new_count > initial_count:
            results["steps"].append("12-验证通过: 数据已新增")
        else:
            results["errors"].append(f"数据未新增: {initial_count} -> {new_count}")

        # 截图
        results["steps"].append("13-截图记录")
        cli.screenshot("test_crud_result.png")
        results["screenshot"] = "test_crud_result.png"

        # ========== 清理测试数据 ==========
        results["steps"].append("14-清理测试数据")

        # 查找并删除刚创建的数据
        cli.evaluate(f"""
            () => {{
                const rows = document.querySelectorAll('.el-table__row')
                for (const row of rows) {{
                    const text = row.textContent
                    if (text.includes('{test_name}')) {{
                        const deleteBtn = row.querySelector('.el-button:has-text("删除")')
                        if (deleteBtn) deleteBtn.click()
                        break
                    }}
                }}
            }}
        """)

        # 等待确认对话框
        if cli.is_visible(".el-message-box", timeout=3000):
            cli.click(".el-message-box__btns .el-button:has-text('确定')", timeout=3000)
            results["steps"].append("15-删除确认")

        cli.wait_for_timeout(1000)
        results["steps"].append("16-清理完成")

        # 最终判定
        results["passed"] = len(results["errors"]) == 0

    except Exception as e:
        results["errors"].append(f"异常: {str(e)}")
        cli.screenshot("test_crud_error.png")
        results["screenshot"] = "test_crud_error.png"

    finally:
        cli.close()

    return results


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(description="架构数据 CRUD 测试")
    parser.add_argument("path", nargs="?", default="/system/archdata", help="目标路径")
    parser.add_argument("entity", nargs="?", default="业务对象", help="实体名称")
    args = parser.parse_args()

    print(f"[INFO] 开始测试: {args.entity} @ {args.path}")

    results = test_archdata_crud(args.path, args.entity)

    # 输出结果
    print("\n" + "=" * 60)
    print("测试结果:")
    print("=" * 60)
    print(f"通过: {results['passed']}")
    print(f"实体: {results['entity']}")
    print(f"路径: {results['path']}")
    print(f"步骤: {' -> '.join(results['steps'])}")

    if results['errors']:
        print(f"错误: {results['errors']}")

    if results['data']:
        print(f"数据: {json.dumps(results['data'], ensure_ascii=False, indent=2)}")

    print(f"截图: {results['screenshot']}")
    print("=" * 60)

    # JSON 输出（便于程序解析）
    print("\n[JSON_RESULT]")
    print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0 if results["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
