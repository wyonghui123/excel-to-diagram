"""
检查 Vite 编译后的 annotationConfig.js 是否包含 emoji
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
import json

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()

    try:
        # 认证
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(500)

        # 加载首页（触发 Vite 编译）
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)

        # 获取 Vite 编译后的 annotationConfig.js 内容
        vite_content = cli.evaluate("""
            () => fetch('/src/composables/useMermaid/annotation/annotationConfig.js')
                .then(r => r.text())
        """)

        print("=" * 60)
        print("Vite annotationConfig.js 内容：")
        print("=" * 60)
        print(vite_content)

        print("\n" + "=" * 60)
        print("检查关键字符串：")
        print("=" * 60)
        print(f"包含 [WARNING]: {'[WARNING]' in vite_content}")
        print(f"包含 [ALERT]: {'[ALERT]' in vite_content}")
        print(f"包含 [DECORATIVE]: {'[DECORATIVE]' in vite_content}")
        print(f"包含 ℹ️: {'ℹ️' in vite_content}")
        print(f"包含 [!]: {'[!]' in vite_content}")
        print(f"包含 [!!]: {'[!!]' in vite_content}")
        print(f"包含 [i]: {'[i]' in vite_content}")
        print(f"包含 [*]: {'[*]' in vite_content}")
        print(f"包含 '重要': {'重要' in vite_content}")
        print(f"包含 '警告': {'警告' in vite_content}")
        print(f"包含 '信息': {'信息' in vite_content}")
        print(f"包含 '提示': {'提示' in vite_content}")

        # 检查是否有 emoji unicode 范围
        import re
        emoji_pattern = re.compile(
            '[\U0001F300-\U0001F9FF]'  # 杂项符号和表情
            '|[\U0001F600-\U0001F64F]'  # 表情符号
            '|[\U0001F680-\U0001F6FF]'  # 交通和地图符号
            '|[\U0001F1E0-\U0001F1FF]'  # 国旗
            '|[\U00002600-\U000027BF]'  # 杂项符号
        )
        emojis = emoji_pattern.findall(vite_content)
        if emojis:
            print(f"\n[X] 发现 emoji: {emojis}")
        else:
            print(f"\n[OK] Vite 编译文件中无 emoji")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
