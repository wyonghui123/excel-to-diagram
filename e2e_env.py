"""检查页面环境"""
import asyncio
from test_helpers.browser_auth import authenticated_page


async def main():
    async with authenticated_page(target_url='/user-permission?tab=users') as page:
        info = await page.evaluate("""() => ({
            url: window.location.href,
            origin: window.location.origin,
            hasVue: typeof window.__VUE__ !== 'undefined',
            hasPinia: typeof window.pinia !== 'undefined',
        })""")
        print(f'页面信息: {info}')
        
        # 直接在页面里 fetch
        result = await page.evaluate("""async () => {
            try {
                const r = await fetch('/api/v2/bo/user?page=1&page_size=3&ordering=-updated_at', { credentials: 'include' });
                const j = await r.json();
                return { status: r.status, success: j.success, total: j.data?.total, top3: j.data?.items?.slice(0,3).map(u => ({id: u.id, username: u.username, updated_at: u.updated_at})) };
            } catch (e) {
                return { error: String(e) };
            }
        }""")
        print(f'直接 fetch 结果: {result}')


if __name__ == '__main__':
    asyncio.run(main())
