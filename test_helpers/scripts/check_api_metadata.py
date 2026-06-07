"""
检查 API 返回的 annotation_category 数据是否有 emoji 或 metadata
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

        # 直接获取 annotation_category 的完整数据
        data = cli.evaluate("""
            () => fetch('/api/v1/enum-types/annotation_category/values?pageSize=100&is_active=true', {
                credentials: 'include'
            }).then(r => r.json())
        """)

        print("=" * 60)
        print("API 返回数据（完整）：")
        print("=" * 60)

        items = data.get('data', {}).get('data', [])
        print(f"总条数: {len(items)}")

        for i, item in enumerate(items):
            print(f"\n--- 分类 {i+1} ---")
            print(f"  code: {item.get('code')}")
            print(f"  name: {item.get('name')}")
            print(f"  metadata: {item.get('metadata')}")

            # 检查是否有 emoji
            name_str = str(item.get('name', ''))
            meta_str = str(item.get('metadata', ''))
            has_emoji = any(e in name_str + meta_str for e in ['[WARNING]', '[ALERT]', '[DECORATIVE]', 'ℹ', '[DECORATIVE]'])

            # 检查 metadata 是否有 icon 或 label
            meta = item.get('metadata')
            if meta:
                if isinstance(meta, dict):
                    print(f"  metadata.icon: {meta.get('icon')}")
                    print(f"  metadata.label: {meta.get('label')}")
                    print(f"  metadata.bg: {meta.get('bg')}")
                    print(f"  metadata.border: {meta.get('border')}")

            if has_emoji:
                print(f"  [X] 包含 EMOJI!")

        # 也检查 options API
        print("\n" + "=" * 60)
        print("检查 /api/v1/annotations/options")
        print("=" * 60)

        options_data = cli.evaluate("""
            () => fetch('/api/v1/annotations/options', {
                credentials: 'include'
            }).then(r => r.json()).catch(e => ({error: e.message}))
        """)
        print(json.dumps(options_data, indent=2, ensure_ascii=False)[:2000])

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
