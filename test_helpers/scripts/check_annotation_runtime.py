"""
运行时检查 annotationCategories 的实际值
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
import json

from test_helpers.browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI()

    try:
        cli.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin")
        cli.wait_for_timeout(1000)
        cli.goto("http://localhost:3004/")
        cli.wait_for_timeout(3000)
        cli.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/detail/business_object/25');
            }
        """)
        cli.wait_for_timeout(3000)

        cli.click("text=添加备注")
        cli.wait_for_timeout(3000)

        # 找到 MetaList/MetaForm 组件实例中的 annotationCategories
        result = cli.evaluate("""
            () => {
                const results = {};

                // 方法1: 在 DOM 中找 "添加备注" 对话框
                const dialog = document.querySelector('.el-dialog');
                if (!dialog) return { error: 'no dialog' };

                // 通过 Vue 实例向上查找
                let comp = dialog.__vueParentComponent;
                if (!comp) comp = dialog.__vue__;
                if (!comp) {
                    // Vue 3: 尝试通过 app._instance
                    const app = document.querySelector('#app').__vue_app__;
                    // 递归查找
                    function findDialogInstance(instance) {
                        if (!instance) return null;
                        if (instance.type && instance.type.name === 'MetaList') return instance;
                        if (instance.subTree) {
                            const found = findDialogInstance(instance.subTree);
                            if (found) return found;
                        }
                        if (instance.children) {
                            for (const child of instance.children) {
                                const found = findDialogInstance(child);
                                if (found) return found;
                            }
                        }
                        return null;
                    }
                    return findDialogInstance(app._instance);
                }

                // 在组件实例树中向上查找 annotationCategories
                let current = comp;
                for (let i = 0; i < 20; i++) {
                    if (!current) break;

                    const ctx = current.ctx || current.setupState || {};
                    const data = current.data || {};

                    // 查找 annotationCategories
                    if (ctx.annotationCategories !== undefined) {
                        return {
                            found: 'ctx.annotationCategories',
                            type: String(ctx.annotationCategories),
                            value: ctx.annotationCategories
                        };
                    }
                    if (ctx._annotationCategories !== undefined) {
                        return {
                            found: 'ctx._annotationCategories',
                            value: ctx._annotationCategories
                        };
                    }
                    if (data.annotationCategories !== undefined) {
                        return {
                            found: 'data.annotationCategories',
                            value: data.annotationCategories
                        };
                    }

                    current = current.parent || current.$parent;
                }

                return { error: 'not found after 20 levels', compType: comp?.type?.name };
            }
        """)

        print("=" * 60)
        print("annotationCategories 运行时代码检查：")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 也检查控制台是否有 EnumService 缓存日志
        cli.screenshot("d:/filework/excel-to-diagram/test_results/final_06_runtime.png")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cli.close()

if __name__ == "__main__":
    main()
